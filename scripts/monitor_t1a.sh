#!/bin/bash
# T1a 监控脚本: 等待 8 个 nocov 基线就绪，或 supervisor 退出
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

TARGET=8
MIN_LINES=100
MAX_WAIT=14400   # 4 小时上限
elapsed=0
poll=60

while [ $elapsed -lt $MAX_WAIT ]; do
    # 计数就绪的 nocov 基线
    ready=0
    for f in task_FM/config/baseline_points_*_nocov.jsonl; do
        [ -f "$f" ] || continue
        lines=$(wc -l < "$f" 2>/dev/null || echo 0)
        if [ "$lines" -ge "$MIN_LINES" ]; then
            ready=$((ready + 1))
        fi
    done

    if [ "$ready" -ge "$TARGET" ]; then
        echo "T1a COMPLETE: $ready/$TARGET nocov baselines ready"
        ls -lh task_FM/config/baseline_points_*_nocov.jsonl
        exit 0
    fi

    # 检查 supervisor 是否还活着
    if ! pgrep -f praxist_supervisor > /dev/null 2>&1; then
        echo "T1a FAILED: supervisor process is gone (ready=$ready/$TARGET)"
        echo "--- last 30 lines of supervisor.out ---"
        tail -30 data/cache/supervisor.out
        exit 1
    fi

    echo "[$((elapsed/60))min] ready=$ready/$TARGET (supervisor alive)"
    sleep $poll
    elapsed=$((elapsed + poll))
done

echo "T1a TIMEOUT: ${MAX_WAIT}s elapsed without completion"
exit 2
