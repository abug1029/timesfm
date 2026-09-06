#!/usr/bin/env python3
"""Patch anthropic_messages compatible_model_patterns to allow DashScope qwen* ids.

Praxist validates --model against plugin.yaml before launch. anthropic_messages
only allowed claude-*; failover model qwen3.7-plus failed with:
  model 'qwen3.7-plus' is not compatible with model_provider:anthropic_messages

Safe local overlay (site-packages). Re-run after rebuilding praxist venvs.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [
    Path.home() / ".praxist-venv/lib/python3.13/site-packages/praxist/plugins/model_providers/anthropic_messages/plugin.yaml",
    ROOT / ".praxist-venv/lib/python3.13/site-packages/praxist/plugins/model_providers/anthropic_messages/plugin.yaml",
]

OLD = '''  compatible_model_patterns:
    - "claude-*"
'''
NEW = '''  compatible_model_patterns:
    - "claude-*"
    - "qwen*"
    - "qwen3*"
'''


def patch(path: Path) -> str:
    if not path.is_file():
        return f"skip missing {path}"
    text = path.read_text(encoding="utf-8")
    if '"qwen*"' in text:
        return f"ok already {path}"
    if OLD not in text:
        return f"FAIL block not found {path}"
    path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    return f"patched {path}"


def main() -> int:
    codes = []
    for p in CANDIDATES:
        msg = patch(p)
        print(msg)
        codes.append(msg.startswith("FAIL"))
    return 1 if any(codes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
