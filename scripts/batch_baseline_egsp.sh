#!/bin/bash
# 基线对比回测 — EG/SP 当前方案 baseline PF/EV/MaxDD
# EG: ha_body+oi+reversal_shadow vs Phase 11 calendar(1.04)
# SP: ha_body+calendar_cyclical vs Phase 11 calendar(1.07) [消融]
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_baseline_egsp_progress.jsonl"
LOG="reports/data_ops/batch_baseline_egsp.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_baseline_egsp"

echo "=== batch_baseline_egsp START $(date -Iseconds) ===" >> "$LOG"

# 基线回测函数: 运行当前 scheme (不加 --combo)
run_baseline() {
    local sym="$1" label="$2"

    # 断点续跑
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
        if echo "$metric" | grep -q "unknown"; then
            echo "[DONE?] $label: $metric (NEEDS_REVIEW)" | tee -a "$LOG"
        else
            echo "[DONE] $label: $metric" | tee -a "$LOG"
        fi

        echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"baseline\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$JSONL"
    else
        local rc=$?
        echo "[FAIL] $label exit=$rc" | tee -a "$LOG"
    fi
    sleep 8
}

# EG: 当前 ha_body+oi+reversal_shadow baseline vs Phase 11 calendar(1.04)
run_baseline "eg" "BL-eg"

# SP: 当前 ha_body+calendar_cyclical baseline vs Phase 11 calendar单协(1.07)
run_baseline "sp" "BL-sp"

echo "=== batch_baseline_egsp DONE $(date -Iseconds) ===" | tee -a "$LOG"
