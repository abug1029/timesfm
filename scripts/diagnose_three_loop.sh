#!/bin/bash
# diagnose_three_loop.sh — 无人值守三环诊断 + 安全自愈 (2026-09-21)
#
# 授权边界（无人值守模式，用户 2026-09-21 批准"自主修复无需批准"）：
#   AUTO（安全自愈，自动执行）:
#     S1  supervisor 进程不存在        -> 经 canonical launcher 重启
#     S2  supervisor 心跳过期(>12min)  -> 同上重启
#     S3  近期日志出现 exit 126/Exec format -> 同上重启（根因 PATH 已由 launcher 修）
#     S4  无新 run 活动 >20min(调度卡)  -> 同上重启
#   NEEDS_HUMAN（不自动，仅报）:
#     H1  claude 仍解析到 /mnt/c (launcher 未生效)
#     H2  verdict 文件损坏 / 队列异常
#     H3  任何需要动 protected 文件/数据/git 的场景
#
# 用法：bash scripts/diagnose_three_loop.sh  (输出单行状态)
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

# 前置 PATH（与 launcher 一致，保证 claude/pgrep 解析正确）
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

NOW=$(date +%s)
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---------- 收集 ----------
SUP_PIDS=$(pgrep -f "scripts/praxist_supervisor.py" | tr '\n' ' ')
HB_FILE=data/cache/supervisor_heartbeat
[ -f "$HB_FILE" ] && HB_MTIME=$(stat -c %Y "$HB_FILE") || HB_MTIME=0
HB_AGE=$(( (NOW - HB_MTIME) / 60 ))
SUPCMD=$(command -v claude 2>/dev/null || echo none)
NEWEST_RUN=$(ls -1dt task_FM/experiments/run_* 2>/dev/null | head -1)
RUN_NEW=$( [ -n "$NEWEST_RUN" ] && stat -c %Y "$NEWEST_RUN" || echo 0 )
RUN_MINS=$(( (NOW - RUN_NEW) / 60 ))
# 近期 126 检测（supervisor.out + 最新 run 的 launcher log）
RECENT_126=$( { tail -100 data/cache/supervisor.out 2>/dev/null; [ -n "$NEWEST_RUN" ] && grep -iE "Exec format|exit 126" "$NEWEST_RUN"/logs/*.log 2>/dev/null; } | grep -icE "Exec format|exit 126" )

SUPERVISOR_UP=0
[ -n "$(echo "$SUP_PIDS" | tr -d ' ')" ] && SUPERVISOR_UP=1

# ---------- 判定状态 ----------
STATE="HEALTHY"; ACTION=""
if ! command -v claude >/dev/null 2>&1; then
  STATE="NEEDS_HUMAN"; ACTION="H1 claude not on PATH"
elif [[ "$SUPCMD" == /mnt/c/* ]]; then
  STATE="NEEDS_HUMAN"; ACTION="H1 claude -> $SUPCMD (Windows shim)"
elif [ "$SUPERVISOR_UP" -eq 0 ]; then
  STATE="AUTO_HEAL"; ACTION="S1 supervisor down"
elif [ "$HB_AGE" -gt 12 ]; then
  STATE="AUTO_HEAL"; ACTION="S2 heartbeat stale ${HB_AGE}min"
elif [ "$RECENT_126" -gt 0 ]; then
  STATE="AUTO_HEAL"; ACTION="S3 recent exit-126 (n=$RECENT_126)"
elif [ -n "$NEWEST_RUN" ] && [ "$RUN_MINS" -gt 20 ]; then
  # S4: only trigger when fast-loop idle AND slow-loop also idle
  # slow-loop running = supervisor is in slow phase normally, do not kill
  SLOW_ALIVE=0
  if pgrep -f "aligned_slow_loop.py" >/dev/null 2>&1; then
    SLOW_ALIVE=1
  fi
  if [ "$SLOW_ALIVE" -eq 0 ]; then
    STATE="AUTO_HEAL"; ACTION="S4 no new run activity ${RUN_MINS}min"
  fi
fi

# ---------- 自愈 ----------
if [ "$STATE" = "AUTO_HEAL" ]; then
  # 先尝试停掉残留 supervisor（SIGTERM 优雅），再 canonical 重启
  if [ "$SUPERVISOR_UP" -eq 1 ]; then
    kill -TERM $SUP_PIDS 2>/dev/null
    sleep 3
  fi
  if O=$(bash scripts/start_supervisor.sh 2>&1); then
    STATE="HEALED"
  else
    STATE="NEEDS_HUMAN"; ACTION="heal restart FAILED: $O"
  fi
fi

case "$STATE" in
  HEALTHY)  echo "HEALTHY pids=[${SUP_PIDS% }] hb=${HB_AGE}min run=${RUN_MINS}min claude=$SUPCMD" ;;
  HEALED)   echo "HEALED [$ACTION] pids=[${SUP_PIDS% }] claude=$SUPCMD" ;;
  *)        echo "NEEDS_HUMAN [$ACTION] pids=[${SUP_PIDS% }] hb=${HB_AGE}min run=${RUN_MINS}min claude=$SUPCMD" ;;
esac