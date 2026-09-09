#!/bin/bash
# 批次 F2b — 单协变量穷举: oi × 10 + reversal_shadow × 3 = 13 tests
# F2 子批次 2/3 (oi 后 10 品种 + reversal_shadow 前 3 品种)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f2b_progress.jsonl"
LOG="reports/data_ops/batch_f2b.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_f2b"

echo "=== batch_f2b START $(date -Iseconds) ===" >> "$LOG"

# oi × 10 品种 (后 10)
for sym in cf i jm jd ao sp ta ur sh p; do
  batch_run_one "$sym" "oi" "F2b-oi-$sym" "$JSONL" "$LOG"
done

# reversal_shadow × 3 品种 (前 3, 排除 SS)
for sym in sr cj fg; do
  batch_run_one "$sym" "reversal_shadow" "F2b-rev-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f2b DONE $(date -Iseconds) ===" | tee -a "$LOG"
