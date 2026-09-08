#!/bin/bash
# 批次 B — sar_dist 组合扫描 (rsi_state 体系)
# B1: SS rsi_state+sar_dist
# B2: SR rsi_state+sar_dist
# B3: JD rsi_state+sar_dist
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

JSONL="reports/data_ops/batch_b_progress.jsonl"
LOG="reports/data_ops/batch_b.log"
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

echo "=== batch_b START $(date -Iseconds) ===" >> "$LOG"
run_one ss "rsi_state,sar_dist"             "B1"
run_one sr "rsi_state,sar_dist"             "B2"
run_one jd "rsi_state,sar_dist"             "B3"
echo "=== batch_b DONE $(date -Iseconds) ===" | tee -a "$LOG"
