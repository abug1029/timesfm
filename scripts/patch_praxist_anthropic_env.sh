#!/bin/bash
# Patch praxist to pass ANTHROPIC_BASE_URL for anthropic_messages provider.
# Run after: pip install --upgrade praxist
# Idempotent: safe to run multiple times.
set -euo pipefail
FM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Patch 1: agent.py - allow ANTHROPIC_BASE_URL in _scoped_legacy_provider_env
AGENT_PY="$FM_ROOT/.venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/backend/agent.py"
if [ -f "$AGENT_PY" ]; then
  if ! grep -q '"ANTHROPIC_BASE_URL"' "$AGENT_PY" 2>/dev/null; then
    python3 -c "
p = '$AGENT_PY'
s = open(p).read()
old = '''    elif provider_ref == \"model_provider:anthropic_messages\":
        allowed = (\"ANTHROPIC_API_KEY\",)'''
new = '''    elif provider_ref == \"model_provider:anthropic_messages\":
        allowed = (\"ANTHROPIC_API_KEY\", \"ANTHROPIC_BASE_URL\", \"ANTHROPIC_AUTH_TOKEN\")'''
assert old in s, 'pattern not found in agent.py'
open(p, 'w').write(s.replace(old, new))
print('Patched: agent.py')
"
  else
    echo "agent.py already patched"
  fi
fi

# Patch 2: provider_env.py - include ANTHROPIC_BASE_URL in freeze_provider_env
PROVIDER_ENV_PY="$FM_ROOT/.venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/provider_env.py"
if [ -f "$PROVIDER_ENV_PY" ]; then
  if ! grep -q 'ANTHROPIC_BASE_URL.*env.get.*ANTHROPIC_BASE_URL' "$PROVIDER_ENV_PY" 2>/dev/null; then
    python3 -c "
p = '$PROVIDER_ENV_PY'
s = open(p).read()
old = '''    if model_provider_ref == \"model_provider:anthropic_messages\":
        return {
            **base,
            \"ANTHROPIC_API_KEY\": env.get(\"ANTHROPIC_API_KEY\"),
        }'''
new = '''    if model_provider_ref == \"model_provider:anthropic_messages\":
        return {
            **base,
            \"ANTHROPIC_API_KEY\": env.get(\"ANTHROPIC_API_KEY\"),
            \"ANTHROPIC_BASE_URL\": env.get(\"ANTHROPIC_BASE_URL\"),
            \"ANTHROPIC_AUTH_TOKEN\": env.get(\"ANTHROPIC_AUTH_TOKEN\"),
        }'''
assert old in s, 'pattern not found in provider_env.py'
open(p, 'w').write(s.replace(old, new))
print('Patched: provider_env.py')
"
  else
    echo "provider_env.py already patched"
  fi
fi
