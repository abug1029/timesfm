#!/bin/bash
# 批次 F3 — 单协变量穷举: hourly_slope × 19 + ha_body × 15 = 34 tests
# 使用 _batch_lib.sh 进行进程管理 (原子锁 + 双模式清场 + heartbeat)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

# ---- 路径设置 ----
FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f3_progress.jsonl"
LOG="reports/data_ops/batch_f3.log"

# ---- 进程管理库 ----
source scripts/_batch_lib.sh

# ---- 初始化 (原子锁 + 清场 + heartbeat) ----
: > "$LOG"
batch_init "batch_f3"

echo "=== batch_f3 START $(date -Iseconds) ===" >> "$LOG"

# hourly_slope × 19 品种 (AO 已有单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p; do
  batch_run_one "$sym" "hourly_slope" "F3-hs-$sym" "$JSONL" "$LOG"
done

# ha_body × 15 品种 (CJ/FG/FU/LH/SP 已有单独测试)
for sym in ss sr ma rb eg bu cf i jm jd ao ta ur sh p; do
  batch_run_one "$sym" "ha_body" "F3-hb-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f3 DONE $(date -Iseconds) ===" | tee -a "$LOG"
