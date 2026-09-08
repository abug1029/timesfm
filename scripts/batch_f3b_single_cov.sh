#!/bin/bash
# 批次 F3b — 单协变量穷举: hourly_slope × 9 + ha_body × 5 = 14 tests
# F3 子批次 2/3
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f3b_progress.jsonl"
LOG="reports/data_ops/batch_f3b.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_f3b"

echo "=== batch_f3b START $(date -Iseconds) ===" >> "$LOG"

# hourly_slope × 9 品种 (后 9, 排除 AO)
for sym in cf i jm jd sp ta ur sh p; do
  batch_run_one "$sym" "hourly_slope" "F3b-hs-$sym" "$JSONL" "$LOG"
done

# ha_body × 5 品种 (前 5, 排除 CJ/FG/FU/LH/SP)
for sym in ss sr ma rb eg; do
  batch_run_one "$sym" "ha_body" "F3b-hb-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f3b DONE $(date -Iseconds) ===" | tee -a "$LOG"
