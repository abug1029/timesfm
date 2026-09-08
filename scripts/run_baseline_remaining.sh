#!/bin/bash
# 运行剩余 15 个品种的回测, 获取当前 PF
# 用于核实 STATE.md 中所有品种的 baseline PF

set -e
cd "$(dirname "$0")/.."

source .praxist-venv/bin/activate
export PYTHONIOENCODING=utf-8

REMAINING="ss sr sp fu m i rb bu sh p eg lh cj jd ta"
MAX_POINTS=396
LOG="reports/data_ops/baseline_remaining_15.log"

echo "========================================" > "$LOG"
echo "  剩余 15 品种 Baseline PF 核实" >> "$LOG"
echo "  开始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"
echo "" >> "$LOG"

for sym in $REMAINING; do
    echo "[$sym] 开始回测 (max-points=$MAX_POINTS)..." | tee -a "$LOG"

    output=$(python -u scripts/monthly_backtest.py "$sym" --max-points "$MAX_POINTS" 2>&1)

    # 提取 PF 行: "396pts DirAcc=50%(ref) MAPE=1.98% decay=1.47x EV_ratio=-0.190 PF=0.68 MaxDD=-26.68% WR=48%"
    pf_line=$(echo "$output" | grep -E "[0-9]+pts.*PF=" | tail -1)

    if [ -n "$pf_line" ]; then
        echo "[$sym] $pf_line" | tee -a "$LOG"
    else
        echo "[$sym] FAIL - 无法解析 PF" | tee -a "$LOG"
    fi
    echo "" >> "$LOG"
done

echo "========================================" >> "$LOG"
echo "  完成: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"
echo "日志: $LOG"
