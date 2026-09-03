#!/bin/bash
# 批次 A — 协变量空白补测
# A1: SS reversal_shadow (固化验证)
# A2: SR sar_dist (孤立对照首测)
# A3: UR ao_accel+oi (组合增强)
# A4: UR ao_accel+reversal_shadow (组合增强)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

JSONL="reports/data_ops/batch_a_progress.jsonl"
LOG="reports/data_ops/batch_a.log"
: > "$LOG"

run_one() {
  local sym="$1" combo="$2" label="$3"
  if [ -f "$JSONL" ] && grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label already done" | tee -a "$LOG"
    return 0
  fi
  echo "[START] $label: $sym --combo '$combo'" | tee -a "$LOG"
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    metric=$(grep -oE '[0-9]+pts DirAcc=.*WR=[0-9]+' "$LOG" | tail -1 || echo "unknown")
    echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"$combo\", \"metric\": \"$metric\"}" >> "$JSONL"
    echo "[DONE] $label: $metric" | tee -a "$LOG"
  else
    local rc=$?
    echo "[FAIL] $label exit=$rc" | tee -a "$LOG"
  fi
  sleep 8
}

echo "=== batch_a START $(date -Iseconds) ===" >> "$LOG"
run_one ss "reversal_shadow"               "A1"
run_one sr "sar_dist"                       "A2"
run_one ur "ao_accel,oi"                    "A3"
run_one ur "ao_accel,reversal_shadow"       "A4"
echo "=== batch_a DONE $(date -Iseconds) ===" | tee -a "$LOG"
