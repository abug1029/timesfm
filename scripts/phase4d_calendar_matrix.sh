#!/usr/bin/env bash
# Phase 4d: calendar_cyclical 季节性固化回测 (per-symbol-per-mode 增量断点)
# 6 品种 × 模式 (JD 2, UR/SR/CF/SP/M 各 3) = 17 symbol-mode
# JD 无 additive (gated_slope 不在 combo 路径)
# 增量断点: JSONL 记成功结果, kill/重启后 skip 已完成项, 无损续跑
set -u

cd "D:/FlyBuddy/fm_a" || { echo "cd failed"; exit 1; }
# shellcheck disable=SC1091
source "D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate" || { echo "venv failed"; exit 1; }

JSONL="reports/monthly_backtest/phase4d_incremental_results.jsonl"
LOG="reports/monthly_backtest/phase4d_calendar_matrix.log"

# 全新启动截断 LOG; 续跑追加 (保旧结果)
if [ ! -s "$JSONL" ]; then
  echo "=== Phase 4d fresh start $(date '+%Y-%m-%d %H:%M:%S') ===" > "$LOG"
else
  echo "=== Phase 4d resume $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
fi

run_one() {
  local sym="$1" mode="$2" orig="$3"
  # 断点续跑: 已完成则跳过
  if grep -q "\"symbol\": \"$sym\".*\"mode\": \"$mode\"" "$JSONL" 2>/dev/null; then
    echo "Skipping $sym $mode (done)"
    return 0
  fi
  # 构造命令参数
  local args
  case "$mode" in
    baseline) args="$sym" ;;
    replace)  args="--cov-override calendar_cyclical $sym" ;;
    additive) args="--combo ${orig},calendar_cyclical $sym" ;;
    *) return 0 ;;
  esac
  echo "" >> "$LOG"
  echo "### $mode $sym" >> "$LOG"
  echo "CMD: python scripts/monthly_backtest.py $args" >> "$LOG"
  echo "  >>> [$sym $mode] start..."
  # 运行 + tee 到 LOG + 捕获指标行 (成功才记 JSONL)
  local metric
  metric=$(python scripts/monthly_backtest.py $args 2>&1 | tee -a "$LOG" | grep -oE "[0-9]+pts DirAcc=.*WR=[0-9]+%" | head -1)
  if [ -n "$metric" ]; then
    echo "{\"symbol\": \"$sym\", \"mode\": \"$mode\", \"metric\": \"$metric\"}" >> "$JSONL"
    echo "  >>> [$sym $mode] OK: $metric"
  else
    echo "  >>> [$sym $mode] FAIL (no metric)"
  fi
  sleep 8  # OOM/显存碎片缓冲
}

# 品种列表: sym|additive_orig (orig 仅 additive 用; JD 无 additive)
SYMBOLS=(
  "jd|"
  "ur|ao_accel"
  "sr|rsi_state,oi"
  "cf|ha_body"
  "sp|ha_body"
  "m|vor"
)

for entry in "${SYMBOLS[@]}"; do
  sym="${entry%%|*}"
  orig="${entry#*|}"
  run_one "$sym" "baseline" "$orig"
  run_one "$sym" "replace"  "$orig"
  # JD 无 additive (gated_slope 不在 combo 路径)
  [ "$sym" != "jd" ] && run_one "$sym" "additive" "$orig"
done

echo "" >> "$LOG"
echo "=== ALL DONE $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
echo "ALL DONE - results in $JSONL"
