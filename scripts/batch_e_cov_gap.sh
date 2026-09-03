#!/bin/bash
# 批次 E — 补充探索
# E1: SS reversal_shadow+calendar_cyclical (影线+季节性)
# E2: UR hourly_slope+reversal_shadow (跨体系迁移验证)
# E3: TA ha_body+ao_accel (PF=0.99 边界改善)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

JSONL="reports/data_ops/batch_e_progress.jsonl"
LOG="reports/data_ops/batch_e.log"
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

echo "=== batch_e START $(date -Iseconds) ===" >> "$LOG"
run_one ss "reversal_shadow,calendar_cyclical"  "E1"
run_one ur "hourly_slope,reversal_shadow"       "E2"
run_one ta "ha_body,ao_accel"                   "E3"
echo "=== batch_e DONE $(date -Iseconds) ===" | tee -a "$LOG"
