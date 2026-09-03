"""
品种指标分析预警脚本

用法:
  python scripts/variety_analysis.py                    # 所有固化品种
  python scripts/variety_analysis.py pp ta rb           # 指定品种
  python scripts/variety_analysis.py --all              # 全部品种 (含未固化)
  python scripts/variety_analysis.py sh --no-predict    # 跳过 TimesFM 预测

流程: 采集最新数据 → 技术分析 → CCL异动检测 → Copilot预测 → 保存报告
"""
import sys
import os
import warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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

import numpy as np
import pandas as pd
from datetime import datetime
from data.data_store import DataStore
from data.config import get_name, DEFAULT_SYMBOLS
from config.prediction_scheme import SCHEMES, get_scheme, list_solidified
from cascade.ccl_monitor import detect_anomalies
from cascade.data_validator import ensure_fresh_data
from scripts import copilot as copilot_mod
from scripts.copilot import load_knowledge_base, stars_label


def analyze_symbol(symbol: str, shared_model=None, kb: dict = None) -> dict:
    """单品种完整分析，返回结构化结果。

    如果传入 shared_model 和 kb，则额外运行 Copilot 推理（TimesFM 预测 + Vol 雷达 + 领航建议）。
    """
    result = {"symbol": symbol, "name": get_name(symbol)}

    with DataStore(symbol) as store:
        daily = store.get_main_continuous(limit=500)
        h1 = store.get_main_contract_1h(limit=480)
        ccl_alert = detect_anomalies(symbol, store)

    if daily.empty or len(daily) < 20:
        result["error"] = "日线数据不足"
        return result

    c = daily["close_price"]
    last = daily.iloc[-1]
    data_date = str(daily["dt"].iloc[-1])[:10]

    # 涨跌
    chg = {}
    for n, label in [(5, "5d"), (20, "20d"), (60, "60d")]:
        if len(c) > n:
            chg[label] = round((c.iloc[-1] / c.iloc[-n-1] - 1) * 100, 2)
        else:
            chg[label] = 0
    result["chg"] = chg

    # 高低点
    result["data_date"] = data_date
    result["close"] = float(c.iloc[-1])
    result["high_20"] = float(c.iloc[-20:].max())
    result["low_20"] = float(c.iloc[-20:].min())
    result["high_60"] = float(c.iloc[-60:].max()) if len(c) >= 60 else float(c.max())
    result["low_60"] = float(c.iloc[-60:].min()) if len(c) >= 60 else float(c.min())

    # 技术指标
    result["ma5"] = float(last.get("ma5", 0))
    result["ma10"] = float(last.get("ma10", 0))
    result["ma20"] = float(last.get("ma20", 0))
    result["ma60"] = float(last.get("ma60", 0))
    result["rsi6"] = float(last.get("rsi6", 0))
    result["rsi12"] = float(last.get("rsi12", 0))
    result["rsi24"] = float(last.get("rsi24", 0))
    result["kdj_k"] = float(last.get("kdj_k", 0))
    result["kdj_d"] = float(last.get("kdj_d", 0))
    result["kdj_j"] = float(last.get("kdj_j", 0))
    result["macd_dif"] = float(last.get("macd_dif", 0))
    result["macd_dea"] = float(last.get("macd_dea", 0))
    result["macd_bar"] = float(last.get("macd_bar", 0))
    result["boll_u"] = float(last.get("boll_upper", 0))
    result["boll_m"] = float(last.get("boll_mid", 0))
    result["boll_l"] = float(last.get("boll_lower", 0))
    result["atr14"] = float(last.get("atr14", 0))
    result["cci14"] = float(last.get("cci14", 0))

    # 均线排列
    p = result["close"]
    ma5, ma10, ma20, ma60 = result["ma5"], result["ma10"], result["ma20"], result["ma60"]
    if ma5 > ma10 > ma20 > ma60:
        result["ma_arrangement"] = "多头排列 🟢"
    elif ma5 < ma10 < ma20 < ma60:
        result["ma_arrangement"] = "空头排列 🔴"
    elif p < ma60 and p < ma20:
        result["ma_arrangement"] = "弱势 🔴"
    elif p > ma60 and p > ma20:
        result["ma_arrangement"] = "强势 🟢"
    else:
        result["ma_arrangement"] = "交叉 🟡"

    # 持仓
    oi = daily["open_interest"]
    result["oi"] = float(oi.iloc[-1])
    if len(oi) > 5:
        result["oi_chg5"] = float(oi.iloc[-1] - oi.iloc[-6])
        result["oi_pct5"] = round(result["oi_chg5"] / oi.iloc[-6] * 100, 2)
    else:
        result["oi_chg5"] = 0
        result["oi_pct5"] = 0
    if len(oi) > 20:
        result["oi_chg20"] = float(oi.iloc[-1] - oi.iloc[-21])
        result["oi_pct20"] = round(result["oi_chg20"] / oi.iloc[-21] * 100, 2)
    else:
        result["oi_chg20"] = 0
        result["oi_pct20"] = 0

    # CCL 近 5/10 日累计
    ccl_vals = daily["ccl_value"].tail(10).dropna()
    if len(ccl_vals) >= 5:
        result["ccl_5d"] = float(ccl_vals.tail(5).sum())
    else:
        result["ccl_5d"] = 0
    if len(ccl_vals) >= 10:
        result["ccl_10d"] = float(ccl_vals.tail(10).sum())
    else:
        result["ccl_10d"] = result["ccl_5d"]

    # CCL 近 12 日明细
    ccl_detail = daily[["dt", "close_price", "open_interest", "ccl_value", "ccl_label"]].tail(12)
    result["ccl_detail"] = ccl_detail.to_dict("records")

    # CCL 异动
    result["ccl_level"] = ccl_alert.overall_level
    result["ccl_emoji"] = ccl_alert.emoji
    result["ccl_label"] = ccl_alert.latest_label
    result["ccl_value"] = ccl_alert.latest_ccl
    result["ccl_p95"] = ccl_alert.p95
    result["ccl_p99"] = ccl_alert.p99
    result["ccl_signals"] = [
        {"type": s.signal_type, "level": s.level, "desc": s.description}
        for s in ccl_alert.signals
    ]

    # 1H
    if not h1.empty:
        result["h1_range"] = f'{h1["dt"].iloc[0]} ~ {h1["dt"].iloc[-1]}'
        result["h1_bars"] = len(h1)
        result["h1_latest"] = float(h1["close_price"].iloc[-1])
    else:
        result["h1_range"] = "无"
        result["h1_bars"] = 0
        result["h1_latest"] = 0

    # 综合信号统计
    bull = 0
    bear = 0
    # 短期动量
    if chg.get("5d", 0) > 2:
        bull += 1
    elif chg.get("5d", 0) < -2:
        bear += 1
    # MACD
    if result["macd_bar"] > 0:
        bull += 1
    elif result["macd_bar"] < 0:
        bear += 1
    # CCL 5日
    if result["ccl_5d"] > 0:
        bull += 1
    elif result["ccl_5d"] < 0:
        bear += 1
    # OI 5日
    if result["oi_pct5"] > 1:
        bull += 1
    elif result["oi_pct5"] < -1:
        bear += 1
    # RSI
    if result["rsi6"] > 55:
        bull += 1
    elif result["rsi6"] < 45:
        bear += 1
    # MA排列
    if "多头" in result["ma_arrangement"] or "强势" in result["ma_arrangement"]:
        bull += 1
    elif "空头" in result["ma_arrangement"] or "弱势" in result["ma_arrangement"]:
        bear += 1

    result["bull_count"] = bull
    result["bear_count"] = bear
    if bull >= 4 and bear <= 1:
        result["overall"] = "偏多 🟢"
    elif bear >= 4 and bull <= 1:
        result["overall"] = "偏空 🔴"
    elif bull > bear + 1:
        result["overall"] = "温和偏多 🟢"
    elif bear > bull + 1:
        result["overall"] = "温和偏空 🔴"
    else:
        result["overall"] = "观望 🟡"

    # 固化方案信息
    scheme = get_scheme(symbol)
    if scheme:
        result["stars"] = scheme.stars
        result["dir_acc"] = scheme.dir_acc
        result["mape"] = scheme.mape
        result["scheme_type"] = scheme.scheme_type
    else:
        result["stars"] = 0
        result["dir_acc"] = 0
        result["mape"] = 0
        result["scheme_type"] = "未固化"

    # ── Copilot 推理（TimesFM 预测 + Vol 雷达 + 领航建议） ──
    if shared_model is not None and kb is not None:
        try:
            card = copilot_mod.run_one(symbol, shared_model=shared_model, kb=kb)
            result["copilot"] = {
                "credit_stars": int(card.kb.get("credit_stars", 0)),
                "historical_pf": card.kb.get("historical_pf"),
                "historical_diracc": card.kb.get("historical_diracc"),
                "vol_sensitivity": card.kb.get("vol_sensitivity", "UNKNOWN"),
                "best_hold_period": card.kb.get("best_hold_period", "—"),
                "vol_prob": card.vol.get("vol_prob"),
                "vol_threshold": card.vol.get("threshold"),
                "vol_high": bool(card.vol.get("high_vol")),
                "vol_message": card.vol.get("message", ""),
                "direction": card.direction,
                "delta_pct": card.delta_pct,
                "point_forecast": card.point_forecast,
                "p10": card.p10,
                "p90": card.p90,
                "advisory": card.advisory,
                "last_1h_dt": card.last_1h_dt,
                "daily_slope": card.daily_slope,
                "cov_label": card.cov_label,
                "current_price": card.current_price,
                "t24": card.t24,
            }
        except Exception as e:
            result["copilot_error"] = str(e)

    return result


def format_report(r: dict) -> str:
    """生成 Markdown 报告"""
    if "error" in r:
        return f"# {r['name']}({r['symbol'].upper()}) 分析预警\n\n⚠️ {r['error']}\n"

    lines = []
    lines.append(f"# {r['name']}({r['symbol'].upper()}) 指标分析预警报告")
    lines.append(f"")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据截至: {r['data_date']}")
    lines.append(f"")

    # 走势
    lines.append("## 一、价格走势")
    lines.append(f"")
    chg = r["chg"]
    lines.append(f"- 近5日涨跌: **{chg.get('5d',0):+.2f}%** / 20日: {chg.get('20d',0):+.2f}% / 60日: {chg.get('60d',0):+.2f}%")
    lines.append(f"- 20日: 高{r['high_20']:,.0f} 低{r['low_20']:,.0f} | 60日: 高{r['high_60']:,.0f} 低{r['low_60']:,.0f}")
    lines.append(f"- 当前: **{r['close']:,.0f}**")
    lines.append(f"")

    # 技术指标
    lines.append("## 二、技术指标")
    lines.append(f"")
    lines.append(f"| 指标 | 值 | 信号 |")
    lines.append(f"|------|-----|------|")
    lines.append(f"| 均线 | MA5={r['ma5']:,.0f} MA10={r['ma10']:,.0f} MA20={r['ma20']:,.0f} MA60={r['ma60']:,.0f} | {r['ma_arrangement']} |")
    # RSI
    rsi6_sig = "🔴 超卖" if r["rsi6"] < 20 else ("🟢 超买" if r["rsi6"] > 80 else ("🟢 偏多" if r["rsi6"] > 55 else ("🔴 偏空" if r["rsi6"] < 45 else "🟡 中性")))
    lines.append(f"| RSI6 | {r['rsi6']:.1f} | {rsi6_sig} |")
    # KDJ
    kdj_sig = "🟠 超买" if r["kdj_j"] > 100 else ("🔴 超卖" if r["kdj_j"] < 0 else ("🟢 偏多" if r["kdj_j"] > 50 else "🔴 偏空"))
    lines.append(f"| KDJ | K={r['kdj_k']:.1f} D={r['kdj_d']:.1f} J={r['kdj_j']:.1f} | {kdj_sig} |")
    # MACD
    macd_sig = "🟢 金叉" if r["macd_bar"] > 0 else "🔴 死叉"
    lines.append(f"| MACD | DIF={r['macd_dif']:.1f} DEA={r['macd_dea']:.1f} BAR={r['macd_bar']:.1f} | {macd_sig} |")
    # CCI
    cci_sig = "🔴 超卖" if r["cci14"] < -100 else ("🔴 超买" if r["cci14"] > 100 else "🟡 中性")
    lines.append(f"| CCI14 | {r['cci14']:.1f} | {cci_sig} |")
    # BOLL
    boll_pos = "上方" if r["close"] > r["boll_u"] else ("中轨附近" if abs(r["close"] - r["boll_m"]) < r["atr14"] else ("下轨附近" if r["close"] < r["boll_l"] else "中下区域"))
    lines.append(f"| BOLL | U={r['boll_u']:,.0f} M={r['boll_m']:,.0f} L={r['boll_l']:,.0f} | {boll_pos} |")
    lines.append(f"| ATR14 | {r['atr14']:,.0f} | 日波动{r['atr14']/r['close']*100:.1f}% |")
    lines.append(f"")

    # 持仓
    lines.append("## 三、持仓分析")
    lines.append(f"")
    lines.append(f"- 最新OI: {r['oi']:,.0f}")
    lines.append(f"- 5日变化: {r['oi_chg5']:+,.0f} ({r['oi_pct5']:+.2f}%)")
    lines.append(f"- 20日变化: {r['oi_chg20']:+,.0f} ({r['oi_pct20']:+.2f}%)")
    lines.append(f"")

    # CCL 明细
    lines.append("## 四、CCL 持仓力量")
    lines.append(f"")
    lines.append(f"近期CCL累计: 5日 **{r['ccl_5d']:+,.0f}** / 10日 **{r['ccl_10d']:+,.0f}**")
    lines.append(f"")
    lines.append(f"| 日期 | 收盘 | OI | CCL | 标签 |")
    lines.append(f"|------|-----:|----:|----:|------|")
    for row in r["ccl_detail"]:
        lines.append(f"| {str(row['dt'])[:10]} | {row['close_price']:,.0f} | {row['open_interest']:,.0f} | {row['ccl_value']:,.0f} | {row['ccl_label']} |")
    lines.append(f"")

    # CCL 异动
    lines.append(f"## 五、CCL 异动预警 {r['ccl_emoji']} {r['ccl_level']}")
    lines.append(f"")
    lines.append(f"当前: {r['ccl_label']} (CCL={r['ccl_value']:+,.0f})")
    lines.append(f"阈值: P95={r['ccl_p95']:,.0f} / P99={r['ccl_p99']:,.0f}")
    lines.append(f"")
    if r["ccl_signals"]:
        lines.append(f"| 信号 | 等级 | 描述 |")
        lines.append(f"|------|:----:|------|")
        for s in r["ccl_signals"]:
            em = {"WATCH": "🟡", "WARNING": "🟠", "CRITICAL": "🔴"}.get(s["level"], "⚪")
            lines.append(f"| {s['type']} | {em} {s['level']} | {s['desc']} |")
    else:
        lines.append(f"无异动信号。")
    lines.append(f"")

    # ── Copilot 模型预测（如有） ──────────────────────────────
    cp = r.get("copilot")
    if cp:
        # 信用背书
        lines.append("## 六、信用背书 (Copilot)")
        lines.append("")
        stars = cp["credit_stars"]
        pf = cp.get("historical_pf")
        da = cp.get("historical_diracc")
        vs = cp.get("vol_sensitivity", "UNKNOWN")
        hold = cp.get("best_hold_period", "—")
        lines.append(f"- **综合评级**: {stars_label(stars)}")
        if pf is not None and da is not None:
            lines.append(f"- **历史信用**: 胜率 {da:.0%}，盈亏比(PF) {pf:.2f}")
        lines.append(f"- **Vol 敏感度 (L1)**: {vs}")
        lines.append(f"- **建议持有窗口**: {hold}")
        lines.append(f"- **协变量**: `{cp.get('cov_label', '—')}`")
        lines.append("")

        # 模型预测
        lines.append("## 七、模型预测 (TimesFM)")
        lines.append("")
        lines.append(f"- **方向**: {cp['direction']}（T+24 预期 {cp['delta_pct']:+.2f}%）")
        lines.append(f"- **日线斜率**: {cp['daily_slope']:+.4f}% / bar")
        lines.append(f"- **1H 截面**: {cp.get('last_1h_dt', '—')}")
        lines.append(f"- **预测终点 T+24**: {cp['t24']:,.1f}")
        lines.append("")

        fc = cp["point_forecast"]
        p10 = cp.get("p10", [])
        p90 = cp.get("p90", [])
        has_quantile = p10 and p10[0] == p10[0]
        lines.append("| 时点 | 点预测 | P10 | P90 | vs现价 |")
        lines.append("|-----:|-------:|----:|----:|-------:|")
        for i, px in enumerate(fc, 1):
            _p10 = p10[i-1] if i-1 < len(p10) else float("nan")
            _p90 = p90[i-1] if i-1 < len(p90) else float("nan")
            chg = (px / cp["current_price"] - 1) * 100 if cp["current_price"] else 0
            p10s = f"{_p10:,.1f}" if _p10 == _p10 else "—"
            p90s = f"{_p90:,.1f}" if _p90 == _p90 else "—"
            mark = " **" if i in (4, 8, 12, 24) else ""
            lines.append(f"| T+{i}{mark} | {px:,.1f} | {p10s} | {p90s} | {chg:+.2f}% |")
        lines.append("")

        # P10/P90 止损锚
        if has_quantile:
            lines.append(f"### 止盈止损锚点")
            lines.append(f"- P10 最低 ≈ **{min(p10):,.1f}** / P90 最高 ≈ **{max(p90):,.1f}**")
            lines.append(f"")

        # Vol 雷达
        lines.append("### Vol 风险雷达")
        vp = cp.get("vol_prob")
        thr = cp.get("vol_threshold")
        if vp is not None:
            tag = "⚠️ 高波预警" if cp["vol_high"] else "✅ 正常"
            lines.append(f"- {tag}: Vol_Prob = {vp:.2f} {'≥' if cp['vol_high'] else '<'} {thr:.2f}")
        else:
            lines.append(f"- 特征不足，雷达跳过")
        lines.append(f"- 板块阈值来源: {cp.get('vol_message', '')}")
        lines.append("")

        # 领航建议
        lines.append("### 领航建议")
        for adv in cp.get("advisory", []):
            emoji = "⚠️" if "强警示" in adv or "警告" in adv else ("⚡" if "机会" in adv else "•")
            lines.append(f"- {emoji} {adv}")
        lines.append("")
    elif r.get("copilot_error"):
        lines.append(f"## 六~七、模型预测 ⚠️ Copilot 推理失败: {r['copilot_error']}")
        lines.append("")

    # 综合（原六 → 八 or 六）
    section_num = "八" if cp else "六"
    lines.append(f"## {section_num}、综合判断")
    lines.append(f"")
    lines.append(f"**{r['overall']}** (多信号 {r['bull_count']} / 空信号 {r['bear_count']})")
    lines.append(f"")

    # 关键价位
    lines.append(f"### 关键价位")
    lines.append(f"- 上方: MA5({r['ma5']:,.0f}) → MA20({r['ma20']:,.0f}) → MA60({r['ma60']:,.0f})")
    lines.append(f"- 下方: BOLL下轨({r['boll_l']:,.0f}) → BOLL中轨({r['boll_m']:,.0f}) → BOLL上轨({r['boll_u']:,.0f})")
    if cp:
        lines.append(f"- P10 防守: {min(cp['p10']):,.0f}" if cp.get("p10") and cp["p10"][0] == cp["p10"][0] else "")
        lines.append(f"- P90 压力: {max(cp['p90']):,.0f}" if cp.get("p90") and cp["p90"][0] == cp["p90"][0] else "")
    lines.append(f"")

    # 固化方案
    if r["stars"] > 0:
        lines.append(f"### 预测方案")
        lines.append(f"- {'⭐' * r['stars']} {r['scheme_type']} | DirAcc={r['dir_acc']:.0%} MAPE={r['mape']:.2f}%")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"> 本报告基于技术指标自动生成，不构成投资建议。")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="品种指标分析预警")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--all", action="store_true", help="全部品种")
    parser.add_argument("--no-collect", action="store_true", help="跳过数据采集")
    parser.add_argument("--with-predict", action="store_true", default=True,
                        help="启用 Copilot/TimesFM 预测（默认开启）")
    parser.add_argument("--no-predict", action="store_true",
                        help="禁用 Copilot/TimesFM 预测（仅技术面+CCL）")
    args = parser.parse_args()

    use_predict = args.with_predict and not args.no_predict

    if args.all:
        symbols = DEFAULT_SYMBOLS
    elif args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        # 默认: 固化品种 + 重点品种
        solidified = list_solidified()
        extra = ["pp", "ta"]  # 额外关注的品种
        symbols = list(dict.fromkeys([s.lower() for s in solidified] + extra))

    reports_base = Path(__file__).resolve().parent.parent / "reports"
    reports_base.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    print(f"品种指标分析预警 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"品种数: {len(symbols)} | Copilot: {'ON' if use_predict else 'OFF'}")
    print(f"报告按品种保存至: {reports_base}/<symbol>/")
    print("=" * 70)

    # ── 加载 Copilot 组件（模型 + KB，一次性） ──────────────
    shared_model = None
    kb = None
    if use_predict:
        print(f"\n[0/3] 加载 Copilot 组件...")
        try:
            kb = load_knowledge_base()
            from cascade.daily_model import DailyModel
            bootstrap = DailyModel()
            shared_model = bootstrap.model
            print(f"  KB: {len(kb.get('symbols', {}))} 品种 | TimesFM 2.5 已加载")
        except Exception as e:
            print(f"  ⚠️ Copilot 加载失败，降级为纯技术面: {e}")
            use_predict = False
            shared_model = None
            kb = None

    # 1. 数据新鲜度检查 + 按需采集
    if not args.no_collect:
        print(f"\n[1/3] 检查数据新鲜度...")
        valid_symbols, skipped = ensure_fresh_data(symbols, auto_collect=True)
        for skip_info in skipped:
            print(f"  {skip_info['symbol'].upper():<4} ⚠️ {skip_info['error']}")
        symbols = valid_symbols
        if not symbols:
            print("无有效品种可分析 (全部数据校验失败)")
            return
    else:
        print(f"\n[1/3] 跳过数据新鲜度检查 (--no-collect)")

    # 2. 分析
    print(f"\n[2/3] 运行分析...")
    results = []
    for s in symbols:
        try:
            r = analyze_symbol(s, shared_model=shared_model, kb=kb)
            cp_tag = ""
            if r.get("copilot"):
                cp = r["copilot"]
                vp = cp.get("vol_prob")
                vp_s = f"Vol={vp:.2f}" if vp is not None else "Vol=—"
                cp_tag = f" | {cp['direction']} {cp['delta_pct']:+.1f}% | {vp_s}"
            print(f"  {s.upper():<4} {r.get('overall', r.get('error', '?'))}{cp_tag}")
            results.append(r)
        except Exception as e:
            print(f"  {s.upper():<4} ❌ {e}")
            results.append({"symbol": s, "name": get_name(s), "error": str(e)})

    # 3. 保存报告 (按品种分类)
    print(f"\n[3/3] 保存报告...")
    for r in results:
        report = format_report(r)
        symbol_dir = reports_base / r['symbol']
        symbol_dir.mkdir(parents=True, exist_ok=True)
        path = symbol_dir / f"analysis_{ts}.md"
        path.write_text(report, encoding="utf-8")
        print(f"  {r['symbol'].upper():<4} → {path.relative_to(reports_base)}")

    # 4. 汇总表
    print(f"\n{'='*70}")
    print(f"{'品种':<6} {'综合':<12} {'5日涨跌':>8} {'OI 5日':>8} {'CCL异动':<12} {'CCL 5日累计':>14}")
    print(f"{'-'*70}")
    for r in results:
        if "error" in r:
            print(f"{r['symbol'].upper():<6} {'❌ '+r['error']}")
            continue
        chg5 = f"{r['chg'].get('5d',0):+.1f}%"
        oi5 = f"{r['oi_pct5']:+.1f}%"
        ccl5 = f"{r['ccl_5d']:+,.0f}"
        ccl_lv = f"{r['ccl_emoji']} {r['ccl_level']}"
        print(f"{r['symbol'].upper():<6} {r['overall']:<12} {chg5:>8} {oi5:>8} {ccl_lv:<12} {ccl5:>14}")

    # 信号汇总
    bull_list = [r for r in results if "多" in r.get("overall", "")]
    bear_list = [r for r in results if "空" in r.get("overall", "")]
    watch_list = [r for r in results if "观望" in r.get("overall", "")]
    alert_list = [r for r in results if r.get("ccl_level", "NORMAL") in ("WARNING", "CRITICAL")]

    print(f"\n--- 信号汇总 ---")
    print(f"偏多 ({len(bull_list)}): {', '.join(r['symbol'].upper() for r in bull_list) or '无'}")
    print(f"偏空 ({len(bear_list)}): {', '.join(r['symbol'].upper() for r in bear_list) or '无'}")
    print(f"观望 ({len(watch_list)}): {', '.join(r['symbol'].upper() for r in watch_list) or '无'}")
    print(f"CCL预警 ({len(alert_list)}): {', '.join(r['symbol'].upper() for r in alert_list) or '无'}")

    print(f"\n报告已保存: {reports_base}/<symbol>/analysis_{ts}.md")


if __name__ == "__main__":
    main()
