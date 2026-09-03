"""
期货预测脚本 — 自动采集数据 + TimesFM 预测 + 生成报告

用法:
  python scripts/predict.py cf              # 单品种
  python scripts/predict.py cf fu p ss ao   # 多品种
  python scripts/predict.py --all           # 所有已采集品种
  python scripts/predict.py --all --collect # 先采集再预测
"""

import sys
import os
import argparse
import numpy as np
import pandas as pd
import torch
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.config import get_name, DEFAULT_SYMBOLS
from data.data_store import DataStore
from cascade.data_validator import ensure_fresh_data
# list_all_dbs 已移除


def predict_symbol(symbol: str, model, horizon: int = 22) -> dict:
    """对单个品种运行预测"""
    with DataStore(symbol) as store:
        arr = store.get_timesfm_input(days=250)
        if len(arr) < 50:
            return {"symbol": symbol, "error": f"数据不足 ({len(arr)} 天)"}

        point, quantile = model.forecast(horizon=horizon, inputs=[arr])

        future_dates = pd.bdate_range(
            start=datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1),
            periods=horizon
        )

        daily = []
        for i in range(horizon):
            daily.append({
                "day": i + 1,
                "date": future_dates[i].strftime("%Y-%m-%d"),
                "pred": float(point[0, i]),
                "p10": float(quantile[0, i, 1]),
                "p25": float(quantile[0, i, 3]),
                "p50": float(quantile[0, i, 5]),
                "p75": float(quantile[0, i, 7]),
                "p90": float(quantile[0, i, 9]),
            })

        result = {
            "symbol": symbol,
            "name": get_name(symbol),
            "latest": float(arr[-1]),
            "year_high": float(arr.max()),
            "year_low": float(arr.min()),
            "data_days": len(arr),
            "mean_pred": float(point[0].mean()),
            "final_pred": float(point[0, -1]),
            "min_pred": float(point[0].min()),
            "max_pred": float(point[0].max()),
            "change_pct": (float(point[0, -1]) / float(arr[-1]) - 1) * 100,
            "p10_floor": float(quantile[0, :, 1].min()),
            "p90_ceil": float(quantile[0, :, 9].max()),
            "week_avgs": [
                float(point[0, :min(5, horizon)].mean()) if horizon > 0 else 0,
                float(point[0, 5:min(10, horizon)].mean()) if horizon > 5 else 0,
                float(point[0, 10:min(15, horizon)].mean()) if horizon > 10 else 0,
                float(point[0, 15:horizon].mean()) if horizon > 15 else 0,
            ],
            "daily": daily,
        }

    return result


def generate_report(results: list, output_path: Path):
    """生成 Markdown 报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"# 期货预测报告")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 生成日期 | {now} |")
    lines.append(f"| 模型 | TimesFM 2.5 (200M) |")
    lines.append(f"| 数据来源 | TqSdk (天勤量化) |")
    symbols_str = " / ".join(f"{r['name']}{r['symbol'].upper()}" for r in results)
    lines.append(f"| 预测品种 | {symbols_str} |")
    lines.append(f"| 历史窗口 | 最近 250 个交易日 |")
    lines.append(f"| 预测周期 | 22 个交易日 (~1个月) |")
    lines.append("")

    # 横向对比
    lines.append("## 品种横向对比")
    lines.append("")
    lines.append("| 品种 | 当前价 | 年内高 | 年内低 | 月末预测 | 预测变动 | 趋势 |")
    lines.append("|------|------:|------:|------:|------:|------:|:----:|")
    for r in results:
        trend = "↑" if r["change_pct"] > 0.5 else "↓" if r["change_pct"] < -0.5 else "→"
        lines.append(
            f"| {r['name']} {r['symbol'].upper()} "
            f"| {r['latest']:,.0f} | {r['year_high']:,.0f} | {r['year_low']:,.0f} "
            f"| {r['final_pred']:,.0f} | {r['change_pct']:+.1f}% | {trend} |"
        )
    lines.append("")

    # 每个品种详情
    for r in results:
        lines.append(f"---")
        lines.append(f"## {r['name']} {r['symbol'].upper()}")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 当前价格 | {r['latest']:,.0f} |")
        lines.append(f"| 年内最高 | {r['year_high']:,.0f} |")
        lines.append(f"| 年内最低 | {r['year_low']:,.0f} |")
        lines.append(f"| 数据天数 | {r['data_days']} |")
        lines.append("")

        # 周度
        lines.append("### 周度汇总")
        lines.append("")
        lines.append("| 周 | 周均价 |")
        lines.append("|---|------:|")
        for i, avg in enumerate(r["week_avgs"]):
            if avg > 0:
                lines.append(f"| 第{i+1}周 | {avg:,.0f} |")
        lines.append("")

        # 逐日 (每5天一个)
        lines.append("### 逐日预测 (每5日)")
        lines.append("")
        lines.append("| 日 | 日期 | 预测价 | P10 | P50 | P90 |")
        lines.append("|---:|:-----|------:|------:|------:|------:|")
        for d in r["daily"]:
            if d["day"] in [1, 5, 10, 15, 20, 22]:
                lines.append(
                    f"| {d['day']} | {d['date']} | {d['pred']:,.0f} "
                    f"| {d['p10']:,.0f} | {d['p50']:,.0f} | {d['p90']:,.0f} |"
                )
        lines.append("")

        # 核心结论
        lines.append("### 核心结论")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 月末预测价 | {r['final_pred']:,.0f} ({r['change_pct']:+.1f}%) |")
        lines.append(f"| 预测最高 | {r['max_pred']:,.0f} |")
        lines.append(f"| 预测最低 | {r['min_pred']:,.0f} |")
        lines.append(f"| 悲观 (P10) | {r['p10_floor']:,.0f} |")
        lines.append(f"| 乐观 (P90) | {r['p90_ceil']:,.0f} |")
        lines.append("")

    # 风险提示
    lines.append("---")
    lines.append("")
    lines.append("⚠️ **风险提示**: TimesFM 为纯统计模型，不含基本面信息，预测仅供参考，不构成投资建议。")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已保存: {output_path}")


# XReg 指标因子列表
XREG_FACTORS = [
    "rsi6", "rsi12", "rsi24",
    "macd_dif", "macd_dea", "macd_bar",
    "ma5", "ma10", "ma20", "ma60",
    "boll_upper", "boll_mid", "boll_lower",
    "atr14",
    "oi_change", "oi_trend_5d", "volume_oi_ratio",
    "ccl_value",
]


def _extract_xreg_from_store(store, symbol: str):
    """从 main_continuous_1d 提取指标到 xreg_factors"""
    import pandas as pd
    total = 0
    for factor in XREG_FACTORS:
        try:
            df = pd.read_sql_query(
                f"SELECT dt, {factor} FROM main_continuous_1d WHERE {factor} IS NOT NULL",
                store.conn
            )
            if df.empty:
                continue
            rows = [(row["dt"], symbol, factor, float(row[factor]))
                    for _, row in df.iterrows()]
            store.conn.executemany(
                "INSERT OR REPLACE INTO xreg_factors (dt, symbol, factor_name, factor_value) VALUES (?, ?, ?, ?)",
                rows
            )
            store.conn.commit()
            total += len(rows)
        except Exception:
            pass
    return total


def main():
    parser = argparse.ArgumentParser(description="期货预测脚本")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--all", action="store_true", help="所有已采集品种")
    parser.add_argument("--collect", action="store_true", help="先采集再预测 (显式全量采集)")
    parser.add_argument("--no-auto-collect", action="store_true",
                        help="禁用自动采集 (默认在数据过期时自动采集)")
    parser.add_argument("--horizon", type=int, default=22, help="预测天数 (默认22)")
    args = parser.parse_args()

    if args.all:
        symbols = list(DEFAULT_SYMBOLS)
        if not symbols:
            print("暂无数据，请先运行 collect")
            return
    elif args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        parser.print_help()
        return

    auto_collect = not args.no_auto_collect

    # 显式采集 (--collect)
    if args.collect:
        from scripts.three_star_predict import ensure_data
        for symbol in symbols:
            print(f"采集 {symbol.upper()}...")
            r = ensure_data(symbol)
            print("  OK" if r["ok"] else f"  FAILED ({r['error']})")

    # 数据新鲜度检查 + 自动采集过期品种
    print(f"\n  [预检查] 验证 {len(symbols)} 个品种的数据"
          f"{' (auto-collect 已启用)' if auto_collect else ''}...")
    valid_symbols, skipped = ensure_fresh_data(symbols, auto_collect=auto_collect)
    symbols = valid_symbols

    # 加载模型
    if not symbols:
        print("无有效品种可预测 (全部数据校验失败)")
        return

    print("加载 TimesFM 模型...")
    torch.set_float32_matmul_precision("high")
    import timesfm
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    model.compile(timesfm.ForecastConfig(
        max_context=1024, max_horizon=256, normalize_inputs=True,
        use_continuous_quantile_head=True, force_flip_invariance=True,
        infer_is_positive=True, fix_quantile_crossing=True,
    ))

    # 预测
    results = []
    for symbol in symbols:
        print(f"预测 {symbol.upper()}...")
        r = predict_symbol(symbol, model, args.horizon)
        if "error" not in r:
            results.append(r)
        else:
            print(f"  [SKIP] {r['error']}")

    # 生成报告
    if results:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        if len(results) == 1:
            filename = f"{ts}_{results[0]['symbol']}.md"
        else:
            filename = f"{ts}_daily.md"
        output_path = Path(__file__).resolve().parent.parent / "reports" / filename
        generate_report(results, output_path)


if __name__ == "__main__":
    main()
