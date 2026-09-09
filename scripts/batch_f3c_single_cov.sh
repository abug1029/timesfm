#!/bin/bash
# 批次 F3c — 单协变量穷举: ha_body × 10 = 10 tests
# F3 子批次 3/3 (排除 CJ/FG/FU/LH/SP + F3b 已测的 SS/SR/MA/RB/EG)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f3c_progress.jsonl"
LOG="reports/data_ops/batch_f3c.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_f3c"

echo "=== batch_f3c START $(date -Iseconds) ===" >> "$LOG"

# ha_body × 10 品种 (排除 CJ/FG/FU/LH/SP 已有, SS/SR/MA/RB/EG 在 F3b)
for sym in bu cf i jm jd ao ta ur sh p; do
  batch_run_one "$sym" "ha_body" "F3c-hb-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f3c DONE $(date -Iseconds) ===" | tee -a "$LOG"
