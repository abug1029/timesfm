#!/bin/bash
# 批次 F2 — 单协变量穷举: oi × 20 + reversal_shadow × 19 = 39 tests
# 使用 _batch_lib.sh 进行进程管理 (原子锁 + 双模式清场 + heartbeat)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

# ---- 路径设置 ----
FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f2_progress.jsonl"
LOG="reports/data_ops/batch_f2.log"

# ---- 进程管理库 ----
source scripts/_batch_lib.sh

# ---- 初始化 (原子锁 + 清场 + heartbeat) ----
: > "$LOG"
batch_init "batch_f2"

echo "=== batch_f2 START $(date -Iseconds) ===" >> "$LOG"

# oi × 20 品种 (全量, 从未单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  batch_run_one "$sym" "oi" "F2-oi-$sym" "$JSONL" "$LOG"
done

# reversal_shadow × 19 品种 (SS 已有单独测试)
for sym in sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  batch_run_one "$sym" "reversal_shadow" "F2-rev-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f2 DONE $(date -Iseconds) ===" | tee -a "$LOG"
