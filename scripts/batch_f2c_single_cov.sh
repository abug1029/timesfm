#!/bin/bash
# 批次 F2c — 单协变量穷举: reversal_shadow × 16 = 16 tests
# F2 子批次 3/3 (reversal_shadow 剩余 16 品种, 排除 SS/SR/CJ/FG)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f2c_progress.jsonl"
LOG="reports/data_ops/batch_f2c.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_f2c"

echo "=== batch_f2c START $(date -Iseconds) ===" >> "$LOG"

# reversal_shadow × 16 品种 (排除 SS 已有, SR/CJ/FG 在 F2b)
for sym in fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  batch_run_one "$sym" "reversal_shadow" "F2c-rev-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f2c DONE $(date -Iseconds) ===" | tee -a "$LOG"
