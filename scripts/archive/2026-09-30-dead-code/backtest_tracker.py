#!/usr/bin/env python3
"""
回测指标追踪脚本 — FM_a 期货版

对比最近两个月的回测结果，输出退化告警。
读取 reports/monthly_backtest/history.json。

用法:
    python scripts/backtest_tracker.py
    python scripts/backtest_tracker.py --json-only
"""

import json
import os
import sys
from typing import Any

# Windows UTF-8 输出修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HISTORY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "reports", "monthly_backtest", "history.json"
)

# 告警阈值（期货波动较大，适当放宽）
DIR_ACC_DROP_THRESHOLD = 0.05       # 方向准确率下降超过 5 个百分点
MAPE_INCREASE_THRESHOLD = 0.5       # MAPE 上升超过 0.5 个百分点 (期货比股票波动大)
DECAY_INCREASE_THRESHOLD = 0.2      # decay 上升超过 0.2


def load_history(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        print(f"错误: 找不到历史文件 {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_symbol_index(summary: list[dict]) -> dict[str, dict]:
    """以 symbol 为 key 建立索引。"""
    return {item["symbol"]: item for item in summary}


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.1%}"


def fmt_abs(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.3f}"


def get_category(symbol: str, categories: dict) -> str | None:
    """查找 symbol 所属分类。"""
    for cat, symbols in categories.items():
        if symbol in symbols:
            return cat
    return None


def main():
    history = load_history(HISTORY_PATH)

    if not history:
        print("错误: history.json 为空", file=sys.stderr)
        sys.exit(1)

    months = sorted(history.keys())

    if len(months) < 2:
        msg = "仅一个月数据，无法对比"
        print(msg)
        json.dump({"message": msg, "months": len(months)}, sys.stderr, ensure_ascii=False)
        return

    prev_month = months[-2]
    curr_month = months[-1]

    prev_data = history[prev_month]
    curr_data = history[curr_month]

    prev_index = build_symbol_index(prev_data.get("summary", []))
    curr_index = build_symbol_index(curr_data.get("summary", []))

    prev_categories = prev_data.get("categories", {})
    curr_categories = curr_data.get("categories", {})

    # 收集所有出现过的 symbol
    all_symbols = sorted(set(list(prev_index.keys()) + list(curr_index.keys())))

    # ── 对比计算 ──

    rows: list[dict] = []
    alerts: list[dict] = []
    category_changes: list[dict] = []

    for sym in all_symbols:
        prev = prev_index.get(sym)
        curr = curr_index.get(sym)

        if prev is None:
            rows.append({
                "symbol": sym,
                "name": curr.get("name", ""),
                "dir_acc_delta": None,
                "mape_delta": None,
                "decay_delta": None,
                "status": "新增",
            })
            continue

        if curr is None:
            rows.append({
                "symbol": sym,
                "name": prev.get("name", ""),
                "dir_acc_delta": None,
                "mape_delta": None,
                "decay_delta": None,
                "status": "移除",
            })
            continue

        prev_da = prev.get("dir_acc")
        curr_da = curr.get("dir_acc")
        prev_mp = prev.get("mape")
        curr_mp = curr.get("mape")
        prev_dc = prev.get("decay")
        curr_dc = curr.get("decay")

        da_delta = (curr_da - prev_da) if (prev_da is not None and curr_da is not None) else None
        mp_delta = (curr_mp - prev_mp) if (prev_mp is not None and curr_mp is not None) else None
        dc_delta = (curr_dc - prev_dc) if (prev_dc is not None and curr_dc is not None) else None

        rows.append({
            "symbol": sym,
            "name": curr.get("name", prev.get("name", "")),
            "dir_acc_delta": da_delta,
            "mape_delta": mp_delta,
            "decay_delta": dc_delta,
            "status": "ok",
        })

        # 告警判断
        sym_alerts = []
        if da_delta is not None and da_delta < -DIR_ACC_DROP_THRESHOLD:
            sym_alerts.append(f"dir_acc 下降 {abs(da_delta):.1%}")
        if mp_delta is not None and mp_delta > MAPE_INCREASE_THRESHOLD:
            sym_alerts.append(f"mape 上升 {mp_delta:.2f}pp")
        if dc_delta is not None and dc_delta > DECAY_INCREASE_THRESHOLD:
            sym_alerts.append(f"decay 上升 {dc_delta:+.2f}")

        if sym_alerts:
            alerts.append({
                "symbol": sym,
                "name": curr.get("name", ""),
                "alerts": sym_alerts,
            })

        # 分类变化
        prev_cat = get_category(sym, prev_categories)
        curr_cat = get_category(sym, curr_categories)
        if prev_cat and curr_cat and prev_cat != curr_cat:
            category_changes.append({
                "symbol": sym,
                "name": curr.get("name", ""),
                "from": prev_cat,
                "to": curr_cat,
            })

    # ── 输出 Markdown 报告 ──

    print(f"# 回测指标对比 ({prev_month} → {curr_month})\n")

    print(f"| 品种 | 名称 | dir_acc 变化 | mape 变化 | decay 变化 | 状态 |")
    print(f"|------|------|-------------|-----------|-----------|------|")
    for r in rows:
        da_s = fmt_pct(r["dir_acc_delta"])
        mp_s = fmt_abs(r["mape_delta"])
        dc_s = fmt_abs(r["decay_delta"])
        status = r["status"]
        if status == "ok" and r["symbol"] in {a["symbol"] for a in alerts}:
            status = "⚠️"
        print(f"| {r['symbol']} | {r['name']} | {da_s} | {mp_s} | {dc_s} | {status} |")

    print()
    if alerts:
        print("## ⚠️ 退化告警\n")
        for a in alerts:
            detail = "; ".join(a["alerts"])
            print(f"- **{a['symbol']}** ({a['name']}): {detail}")
    else:
        print("## ✅ 无退化告警")

    print()
    if category_changes:
        print("## 分类变化\n")
        for c in category_changes:
            print(f"- **{c['symbol']}** ({c['name']}): {c['from']} → {c['to']}")
    else:
        print("## 分类无变化")

    # ── JSON 摘要输出到 stderr ──

    summary = {
        "prev_month": prev_month,
        "curr_month": curr_month,
        "total_symbols": len(all_symbols),
        "alert_count": len(alerts),
        "category_change_count": len(category_changes),
        "alerts": [
            {"symbol": a["symbol"], "name": a["name"], "details": a["alerts"]}
            for a in alerts
        ],
        "category_changes": category_changes,
        "rows": [
            {
                "symbol": r["symbol"],
                "dir_acc_delta": r["dir_acc_delta"],
                "mape_delta": r["mape_delta"],
                "decay_delta": r["decay_delta"],
                "status": r["status"],
            }
            for r in rows
        ],
    }
    json.dump(summary, sys.stderr, ensure_ascii=False, indent=2)
    print(file=sys.stderr)


if __name__ == "__main__":
    main()
