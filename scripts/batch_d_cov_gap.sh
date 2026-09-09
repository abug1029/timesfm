#!/bin/bash
# 批次 D — 测试不足品种补测
# D1: SP ha_body (消融: calendar 是否有贡献)
# D2: SP rsi_state+oi (正交方案替代)
# D3: MA sar_dist+hourly_slope (新组合)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

JSONL="reports/data_ops/batch_d_progress.jsonl"
LOG="reports/data_ops/batch_d.log"
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

echo "=== batch_d START $(date -Iseconds) ===" >> "$LOG"
run_one sp "ha_body"                        "D1"
run_one sp "rsi_state,oi"                   "D2"
run_one ma "sar_dist,hourly_slope"          "D3"
echo "=== batch_d DONE $(date -Iseconds) ===" | tee -a "$LOG"
