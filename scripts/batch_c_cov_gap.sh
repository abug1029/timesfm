#!/bin/bash
# 批次 C — ha_body + sar_dist 正交增强 (干净归因)
# C1: RB ha_body+sar_dist
# C2: FU ha_body+sar_dist
# C3: FG ha_body+sar_dist
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

JSONL="reports/data_ops/batch_c_progress.jsonl"
LOG="reports/data_ops/batch_c.log"
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

echo "=== batch_c START $(date -Iseconds) ===" >> "$LOG"
run_one rb "ha_body,sar_dist"               "C1"
run_one fu "ha_body,sar_dist"               "C2"
run_one fg "ha_body,sar_dist"               "C3"
echo "=== batch_c DONE $(date -Iseconds) ===" | tee -a "$LOG"
