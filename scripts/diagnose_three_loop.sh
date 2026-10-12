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

# ---------- 批次 A 新增：维护窗口与熔断 ----------
MAINT_FLAG=data/cache/maintenance.flag
HEAL_FAIL_COUNT=data/cache/heal_fail.count
D5_DISABLED_FLAG=data/cache/d5_disabled.flag
CIRCUIT_BREAKER_THRESHOLD=3
# 覆盖一次常规部署；更长维护须续期 touch（closure spec §4.1.3: T_expire = 4h）
MAINT_FLAG_EXPIRE_HOURS=4

# 检查维护窗口旗标（存在且未过期则暂停自愈）
MAINT_WINDOW_ACTIVE=0
if [ -f "$MAINT_FLAG" ]; then
  MAINT_MTIME=$(stat -c %Y "$MAINT_FLAG")
  MAINT_AGE_HOURS=$(( (NOW - MAINT_MTIME) / 3600 ))
  if [ "$MAINT_AGE_HOURS" -lt "$MAINT_FLAG_EXPIRE_HOURS" ]; then
    MAINT_WINDOW_ACTIVE=1
    log "维护窗口激活（${MAINT_AGE_HOURS}h/${MAINT_FLAG_EXPIRE_HOURS}h）"
  else
    log "维护窗口已过期（${MAINT_AGE_HOURS}h），自动失效"
    rm -f "$MAINT_FLAG"
  fi
fi

# 检查熔断状态
CIRCUIT_BROKEN=0
if [ -f "$HEAL_FAIL_COUNT" ]; then
  FAIL_COUNT=$(cat "$HEAL_FAIL_COUNT")
  if [ "$FAIL_COUNT" -ge "$CIRCUIT_BREAKER_THRESHOLD" ]; then
    CIRCUIT_BROKEN=1
    log "熔断已触发（失败${FAIL_COUNT}次≥${CIRCUIT_BREAKER_THRESHOLD}），自愈停用"
  fi
fi

# 检查 D5 禁用旗标
D5_DISABLED=0
if [ -f "$D5_DISABLED_FLAG" ]; then
  D5_DISABLED=1
  log "D5 扫尾已禁用"
fi

# ---------- 批次 A2：孤儿 run 扫尾 ----------
# 仅当 D5 未禁用且 supervisor 不在运行时执行
ACTIVE_RUNS_FILE=data/cache/active_runs.json
SLOW_LOOP_LOCK=data/cache/aligned_slow_loop.lock
EXPERIMENTS_DIR="$(pwd)/task_FM/experiments"

cleanup_orphan_runs() {
  # D5 禁用时跳过
  if [ "$D5_DISABLED" -eq 1 ]; then
    return
  fi

  # supervisor 还在运行时不扫尾（它自己管理）
  if [ "$SUPERVISOR_UP" -eq 1 ]; then
    return
  fi

  # 检查 active_runs.json 是否存在
  if [ ! -f "$ACTIVE_RUNS_FILE" ]; then
    return
  fi

  # 读取 active_runs.json
  local batch_id pid cmdline start_ts
  batch_id=$(jq -r '.batch_id // empty' "$ACTIVE_RUNS_FILE" 2>/dev/null)
  pid=$(jq -r '.pid // empty' "$ACTIVE_RUNS_FILE" 2>/dev/null)
  cmdline=$(jq -r '.cmdline // empty' "$ACTIVE_RUNS_FILE" 2>/dev/null)

  if [ -z "$batch_id" ]; then
    return
  fi

  # 检查 flock（aligned_slow_loop.lock）
  # 如果锁存在，说明进程还在跑（可能是孤儿）
  if [ -f "$SLOW_LOOP_LOCK" ]; then
    # 尝试获取锁（非阻塞）
    if (set -C; 2>/dev/null > "$SLOW_LOOP_LOCK.test") 2>/dev/null; then
      # 能获取锁，说明没有进程持有
      rm -f "$SLOW_LOOP_LOCK.test"
      log "无孤儿 run（锁可获取），清理 stale active_runs.json"
      rm -f "$ACTIVE_RUNS_FILE"
      return
    fi
    rm -f "$SLOW_LOOP_LOCK.test"

    # 锁被持有，检查 pid 是否还活着
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      # 进程还活着，检查 cmdline 和 worktree
      local proc_cmdline proc_cwd
      proc_cmdline=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')
      proc_cwd=$(readlink /proc/$pid/cwd 2>/dev/null)

      # 校验：cmdline 包含 batch_id 且 cwd 在 experiments 目录下
      if echo "$proc_cmdline" | grep -q "$batch_id" && echo "$proc_cwd" | grep -q "^$EXPERIMENTS_DIR"; then
        log "发现孤儿 run：pid=$pid batch=$batch_id cwd=$proc_cwd"
        log "终止孤儿 run..."
        kill -TERM "$pid" 2>/dev/null
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
          log "孤儿 run 未响应 SIGTERM，发送 SIGKILL"
          kill -KILL "$pid" 2>/dev/null
        fi
        rm -f "$ACTIVE_RUNS_FILE"
        log "孤儿 run 已清理"
      else
        log "active_runs.json 中的 pid=$pid 不匹配（cmdline 或 worktree 不符），跳过"
      fi
    else
      # pid 不存在，清理 active_runs.json
      log "active_runs.json 中的 pid=$pid 已不存在，清理记录"
      rm -f "$ACTIVE_RUNS_FILE"
    fi
  else
    # 锁不存在，清理 active_runs.json
    rm -f "$ACTIVE_RUNS_FILE"
  fi
}

# 执行扫尾（在自愈判定前，但需要 SUPERVISOR_UP 定义后）
# cleanup_orphan_runs 将在后面调用

# 告警函数（日志 + 桌面通知）
alert() {
  local msg="$1"
  log "ALERT: $msg"
  # 桌面通知（WSL 下通过 wsl-notify-send 或 PowerShell）
  if command -v wsl-notify-send >/dev/null 2>&1; then
    wsl-notify-send "三环告警" "$msg" 2>/dev/null || true
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('$msg', '三环告警', 'OK', 'Warning')" 2>/dev/null || true
  fi
}

# 记录自愈失败
record_heal_failure() {
  if [ -f "$HEAL_FAIL_COUNT" ]; then
    FAIL_COUNT=$(cat "$HEAL_FAIL_COUNT")
    echo $((FAIL_COUNT + 1)) > "$HEAL_FAIL_COUNT"
  else
    echo 1 > "$HEAL_FAIL_COUNT"
  fi
  FAIL_COUNT=$(cat "$HEAL_FAIL_COUNT")
  log "自愈失败计数：${FAIL_COUNT}/${CIRCUIT_BREAKER_THRESHOLD}"
  if [ "$FAIL_COUNT" -ge "$CIRCUIT_BREAKER_THRESHOLD" ]; then
    alert "熔断触发：连续${FAIL_COUNT}次自愈失败，停用自愈与D5扫尾"
    touch "$D5_DISABLED_FLAG"
  fi
}

# 记录自愈成功（清零计数）
record_heal_success() {
  if [ -f "$HEAL_FAIL_COUNT" ]; then
    rm -f "$HEAL_FAIL_COUNT"
    log "自愈成功，失败计数清零"
  fi
  # 同时清除 D5 禁用旗标
  if [ -f "$D5_DISABLED_FLAG" ]; then
    rm -f "$D5_DISABLED_FLAG"
    log "D5 禁用旗标已清除"
  fi
}

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

# 执行孤儿 run 扫尾（批次 A2）
cleanup_orphan_runs

# ---------- 判定状态 ----------
# P0-B: 计算 supervisor 最小启动时长（取所有 PID 中最年轻的）
# 用于 S2/S4 宽限期：启动 <30min 内不判 stale，避免基线重生期被误杀
if [ -n "$SUP_PIDS" ]; then
SUP_START_MINS=999
for _spb_pid in $SUP_PIDS; do
  _spb_etime=$(ps -p $_spb_pid -o etimes= 2>/dev/null | tr -d ' ')
  if [ -n "$_spb_etime" ]; then
    _spb_mins=$(( _spb_etime / 60 ))
    [ $_spb_mins -lt $SUP_START_MINS ] && SUP_START_MINS=$_spb_mins
  fi
done
fi  # end of SUP_PIDS empty guard
unset _spb_pid _spb_etime _spb_mins

STATE="HEALTHY"; ACTION=""
if ! command -v claude >/dev/null 2>&1; then
  STATE="NEEDS_HUMAN"; ACTION="H1 claude not on PATH"
elif [[ "$SUPCMD" == /mnt/c/* ]]; then
  STATE="NEEDS_HUMAN"; ACTION="H1 claude -> $SUPCMD (Windows shim)"
elif [ "$SUPERVISOR_UP" -eq 0 ]; then
  STATE="AUTO_HEAL"; ACTION="S1 supervisor down"
elif [ "$SUP_START_MINS" -ge 30 ] && [ "$HB_AGE" -gt 12 ]; then
  STATE="AUTO_HEAL"; ACTION="S2 heartbeat stale ${HB_AGE}min (uptime ${SUP_START_MINS}m)"
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
  # 检查维护窗口
  if [ "$MAINT_WINDOW_ACTIVE" -eq 1 ]; then
    log "维护窗口激活，跳过自愈"
    STATE="MAINTENANCE"
    ACTION="维护窗口中，暂停自愈"
  # 检查熔断
  elif [ "$CIRCUIT_BROKEN" -eq 1 ]; then
    log "熔断已触发，跳过自愈（仅告警）"
    alert "自愈请求被熔断阻止（$ACTION）"
    STATE="CIRCUIT_BROKEN"
    ACTION="熔断中，需人工清除 heal_fail.count"
  else
    # P1-A v2: 先尝试停掉残留 supervisor（SIGTERM 优雅），再 canonical 重启
    # 若 supervisor 启动 <30min，跳过 kill + 跳过 start（宽限期内让基线重生跑完）
    # 修复 reviewer finding: skip-kill 后调 start_supervisor.sh 会撞 Python flock，
    # 新进程秒退，bash 侧不知，日志噪音 "heartbeat not advancing"
    # NEEDS_COLD_START: 0 = cold start (use pgrep), 1 = hot restart (use stat mtime)
    # Inverted from SUPERVISOR_UP: if supervisor was down (0), we need cold start (0)
    NEEDS_COLD_START=$SUPERVISOR_UP
    if [ "$SUPERVISOR_UP" -eq 1 ]; then
      if [ "$SUP_START_MINS" -lt 30 ]; then
        log "supervisor 启动仅 ${SUP_START_MINS}min，跳过 kill + start（宽限期）"
        STATE="HEALTHY"
        ACTION="grace period active (${SUP_START_MINS}m < 30m)"
        # 不调 start_supervisor.sh，直接退出 AUTO_HEAL 块
      else
        kill -TERM $SUP_PIDS 2>/dev/null
        sleep 3
        # 进入下面的 start_supervisor.sh 流程
        NEEDS_COLD_START=0   # 刚杀了旧进程，走冷启动路径（pgrep 验活）
      fi
    fi

    # 仅在需要启动新 supervisor 时跑（skip-kill 路径已 STATE=HEALTHY 退出）
    if [ "$STATE" = "AUTO_HEAL" ]; then
      if O=$(bash scripts/start_supervisor.sh 2>&1); then
        # P1-B v2: 区分冷启动 vs 热重启
        # - 冷启动（S1 或刚 kill 旧进程）：模型加载 >10s，5s 内心跳不会写
        #   -> 用 pgrep 弱验活（进程活着即 HEALED）
        # - 热重启（原进程还在写心跳）：5s 足够心跳推进
        #   -> 用 stat mtime 强验活（防误报 HEALED）
        if [ "$NEEDS_COLD_START" -eq 0 ]; then
          # 冷启动路径：S1 原本 down 或刚 kill 旧进程
          sleep 5
          if pgrep -f "scripts/praxist_supervisor.py" >/dev/null 2>&1; then
            STATE="HEALED"
            record_heal_success
          else
            STATE="NEEDS_HUMAN"
            ACTION="heal started but process not running after 5s"
            record_heal_failure
          fi
        else
          # 热重启路径：理论上不会到这里（NEEDS_COLD_START=1 时上面要么 skip 要么 kill）
          # 保险起见保留心跳 mtime 检查
          sleep 5
          NEW_HB_MTIME=$(stat -c %Y "$HB_FILE" 2>/dev/null || echo 0)
          if [ "$NEW_HB_MTIME" -gt "$HB_MTIME" ]; then
            STATE="HEALED"
            record_heal_success
          else
            STATE="NEEDS_HUMAN"
            ACTION="heal started but heartbeat not advancing"
            record_heal_failure
          fi
        fi
      else
        STATE="NEEDS_HUMAN"
        ACTION="heal restart FAILED: $O"
        record_heal_failure
      fi
    fi
  fi
fi

case "$STATE" in
  HEALTHY)  echo "HEALTHY pids=[${SUP_PIDS% }] hb=${HB_AGE}min run=${RUN_MINS}min claude=$SUPCMD" ;;
  HEALED)   echo "HEALED [$ACTION] pids=[${SUP_PIDS% }] claude=$SUPCMD" ;;
  MAINTENANCE) echo "MAINTENANCE [$ACTION] pids=[${SUP_PIDS% }] hb=${HB_AGE}min run=${RUN_MINS}min" ;;
  CIRCUIT_BROKEN) echo "CIRCUIT_BROKEN [$ACTION] pids=[${SUP_PIDS% }] hb=${HB_AGE}min run=${RUN_MINS}min" ;;
  *)        echo "NEEDS_HUMAN [$ACTION] pids=[${SUP_PIDS% }] hb=${HB_AGE}min run=${RUN_MINS}min claude=$SUPCMD" ;;
esac