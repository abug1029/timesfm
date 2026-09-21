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
cd "$(dirname "$(readlink -f "$0")")/.."   # repo root (robust to bare-name / PATH launch)

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

# 2b) Re-assert prepend in case .env.praxist ever sets PATH (would clobber step 1).
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# 3) Sanity: claude must be the WSL-native binary before we start peers.
if ! command -v claude >/dev/null 2>&1; then
  echo "FATAL: claude not found on PATH" >&2
  exit 1
fi
case "$(readlink -f "$(command -v claude)" 2>/dev/null || echo /mnt/c/unknown)" in
  /mnt/c/*)
    echo "WARN: claude resolves to Windows shim $(command -v claude) — will exit-126 for peers" >&2 ;;
  *)
    echo "OK: claude -> $(command -v claude) (WSL-native)" ;;
esac

# 4) Launch supervisor detached (survives SSH/session close).
mkdir -p data/cache
setsid nohup .venv/bin/python -u scripts/praxist_supervisor.py \
  --goal scripts/praxist_goal.yaml \
  >> data/cache/supervisor.out 2>&1 < /dev/null &

sleep 1
SUPERVISOR_PID=$!
if [ -n "${SUPERVISOR_PID:-}" ]; then
  echo "Supervisor launched: PID ${SUPERVISOR_PID}"
else
  echo "WARN: could not detect supervisor PID (check data/cache/supervisor.out)" >&2
fi