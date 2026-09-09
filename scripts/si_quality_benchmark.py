#!/usr/bin/env python3
"""SEALED self-improve quality benchmark for the TimesFM praxist system.

Hard gate (primary=0.0 and exit non-zero if any fails):
  1. py_compile on the key trading modules.
  2. pytest suite passes:  pytest tests/ -q -p no:cacheprovider -m "not slow"

Soft score (only used as primary when the hard gate passes):
  start at 1.0 and subtract deterministic, static penalties over the Python
  sources under scripts/ and cascade/ (plus tracked scripts/docs/shell for the
  version-consistency check). Nothing here imports the trading modules (they
  need torch); it is regex/AST over file text only -> deterministic, offline.

Last line of stdout is a JSON object. Exit 0 on a scored run (even if the
score is <1); exit non-zero only on hard-gate failure or an internal error.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- hard gate inputs -------------------------------------------------------
COMPILE_MODULES = [
    "scripts/praxist_supervisor.py",
    "scripts/aligned_slow_loop.py",
    "cascade/features.py",
    "cascade/daily_model.py",
    "cascade/hourly_model.py",
    "scripts/monthly_backtest.py",
    "task_FM/evaluations/fm_eval/evaluator.py",
]
PYTEST_ARGS = ["tests/", "-q", "-p", "no:cacheprovider", "-m", "not slow"]
PYTEST_TIMEOUT = 240  # seconds; suite is ~15s, generous ceiling for the 3-min budget

# --- soft score tuning ------------------------------------------------------
BARE_EXCEPT_UNIT = 0.08
BARE_EXCEPT_CAP = 0.40
VENV_UNIT = 0.05
VENV_CAP = 0.20
MONITOR_UNIT = 0.05
MONITOR_CAP = 0.15

MONITOR_FILES = [
    "scripts/praxist_supervisor.py",
    "scripts/aligned_slow_loop.py",
    "scripts/monthly_backtest.py",
]

# extensions treated as "tracked scripts / docs / shell" for the venv scan
VENV_EXTENSIONS = {
    ".py", ".sh", ".bash", ".ps1", ".bat", ".cmd",
    ".md", ".rst", ".txt", ".yaml", ".yml",
}
VENV_EXCLUDE_PREFIXES = (".omc/",)
SELF_PATH = "scripts/si_quality_benchmark.py"

# regex: a standalone ".venv" directory token (never matches ".praxist-venv",
# which does not even contain the substring ".venv").
_VENV_RE = re.compile(r"(?<![\w.-])\.venv(?![\w-])")
_PRINT_RE = re.compile(r"\bprint\s*\(")
_IMPORT_LOGGING_RE = re.compile(r"(?m)^\s*import\s+logging\b")
_FROM_LOGGING_RE = re.compile(r"(?m)^\s*from\s+logging\b")
_EMIT_DEF_RE = re.compile(r"def\s+\w*emit\w*\s*\(")


def log(msg: str) -> None:
    """Diagnostics go to stderr so the JSON line is always the last stdout line."""
    print(msg, file=sys.stderr, flush=True)


def run_compile() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", *COMPILE_MODULES],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()


def run_pytest() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *PYTEST_ARGS],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, f"pytest timed out after {PYTEST_TIMEOUT}s"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()


# --- static analysis --------------------------------------------------------
def _caught_exc_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Attribute):
        names.add(node.attr)
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            names |= _caught_exc_names(elt)
    return names


def _handler_is_pass_only(handler: ast.ExceptHandler) -> bool:
    body = list(handler.body)
    return bool(body) and all(isinstance(s, ast.Pass) for s in body)


def count_silent_exceptions(py_files: list[Path]) -> int:
    """Count bare `except:` clauses plus `except Exception...:` that only `pass`."""
    total = 0
    for path in py_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=str(path))
        except (SyntaxError, ValueError, OSError):
            # A file that does not parse would already fail the compile gate;
            # skip it here rather than double-counting.
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                total += 1  # bare except:
                continue
            names = _caught_exc_names(node.type)
            if ("Exception" in names or "BaseException" in names) and _handler_is_pass_only(node):
                total += 1  # silent swallow
    return total


def git_tracked_files() -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def count_venv_refs() -> int:
    tracked = git_tracked_files()
    if tracked is None:
        log("WARNING: git ls-files unavailable; falling back to scripts/cascade/docs walk")
        candidates = []
        for base in ("scripts", "cascade", "docs"):
            base_dir = REPO / base
            if base_dir.exists():
                candidates += [p for p in base_dir.rglob("*") if p.is_file()]
        rels = [str(p.relative_to(REPO)).replace("\\", "/") for p in candidates]
    else:
        rels = tracked

    total = 0
    for rel in sorted(rels):
        if rel in (SELF_PATH,):
            continue
        if any(rel.startswith(prefix) for prefix in VENV_EXCLUDE_PREFIXES):
            continue
        if "/.venv/" in rel or "/.praxist-venv/" in rel or rel.startswith(".venv/"):
            continue
        ext = Path(rel).suffix.lower()
        if ext not in VENV_EXTENSIONS:
            continue
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _VENV_RE.finditer(text):
            # defensive: never count the canonical praxist venv
            preceding = text[max(0, m.start() - 8):m.start()]
            if preceding.endswith("praxist-"):
                continue
            total += 1
    return total


def python_scope_files() -> list[Path]:
    files: list[Path] = []
    for base in ("scripts", "cascade"):
        base_dir = REPO / base
        if not base_dir.exists():
            continue
        for p in base_dir.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.name == "si_quality_benchmark.py":
                continue
            files.append(p)
    return sorted(files)


def evaluate_monitoring() -> tuple[int, list[str]]:
    """Return (penalized_count, monitored_files)."""
    monitored: list[str] = []
    penalized = 0
    for rel in MONITOR_FILES:
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        has_logging = bool(
            _IMPORT_LOGGING_RE.search(text)
            or _FROM_LOGGING_RE.search(text)
            or ("logging.getLogger" in text)
        )
        has_emit = ("_emit_event" in text) or bool(_EMIT_DEF_RE.search(text))
        uses_print = bool(_PRINT_RE.search(text))
        if has_logging or has_emit:
            monitored.append(rel)
        elif uses_print:
            penalized += 1
    return penalized, sorted(monitored)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def main() -> int:
    log(f"[bench] repo={REPO} python={sys.executable}")

    # ---- hard gate ----
    compile_ok, compile_out = run_compile()
    log(f"[bench] py_compile: {'PASS' if compile_ok else 'FAIL'}")
    if not compile_ok:
        log(compile_out[-2000:])

    tests_pass, test_out = run_pytest()
    tail = "\n".join(test_out.splitlines()[-15:])
    log(f"[bench] pytest (-m 'not slow'): {'PASS' if tests_pass else 'FAIL'}")
    log(tail)

    gate_ok = compile_ok and tests_pass

    # ---- static soft-score analysis (always computed; reported regardless) ----
    py_files = python_scope_files()
    log(f"[bench] scanning {len(py_files)} python files under scripts/ + cascade/")
    bare_count = count_silent_exceptions(py_files)
    bare_penalty = min(BARE_EXCEPT_CAP, BARE_EXCEPT_UNIT * bare_count)

    venv_refs = count_venv_refs()
    venv_penalty = min(VENV_CAP, VENV_UNIT * venv_refs)

    mon_penalized, monitored = evaluate_monitoring()
    mon_penalty = min(MONITOR_CAP, MONITOR_UNIT * mon_penalized)

    soft = clamp(1.0 - bare_penalty - venv_penalty - mon_penalty)

    primary = round(soft, 6) if gate_ok else 0.0
    result = {
        "primary": primary,
        "sub_scores": {
            "compile": 1 if compile_ok else 0,
            "tests_pass": 1 if tests_pass else 0,
            "bare_except_penalty": round(bare_penalty, 6),
            "version_penalty": round(venv_penalty, 6),
            "monitoring_penalty": round(mon_penalty, 6),
        },
        "details": {
            "bare_except_count": bare_count,
            "venv_refs": venv_refs,
            "monitored": monitored,
            "monitoring_penalized": mon_penalized,
            "soft_score_if_gate_passes": round(soft, 6),
        },
    }
    log(
        "[bench] bare_except=%d (pen %.2f) venv_refs=%d (pen %.2f) "
        "monitor_penalized=%d (pen %.2f) soft=%.4f gate=%s"
        % (bare_count, bare_penalty, venv_refs, venv_penalty,
           mon_penalized, mon_penalty, soft, "PASS" if gate_ok else "FAIL")
    )

    print(json.dumps(result, sort_keys=False))
    return 0 if gate_ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # internal error -> non-zero, still emit JSON
        import traceback
        traceback.print_exc()
        print(json.dumps({
            "primary": 0.0,
            "sub_scores": {
                "compile": 0, "tests_pass": 0,
                "bare_except_penalty": 0.0, "version_penalty": 0.0,
                "monitoring_penalty": 0.0,
            },
            "details": {"error": f"{type(exc).__name__}: {exc}"},
        }))
        sys.exit(2)
