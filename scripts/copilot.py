#!/usr/bin/env python3
"""
FM_a 主观交易领航员 (Copilot)

定位：领航员而非自动驾驶。
  - 永不压平预测（Vol Gating 仅输出风险标签与建议）
  - 展示历史信用背书（PF / DirAcc / 星级）
  - 盘中可即时补 1H 截面
  - CLI 仪表盘 + Markdown 深度研报

用法:
  python scripts/copilot.py ss fu
  python scripts/copilot.py ss i --no-refresh
  python scripts/copilot.py --three-star   # 信用≥2星（历史名，非真实3星）
  python scripts/copilot.py ss --no-vol-radar
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from scripts.cascade_predict import TICK_SIZE

# ── 屏蔽刷屏 ──────────────────────────────────────────────
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
warnings.filterwarnings("ignore")

# ── Windows GBK 终端 → 强制 UTF-8 输出 ────────────────────
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

# ─────────────────────────────────────────────────────────
# 常量 / 路径
# ─────────────────────────────────────────────────────────

KB_PATH = ROOT / "config" / "knowledge_base.json"
REPORT_DIR = ROOT / "reports" / "daily"
DEFAULT_HORIZON = 24


# ─────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────

def load_knowledge_base(path: Path = KB_PATH) -> dict:
    if not path.exists():
        return {"_meta": {"warning": "knowledge_base missing"}, "symbols": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def kb_entry(kb: dict, symbol: str) -> dict:
    return (kb.get("symbols") or {}).get(symbol.lower(), {})


def stars_label(n: int) -> str:
    n = max(0, min(3, int(n or 0)))
    if n <= 0:
        return "  边缘弱信号"
    return "*" * n + f" ({n}星)"


# ─────────────────────────────────────────────────────────
# 盘中 1H 刷新
# ─────────────────────────────────────────────────────────

def refresh_intraday_1h(symbol: str, quiet: bool = False) -> dict:
    """
    拉取 TqSdk 主力连续 1H，增量写入 SQLite。
    日线不重算（盘中用昨日收盘特征即可）。
    """
    from data.tqsdk_fetcher import UnifiedFetcher
    from data.indicator_calculator import IndicatorCalculator
    from data.data_store import DataStore

    info = {"symbol": symbol, "stored": 0, "last_dt": None, "ok": False, "error": None}
    try:
        fetcher = UnifiedFetcher()
        calc = IndicatorCalculator()
        df = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=10000)
        if df is None or df.empty:
            info["error"] = "empty_kline"
            return info
        if "dt" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"dt": "date"})
        main_code = f"{symbol.upper()}_MAIN"
        df = df.copy()
        df["contract_code"] = main_code
        # IndicatorCalculator needs open/close
        if "close_price" in df.columns and "close" not in df.columns:
            df = df.rename(columns={"open_price": "open", "close_price": "close"})
        df = calc.calculate_all(df)
        if "open" in df.columns:
            df = df.rename(columns={"open": "open_price", "close": "close_price"})
        with DataStore(symbol) as store:
            stored = store.store_klines_1h(main_code, df)
            info["stored"] = int(stored)
            try:
                last = store.get_main_contract_1h(limit=1)
                if last is not None and not last.empty:
                    info["last_dt"] = str(last["dt"].iloc[-1])
            except Exception:
                if "date" in df.columns:
                    info["last_dt"] = str(df["date"].iloc[-1])
        info["ok"] = True
        if not quiet:
            print(f"  [intraday] {symbol.upper()} 1H +{info['stored']} last={info['last_dt']}")
    except Exception as e:
        info["error"] = str(e)
        if not quiet:
            print(f"  [intraday] {symbol.upper()} 刷新失败: {e}")
    return info


# ─────────────────────────────────────────────────────────
# Vol 雷达（只读，不压平）
# ─────────────────────────────────────────────────────────

def evaluate_vol_radar(symbol: str, hourly_df) -> dict:
    """绑定板块 operational thr，返回 vol_prob / veto 标记（仅预警）。"""
    from cascade.vol_risk_filter import VolRiskFilter, ThrPolicy

    out = {
        "enabled": True,
        "vol_prob": None,
        "threshold": None,
        "threshold_source": None,
        "model_source": None,
        "high_vol": False,
        "message": "",
        "error": None,
    }
    try:
        policy = ThrPolicy.from_cli()  # 读 operational_thr.json
        filt = VolRiskFilter.bind_for_symbol(symbol, mode="r1", policy=policy)
        decision = filt.evaluate(hourly_df)
        out["vol_prob"] = float(decision.vol_prob) if decision.vol_prob == decision.vol_prob else None
        out["threshold"] = float(decision.threshold)
        out["threshold_source"] = getattr(filt, "threshold_source", None)
        out["model_source"] = getattr(filt, "model_source", None)
        out["high_vol"] = bool(decision.veto)
        # 覆写文案：预警而非熔断
        if out["vol_prob"] is None:
            out["message"] = "特征不足，风险雷达跳过"
        elif out["high_vol"]:
            out["message"] = (
                f"极高波动预警 (Vol_Prob: {out['vol_prob']:.2f} ≥ {out['threshold']:.2f})"
            )
        else:
            out["message"] = (
                f"正常 (Vol_Prob: {out['vol_prob']:.2f} < {out['threshold']:.2f})"
            )
    except Exception as e:
        out["enabled"] = False
        out["error"] = str(e)
        out["message"] = f"风险雷达不可用: {e}"
    return out



def quantize_price(price: float, tick_size: float, mode: str = "round") -> float:
    """最小变动价位物理网格整量化 (Tick Snapping).

    mode: 'round' (四舍五入), 'floor' (向下, 多头止损), 'ceil' (向上, 空头止损)
    """
    if tick_size <= 0:
        return price
    factor = 1.0 / tick_size
    if mode == "floor":
        return float(np.floor(np.round(price * factor, 6)) / factor)
    elif mode == "ceil":
        return float(np.ceil(np.round(price * factor, 6)) / factor)
    else:
        return float(np.round(price * factor) / factor)


def _price_format(price: float, tick_size: float) -> str:
    """基于 tick_size 自动决定显示精度"""
    s = f"{tick_size:g}"
    precision = len(s.split('.')[1]) if '.' in s else 0
    return f"{price:.{precision}f}"


def generate_risk_bounds(
    direction: str,
    p10: float,
    p90: float,
    tick_size: float,
    stop_buffer_ticks: int = 2,
) -> list:
    """方向自适应止盈止损映射 + tick 整量化 + 价格下界保护"""
    buffer = tick_size * stop_buffer_ticks
    fmt = lambda v: _price_format(quantize_price(v, tick_size), tick_size)
    lines = []

    if "多" in direction or "↑" in direction:
        raw_stop = p10 - buffer
        stop = max(quantize_price(raw_stop, tick_size, mode="floor"), tick_size)
        target = quantize_price(p90, tick_size, mode="round")
        lines.append(f"止损参考 (多头防线): P10≈{fmt(p10)}, 建议止损位 {fmt(stop)}")
        lines.append(f"止盈参考 (第一目标): P90≈{fmt(target)} (触及高位减仓)")

    elif "空" in direction or "↓" in direction:
        raw_stop = p90 + buffer
        stop = quantize_price(raw_stop, tick_size, mode="ceil")
        target = max(quantize_price(p10, tick_size, mode="round"), tick_size)
        lines.append(f"止损参考 (空头防线): P90≈{fmt(p90)}, 建议止损位 {fmt(stop)}")
        lines.append(f"止盈参考 (第一目标): P10≈{fmt(target)} (跌至目标位分批止盈)")

    else:
        lines.append(f"区间下轨支撑: P10≈{fmt(p10)}")
        lines.append(f"区间上轨阻力: P90≈{fmt(p90)}")
        lines.append("建议: 高抛低吸或观望")

    return lines


def _direction_bias(direction: str) -> str:
    d = direction or ""
    if "多" in d or "↑" in d:
        return "多头"
    if "空" in d or "↓" in d:
        return "空头"
    return "震荡/中性"


def craft_advisory(
    symbol: str,
    kb: dict,
    direction: str,
    delta_pct: float | None,
    vol: dict,
    scheme_type: str | None,
) -> list[str]:
    """生成领航员建议（多行）。"""
    e = kb_entry(kb, symbol)
    lines: list[str] = []
    stars = int(e.get("credit_stars") or 0)
    pf = e.get("historical_pf")
    dir_acc = e.get("historical_diracc")
    hold = e.get("best_hold_period") or "T+1 ~ T+24"
    vol_sens = e.get("vol_sensitivity") or "UNKNOWN"
    high_vol = bool(vol.get("high_vol"))

    # 底气
    if pf is not None and dir_acc is not None:
        if stars >= 3:
            lines.append(
                f"模型底气: 历史胜率 {dir_acc:.0%}，盈亏比(PF) {pf:.2f}。"
                f"属于本系统核心优势品种。"
            )
        elif stars >= 2:
            lines.append(
                f"模型底气: 历史胜率 {dir_acc:.0%}，盈亏比(PF) {pf:.2f}。"
                f"中等信用，仓位适中。"
            )
        else:
            lines.append(
                f"模型底气: 历史胜率 {dir_acc:.0%}，盈亏比(PF) {pf:.2f}。"
                f"利润/胜率偏薄，请控制仓位，仅作参考。"
            )

    # 方向与时效
    dlt = f"{delta_pct:+.2f}%" if delta_pct is not None else "N/A"
    bias = _direction_bias(direction)

    lines.append(f"时效策略: 建议关注窗口 {hold}；当前方向偏向【{bias}】（加权涨跌 {dlt}）。")

    # 高波差异化指南
    if high_vol:
        if vol_sens == "HELPS":
            lines.append(
                "⚠️ 领航员强警示: 历史全链路显示，该品种在高波期开启过滤可改善期望，"
                "主观侧强烈建议空仓观望或极轻仓，勿逆势加杠杆。"
            )
        elif vol_sens == "HURTS":
            lines.append(
                "⚡ 机会提示: 历史回测中该品种高波期「一刀切空仓」反而伤害收益，"
                "可能走单边趋势——可紧跟预测方向，但务必拉宽止损并用 P10/P90 锚定。"
            )
        elif vol_sens == "MIXED":
            lines.append(
                "⚠️ 高波混合态: 历史表现好坏参半。建议降仓跟随方向，"
                "严格用 P10 止损，盈利后按时效窗口提前兑现。"
            )
        else:
            lines.append(
                "⚠️ 极高波动风险 — 建议观望或轻仓。历史 vol 敏感度标签不足，优先防守。"
            )
    else:
        if stars >= 3 and bias != "震荡/中性":
            lines.append(f"副驾建议: {bias}结构相对清晰，可在日内回撤处分批参与，持有参考 {hold}。")
        elif bias == "震荡/中性":
            lines.append("副驾建议: 方向不鲜明，观望或极小仓试探即可。")
        else:
            lines.append(f"副驾建议: 轻仓跟踪 {bias} 方向，严守止损，勿重仓博弈。")

    return lines



def craft_advisory_v2(symbol, kb, direction, delta_pct, vol, scheme_type):
    """Advisory with effective_stars override for degraded/revoked status."""
    entry = kb_entry(kb, symbol)
    status = entry.get("slow_loop_status", "ok")

    raw_stars = int(entry.get("credit_stars") or 0)
    effective_stars = 1 if status in ("degraded", "revoked") else raw_stars

    lines = []
    if status == "revoked":
        lines.append("🔒 慢环实证已完全退化冻结，禁止建立新仓，仅供观望监控。")
        return lines

    if effective_stars >= 2:
        lines.append(f"模型底气: 盈亏比(PF) {entry.get('historical_pf', 0):.2f}，中等信用，建议标准仓位。")
    else:
        reason = "（慢环实证退化）" if status == "degraded" else ""
        lines.append(f"模型底气: 弱信号品种{reason}，建议轻仓试探或观望。")

    return lines


def copilot_trade_signal(fc, last_close, scheme, daily_slope):
    """Copilot card trade fields from 1H forecast (CF-01 A).

    Tradable direction = weighted 1H via position_from_forecast.
    Daily slope only fills regime_direction. delta_pct is weighted vs last_close.
    """
    from cascade.signal_contract import position_from_forecast

    arr = np.asarray(fc, dtype=float).ravel() if fc is not None else np.zeros(0)
    if arr.size == 0:
        return {
            "direction": "中性 →",
            "regime_direction": "",
            "weighted_pred": float(last_close or 0.0),
            "delta_pct": 0.0,
        }
    sig = position_from_forecast(
        arr, float(last_close), scheme=scheme, daily_slope=daily_slope,
    )
    weighted = float(sig["weighted_pred"])
    base = float(last_close) if last_close else 0.0
    delta_pct = (weighted / base - 1.0) * 100.0 if base else 0.0
    return {
        "direction": sig["direction"],
        "regime_direction": sig.get("regime_direction") or "",
        "weighted_pred": weighted,
        "delta_pct": delta_pct,
    }


# ─────────────────────────────────────────────────────────
# 预测核心（永不压平）
# ─────────────────────────────────────────────────────────

@dataclass
class CopilotCard:
    symbol: str
    name: str
    current_price: float
    direction: str
    t4: float
    t12: float
    t24: float
    delta_pct: float
    point_forecast: list[float]
    p10: list[float]
    p90: list[float]
    daily_slope: float
    cov_label: str
    scheme_type: Optional[str]
    vol: dict
    kb: dict
    advisory: list[str] = field(default_factory=list)
    last_1h_dt: Optional[str] = None
    context_len: int = 0
    covariates: dict = field(default_factory=dict)
    xreg_fallback: bool = False
    regime_direction: str = ""


def run_one(
    symbol: str,
    shared_model,
    kb: dict,
    horizon: int = DEFAULT_HORIZON,
    use_vol_radar: bool = True,
    visualize: bool = False,
) -> CopilotCard:
    from data.data_store import DataStore
    from data.config import get_name
    from config.prediction_scheme import get_scheme
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel

    symbol = symbol.lower()
    scheme = get_scheme(symbol)
    ctx_bars = scheme.context_bars if scheme else 480
    ctx_days = scheme.context_days if scheme else 250
    h_days = scheme.horizon_days if scheme else 22
    cov_type = scheme.covariate_type if scheme else "ccl"
    cov_types = scheme.covariate_types if scheme else None
    cov_label = "+".join(cov_types) if cov_types else cov_type

    with DataStore(symbol) as store:
        daily_model = DailyModel(shared_model=shared_model)
        daily_result = daily_model.predict(
            symbol, store, context_days=ctx_days, horizon_days=h_days
        )
        hourly_df = store.get_main_contract_1h(limit=ctx_bars)
        last_1h_dt = None
        if hourly_df is not None and not hourly_df.empty:
            last_1h_dt = str(hourly_df["dt"].iloc[-1])
            last_close = float(hourly_df["close_price"].iloc[-1])
        else:
            last_close = 0.0

        vol = {"enabled": False, "high_vol": False, "message": "未启用", "vol_prob": None, "threshold": None}
        if use_vol_radar and hourly_df is not None and not hourly_df.empty:
            vol = evaluate_vol_radar(symbol, hourly_df)

        # ★ 永不压平：始终用静态 scheme 出完整预测
        hourly_model = HourlyModel(shared_model=daily_model.model)
        hourly_result = hourly_model.predict(
            symbol,
            store,
            daily_result,
            horizon=horizon,
            visualize=visualize,
            covariate_type=cov_type,
            covariate_types=cov_types,
            skip_validation=True,
        )

        fc = np.asarray(hourly_result.point_forecast, dtype=float)
        q = hourly_result.quantile_forecast
        p10 = p90 = [float("nan")] * len(fc)
        if q is not None and getattr(q, "ndim", 0) == 2 and q.shape[1] >= 10:
            p10 = [float(q[i, 1]) for i in range(len(fc))]
            p90 = [float(q[i, 9]) for i in range(len(fc))]

        d_slope = float(daily_result.horizon_slope)
        # 可交易涨跌：加权 1H vs 当前（CF-01 A）；T+24 终点仅作轨迹展示
        t24 = float(fc[-1]) if len(fc) else last_close
        sig = copilot_trade_signal(fc, last_close, scheme, d_slope)
        direction = sig["direction"]
        regime_direction = sig["regime_direction"]
        delta_pct = sig["delta_pct"]

        def _at(i: int) -> float:
            if len(fc) == 0:
                return last_close
            return float(fc[min(i, len(fc) - 1)])

        e = kb_entry(kb, symbol)
        advisory = craft_advisory(
            symbol, kb, direction, delta_pct, vol,
            scheme.scheme_type if scheme else None,
        )

        return CopilotCard(
            symbol=symbol,
            name=get_name(symbol) or (e.get("name") or symbol.upper()),
            current_price=last_close,
            direction=direction,
            t4=_at(3),
            t12=_at(11),
            t24=t24,
            delta_pct=delta_pct,
            point_forecast=[float(x) for x in fc],
            p10=p10,
            p90=p90,
            daily_slope=d_slope * 100.0,
            cov_label=cov_label,
            scheme_type=scheme.scheme_type if scheme else None,
            vol=vol,
            kb=e,
            advisory=advisory,
            last_1h_dt=last_1h_dt,
            context_len=int(hourly_result.context_len or 0),
            covariates=dict(hourly_result.covariates or {}),
            xreg_fallback=bool(hourly_result.xreg_fallback),
            regime_direction=regime_direction,
        )


# ─────────────────────────────────────────────────────────
# Rich CLI
# ─────────────────────────────────────────────────────────

def render_cli(cards: list[CopilotCard], asof: str) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich import box

        # Windows GBK 终端不支持 emoji/Unicode → 走纯文本降级
        enc = getattr(sys.stdout, "encoding", "") or ""
        if "utf" not in enc.lower() and "cp65001" not in enc.lower():
            try:
                "⭐".encode(enc)
            except (UnicodeEncodeError, LookupError):
                _render_cli_plain(cards, asof)
                return

        console = Console(force_terminal=True, soft_wrap=True)
        use_rich = True
    except Exception:
        use_rich = False
        console = None

    if not use_rich:
        _render_cli_plain(cards, asof)
        return

    header = Text.assemble(
        (" FM_a 主观交易领航员 ", "bold white on blue"),
        (f" 截面: {asof} ", "bold"),
    )
    console.print(Panel(header, expand=True, box=box.DOUBLE))

    for i, c in enumerate(cards, 1):
        stars = int(c.kb.get("credit_stars") or 0)
        pf = c.kb.get("historical_pf")
        da = c.kb.get("historical_diracc")
        hold = c.kb.get("best_hold_period") or "—"
        title = f"[{i}/{len(cards)}]  {c.symbol.upper()} ({c.name}) | 综合评级: {stars_label(stars)}"

        body = Table.grid(padding=(0, 1))
        body.add_column(style="bold cyan", justify="right")
        body.add_column()

        arrow_path = (
            f"T+4 [{c.t4:,.0f}] {_arrow(c.current_price, c.t4)} "
            f"T+12 [{c.t12:,.0f}] {_arrow(c.t4, c.t12)} "
            f"T+24 [{c.t24:,.0f}]"
        )
        body.add_row("当前价", f"{c.current_price:,.2f}  →  预测终点: {c.t24:,.2f}  (加权: {c.delta_pct:+.2f}%)")
        body.add_row("可交易方向", c.direction)
        body.add_row("日线状态", c.regime_direction or "—")
        body.add_row("核心轨迹", arrow_path)
        body.add_row(
            "协变量",
            f"{c.cov_label}"
            + (f"  | 历史 PF {pf:.2f} · 胜率 {da:.0%}" if pf is not None and da is not None else ""),
        )
        body.add_row("时效策略", str(hold))
        body.add_row("日线斜率", f"{c.daily_slope:+.4f}% / bar  (scheme={c.scheme_type or '—'})")
        body.add_row("1H 截面", str(c.last_1h_dt or "—") + f"  ctx={c.context_len}")

        # 风险行着色
        if c.vol.get("high_vol"):
            risk_style = "bold red"
            risk_txt = f"⚠ {c.vol.get('message', '高波')}"
        else:
            risk_style = "green"
            risk_txt = f"✓ {c.vol.get('message', '正常')}"
        body.add_row("风险雷达", Text(risk_txt, style=risk_style))

        # P10/P90 锚点
        if c.p10 and c.p10[0] == c.p10[0]:
            body.add_row(
                "极端防守",
                f"P10≈{min(c.p10):,.0f}  /  P90≈{max(c.p90):,.0f}  "
                f"(历史 Coverage≈{(c.kb.get('historical_coverage') or 0)*100:.0f}%)",
            )

        for line in c.advisory:
            style = "bold red" if ("强警示" in line or "警告" in line or "⚠️" in line) else (
                "bold yellow" if "机会" in line or "⚡" in line else "white"
            )
            body.add_row("领航建议", Text(line, style=style))

        border = "red" if c.vol.get("high_vol") else "bright_blue"
        console.print(Panel(body, title=title, border_style=border, box=box.HEAVY))

    console.print()


def _arrow(a: float, b: float) -> str:
    if b > a * 1.0005:
        return "↗"
    if b < a * 0.9995:
        return "↘"
    return "→"


def _render_cli_plain(cards: list[CopilotCard], asof: str) -> None:
    bar = "=" * 80
    print(bar)
    print(f" FM_a 主观交易领航员 (截面: {asof})")
    print(bar)
    for i, c in enumerate(cards, 1):
        stars = int(c.kb.get("credit_stars") or 0)
        print(f"\n[{i}/{len(cards)}]  {c.symbol.upper()} ({c.name}) | 综合评级: {stars_label(stars)}")
        print("-" * 80)
        print(f"▶ 当前价: {c.current_price:,.2f}  →  预测终点: {c.t24:,.2f} (加权: {c.delta_pct:+.2f}%)")
        print(f"▶ 可交易方向: {c.direction}")
        print(f"▶ 日线状态: {c.regime_direction or '—'}")
        print(
            f"▶ 核心轨迹: T+4 [{c.t4:,.0f}] {_arrow(c.current_price, c.t4)} "
            f"T+12 [{c.t12:,.0f}] {_arrow(c.t4, c.t12)} T+24 [{c.t24:,.0f}]"
        )
        pf, da = c.kb.get("historical_pf"), c.kb.get("historical_diracc")
        hist = f" (历史 PF {pf:.2f} | 胜率 {da:.0%})" if pf is not None and da is not None else ""
        print(f"▶ 协变量: {c.cov_label}{hist}")
        print(f"▶ 时效策略: {c.kb.get('best_hold_period', '—')}")
        flag = "⚠" if c.vol.get("high_vol") else "✓"
        print(f"▶ 风险雷达: {flag} {c.vol.get('message', '')}")
        for line in c.advisory:
            print(f"▶ {line}")
    print(bar)


# ─────────────────────────────────────────────────────────
# Markdown Tear Sheet
# ─────────────────────────────────────────────────────────

def write_markdown(cards: list[CopilotCard], asof: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# FM_a 领航员研报")
    lines.append("")
    lines.append(f"**截面**: {asof}  ")
    lines.append(f"**品种**: {', '.join(c.symbol.upper() for c in cards)}  ")
    lines.append(f"**原则**: 预测永不压平；Vol 仅预警；历史回测作信用背书  ")
    lines.append("")

    # 总览表
    lines.append("## 一、结论面板")
    lines.append("")
    lines.append("| 品种 | 评级 | 现价 | T+24 | 加权涨跌 | 可交易方向 | 日线状态 | Vol_Prob | 风险 | 历史PF | 胜率 |")
    lines.append("|------|:----:|-----:|-----:|--------:|:----------:|:--------:|---------:|:----:|-------:|-----:|")
    for c in cards:
        stars = int(c.kb.get("credit_stars") or 0)
        vp = c.vol.get("vol_prob")
        vp_s = f"{vp:.2f}" if isinstance(vp, float) else "—"
        risk = "高波" if c.vol.get("high_vol") else "正常"
        pf = c.kb.get("historical_pf")
        da = c.kb.get("historical_diracc")
        lines.append(
            f"| {c.symbol.upper()} | {'⭐'*stars if stars else '☆'} | {c.current_price:,.1f} "
            f"| {c.t24:,.1f} | {c.delta_pct:+.2f}% | {c.direction} | {c.regime_direction or '—'} | {vp_s} | {risk} "
            f"| {pf if pf is not None else '—'} | {f'{da:.0%}' if da is not None else '—'} |"
        )
    lines.append("")

    for c in cards:
        lines.append(f"## 二、{c.symbol.upper()} {c.name} 深度拆解")
        lines.append("")
        lines.append("### 2.1 领航结论")
        lines.append("")
        for a in c.advisory:
            lines.append(f"- {a}")
        lines.append("")
        lines.append(
            f"- **可交易方向**: {c.direction}  \n"
            f"- **日线状态**: {c.regime_direction or '—'}  \n"
            f"- **协变量**: `{c.cov_label}`  \n"
            f"- **方案类型**: {c.scheme_type or '—'}  \n"
            f"- **日线斜率 (Daily_Slope)**: {c.daily_slope:+.4f}% / bar  \n"
            f"- **1H 截面**: {c.last_1h_dt or '—'}  \n"
            f"- **Vol 敏感度 (L1)**: {c.kb.get('vol_sensitivity', '—')}  \n"
            f"- **最佳持有窗口**: {c.kb.get('best_hold_period', '—')}  \n"
            f"- **信用说明**: {c.kb.get('covariate_rationale', '')}"
        )
        lines.append("")

        lines.append("### 2.2 预测曲线 (T+1 ~ T+24)")
        lines.append("")
        lines.append("| 时点 | 点预测 | P10 | P90 | vs现价 |")
        lines.append("|-----:|-------:|----:|----:|-------:|")
        for i, px in enumerate(c.point_forecast, 1):
            p10 = c.p10[i - 1] if i - 1 < len(c.p10) else float("nan")
            p90 = c.p90[i - 1] if i - 1 < len(c.p90) else float("nan")
            chg = (px / c.current_price - 1) * 100 if c.current_price else 0
            p10s = f"{p10:,.1f}" if p10 == p10 else "—"
            p90s = f"{p90:,.1f}" if p90 == p90 else "—"
            mark = ""
            if i in (4, 8, 12, 24):
                mark = " **"
            lines.append(
                f"| T+{i}{mark} | {px:,.1f} | {p10s} | {p90s} | {chg:+.2f}% |"
            )
        lines.append("")

        lines.append("### 2.3 止盈止损锚点 (P10 / P90)")
        lines.append("")
        if c.p10 and c.p10[0] == c.p10[0]:
            cov = c.kb.get("historical_coverage")
            cov_s = f"{cov:.0%}" if cov else "约 60–80%"
            lines.append(
                f"- 区间最低 P10 ≈ **{min(c.p10):,.1f}**；最高 P90 ≈ **{max(c.p90):,.1f}**  \n"
                f"- 历史 P10–P90 Coverage ≈ **{cov_s}**  \n"
            )
            # ★ 安全提取 P10/P90 (避免 numpy 数组真值歧义 ValueError)
            p10_val = float(np.min(c.p10)) if (c.p10 is not None and len(c.p10) > 0) else 0.0
            p90_val = float(np.max(c.p90)) if (c.p90 is not None and len(c.p90) > 0) else 0.0
            tick_size = TICK_SIZE.get(c.symbol, 1.0)
            risk_lines = generate_risk_bounds(c.direction, p10_val, p90_val, tick_size)
            for rl in risk_lines:
                lines.append(f"- {rl}  \n")
        else:
            lines.append("- 本次未取得分位数输出（可能 xreg 回退）。")
        if c.xreg_fallback:
            lines.append("- ⚠️ 本次 XReg 回退为无协变量预测，置信度下调。")
        lines.append("")

        lines.append("### 2.4 因子快照")
        lines.append("")
        if c.covariates:
            lines.append("| 因子 | 最新值 |")
            lines.append("|------|-------:|")
            for k, v in c.covariates.items():
                try:
                    arr = np.asarray(v, dtype=float)
                    if arr.ndim == 0:
                        val = float(arr)
                    else:
                        val = float(arr[-1])
                    lines.append(f"| `{k}` | {val:+.6g} |")
                except Exception:
                    lines.append(f"| `{k}` | {v} |")
        else:
            lines.append("_无额外因子字典（daily_slope 已在上文）_")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated by scripts/copilot.py @ {asof}_")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def select_copilot_symbols(requested: list[str], valid: list[str]) -> list[str]:
    """Freshness result: valid only. Empty valid never falls back to requested."""
    return list(valid)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FM_a 主观交易领航员 (Copilot) — 预测不压平，Vol 仅预警"
    )
    parser.add_argument("symbols", nargs="*", help="品种代码，如 ss fu")
    parser.add_argument(
        "--three-star", action="store_true",
        help="信用≥2星品种（历史 CLI 名；2026-08 后无真实3星）",
    )
    parser.add_argument("--all-solidified", action="store_true", help="全部固化品种")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument("--no-refresh", action="store_true", help="跳过盘中 1H 刷新")
    parser.add_argument("--no-vol-radar", action="store_true", help="关闭波动率雷达")
    parser.add_argument("--no-collect", action="store_true", help="跳过 ensure_fresh_data")
    parser.add_argument("--visualize", action="store_true", help="写出对齐图（慢）")
    parser.add_argument("--out-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()

    from config.prediction_scheme import list_solidified
    from cascade.data_validator import ensure_fresh_data

    if args.three_star:
        from config.prediction_scheme import list_by_stars
        symbols = list_by_stars(2) or ["ss", "sr", "m"]
    elif args.all_solidified:
        symbols = list_solidified()
    elif args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        parser.print_help()
        print("\n示例: python scripts/copilot.py ss fu")
        return 2

    asof = datetime.now().strftime("%Y-%m-%d %H:%M")
    kb = load_knowledge_base()
    if not (kb.get("symbols")):
        print("[WARN] knowledge_base.json 为空，请先运行: python scripts/build_knowledge_base.py")

    print(f"\n[Copilot] 截面 {asof} | 品种 {', '.join(s.upper() for s in symbols)}")
    print("[Copilot] 模式: 领航员（预测永不压平；Vol=预警）")

    # 数据新鲜度（日线）；盘中 1H 另刷
    if not args.no_collect:
        print("[Copilot] ensure_fresh_data ...")
        valid, skipped = ensure_fresh_data(symbols, auto_collect=True)
        if skipped:
            print(f"  [SKIP] {skipped}")
        symbols = select_copilot_symbols(symbols, valid)
        if not symbols:
            print("无有效品种可预测 (全部数据校验失败)")
            return 1

    if not args.no_refresh:
        print("[Copilot] 盘中 1H 刷新 ...")
        for s in symbols:
            refresh_intraday_1h(s)

    # 加载模型一次（DailyModel() 内部 from_pretrained）
    print("[Copilot] 加载 TimesFM 2.5 ...")
    from cascade.daily_model import DailyModel

    bootstrap = DailyModel()
    shared_model = bootstrap.model
    print("[Copilot] 模型已加载")

    cards: list[CopilotCard] = []
    for s in symbols:
        print(f"\n[Copilot] 推理 {s.upper()} ...")
        try:
            card = run_one(
                s,
                shared_model=shared_model,
                kb=kb,
                horizon=args.horizon,
                use_vol_radar=not args.no_vol_radar,
                visualize=args.visualize,
            )
            cards.append(card)
            # Phase L: durable live ledger (never flattens predictions)
            try:
                from cascade.live_ledger import insert_from_copilot_card

                uid = insert_from_copilot_card(card)
                print(f"  [ledger] uuid={uid} cov={card.cov_label} vol={card.vol.get('vol_prob')}")
            except Exception as le:
                print(f"  [ledger] write failed: {le}")
        except Exception as e:
            print(f"  [ERROR] {s.upper()}: {e}")
            import traceback
            traceback.print_exc()

    if not cards:
        print("[Copilot] 无成功结果")
        return 1

    print()
    render_cli(cards, asof)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    sym_tag = "_".join(c.symbol for c in cards)
    if len(sym_tag) > 40:
        sym_tag = f"{len(cards)}sym"
    md_path = args.out_dir / f"{ts}_{sym_tag}.md"
    write_markdown(cards, asof, md_path)

    try:
        from rich.console import Console
        Console().print(f"\n[bold green]详细 Markdown 研报已生成:[/bold green] {md_path}")
    except Exception:
        print(f"\n详细 Markdown 研报已生成: {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
