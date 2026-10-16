#!/bin/bash
# 障碍 4：pp/bz/eb 基线重生
# 覆盖度从 88.9% -> 100%
# 2026-10-16

set -euo pipefail
cd "$(dirname "$0")/.."

source .venv/bin/activate
export PYTHONIOENCODING=utf-8

MISSING="pp bz eb"
ROOT="$(pwd)"
LOG="logs/baseline_regen_pp_bz_eb_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee "$LOG"
echo "  pp/bz/eb 基线重生" | tee -a "$LOG"
echo "  开始: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"

for sym in $MISSING; do
    echo "" | tee -a "$LOG"
    echo "[$sym] 开始基线生成..." | tee -a "$LOG"

    bl_file="task_FM/config/baseline_points_${sym}_nocov.jsonl"
    if [ -f "$bl_file" ]; then
        line_count=$(wc -l < "$bl_file")
        if [ "$line_count" -gt 0 ]; then
            echo "[$sym] 已有基线 (${line_count} 行)，跳过" | tee -a "$LOG"
            continue
        fi
    fi

    python -u scripts/generate_baseline_points.py \
        --symbol "$sym" \
        --cov none \
        --root "$ROOT" \
        2>&1 | tee -a "$LOG"

    echo "[$sym] 完成" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"
echo "  完成: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- 覆盖度验证 ---" | tee -a "$LOG"
python3 scripts/check_baseline_coverage.py 2>&1 | tee -a "$LOG"

echo "日志: $LOG"
