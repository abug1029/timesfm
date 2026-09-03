#!/bin/bash
# _batch_lib.sh — 长时 batch 任务共享进程管理库
# 所有 batch_f[1-4]_single_cov.sh source 此文件
#
# 提供:
#   batch_init "$BATCH_NAME"  — 原子抢锁 + 双模式清场 + heartbeat
#   batch_run_one "$sym" "$combo" "$label" — worker 启动 + PID 追踪
#   cleanup                    — EXIT trap: 安全删锁 + 杀 heartbeat
#
# 使用前必须设置:
#   BATCH_NAME="batch_f1"  (或其他标识)
#   FM_ROOT="D:/FlyBuddy/FM_a"
#
# 锁文件: reports/data_ops/.batch_runner.lock
#   内容: winpid|batch_name|unix_timestamp
# worker PID: reports/data_ops/.worker.pid

# ============================================================
# 常量
# ============================================================
LOCK_FILE="${FM_ROOT}/reports/data_ops/.batch_runner.lock"
WORKER_PID_FILE="${FM_ROOT}/reports/data_ops/.worker.pid"
HEARTBEAT_INTERVAL=60       # 秒
STALE_THRESHOLD=300         # 5 分钟无心跳视为过期
KILL_SCRIPT="${FM_ROOT}/scripts/_kill_batch.ps1"

# ============================================================
# 工具函数
# ============================================================

# 获取当前 bash 的 Windows PID (用于跨进程识别)
_get_my_winpid() {
    if [ -f /proc/self/winpid ]; then
        cat /proc/self/winpid
    else
        ps -p $$ -o winpid= 2>/dev/null | tr -d ' '
    fi
}

# 获取当前时间戳 (秒)
_now_ts() {
    date +%s
}

# 从锁文件提取字段
_lock_field() {
    local field="$1"  # 1=winpid, 2=name, 3=timestamp
    if [ -f "$LOCK_FILE" ]; then
        cut -d'|' -f"$field" "$LOCK_FILE" 2>/dev/null
    fi
}

# 检查锁是否过期 (心跳时间戳距今 > STALE_THRESHOLD)
_lock_is_stale() {
    local lock_ts
    lock_ts=$(_lock_field 3)
    if [ -z "$lock_ts" ]; then
        return 0  # 无时间戳 → 视为过期
    fi
    local now
    now=$(_now_ts)
    local age=$(( now - lock_ts ))
    [ "$age" -ge "$STALE_THRESHOLD" ]
}

# 打印锁持有者信息
_print_lock_holder() {
    local winpid name ts
    winpid=$(_lock_field 1)
    name=$(_lock_field 2)
    ts=$(_lock_field 3)
    local age="unknown"
    if [ -n "$ts" ]; then
        age=$(( $(_now_ts) - ts ))
        age="${age}s ago"
    fi
    echo "  Lock holder: winpid=$winpid name=$name heartbeat=$age"
}

# ============================================================
# 双模式清场
# ============================================================

# 调用 _kill_batch.ps1 清理所有残留进程
# 参数: $1 = 要排除的 winpid (通常是自身)
_do_cleanup() {
    local exclude_pid="${1:-0}"

    echo "[batch_lib] Dual-mode cleanup (exclude PID=$exclude_pid)..."

    # Step 1: Dry-run 预览
    local preview
    preview=$(powershell -NoProfile -ExecutionPolicy Bypass \
        -File "$KILL_SCRIPT" -DryRun -ExcludePid "$exclude_pid" 2>&1)
    echo "$preview"

    if echo "$preview" | grep -q "NONE FOUND"; then
        echo "[batch_lib] No residual processes. Clean."
        return 0
    fi

    # Step 2: 实际清场
    local kill_result
    kill_result=$(powershell -NoProfile -ExecutionPolicy Bypass \
        -File "$KILL_SCRIPT" -ExcludePid "$exclude_pid" 2>&1)
    echo "$kill_result"

    # Step 3: 复查
    if echo "$kill_result" | grep -q "VERIFIED CLEAN"; then
        echo "[batch_lib] Cleanup verified."
        return 0
    elif echo "$kill_result" | grep -q "STILL ALIVE"; then
        echo "[batch_lib] ERROR: residual processes remain after kill!"
        return 1
    else
        echo "[batch_lib] WARNING: unexpected cleanup result"
        return 1
    fi
}

# 清理 worker.pid 中的遗留 worker
_cleanup_orphan_workers() {
    if [ ! -f "$WORKER_PID_FILE" ]; then
        return 0
    fi

    local count
    count=$(wc -l < "$WORKER_PID_FILE" 2>/dev/null || echo 0)
    if [ "$count" -eq 0 ]; then
        rm -f "$WORKER_PID_FILE"
        return 0
    fi

    echo "[batch_lib] Found $count worker PIDs in $WORKER_PID_FILE, killing..."
    while IFS= read -r wpid; do
        if [ -n "$wpid" ]; then
            echo "[batch_lib]   Killing orphan worker PID=$wpid"
            # MSYS kill 对 Windows PID 无效, 仅用 taskkill
            taskkill /F /PID "$wpid" 2>/dev/null || true
        fi
    done < "$WORKER_PID_FILE"

    rm -f "$WORKER_PID_FILE"
    sleep 2
}

# ============================================================
# Heartbeat (后台进程)
# ============================================================

_start_heartbeat() {
    # 后台 while 循环, 每 HEARTBEAT_INTERVAL 秒更新锁时间戳
    (
        while true; do
            sleep "$HEARTBEAT_INTERVAL"

            # 自校验: 父进程 (winpid) 还活着吗?
            # 用 PowerShell exit code 直接判断, 不依赖 grep 文本匹配
            if ! powershell -NoProfile -Command \
                "exit !(Get-Process -Id $MY_WINPID -ErrorAction SilentlyContinue)" 2>/dev/null; then
                exit 0  # 父已死, heartbeat 自退
            fi

            # 更新锁时间戳 (仅当锁仍属于自己时)
            if [ -f "$LOCK_FILE" ]; then
                local current_winpid
                current_winpid=$(cut -d'|' -f1 "$LOCK_FILE" 2>/dev/null)
                if [ "$current_winpid" = "$MY_WINPID" ]; then
                    local ts
                    ts=$(_now_ts)
                    echo "${MY_WINPID}|${BATCH_NAME}|${ts}" > "$LOCK_FILE"
                else
                    exit 0  # 锁已被抢, 自退
                fi
            else
                exit 0  # 锁已删除, 自退
            fi
        done
    ) &
    HEARTBEAT_PID=$!
    # 从子 shell 分离 (避免 wait 时阻塞)
    disown "$HEARTBEAT_PID" 2>/dev/null || true
}

# ============================================================
# batch_init — 主入口
# ============================================================

batch_init() {
    local batch_name="${1:?Usage: batch_init <name>}"
    BATCH_NAME="$batch_name"

    # 获取自身 winpid
    MY_WINPID=$(_get_my_winpid)
    if [ -z "$MY_WINPID" ]; then
        echo "[batch_lib] ERROR: cannot determine winpid"
        exit 1
    fi
    echo "[batch_lib] Initializing (winpid=$MY_WINPID, batch=$BATCH_NAME)"

    # ---- Step 1: 原子抢锁 (set -C noclobber) ----
    local lock_acquired=false
    (
        set -C
        echo "${MY_WINPID}|${BATCH_NAME}|$(_now_ts)" > "$LOCK_FILE"
    ) 2>/dev/null

    if [ $? -eq 0 ] && [ -f "$LOCK_FILE" ]; then
        # 验证锁内容确实是我们写的 (防止 race)
        local lock_winpid
        lock_winpid=$(_lock_field 1)
        if [ "$lock_winpid" = "$MY_WINPID" ]; then
            lock_acquired=true
            echo "[batch_lib] Lock acquired atomically."
        fi
    fi

    if [ "$lock_acquired" = false ]; then
        # 抢锁失败 → 检查持有者心跳
        echo "[batch_lib] Lock held by another instance."
        _print_lock_holder

        if _lock_is_stale; then
            echo "[batch_lib] Lock is STALE (>${STALE_THRESHOLD}s). Taking over..."
            # 强制删除过期锁
            rm -f "$LOCK_FILE"
            # 重试抢锁
            (
                set -C
                echo "${MY_WINPID}|${BATCH_NAME}|$(_now_ts)" > "$LOCK_FILE"
            ) 2>/dev/null

            local retry_winpid
            retry_winpid=$(_lock_field 1)
            if [ "$retry_winpid" = "$MY_WINPID" ]; then
                lock_acquired=true
                echo "[batch_lib] Lock re-acquired after stale cleanup."
            else
                echo "[batch_lib] ERROR: failed to re-acquire lock (race condition)."
                exit 1
            fi
        else
            echo "[batch_lib] Lock is FRESH. Exiting to avoid duplicate."
            exit 1
        fi
    fi

    # ---- Step 2: 跳过自动清场 (MSYS winpid 不对应 Windows 进程树, 无法保护自身) ----
    # 孤儿清理改为手动: powershell -File scripts/_kill_batch.ps1
    # 若上次崩溃残留进程, 启动前先手动运行 _kill_batch.ps1
    echo "[batch_lib] Skipping auto-cleanup (MSYS winpid incompatible with Win32_Process tree)."
    echo "[batch_lib] If stale processes exist, run: powershell -File scripts/_kill_batch.ps1"

    # ---- Step 3: 初始化 worker PID 文件 ----
    : > "$WORKER_PID_FILE"

    # ---- Step 4: 启动 heartbeat ----
    _start_heartbeat
    echo "[batch_lib] Heartbeat started (PID=$HEARTBEAT_PID, interval=${HEARTBEAT_INTERVAL}s)"

    # ---- Step 5: 设置 EXIT trap ----
    trap '_batch_cleanup' EXIT

    echo "[batch_lib] Init complete. Ready to run."
}

# ============================================================
# EXIT cleanup
# ============================================================

_batch_cleanup() {
    local rc=$?

    # 杀 heartbeat
    if [ -n "$HEARTBEAT_PID" ]; then
        kill "$HEARTBEAT_PID" 2>/dev/null || true
    fi

    # 仅当锁仍属于自己时才删 (防止删掉新实例的锁)
    if [ -f "$LOCK_FILE" ]; then
        local lock_winpid
        lock_winpid=$(cut -d'|' -f1 "$LOCK_FILE" 2>/dev/null)
        if [ "$lock_winpid" = "$MY_WINPID" ]; then
            rm -f "$LOCK_FILE"
        fi
    fi

    # 清理 worker PID 文件
    rm -f "$WORKER_PID_FILE"
}

# ============================================================
# batch_run_one — worker 启动 + PID 追踪
# 用法: batch_run_one "ss" "calendar_cyclical" "F1-cal-ss"
# ============================================================

batch_run_one() {
    local sym="$1" combo="$2" label="$3"
    local jsonl="$4" log="$5"

    # 断点续跑: 已完成则跳过
    if [ -f "$jsonl" ] && grep -q "\"label\": \"$label\"" "$jsonl" 2>/dev/null; then
        echo "[SKIP] $label already done" | tee -a "$log"
        return 0
    fi

    echo "[START] $label: $sym --combo '$combo'" | tee -a "$log"

    # 启动 worker (前台, 因为需要串行执行)
    if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$log" 2>&1; then
        # 提取指标
        local pf ev maxdd diracc
        pf=$(grep -aoE 'PF=[0-9.]+' "$log" | tail -1 || echo "PF=unknown")
        ev=$(grep -aoE 'EV_ratio=[+-]?[0-9.]+' "$log" | tail -1 || echo "EV_ratio=unknown")
        maxdd=$(grep -aoE 'MaxDD=[+-]?[0-9.]+%' "$log" | tail -1 || echo "MaxDD=unknown")
        diracc=$(grep -aoE '[0-9]+pts DirAcc=[0-9.]+' "$log" | tail -1 || echo "unknown")

        local metric="${diracc} ${pf} ${ev} ${maxdd}"
        if echo "$metric" | grep -q "unknown"; then
            echo "[DONE?] $label: $metric (NEEDS_REVIEW)" | tee -a "$log"
        else
            echo "[DONE] $label: $metric" | tee -a "$log"
        fi

        # 写 JSONL
        echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"$combo\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$jsonl"
    else
        local rc=$?
        echo "[FAIL] $label exit=$rc" | tee -a "$log"
    fi

    sleep 8
}

# ============================================================
# batch_shutdown — 手动终止 (可选)
# ============================================================

batch_shutdown() {
    echo "[batch_lib] Shutting down..."
    _batch_cleanup
    echo "[batch_lib] Shutdown complete."
}
