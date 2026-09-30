#!/bin/bash
# 三环系统清洁重启脚本
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 三环系统清洁重启 ==="
echo "时间: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# 1. 停止旧 supervisor
echo "[1/5] 停止旧的 supervisor 进程..."
if pgrep -f praxist_supervisor.py >/dev/null 2>&1; then
  echo "  发现运行中的 supervisor"
  pkill -TERM -f praxist_supervisor.py || true
  sleep 2
  if pgrep -f praxist_supervisor.py >/dev/null 2>&1; then
    echo "  强制终止..."
    pkill -9 -f praxist_supervisor.py || true
    sleep 1
  fi
  echo "  ✓ 已停止"
else
  echo "  ✓ 无运行中的 supervisor"
fi

# 2. 归档 run-level 状态
echo "[2/5] 归档 run-level 状态..."
RUN_DIR=$(ls -td task_FM/experiments/run_*_primary_task_FM 2>/dev/null | head -1 || echo "")
if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  COUNT=0
  [ -f "$RUN_DIR/run.json" ] && mv "$RUN_DIR/run.json" "$RUN_DIR/run.json.archived_$TS" && COUNT=$((COUNT+1))
  [ -f "$RUN_DIR/orchestrator_status.json" ] && mv "$RUN_DIR/orchestrator_status.json" "$RUN_DIR/orchestrator_status.json.archived_$TS" && COUNT=$((COUNT+1))
  [ -f "$RUN_DIR/run_stop_report.json" ] && mv "$RUN_DIR/run_stop_report.json" "$RUN_DIR/run_stop_report.json.archived_$TS" && COUNT=$((COUNT+1))
  echo "  ✓ 已归档 $COUNT 个文件"
else
  echo "  ✓ 无需归档"
fi

# 3. 归档 peer-level 状态
echo "[3/5] 归档 peer-level 状态..."
if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  COUNT=0
  for peer_dir in "$RUN_DIR"/gen_*/peers/*/memory; do
    [ -d "$peer_dir" ] || continue
    [ -f "$peer_dir/peer_state.yaml" ] && mv "$peer_dir/peer_state.yaml" "$peer_dir/peer_state.yaml.archived_$TS" && COUNT=$((COUNT+1))
    [ -f "$peer_dir/session_handoff.md" ] && mv "$peer_dir/session_handoff.md" "$peer_dir/session_handoff.md.archived_$TS" && COUNT=$((COUNT+1))
  done
  echo "  ✓ 已归档 $COUNT 个 peer 文件"
else
  echo "  ✓ 无需归档"
fi

# 4. 删除 lock 文件
echo "[4/5] 删除 lock 文件..."
COUNT=0
[ -f data/cache/supervisor.lock ] && rm -f data/cache/supervisor.lock && COUNT=$((COUNT+1))
[ -f data/cache/aligned_slow_loop.lock ] && rm -f data/cache/aligned_slow_loop.lock && COUNT=$((COUNT+1))
echo "  ✓ 已删除 $COUNT 个 lock"

# 5. 创建重启标记
if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then
  echo "[5/5] 创建重启标记..."
  cat > "$RUN_DIR/RESTART_MARKER.md" <<EOF
# Restart Marker

Time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Type: Clean restart

## Notice to Peer Agents
- This is a fresh start
- Do not reference old session IDs
- Treat all peer states as initial
- Ignore archived finalized markers
EOF
  echo "  ✓ 已创建"
fi

echo ""
echo "=== 清洁重启完成 ==="
sleep 2
exec bash scripts/start_supervisor.sh
