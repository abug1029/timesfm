#!/usr/bin/env python3
"""三环监督环: goal 判定 + 两环调度, 纯 Python 0 token"""
import argparse, atexit, fcntl, glob, json, os, re, signal, subprocess, sys, threading, time, traceback, uuid
from datetime import datetime, timedelta
import yaml
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
import registry_lib as rl
from goal_dsl import evaluate_goal
from cascade.cov_family import ALLOWED_FAMILIES
try:
    from cascade.statistical_tests import bh_fdr_promote
except ImportError:
    bh_fdr_promote = None

def _resolve_praxist_bin() -> str:
    """Prefer repo .venv praxist; allow PRAXIST_BIN override."""
    candidates = [
        os.environ.get("PRAXIST_BIN"),
        os.path.join(FM_ROOT, ".venv", "bin", "praxist"),  # prefer repo venv
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError(
        "praxist binary not found (tried PRAXIST_BIN, %s); "
        "install repo .venv or set PRAXIST_BIN" % (FM_ROOT,)
    )

PRAXIST = _resolve_praxist_bin()
QUEUE = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl")
INPROGRESS = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl")
REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")
STATE_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_state.json")
LOCK_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor.lock")
VERDICTS_INC = os.path.join(FM_ROOT, "task_FM", "known_verdicts.inc.md")
POOL_PATH = os.path.join(FM_ROOT, "task_FM", "config", "covariate_pool.json")
BACKLOG_PATH = os.path.join(FM_ROOT, "task_FM", "config", "covariate_backlog.jsonl")
SYMBOL_STATUS_PATH = os.path.join(FM_ROOT, "task_FM", "config", "symbol_status.json")
MENU_INC = os.path.join(FM_ROOT, "task_FM", "covariate_menu.inc.md")
REPORT_DIR = os.path.join(FM_ROOT, "docs", "superpowers", "reports")


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
        base = root or FM_ROOT
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

STATE_MD = os.path.join(FM_ROOT, "STATE.md")
EVENTS_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_events.jsonl")
HEARTBEAT_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_heartbeat")
STOP_REPORT_JSON = os.path.join(FM_ROOT, "data", "cache", "stop_report.json")
_EVENT_LOCK = threading.Lock()
_SHUTDOWN_REQUESTED = False
_RUN_ID = uuid.uuid4().hex[:12]
_START_TIME = time.time()
_STOP_EMITTED = False
POLL_S = 300
PHASES = ("fast", "slow", "wait_quota")
# v1 遗留复测触发判据 (RETEST_GATE_N=350, RETEST_GATE_IC=0.05)；非 v23 gate 镜像
# （v23 口径见 docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md）。
# 宿主侧仅用于识别"仅差样本"的近失误裁决并安排复测，不改变慢环硬门本身。
RETEST_GATE_N = 350
RETEST_GATE_IC = 0.05
RETEST_PF_RATIO = 1.05

with open(os.path.join(FM_ROOT, "config", "knowledge_base.json"), encoding="utf-8") as _f:
    _kb = json.load(_f)
INCUMBENT_PF = {sym: float(rec["historical_pf"])
                for sym, rec in _kb["symbols"].items()
                if rec.get("historical_pf") is not None}
if not INCUMBENT_PF:
    print("[degraded] KB PF all null (schemes_snapshot_no_L1): "
          "retest PF ratio gate denominator falls back to 1.0",
          file=sys.stderr)



def _now_iso():
    return datetime.now().isoformat()

def _mark_stop_emitted():
    global _STOP_EMITTED
    _STOP_EMITTED = True


# ── Event monitoring system ──────────────────────────────────

def _emit_event(level, event, data=None, **extra):
    """Append a structured event to the events JSONL.

    Thread-safe via _EVENT_LOCK. On write failure, falls back to stderr.
    Never raises — monitoring must not crash the supervisor.
    """
    rec = {
        "ts": _now_iso(),
        "schema_version": 1,
        "run_id": _RUN_ID,
        "pid": os.getpid(),
        "level": level,
        "event": event,
        "data": data or {},
    }
    rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False, default=str)
    try:
        os.makedirs(os.path.dirname(EVENTS_PATH), exist_ok=True)
        with _EVENT_LOCK:
            with open(EVENTS_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
    except OSError as e:
        print(f"[EVENT_FALLBACK] {line}", file=sys.stderr)
    if event == "supervisor_stopped":
        _mark_stop_emitted()
        _write_stop_json(rec)


def _write_stop_json(event_rec):
    """Write a timestamped stop report JSON (keeps history)."""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.dirname(STOP_REPORT_JSON),
                            f"stop_report_{ts}.json")
        report = {
            "ts": _now_iso(),
            "run_id": _RUN_ID,
            "pid": os.getpid(),
            "uptime_s": round(time.time() - _START_TIME, 1),
            "event": event_rec.get("event"),
            "data": event_rec.get("data", {}),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        with open(STOP_REPORT_JSON, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[STOP_REPORT_ERROR] {e}", file=sys.stderr)


def _write_heartbeat():
    """Write heartbeat timestamp. Called each main loop iteration."""
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
        with open(HEARTBEAT_PATH, "w") as f:
            f.write(json.dumps({"ts": _now_iso(), "run_id": _RUN_ID,
                                "pid": os.getpid()}))
    except OSError as e:
        print(f"[WARN] Failed to write heartbeat: {e}", file=sys.stderr)


def _signal_handler(signum, frame):
    """Signal handler: set flag only, no I/O. Main loop detects and emits event."""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True


def _atexit_handler():
    """Emit stop event on any exit path not already handled."""
    global _STOP_EMITTED
    if _STOP_EMITTED:
        return
    if os.path.exists(STOP_REPORT_JSON):
        try:
            existing = json.load(open(STOP_REPORT_JSON, encoding="utf-8"))
            if existing.get("run_id") == _RUN_ID:
                return
        except (OSError, json.JSONDecodeError):
            pass
    # atexit 兜底只在未覆盖的退出(未捕获异常等; CPython 此类退出码=1)触发。
    # 干净退出(goal_reached/budget_exhausted/dry-run/one-shot/signal)已先 _mark_stop_emitted()。
    # 历史 bug: getattr(sys,"exitcode",1) 中 sys.exitcode 并非标准属性, hasattr 恒 False,
    # 导致任何干净退出在漏标时都被记 exit_code=1。
    _emit_event("critical", "supervisor_stopped", {
        "reason": "unexpected_exit",
        "exit_code": 1,
        "uptime_s": round(time.time() - _START_TIME, 1),
    })


# Signal/atexit handlers are armed only when main() actually runs the supervisor.
# 历史 bug: 这些在 import 时注册, 导致仅把本模块当库 import 的只读脚本/测试
# (调 harvest_proposals/build_snapshot 等) 退出时被 atexit 误报 unexpected_exit。
_HANDLERS_ARMED = False

def _arm_handlers():
    global _HANDLERS_ARMED
    if _HANDLERS_ARMED:
        return
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_atexit_handler)
    _HANDLERS_ARMED = True


def parse_429_reset(log_text):
    m = re.search(r"reset at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})", log_text)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")

def load_state():
    if not os.path.exists(STATE_PATH):
        st = {"cycles_done": 0, "last_run_dir": None, "last_run_id": None,
              "last_harvested_run_id": None, "paused_429": False, "phase": "fast",
              "llm_provider": "primary", "llm_route": "primary"}
    else:
        try:
            st = json.load(open(STATE_PATH, encoding="utf-8"))
        except Exception:
            st = {"cycles_done": 0}
    return _ensure_tokens_baseline(st)

def save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)

def load_goal(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["goal"]

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
    st = st if st is not None else load_state()
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
        model = _env_first("FAILOVER_MODEL", "ANTHROPIC_FAILOVER_MODEL") or "qwen3.7-plus"
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
        model = _env_first("PRIMARY_MODEL") or "claude-opus-4-7"
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
    return _env_first("FAILOVER_MODEL", "ANTHROPIC_FAILOVER_MODEL") or "qwen3.7-plus"


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
    """--model override for start/resume (primary: claude-opus-4-7; failover: qwen3.7-plus)."""
    route = (route or _llm_provider(st)).strip().lower()
    if route == "failover":
        return ["--model", _failover_model_name()]
    model = _env_first("PRIMARY_MODEL") or "claude-opus-4-7"
    return ["--model", model]


def _provider_state(provider: str) -> dict:
    """Persist both llm_provider (canonical) and llm_route (compat)."""
    return {"llm_provider": provider, "llm_route": provider}


def _praxist(args, env=None):
    r = subprocess.run([PRAXIST, *args], capture_output=True, text=True, env=env)
    return {"ok": r.returncode == 0, "stdout": r.stdout or "", "stderr": r.stderr or "", "rc": r.returncode}

def _status_rows():
    r = _praxist(["status", "--json"])
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
    logs = sorted(glob.glob(os.path.join(FM_ROOT, "task_FM", "experiments", "run_*", "logs", "*.log")),
                  key=os.path.getmtime, reverse=True)
    for lp in logs[:5]:
        try:
            reset = parse_429_reset(open(lp, encoding="utf-8", errors="ignore").read())
        except OSError:
            continue
        if reset:
            return reset
    return None

def quota_gate(goal, now=None):
    """return (window_ok, sleep_seconds_if_blocked). Windows refill at reset+N*win_h."""
    cad = goal.get("cadence") or {}
    run_h = float(cad.get("run_budget_hours", 2.0))
    win_h = float(cad.get("quota_window_hours", 5.0))
    margin_h = float(cad.get("quota_margin_min", 30)) / 60.0
    need = run_h + margin_h
    reset = _latest_429_reset()
    if reset is None:
        return True, 0
    now = now or datetime.now(reset.tzinfo)
    if now.tzinfo is None and reset.tzinfo is not None:
        now = now.replace(tzinfo=reset.tzinfo)
    elif now.tzinfo is not None and reset.tzinfo is None:
        reset = reset.replace(tzinfo=now.tzinfo)
    if now < reset:
        return False, max(1, int((reset - now).total_seconds()))
    win = timedelta(hours=win_h)
    n = (now - reset) // win
    window_start = reset + n * win
    remaining_h = (win - (now - window_start)).total_seconds() / 3600.0
    if remaining_h >= need:
        return True, 0
    next_reset = window_start + win
    return False, max(1, int((next_reset - now).total_seconds()))

def build_snapshot(registry_path, cycles_done, cpu_hours_used, tokens_used_m):
    snap = rl.load_snapshot(registry_path)
    passing = rl.pass_variants(snap)
    symbols_hit = {v["symbol"] for v in passing}
    families_hit = {
        v.get("cov_family")
        for v in passing
        if v.get("cov_family")
        and v.get("cov_family") != "unknown"
    } & ALLOWED_FAMILIES
    n_one_star_symbols_hit = len(symbols_hit & GOAL_SYMBOLS_SET)
    n_unique_pass_variants = len({v["variant_id"] for v in passing})
    n_families_hit = len(families_hit)
    # v23: v2 过门变体的 min dir_acc (pass_variants = gate_pass 且 (fdr_pass 或 migrated_pass);
    # v1 legacy: gate_pass 且 ev>0);
    # 无过门变体 (或无数值 dir_acc) 时为 None, goal 条件用 is not None 防护判 unmet 而非 eval error。
    pass_dir_accs = [float(v["dir_acc"]) for v in passing
                     if isinstance(v.get("dir_acc"), (int, float))]
    min_pass_variant_dir_acc = min(pass_dir_accs) if pass_dir_accs else None
    return {
        "variants": snap,
        "symbols_hit": symbols_hit,
        "families_hit": families_hit,
        "cycles_done": cycles_done,
        "cpu_hours_used": cpu_hours_used,
        "tokens_used_m": tokens_used_m,
        "n_one_star_symbols_hit": n_one_star_symbols_hit,
        "n_unique_pass_variants": n_unique_pass_variants,
        "n_families_hit": n_families_hit,
        "min_pass_variant_dir_acc": min_pass_variant_dir_acc,
    }

def harvest_survivors(root, snapshot, dead, existing, top_k, aligned_max_points=600):
    """Pick up to top_k diagnostic survivors, preferring symbol×cov diversity.

    Ranking is by diagnostic dir_acc, but we fill seats in passes:
      1) unique symbols (avoid 3× same symbol)
      2) remaining by dir_acc (different cov on a seen symbol is OK)
    """
    out = []
    seen = set()
    passing_ids = {v["variant_id"] for v in rl.pass_variants(snapshot or {})}
    run_dirs = sorted(glob.glob(os.path.join(root, "task_FM", "experiments", "run_*")),
                      key=os.path.getmtime, reverse=True)
    for run_dir in run_dirs:
        for sp in glob.glob(os.path.join(run_dir, "results", "**", "evaluation_summary.json"),
                            recursive=True):
            try:
                d = json.load(open(sp, encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or d.get("stage") != "diagnostic":
                continue
            metrics = d.get("metrics") or {}
            dir_acc = float(metrics.get("dir_acc") or d.get("dir_acc") or 0.0)
            if dir_acc < 0.50:
                continue
            try:
                symbol = d["symbol"].lower()
                cov = d["cov_override"]
            except KeyError:
                continue
            vid = f"{symbol}_{cov}"
            if vid in dead or vid in existing or vid in passing_ids or vid in seen:
                continue
            seen.add(vid)
            out.append({"variant_id": vid, "symbol": symbol, "cov_override": cov,
                        "max_points": int(aligned_max_points),
                        "stage": "aligned", "checkpoint_path": "",
                        "enqueued_at": _now_iso(), "src_run": os.path.basename(run_dir),
                        "_dir_acc": dir_acc})
    out.sort(key=lambda r: -r["_dir_acc"])
    selected = []
    used_symbols = set()
    for r in out:
        if len(selected) >= int(top_k):
            break
        if r["symbol"] in used_symbols:
            continue
        selected.append(r)
        used_symbols.add(r["symbol"])
    if len(selected) < int(top_k):
        selected_ids = {r["variant_id"] for r in selected}
        for r in out:
            if len(selected) >= int(top_k):
                break
            if r["variant_id"] in selected_ids:
                continue
            selected.append(r)
            selected_ids.add(r["variant_id"])
    for r in selected:
        r.pop("_dir_acc", None)
    return selected

def collect_proposed_variant_ids(root=None):
    """Parse results/**/proposals/*.json into {symbol_cov}."""
    root = root or FM_ROOT
    out = set()
    pattern = os.path.join(root, "task_FM", "experiments", "run_*", "results",
                           "**", "proposals", "*.json")
    for sp in glob.glob(pattern, recursive=True):
        try:
            with open(sp, encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            continue
        if not isinstance(p, dict):
            continue
        symbol = str(p.get("symbol") or "").lower().strip()
        cov = str(p.get("cov_override") or "").strip()
        if symbol and cov:
            out.add("%s_%s" % (symbol, cov))
    return out


def materialize_known_verdicts(snapshot, dest_path, *, proposed_ids=None,
                               status_map=None, queue_ids=None, root=None):
    if status_map is None:
        status_map = load_symbol_status()
    if queue_ids is None:
        queue_ids = rl.in_flight_ids(QUEUE, INPROGRESS)
    if proposed_ids is None:
        proposed_ids = collect_proposed_variant_ids(root or FM_ROOT)

    lines = ["## Known aligned verdicts (supervisor snapshot)",
             "v2 pass (gate_pass=True AND (fdr_pass OR migrated_pass)): already solved, do NOT re-propose.",
             "v1 legacy: pass by ev>0 (legacy econ caliber, schema=v1 entries only).",
             "hard-gate-but-losing (gate_pass=True but not (fdr_pass or migrated_pass)): 过硬门但未过 v23 统计检验; not a success; do not re-propose as solved.",
             "DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.",
             ""]
    items = list(snapshot.values()) if isinstance(snapshot, dict) else []

    # ## Symbol status (full GOAL_SYMBOLS_SET, never truncated)
    lines.append("## Symbol status")
    for sym in sorted(GOAL_SYMBOLS_SET):
        n_ok = 0
        n_pass = 0
        best = None
        for v in items:
            if str(v.get("symbol") or "").lower() != sym:
                continue
            if v.get("status", "ok") == "ok":
                n_ok += 1
            if v.get("gate_pass"):
                n_pass += 1
            da = v.get("dir_acc")
            if isinstance(da, (int, float)) and not isinstance(da, bool):
                da = float(da)
                if da == da and -1e308 < da < 1e308:
                    if best is None or da > best:
                        best = da
        rec = status_map.get(sym) or {}
        st = str(rec.get("status") or "ACTIVE").upper()
        if st == "DEAD":
            label = "SYMBOL_DEAD"
        elif st == "HOLD":
            label = "HOLD"
        else:
            label = "ACTIVE"
        best_s = ("%.3f" % best) if best is not None else "n/a"
        line = "- %s: %s, n_ok=%d, n_pass=%d, best=%s" % (
            sym, label, n_ok, n_pass, best_s)
        reason = rec.get("reason")
        if reason:
            line += " — %s" % reason
        if st == "DEAD":
            line += " — 不要提案"
        elif st == "HOLD":
            hg = rec.get("hold_generations")
            if hg is not None:
                line += " — 暂停 %s 代" % hg
        lines.append(line)
    lines.append("")
    lines.extend(_effective_clue_lines(items))

    # ## Do not re-propose; source priority: verdict > queue > proposed
    lines.append("## Do not re-propose (variant_id)")
    tagged = {}
    for vid in (proposed_ids or set()):
        tagged[str(vid)] = "proposed"
    for vid in (queue_ids or set()):
        tagged[str(vid)] = "queue"
    if isinstance(snapshot, dict):
        for vid in snapshot.keys():
            tagged[str(vid)] = "verdict"
    all_vids = sorted(tagged.keys())
    total = len(all_vids)
    for vid in all_vids[:80]:
        lines.append("- %s (%s)" % (vid, tagged[vid]))
    if total > 80:
        lines.append("truncated=%d" % total)
    lines.append("")

    def _da_key(v):
        da = v.get("dir_acc")
        # v23: 排序键 dir_acc 降序, 数值缺失排最后; ev 仅作展示列
        return -(float(da) if isinstance(da, (int, float)) else float("-inf"))

    items.sort(key=lambda v: (not v.get("gate_pass", False), _da_key(v)))
    if not items:
        lines.append("(no aligned verdicts yet)")
    for v in items[:20]:
        gate = bool(v.get("gate_pass", False))
        ev = float(v.get("ev") or 0)
        status = v.get("status", "ok")
        v2 = v.get("schema") == "fm.aligned_verdict.v2"
        promoted = (bool(v.get("fdr_pass")) or bool(v.get("migrated_pass"))) if v2 else (ev > 0)
        if gate and promoted:
            state = "v2_pass" if v2 else "v1_legacy_pass"
        elif gate:
            state = "hard-gate-but-losing"
        elif status == "ok":
            state = "DEAD"
        else:
            state = status
        lines.append("- {0}: {1}, gate_pass={2}, ev={3}, n={4}, status={5}".format(
            v.get("variant_id"), state, v.get("gate_pass"), v.get("ev"),
            v.get("n"), status))
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines) + '\n')


def _verdict_family(v):
    fam = str(v.get("cov_family") or "").strip()
    return fam or str(v.get("cov_override") or "").strip()


def _finite_dir_acc(v):
    da = v.get("dir_acc")
    if isinstance(da, (int, float)) and not isinstance(da, bool):
        da = float(da)
        if da == da and -1e308 < da < 1e308:
            return da
    return None


def _has_prior_failure(snapshot, symbol, cov):
    """True if snapshot has an ok+unpassed verdict on this symbol or this cov."""
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if v.get("status", "ok") != "ok" or v.get("gate_pass"):
            continue
        if str(v.get("symbol") or "").lower() == str(symbol).lower():
            return True
        if str(v.get("cov_override") or "") == cov:
            return True
    return False


def _effective_clue_lines(items):
    """Live passing / near-miss / weak-family clues. Never a frozen menu."""
    fam_ok = {}
    fam_pass = {}
    near = []
    for v in items:
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        fam = _verdict_family(v)
        if fam:
            fam_ok[fam] = fam_ok.get(fam, 0) + 1
            if v.get("gate_pass"):
                fam_pass[fam] = fam_pass.get(fam, 0) + 1
        da = _finite_dir_acc(v)
        if da is None or v.get("gate_pass"):
            continue
        emin = v.get("effective_min")
        if not (isinstance(emin, (int, float)) and not isinstance(emin, bool)):
            emin = 0.52
        else:
            emin = float(emin)
        if 0.49 <= da < emin:
            near.append((v.get("variant_id"), da, emin))
    lines = ["## Effective clues (from snapshot, not a frozen menu)",
             "### Passing families"]
    passing = [(fam, fam_pass[fam]) for fam in fam_pass if fam_pass[fam] > 0]
    passing.sort(key=lambda x: (-x[1], x[0]))
    if passing:
        for fam, n in passing:
            lines.append("- %s: %d gate_pass" % (fam, n))
    else:
        lines.append("- (none yet)")
    lines.append("### Near-miss (0.49 <= dir_acc < effective_min)")
    if near:
        near.sort(key=lambda x: -x[1])
        for vid, da, emin in near[:12]:
            lines.append("- %s dir_acc=%.3f min=%.3f" % (vid, da, emin))
    else:
        lines.append("- (none)")
    lines.append("### Weak families (>=4 ok, 0 pass)")
    weak = [fam for fam, n in fam_ok.items()
            if n >= 4 and fam_pass.get(fam, 0) == 0]
    weak.sort()
    if weak:
        for fam in weak:
            lines.append("- %s: %d ok, 0 pass — 不要为凑探索而提，除非有 failure_delta"
                         % (fam, fam_ok[fam]))
    else:
        lines.append("- (none)")
    lines.append("")
    return lines


def load_covariate_pool():
    """读协变量池 covariate_pool.json → cov dict。fail-open 返回 {}。"""
    try:
        with open(POOL_PATH, encoding="utf-8") as f:
            return (json.load(f) or {}).get("covariates", {})
    except Exception as e:
        print("[WARN] covariate pool load failed (fail-open): %s" % e, file=sys.stderr)
        return {}


def load_symbol_status(path=None):
    """Return {symbol: {"status": "DEAD"|"HOLD"|"ACTIVE", ...}}. Missing file -> {}."""
    p = path or SYMBOL_STATUS_PATH
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f) or {}
        out = {}
        for sym, rec in (raw.get("symbols") or {}).items():
            if not isinstance(rec, dict):
                continue
            st = str(rec.get("status") or "ACTIVE").upper()
            if st in ("DEAD", "HOLD", "ACTIVE"):
                out[str(sym).lower()] = rec
        return out
    except Exception as e:
        print("[WARN] symbol_status load failed (fail-open): %s" % e, file=sys.stderr)
        return {}

def _load_evaluator():
    """惰性导入 evaluator (仅 json/os/AST, 无 torch) 复用 active/archived/symbol 校验。"""
    try:
        p = os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval")
        if p not in sys.path:
            sys.path.insert(0, p)
        import evaluator as ev
        return ev
    except Exception as e:
        print("[WARN] evaluator import failed in supervisor: %s" % e, file=sys.stderr)
        return None

# ── v2 预注册宇宙 (evaluator 预注册品种) ──────────────────────────
_ev_mod_for_goal = _load_evaluator()
# 8 个信用品种 (1★ 过门目标); 不跟随 evaluator.ALLOWED_SYMBOLS 膨胀
GOAL_SYMBOLS_SET = frozenset({"m", "ss", "sr", "cj", "jd", "lh", "eg", "rb"})
del _ev_mod_for_goal



def _cross_run_repeat_counts(root=None, max_runs=20):
    """Count how many runs each variant_id appears in (shared_findings).

    Returns {variant_name: run_count}. Used for repeat-offender penalty.
    Scans at most `max_runs` most recent runs to bound cost.
    """
    base = root or FM_ROOT
    runs_dir = os.path.join(base, "task_FM", "experiments")
    if not os.path.isdir(runs_dir):
        return {}
    # Most recent N runs
    run_dirs = sorted(glob.glob(os.path.join(runs_dir, "run_*")),
                      key=os.path.getmtime, reverse=True)[:max_runs]
    counts = {}
    for rd in run_dirs:
        sf_dir = os.path.join(rd, "shared_findings")
        if not os.path.isdir(sf_dir):
            continue
        seen_in_run = set()
        for f in glob.glob(os.path.join(sf_dir, "*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
                # variant_name is the symbol_cov key
                vn = d.get("variant_name") or ""
                if not vn:
                    title = d.get("title", "")
                    vn = title.split(":")[0].strip() if ":" in title else ""
                if vn:
                    seen_in_run.add(vn)
            except (OSError, json.JSONDecodeError):
                continue
        for vn in seen_in_run:
            counts[vn] = counts.get(vn, 0) + 1
    return counts


def _dead_families(snapshot, min_ok=4):
    """Return set of family names with >= min_ok ok verdicts and 0 pass.

    These families are considered DEAD: no amount of re-proposing will help
    without a fundamental mechanism change.
    """
    fam_ok = {}
    fam_pass = {}
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        fam = str(v.get("cov_family") or "").strip()
        if not fam:
            continue
        fam_ok[fam] = fam_ok.get(fam, 0) + 1
        if v.get("gate_pass"):
            fam_pass[fam] = fam_pass.get(fam, 0) + 1
    return {fam for fam, n in fam_ok.items()
            if n >= min_ok and fam_pass.get(fam, 0) == 0}


def _proposal_priority_score(prop, cov, symbol, snapshot, status_map=None, repeat_counts=None):
    """机制化排序 (替代噪声小样本 EV)。确定性可复现。
    1) 协变量履历 (v23 口径): 同 cov 任一品种 (含自身; 生产经历史去重同 vid
       不可达) gate_pass=True 时, dir_acc 超过硬门 0.52 的部分 x200 加分。
       gate_pass 门槛为有意校准: 过硬门未过 FDR 的高 dir_acc 仍视为有意义信号
       (v23 完整 pass 定义见 registry_lib.pass_variants, 更严)。评审 M-1 登记。
       NaN/inf/bool dir_acc 一律不计入。
    2) 机制完备度: symbol_fit/kill/promote 齐全加分
    3) 新颖性: 未测组合加分 +5 (2026-09-17 探索偏置调整, 原 +2)
    4) 探索分: 协变量开发度 —— 该 cov 累计 ok verdicts 越少加分越高
       (0 个 +6 / 1 个 +4 / 2 个 +2 / >=3 个 0), 对冲履历分的利用偏置。
       平衡点 (可达路径: 已测 1 次 + 新组合有新颖分): 其他品种
       dir_acc > 0.53 的真履历胜过全新组合。评审 M-2 修正 (原误写 0.555)。
    5) 过门族迁移: 提案带 covariate_family 且该族在其他品种有 gate_pass 时 +8
       (压过全新 cov 的探索 +6)。
    6) 弱族: 同 cov_family ≥4 条 ok 且 0 过门时 -8。
    """
    score = 0.0
    n_cov_ok = 0
    for v in (snapshot or {}).values():
        if v.get("cov_override") == cov and v.get("status", "ok") == "ok":
            n_cov_ok += 1
            da = v.get("dir_acc")
            if v.get("gate_pass") and isinstance(da, (int, float)) and not isinstance(da, bool):
                da = float(da)
                if da == da and -1e308 < da < 1e308:
                    score += max(0.0, da - 0.52) * 200.0
    for key in ("symbol_fit", "kill_condition", "promote_condition"):
        if str(prop.get(key) or "").strip():
            score += 1.0
    if "%s_%s" % (symbol, cov) not in (snapshot or {}):
        score += 5.0
    score += {0: 6.0, 1: 4.0, 2: 2.0}.get(n_cov_ok, 0.0)
    n_fail = 0
    for v in (snapshot or {}).values():
        if v.get("symbol") == symbol and v.get("status", "ok") == "ok" and not v.get("gate_pass"):
            n_fail += 1
    if n_fail >= 8:
        # Steeper curve: 8→-50, 9→-60, 10→-70, ...
        score -= 50.0 + 10.0 * (n_fail - 8)
    elif n_fail >= 3:
        score -= 8.0 * (n_fail - 2)
    if status_map is None:
        status_map = load_symbol_status()
    st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
    if st == "DEAD":
        score -= 50.0
    elif st == "HOLD":
        score -= 20.0
    fam = str(prop.get("covariate_family") or "").strip()
    if fam:
        n_fam_ok = 0
        n_fam_pass = 0
        other_pass = False
        for v in (snapshot or {}).values():
            if str(v.get("cov_family") or "") != fam:
                continue
            if v.get("status", "ok") != "ok":
                continue
            n_fam_ok += 1
            if v.get("gate_pass"):
                n_fam_pass += 1
                if str(v.get("symbol") or "").lower() != str(symbol).lower():
                    other_pass = True
        if other_pass and st == "ACTIVE":
            score += 8.0
        if n_fam_ok >= 4 and n_fam_pass == 0:
            score -= 8.0
    # Cross-run repeat offender penalty
    vid = "%s_%s" % (symbol, cov)
    repeat_counts = repeat_counts or {}
    n_runs = repeat_counts.get(vid, 0)
    if n_runs >= 3:
        score -= 20.0 + 10.0 * (n_runs - 3)  # 3→-20, 4→-30, 5→-40
    elif n_runs >= 2:
        score -= 8.0
    return score

def _append_backlog(prop, src_path):
    """新协变量想法追加到 backlog (宿主评审用)，不入 aligned 队列。

    按 name 去重: harvest_proposals 每个 cycle 重扫所有 run, 同一 new_cov
    proposal 会被反复看到; 已在 backlog 的同名想法不得重复追加。
    返回 True=本次新增, False=同名已存在。
    """
    os.makedirs(os.path.dirname(BACKLOG_PATH), exist_ok=True)
    nc = prop.get("new_covariate") or prop.get("new_cov") or {}
    name = nc.get("name") or prop.get("cov_override")
    existing = set()
    if os.path.exists(BACKLOG_PATH):
        try:
            with open(BACKLOG_PATH, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        existing.add(json.loads(line).get("name"))
        except (OSError, json.JSONDecodeError):
            pass
    if name in existing:
        return False
    rec = {"ts": _now_iso(), "src": src_path,
           "name": name, "proposal": prop}
    with open(BACKLOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True

def harvest_proposals(root, snapshot, dead, existing, pool, top_k,
                      aligned_max_points=600, priority_symbols=None):
    """收割 peer 机制化假设 (results/**/proposals/*.json) → aligned 队列行。
    与 harvest_survivors 平行但:
      - 不依赖诊断评估 (peer 不跑 eval)，验证证据来自慢环
      - 强制机制论证 (mechanism>=40 字)
      - 多样性按 family (QD 门)
      - priority_symbols (目标 1 星品种) 优先选座: 其中当前有效点 n>=350 的最先,
        样本暂不足的次之, 其余品种最后 —— 慢环是瓶颈, 座位优先给能直接推进目标的组合
    new_cov_*.json (new_covariate 字段) → 汇入 backlog, 不入队。
    返回 (selected_rows, stats)。
    """
    priority = set(priority_symbols or [])
    n_cache = {}
    ev = _load_evaluator()
    status_map = load_symbol_status()
    stats = {"seen": 0, "rejected": 0, "backlog": 0, "selected": 0,
             "reject_reasons": {}}
    passing_ids = {v["variant_id"] for v in rl.pass_variants(snapshot or {})}
    archived = getattr(ev, "ARCHIVED_COVARIATES", {}) if ev else {}
    valid_covs = getattr(ev, "VALID_COVARIATES", None) if ev else None
    allowed_syms = getattr(ev, "ALLOWED_SYMBOLS", None) if ev else None

    def _reject(reason):
        stats["rejected"] += 1
        stats["reject_reasons"][reason] = stats["reject_reasons"].get(reason, 0) + 1

    candidates = []
    seen_vids = set()
    run_dirs = sorted(glob.glob(os.path.join(root, "task_FM", "experiments", "run_*")),
                      key=os.path.getmtime, reverse=True)
    for run_dir in run_dirs:
        for sp in glob.glob(os.path.join(run_dir, "results", "**", "proposals", "*.json"),
                            recursive=True):
            try:
                with open(sp, encoding="utf-8") as f:
                    p = json.load(f)
            except Exception:
                _reject("unparseable_json"); continue
            stats["seen"] += 1
            # 新协变量想法 → backlog（不要求 hypothesis_proposal schema）
            if p.get("new_covariate") or p.get("new_cov"):
                if _append_backlog(p, sp):
                    stats["backlog"] += 1
                else:
                    _reject("backlog_dup")
                continue
            if p.get("schema") != "fm.hypothesis_proposal.v1":
                _reject("schema_mismatch"); continue
            symbol = str(p.get("symbol") or "").lower().strip()
            cov = str(p.get("cov_override") or "").strip()
            mechanism = str(p.get("mechanism") or "").strip()
            if not symbol or not cov:
                _reject("missing_symbol_or_cov"); continue
            if allowed_syms is not None and symbol not in allowed_syms:
                _reject("symbol_not_allowed"); continue
            if cov in archived:
                _reject("cov_archived"); continue
            if valid_covs is not None and cov not in valid_covs:
                _reject("cov_not_in_active_pool"); continue
            if len(mechanism) < 40:
                _reject("mechanism_too_short"); continue
            vid = "%s_%s" % (symbol, cov)
            sym_st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
            if sym_st == "DEAD":
                _reject("symbol_dead"); continue
            if sym_st == "HOLD":
                _reject("symbol_hold"); continue
            # DEAD family check: 4+ ok verdicts, 0 pass → family is dead
            dead_fams = _dead_families(snapshot or {})
            fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
            if fam and fam in dead_fams:
                _reject("family_dead"); continue
            if _has_prior_failure(snapshot or {}, symbol, cov):
                delta = str(p.get("failure_delta") or "").strip()
                if len(delta) < 20:
                    _reject("no_failure_delta"); continue
            if vid in dead or vid in existing or vid in passing_ids or vid in seen_vids:
                _reject("dedup"); continue
            seen_vids.add(vid)
            family = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or "other"
            repeat_counts = _cross_run_repeat_counts()
            score = _proposal_priority_score(p, cov, symbol, snapshot or {},
                                            status_map=status_map,
                                            repeat_counts=repeat_counts)
            if priority:
                if symbol not in n_cache:
                    n_cache[symbol] = _valid_n_for_symbol(symbol)
                n_now = n_cache[symbol]
                # 0=目标品种且当前可过门; 1=目标品种但样本暂不足(cj/lh); 2=非目标品种; 查询失败归 1
                if symbol not in priority:
                    tier = 2
                elif n_now is not None and n_now >= RETEST_GATE_N:
                    tier = 0
                else:
                    tier = 1
            else:
                tier = 0
            candidates.append({
                "variant_id": vid, "symbol": symbol, "cov_override": cov,
                "max_points": int(aligned_max_points), "stage": "aligned",
                "checkpoint_path": "", "enqueued_at": _now_iso(),
                "src_run": os.path.basename(run_dir), "source": "peer_proposal",
                "_family": family, "_score": score, "_tier": tier})

    candidates.sort(key=lambda r: (r["_tier"], -r["_score"], r["_family"], r["variant_id"]))
    selected = []
    used_families = set()
    # Pass 1: 每个 family 一个名额 (QD 多样性)
    for r in candidates:
        if len(selected) >= int(top_k):
            break
        if r["_family"] in used_families:
            continue
        selected.append(r); used_families.add(r["_family"])
    # Pass 2: 剩余名额按分数补
    if len(selected) < int(top_k):
        sel_ids = {r["variant_id"] for r in selected}
        for r in candidates:
            if len(selected) >= int(top_k):
                break
            if r["variant_id"] not in sel_ids:
                selected.append(r); sel_ids.add(r["variant_id"])
    for r in selected:
        r.pop("_family", None); r.pop("_score", None); r.pop("_tier", None)
    stats["selected"] = len(selected)
    return selected, stats

def materialize_covariate_menu(pool, dest_path):
    """从协变量池生成 peer 菜单 (active 机制目录 + archived 禁用块)。"""
    lines = ["## Covariate pool (supervisor snapshot)",
             "Propose symbol x covariate combos ONLY with ACTIVE covariates below.",
             "Each covariate carries a mechanism hypothesis — your own mechanism argument must extend it to the chosen symbol.",
             "archived covariates are RETIRED: do NOT propose them.",
             ""]
    active = {n: v for n, v in pool.items() if v.get("status") == "active"}
    archived = {n: v for n, v in pool.items() if v.get("status") == "archived"}
    experimental = {n: v for n, v in pool.items() if v.get("status") == "experimental"}
    by_fam = {}
    for n, v in active.items():
        by_fam.setdefault(v.get("family", "other"), []).append((n, v))
    for fam in sorted(by_fam):
        lines.append("### family: %s" % fam)
        for n, v in sorted(by_fam[fam]):
            tr = " 【旧口径线索·非证据】[track: %s]" % v["track_record"] if v.get("track_record") else ""
            lines.append("- %s: %s%s" % (n, v.get("mechanism", ""), tr))
        lines.append("")
    if experimental:
        lines.append("### experimental (host testing — do not propose yet)")
        for n in sorted(experimental):
            lines.append("- %s" % n)
        lines.append("")
    if archived:
        lines.append("### archived — DO NOT PROPOSE")
        for n in sorted(archived):
            lines.append("- %s: %s" % (n, archived[n].get("archived_reason", "archived")))
        lines.append("")
    # 品种样本天花板 (本地库当前可对齐有效点; 硬门 n>=350)。fail-open：无 DB/查询失败则跳过。
    try:
        n_table = _symbol_n_table()
    except Exception as exc:
        # 仅预期失败 (DB 连接/查询); 其余 (ImportError, AttributeError) 需浮出
        if isinstance(exc, (ImportError, AttributeError, SyntaxError)):
            raise
        n_table = []
    if n_table:
        lines.append("### symbol sample ceiling (valid aligned points now; hard gate n>=350)")
        lines.append("BELOW GATE symbols cannot pass today regardless of covariate "
                     "(1H bars accrue over time; supervisor auto-retests near-misses):")
        for sym, n in n_table:
            tag = "unknown" if n is None else ("gate-reachable" if n >= RETEST_GATE_N else "BELOW GATE")
            lines.append("- %s: n=%s %s" % (sym, "?" if n is None else n, tag))
        lines.append("")
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def _valid_n_for_symbol(symbol):
    """复刻 monthly_backtest.run_symbol_backtest 的有效评估点计数 (不 import torch)。

    eval_indices = range(CONTEXT_BARS, total-HORIZON+1, STEP)，再按日线充足性
    (累计日线 >= max(CONTEXT_DAYS-HORIZON_DAYS,100)) 过滤。任何异常返回 None (fail-open)。
    """
    try:
        import bisect
        from config.backtest_config import (
            CONTEXT_BARS, HORIZON, STEP, CONTEXT_DAYS, HORIZON_DAYS, EVAL_WINDOW_BARS)
        from data.data_store import DataStore
        store = DataStore(symbol)
        try:
            h1 = store.get_main_contract_1h(limit=99999)
            daily = store.get_main_continuous(limit=99999)
        finally:
            store.close()
        if h1.empty or len(h1) < CONTEXT_BARS + HORIZON or daily.empty:
            return 0
        need = max(CONTEXT_DAYS - HORIZON_DAYS, 100)
        dates = sorted(daily["dt"].astype(str).str[:10].tolist())
        n_ok = 0
        eval_start = max(CONTEXT_BARS, len(h1) - EVAL_WINDOW_BARS)
        for idx in range(eval_start, len(h1) - HORIZON + 1, STEP):
            if bisect.bisect_right(dates, str(h1["dt"].iloc[idx])[:10]) >= need:
                n_ok += 1
        return n_ok
    except Exception:
        return None

def _symbol_n_table():
    """[(symbol, valid_n)] for evaluator-allowed symbols; [] if evaluator unavailable."""
    ev = _load_evaluator()
    syms = sorted(getattr(ev, "ALLOWED_SYMBOLS", None) or [])
    return [(s, _valid_n_for_symbol(s)) for s in syms]

def _retest_candidates(snapshot):
    """gate 仅因 n 不足而失败的近失误最新裁决 (ic>=0.05, ev>0, pf/incumbent>1.05)。

    注意：这是近失误复测的遗留判据 (v1, 2026-09-09 落地)。v23 主裁决链
    (DirAcc/MAPE + DM(NW-HAC) + BH-FDR + 自适应门，见 docs/superpowers/specs/
    2026-09-14-prediction-quality-redesign-design.md) 不使用 ic/ev/pf；
    本函数仅用于 gate 仅差 n (n < RETEST_GATE_N) 的复测扫描。

    语义即 'inconclusive, retest when more data' (cj_oi 2026-09-08: PF1.133/ev19.46/
    ic0.08, 仅 n=324<350)。snapshot 按 variant_id 保留最新裁决。no_data 已被排除
    (status != ok)；gate 因 ic 不足而失败者不入选 (加样本也救不回)。
    """
    out = []
    for vid, v in snapshot.items():
        if v.get("status", "ok") != "ok" or v.get("gate_pass") is not False:
            continue
        n = int(v.get("n") or 0)
        if n <= 0 or n >= RETEST_GATE_N:
            continue
        ic = float(v.get("ic") or 0.0)
        ev = float(v.get("ev") or 0.0)
        ratio = float(v.get("pf") or 0.0) / INCUMBENT_PF.get(v.get("symbol"), 1.0)
        if ic >= RETEST_GATE_IC and ev > 0 and ratio > RETEST_PF_RATIO:
            out.append(v)
    return out

def plan_sample_retests(goal):
    """只读：返回当前可排队的 (row, last_n, current_n) 复测计划 (不写队列)。"""
    cad = goal.get("cadence") or {}
    margin = int(cad.get("retest_min_new_points", 1))
    inflight = rl.in_flight_ids(QUEUE, INPROGRESS)
    snap = rl.load_snapshot(REGISTRY)
    plan = []
    for v in _retest_candidates(snap):
        vid = v["variant_id"]
        if vid in inflight:
            continue
        cur_n = _valid_n_for_symbol(v["symbol"])
        if not cur_n or cur_n < RETEST_GATE_N:
            continue
        if cur_n - int(v.get("n") or 0) < margin:
            continue
        row = {"variant_id": vid, "symbol": v["symbol"],
               "cov_override": v["cov_override"],
               "max_points": int(v.get("max_points")
                                 or cad.get("aligned_max_points", 600)),
               "stage": "aligned", "checkpoint_path": "",
               "enqueued_at": _now_iso(), "src_run": "supervisor_retest",
               "source": "sample_retest"}
        plan.append((row, int(v.get("n") or 0), cur_n))
    return plan

def _maybe_enqueue_retests(goal, log):
    """近失误自动复测：本地数据长到过门样本量时旁路 dead 去重补队 (checkpoint resume)。"""
    plan = plan_sample_retests(goal)
    if not plan:
        return 0
    # dead 去重刻意旁路：这些 variant 上次 gate=False 已在 dead 集，复测是宿主显式决策；
    # queue/inflight 去重仍在 rl.queue_enqueue 内部生效。
    added = rl.queue_enqueue(QUEUE, [row for row, _, _ in plan],
                             dead=set(), existing=set())
    if added:
        _merge_save({"phase": "slow"})
        for row, last_n, cur_n in plan:
            _log_decision(log, "sample_retest_enqueued",
                          "%s n %d->%d (gate_n=%d); checkpoint resume, 只算新点"
                          % (row["variant_id"], last_n, cur_n, RETEST_GATE_N),
                          [row["variant_id"]])
            _emit_event("action", "sample_retest_enqueued",
                        {"variant_id": row["variant_id"],
                         "last_n": last_n, "current_n": cur_n})
    return added

def _log_decision(log_path, action, reason, refs=None):
    rec = {"ts": _now_iso(), "action": action, "reason": reason, "refs": refs or []}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def _read_cpu_hours():
    p = os.path.join(FM_ROOT, "data", "cache", "slow_loop_metrics.jsonl")
    total = 0.0
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            total += float(json.loads(line).get("elapsed_s", 0)) / 3600.0
                        except (json.JSONDecodeError, ValueError, TypeError):
                            continue
        except OSError:
            pass
    return round(total, 3)

def _ensure_tokens_baseline(st):
    """Freeze historical disk usage as baseline on first known read; budget the delta."""
    if "tokens_baseline_m" in st:
        return st
    tok_m, tok_unknown = _read_token_m()
    if tok_unknown:
        return st
    st["tokens_baseline_m"] = float(tok_m)
    save_state(st)
    return st


def _token_spend_m(st, tok_m):
    """Tokens used since supervisor baseline (pre-existing disk totals excluded)."""
    if "tokens_baseline_m" not in st:
        return float(tok_m)
    return max(0.0, float(tok_m) - float(st["tokens_baseline_m"]))


def _read_token_m():
    """Best-effort. 若所有 generation_results 都缺 runtime_usage, 返回 (0.0, True)=unknown, 跳过 token 预算。"""
    total = 0.0
    saw = False
    for gr in glob.glob(os.path.join(FM_ROOT, "task_FM", "experiments", "run_*", "gen_*", "generation_results.json")):
        try:
            d = json.load(open(gr, encoding="utf-8"))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else [d]):
            u = (it or {}).get("runtime_usage") or {}
            tok = u.get("total_tokens")
            if tok is None:
                tok = (it or {}).get("total_tokens")
            if tok is None:
                continue
            saw = True
            total += float(tok)
    return round(total / 1e6, 3), (not saw)

def _in_slow_window(goal, now=None):
    win = (goal.get("cadence") or {}).get("slow_loop_window") or ""
    if "-" not in win:
        return True
    a, b = [x.strip() for x in win.split("-", 1)]
    now_s = (now or datetime.now()).strftime("%H:%M")
    if a <= b:
        return a <= now_s <= b
    return now_s >= a or now_s <= b

def _deadline_passed(b):
    d = b.get("deadline")
    if not d:
        return False
    try:
        return datetime.now() > datetime.fromisoformat(str(d))
    except ValueError:
        return False

def _slow_loop_alive():
    lock_path = os.path.join(FM_ROOT, "data", "cache", "aligned_slow_loop.lock")
    if not os.path.exists(lock_path):
        return False
    try:
        f = os.open(lock_path, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(f)

def _queue_busy():
    return bool(rl.queue_load(QUEUE) + rl.queue_load(INPROGRESS))

def _slow_drain_complete():
    return (not _queue_busy()) and (not _slow_loop_alive())

def ensure_phase(st):
    """Fill st['phase']. Queued/running aligned always wins (local CPU drain).

    wait_quota / paused_429 / failover must NOT block already-enqueued slow work.
    """
    if _queue_busy() or _slow_loop_alive():
        st["phase"] = "slow"
        return st
    if st.get("phase") in PHASES:
        return st
    if st.get("paused_429") and not _run_active():
        if _failover_configured() or _llm_provider(st) == "failover":
            st["phase"] = "fast"
        else:
            st["phase"] = "wait_quota"
    else:
        st["phase"] = "fast"
    return st

def write_stop_report(kind, snap, why, budgets_line):
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REPORT_DIR, f"supervisor_{kind}_{ts}.md")
    body = ["# Supervisor {0}".format(kind), "",
            "- ts: {0}".format(_now_iso()),
            "- cycles_done: {0}".format(snap.get("cycles_done")),
            "- cpu_hours_used: {0}".format(snap.get("cpu_hours_used")),
            "- tokens_used_m: {0}".format(snap.get("tokens_used_m")),
            "- symbols_hit: {0}".format(sorted(snap.get("symbols_hit") or [])),
            "- families_hit: {0}".format(sorted(snap.get("families_hit") or [])),
            "- budgets: {0}".format(budgets_line),
            "- why: {0}".format("; ".join(why) if why else "(all conditions met)"),
            ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    try:
        with open(STATE_MD, "a", encoding="utf-8") as f:
            f.write("\n## Supervisor {0} ({1})\n\nSee {2}\n".format(kind, ts, path))
    except OSError as e:
        print(f"[WARN] Failed to write state file: {e}", file=sys.stderr)
    return path

def _merge_save(updates):
    fresh = load_state()
    fresh.update(updates)
    save_state(fresh)
    return fresh

def decide_fast_loop(goal, dry_run=False, now=None):
    """纯决策: 返回 actions 列表 [{action, reason, refs, argv?}]. dry_run 不调用 praxist。

    429 path: if FAILOVER_*/ANTHROPIC_FAILOVER_* configured, set llm_provider=failover,
    overlay BASE_URL+KEY+MODEL into env, and resume/start — do not wait_quota-only for Ark.
    Revert to primary only on the next NEW run_started when Ark quota is ok (no mid-run thrash).
    """
    actions = []
    ok, sleep_s = quota_gate(goal, now=now)
    active = _run_active()
    meta = _active_run_meta() if active else None
    st = ensure_phase(load_state())
    failover_ok = _failover_configured()
    provider_now = _llm_provider(st)

    def _resume_argv(rd, provider):
        return [
            "resume", rd, "--daemonize", "--json",
            "--model-provider", "model_provider:anthropic_messages",
            *_model_argv(provider),
        ]

    def _start_argv(provider):
        tag = "failover_qwen" if provider == "failover" else "primary"
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = os.path.join(
            FM_ROOT, "task_FM", "experiments", f"run_{ts}_{tag}_task_FM",
        )
        return [
            "start", "--task-path", os.path.join(FM_ROOT, "task_FM"),
            "--run-dir", run_dir,
            "--daemonize", "--json",
            "--model-provider", "model_provider:anthropic_messages",
            *_model_argv(provider),
        ]

    def _plan_resume(rd, provider, reason):
        argv = _resume_argv(rd, provider)
        actions.append({
            "action": "run_resumed",
            "reason": reason,
            "refs": [rd, provider],
            "argv": argv,
            "llm_provider": provider,
        })
        if not dry_run:
            r = _praxist(argv, env=_praxist_env(provider))
            if r.get("ok"):
                upd = {"paused_429": False, "phase": "fast", **_provider_state(provider)}
                _merge_save(upd)
            return r
        return None

    def _plan_start(provider, reason):
        argv = _start_argv(provider)
        actions.append({
            "action": "run_started",
            "reason": reason,
            "refs": [provider],
            "argv": argv,
            "llm_provider": provider,
        })
        if not dry_run:
            r = _praxist(argv, env=_praxist_env(provider))
            if r.get("ok"):
                updates = {"paused_429": False, "phase": "fast", **_provider_state(provider)}
                _emit_event("info", "run_started", {"provider": provider, "reason": reason})
                try:
                    js = json.loads(r["stdout"] or "{}")
                    if isinstance(js, dict):
                        if js.get("run_dir"):
                            updates["last_run_dir"] = js["run_dir"]
                        if js.get("run_id"):
                            updates["last_run_id"] = js["run_id"]
                except json.JSONDecodeError:
                    pass
                _merge_save(updates)
            return r
        return None

    # --- Active run + Ark quota banned ---
    if active and not ok:
        run_id = (meta or {}).get("run_id") or st.get("last_run_id")
        run_dir = (meta or {}).get("run_dir") or st.get("last_run_dir")
        if provider_now == "primary" and failover_ok and run_dir:
            stop_argv = ["stop", str(run_id)] if run_id else None
            can_resume = _failover_can_resume_same_run(run_dir)
            continue_argv = (
                _resume_argv(run_dir, "failover") if can_resume else _start_argv("failover")
            )
            continue_action = "run_resumed" if can_resume else "run_started"
            reason = (
                "Ark/primary 429; DashScope failover resume (same model id)"
                if can_resume
                else "Ark/primary 429; DashScope failover FRESH start "
                     "(Praxist resume forbids model change claude→qwen)"
            )
            actions.append({
                "action": "run_failover_llm",
                "reason": reason,
                "refs": [run_id, run_dir, "failover", "resume" if can_resume else "start"],
                "argv": stop_argv,
                "resume_argv": continue_argv if can_resume else None,
                "start_argv": None if can_resume else continue_argv,
                "llm_provider": "failover",
            })
            actions.append({
                "action": continue_action,
                "reason": reason,
                "refs": [run_dir, "failover"],
                "argv": continue_argv,
                "llm_provider": "failover",
            })
            if not dry_run:
                if run_id:
                    _praxist(["stop", str(run_id)])
                _merge_save({
                    "paused_429": False,
                    "last_run_dir": run_dir,
                    "last_run_id": run_id,
                    "phase": "fast",
                    **_provider_state("failover"),
                })
                r = _praxist(continue_argv, env=_praxist_env("failover"))
                if r.get("ok") and not can_resume:
                    # Capture new run_dir/id from start JSON when available
                    try:
                        js = json.loads(r.get("stdout") or "{}")
                        upd = {}
                        if isinstance(js, dict):
                            if js.get("run_dir"):
                                upd["last_run_dir"] = js["run_dir"]
                            if js.get("run_id"):
                                upd["last_run_id"] = js["run_id"]
                        if upd:
                            _merge_save(upd)
                    except json.JSONDecodeError:
                        pass
                if not r.get("ok"):
                    actions.append({
                        "action": "run_paused_429",
                        "reason": "failover continue failed; wait Ark reset",
                        "refs": [run_id, run_dir, (r.get("stderr") or "")[:200]],
                        "sleep_s": sleep_s,
                    })
                    _merge_save({"paused_429": True, **_provider_state("failover")})
                _emit_event("action", "provider_switch", {"from": "primary", "to": "failover", "reason": "429_rate_limit"})
            return actions
        # Already on failover: Ark quota_gate must NOT stop a live DashScope run.
        if provider_now == "failover":
            actions.append({
                "action": "noop",
                "reason": "Ark quota banned but llm_provider=failover; keep live DashScope run",
                "refs": [run_id, run_dir],
            })
            return actions
        # No failover configured → classic pause/wait for Ark reset
        actions.append({
            "action": "run_paused_429",
            "reason": "quota banned; stop then wait reset",
            "refs": [run_id, run_dir, provider_now],
            "argv": ["stop", str(run_id)] if run_id else None,
            "sleep_s": sleep_s,
        })
        if not dry_run and run_id:
            r = _praxist(["stop", str(run_id)])
            if r.get("ok"):
                _merge_save({
                    "paused_429": True,
                    "last_run_dir": run_dir,
                    "last_run_id": run_id,
                })
        return actions

    if st.get("phase") == "slow":
        return actions

    # --- paused_429: prefer failover resume over wait_quota ---
    if st.get("paused_429"):
        rd = st.get("last_run_dir") or st.get("last_run_id")
        if not active and rd:
            if failover_ok or provider_now == "failover":
                # Stay on failover for THIS run (no thrash to primary mid-run)
                if provider_now == "failover" or (failover_ok and not ok):
                    if _failover_can_resume_same_run(rd):
                        _plan_resume(
                            rd, "failover",
                            "paused_429; resume via DashScope failover (same model id)",
                        )
                    else:
                        _plan_start(
                            "failover",
                            "paused_429; FRESH DashScope start "
                            "(resume identity forbids model/task drift)",
                        )
                    return actions
                if ok:
                    # Quota ok but we never failed over — resume primary
                    _plan_resume(rd, "primary", "quota window ok; resume same run_dir on primary")
                    return actions
            if ok:
                _plan_resume(rd, "primary", "quota window ok; resume same run_dir on primary")
                return actions
        if not ok:
            if failover_ok and not rd and not active:
                _plan_start("failover", "paused_429 no run_dir; failover start not wait_quota")
                return actions
            actions.append({
                "action": "wait_quota",
                "reason": "quota window insufficient",
                "refs": [],
                "sleep_s": sleep_s,
            })
        return actions

    # --- wait_quota phase: bypass with failover when configured ---
    if st.get("phase") == "wait_quota":
        if not ok and failover_ok:
            rd = st.get("last_run_dir") or st.get("last_run_id")
            if not dry_run:
                _merge_save({"phase": "fast", **_provider_state("failover")})
            if rd and not active and _failover_can_resume_same_run(rd):
                _plan_resume(rd, "failover", "wait_quota bypassed; failover resume (same model)")
            elif not active:
                _plan_start(
                    "failover",
                    "wait_quota bypassed; failover start "
                    "(fresh run when model differs or no resumable dir)",
                )
            return actions
        if not ok:
            actions.append({
                "action": "wait_quota",
                "reason": "quota window insufficient",
                "refs": [],
                "sleep_s": sleep_s,
            })
            return actions
        if not dry_run:
            _merge_save({"phase": "fast"})
        st = dict(st)
        st["phase"] = "fast"

    # --- New start ---
    # Ark ok → primary (and leave failover only on NEW run_started).
    # Ark blocked + failover → start on failover (not wait_quota-only).
    if not active:
        last = st.get("last_run_id")
        harvested_already = (not last) or st.get("last_harvested_run_id") == last
        if harvested_already and st.get("phase") != "slow":
            if ok:
                # Optional: Ark quota ok again → force primary on NEW run
                provider = "primary"
                reason = "window ok, no active run"
                if provider_now == "failover":
                    reason = "ark quota ok; new run_started on primary (left failover)"
                _plan_start(provider, reason)
                return actions
            if failover_ok:
                _plan_start("failover", "ark quota insufficient; start on failover")
                return actions
    if not ok:
        actions.append({
            "action": "wait_quota",
            "reason": "quota window insufficient",
            "refs": [],
            "sleep_s": sleep_s,
        })
    return actions


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--goal", default=os.path.join(FM_ROOT, "scripts", "praxist_goal.yaml"))
    ap.add_argument("--root", default=FM_ROOT)
    ap.add_argument("--max-cycles", type=int, default=None)
    args = ap.parse_args(argv)
    # Self-healing: load .env.praxist so startup doesn't depend on shell source.
    # Uses args.root so tests with --root tmp_path don't FATAL-exit.
    env_loaded = _load_dotenv(root=getattr(args, "root", None))
    missing_req, missing_rec = _check_required_env()
    if missing_req and env_loaded:
        # .env.praxist EXISTS but is missing required keys -> real config error.
        print("[FATAL] .env.praxist exists but required vars missing: %s"
              % ", ".join(missing_req), file=sys.stderr)
        sys.exit(2)
    if missing_req and not env_loaded:
        # No .env.praxist at this root (tests / non-standard setup). Warn only.
        print("[WARN] No .env.praxist at %s and required vars not in env: %s"
              % (getattr(args, "root", FM_ROOT), ", ".join(missing_req)),
              file=sys.stderr)
    if missing_rec:
        print("[WARN] Recommended env vars missing: %s (will use code defaults)"
              % ", ".join(missing_rec), file=sys.stderr)
    _arm_handlers()
    if args.root != FM_ROOT:
        # 测试可把模块级路径 monkeypatch; --root 仅给 harvest 用
        pass
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock = open(LOCK_PATH, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another supervisor holds the lock; exit")
        _emit_event("info", "lock_contention", {"reason": "another supervisor holds the lock"})
        # 主动避让不是崩溃: 标记后退出, atexit 不得误报 unexpected_exit。
        _mark_stop_emitted()
        return 0
    try:
        return _main_locked(args)
    except Exception as e:
        _emit_event("critical", "error", {
            "exception": str(e),
            "traceback": traceback.format_exc()[-500:],
            "uptime_s": round(time.time() - _START_TIME, 1),
        })
        raise
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

def _harvest_rows(goal):
    cad = goal.get("cadence") or {}
    snap_now = rl.load_snapshot(REGISTRY)
    dead = rl.dead_variants(snap_now)
    # 修复：existing 包含历史 verdicts（避免重复入队）
    in_flight = rl.in_flight_ids(QUEUE, INPROGRESS)
    historical = set(snap_now.keys())  # 所有历史 verdicts
    existing = in_flight | historical
    pool = load_covariate_pool()
    rows, pstats = harvest_proposals(
        FM_ROOT, snap_now, dead, existing, pool,
        top_k=cad.get("survivors_per_cycle", 2),
        aligned_max_points=cad.get("aligned_max_points", 400),
        priority_symbols=cad.get("priority_symbols"))
    return rows, dead, existing, pstats

def _maybe_harvest(st, goal, log):
    """Harvest a finished run's peer proposals into the aligned queue.

    paused_429 / wait_quota / failover do NOT block harvest: proposals are local
    hypotheses fed to the slow loop (local CPU) and should keep draining.
    """
    last = st.get("last_run_id")
    harvested_already = bool(last) and st.get("last_harvested_run_id") == last
    if _run_active() or not last or harvested_already:
        return False
    rows, dead, existing, pstats = _harvest_rows(goal)
    if pstats and pstats.get("seen"):
        _log_decision(log, "proposal_scan",
                      "seen=%(seen)d rejected=%(rejected)d backlog=%(backlog)d reasons=%(reject_reasons)s" % pstats,
                      [])
    if rows:
        n = rl.queue_enqueue(QUEUE, rows, dead, existing)
        _log_decision(log, "harvested_proposals", f"enqueued {n}",
                      [r["variant_id"] for r in rows])
        _merge_save({"last_harvested_run_id": last, "phase": "slow"})
        try:
            from praxist_assets_archive import archive_fast_harvest
            archive_fast_harvest(last, rows, load_state())
        except Exception as e:
            _log_decision(log, "assets_archive_error", f"harvest: {e}")
    else:
        _log_decision(log, "harvest_empty",
                      "finished run produced 0 valid proposals "
                      "(need results/**/proposals/*.json; reject_reasons=%s)"
                      % (pstats.get("reject_reasons") if pstats else {}))
        gate_ok, _ = quota_gate(goal)
        fresh = load_state()
        fresh["cycles_done"] = int(fresh.get("cycles_done") or 0) + 1
        fresh["last_harvested_run_id"] = last
        fresh["phase"] = "fast" if gate_ok else "wait_quota"
        save_state(fresh)
    return True


def ensure_baselines(symbols, root):
    """Check baseline_metrics.json + baseline_points_{symbol}.jsonl validity.

    For each symbol, check that baseline_metrics has a valid entry AND
    baseline_points_{symbol}.jsonl has >= 100 valid lines. If not, serially
    call generate_baseline_points.generate.
    """
    try:
        import generate_baseline_points as gbp
    except ImportError:
        return
    config_dir = os.path.join(root, "task_FM", "config")
    metrics_path = os.path.join(config_dir, "baseline_metrics.json")
    try:
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)
    except (OSError, json.JSONDecodeError):
        # Cold start: no metrics file yet, treat as empty
        metrics = {}
        # Skip generation under pytest to avoid slow model calls in tests
        if "pytest" in sys.modules:
            return
    for sym in sorted(symbols):
        sym_lower = sym.lower()
        points_path = os.path.join(config_dir, f"baseline_points_{sym_lower}.jsonl")
        met = metrics.get(sym_lower, {})
        if not isinstance(met, dict) or not met.get("n") or int(met.get("n", 0)) <= 0:
            try:
                gbp.generate(sym_lower, "ccl", root)
            except Exception as e:
                print(f"[ERROR] ensure_baselines: generate failed for {sym_lower}: {e}", file=sys.stderr)
            continue
        n_lines = 0
        if os.path.exists(points_path):
            try:
                with open(points_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                json.loads(line)
                                n_lines += 1
                            except json.JSONDecodeError:
                                pass
            except OSError:
                pass
        if n_lines < 100:
            try:
                gbp.generate(sym_lower, "ccl", root)
            except Exception as e:
                print(f"[ERROR] ensure_baselines: generate failed for {sym_lower} (n_lines={n_lines}): {e}", file=sys.stderr)


def wait_for_batch(batch_id, batch_records, registry_path, timeout=7200):
    """Scan registry until all batch_records have a verdict or timeout.

    Returns list of records that got a verdict. On timeout, writes timeout
    tombstone entries to registry for records without verdicts.
    timeout=0: single scan, no polling — missing variants are tombstoned
    immediately (used after slow-loop drain is complete).
    """
    start = time.monotonic()
    needed = {r["variant_id"] for r in batch_records}
    found = {}
    while True:
        try:
            with open(registry_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    vid = rec.get("variant_id")
                    if vid in needed and rec.get("batch_id") == batch_id:
                        if rec.get("status") in ("ok", "error", "timeout"):
                            found[vid] = rec
        except OSError:
            pass
        if needed <= set(found.keys()):
            break
        # timeout=0: single scan, no polling (post-drain finalize: missing
        # variants are tombstoned immediately instead of waiting 7200s)
        if time.monotonic() - start >= timeout:
            break
        time.sleep(5)
    missing = needed - set(found.keys())
    if missing:
        for r in batch_records:
            if r["variant_id"] in missing:
                tomb = rl.make_timeout_tombstone(
                    r.get("symbol", ""), r["variant_id"], batch_id
                )
                try:
                    rl.append_verdict(registry_path, tomb)
                except Exception as e:
                    _vid = r["variant_id"]
                    print(f"[WARN] wait_for_batch tombstone write failed "
                          f"for {_vid}: {e}", file=sys.stderr)
    return list(found.values())


def cleanup_batch_workers(batch_id):
    """Best-effort cleanup of batch workers. Kill processes with matching batch_id."""
    try:
        result = subprocess.run(
            ["pkill", "-f", f"--batch-id.*{batch_id}"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print(f"[INFO] Cleaned up workers for batch {batch_id}")
    except FileNotFoundError:
        pass  # pkill not available
    except Exception as e:
        print(f"[WARN] cleanup_batch_workers failed for {batch_id}: {e}", file=sys.stderr)


def _maybe_start_slow_loop(goal, log):
    st = load_state()
    if st.get("phase") != "slow":
        return
    if not _queue_busy() or _slow_loop_alive():
        return
    out_path = os.path.join(FM_ROOT, "data", "cache", "slow_loop.out")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_fp = open(out_path, "ab")
    try:
        project_python = os.path.join(FM_ROOT, ".venv", "bin", "python")
        if not os.path.isfile(project_python):
            project_python = sys.executable
        batch_id = "batch_" + uuid.uuid4().hex[:8]
        # Capture current queue records for batch tracking
        try:
            batch_records = rl.queue_load(QUEUE) + rl.queue_load(INPROGRESS)
        except Exception:
            batch_records = []
        subprocess.Popen(
            [project_python, os.path.join(HERE, "aligned_slow_loop.py"),
             "--batch-id", batch_id],
            stdout=out_fp, stderr=subprocess.STDOUT, start_new_session=True)
        # Persist batch_id for FDR promotion on completion
        fresh = load_state()
        fresh["current_batch_id"] = batch_id
        fresh["current_batch_records"] = [
            {"variant_id": r.get("variant_id"), "symbol": r.get("symbol", "") or ""}
            for r in batch_records if r.get("variant_id")]
        save_state(fresh)
    finally:
        out_fp.close()
    _log_decision(log, "slow_loop_started", "phase=slow, queue busy")

def _maybe_finish_slow(goal, log):
    st = load_state()
    if st.get("phase") != "slow":
        return False
    if not _slow_drain_complete():
        return False
    # Wait for batch completion with timeout tombstones before FDR
    batch_id = st.get("current_batch_id")
    if batch_id:
        try:
            saved = st.get("current_batch_records")
            if not isinstance(saved, list) or not saved:
                # legacy state: variant_ids only — resolve symbols from registry verdicts
                sym_by_vid = {}
                try:
                    for vrec in rl.read_verdicts(REGISTRY):
                        vid = vrec.get("variant_id")
                        if vid and vid not in sym_by_vid:
                            sym_by_vid[vid] = vrec.get("symbol", "")
                except Exception:
                    sym_by_vid = {}
                saved = [{"variant_id": vid, "symbol": sym_by_vid.get(vid, "")}
                         for vid in (st.get("current_batch_variant_ids") or []) if vid]
            batch_records = saved
            if batch_records:
                # drain already complete: single scan, tombstone missing immediately
                wait_for_batch(batch_id, batch_records, REGISTRY, timeout=0)
        except Exception as e:
            _log_decision(log, "wait_for_batch_error", str(e))
    # Batch completion: apply FDR promotion to batch verdicts
    if batch_id:
        try:
            all_verdicts = rl.read_verdicts(REGISTRY)
            batch_verdicts = [v for v in all_verdicts if v.get("batch_id") == batch_id]
            if batch_verdicts and bh_fdr_promote is not None:
                updates = bh_fdr_promote(batch_verdicts)
                if updates:
                    rl.update_batch_verdicts(REGISTRY, batch_id, updates)
                    _log_decision(log, "batch_fdr_promote",
                                 f"batch={batch_id} promoted={len(updates)}")
        except Exception as e:
            _log_decision(log, "batch_fdr_error", str(e))
        try:
            cleanup_batch_workers(batch_id)
        except Exception as e:
            _log_decision(log, "cleanup_batch_error", str(e))
        # Clear batch tracking from state
        fresh = load_state()
        fresh.pop("current_batch_id", None)
        fresh.pop("current_batch_records", None)
        fresh.pop("current_batch_variant_ids", None)  # legacy key
        save_state(fresh)
    snap = rl.load_snapshot(REGISTRY)
    materialize_known_verdicts(
        snap, VERDICTS_INC,
        status_map=load_symbol_status(),
        queue_ids=rl.in_flight_ids(QUEUE, INPROGRESS),
        proposed_ids=collect_proposed_variant_ids(FM_ROOT),
    )
    materialize_covariate_menu(load_covariate_pool(), MENU_INC)
    gate_ok, _ = quota_gate(goal)
    fresh = load_state()
    fresh["cycles_done"] = int(fresh.get("cycles_done") or 0) + 1
    fresh["phase"] = "fast" if gate_ok else "wait_quota"
    save_state(fresh)
    _log_decision(log, "slow_drain_complete",
                  "queue empty, slow idle, cycle+1 phase={0}".format(fresh["phase"]))
    try:
        from praxist_assets_archive import archive_slow_cycle
        archive_slow_cycle(fresh, goal)
    except Exception as e:
        _log_decision(log, "assets_archive_error", f"slow: {e}")
    return True

def _main_locked(args):
    log = os.path.join(FM_ROOT, ".omc", "supervisor_decisions.jsonl")
    one_shot = args.dry_run or args.once
    # Pre-flight: ensure baseline metrics/points exist for all goal symbols
    try:
        ensure_baselines(GOAL_SYMBOLS_SET, args.root)
    except Exception as e:
        print(f"[ERROR] ensure_baselines pre-flight failed: {e}", file=sys.stderr)
    while True:
        _write_heartbeat()
        if _SHUTDOWN_REQUESTED:
            _emit_event("critical", "supervisor_stopped", {
                "reason": "signal_received",
                "exit_code": 0,
                "uptime_s": round(time.time() - _START_TIME, 1),
            })
            return 0
        # Reload goal every poll so hot token_budget_m / max_cycles edits apply
        # without restart (2026-09-08: stale 50 in-memory while disk was 80 → false
        # budget_exhausted at tok_m=52.516).
        goal = load_goal(args.goal)
        max_cycles = args.max_cycles or goal["budgets"]["max_cycles"]
        st = load_state()
        cycles = int(st.get("cycles_done") or 0)
        cpu_h = _read_cpu_hours()
        tok_m, tok_unknown = _read_token_m()
        tok_spend = _token_spend_m(st, tok_m)
        snap = build_snapshot(REGISTRY, cycles, cpu_h, tok_spend)
        ok, why = evaluate_goal(goal["success_condition"], snap)
        b = goal["budgets"]
        tok_budget = b.get("token_budget_m", 80)
        tok_hit = (not tok_unknown) and tok_spend >= tok_budget
        budget_hit = (cycles >= max_cycles or cpu_h >= b.get("cpu_hours", 60)
                      or tok_hit or _deadline_passed(b))

        if args.dry_run:
            if ok:
                print(json.dumps({"action": "goal_reached",
                                  "reason": "; ".join(why) or "all conditions met"},
                                 ensure_ascii=False))
            elif budget_hit:
                print(json.dumps({"action": "budget_exhausted",
                                  "reason": f"cycles={cycles} cpu_h={cpu_h} tok_m={tok_spend} tok_unknown={tok_unknown}"},
                                 ensure_ascii=False))
            rows, _, _, pstats = _harvest_rows(goal)
            print(json.dumps({"action": "harvest_plan", "n": len(rows),
                              "vids": [r["variant_id"] for r in rows],
                              "proposal_stats": pstats}, ensure_ascii=False))
            for rrow, last_n, cur_n in plan_sample_retests(goal):
                print(json.dumps({"action": "sample_retest_plan",
                                  "variant_id": rrow["variant_id"],
                                  "last_n": last_n, "current_n": cur_n},
                                 ensure_ascii=False))
            planned = decide_fast_loop(goal, dry_run=True)
            for a in planned:
                print(json.dumps(a, ensure_ascii=False, default=str))
            _mark_stop_emitted()
            return 0

        materialize_known_verdicts(
            snap["variants"], VERDICTS_INC,
            status_map=load_symbol_status(),
            queue_ids=rl.in_flight_ids(QUEUE, INPROGRESS),
            proposed_ids=collect_proposed_variant_ids(FM_ROOT),
        )
        materialize_covariate_menu(load_covariate_pool(), MENU_INC)
        if ok:
            rec = _log_decision(log, "goal_reached", "; ".join(why) or "all conditions met")
            write_stop_report("goal_reached", snap, why, rec["reason"])
            _emit_event("critical", "goal_reached", {
                "why": why, "cycles_done": cycles, "cpu_h": cpu_h, "tok_m": tok_spend,
                "symbols_hit": sorted(snap.get("symbols_hit") or []),
                "uptime_s": round(time.time() - _START_TIME, 1),
            })
            # 干净终止: 先标记, 否则 atexit 兜底会误报 supervisor_stopped/unexpected_exit。
            _mark_stop_emitted()
            print(json.dumps(rec, ensure_ascii=False))
            return 0
        if budget_hit:
            # If a fast run is still alive, do NOT exit — wait for it to finish so we
            # can harvest→slow before any budget_exhausted return (2026-09-07 lesson:
            # exited at tok>budget while failover run lived → missed harvest).
            if _run_active():
                _log_decision(
                    log, "budget_hit_wait_run",
                    f"cycles={cycles}/{max_cycles} cpu_h={cpu_h} "
                    f"tok_m={tok_spend}/{tok_budget}; "
                    "defer exit until active run ends then harvest/slow",
                )
                budget_hit = False
            else:
                # Drain finished-run harvest + local slow queue BEFORE exiting on budget.
                st_pre = load_state()
                _maybe_harvest(st_pre, goal, log)
            st_pre = load_state()
            if st_pre.get("phase") == "slow" or _queue_busy() or _slow_loop_alive():
                if st_pre.get("phase") != "slow":
                    _merge_save({"phase": "slow"})
                    _emit_event("action", "phase_change", {"from": "fast", "to": "slow"})
                _maybe_start_slow_loop(goal, log)
                # One-shot drain wait is not appropriate here; leave slow running and
                # only exit once queue is empty. If still draining, keep process alive.
                if not _slow_drain_complete():
                    _log_decision(
                        log, "budget_hit_drain_slow",
                        f"cycles={cycles} cpu_h={cpu_h} tok_m={tok_spend}; "
                        "defer exit until aligned queue drains",
                    )
                    # Fall through to slow-handling path below instead of return.
                    budget_hit = False
                    # Skip success/budget returns by jumping to phase handling
                else:
                    _maybe_finish_slow(goal, log)
                    # Re-check goal after slow drain — slow loop verdicts may have
                    # satisfied the success condition since the stale snapshot at top.
                    fresh_cycles = int(load_state().get("cycles_done") or 0)
                    fresh_cpu_h = _read_cpu_hours()
                    fresh_tok_m, fresh_tok_unknown = _read_token_m()
                    fresh_tok_spend = _token_spend_m(load_state(), fresh_tok_m)
                    fresh_snap = build_snapshot(REGISTRY, fresh_cycles, fresh_cpu_h, fresh_tok_spend)
                    fresh_ok, fresh_why = evaluate_goal(goal["success_condition"], fresh_snap)
                    if fresh_ok:
                        rec = _log_decision(log, "goal_reached",
                                            "; ".join(fresh_why) or "all conditions met (post-slow-drain)")
                        write_stop_report("goal_reached", fresh_snap, fresh_why, rec["reason"])
                        _emit_event("critical", "goal_reached", {
                            "why": fresh_why, "cycles_done": fresh_cycles,
                            "cpu_h": fresh_cpu_h, "tok_m": fresh_tok_spend,
                            "source": "budget_hit_post_slow_drain",
                        })
                        _mark_stop_emitted()
                        print(json.dumps(rec, ensure_ascii=False))
                        return 0
                    # Goal not reached — recompute budget_hit with fresh numbers
                    fresh_b = goal["budgets"]
                    fresh_tok_hit = (not fresh_tok_unknown) and fresh_tok_spend >= fresh_b.get("token_budget_m", 80)
                    budget_hit = (fresh_cycles >= (args.max_cycles or goal["budgets"]["max_cycles"])
                                  or fresh_cpu_h >= fresh_b.get("cpu_hours", 60)
                                  or fresh_tok_hit or _deadline_passed(fresh_b))
                    # Update outer-scope vars so the budget_exhausted report (if still hit) is accurate
                    cycles, cpu_h, tok_spend, snap = fresh_cycles, fresh_cpu_h, fresh_tok_spend, fresh_snap
                    tok_unknown, tok_hit = fresh_tok_unknown, fresh_tok_hit
            if budget_hit:
                rec = _log_decision(log, "budget_exhausted",
                                    f"cycles={cycles}/{max_cycles} cpu_h={cpu_h} "
                                    f"tok_m={tok_spend}/{tok_budget} tok_unknown={tok_unknown} "
                                    f"tok_hit={tok_hit}")
                write_stop_report("budget_exhausted", snap, [rec["reason"]], rec["reason"])
                _emit_event("critical", "budget_exhausted", {
                    "cycles": cycles, "cpu_h": cpu_h, "tok_m": tok_spend,
                    "tok_unknown": tok_unknown,
                    "uptime_s": round(time.time() - _START_TIME, 1),
                })
                # 干净终止: 先标记, 否则 atexit 兜底会误报 supervisor_stopped/unexpected_exit。
                _mark_stop_emitted()
                print(json.dumps(rec, ensure_ascii=False))
                return 0

        st = ensure_phase(load_state())
        st = _merge_save({"phase": st["phase"]})
        # Harvest finished runs even during paused_429 / wait_quota.
        if not _run_active():
            _maybe_harvest(st, goal, log)
        # n-不足型近失误自动复测 (本地慢环, 不受 LLM 暂停/failover 影响)。
        try:
            _maybe_enqueue_retests(goal, log)
        except Exception as e:
            _log_decision(log, "retest_scan_error", str(e))
        st = load_state()
        # Local aligned drain is never blocked by LLM pause/failover.
        if st.get("phase") == "slow" or _queue_busy() or _slow_loop_alive():
            if st.get("phase") != "slow":
                _merge_save({"phase": "slow"})
            _maybe_start_slow_loop(goal, log)
            _maybe_finish_slow(goal, log)
        planned = decide_fast_loop(goal, dry_run=False)
        for a in planned:
            print(json.dumps(a, ensure_ascii=False, default=str))
            _log_decision(log, a["action"], a.get("reason", ""), a.get("refs") or [])

        # Session unstick (ops nudge / optional disk backfill). Safe no-op when healthy.
        try:
            from praxist_session_unstick import detect_and_act as _session_unstick
            _u = _session_unstick(dry_run=False, force=False)
            if _u.get("action") not in (None, "noop") or _u.get("escalate"):
                _log_decision(
                    log,
                    "session_unstick_escalate" if _u.get("escalate") else "session_unstick",
                    _u.get("reason") or _u.get("action") or "",
                    [str(_u.get("run_dir") or ""), str(_u.get("nudge") or ""),
                     str(_u.get("backfill") or "")],
                )
                print(json.dumps({"action": "session_unstick", **{k: _u.get(k) for k in
                      ("action", "reason", "escalate", "claude", "mem_gib", "nudge",
                       "backfill", "missing_peers", "synth")}},
                                 ensure_ascii=False, default=str))
        except Exception as e:
            _log_decision(log, "session_unstick_error", str(e))

        if one_shot:
            _mark_stop_emitted()
            return 0
        sleep_s = POLL_S
        for a in planned:
            if a.get("sleep_s"):
                sleep_s = min(sleep_s, int(a["sleep_s"]))
        time.sleep(max(1, sleep_s))

if __name__ == "__main__":
    sys.exit(main() or 0)
