#!/bin/bash
# Start praxist — SSH-resilient, self-daemonizing.
# Usage: bash start_praxist.sh [--once] [--supervisor]
#   --once        run supervisor --once (single decision cycle)
#   --supervisor  run supervisor loop (continuous)
#   (default)     start praxist fast-loop run
#
# This script never blocks: it launches the process detached and returns
# immediately. Safe to run over flaky SSH — no session dependency.

FM_ROOT="/workspace/repos/timesfm-abug1029"
HOLD="$FM_ROOT/docs/superpowers/reports/praxist_20260906_ctrl/IDLE_HOLD"
PRAXIST_BIN="/home/box/.praxist-venv/bin/python3"
LOG_DIR="$FM_ROOT/data/cache"
mkdir -p "$LOG_DIR"

if [[ -f "$HOLD" ]]; then
  echo "REFUSED: IDLE_HOLD present ($HOLD). Do not start Praxist until user lifts hold." >&2
  exit 78
fi

# Source env (non-blocking, no secret echo)
set -a
source "$FM_ROOT/.env.praxist"
set +a

cd "$FM_ROOT" || exit 1

case "${1:-start}" in
  --supervisor)
    LOG="$LOG_DIR/supervisor_loop.out"
    echo "[$(date -Is)] Starting supervisor loop (detached) → $LOG"
    nohup "$PRAXIST_BIN" -u "$FM_ROOT/scripts/praxist_supervisor.py" >> "$LOG" 2>&1 &
    disown
    echo "PID: $!"
    ;;
  --once)
    LOG="$LOG_DIR/supervisor_once.out"
    echo "[$(date -Is)] Running supervisor --once (detached) → $LOG"
    nohup "$PRAXIST_BIN" -u "$FM_ROOT/scripts/praxist_supervisor.py" --once >> "$LOG" 2>&1 &
    disown
    echo "PID: $!"
    ;;
  start|*)
    TIMESTAMP=$(date -u +"%Y-%m-%d_%H-%M-%S")
    RUN_DIR="$FM_ROOT/task_FM/experiments/run_${TIMESTAMP}_primary_task_FM"
    LOG="$RUN_DIR/logs/launcher.nohup.log"
    mkdir -p "$(dirname "$LOG")"
    echo "[$(date -Is)] Starting praxist (detached) → $RUN_DIR"
    nohup /home/box/.praxist-venv/bin/praxist start \
      --task-path "$FM_ROOT/task_FM" \
      --run-dir "$RUN_DIR" \
      --daemonize \
      --json \
      --model-provider model_provider:anthropic_messages \
      --model qwen3.7-plus >> "$LOG" 2>&1 &
    disown
    START_PID=$!
    # Wait for run.json to appear (praxist daemonize writes it on success)
    for i in $(seq 1 30); do
      sleep 1
      if [[ -f "$RUN_DIR/run.json" ]]; then
        echo "Run started. run_dir=$RUN_DIR"
        cat "$RUN_DIR/run.json" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f\"  run_id: {d.get('run_id','?')}\")
    print(f\"  pid:    {d.get('pid','?')}\")
    print(f\"  model:  {d.get('model','?')}\")
    print(f\"  state:  {d.get('state','?')}\")
except: pass
" 2>/dev/null
        exit 0
      fi
    done
    echo "Timeout waiting for run.json (launcher PID=$START_PID may still be starting)"
    echo "Check: tail -f $LOG"
    ;;
esac
