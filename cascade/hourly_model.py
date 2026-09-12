"""
Stage 2: 1H 级联预测模型 (XReg)

使用 TimesFM 2.5 的 forecast_with_covariates() 方法，
以日线斜率和 CCL (仓单量价) 指标作为协变量，进行 1H 级别预测。
"""

import numpy as np
import pandas as pd
import torch
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import timesfm
from data.data_store import DataStore, BacktestDataStore
from .daily_model import DailyResult, ensure_compiled
from .features import build_covariate_matrix, build_combo_covariate_matrix, visualize_alignment


@dataclass
class HourlyResult:
    """1H 级联预测结果"""
    symbol: str
    point_forecast: np.ndarray       # shape (horizon,)
    quantile_forecast: np.ndarray    # shape (horizon, 10)
    covariates: dict                 # {"daily_slope": ..., "ccl_pct": ...}
    context_len: int                 # context 长度
    horizon: int                     # horizon 长度
    # 消融对比 (可选)
    baseline_forecast: Optional[np.ndarray] = None
    baseline_quantile: Optional[np.ndarray] = None
    # XReg 回退标记
    xreg_fallback: bool = False        # True 表示协变量预测失败，回退到无协变量模式


def _needs_feedstock(covariate_type: str, covariate_types: list) -> bool:
    """检测是否用到 crack_spread_* 协变量"""
    types = covariate_types or ([covariate_type] if covariate_type else [])
    return any(t and t.startswith("crack_spread_") for t in types)


def _fetch_feedstock_1h(fs_sym: str, target_store, limit: int = 480):
    """cutoff 感知读取 feedstock 1H (防穿越)

    backtest 路径(cutoff 为真实过去日期): 复用 BacktestDataStore 截止语义, 返回截止前 limit 根
    production/scan 路径: 返回最新 limit 根
    """
    cutoff = getattr(target_store, "cutoff_date", None)
    if cutoff and cutoff != "9999-12-31":
        with BacktestDataStore(fs_sym, cutoff) as s:
            df = s.get_main_contract_1h(limit=limit)
    else:
        with DataStore(fs_sym) as s:
            df = s.get_main_contract_1h(limit=limit)
    # 预热不足 warn: norm_window(120) + horizon(24) = 144 为最低有效长度 (不阻断)
    if df.empty or len(df) < 144:
        print(f"  [WARN] feedstock {fs_sym} 数据不足 ({len(df) if not df.empty else 0} < 144), 协变量前段将填 0")
    return df


class HourlyModel:
    """1H 级联预测模型 (XReg)"""

    _XREG_CONFIG = timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=128,
        return_backcast=True,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    )

    def __init__(self, shared_model=None):
        torch.set_float32_matmul_precision("high")
        if shared_model is not None:
            # [B2-1] 共享模型实例，避免重复加载 (~800MB)
            self.model = shared_model
            # compile 为 XReg 配置 (predict 中也会重新 compile，确保配置正确)
            ensure_compiled(self.model, self._XREG_CONFIG)
        else:
            self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                "google/timesfm-2.5-200m-pytorch"
            )
            ensure_compiled(self.model, self._XREG_CONFIG)

    def predict(self, symbol: str, store: DataStore,
                daily_result: DailyResult, horizon: int = 24,
                visualize: bool = True,
                covariate_type: str = "ccl",
                covariate_types: list = None,
                verbose: bool = True,
                skip_validation: bool = False,
                fill_strategy: str = "default",
                half_life: float = 12.0) -> HourlyResult:
        """
        1H 级联预测 (防穿越版)

        Args:
            symbol: 品种代码
            store: DataStore
            daily_result: Stage 1 日线预测结果
            horizon: 预测时域 (小时, 默认 24)
            visualize: 是否生成对齐可视化图
            covariate_type: 单协变量模式 (向后兼容)
            covariate_types: 多协变量组合模式 (正交铁三角)
                e.g. ["rsi_state", "oi", "hurst"]
            verbose: 是否输出校验/数据日志 (回测时设 False 提速)
            skip_validation: 跳过内部数据校验 (预检查已通过时为 True)
            fill_strategy: Horizon 填充策略, "default" (常数) 或 "decay" (衰减)

        Returns:
            HourlyResult
        """
        # 确保 XReg 配置生效 (DailyModel 会重编译为日线配置，每次 predict 前重新 compile)
        ensure_compiled(self.model, self._XREG_CONFIG)

        # 0. 数据校验 (skip_validation 仅跳过重复告警输出，错误阻断始终生效)
        from .data_validator import validate_prediction_data
        vr = validate_prediction_data(symbol, store)
        if not vr.ok:
            raise ValueError(f"{symbol}: 数据校验失败: {'; '.join(vr.errors)}")
        for w in vr.warnings:
            if verbose and not skip_validation:  # skip_validation 时不重复打印已知告警
                print(f"  [WARN] {w}")

        # 1. 读取 1H 数据 (合约对齐)
        # _MAIN 是主力连续合约 (包含夜盘和最新数据), 不应被具体合约覆盖
        is_continuous = vr.contract_1h and vr.contract_1h.endswith("_MAIN")
        if vr.contract_daily and vr.contract_1h != vr.contract_daily and not is_continuous:
            # 强制对齐: 1H 使用日线指定的合约 (仅当非连续合约时)
            if verbose:
                print(f"  [ALIGN] 1H 合约对齐: {vr.contract_1h} → {vr.contract_daily}")
            df_1h = store.get_klines_1h(contract_code=vr.contract_daily, limit=480)
        else:
            df_1h = store.get_main_contract_1h(limit=480)
            if not df_1h.empty and verbose:
                print(f"  [DATA] 使用连续合约 1H: {df_1h['contract_code'].iloc[-1]}, "
                      f"截至 {df_1h['dt'].iloc[-1]}")
        if df_1h.empty:
            raise ValueError(f"{symbol}: 无 1H 数据")

        hourly_closes = df_1h["close_price"].dropna().values.astype(np.float64)
        context_len = len(hourly_closes)

        if context_len < 48:
            raise ValueError(f"{symbol}: 1H 数据不足 ({context_len} bars)")

        # Phase 8: crack_spread 跨品种 feedstock 注入 (DI 咽喉点)
        feedstock_cache = None
        if _needs_feedstock(covariate_type, covariate_types):
            from config.crack_spread_pairs import get_crack_pair
            pair = get_crack_pair(symbol)
            if pair:
                feedstock_cache = {pair[0]: _fetch_feedstock_1h(pair[0], store)}
            elif verbose:
                print(f"  [WARN] {symbol}: crack_spread 协变量无配对, 退化为零填充")

        # 2. 构建协变量
        # 去重 (防止 ["oi", "oi"] 传入重复协变量)
        if covariate_types is not None:
            covariate_types = list(dict.fromkeys(covariate_types))
        combo_mode = covariate_types is not None and len(covariate_types) > 1

        if combo_mode:
            # 多协变量组合模式
            covariates = build_combo_covariate_matrix(
                symbol=symbol,
                store=store,
                historical_daily_closes=daily_result.historical_closes,
                predicted_daily_closes=daily_result.forecast,
                daily_dates=daily_result.historical_dates,
                horizon=horizon,
                covariate_types=covariate_types,
                feedstock_cache=feedstock_cache,
                fill_strategy=fill_strategy,
                half_life=half_life,
                df_1h=df_1h,
            )
        else:
            # 单协变量模式 (向后兼容)
            single_type = covariate_types[0] if covariate_types else covariate_type
            covariates = build_covariate_matrix(
                symbol=symbol,
                store=store,
                historical_daily_closes=daily_result.historical_closes,
                predicted_daily_closes=daily_result.forecast,
                daily_dates=daily_result.historical_dates,
                horizon=horizon,
                covariate_type=single_type,
                feedstock_cache=feedstock_cache,
                fill_strategy=fill_strategy,
                half_life=half_life,
                df_1h=df_1h,
            )

        slope_arr = covariates["daily_slope"]
        total_len = context_len + horizon

        assert len(slope_arr) == total_len, f"slope length mismatch: {len(slope_arr)} != {total_len}"

        # 3. 协变量对齐可视化 (仅第一第二协变量)
        if visualize:
            try:
                # 取第一个非 slope 的协变量用于可视化
                non_slope_keys = [k for k in covariates if k != "daily_slope"]
                if not non_slope_keys:
                    raise ValueError("无第二协变量用于可视化")
                viz_key = non_slope_keys[0]
                cov_arr_viz = covariates[viz_key]
                save_path = str(Path(__file__).parent.parent / "reports" / f"alignment_{symbol}.png")
                visualize_alignment(
                    hourly_prices=hourly_closes,
                    slope_array=slope_arr[:context_len],
                    ccl_array=cov_arr_viz[:context_len],
                    context_len=context_len,
                    save_path=save_path,
                )
            except Exception as e:
                print(f"  [WARN] 可视化失败: {e}")

        # 4. 构建 XReg 输入
        # forecast_with_covariates 需要: dict[str, list[np.ndarray]]
        dynamic_covariates = {}
        for key, arr in covariates.items():
            assert len(arr) == total_len, f"{key} length mismatch: {len(arr)} != {total_len}"
            dynamic_covariates[key] = [arr]

        # 5. Ridge 正则化: 多协变量时增大 ridge 防过拟合
        ridge_val = 0.1 if combo_mode else 0.0

        # 6. 调用 forecast_with_covariates
        xreg_fallback = False
        try:
            point_fc, quant_fc = self.model.forecast_with_covariates(
                inputs=[hourly_closes],
                dynamic_numerical_covariates=dynamic_covariates,
                xreg_mode="xreg + timesfm",
                normalize_xreg_target_per_input=True,
                ridge=ridge_val,
            )
            # 输出可能包含 backcast+forecast，只取最后 horizon 个
            raw_point = point_fc[0]
            raw_quant = quant_fc[0]
            point_forecast = raw_point[-horizon:] if len(raw_point) > horizon else raw_point
            quantile_forecast = raw_quant[-horizon:] if len(raw_quant) > horizon else raw_quant
        except Exception as e:
            print(f"  [WARN] XReg 预测失败 ({e}), 回退到无协变量模式")
            point_forecast, quantile_forecast = self._fallback_predict(hourly_closes, horizon)
            covariates = {}  # 标记协变量未使用
            xreg_fallback = True

        # 6. 消融对比: 无协变量预测 (仅在非回测模式下执行)
        baseline_point = None
        baseline_quant = None
        if visualize:
            try:
                baseline_point, baseline_quant = self._fallback_predict(hourly_closes, horizon)
            except Exception:
                baseline_point = None
                baseline_quant = None

        return HourlyResult(
            symbol=symbol,
            point_forecast=point_forecast,
            quantile_forecast=quantile_forecast,
            covariates=covariates,
            context_len=context_len,
            horizon=horizon,
            baseline_forecast=baseline_point,
            baseline_quantile=baseline_quant,
            xreg_fallback=xreg_fallback,
        )

    def _fallback_predict(self, hourly_closes: np.ndarray, horizon: int):
        """无协变量的回退预测"""
        point, quantile = self.model.forecast(
            horizon=horizon,
            inputs=[hourly_closes],
        )
        raw_p = point[0]
        raw_q = quantile[0]
        # 只取最后 horizon 个
        p = raw_p[-horizon:] if len(raw_p) > horizon else raw_p
        q = raw_q[-horizon:] if len(raw_q) > horizon else raw_q
        return p, q

    def summary(self, result: HourlyResult, daily_result: DailyResult) -> str:
        """生成级联预测摘要"""
        fc = result.point_forecast
        lines = [
            f"",
            f"1H 级联预测 ({result.symbol.upper()}) — 未来 {result.horizon} 小时",
            f"  Context: {result.context_len} bars",
            f"  日线斜率: {daily_result.horizon_slope * 100:+.3f}%/天",
            f"  预测范围: {fc.min():.1f} ~ {fc.max():.1f}",
            f"  最终预测: {fc[-1]:.1f}",
        ]

        if result.quantile_forecast is not None and result.quantile_forecast.ndim == 2:
            lines.append(f"  P10 最低: {result.quantile_forecast[:, 1].min():.1f}")
            lines.append(f"  P90 最高: {result.quantile_forecast[:, 9].max():.1f}")

        # 逐小时预测表
        lines.append(f"")
        lines.append(f"  {'Hour':<6} {'Pred':>8} {'P10':>8} {'P90':>8}")
        lines.append(f"  {'-'*34}")
        for i in range(result.horizon):
            p = fc[i]
            if result.quantile_forecast is not None and result.quantile_forecast.ndim == 2:
                p10 = result.quantile_forecast[i, 1] if i < len(result.quantile_forecast) else 0
                p90 = result.quantile_forecast[i, 9] if i < len(result.quantile_forecast) else 0
            else:
                p10 = p90 = 0
            lines.append(f"  T+{i+1:<3} {p:>8.1f} {p10:>8.1f} {p90:>8.1f}")

        # 消融对比
        if result.baseline_forecast is not None:
            bl = result.baseline_forecast
            diff = fc - bl
            same_sign = np.mean(np.sign(fc) == np.sign(bl))
            lines.append(f"")
            lines.append(f"  消融对比 (有协变量 vs 无协变量):")
            lines.append(f"    最大差异: {np.abs(diff).max():.1f}")
            lines.append(f"    平均差异: {np.abs(diff).mean():.1f}")
            lines.append(f"    方向一致率: {same_sign:.0%}")

        # 协变量统计
        if result.covariates:
            slope = result.covariates.get("daily_slope", np.array([]))
            ctx = result.context_len
            if len(slope) > ctx:
                ctx_slope = slope[:ctx]
                hz_slope = slope[ctx:]
                lines.append(f"")
                lines.append(f"  协变量统计:")
                lines.append(f"    Context slope: [{ctx_slope.min()*100:+.3f}%, {ctx_slope.max()*100:+.3f}%]")
                lines.append(f"    Horizon slope: {hz_slope.mean()*100:+.3f}% (constant)")
                # 第二协变量 (显示所有, 支持组合模式)
                for key, label in [("ccl_pct", "CCL"), ("oi_pct_change", "OI"),
                                   ("rsi_slope", "RSI斜率"), ("hourly_slope", "1H斜率"),
                                   ("rsi_state", "RSI状态"), ("pca_momentum", "PCA动量"),
                                   ("hurst", "Hurst指数"), ("regime_gated", "门控融合"),
                                   ("basis_momentum", "基差动量"), ("vor", "量仓比")]:
                    arr = result.covariates.get(key, np.array([]))
                    if len(arr) > ctx:
                        lines.append(f"    Context {label}: [{arr[:ctx].min()*100:+.2f}%, {arr[:ctx].max()*100:+.2f}%]")

        return "\n".join(lines)
