#!/bin/bash
# Phase 13c: 非 top 探索 — 用未参与 Phase 11 top-3 的协变量配对
# 6 tests: JM/MA/UR/FG/CF/AO
# 策略: 尝试 calendar_cyclical + ha_body (M 的成功模式) 和其他非 top 组合
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_p13c_progress.jsonl"
LOG="reports/data_ops/batch_p13c.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_p13c"

echo "=== batch_p13c START $(date -Iseconds) ===" >> "$LOG"

# JM: ha_body + calendar (M 的成功模式)
batch_run_one "jm" "ha_body,calendar_cyclical" "P13c-JM-ha+cal" "$JSONL" "$LOG"

# MA: oi + calendar (oi 在 CF/FG 有贡献)
batch_run_one "ma" "oi,calendar_cyclical" "P13c-MA-oi+cal" "$JSONL" "$LOG"

# UR: ao_accel + calendar (当前方案 + calendar)
batch_run_one "ur" "ao_accel,calendar_cyclical" "P13c-UR-ao+cal" "$JSONL" "$LOG"

# FG: rev + calendar (reversal_shadow 未与 calendar 配对)
batch_run_one "fg" "reversal_shadow,calendar_cyclical" "P13c-FG-rev+cal" "$JSONL" "$LOG"

# CF: ha_body + calendar (当前方案就是 ha_body+cal 的变体)
batch_run_one "cf" "ha_body,calendar_cyclical" "P13c-CF-ha+cal" "$JSONL" "$LOG"

# AO: ha_body + calendar (ha_body 在 Phase 11 单测中未被 AO 测试)
batch_run_one "ao" "ha_body,calendar_cyclical" "P13c-AO-ha+cal" "$JSONL" "$LOG"

echo "=== batch_p13c DONE $(date -Iseconds) ===" | tee -a "$LOG"
