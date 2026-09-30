#!/usr/bin/env python3
"""
scheme_migrator.py — FM_a 品种分类自动迁移

对比最新月度回测的 classify() 结果与 prediction_scheme.py 中的固化分类，
发现分类变化时生成迁移提案。

用法:
    python scripts/scheme_migrator.py
"""

import json
import re
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = FM_ROOT / "reports"
BACKTEST_DIR = REPORTS_DIR / "monthly_backtest"
PROPOSAL_FILE = REPORTS_DIR / "scheme_migration_proposals.json"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES


def load_current_scheme_types() -> dict:
    """从 prediction_scheme.py 读取各品种的当前 scheme_type。"""
    types = {}
    scheme_path = FM_ROOT / "config" / "prediction_scheme.py"
    if not scheme_path.exists():
        return types
    try:
        text = scheme_path.read_text(encoding="utf-8")
        for m in re.finditer(
            r'symbol=["\'](\w+)["\'].*?scheme_type=["\'](\w+)["\']',
            text, re.DOTALL
        ):
            types[m.group(1).lower()] = m.group(2)
    except Exception:
        pass
    return types


def load_latest_backtest_classify() -> dict:
    """从最新月度回测报告中提取 classify 结果。

    解析 history.json 中最近一个月的分类。
    """
    history_file = BACKTEST_DIR / "history.json"
    if not history_file.exists():
        return {}

    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        months = sorted(data.keys())
        if not months:
            return {}
        latest = data[months[-1]]
        # categories 格式: {"trend": ["ss", "sp"], "stable": ["rb", "fu"], ...}
        categories = latest.get("categories", {})
        # 反转为 {symbol: category}
        result = {}
        for cat, symbols in categories.items():
            for sym in symbols:
                result[sym.lower()] = cat
        return result
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def load_latest_metrics() -> dict:
    """从 history.json 最近一个月提取各品种的指标。"""
    history_file = BACKTEST_DIR / "history.json"
    if not history_file.exists():
        return {}
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        months = sorted(data.keys())
        if not months:
            return {}
        latest = data[months[-1]]
        metrics = {}
        for item in latest.get("summary", []):
            sym = item["symbol"].lower()
            metrics[sym] = {
                "dir_acc": item.get("dir_acc", 0),
                "mape": item.get("mape", 0),
                "decay": item.get("decay", 0),
            }
        return metrics
    except Exception:
        return {}


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 🔄 分类迁移提案\n")
    print(f"**时间**: {now_str}\n")

    current_types = load_current_scheme_types()
    new_types = load_latest_backtest_classify()
    metrics = load_latest_metrics()

    if not current_types:
        print("> 无固化方案数据\n")
        return

    if not new_types:
        print("> 无回测分类数据，请先运行 monthly_backtest.py\n")
        return

    # 对比
    proposals = []
    consistent = []
    for sym in current_types:
        curr = current_types.get(sym)
        new = new_types.get(sym)
        if curr and new and curr != new:
            m = metrics.get(sym, {})
            proposals.append({
                "symbol": sym,
                "name": SYMBOL_NAMES.get(sym, ""),
                "current_type": curr,
                "proposed_type": new,
                "dir_acc": m.get("dir_acc", 0),
                "mape": m.get("mape", 0),
                "decay": m.get("decay", 0),
                "timestamp": now_str,
            })
        elif curr and new:
            consistent.append(sym)

    if proposals:
        print(f"## 迁移提案 ({len(proposals)} 个)\n")
        print("| 品种 | 名称 | 当前分类 | 建议分类 | DirAcc | MAPE | 理由 |")
        print("|------|------|---------|---------|:------:|:----:|------|")

        for p in proposals:
            # 生成理由
            if p["proposed_type"] == "oscillation" and p["current_type"] != "oscillation":
                reason = "DirAcc 下降到震荡区间"
            elif p["proposed_type"] == "trend" and p["current_type"] != "trend":
                reason = "DirAcc 提升到趋势区间"
            elif p["proposed_type"] == "high_error":
                reason = "MAPE 超过 5%"
            elif p["proposed_type"] == "stable":
                reason = "MAPE <2%，适合稳定型策略"
            else:
                reason = f"指标更符合 {p['proposed_type']} 特征"

            print(
                f"| `{p['symbol']}` | {p['name']} "
                f"| {p['current_type']} | **{p['proposed_type']}** "
                f"| {p['dir_acc']:.1%} | {p['mape']:.2f}% "
                f"| {reason} |"
            )

        # 保存提案
        PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROPOSAL_FILE.write_text(
            json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n> 提案已保存到 `{PROPOSAL_FILE.name}`，需人工确认后修改 `prediction_scheme.py`。")
    else:
        print("✅ 所有品种分类一致，无需迁移\n")

    print(f"\n## 汇总\n")
    print(f"- 固化品种: {len(current_types)}")
    print(f"- 分类一致: {len(consistent)}")
    print(f"- 需迁移: {len(proposals)}")

    json.dump({
        "proposal_count": len(proposals),
        "consistent_count": len(consistent),
        "proposals": proposals,
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
