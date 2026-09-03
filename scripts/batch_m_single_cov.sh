#!/bin/bash
# M (豆粕) Phase 11 单协变量补跑 — 7 tests
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_m_progress.jsonl"
LOG="reports/data_ops/batch_m.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_m"

echo "=== batch_m START $(date -Iseconds) ===" >> "$LOG"

for combo in calendar_cyclical rsi_state oi reversal_shadow hourly_slope ha_body ao_accel; do
    batch_run_one "m" "$combo" "M-${combo:0:3}" "$JSONL" "$LOG"
done

echo "=== batch_m DONE $(date -Iseconds) ===" | tee -a "$LOG"
