#!/bin/bash
# 归档 supervisor 历史日志
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

ARCH="data/archive/logs_2026-09-28T1210"
mkdir -p "$ARCH"

echo "=== 归档前行数 ==="
wc -l data/cache/supervisor.out

# 1) 完整复制 supervisor.out（含历史 + 当前运行）
cp -p data/cache/supervisor.out "$ARCH/supervisor.out.full"

# 2) 复制其余遗留日志（均为 Sep 10-24，非运行中进程持有）
for f in supervisor_events.jsonl supervisor_heartbeat supervisor_loop.log supervisor_loop.out supervisor_state.json; do
    if [ -f "data/cache/$f" ]; then
        cp -p "data/cache/$f" "$ARCH/"
        echo "archived: $f"
    fi
done

# 3) 记录归档时的运行快照
{
    echo "# supervisor 日志归档 2026-09-28T1210"
    echo
    echo "归档原因: supervisor.out 累积了 Sep 23-24 历史内容，"
    echo "          导致当前 T1a 运行进度难以辨识（grep 到 105 条历史 Baseline generation 记录）。"
    echo
    echo "归档时状态:"
    echo "- supervisor PID: $(pgrep -f praxist_supervisor | head -1)"
    echo "- 归档行数: $(wc -l < data/cache/supervisor.out)"
    echo "- 当前 T1a 进度: CJ 完成，EG 生成中"
    echo "- 已就绪 nocov 基线: rb, cj"
    echo
    echo "归档后 supervisor.out 已截断为 0，后续仅含本轮运行日志。"
    echo "被截断的历史内容完整保存在 supervisor.out.full。"
} > "$ARCH/MANIFEST.md"

echo
echo "=== 归档清单 ==="
ls -lh --time-style=+%m-%d_%H:%M "$ARCH/"

# 4) 截断运行中的 supervisor.out（fd 为 O_APPEND，截断安全）
BEFORE=$(wc -l < data/cache/supervisor.out)
: > data/cache/supervisor.out
AFTER=$(wc -l < data/cache/supervisor.out)
echo
echo "=== 截断结果 ==="
echo "supervisor.out: $BEFORE 行 -> $AFTER 行"
echo "历史内容已保存至: $ARCH/supervisor.out.full"

# 5) 验证进程仍存活
if pgrep -f praxist_supervisor > /dev/null; then
    echo "supervisor 进程存活: OK"
else
    echo "WARN: supervisor 进程未找到"
fi
