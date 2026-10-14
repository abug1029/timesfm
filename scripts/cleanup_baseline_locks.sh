#!/bin/bash
# 清理残留的基线重生锁文件（仅清理无进程持有的锁）
#
# 用法: bash scripts/cleanup_baseline_locks.sh
#
# 逻辑：
# 1. 检查锁文件是否存在
# 2. 用 fuser 检查是否有进程持有该锁
# 3. 读取锁文件中的 PID，检查进程是否存活
# 4. 仅清理无进程持有且 PID 已死的锁文件

set -e
cd "$(dirname "$0")/.."

echo "清理残留的锁文件..."

lock_count=0

cleanup_lock() {
    local lock_file="$1"
    if [ ! -f "$lock_file" ]; then
        return
    fi

    # 检查是否有进程持有该锁
    if fuser "$lock_file" 2>/dev/null; then
        echo "  跳过（进程持有）: $lock_file"
        return
    fi

    # 检查锁文件中的 PID 是否存活
    local pid=$(cat "$lock_file" 2>/dev/null | tr -d '[:space:]')
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "  跳过（PID $pid 存活）: $lock_file"
        return
    fi

    echo "  清理: $lock_file"
    rm -f "$lock_file"
    lock_count=$((lock_count + 1))
}

# 清理品种锁
for lock_file in task_FM/config/.*.lock; do
    if [ -f "$lock_file" ]; then
        cleanup_lock "$lock_file"
    fi
done

# 清理工全局锁
cleanup_lock "/tmp/daily_update.lock"
cleanup_lock "/tmp/ensure_baselines.lock"

echo ""
echo "清理完成: 移除 $lock_count 个锁文件"
