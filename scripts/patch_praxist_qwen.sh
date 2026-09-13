#!/usr/bin/env bash
# Patch praxist anthropic_messages plugin to accept qwen* models.
# Required after every fresh 'pip install praxist'.
# Usage: bash scripts/patch_praxist_qwen.sh [venv_path]
set -euo pipefail
VENV="${1:-.venv}"
PLUGIN="$VENV/lib/python3.11/site-packages/praxist/plugins/model_providers/anthropic_messages/plugin.yaml"
if [ ! -f "$PLUGIN" ]; then
  echo "ERROR: $PLUGIN not found"
  exit 1
fi
if grep -q '"qwen\*"' "$PLUGIN"; then
  echo "Already patched: qwen* present"
else
  sed -i 's|    - "claude-\*"|    - "claude-*"\n    - "qwen*"|' "$PLUGIN"
  echo "Patched: added qwen* to compatible_model_patterns"
fi
