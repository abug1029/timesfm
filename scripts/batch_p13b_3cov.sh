#!/bin/bash
# Phase 13b: 3-cov 组合 — top-1 + top-2 + calendar_cyclical
# 6 tests: JM/MA/UR/FG/CF/AO
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_p13b_progress.jsonl"
LOG="reports/data_ops/batch_p13b.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_p13b"

echo "=== batch_p13b START $(date -Iseconds) ===" >> "$LOG"

# JM: hs + rsi + calendar (top-3 combined)
batch_run_one "jm" "hourly_slope,rsi_state,calendar_cyclical" "P13b-JM-hs+rsi+cal" "$JSONL" "$LOG"

# MA: rsi + oi + calendar
batch_run_one "ma" "rsi_state,oi,calendar_cyclical" "P13b-MA-rsi+oi+cal" "$JSONL" "$LOG"

# UR: rsi + hs + calendar
batch_run_one "ur" "rsi_state,hourly_slope,calendar_cyclical" "P13b-UR-rsi+hs+cal" "$JSONL" "$LOG"

# FG: oi + hs + calendar
batch_run_one "fg" "oi,hourly_slope,calendar_cyclical" "P13b-FG-oi+hs+cal" "$JSONL" "$LOG"

# CF: rev + ha + calendar
batch_run_one "cf" "reversal_shadow,ha_body,calendar_cyclical" "P13b-CF-rev+ha+cal" "$JSONL" "$LOG"

# AO: rev + oi + calendar
batch_run_one "ao" "reversal_shadow,oi,calendar_cyclical" "P13b-AO-rev+oi+cal" "$JSONL" "$LOG"

echo "=== batch_p13b DONE $(date -Iseconds) ===" | tee -a "$LOG"
