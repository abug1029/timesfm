#!/usr/bin/env bash
# While IDLE_HOLD exists, SIGTERM any praxist.run (not interactive claude / hardcap).
set -euo pipefail
HOLD="/home/abug/timesfm/docs/superpowers/reports/praxist_20260907_ctrl/IDLE_HOLD"
LOG="/home/abug/timesfm/docs/superpowers/reports/praxist_20260907_ctrl/idle_hold_guard.log"
INTERVAL=30
echo "$(date -Is) guard_start pid=$$" >>"$LOG"
while true; do
  if [[ ! -f "$HOLD" ]]; then
    echo "$(date -Is) IDLE_HOLD gone; exiting" >>"$LOG"
    exit 0
  fi
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
    case "$cmd" in
      *'praxist.run'*)
        echo "$(date -Is) SIGTERM pid=$pid cmd=${cmd:0:180}" >>"$LOG"
        kill -TERM "$pid" 2>/dev/null || true
        ;;
    esac
  done < <(pgrep -f 'python3? -m praxist\.run' || true)
  sleep "$INTERVAL"
done
