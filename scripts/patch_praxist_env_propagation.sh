#!/bin/bash
# Patch praxist to pass all required env vars for all providers.
# Fixes 3 bugs found in env propagation chain:
# 1. anthropic_messages: missing ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN
# 2. openai_compatible: missing OPENAI_BASE_URL
# 3. base dict: missing OPENAI_BASE_URL definition
#
# Run after: pip install --upgrade praxist
# Idempotent: safe to run multiple times.
set -euo pipefail
FM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FM_ROOT

echo "Patching praxist env propagation (FM_ROOT=$FM_ROOT)..."

# Backup all files first
for rel in \
  ".venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/backend/agent.py" \
  ".venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/provider_env.py" \
  ".venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/stage.py"
do
  f="$FM_ROOT/$rel"
  [ -f "$f" ] && cp "$f" "${f}.bak_before_env_fix" 2>/dev/null || true
done

"$FM_ROOT/.venv/bin/python" << 'PYEOF'
import os

fm_root = os.environ.get('FM_ROOT', '/home/abug/timesfm')
files = [
    os.path.join(fm_root, '.venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/backend/agent.py'),
    os.path.join(fm_root, '.venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/provider_env.py'),
    os.path.join(fm_root, '.venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/stage.py'),
]

for p in files:
    if not os.path.exists(p):
        print(f'  SKIP: {p} not found')
        continue
    s = open(p).read()
    orig = s
    basename = os.path.basename(p)

    if basename == 'agent.py':
        old = '    elif provider_ref == "model_provider:anthropic_messages":\n        allowed = ("ANTHROPIC_API_KEY",)'
        new = '    elif provider_ref == "model_provider:anthropic_messages":\n        allowed = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")'
        s = s.replace(old, new)
        old2 = '    elif provider_ref == "model_provider:openai_compatible":\n        allowed = ("OPENAI_API_KEY",)'
        new2 = '    elif provider_ref == "model_provider:openai_compatible":\n        allowed = ("OPENAI_API_KEY", "OPENAI_BASE_URL")'
        s = s.replace(old2, new2)

    if basename == 'provider_env.py':
        old = '        "OPENAI_API_KEY": None,\n        "DEEPSEEK_API_KEY": None,\n    }'
        new = '        "OPENAI_API_KEY": None,\n        "OPENAI_BASE_URL": None,\n        "DEEPSEEK_API_KEY": None,\n    }'
        s = s.replace(old, new)
        old2 = '    if model_provider_ref == "model_provider:anthropic_messages":\n        return {\n            **base,\n            "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY"),\n        }'
        new2 = '    if model_provider_ref == "model_provider:anthropic_messages":\n        return {\n            **base,\n            "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY"),\n            "ANTHROPIC_BASE_URL": env.get("ANTHROPIC_BASE_URL"),\n            "ANTHROPIC_AUTH_TOKEN": env.get("ANTHROPIC_AUTH_TOKEN"),\n        }'
        s = s.replace(old2, new2)
        old3 = '    if model_provider_ref == "model_provider:openai_compatible":\n        return {**base, "OPENAI_API_KEY": env.get("OPENAI_API_KEY")}'
        new3 = '    if model_provider_ref == "model_provider:openai_compatible":\n        return {\n            **base,\n            "OPENAI_API_KEY": env.get("OPENAI_API_KEY"),\n            "OPENAI_BASE_URL": env.get("OPENAI_BASE_URL"),\n        }'
        s = s.replace(old3, new3)

    if basename == 'stage.py':
        old = '        "OPENROUTER_API_KEY": None,\n        "OPENAI_API_KEY": None,\n        "DEEPSEEK_API_KEY": None,'
        new = '        "OPENROUTER_API_KEY": None,\n        "OPENAI_API_KEY": None,\n        "OPENAI_BASE_URL": None,\n        "DEEPSEEK_API_KEY": None,'
        s = s.replace(old, new)
        old2 = '    if model_provider_ref == "model_provider:anthropic_messages":\n        return {\n            **base,\n            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),\n        }'
        new2 = '    if model_provider_ref == "model_provider:anthropic_messages":\n        return {\n            **base,\n            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),\n            "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL"),\n            "ANTHROPIC_AUTH_TOKEN": os.environ.get("ANTHROPIC_AUTH_TOKEN"),\n        }'
        s = s.replace(old2, new2)
        old3 = '    if model_provider_ref == "model_provider:openai_compatible":\n        return {**base, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY")}'
        new3 = '    if model_provider_ref == "model_provider:openai_compatible":\n        return {\n            **base,\n            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),\n            "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL"),\n        }'
        s = s.replace(old3, new3)

    if s != orig:
        open(p, 'w').write(s)
        print(f'  Patched: {basename}')
    else:
        print(f'  Already patched: {basename}')
PYEOF

echo "Done."
