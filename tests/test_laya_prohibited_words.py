import re
import os
import pytest

PROHIBITED_PATTERNS = [
    r"(?:训练|进化|微调|优化)\s*Laya",
    r"Laya[^\n]{0,15}(?<!不)可学习",
    r"(?<!不)可学习[^\n]{0,15}Laya",
]

def scan_codebase_with_regex(patterns):
    violations = []
    repo_root = "/home/abug/timesfm"
    skip_files = {"test_laya_prohibited_words.py", "test_proposal_gate_plugin.py"}
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "node_modules", "__pycache__", "superpowers", ".omc"}]
        for fname in files:
            if fname in skip_files:
                continue
            if not fname.endswith((".py", ".md", ".jinja2", ".yaml", ".yml")):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        violations.append({"file": fpath, "pattern": pattern, "match": match.group()})
            except Exception:
                pass
    return violations

def test_no_laya_prohibited_words_in_codebase():
    violations = scan_codebase_with_regex(PROHIBITED_PATTERNS)
    assert len(violations) == 0, f"Found prohibited words: {violations}"
