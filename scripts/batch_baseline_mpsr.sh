#!/bin/bash
# M/P/SR 基线对比回测 — 3 tests
# M: 当前 ha_body+calendar_cyclical vs Phase 11 calendar(1.06) [消融 ha_body]
# P: 当前 rsi_state+reversal_shadow vs Phase 11 calendar(1.02)
# SR: 当前 rsi_state+oi+calendar_cyclical vs Phase 11 reversal_shadow(1.03)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_baseline_mpsr_progress.jsonl"
LOG="reports/data_ops/batch_baseline_mpsr.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_baseline_mpsr"

echo "=== batch_baseline_mpsr START $(date -Iseconds) ===" >> "$LOG"

run_baseline() {
    local sym="$1" label="$2"
    if [ -f "$JSONL" ] && grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
        echo "[SKIP] $label already done" | tee -a "$LOG"
        return 0
    fi
    echo "[START] $label: $sym (baseline)" | tee -a "$LOG"
    if python scripts/monthly_backtest.py "$sym" >> "$LOG" 2>&1; then
        local pf ev maxdd diracc
        pf=$(grep -aoE 'PF=[0-9.]+' "$LOG" | tail -1 || echo "PF=unknown")
        ev=$(grep -aoE 'EV_ratio=[+-]?[0-9.]+' "$LOG" | tail -1 || echo "EV_ratio=unknown")
        maxdd=$(grep -aoE 'MaxDD=[+-]?[0-9.]+%' "$LOG" | tail -1 || echo "MaxDD=unknown")
        diracc=$(grep -aoE '[0-9]+pts DirAcc=[0-9.]+' "$LOG" | tail -1 || echo "unknown")
        local metric="${diracc} ${pf} ${ev} ${maxdd}"
        echo "[DONE] $label: $metric" | tee -a "$LOG"
        echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"baseline\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$JSONL"
    else
        echo "[FAIL] $label exit=$?" | tee -a "$LOG"
    fi
    sleep 8
}

run_baseline "m" "BL-m"
run_baseline "p" "BL-p"
run_baseline "sr" "BL-sr"

echo "=== batch_baseline_mpsr DONE $(date -Iseconds) ===" | tee -a "$LOG"
