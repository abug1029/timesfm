#!/bin/bash
# 批次 F2a — 单协变量穷举: oi × 10 = 10 tests
# F2 子批次 1/3 (oi 前 10 品种)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f2a_progress.jsonl"
LOG="reports/data_ops/batch_f2a.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_f2a"

echo "=== batch_f2a START $(date -Iseconds) ===" >> "$LOG"

# oi × 10 品种 (前 10)
for sym in ss sr cj fg fu lh ma rb eg bu; do
  batch_run_one "$sym" "oi" "F2a-oi-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f2a DONE $(date -Iseconds) ===" | tee -a "$LOG"
