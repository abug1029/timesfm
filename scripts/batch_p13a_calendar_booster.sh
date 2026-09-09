#!/bin/bash
# Phase 13a: Calendar 通用增强 — 弱信号品种 top-1 + calendar
# 6 tests: JM/MA/UR/FG/CF/AO
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_p13a_progress.jsonl"
LOG="reports/data_ops/batch_p13a.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_p13a"

echo "=== batch_p13a START $(date -Iseconds) ===" >> "$LOG"

# JM: best=hourly_slope(0.90) + calendar
batch_run_one "jm" "hourly_slope,calendar_cyclical" "P13a-JM-hs+cal" "$JSONL" "$LOG"

# MA: best=rsi_state(1.00) + calendar
batch_run_one "ma" "rsi_state,calendar_cyclical" "P13a-MA-rsi+cal" "$JSONL" "$LOG"

# UR: best=rsi_state(0.96) + calendar
batch_run_one "ur" "rsi_state,calendar_cyclical" "P13a-UR-rsi+cal" "$JSONL" "$LOG"

# FG: best=oi(0.93) + calendar
batch_run_one "fg" "oi,calendar_cyclical" "P13a-FG-oi+cal" "$JSONL" "$LOG"

# CF: best=reversal_shadow(0.90) + calendar
batch_run_one "cf" "reversal_shadow,calendar_cyclical" "P13a-CF-rev+cal" "$JSONL" "$LOG"

# AO: best=reversal_shadow(0.73) + calendar
batch_run_one "ao" "reversal_shadow,calendar_cyclical" "P13a-AO-rev+cal" "$JSONL" "$LOG"

echo "=== batch_p13a DONE $(date -Iseconds) ===" | tee -a "$LOG"
