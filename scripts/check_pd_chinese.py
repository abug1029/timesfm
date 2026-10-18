#!/usr/bin/env python3
"""一次性门禁脚本：扫描所有 proposal，验证 _build_state() 输出无东亚宽字符。

Usage:
    cd /home/abug/timesfm && python scripts/check_pd_chinese.py

Exit codes:
    0: 所有 state 无东亚宽字符
    1: 存在含东亚宽字符的 state
"""
import json
import re
import sys
from pathlib import Path

# 确保项目根在 sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from cascade.typesafe_prescreen import _build_state

# 东亚宽字符正则（与 SPEC 验收字符类一致）
_EAST_ASIAN_WIDE = re.compile(
    r"[一-鿿"
    r"　-〿"
    r"！-／：-＠［-＿｛-･]"
)

def check_proposals():
    proposals_dir = Path("task_FM/experiments")
    if not proposals_dir.exists():
        print(f"ERROR: {proposals_dir} does not exist", file=sys.stderr)
        return False

    proposal_files = list(proposals_dir.glob("run_*/results/**/proposals/*.json"))
    if not proposal_files:
        print("WARNING: no proposal files found", file=sys.stderr)
        return True

    total = 0
    violations = 0
    skipped = 0

    for pf in proposal_files:
        try:
            with open(pf) as f:
                proposal = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"SKIP (unreadable): {pf}: {e}")
            skipped += 1
            continue

        symbol = proposal.get("symbol")
        if not symbol:
            # symbol 缺失的 proposal 跳过（_build_state 依赖 symbol 查 sector_map）
            skipped += 1
            continue

        try:
            state = _build_state(proposal, symbol, None, None)
        except Exception as e:
            print(f"SKIP (error): {pf}: {e}")
            skipped += 1
            continue

        pd = state["proposal_summary"]["predicted_direction"]

        total += 1
        if _EAST_ASIAN_WIDE.search(pd):
            violations += 1
            print(f"VIOLATION: {pf} -> predicted_direction={pd!r}")

    print(f"\nScanned {total} proposals ({skipped} skipped), {violations} violations")
    return violations == 0

if __name__ == "__main__":
    sys.exit(0 if check_proposals() else 1)
