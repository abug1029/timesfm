#!/bin/bash
# 等待 rb nocov 基线重生完成且指纹正确
cd /home/abug/timesfm

TARGET_FP="bd851c9ca0730dc5"
P=task_FM/config/baseline_points_rb_nocov.jsonl
MAX_WAIT=2400   # 40 分钟上限
elapsed=0

while [ $elapsed -lt $MAX_WAIT ]; do
    if [ -f "$P" ]; then
        lines=$(wc -l < "$P" 2>/dev/null || echo 0)
        fp=$(head -1 "$P" 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.loads(sys.stdin.read()); print((d.get('protocol_fingerprint') or 'None')[:16])
except Exception: print('parse_error')
" 2>/dev/null || echo "unreadable")
        if [ "$lines" -ge 100 ] && [ "$fp" = "$TARGET_FP" ]; then
            echo "✅ rb 基线重生完成且指纹正确"
            echo "   行数=$lines  指纹=$fp"
            exit 0
        fi
        echo "[$((elapsed/60))min] 行数=$lines 指纹=$fp（目标 $TARGET_FP）"
    else
        echo "[$((elapsed/60))min] 文件尚未生成"
    fi

    if ! pgrep -f 'scripts/regen_rb.py' > /dev/null; then
        echo "❌ regen 进程已退出但基线未就绪"
        echo "--- 日志尾部 ---"
        tail -20 /tmp/regen_rb.log 2>/dev/null
        exit 1
    fi

    sleep 60
    elapsed=$((elapsed + 60))
done

echo "⏱ 超时 ${MAX_WAIT}s"
exit 2
