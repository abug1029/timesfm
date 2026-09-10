"""
跨周期级联预测 — 主入口

用法:
  python scripts/cascade_predict.py cf              # 单品种
  python scripts/cascade_predict.py cf rb i          # 多品种
  python scripts/cascade_predict.py --all            # 所有品种
  python scripts/cascade_predict.py cf --horizon 12  # 自定义预测时域

输出:
  每个品种报告保存到 reports/<symbol>/ 目录 (按品种分类)
  ├── reports/<symbol>/cascade_YYYYMMDD_HHmm.md   # 品种详细报告
  └── reports/summaries/YYYYMMDD_HHmm_summary.md   # 汇总报告
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# list_all_dbs 已移除
from data.data_store import DataStore
from data.config import get_name, DEFAULT_SYMBOLS
from cascade.data_validator import validate_prediction_data, detect_trading_hours, generate_trading_dates, ensure_fresh_data
from cascade.ccl_monitor import detect_anomalies as ccl_detect_anomalies
from cascade.prediction_tracker import track_prediction, get_recent_predictions
from config.prediction_scheme import (
    get_scheme, is_solidified, list_solidified,
    signal_weight, trend_direction, confidence_band, scheme_summary,
    VarietyScheme,
)
from cascade.vol_risk_filter import VolRiskFilter, apply_neutral_override_v2
from cascade.features import _calc_atr

# 品种最小变动价位表 (权威源, copilot.py 从此处导入)
TICK_SIZE = {
    'ss': 5.0, 'rb': 1.0, 'i': 0.5, 'jm': 0.5,
    'au': 0.02, 'ag': 1.0, 'cu': 10.0, 'al': 5.0,
    'm': 1.0, 'y': 2.0, 'p': 2.0, 'sr': 1.0,
    'cf': 5.0, 'ta': 2.0, 'ma': 1.0, 'fu': 1.0,
    'bu': 2.0, 'jd': 1.0, 'lh': 5.0, 'eg': 1.0,
    'cj': 5.0, 'ur': 1.0, 'fg': 1.0, 'sp': 1.0,
    'ao': 1.0, 'sh': 1.0,
    # Added: missing symbols from DEFAULT_SYMBOLS
    'sc': 0.1, 'eb': 1.0, 'pp': 1.0, 'bz': 1.0,
    'px': 1.0, 'oi': 1.0,
}


def is_vol_filter_enabled(cli_flag: bool = False) -> bool:
    """
    波动率熔断器（Vol Circuit Breaker）总开关。

    默认关闭。CLI --vol-filter / --vol-filter-neutral 或 FM_VOL_FILTER=1。
    高波时默认 Neutral Override（预测压平 → 空仓），非趋势路由。
    """
    return VolRiskFilter.is_enabled(cli_flag=cli_flag)


def _compute_direction(d_slope: float, scheme: VarietyScheme = None) -> str:
    """统一方向判断逻辑 (供 run_cascade 和 _build_report 共用)"""
    if scheme:
        thr = scheme.trend_threshold_pct
        if d_slope * 100 > thr:
            return "看多 ↑"
        elif d_slope * 100 < -thr:
            return "看空 ↓"
        else:
            return "中性 →"
    return "看多 ↑" if d_slope > 0.001 else "看空 ↓" if d_slope < -0.001 else "中性 →"


def run_cascade(symbol: str, horizon: int = 24, visualize: bool = True,
                shared_model=None, use_vol_filter: bool = False,
                vol_filter: "VolRiskFilter | None" = None,
                vol_action: str = "neutral") -> tuple:
    """
    运行单品种级联预测

    Args:
        use_vol_filter: 是否启用波动率熔断器（默认 False）。
        vol_filter: 预加载的 VolRiskFilter（多品种时复用）。
        vol_action: 熔断动作 — "neutral"（预测压平/空仓，推荐）
                    或 "slope_only"（旧：仅剥离第二协变量）。

    Returns:
        (report_text, result_data) 元组
    """
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel, HourlyResult

    scheme = get_scheme(symbol)
    tag = f"[固化方案 {scheme.scheme_type}]" if scheme else ""
    print(f"\n{'='*60}")
    print(f"[级联预测] {symbol.upper()} {tag}")
    print(f"{'='*60}")

    # 使用固化参数 (若有) 或传入参数
    ctx_bars = scheme.context_bars if scheme else 480
    ctx_days = scheme.context_days if scheme else 250
    h_days = scheme.horizon_days if scheme else 22
    actual_horizon = horizon  # 1H horizon 由调用方决定

    with DataStore(symbol) as store:
        # Stage 1: 日线模型 (共享实例，避免重复加载 ~800MB)
        print(f"\n  [Stage 1] 日线预测 (context={ctx_days}d, horizon={h_days}d)...")
        daily_model = DailyModel(shared_model=shared_model)
        daily_result = daily_model.predict(symbol, store,
                                           context_days=ctx_days, horizon_days=h_days)
        print(daily_model.summary(daily_result, scheme))

        # 读取历史数据用于报告
        from data.data_store import get_safe_daily
        daily_df = get_safe_daily(symbol, store=store)
        hourly_df = store.get_main_contract_1h(limit=ctx_bars)

        # 静态配置（生产默认）；熔断不改 XReg 维数，避免 Ridge 跳变
        cov_type = scheme.covariate_type if scheme else "ccl"
        cov_types = scheme.covariate_types if scheme else None
        half_life = scheme.half_life_bars if scheme else 12.0
        cov_label = '+'.join(cov_types) if cov_types else cov_type
        force_neutral = False
        force_slope_only = False
        vol_gate_info = None

        # Stage 2 前: 可选波动率熔断器（默认 OFF）
        if use_vol_filter:
            print(f"\n  [Vol Gating] Absolute Risk Overlay (experimental ON, "
                  f"action={vol_action})...")
            try:
                filt = vol_filter or VolRiskFilter.load_or_train()
                decision = filt.evaluate(hourly_df)
                vol_gate_info = decision.to_dict()
                print(f"    {decision.message}")
                if decision.veto:
                    if vol_action == "slope_only":
                        force_slope_only = True
                        cov_label = f"{cov_label} → slope_only [RISK]"
                        print(f"    → ACTION: strip second covariate (legacy)")
                    else:
                        force_neutral = True
                        cov_label = f"{cov_label} + NEUTRAL_OVERRIDE [RISK]"
                        print(f"    → ACTION: Neutral Override (flat forecast / no position)")
            except Exception as e:
                print(f"    [WARN] Vol Gating failed ({e}); keep static scheme")
        else:
            print(f"\n  [Vol Gating] OFF (default static scheme; "
                  f"enable: --vol-filter-neutral or FM_VOL_FILTER=1)")

        print(f"\n  [Stage 2] 1H 级联预测 (XReg, horizon={actual_horizon}h, cov={cov_label})...")
        hourly_model = HourlyModel(shared_model=daily_model.model)

        if force_slope_only:
            hourly_result = hourly_model.predict(
                symbol, store, daily_result,
                horizon=actual_horizon, visualize=visualize,
                covariate_type="slope_only",
                covariate_types=None,
                skip_validation=True,
                half_life=half_life,
            )
        else:
            # 始终用静态 scheme 跑 XReg（含将要中性覆写的情况）
            hourly_result = hourly_model.predict(
                symbol, store, daily_result,
                horizon=actual_horizon, visualize=visualize,
                covariate_type=cov_type,
                covariate_types=cov_types,
                skip_validation=True,
                half_life=half_life,
            )

        # 获取最新 1H 收盘价
        last_1h_close = float(hourly_df["close_price"].iloc[-1]) if not hourly_df.empty else None

        # 计算 ATR_14 (Wilder RMA, 取最后一个有效值)
        atr_arr = _calc_atr(hourly_df, period=14)
        atr_val = float(atr_arr[-1]) if len(atr_arr) > 0 else 0.0
        tick_size = TICK_SIZE.get(symbol, 1.0)

        # Absolute Risk Overlay: 预测压平 → delta_pred=0 → 空仓
        if force_neutral and last_1h_close is not None:
            flat_pt, flat_q = apply_neutral_override_v2(
                hourly_result.point_forecast,
                last_1h_close,
                hourly_result.quantile_forecast,
                atr=atr_val,
                tick_size=tick_size,
            )
            hourly_result = HourlyResult(
                symbol=hourly_result.symbol,
                point_forecast=flat_pt,
                quantile_forecast=flat_q if flat_q is not None else hourly_result.quantile_forecast,
                covariates=hourly_result.covariates,
                context_len=hourly_result.context_len,
                horizon=hourly_result.horizon,
                baseline_forecast=hourly_result.point_forecast,  # 保留原始预测供审计
                baseline_quantile=hourly_result.quantile_forecast,
                xreg_fallback=hourly_result.xreg_fallback,
            )
            print(f"    [RISK] Forecast flattened to base={last_1h_close:.2f} "
                  f"(horizon={actual_horizon})")

        print(hourly_model.summary(hourly_result, daily_result))

    # 生成报告
    report = _build_report(symbol, daily_result, hourly_result,
                           daily_df, hourly_df, actual_horizon, scheme,
                           vol_gate_info=vol_gate_info)

    # 构建结构化数据 (供汇总报告使用)
    fc = hourly_result.point_forecast
    d_slope = daily_result.horizon_slope

    # 可交易方向=加权1H；日线=regime 副标签（CF-01 A / signal_contract）
    from cascade.signal_contract import position_from_forecast
    weighted_pred = None
    delta_pct = None
    regime_direction = None
    if last_1h_close is not None:
        _sig = position_from_forecast(
            fc, float(last_1h_close), scheme=scheme, daily_slope=d_slope,
        )
        weighted_pred = float(_sig["weighted_pred"])
        delta_pct = (weighted_pred / float(last_1h_close) - 1) * 100
        direction = _sig["direction"]  # 可交易方向
        regime_direction = _sig.get("regime_direction")
    else:
        direction = _compute_direction(d_slope, scheme)
        regime_direction = direction

    result_data = {
        "symbol": symbol,
        "name": get_name(symbol),
        "current_price": float(last_1h_close) if last_1h_close is not None else 0,
        "direction": direction,  # 可交易方向（加权1H）
        "regime_direction": regime_direction,  # 日线状态（副标签）
        "t1": float(fc[0]),
        "t24": float(fc[-1]),            # 末日预测 (horizon 末端, 默认 T+24)
        "horizon": len(fc),              # 实际预测时域; 非 24 时 t24 实为 T+horizon
        "slope": float(d_slope * 100),
        "weighted_pred": weighted_pred,
        "delta_pct": delta_pct,
        "scheme_type": scheme.scheme_type if scheme else None,
        "dir_acc": scheme.dir_acc if scheme else None,
        "mape": scheme.mape if scheme else None,
        "vol_gate": vol_gate_info,
        "cov_label": cov_label,
        "product_note": "辅助非自动下单；交易方向=加权1H，非日线标签",
    }

    return report, result_data


def _trend_desc(closes):
    """生成趋势描述"""
    if len(closes) < 10:
        return "数据不足"
    c = np.array(closes, dtype=float)
    latest = c[-1]
    high = c.max()
    low = c.min()
    recent = c[-min(20, len(c)):]
    x = np.arange(len(recent))
    slope = np.polyfit(x, recent, 1)[0]
    pct = slope / recent.mean() * 100
    trend = "上升" if pct > 0.1 else "下降" if pct < -0.1 else "横盘"
    return (f"最新 {latest:,.0f}, "
            f"区间 {low:,.0f}~{high:,.0f} (振幅 {(high-low)/low*100:.1f}%), "
            f"近期{trend} ({pct:+.3f}%/bar), "
            f"距高点 {(latest-high)/high*100:+.1f}%, "
            f"距低点 {(latest-low)/low*100:+.1f}%")


def _monthly_table(df, date_col="dt", price_col="close_price"):
    """月度走势表"""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["month"] = df[date_col].dt.to_period("M")
    monthly = df.groupby("month")[price_col].agg(["first", "last", "min", "max"])
    lines = ["| 月份 | 开盘 | 收盘 | 最低 | 最高 | 涨跌 |",
             "|------|-----:|-----:|-----:|-----:|-----:|"]
    for idx, row in monthly.tail(6).iterrows():
        chg = (row["last"] - row["first"]) / row["first"] * 100
        arrow = "↑" if chg > 0 else "↓" if chg < 0 else "→"
        lines.append(f"| {idx} | {row['first']:,.0f} | {row['last']:,.0f} "
                     f"| {row['min']:,.0f} | {row['max']:,.0f} | {chg:+.1f}% {arrow} |")
    return "\n".join(lines)


def _build_report(symbol, daily_result, hourly_result,
                  daily_df, hourly_df, horizon,
                  scheme: VarietyScheme = None,
                  vol_gate_info: dict = None):
    """生成完整 4 板块报告 (三星品种含固化方案信息)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    name = get_name(symbol)
    fc = hourly_result.point_forecast
    d_fc = daily_result.forecast
    d_slope = daily_result.horizon_slope

    # 日线区块用 regime；交易方向在信号解读用加权1H
    regime_direction = _compute_direction(d_slope, scheme)
    direction = regime_direction  # 下文日线段落；信号表会覆盖为 trade

    # 置信区间调整 (固化方案可能乘宽)
    h_quant = hourly_result.quantile_forecast
    if scheme and h_quant is not None and h_quant.ndim == 2:
        h_quant = confidence_band(h_quant, scheme)

    lines = [
        f"# {name}({symbol.upper()}) 级联预测报告",
        f"",
    ]

    # ── 波动率熔断提示 ──
    if vol_gate_info and vol_gate_info.get("veto"):
        action = vol_gate_info.get("action", "neutral_override")
        if action == "neutral_override":
            action_desc = "预测压平 / 空仓（Neutral Override）"
        else:
            action_desc = "剥离第二协变量（slope-only，legacy）"
        lines.extend([
            "> **[RISK] High Volatility Predicted** — Absolute Risk Overlay 已触发：",
            f"> {action_desc}，vol_prob="
            f"{vol_gate_info.get('vol_prob', float('nan')):.2%}。"
            "高波无序期不承担方向风险。",
            "",
        ])
    elif vol_gate_info and vol_gate_info.get("enabled"):
        lines.append(
            f"> Vol Gating 已评估：vol_prob="
            f"{vol_gate_info.get('vol_prob', float('nan')):.2%} "
            f"(thr={vol_gate_info.get('threshold', 0):.0%})，未熔断。"
        )
        lines.append("")

    # ── 固化方案卡片 (三星品种) ──
    if scheme:
        lines.append("## 固化预测方案")
        lines.append("")
        lines.append(scheme_summary(scheme))
        lines.append("")

    lines.extend([
        f"| 字段 | 值 |",
        f"|------|-----|",
        f"| 生成日期 | {now} |",
        f"| 模型 | TimesFM 2.5 级联 (日线→1H XReg) |",
        f"| 预测时域 | {horizon} 小时 |",
        f"",
    ])

    # ── 预测输入数据 ──
    lines.append("## 预测输入数据")
    lines.append("")
    lines.append("| 数据 | 最新值 | 时间 |")
    lines.append("|------|------:|------|")
    if not daily_df.empty:
        d_last_price = float(daily_df["close_price"].iloc[-1])
        d_last_dt = pd.to_datetime(daily_df["dt"].iloc[-1]).strftime("%Y-%m-%d")
        lines.append(f"| 日线收盘价 | {d_last_price:,.1f} | {d_last_dt} |")
    if not hourly_df.empty:
        h_last_price = float(hourly_df["close_price"].iloc[-1])
        h_last_dt = pd.to_datetime(hourly_df["dt"].iloc[-1]).strftime("%Y-%m-%d %H:%M")
        lines.append(f"| 1H 收盘价 | {h_last_price:,.1f} | {h_last_dt} |")
        lines.append(f"| 1H 数据量 | {len(hourly_df)} bars | — |")
    lines.append("")

    # ── 一、过往日线走势 ──
    lines.append("## 一、过往日线走势")
    lines.append("")
    if not daily_df.empty:
        d_closes = daily_df["close_price"].dropna().values
        d_dates = pd.to_datetime(daily_df["dt"])
        lines.append(f"**数据范围**: {d_dates.iloc[0].strftime('%Y-%m-%d')} ~ "
                     f"{d_dates.iloc[-1].strftime('%Y-%m-%d')} ({len(d_closes)} 个交易日)")
        lines.append("")
        lines.append(f"**概况**: {_trend_desc(d_closes)}")
        lines.append("")
        lines.append("### 近 6 个月月度走势")
        lines.append("")
        lines.append(_monthly_table(daily_df))
        lines.append("")
    else:
        lines.append("无日线历史数据")
        lines.append("")

    # ── 二、未来日线走势预测 ──
    lines.append("## 二、未来日线走势预测")
    lines.append("")
    lines.append(
        f"**预测斜率**: {d_slope*100:+.3f}%/天 | **日线状态(副)**: {regime_direction}"
    )
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 预测天数 | {len(d_fc)} 天 |")
    lines.append(f"| 预测范围 | {d_fc.min():,.0f} ~ {d_fc.max():,.0f} |")
    lines.append(f"| 首日预测 | {d_fc[0]:,.0f} |")
    lines.append(f"| 末日预测 | {d_fc[-1]:,.0f} |")
    if daily_result.quantile_forecast is not None:
        lines.append(f"| P10 范围 | {daily_result.quantile_forecast[:, 1].min():,.0f} ~ "
                     f"{daily_result.quantile_forecast[:, 1].max():,.0f} |")
        lines.append(f"| P90 范围 | {daily_result.quantile_forecast[:, 9].min():,.0f} ~ "
                     f"{daily_result.quantile_forecast[:, 9].max():,.0f} |")
    lines.append("")
    lines.append("### 日线预测走势")
    lines.append("")
    # 生成未来交易日 (跳过周末)
    last_daily_dt = pd.to_datetime(daily_df["dt"].iloc[-1]) if not daily_df.empty else None
    if last_daily_dt is not None:
        future_days = pd.bdate_range(start=last_daily_dt + pd.Timedelta(days=1), periods=len(d_fc))
    else:
        future_days = None
    lines.append("| 日期 | 天 | 预测价 | P10 | P50 | P90 |")
    lines.append("|------|---:|------:|-----:|-----:|-----:|")
    for i in range(len(d_fc)):
        if i in [0, 4, 9, 14, 19, 21] or i == len(d_fc) - 1:
            p = d_fc[i]
            q = daily_result.quantile_forecast[i] if daily_result.quantile_forecast is not None else [0]*10
            date_str = future_days[i].strftime("%m-%d") if future_days is not None else "—"
            lines.append(f"| {date_str} | D+{i+1} | {p:,.0f} | {q[1]:,.0f} | {q[5]:,.0f} | {q[9]:,.0f} |")
    lines.append("")

    # ── 三、1小时级别过往走势 ──
    lines.append("## 三、1 小时级别过往走势")
    lines.append("")
    if not hourly_df.empty:
        h_closes = hourly_df["close_price"].dropna().values
        h_dates = pd.to_datetime(hourly_df["dt"])
        lines.append(f"**数据范围**: {h_dates.iloc[0].strftime('%Y-%m-%d %H:%M')} ~ "
                     f"{h_dates.iloc[-1].strftime('%Y-%m-%d %H:%M')} ({len(h_closes)} 根 K 线)")
        lines.append("")
        lines.append(f"**概况**: {_trend_desc(h_closes)}")
        lines.append("")
        # CCL 统计
        if "ccl_value" in hourly_df.columns and hourly_df["ccl_value"].notna().any():
            h_ccl = hourly_df["ccl_value"].dropna().values
            if len(h_ccl) > 1:
                h_base = hourly_df["open_interest"].dropna().values if "open_interest" in hourly_df.columns else np.ones_like(h_ccl)
                ccl_pct = np.where(h_base > 0, h_ccl / h_base, 0)
                ccl_pct = np.clip(ccl_pct, -0.3, 0.3)
                lines.append(f"**CCL (仓单量价)**: 均值 {ccl_pct.mean()*100:+.2f}%, "
                             f"范围 [{ccl_pct.min()*100:+.2f}%, {ccl_pct.max()*100:+.2f}%]")
                lines.append("")
        elif "open_interest" in hourly_df.columns:
            h_oi = hourly_df["open_interest"].dropna().values
            if len(h_oi) > 1:
                oi_chg = np.diff(h_oi) / h_oi[:-1]
                oi_chg = np.clip(oi_chg, -0.3, 0.3)
                lines.append(f"**持仓变化**: 均值 {oi_chg.mean()*100:+.2f}%, "
                             f"范围 [{oi_chg.min()*100:+.2f}%, {oi_chg.max()*100:+.2f}%]")
                lines.append("")
    else:
        lines.append("无 1H 历史数据")
        lines.append("")

    # ── 四、1小时级别走势预测 ──
    lines.append("## 四、1 小时级别走势预测")
    lines.append("")
    lines.append(f"**Context**: {hourly_result.context_len} bars | "
                 f"**Horizon**: {horizon} 小时 | "
                 f"**日线斜率协变量**: {d_slope*100:+.3f}%/天 (日线状态: {regime_direction})")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 预测范围 | {fc.min():,.0f} ~ {fc.max():,.0f} |")
    lines.append(f"| 最终预测 (T+{horizon}) | {fc[-1]:,.0f} |")
    lines.append(f"| 预测均值 | {fc.mean():,.0f} |")
    lines.append("")

    # 逐小时表
    lines.append("### 逐小时预测")
    lines.append("")
    # 生成未来交易时间 (基于历史交易时段, 跳过非交易时点和周末)
    last_1h_dt = pd.to_datetime(hourly_df["dt"].iloc[-1]) if not hourly_df.empty else None
    valid_hours = detect_trading_hours(hourly_df) if not hourly_df.empty else []
    if last_1h_dt is not None:
        future_hours = generate_trading_dates(last_1h_dt, horizon, valid_hours)
    else:
        future_hours = None
    lines.append("| 时间 | Hour | Pred | P10 | P50 | P90 | 信号权重 |")
    lines.append("|------|-----:|-----:|-----:|-----:|-----:|:--------:|")

    # 计算信号权重 (固化方案)
    weights = signal_weight(horizon, scheme) if scheme else None

    for i in range(horizon):
        p = fc[i]
        if h_quant is not None and h_quant.ndim == 2:
            p10 = h_quant[i, 1]
            p50 = h_quant[i, 5]
            p90 = h_quant[i, 9]
        else:
            p10 = p50 = p90 = 0
        w_str = f"{weights[i]:.2f}" if weights is not None else "—"
        time_str = future_hours[i].strftime("%m-%d %H:%M") if future_hours is not None else "—"
        lines.append(f"| {time_str} | T+{i+1} | {p:,.0f} | {p10:,.0f} | {p50:,.0f} | {p90:,.0f} | {w_str} |")
    lines.append("")

    # 协变量摘要
    if hourly_result.covariates:
        slope_arr = hourly_result.covariates.get("daily_slope", [])
        # 动态获取第二协变量 (CCL 或 OI)
        second_cov_key = None
        second_cov_label = None
        for key, label in [("ccl_pct", "CCL (仓单量价)"), ("oi_pct_change", "OI (持仓变化)")]:
            if key in hourly_result.covariates and len(hourly_result.covariates[key]) > 0:
                second_cov_key = key
                second_cov_label = label
                break
        ctx = hourly_result.context_len
        lines.extend(["### 协变量摘要", "",
                      "| 协变量 | Context (历史) | Horizon (预测) |",
                      "|--------|---------|---------|"])
        if len(slope_arr) > ctx:
            cs = slope_arr[:ctx]
            hs = slope_arr[ctx:]
            lines.append(f"| 日线斜率 | [{cs.min()*100:+.3f}%, {cs.max()*100:+.3f}%] | {hs.mean()*100:+.3f}% (constant) |")
        if second_cov_key is not None:
            cc = hourly_result.covariates[second_cov_key][:ctx]
            lines.append(f"| {second_cov_label} | [{cc.min()*100:+.2f}%, {cc.max()*100:+.2f}%] | 0 (zero-filled) |")
        lines.append("")

    # 消融对比
    if hourly_result.baseline_forecast is not None:
        bl = hourly_result.baseline_forecast
        diff = fc - bl
        lines.extend(["### 消融对比 (有/无协变量)", "",
                      "| 指标 | 值 |", "|------|-----|",
                      f"| 最大差异 | {abs(diff).max():,.0f} |",
                      f"| 平均差异 | {abs(diff).mean():,.0f} |",
                      f"| 方向一致率 | {np.mean(np.sign(fc) == np.sign(bl)):.0%} |",
                      ""])

    # ── 信号解读：可交易方向 = 加权1H（CF-01 A）──
    if scheme:
        lines.extend(["### 信号解读 (固化方案)", "",
                      "| 指标 | 值 |", "|------|-----|"])
        last_1h_close = float(hourly_df["close_price"].iloc[-1]) if not hourly_df.empty else float(fc[0])
        from cascade.signal_contract import position_from_forecast
        _sig = position_from_forecast(fc, last_1h_close, scheme=scheme, daily_slope=d_slope)
        weighted_pred = float(_sig["weighted_pred"])
        trade_dir = _sig["direction"]
        lines.append(f"| 加权预测价 | {weighted_pred:,.0f} |")
        lines.append(f"| 最终预测 (T+{horizon}) | {fc[-1]:,.0f} |")
        if scheme.short_horizon_only:
            lines.append(f"| 有效信号段 | T+1 ~ T+{horizon//2} (短段型) |")
        else:
            lines.append(f"| 有效信号段 | T+1 ~ T+{horizon} (全段型, 按衰减加权) |")
        delta_pct = (weighted_pred / last_1h_close - 1) * 100
        lines.append(f"| 预期变动 | {delta_pct:+.2f}% |")
        lines.append(f"| **可交易方向** | **{trade_dir}** |")
        lines.append(f"| 日线状态(副) | {_sig.get('regime_direction') or regime_direction} |")
        lines.append(f"| 信号可信度 | DirAcc={scheme.dir_acc:.0%}(展示) MAPE={scheme.mape:.2f}% |")
        lines.append(f"| 产品定位 | 主观辅助，非自动下单 |")
        lines.append("")

        # ── 历史预测对比 ──
        recent = get_recent_predictions(symbol, 5)
        if recent:
            lines.extend([
                "### 历史预测对比 (最近5次)",
                "",
                "| 时间 | 当前价 | T+1预测 | T+24预测 | 方向 |",
                "|------|--------|---------|----------|:----:|",
            ])
            for r in reversed(recent):
                t1_err = f"{r.t1_error:+.2f}%" if r.t1_error is not None else "-"
                lines.append(
                    f"| {r.timestamp} | {r.current_price:,.0f} | {r.pred_t1:,.0f} | "
                    f"{r.pred_t24:,.0f} | {r.direction} |"
                )
            lines.append("")

    # ── CCL 异动预警 ──
    try:
        ccl_alert = ccl_detect_anomalies(symbol, preloaded_df=hourly_df)
        lines.append("")
        lines.append(ccl_alert.format_report())
        lines.append("")
    except Exception as e:
        lines.append("")
        lines.append(f"### CCL 异动预警 ⚠️ 检测失败: {e}")
        lines.append("")

    lines.extend([
        f"---", f"",
        f"> **风险提示**: 本预测基于 TimesFM 统计模型 + XReg 跨周期协变量，不含基本面信息，仅供参考，不构成投资建议。",
        f"",
    ])
    return "\n".join(lines)


def _build_summary(results: list, ts: str) -> str:
    """
    生成汇总报告

    Args:
        results: 包含成功和失败的预测结果列表
            成功: {"symbol": "cf", "name": "棉花", "direction": "看空 ↓", ...}
            失败: {"symbol": "cf", "error": "..."}
        ts: 时间戳字符串 (YYYYMMDD_HHmm)

    Returns:
        Markdown 格式的汇总报告
    """
    # 分离成功和失败的结果
    success = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    # 解析时间戳
    dt = datetime.strptime(ts, "%Y%m%d_%H%M")
    ts_display = dt.strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 级联预测汇总报告",
        "",
        "| 字段 | 值 |",
        "|------|-----|",
        f"| 运行时间 | {ts_display} |",
        f"| 预测品种 | {len(results)} |",
        f"| 成功 | {len(success)} |",
        f"| 跳过/失败 | {len(failed)} |",
        "",
    ]

    # ── 方向总览 ──
    lines.extend([
        "## 方向总览",
        "",
        "| 品种 | 方向 | T+1 | T+24 | 预期变动 | 信号可信度 |",
        "|------|:----:|----:|-----:|--------:|:--------:|",
    ])

    # 按方向排序: 看多 → 中性 → 看空
    direction_order = {"看多 ↑": 0, "中性 →": 1, "看空 ↓": 2}
    sorted_results = sorted(success, key=lambda r: direction_order.get(r.get("direction", ""), 9))

    for r in sorted_results:
        symbol = r["symbol"].upper()
        name = r["name"]
        direction = r.get("direction", "—")
        t1 = f"{r['t1']:,.0f}" if "t1" in r else "—"
        t24 = f"{r['t24']:,.0f}" if "t24" in r else "—"

        # 预期变动 (仅固化品种)
        delta_pct = r.get("delta_pct")
        delta_str = f"{delta_pct:+.2f}%" if delta_pct is not None else "—"

        # 信号可信度 (仅固化品种)
        dir_acc = r.get("dir_acc")
        mape = r.get("mape")
        if dir_acc is not None and mape is not None:
            confidence = f"DirAcc={dir_acc:.0%}, MAPE={mape:.2f}%"
        else:
            confidence = "—"

        lines.append(f"| {symbol} {name} | {direction} | {t1} | {t24} | {delta_str} | {confidence} |")

    lines.append("")

    # ── 分类统计 ──
    lines.extend([
        "## 分类统计",
        "",
        "| 方向 | 品种数 | 品种列表 |",
        "|:----:|:------:|:---------|",
    ])

    # 按方向分组
    bullish = [r for r in success if r.get("direction") == "看多 ↑"]
    bearish = [r for r in success if r.get("direction") == "看空 ↓"]
    neutral = [r for r in success if r.get("direction") == "中性 →"]

    for label, group in [("看多 ↑", bullish), ("看空 ↓", bearish), ("中性 →", neutral)]:
        symbols_str = ", ".join(r["symbol"].upper() for r in group) if group else "—"
        lines.append(f"| {label} | {len(group)} | {symbols_str} |")

    lines.append("")

    # ── 三星品种重点信号 ──
    solidified_results = [r for r in success if r.get("scheme_type") is not None]
    if solidified_results:
        lines.extend([
            "## 三星品种重点信号",
            "",
            "| 品种 | 类型 | DirAcc | MAPE | 加权预测 | 预期变动 | 判断 |",
            "|------|:----:|:------:|:----:|--------:|--------:|:----:|",
        ])

        for r in solidified_results:
            symbol = r["symbol"].upper()
            name = r["name"]
            scheme_type = r.get("scheme_type", "—")
            dir_acc = f"{r['dir_acc']:.0%}" if r.get("dir_acc") is not None else "—"
            mape = f"{r['mape']:.2f}%" if r.get("mape") is not None else "—"
            weighted_pred = f"{r['weighted_pred']:,.0f}" if r.get("weighted_pred") is not None else "—"
            delta_pct = f"{r['delta_pct']:+.2f}%" if r.get("delta_pct") is not None else "—"
            direction = r.get("direction", "—")

            lines.append(f"| {symbol} {name} | {scheme_type} | {dir_acc} | {mape} | {weighted_pred} | {delta_pct} | {direction} |")

        lines.append("")

    # ── 失败/跳过品种 ──
    if failed:
        lines.extend([
            "## 跳过/失败品种",
            "",
            "| 品种 | 原因 |",
            "|------|------|",
        ])
        for r in failed:
            symbol = r["symbol"].upper()
            error = r.get("error", "未知错误")
            # 截断过长的错误信息
            if len(error) > 80:
                error = error[:77] + "..."
            lines.append(f"| {symbol} | {error} |")
        lines.append("")

    # ── 详细报告链接 ──
    if success:
        lines.extend([
            "## 详细报告链接",
            "",
        ])
        for r in sorted_results:
            symbol = r["symbol"]
            name = r["name"]
            lines.append(f"- [{symbol.upper()} {name}](cascade_{symbol}.md)")
        lines.append("")

    lines.extend([
        "---",
        "",
        "> **风险提示**: 本预测基于 TimesFM 统计模型 + XReg 跨周期协变量，不含基本面信息，仅供参考，不构成投资建议。",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="跨周期级联预测")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--all", action="store_true", help="所有品种")
    parser.add_argument("--three-star", action="store_true",
                        help="仅运行三星固化品种 (SS/UR/SR)")
    parser.add_argument("--horizon", type=int, default=24, help="预测时域 (小时, 默认 24)")
    parser.add_argument("--no-viz", action="store_true", help="跳过可视化")
    parser.add_argument("--collect", action="store_true",
                        help="预测前显式采集所有品种的最新数据 (日线+1H)")
    parser.add_argument("--collect-if-stale", type=int, default=0,
                        help="数据滞后超过 N 天时预采集 (0=禁用, 默认 0)")
    parser.add_argument("--no-auto-collect", action="store_true",
                        help="禁用自动采集 (默认在预校验失败时自动采集过期品种)")
    parser.add_argument("--vol-filter", action="store_true",
                        help="启用波动率熔断 (默认 Neutral Override 空仓; 默认 OFF)")
    parser.add_argument("--vol-filter-neutral", action="store_true",
                        help="同 --vol-filter：高波时预测压平/空仓（推荐）")
    parser.add_argument("--vol-filter-slope", action="store_true",
                        help="legacy：高波时仅剥离第二协变量 (slope_only)")
    parser.add_argument("--vol-thr", type=float, default=0.55,
                        help="熔断概率阈值 (默认 0.55)")
    args = parser.parse_args()

    vol_on = is_vol_filter_enabled(
        cli_flag=args.vol_filter or args.vol_filter_neutral or args.vol_filter_slope
    )
    vol_action = "slope_only" if args.vol_filter_slope else "neutral"
    shared_vol_filter = None
    if vol_on:
        print(f"\n  [WARN] Vol Gating ON (experimental, action={vol_action}). "
              "Production default remains OFF.")
        try:
            shared_vol_filter = VolRiskFilter.load_or_train(
                prob_threshold=args.vol_thr,
            )
            shared_vol_filter.prob_threshold = args.vol_thr
        except Exception as e:
            print(f"  [WARN] Vol filter init failed ({e}); will retry per symbol or skip")
    else:
        print("\n  [Vol Gating] OFF → static scheme only "
              "(enable: --vol-filter-neutral / FM_VOL_FILTER=1)")

    if args.three_star:
        # 历史名 --three-star：现映射信用≥2星（新口径无3星）
        from config.prediction_scheme import list_by_stars
        symbols = list_by_stars(2) or list_solidified()
    elif args.all:
        symbols = list(DEFAULT_SYMBOLS)
    elif args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        parser.print_help()
        return

    if not symbols:
        print("无数据")
        return

    # ── 数据采集 (在预检查之前) ──
    if args.collect:
        print(f"\n  [采集] 采集 {len(symbols)} 个品种的最新数据...")
        from scripts.three_star_predict import ensure_data
        collect_failed = []
        for s in symbols:
            print(f"    {s.upper()}...", end=" ", flush=True)
            r = ensure_data(s)
            print("OK" if r["ok"] else f"FAILED ({r['error']})")
            if not r["ok"]:
                collect_failed.append(s.upper())
        if collect_failed:
            print(f"  [WARN] {len(collect_failed)} 品种采集失败: {', '.join(collect_failed)}"
                  f"，预检查将按需重试")
    elif args.collect_if_stale > 0:
        # 按需采集: 检查最旧品种，滞后超阈值则采集
        stale_symbols = []
        for s in symbols:
            try:
                with DataStore(s) as store:
                    df = store.get_main_contract_1h(limit=1)
                    if not df.empty:
                        latest = pd.to_datetime(df["dt"].iloc[-1])
                        days_stale = (datetime.now() - latest).days
                        if days_stale >= args.collect_if_stale:
                            stale_symbols.append((s, days_stale))
            except Exception:
                stale_symbols.append((s, -1))
        if stale_symbols:
            print(f"\n  [按需采集] {len(stale_symbols)} 个品种数据滞后 "
                  f"(阈值 {args.collect_if_stale} 天)...")
            from scripts.three_star_predict import ensure_data
            for s, d in stale_symbols:
                label = f"{d}天" if d >= 0 else "未知"
                print(f"    {s.upper()} (滞后{label})...", end=" ", flush=True)
                r = ensure_data(s)
                print("OK" if r["ok"] else f"FAILED ({r['error']})")

    # 预检查: 数据完整性 + 时效性验证 + 自动采集 (在加载模型之前，避免浪费推理资源)
    auto_collect = not args.no_auto_collect
    print(f"\n  [预检查] 验证 {len(symbols)} 个品种的数据"
          f"{' (auto-collect 已启用)' if auto_collect else ''}...")
    valid_symbols, skipped_symbols = ensure_fresh_data(symbols, auto_collect=auto_collect)
    symbols = valid_symbols

    if not symbols:
        print("无有效品种可预测 (全部数据校验失败)")
        # 仍然生成空报告
        reports_base = Path(__file__).resolve().parent.parent / "reports"
        summaries_dir = reports_base / "summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        summary = _build_summary(skipped_symbols, ts)
        (summaries_dir / f"{ts}_summary.md").write_text(summary, encoding="utf-8")
        return

    # 显示固化状态
    solidified = [s for s in symbols if is_solidified(s)]
    if solidified:
        print(f"\n  固化品种 ({len(solidified)}): {', '.join(s.upper() for s in solidified)}")

    reports_base = Path(__file__).resolve().parent.parent / "reports"
    reports_base.mkdir(exist_ok=True)
    summaries_dir = reports_base / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # 进度日志 (放入 summaries 目录)
    progress_log = summaries_dir / f"{ts}_progress.log"

    def _log_progress(msg: str):
        """追加写入进度日志 (write_text 会覆盖，改用 append)"""
        with open(progress_log, 'a', encoding='utf-8') as f:
            f.write(msg + "\n")

    _log_progress(f"START {ts} symbols={','.join(s.upper() for s in symbols)}")

    # 预加载模型 (共享实例，避免重复加载 ~800MB)
    print(f"\n  加载 TimesFM 2.5 模型 (共享)...")
    from cascade.daily_model import DailyModel
    bootstrap = DailyModel()
    shared_model = bootstrap.model
    print(f"  模型已加载")
    print(f"  报告按品种保存至: {reports_base}/<symbol>/")

    all_results = list(skipped_symbols)  # 预检查跳过的品种也纳入汇总报告

    for idx, symbol in enumerate(symbols):
        try:
            scheme = get_scheme(symbol)
            tag = f"[{scheme.stars}星固化]" if scheme else ""
            print(f"\n  [{idx+1}/{len(symbols)}] {symbol.upper()} {tag}")
            _log_progress(f"[{idx+1}/{len(symbols)}] {symbol.upper()} START")
            report, result_data = run_cascade(
                symbol, args.horizon, visualize=not args.no_viz,
                shared_model=shared_model,
                use_vol_filter=vol_on,
                vol_filter=shared_vol_filter,
                vol_action=vol_action,
            )
            # 按品种保存: reports/<symbol>/cascade_YYYYMMDD_HHmm.md
            symbol_dir = reports_base / symbol
            symbol_dir.mkdir(parents=True, exist_ok=True)
            report_path = symbol_dir / f"cascade_{ts}.md"
            report_path.write_text(report, encoding="utf-8")
            all_results.append(result_data)
            print(f"\n  报告保存: {report_path}")

            # 记录预测到历史追踪
            scheme = get_scheme(symbol)
            if scheme and result_data.get('t1') is not None:
                try:
                    track_prediction(
                        symbol=symbol,
                        current_price=result_data.get('current_price', 0),
                        pred_t1=result_data.get('t1', 0),
                        pred_t24=result_data.get('t24', 0),
                        weighted_pred=result_data.get('weighted_pred', 0),
                        direction=result_data.get('direction', '→'),
                        dir_acc=scheme.dir_acc,
                        mape=scheme.mape,
                        covariate=scheme.covariate_type,
                    )
                    print(f"  预测已记录到历史追踪")
                except Exception as e:
                    print(f"  [WARN] 历史追踪记录失败: {e}")

            _log_progress(f"[{idx+1}/{len(symbols)}] {symbol.upper()} OK")
        except ValueError as e:
            if "数据校验失败" in str(e):
                # 断路器: 数据校验失败 → 跳过该品种, 继续下一个
                print(f"\n  [SKIP] {symbol.upper()}: {e}")
                all_results.append({"symbol": symbol, "name": get_name(symbol), "error": str(e)})
                _log_progress(f"[{idx+1}/{len(symbols)}] {symbol.upper()} SKIP {e}")
                continue
            raise  # 非校验错误仍然抛出
        except Exception as e:
            print(f"\n  [ERROR] {symbol.upper()}: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({"symbol": symbol, "name": get_name(symbol), "error": str(e)})
            _log_progress(f"[{idx+1}/{len(symbols)}] {symbol.upper()} ERROR {e}")

    # 生成汇总报告
    if all_results:
        summary = _build_summary(all_results, ts)
        summary_path = summaries_dir / f"{ts}_summary.md"
        summary_path.write_text(summary, encoding="utf-8")
        print(f"\n  汇总报告: {summary_path}")

    _log_progress(f"DONE {datetime.now().strftime('%Y%m%d_%H%M')}")

    print(f"\n{'='*60}")
    print("级联预测完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
