import glob
import json
import os
import re
from datetime import datetime

import sup_env
import sup_paths
import sup_state

def parse_429_reset(log_text):
    m = re.search(r"reset at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})", log_text)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")

def _env_first(*names):
    """First non-empty env value among names (never log/echo secrets)."""
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return None


def _failover_configured() -> bool:
    """DashScope (or other) Anthropic-compatible failover ready?

    Accepts both FAILOVER_* and ANTHROPIC_FAILOVER_* names (launchers source .env.praxist).
    """
    base = _env_first("FAILOVER_ANTHROPIC_BASE_URL", "ANTHROPIC_FAILOVER_BASE_URL")
    key = _env_first(
        "FAILOVER_ANTHROPIC_API_KEY",
        "ANTHROPIC_FAILOVER_API_KEY",
        "FAILOVER_ANTHROPIC_AUTH_TOKEN",
    )
    return bool(base and key)


def _llm_provider(st=None) -> str:
    """Canonical state key is llm_provider; llm_route kept as read fallback."""
    st = st if st is not None else sup_state.load_state()
    route = (st.get("llm_provider") or st.get("llm_route") or "primary")
    route = str(route).strip().lower()
    return route if route in ("primary", "failover") else "primary"


# Back-compat alias used by older call sites / docs
def _llm_route(st=None) -> str:
    return _llm_provider(st)


def _praxist_env(route: str | None = None, st=None):
    """Build env for praxist child. Selects primary vs failover from state/route.

    Primary (default): Volcengine Ark via ANTHROPIC_* or PRIMARY_*.
    Failover: DashScope coding Anthropic endpoint via FAILOVER_* / ANTHROPIC_FAILOVER_*.
    """
    env = dict(os.environ)
    route = (route or _llm_provider(st)).strip().lower()
    if route == "failover" and _failover_configured():
        base = _env_first("FAILOVER_ANTHROPIC_BASE_URL", "ANTHROPIC_FAILOVER_BASE_URL")
        key = _env_first(
            "FAILOVER_ANTHROPIC_API_KEY",
            "ANTHROPIC_FAILOVER_API_KEY",
            "FAILOVER_ANTHROPIC_AUTH_TOKEN",
        )
        if base:
            env["ANTHROPIC_BASE_URL"] = base
        if key:
            env["ANTHROPIC_API_KEY"] = key
            env["ANTHROPIC_AUTH_TOKEN"] = key
        model = _env_first("FAILOVER_MODEL", "ANTHROPIC_FAILOVER_MODEL") or "kimi-k2.5"
        env["PRAXIST_FAILOVER_MODEL"] = model
        env["PRAXIST_MODEL"] = model  # praxist start resolves --model from PRAXIST_MODEL
        env["MODEL"] = model
    else:
        # Restore primary Ark endpoint/key when explicitly on primary.
        p_base = _env_first("PRIMARY_ANTHROPIC_BASE_URL", "ANTHROPIC_BASE_URL")
        p_key = _env_first(
            "PRIMARY_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
        )
        if p_base:
            env["ANTHROPIC_BASE_URL"] = p_base
        if p_key:
            env["ANTHROPIC_API_KEY"] = p_key
            env["ANTHROPIC_AUTH_TOKEN"] = p_key
        model = _env_first("PRIMARY_MODEL") or "kimi-k2.5"
        env["PRAXIST_MODEL"] = model
        env["MODEL"] = model
    # Claude Code prefers ANTHROPIC_AUTH_TOKEN over API_KEY. After route overlay,
    # force both to the SAME selected key so a stale primary AUTH_TOKEN cannot
    # ride into a DashScope failover process (401 invalid access token).
    key = env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN")
    if key:
        env["ANTHROPIC_API_KEY"] = key
        env["ANTHROPIC_AUTH_TOKEN"] = key
    volc_key = os.environ.get("VOLCENGINE_API_KEY")
    if volc_key:
        env["VOLCENGINE_API_KEY"] = volc_key
    # Sticky RUN_DIR from old shells/.env.praxist makes `praxist start`
    # try to reuse a finished non-empty dir (e.g. 11-57 SHUTDOWN). Drop it
    # so default/fresh starts allocate a new experiments/run_<ts>_… path.
    for sticky in ("RUN_DIR", "RUN", "RUNDIR", "PRAXIST_RUN_DIR"):
        env.pop(sticky, None)
    return env


def _failover_model_name() -> str:
    return _env_first("FAILOVER_MODEL", "ANTHROPIC_FAILOVER_MODEL") or "kimi-k2.5"


def _recorded_run_model(run_dir) -> str | None:
    """Read canonical --model from an existing run's startup_config.json."""
    if not run_dir:
        return None
    p = os.path.join(str(run_dir), "startup_config.json")
    try:
        data = json.loads(open(p, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    args = data.get("canonical_args") if isinstance(data, dict) else None
    if not isinstance(args, dict):
        return None
    model = str(args.get("model") or "").strip()
    return model or None


def _failover_can_resume_same_run(run_dir) -> bool:
    """Praxist resume rejects model identity changes.

    Only resume the same run_dir on failover when it already started with the
    failover model id. Otherwise start a fresh run (DashScope qwen ≠ Ark claude).
    """
    recorded = _recorded_run_model(run_dir)
    if not recorded:
        return False
    return recorded == _failover_model_name()


def _model_argv(route: str | None = None, st=None) -> list:
    """--model override for start/resume (primary: kimi-k2.5; failover: kimi-k2.5)."""
    route = (route or _llm_provider(st)).strip().lower()
    if route == "failover":
        return ["--model", _failover_model_name()]
    model = _env_first("PRIMARY_MODEL") or "kimi-k2.5"
    return ["--model", model]


def _provider_state(provider: str) -> dict:
    """Persist both llm_provider (canonical) and llm_route (compat)."""
    return {"llm_provider": provider, "llm_route": provider}


def _status_rows():
    r = sup_env._praxist(["status", "--json"])
    try:
        data = json.loads(r["stdout"] or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []

def _run_active():
    return any((row or {}).get("state") in {"running", "starting"} for row in _status_rows())

def _active_run_meta():
    for row in _status_rows():
        if (row or {}).get("state") in {"running", "starting"}:
            return row
    return None

def _latest_429_reset():
    logs = sorted(glob.glob(os.path.join(sup_paths.FM_ROOT, "task_FM", "experiments", "run_*", "logs", "*.log")),
                  key=os.path.getmtime, reverse=True)
    for lp in logs[:5]:
        try:
            reset = parse_429_reset(open(lp, encoding="utf-8", errors="ignore").read())
        except OSError:
            continue
        if reset:
            return reset
    return None
