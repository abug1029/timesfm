#!/bin/bash
# 批次 F3a — 单协变量穷举: hourly_slope × 10 = 10 tests
# F3 子批次 1/3
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f3a_progress.jsonl"
LOG="reports/data_ops/batch_f3a.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_f3a"

echo "=== batch_f3a START $(date -Iseconds) ===" >> "$LOG"

# hourly_slope × 10 品种 (前 10, 排除 AO)
for sym in ss sr cj fg fu lh ma rb eg bu; do
  batch_run_one "$sym" "hourly_slope" "F3a-hs-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f3a DONE $(date -Iseconds) ===" | tee -a "$LOG"
