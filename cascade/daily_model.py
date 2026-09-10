"""
Stage 1: 日线模型

用 TimesFM 进行日线级别预测，提取预测斜率。
输出 DailyResult 供 Stage 2 (1H 模型) 使用。
"""

from datetime import datetime
import numpy as np
import pandas as pd
import torch
from dataclasses import dataclass
from typing import Optional

import timesfm
from data.data_store import DataStore


@dataclass
class DailyResult:
    """日线预测结果"""
    symbol: str
    forecast: np.ndarray           # shape (22,), 22日预测价格
    horizon_slope: float           # 预测段的百分比斜率
    historical_closes: np.ndarray  # 历史真实日线收盘价
    historical_dates: pd.DatetimeIndex  # 历史真实日期
    quantile_forecast: Optional[np.ndarray] = None  # shape (22, 10)
    r_squared: float = 0.0
    slope_unreliable: bool = False


FM_COMPILED_FP_ATTR = "_fm_compiled_fp"
FP_FIELDS = (
    "max_context",
    "max_horizon",
    "normalize_inputs",
    "use_continuous_quantile_head",
    "force_flip_invariance",
    "infer_is_positive",
    "fix_quantile_crossing",
    "return_backcast",
    "per_core_batch_size",
)


def forecast_config_fp(config):
    try:
        return tuple(getattr(config, name) for name in FP_FIELDS)
    except Exception:
        return None


def ensure_compiled(model, config):
    fp = forecast_config_fp(config)
    if fp is not None and getattr(model, FM_COMPILED_FP_ATTR, None) == fp:
        return
    model.compile(config)
    if fp is not None:
        setattr(model, FM_COMPILED_FP_ATTR, fp)


class DailyModel:
    """日线预测模型"""

    _DAILY_CONFIG = timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=256,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    )

    def __init__(self, shared_model=None):
        torch.set_float32_matmul_precision("high")
        if shared_model is not None:
            self.model = shared_model
        else:
            self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                "google/timesfm-2.5-200m-pytorch"
            )
        # compile 为日线配置 (predict 中也会重新 compile，确保配置正确)
        ensure_compiled(self.model, self._DAILY_CONFIG)

    def predict(self, symbol: str, store: DataStore,
                context_days: int = 250, horizon_days: int = 22) -> DailyResult:
        """
        日线预测

        Args:
            symbol: 品种代码
            store: DataStore 实例
            context_days: 历史窗口天数
            horizon_days: 预测天数

        Returns:
            DailyResult
        """
        # 确保日线配置生效 (HourlyModel 会重编译为 XReg，每次 predict 前重新 compile)
        ensure_compiled(self.model, self._DAILY_CONFIG)

        # 读取主链日线数据
        df = store.get_main_continuous(limit=context_days)
        if df.empty:
            raise ValueError(f"{symbol}: 无日线主链数据")

        closes = df["close_price"].dropna().values.astype(np.float64)
        dates = pd.to_datetime(df["dt"]).reset_index(drop=True)

        if len(closes) < 30:
            raise ValueError(f"{symbol}: 日线数据不足 ({len(closes)} 天)")

        # 时效性检查: 日线数据滞后超过阈值时阻断 (考虑周末/假日)
        is_backtest = hasattr(store, 'cutoff_date')
        if not is_backtest:
            latest_daily = dates.iloc[-1]
            days_stale = (datetime.now() - latest_daily).days
            # 按星期放宽阈值 (日线数据更新频率低于 1H，阈值略宽)
            dow = datetime.now().weekday()  # 0=Mon ... 6=Sun
            max_allowed = 3
            if dow == 0:       # Monday: Fri data = 3 days
                max_allowed = 5
            elif dow == 1:     # Tuesday: Fri data = 4 days
                max_allowed = 6
            elif dow == 2:     # Wednesday: covers long weekend
                max_allowed = 5
            elif dow in (5, 6):  # Sat/Sun
                max_allowed = 4
            if days_stale > max_allowed:
                raise ValueError(
                    f"{symbol}: 日线数据滞后 {days_stale} 天 "
                    f"(最新: {latest_daily.strftime('%Y-%m-%d')}，阈值 {max_allowed} 天)，"
                    f"可能是节假日导致，请先采集数据"
                )

        # TimesFM 预测
        point, quantile = self.model.forecast(
            horizon=horizon_days,
            inputs=[closes],
        )

        forecast = point[0]  # shape (horizon_days,)
        quant = quantile[0]  # shape (horizon_days, 10)

        # 计算 horizon 段的百分比斜率 (线性回归)
        x = np.arange(len(forecast), dtype=float)
        coeffs = np.polyfit(x, forecast, 1)
        reg_slope = coeffs[0]
        horizon_slope = reg_slope / forecast.mean() if forecast.mean() != 0 else 0.0

        # R²: 线性拟合优度，用于判断斜率可靠性
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((forecast - y_pred) ** 2)
        ss_tot = np.sum((forecast - np.mean(forecast)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        slope_unreliable = r_squared < 0.35

        return DailyResult(
            symbol=symbol,
            forecast=forecast,
            horizon_slope=horizon_slope,
            historical_closes=closes,
            historical_dates=dates,
            quantile_forecast=quant,
            r_squared=r_squared,
            slope_unreliable=slope_unreliable,
        )


def _compute_direction_v2(daily_result, scheme) -> str:
    """R²-gated direction decision.

    If slope_unreliable (R² < 0.35), return neutral regardless of slope.
    Otherwise apply scheme threshold (or default 0.001) on horizon_slope.
    """
    if getattr(daily_result, "slope_unreliable", False):
        return "中性 → (形态分歧)"
    if scheme:
        thr_ratio = scheme.trend_threshold_pct / 100.0
    else:
        thr_ratio = 0.001
    slope = daily_result.horizon_slope
    if slope > thr_ratio:
        return "看多 ↑"
    elif slope < -thr_ratio:
        return "看空 ↓"
    else:
        return "中性 →"


    def summary(self, result: DailyResult, scheme=None) -> str:
        """生成日线预测摘要"""
        fc = result.forecast
        lines = [
            f"日线预测 ({result.symbol.upper()})",
            f"  历史窗口: {len(result.historical_closes)} 天",
            f"  预测天数: {len(fc)} 天",
            f"  预测范围: {fc.min():.1f} ~ {fc.max():.1f}",
            f"  Horizon 斜率: {result.horizon_slope * 100:+.3f}%/天",
            f"  方向: {_compute_direction_v2(result, scheme)}",
        ]
        if result.quantile_forecast is not None:
            lines.append(f"  P10 范围: {result.quantile_forecast[:, 1].min():.1f} ~ {result.quantile_forecast[:, 1].max():.1f}")
            lines.append(f"  P90 范围: {result.quantile_forecast[:, 9].min():.1f} ~ {result.quantile_forecast[:, 9].max():.1f}")
        return "\n".join(lines)
