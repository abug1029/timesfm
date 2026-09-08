#!/bin/bash
# Phase 15a 修复重跑: StdDev (returns std) + VWAP (decay fill)
# 6 品种 x 2 协变量 = 12 tests
# 修复项:
#   1. StdDev: std(close,20) -> std(returns,20) (已在 features.py 修复)
#   2. VWAP:  np.full 常数填充 -> _decay_fill 衰减填充 (已在 features.py 修复)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_p15a_fix_rerun.jsonl"
LOG="reports/data_ops/batch_p15a_fix_rerun.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_p15a_fix_rerun"

echo "=== batch_p15a_fix_rerun START $(date -Iseconds) ===" >> "$LOG"
echo "修复项: StdDev=returns_std, VWAP=decay_fill" >> "$LOG"

for SYM in jm ma ur fg cf ao; do
    # StdDev (修复后重跑)
    batch_run_one "$SYM" "stddev" "P15fix-${SYM}-stddev" "$JSONL" "$LOG"

    # VWAP deviation (修复后重跑)
    batch_run_one "$SYM" "vwap_deviation" "P15fix-${SYM}-vwap" "$JSONL" "$LOG"
done

echo "=== batch_p15a_fix_rerun DONE $(date -Iseconds) ===" | tee -a "$LOG"
