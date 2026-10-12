import os
import subprocess

import sup_paths

# 惰性解析: 导入期不得要求 praxist 存在，否则新克隆 / CI / worktree 无法收集测试。
_PRAXIST = None


def _resolve_praxist_bin() -> str:
    """Prefer repo .venv praxist; allow PRAXIST_BIN override."""
    candidates = [
        os.environ.get("PRAXIST_BIN"),
        os.path.join(sup_paths.FM_ROOT, ".venv", "bin", "praxist"),  # prefer repo venv
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError(
        "praxist binary not found (tried PRAXIST_BIN, %s); "
        "install repo .venv or set PRAXIST_BIN" % (sup_paths.FM_ROOT,)
    )


def _praxist_bin() -> str:
    global _PRAXIST
    if _PRAXIST is None:
        _PRAXIST = _resolve_praxist_bin()
    return _PRAXIST


def _load_dotenv(root=None, path=None):
    """Load .env.praxist into os.environ (only for keys not already set).

    Eliminates the dependency on shell `source .env.praxist` before startup.
    Existing env vars take precedence (explicit > file).
    `root` overrides FM_ROOT for dotenv lookup (used when --root is passed).
    Returns True if file was loaded, False if not found.
    """
    if path:
        p = path
    else:
        base = root or sup_paths.FM_ROOT
        p = os.path.join(base, ".env.praxist")
    if not os.path.isfile(p):
        return False
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("_"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            # M2: strip bash-compatible `export` prefix
            if key.startswith("export "):
                key = key[7:].strip()
            value = value.strip()
            # M1: strip inline comments (only for unquoted values)
            if value and not value.startswith(("'", '"')):
                comment_idx = value.find(" #")
                if comment_idx >= 0:
                    value = value[:comment_idx].rstrip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
    return True


def _check_required_env():
    """Fail-fast with clear error if required env vars are missing.

    Returns (missing_required, missing_recommended).
    """
    required = ["ANTHROPIC_API_KEY"]
    recommended = ["PRIMARY_MODEL", "ANTHROPIC_BASE_URL"]
    missing_req = [k for k in required if not os.environ.get(k)]
    missing_rec = [k for k in recommended if not os.environ.get(k)]
    return missing_req, missing_rec


def _praxist(args, env=None):
    r = subprocess.run([_praxist_bin(), *args], capture_output=True, text=True, env=env)
    return {"ok": r.returncode == 0, "stdout": r.stdout or "", "stderr": r.stderr or "", "rc": r.returncode}
