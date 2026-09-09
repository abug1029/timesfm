#!/bin/bash
# 批次 F4 — 单协变量穷举: ao_accel × 20 = 20 tests
# ao_accel 是 UR 的固化协变量, 从未在其余 19 品种单独测试
# 使用 _batch_lib.sh 进行进程管理 (原子锁 + 双模式清场 + heartbeat)
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source .praxist-venv/bin/activate

# ---- 路径设置 ----
FM_ROOT="D:/FlyBuddy/FM_a"
JSONL="reports/data_ops/batch_f4_progress.jsonl"
LOG="reports/data_ops/batch_f4.log"

# ---- 进程管理库 ----
source scripts/_batch_lib.sh

# ---- 初始化 (原子锁 + 清场 + heartbeat) ----
: > "$LOG"
batch_init "batch_f4"

echo "=== batch_f4 START $(date -Iseconds) ===" >> "$LOG"

# ao_accel × 20 品种 (全量, 从未单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  batch_run_one "$sym" "ao_accel" "F4-ao-$sym" "$JSONL" "$LOG"
done

echo "=== batch_f4 DONE $(date -Iseconds) ===" | tee -a "$LOG"
