#!/bin/bash
# 批次 F1 — 单协变量穷举: calendar_cyclical × 18 + rsi_state × 20 = 38 tests
# 使用 _batch_lib.sh 进行进程管理 (原子锁 + 双模式清场 + heartbeat)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

# ---- 路径设置 ----
FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f1_progress.jsonl"
LOG="reports/data_ops/batch_f1.log"

# ---- 进程管理库 ----
source scripts/_batch_lib.sh

# ---- 初始化 (原子锁 + 清场 + heartbeat) ----
: > "$LOG"
batch_init "batch_f1"

echo "=== batch_f1 START $(date -Iseconds) ===" >> "$LOG"

# calendar_cyclical × 18 品种 (AO/SR 已有单独测试)
for sym in ss cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p; do
  batch_run_one "$sym" "calendar_cyclical" "F1-cal-$sym" "$JSONL" "$LOG"
done

# rsi_state × 20 品种 (全量, 从未单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  batch_run_one "$sym" "rsi_state" "F1-rsi-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f1 DONE $(date -Iseconds) ===" | tee -a "$LOG"
