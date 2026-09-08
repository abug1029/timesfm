#!/bin/bash
# 弱信号品种组合协变量测试 — 7 品种 × 2 组合 = 14 tests
# 基于 Phase 11 单协变量 top-2 组合
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_weak_combo_progress.jsonl"
LOG="reports/data_ops/batch_weak_combo.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_weak_combo"

echo "=== batch_weak_combo START $(date -Iseconds) ===" >> "$LOG"

# BU: cal(0.99) + hs(0.91), cal(0.99) + rev(0.87)
batch_run_one "bu" "calendar_cyclical,hourly_slope" "BU-cal+hs" "$JSONL" "$LOG"
batch_run_one "bu" "calendar_cyclical,reversal_shadow" "BU-cal+rev" "$JSONL" "$LOG"

# JM: hs(0.90) + ha(0.87), hs(0.90) + rsi(0.85)
batch_run_one "jm" "hourly_slope,ha_body" "JM-hs+ha" "$JSONL" "$LOG"
batch_run_one "jm" "hourly_slope,rsi_state" "JM-hs+rsi" "$JSONL" "$LOG"

# MA: rsi(1.00) + oi(0.86), rsi(1.00) + cal(0.84)
batch_run_one "ma" "rsi_state,oi" "MA-rsi+oi" "$JSONL" "$LOG"
batch_run_one "ma" "rsi_state,calendar_cyclical" "MA-rsi+cal" "$JSONL" "$LOG"

# UR: rsi(0.96) + hs(0.90), rsi(0.96) + cal(0.88)
batch_run_one "ur" "rsi_state,hourly_slope" "UR-rsi+hs" "$JSONL" "$LOG"
batch_run_one "ur" "rsi_state,calendar_cyclical" "UR-rsi+cal" "$JSONL" "$LOG"

# FG: oi(0.93) + hs(0.88), oi(0.93) + cal(0.87)
batch_run_one "fg" "oi,hourly_slope" "FG-oi+hs" "$JSONL" "$LOG"
batch_run_one "fg" "oi,calendar_cyclical" "FG-oi+cal" "$JSONL" "$LOG"

# CF: rev(0.90) + ha(0.84), rev(0.90) + cal(0.84)
batch_run_one "cf" "reversal_shadow,ha_body" "CF-rev+ha" "$JSONL" "$LOG"
batch_run_one "cf" "reversal_shadow,calendar_cyclical" "CF-rev+cal" "$JSONL" "$LOG"

# AO: rev(0.73) + ha(0.73), rev(0.73) + oi(0.71)
batch_run_one "ao" "reversal_shadow,ha_body" "AO-rev+ha" "$JSONL" "$LOG"
batch_run_one "ao" "reversal_shadow,oi" "AO-rev+oi" "$JSONL" "$LOG"

echo "=== batch_weak_combo DONE $(date -Iseconds) ===" | tee -a "$LOG"
