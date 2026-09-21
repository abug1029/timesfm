#!/bin/bash
# Canonical supervisor launcher for FM_a three-loop system.
#
# Durable fix for the peer "Exec format error (exit 126)" bug:
# Peer agents spawn `claude`, which must resolve to the WSL-native binary at
# ~/.local/bin/claude (NOT the Windows npm shim at /mnt/c/.../npm/claude).
# Supervisors launched via non-login `bash -c` inherit a PATH that lacks
# ~/.local/bin unless we prepend it here. This script is THE canonical start.
#
# Usage:  scripts/start_supervisor.sh
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root /home/abug/timesfm

# 1) Guarantee WSL-native claude / user bins precede Windows npm shim.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# 2) Load Praxist credentials (DashScope/Anthropic, model, TimesFM weights).
set -a
if [ -f .env.praxist ]; then
  # shellcheck disable=SC1091
  source .env.praxist
fi
set +a

# 3) Sanity: claude must be the WSL-native binary before we start peers.
if ! command -v claude >/dev/null 2>&1; then
  echo "FATAL: claude not found on PATH" >&2
  exit 1
fi
if [ "$(readlink -f "$(command -v claude)" 2>/dev/null)" = "/home/abug/.local/bin/claude" ] \
   || echo "$(command -v claude)" | grep -q "/home/abug/.local/bin"; then
  echo "OK: claude -> $(command -v claude) (WSL-native)"
else
  echo "WARN: claude resolves to $(command -v claude) — unexpectedly not ~/.local/bin" >&2
fi

# 4) Launch supervisor detached (survives SSH/session close).
mkdir -p data/cache
setsid nohup .venv/bin/python -u scripts/praxist_supervisor.py \
  --goal scripts/praxist_goal.yaml \
  >> data/cache/supervisor.out 2>&1 < /dev/null &

sleep 1
PID=$(pgrep -f "scripts/praxist_supervisor.py" | head -1 || true)
if [ -n "${PID:-}" ]; then
  echo "Supervisor launched: PID ${PID}"
else
  echo "WARN: could not detect supervisor PID (check data/cache/supervisor.out)" >&2
fi