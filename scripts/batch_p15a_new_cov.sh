#!/bin/bash
# Phase 15a: 新协变量单协变量回测
# 6 弱信号品种 × 4 新协变量 = 24 tests
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_p15a_progress.jsonl"
LOG="reports/data_ops/batch_p15a.log"

source scripts/_batch_lib.sh

: > "$LOG"
batch_init "batch_p15a"

echo "=== batch_p15a START $(date -Iseconds) ===" >> "$LOG"

# 弱信号品种: JM/MA/UR/FG/CF/AO
# 新协变量: nvi, qstick, vwap_deviation, stddev

for SYM in jm ma ur fg cf ao; do
    # NVI
    batch_run_one "$SYM" "nvi" "P15a-${SYM}-nvi" "$JSONL" "$LOG"

    # QSTICK
    batch_run_one "$SYM" "qstick" "P15a-${SYM}-qstick" "$JSONL" "$LOG"

    # VWAP deviation
    batch_run_one "$SYM" "vwap_deviation" "P15a-${SYM}-vwap" "$JSONL" "$LOG"

    # StdDev
    batch_run_one "$SYM" "stddev" "P15a-${SYM}-stddev" "$JSONL" "$LOG"
done

echo "=== batch_p15a DONE $(date -Iseconds) ===" | tee -a "$LOG"
