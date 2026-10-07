#!/usr/bin/env python3
"""三环监督环: goal 判定 + 两环调度, 纯 Python 0 token"""
import argparse, atexit, fcntl, glob, json, logging, os, re, signal, subprocess, sys, threading, time, traceback, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import yaml
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
import registry_lib as rl
from goal_dsl import evaluate_goal
from cascade.cov_family import ALLOWED_FAMILIES, resolve_cov_family
from cascade import experiment_fingerprint as ef
import search_trees as st
import search_promote
try:
    from cascade.statistical_tests import bh_fdr_promote
except ImportError:
    bh_fdr_promote = None

_PERSISTABLE_DM = frozenset({"ok", "set_mismatch_ok"})


def fdr_pass_persistable(verdict):
    """W3.4：只有确认运行、缺失可接受、且 DM 状态可确认时，fdr_pass=True 才能落盘。"""
    if not isinstance(verdict, dict):
        return False
    return (
        verdict.get("run_mode") == "confirmation"
        and verdict.get("missingness_admissible") is True
        and verdict.get("dm_status") in _PERSISTABLE_DM
    )


def promote_batch_for_persistence(verdicts):
    """先做原 BH/Bonferroni，再拒绝不可确认行的 True。不写文件。"""
    updates = bh_fdr_promote(verdicts)
    by_vid = {}
    for verdict in verdicts or []:
        vid = verdict.get("variant_id")
        if vid is not None:
            by_vid[vid] = verdict
    for vid, update in updates.items():
        if update.get("fdr_pass") is True and not fdr_pass_persistable(by_vid.get(vid)):
            update["fdr_pass"] = False
    return updates

# 惰性解析: 导入期不得要求 praxist 存在，否则新克隆 / CI / worktree 无法收集测试。
_PRAXIST = None


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


def _praxist_bin() -> str:
    global _PRAXIST
    if _PRAXIST is None:
        _PRAXIST = _resolve_praxist_bin()
    return _PRAXIST
QUEUE = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl")
INPROGRESS = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl")
REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")
# P2.2 (spec 2026-10-05 §6.7): 搜索树事件账（append-only；写入侧 2.3 落地）
SEARCH_COMMITMENTS_PATH = os.path.join(FM_ROOT, "task_FM", "config", "search_commitments.jsonl")
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




# ── PR-C2: 研究 family 接线（spec 4.3 W3.6）────────────────────
# 纯逻辑在 cascade/research_family.py（唯一家）；此处只做 supervisor 侧接线，
# 避免 family 状态机散落进监督环。
from cascade.research_family import (  # noqa: E402
    all_terminal as _fam_all_terminal,
    default_family_key as _fam_default_key,
    family_report_scope as _fam_report_scope,
    make_member as _fam_make_member,
    register_member as _fam_register_member,
    seal_family as _fam_seal_family,
)

FAMILY_REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "family_registry.jsonl")
PREREGISTRY_PATH = os.path.join(FM_ROOT, "task_FM", "config", "preregistry.jsonl")


def family_key_for(symbol, **kwargs):
    """该品种的默认研究 family 键（一个品种 = 一个 family）。"""
    return _fam_default_key(symbol, **kwargs)


def register_family_member(family_key, symbol, variant_id, registered_at,
                           members, run_mode="confirmation"):
    """把一个确认成员登记进 family。返回 (成员列表, 结果标签)。

    探索期结果会被拒绝进入 —— 探索自由、确认严格是本设计的分界线。
    """
    member = _fam_make_member(
        family_key, symbol, variant_id, registered_at, run_mode=run_mode
    )
    return _fam_register_member(members, member, registered_at)


def seal_research_family(members, now):
    """封账：全部成员终态后一次性跑 family 级 BH-FDR。"""
    return _fam_seal_family(members, now)


def _prereg_field(row, key, default=None):
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(row, key, default)


def _find_prereg(registry, prereg_id):
    for row in registry:
        if _prereg_field(row, "prereg_id") == prereg_id:
            return row
    return None


def dispatch_confirmation(proposal, registry, members):
    """确认分派。不启动监督环。

    调用 queue_decision。拒绝则不登记 family；接受则 register_family_member。
    """
    import preregistry as _prereg

    decision = _prereg.queue_decision(proposal, registry, run_mode="confirmation")
    if not decision.accepted:
        return {
            "accepted": False,
            "reason": decision.reason,
            "run_label": decision.run_label,
            "prereg_id": decision.prereg_id,
            "members": members,
            "registration": None,
        }
    matched = _find_prereg(registry, decision.prereg_id)
    symbol = proposal.get("symbol") or _prereg_field(matched, "symbol")
    variant_id = proposal.get("variant_id")
    if not variant_id:
        raise ValueError("confirmation proposal requires variant_id")
    registered_at = _prereg_field(matched, "registered_at")
    family_key = proposal.get("family_key") or family_key_for(symbol)
    new_members, tag = register_family_member(
        family_key, symbol, variant_id, registered_at, members,
        run_mode="confirmation",
    )
    return {
        "accepted": True,
        "reason": None,
        "run_label": decision.run_label,
        "prereg_id": decision.prereg_id,
        "members": new_members,
        "registration": tag,
    }


def _stamp_member(members, row, label):
    variant_id = row.get("variant_id")
    stamped = []
    for member in members:
        member = dict(member)
        if variant_id is not None and member.get("variant_id") == variant_id:
            member["status"] = label
            if "p_value" in row:
                member["p_value"] = row.get("p_value")
        stamped.append(member)
    return stamped


def _seal_if_all_terminal(members, label, now, audit):
    # underpowered / refuted_by_contamination 也是终态，可以封账。
    # family_bh_fdr 对这两种状态固定按 p=1，不看成员上已写的 p_value。
    if _fam_all_terminal(members):
        sealed, _adjusted = seal_research_family(members, now)
        return {
            "run_label": label,
            "audit": audit,
            "members": sealed,
            "sealed": True,
        }
    return {
        "run_label": label,
        "audit": audit,
        "members": members,
        "sealed": False,
    }


def finalize_confirmation(row, members, now):
    """终结一条确认。不启动监督环，不把 fdr_pass 写成 True。

    样本未满且行上没有 request_early_seal 时，只返回 peek 审计，不改标签。
    显式提前封账走 early_seal。样本已满走 classify_confirmation，
    全体终态才 seal_research_family。
    """
    import preregistry as _prereg

    n_actual = row["n_confirm_actual"]
    n_required = row["n_confirm_required"]
    if n_actual < n_required and row.get("request_early_seal") is not True:
        decision = _prereg.peek_gate(n_actual, n_required)
        return {
            "run_label": row.get("run_label"),
            "audit": decision.audit,
            "members": members,
            "sealed": False,
        }
    if n_actual < n_required:
        seal = _prereg.early_seal(n_actual, n_required)
        updated = _stamp_member(members, row, seal.terminal_state)
        return _seal_if_all_terminal(updated, seal.terminal_state, now, None)
    label = _prereg.classify_confirmation(row)
    updated = _stamp_member(members, row, label)
    return _seal_if_all_terminal(updated, label, now, None)

def _now_iso():
    return datetime.now().isoformat()


_BASE_COVARIATE = "daily_slope"


def _requested_covariate(prereg_row):
    keys = ((prereg_row or {}).get("cov_fingerprint") or {}).get("keys") or []
    extra = [key for key in keys if key != _BASE_COVARIATE]
    if len(extra) != 1:
        return None
    return extra[0]


def confirmation_queue_row(prereg_row, variant_id):
    cov = _requested_covariate(prereg_row)
    n_req = int(prereg_row["n_confirm_required"])
    return {
        "variant_id": variant_id,
        "symbol": str(prereg_row["symbol"]).lower(),
        "cov_override": cov,
        "max_points": n_req,
        "stage": "aligned",
        "checkpoint_path": "",
        "enqueued_at": _now_iso(),
        "src_run": "confirmation_dispatch",
        "source": "confirmation",
        "run_mode": "confirmation",
        "prereg_id": prereg_row["prereg_id"],
        "confirm_from_ts": prereg_row["confirm_from_ts"],
        "n_confirm_required": n_req,
    }


def due_confirmations(registry, now_ts, blocked_ids, already_ran_ids,
                      fingerprint_for, family_for):
    """到期且未占用、未跑过的预注册。不入队，不读时钟，不读权重。"""
    import cascade.experiment_fingerprint as ef

    out = []
    for row in registry or []:
        if not isinstance(row, dict):
            continue
        if row.get("terminal_state") not in (None, ""):
            continue
        confirm_from = row.get("confirm_from_ts")
        if not isinstance(confirm_from, str) or confirm_from > now_ts:
            continue
        if row.get("prereg_id") in already_ran_ids:
            continue
        cov = _requested_covariate(row)
        if cov is None:
            continue
        fp = fingerprint_for(str(row.get("symbol") or "").lower(), cov)
        fam = family_for(cov)
        if not fp or not fam:
            continue
        vid = ef.build_variant_id(str(row["symbol"]).lower(), fam, fp)
        if vid in blocked_ids:
            continue
        out.append(confirmation_queue_row(row, vid))
    return out


def load_preregistry(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_family_members(path):
    by_vid = {}
    order = []
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            member = json.loads(line)
            vid = member.get("variant_id")
            if vid not in by_vid:
                order.append(vid)
            by_vid[vid] = member
    return [by_vid[vid] for vid in order]


def save_family_members(path, members):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for member in members:
            fh.write(json.dumps(member, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _merge_family_members(members, family_key, returned):
    """同一 family_key 整段替换。其它 family 的相对顺序保留。"""
    returned = list(returned or [])
    out = []
    placed = False
    for member in members:
        if member.get("family_key") != family_key:
            out.append(member)
            continue
        if not placed:
            out.extend(returned)
            placed = True
    if not placed:
        out.extend(returned)
    return out


_CONFIRM_DATA_TTL_S = 1800
_CONFIRM_DATA_CACHE: dict[str, tuple] = {}   # symbol -> (queried_at, latest_dt | None)


def _confirm_data_ready(symbol, confirm_from_ts):
    """该品种的 1H 数据是否已越过 confirm_from_ts。

    2026-10-03（D1）：confirm_from_ts 是注册时锁定的固定日历边界，但数据要过几天
    才追上来。边界之前派发确认行 → 评估窗口必然为空 → 每轮落一座 no_data 墓碑
    （实测每 ~5.7 分钟一座）。这里做 fail-closed 的数据闸门：查不到数据也算未就绪。
    查询结果按 symbol 缓存 30 分钟，避免每轮打库。
    """
    import time as _time
    key = str(symbol).lower()
    now = _time.time()
    hit = _CONFIRM_DATA_CACHE.get(key)
    if hit is not None and now - hit[0] <= _CONFIRM_DATA_TTL_S:
        latest = hit[1]
    else:
        latest = None
        try:
            from data.data_store import DataStore
            store = DataStore(key)
            try:
                h1 = store.get_main_contract_1h(limit=99999)
            finally:
                store.close()
            if h1 is not None and not h1.empty:
                latest = str(h1["dt"].astype(str).max())
        except Exception:
            latest = None
        _CONFIRM_DATA_CACHE[key] = (now, latest)
    if not latest:
        return False
    return latest > str(confirm_from_ts)


def _confirmation_is_final(v):
    """确认终态 = 真实评估落账且样本已满（n_confirm_actual >= n_confirm_required）。

    2026-10-04（E1）：peek（status=ok 但样本未满）不算终态。字段缺失视为
    非终态（走 E2 节流自愈），同时防御 None 参与比较崩溃。
    """
    if not isinstance(v, dict) or v.get("status") != "ok":
        return False
    n_act = v.get("n_confirm_actual")
    n_req = v.get("n_confirm_required")
    return n_act is not None and n_req is not None and n_act >= n_req


def _maybe_enqueue_confirmations(log, now_ts):
    registry = load_preregistry(PREREGISTRY_PATH)
    blocked = rl.in_flight_ids(QUEUE, INPROGRESS)
    snap = _active_protocol_snapshot(REGISTRY)
    # 2026-10-04（E1）：只有满样终态裁决才算「已跑过」。D1 闸门只保证有
    # 1 根 bar 越过 confirm_from_ts，不保证 1199/986 个带 24h 前向标签的
    # 样本已就位——数据恢复后的首裁决必然是 status=ok 的未满样 peek
    # （_finalize_confirmation_verdict 的既有语义），若把 peek 计入
    # already，该预注册将永不再派发，n_confirm_required 永远到不了，
    # 确认通道静默死亡。no_data / error / timeout 墓碑同理不占坑；
    # 重派频次由 E2 节流兜底，不会 churn。
    already = {
        v.get("prereg_id") for v in (snap or {}).values()
        if isinstance(v, dict) and v.get("prereg_id")
        and _confirmation_is_final(v)
    }
    pool = load_covariate_pool()

    def family_for(cov):
        return (pool.get(cov) or {}).get("family")

    rows = due_confirmations(
        registry, now_ts, blocked, already, _experiment_fp_for, family_for)
    # 2026-10-03（D1）：数据未越过 confirm_from_ts 的先不派发 —— 否则空评估 +
    # no_data 墓碑 + 去重失效 = 每轮重复入队。已在队里的不受影响。
    rows = [r for r in rows
            if _confirm_data_ready(r["symbol"], r.get("confirm_from_ts") or "")]
    # 2026-10-04（E2）：非终态结果不永久占坑，但每 prereg 至少间隔 6h 才重派。
    # 否则未满样期间每 ~5.7 分钟一条 peek/墓碑（~250 行/天 × ~50 天填充期
    # ≈ 1.2 万行/prereg），等于把 D1 修掉的死循环换个形式请回来。
    _now_r = time.time()
    throttled = set()
    kept = []
    for r in rows:
        _pid = r.get("prereg_id") or ""
        if _now_r - _CONFIRM_REDISPATCH.get(_pid, 0.0) < _CONFIRM_REDISPATCH_TTL_S:
            throttled.add(_pid)
            continue
        kept.append(r)
    rows = kept
    produced = {row["prereg_id"] for row in rows}
    for src in registry:
        if not isinstance(src, dict) or src.get("terminal_state") not in (None, ""):
            continue
        confirm_from = src.get("confirm_from_ts")
        if not isinstance(confirm_from, str) or confirm_from > now_ts:
            continue
        if src.get("prereg_id") in already or src.get("prereg_id") in produced:
            continue
        # 2026-10-03：确认通道要跑 1.2–2.0 年，无条件每轮记账会写出
        # 30–40 万条/年（实测 17 分钟 8 条）。同一 prereg 每 6h 记一次。
        _pid = src.get("prereg_id") or ""
        _last = _CONFIRMATION_NOTICE.get(_pid, 0.0)
        _now = time.time()
        if _now - _last < _CONFIRMATION_NOTICE_TTL_S:
            continue
        _CONFIRMATION_NOTICE[_pid] = _now
        _state = ("redispatch_throttle"
                  if (src.get("prereg_id") or "") in throttled else "not_ready")
        _log_decision(log, "confirmation_not_enqueued",
                      src.get("prereg_id") or "",
                      [str(src.get("symbol") or ""), _state])
    if not rows:
        return 0
    added = 0
    members = load_family_members(FAMILY_REGISTRY)
    for row in rows:
        try:
            family_key = family_key_for(row["symbol"])
            proposal = {
                "prereg_id": row["prereg_id"],
                "symbol": row["symbol"],
                "variant_id": row["variant_id"],
                "family_key": family_key,
            }
            family_members = [
                member for member in members
                if member.get("family_key") == family_key
            ]
            # 已登记只跳过再次 register。没进快照、也不在队里时仍可入队一次。
            registered = any(
                member.get("variant_id") == row.get("variant_id")
                for member in family_members
            )
            if not registered:
                decision = dispatch_confirmation(proposal, registry, family_members)
                if not decision["accepted"] or str(decision.get("registration") or "").startswith("rejected"):
                    _log_decision(log, "confirmation_rejected",
                                  decision.get("reason") or decision.get("registration") or "",
                                  [row["variant_id"]])
                    continue
                members = _merge_family_members(members, family_key, decision.get("members") or [])
                save_family_members(FAMILY_REGISTRY, members)
            n = rl.queue_enqueue(QUEUE, [row], dead=set(), existing=set())
            added += n
            if n:
                _log_decision(log, "confirmation_enqueued", row["prereg_id"], [row["variant_id"]])
                _CONFIRM_REDISPATCH[row["prereg_id"]] = time.time()
        except Exception as e:
            _log_decision(log, "confirmation_enqueue_error", str(e),
                          [str(row.get("variant_id") or "")])
    return added


def _finalize_confirmation_verdict(verdict, members, now):
    """样本未满只 peek。不把 fdr_pass 写成 True，不设 request_early_seal。"""
    if not isinstance(verdict, dict) or verdict.get("run_mode") != "confirmation":
        return None
    row = dict(verdict)
    if row.get("n_confirm_actual") is None:
        row["n_confirm_actual"] = row.get("n") if row.get("n") is not None else 0
    if row.get("n_confirm_required") is None:
        return None
    row["request_early_seal"] = False
    return finalize_confirmation(row, members, now)


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


def _shutdown_exit():
    """标志为真时走与循环顶相同的干净退出。不收割，不启动新 run，不杀已经在跑的子进程。"""
    if not _SHUTDOWN_REQUESTED:
        return None
    _emit_event("critical", "supervisor_stopped", {
        "reason": "signal_received",
        "exit_code": 0,
        "uptime_s": round(time.time() - _START_TIME, 1),
    })
    return 0


def _sleep_interruptible(seconds):
    """最多睡 seconds 秒。每 1 秒看一次标志。处理函数本身仍然只置标志。"""
    remaining = max(1, int(seconds))
    while remaining > 0:
        if _SHUTDOWN_REQUESTED:
            return
        time.sleep(1)
        remaining -= 1


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

def _norm_search_policy(goal):
    """spec 2026-10-05 §6.1：search_policy ∈ {off, shadow, enforce}，缺省 off。

    - off：批准前后默认，收割行为与今日相同。
    - shadow：树检查照常求值，只进拒绝计数与决策日志（plan 2.9）。
    - enforce：§6.2 起的拒绝生效（plan 2.2）。
    非法值 fail-closed 回 off 并 warning 留痕（打错键不得静默改变收割行为）。
    精确匹配三个字面量、不做空白归一：带引号的病态值（如 " enforce"）必须
    留痕走 off，不得无痕激活拒绝（审核 NIT-1，2026-10-06）。
    goal 每 poll 热重载（main 循环 load_goal，2026-09-08 起与 budgets/
    cadence 同一热重载设计），宿主改键下一轮 poll 生效、无需重启
    （审核 MINOR-1 勘正：此前「需重启」的说法与事实相反）。
    """
    raw = (goal or {}).get("search_policy", "off")
    if raw is None:
        return "off"
    if raw in ("off", "shadow", "enforce"):
        return raw
    logging.warning("search_policy 非法值 %r → 按 off 处理"
                    "（合法值 off|shadow|enforce，精确匹配）", raw)
    return "off"

def _goal_target_symbols(goal):
    cad = (goal or {}).get("cadence") or {}
    raw = cad.get("target_symbols") or []
    out = []
    seen = set()
    for item in raw:
        sym = str(item).lower().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out

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
    r = subprocess.run([_praxist_bin(), *args], capture_output=True, text=True, env=env)
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

def symbol_goal_tier(variants, symbol, max_history_n=None):
    """三档。不读文件。

    计入：counts_as_success 为真，或已落盘的 run_label 恰好是 confirmed 且 fdr_pass 为真。
    不补写裁决里没有的分类字段。
    """
    import preregistry as _prereg

    n_confirm_required = _prereg.n_confirm_required_for_symbol(symbol)
    n_confirmed_variants = 0
    for row in variants:
        try:
            ok = _prereg.counts_as_success(row) is True
        except (TypeError, ValueError):
            ok = False
        getter = getattr(row, "get", None)
        if not ok and callable(getter):
            ok = (
                getter("run_label") == "confirmed"
                and getter("fdr_pass") is True
            )
        if ok:
            n_confirmed_variants += 1
    if n_confirmed_variants >= 1:
        tier = "可预测"
    elif max_history_n is not None and max_history_n < n_confirm_required:
        tier = "当前不可验证"
    else:
        tier = "需更多样本"
    return {
        "tier": tier,
        "n_confirmed_variants": n_confirmed_variants,
    }

def build_snapshot(registry_path, cycles_done, cpu_hours_used, tokens_used_m):
    # 跨协议不可比的裁决不得进入目标统计：无指纹 / 旧指纹的行一律排除。
    # jsonl 不改写，完整历史仍可用 rl.load_snapshot(path) 不带参数读到。
    snap = rl.load_snapshot(registry_path,
                            only_protocol=_current_protocol_fingerprint())
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
    # v23: v2 过门变体的 min dir_acc (pass_variants = gate_pass 且 fdr_pass;
    # v1 legacy: gate_pass 且 ev>0);
    # 无过门变体 (或无数值 dir_acc) 时为 None, goal 条件用 is not None 防护判 unmet 而非 eval error。
    pass_dir_accs = [float(v["dir_acc"]) for v in passing
                     if isinstance(v.get("dir_acc"), (int, float))]
    min_pass_variant_dir_acc = min(pass_dir_accs) if pass_dir_accs else None
    # Phase 1: 基础质量门槛
    n_gate_pass_variants = len([v for v in snap.get("variants", {}).values() if v.get("gate_pass")])
    gate_pass_dir_accs = [float(v["dir_acc"]) for v in snap.get("variants", {}).values() 
                          if v.get("gate_pass") and isinstance(v.get("dir_acc"), (int, float))]
    avg_dir_acc_gate_pass = sum(gate_pass_dir_accs) / len(gate_pass_dir_accs) if gate_pass_dir_accs else 0.0
    
    # Phase 2: 高质量变体
    n_tier_a_or_b = len([v for v in snap.get("variants", {}).values() 
                         if v.get("tier") in ["A", "B"]])
    n_symbols_represented = len(symbols_hit)
    
    # Phase 3: 稳定性验证 (placeholder - need actual multi-seed validation data)
    n_validated_multi_seed = 0  # TODO: implement multi-seed validation tracking
    decay_below_threshold = 0  # TODO: implement decay tracking
    
    # 定义目标品种集
    TARGET_SYMBOLS = {"m", "ss", "sr", "cj", "jd", "lh", "eg", "rb", "i", "p", "y", "cf", 
                      "bu", "fu", "ta", "ma", "fg", "ur", "px", "oi", "sh", "sp", "ao", "sc"}
    
    # 按品种统计指标
    symbol_stats = {}
    for symbol in TARGET_SYMBOLS:
        symbol_variants = [
            v for v in snap.values()
            if isinstance(v, dict) and v.get("symbol") == symbol
        ]
        symbol_gate_pass = [v for v in symbol_variants if v.get("gate_pass")]
        symbol_tier_a_b = [v for v in symbol_variants if v.get("tier") in ["A", "B"]]
        
        # Phase 1: 基础质量门槛
        n_gate_pass = len(symbol_gate_pass)
        gate_pass_dir_accs = [float(v["dir_acc"]) for v in symbol_gate_pass 
                              if isinstance(v.get("dir_acc"), (int, float))]
        avg_dir_acc = sum(gate_pass_dir_accs) / len(gate_pass_dir_accs) if gate_pass_dir_accs else 0.0
        
        # Phase 2: 高质量变体
        n_tier_a_b = len(symbol_tier_a_b)
        
        # Phase 3 的 multi_seed / decay 仍未实现，不在这里发明通过条件。
        n_validated = 0
        n_decay = 0

        judged = symbol_goal_tier(symbol_variants, symbol)
        phase1_pass = judged["tier"] == "可预测"
        phase2_pass = False
        phase3_pass = False

        symbol_stats[symbol] = {
            "n_gate_pass": n_gate_pass,
            "avg_dir_acc": avg_dir_acc,
            "n_tier_a_b": n_tier_a_b,
            "n_validated": n_validated,
            "n_decay": n_decay,
            "phase1_pass": phase1_pass,
            "phase2_pass": phase2_pass,
            "phase3_pass": phase3_pass,
            "tier": judged["tier"],
            "n_confirmed_variants": judged["n_confirmed_variants"],
        }
    
    # 检查所有品种是否都通过各阶段
    all_symbols_pass_phase1 = all(stats["phase1_pass"] for stats in symbol_stats.values())
    all_symbols_pass_phase2 = all(stats["phase2_pass"] for stats in symbol_stats.values())
    all_symbols_pass_phase3 = all(stats["phase3_pass"] for stats in symbol_stats.values())
    
    # 统计通过各阶段的品种数
    n_symbols_pass_phase1 = sum(1 for stats in symbol_stats.values() if stats["phase1_pass"])
    n_symbols_pass_phase2 = sum(1 for stats in symbol_stats.values() if stats["phase2_pass"])
    n_symbols_pass_phase3 = sum(1 for stats in symbol_stats.values() if stats["phase3_pass"])
    
    return {
        "variants": snap,
        "symbols_hit": symbols_hit,
        "families_hit": families_hit,
        "cycles_done": cycles_done,
        "cpu_hours_used": cpu_hours_used,
        "tokens_used_m": tokens_used_m,
        # Legacy metrics (keep for backward compatibility)
        "n_one_star_symbols_hit": n_one_star_symbols_hit,
        "n_unique_pass_variants": n_unique_pass_variants,
        "n_families_hit": n_families_hit,
        "min_pass_variant_dir_acc": min_pass_variant_dir_acc,
        # Per-symbol metrics
        "symbol_stats": symbol_stats,
        "target_symbols": TARGET_SYMBOLS,
        # Phase pass status (all symbols)
        "all_symbols_pass_phase1": all_symbols_pass_phase1,
        "all_symbols_pass_phase2": all_symbols_pass_phase2,
        "all_symbols_pass_phase3": all_symbols_pass_phase3,
        # Phase pass counts
        "n_symbols_pass_phase1": n_symbols_pass_phase1,
        "n_symbols_pass_phase2": n_symbols_pass_phase2,
        "n_symbols_pass_phase3": n_symbols_pass_phase3,
        "n_target_symbols": len(TARGET_SYMBOLS),
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
            fam = resolve_cov_family({"cov_override": cov})
            fp = _experiment_fp_for(symbol, cov)
            if fam == "unknown" or fp is None:
                continue  # W6.4: 身份不可得 → 跳过, 不回退旧式 symbol_cov
            vid = ef.build_variant_id(symbol, fam, fp)
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


def _protocol_section_line(fp):
    """节级指纹。没有主协议组时写 none，避免编造一代协议。"""
    if isinstance(fp, str) and fp:
        return "protocol %s" % fp[:12]
    return "protocol (none)"


def materialize_known_verdicts(snapshot, dest_path, *, proposed_ids=None,
                               status_map=None, queue_ids=None, root=None,
                               excluded_items=None, commitments_path=None):
    if status_map is None:
        status_map = load_symbol_status()
    if queue_ids is None:
        queue_ids = rl.in_flight_ids(QUEUE, INPROGRESS)
    if proposed_ids is None:
        proposed_ids = collect_proposed_variant_ids(root or FM_ROOT)

    lines = ["## Known aligned verdicts (supervisor snapshot)",
             "v2 pass (gate_pass=True AND fdr_pass=True AND p_value NOT NULL AND run_mode='confirmation'): already solved, do NOT re-propose.",
             "v1 legacy: pass by ev>0 (legacy econ caliber, schema=v1 entries only).",
             "hard-gate-but-losing (gate_pass=True but not fdr_pass): 过硬门但未过统计检验; not a success; do not re-propose as solved.",
             "DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.",
             ""]
    items = list(snapshot.values()) if isinstance(snapshot, dict) else []

    # ── N3: _primary_fp 排名守卫 (spec W1.5「排序与比较的守卫」) ──
    # 不同 protocol_fingerprint 的 dir_acc 不可直接比较 (协议不同 = 评估口径不同).
    # 主协议组选择: 优先含 confirmation 运行的组, 否则成员最多的组.
    # 其余协议组的 verdict 不进主排名, 单独标注.
    _proto_groups = {}
    for _v in items:
        _fp = _v.get("protocol_fingerprint")
        _proto_groups.setdefault(_fp, []).append(_v)
    _primary_fp = next(
        (fp for fp, g in _proto_groups.items()
         if any(str(_v.get("run_mode")) == "confirmation" for _v in g)),
        None)
    if _primary_fp is None and _proto_groups:
        _primary_fp = max(_proto_groups, key=lambda f: len(_proto_groups[f]))
    _items = sorted(_proto_groups.get(_primary_fp, items),
                    key=lambda v: str(v.get("symbol") or "").lower())
    # 按品种预计算主协议组 best dir_acc (排名字段只取主组).
    _best_by_sym = {}
    for v in _items:
        _sym = str(v.get("symbol") or "").lower()
        _da = v.get("dir_acc")
        if isinstance(_da, (int, float)) and not isinstance(_da, bool):
            _da = float(_da)
            if _da == _da and -1e308 < _da < 1e308:
                if _sym not in _best_by_sym or _da > _best_by_sym[_sym]:
                    _best_by_sym[_sym] = _da

    # ── T1 (2026-10-05): 旧协议先验注记（仅上下文，不进主排名） ──
    # excluded_items: 调用侧传入被 only_protocol 过滤掉的行（dict 或 list）。
    # None 时从输入内非主协议组兜底推导——只认「有旧指纹」的行；
    # fp=None 的 v1 legacy 行不进注记（无指纹不构成「旧协议」，也不是当前证据）。
    if excluded_items is None:
        _excl = []
        for _fp, _grp in _proto_groups.items():
            if _fp == _primary_fp or _fp is None:
                continue
            _excl.extend(_grp)
    else:
        _excl = (list(excluded_items.values())
                 if isinstance(excluded_items, dict)
                 else list(excluded_items))
        # 安全网：fp == 主协议的行不得进注记区（调用侧混入时防重复计入）。
        _excl = [v for v in _excl if isinstance(v, dict)
                 and v.get("protocol_fingerprint") != _primary_fp]
    _excl_fp_rows = [v for v in _excl
                     if isinstance(v.get("protocol_fingerprint"), str)
                     and v.get("protocol_fingerprint")]
    _excl_fp_groups = sorted({v["protocol_fingerprint"] for v in _excl_fp_rows})
    # 头部锚点：快照时间 + 主协议指纹 + 源 registry mtime（peer 引用证据时的出处）。
    try:
        _reg_mtime = datetime.fromtimestamp(
            os.path.getmtime(REGISTRY)).isoformat()
    except Exception:
        _reg_mtime = "n/a"
    _fp8 = (_primary_fp[:8]
            if isinstance(_primary_fp, str) and _primary_fp else "none")
    lines.append("generated_at=%s protocol_fp8=%s registry_mtime=%s"
                 % (datetime.now().isoformat(), _fp8, _reg_mtime))
    # ## Symbol status (full GOAL_SYMBOLS_SET, never truncated)
    lines.append("## Symbol status")
    lines.append(_protocol_section_line(_primary_fp))
    lines.append(
        "按协议指纹分组排名；另有 %d 个协议组的 %d 条 verdict 未进主排名"
        "（见 Old-protocol priors，仅上下文）。"
        % (len(_excl_fp_groups), len(_excl_fp_rows)))
    for sym in sorted(GOAL_SYMBOLS_SET):
        n_ok = 0
        n_pass = 0
        for v in items:
            if str(v.get("symbol") or "").lower() != sym:
                continue
            if v.get("status", "ok") == "ok":
                n_ok += 1
            if v.get("gate_pass"):
                n_pass += 1
        best = _best_by_sym.get(sym)
        rec = status_map.get(sym) or {}
        sym_status = str(rec.get("status") or "ACTIVE").upper()
        if sym_status == "DEAD":
            label = "SYMBOL_DEAD"
        elif sym_status == "HOLD":
            label = "HOLD"
        else:
            label = "ACTIVE"
        best_s = ("%.3f" % best) if best is not None else "n/a"
        line = "- %s: %s, n_ok=%d, n_pass=%d, best=%s" % (
            sym, label, n_ok, n_pass, best_s)
        reason = rec.get("reason")
        if reason:
            line += " — %s" % reason
        if sym_status == "DEAD":
            line += " — 不要提案"
        elif sym_status == "HOLD":
            hg = rec.get("hold_generations")
            if hg is not None:
                line += " — 暂停 %s 代" % hg
        lines.append(line)
    lines.append("")
    clue_lines = _effective_clue_lines(items)
    if clue_lines and clue_lines[0].startswith("## Effective clues"):
        clue_lines.insert(1, _protocol_section_line(_primary_fp))
    lines.extend(clue_lines)
    lines.extend(st.render_open_trees(
        st.load_tree_index(commitments_path or SEARCH_COMMITMENTS_PATH),
        snapshot if isinstance(snapshot, dict) else {}))
    lines.extend(_dead_family_lines(items, _primary_fp))
    lines.extend(_cross_matrix_lines(_items, _primary_fp))
    lines.extend(_old_protocol_prior_lines(_excl_fp_rows))
    lines.extend(_locked_window_lines(
        snapshot if isinstance(snapshot, dict) else {}, root))

    # ## Do not re-propose; source priority: verdict > queue > proposed
    lines.append("## Do not re-propose (variant_id)")
    lines.append(_protocol_section_line(_primary_fp))
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
    # items 已按 (gate_pass 优先, dir_acc 降序) 排序。截断只能切尾部：
    # gate_pass 行是「已解出、不要再提」的集合，切掉它会让 peer 重复提案。
    _shown = [v for v in items if v.get("gate_pass")]
    _shown += [v for v in items if not v.get("gate_pass")][:max(0, 80 - len(_shown))]
    for v in _shown:
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
        own_fp = v.get("protocol_fingerprint")
        vid = v.get("variant_id")
        if isinstance(own_fp, str) and own_fp:
            vid = "[%s] %s" % (own_fp[:12], vid)
        lines.append("- {0}: {1}, gate_pass={2}, ev={3}, n={4}, status={5}".format(
            vid, state, v.get("gate_pass"), v.get("ev"),
            v.get("n"), status))
    if len(items) > len(_shown):
        lines.append("verdicts_truncated=%d" % (len(items) - len(_shown)))
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
    """True if snapshot has an ok+unpassed+confirmable verdict on this symbol or this cov.

    2026-10-03：只认可确认 DM 的失败（见 _is_confirmable_failure）。描述性行不是
    检验结论，不能用来否决新提案——否则确认产出前几乎每份提案都会被
    no_failure_delta 拒收（实测单轮拒 1,922 份、可用候选 7 轮内 123→47）。
    """
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if not _is_confirmable_failure(v):
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
             "仅当前协议，旧协议已滤除；分母含描述性裁决。",
             "### Passing families"]
    passing = [(fam, fam_pass[fam]) for fam in fam_pass if fam_pass[fam] > 0]
    passing.sort(key=lambda x: (-x[1], x[0]))
    if passing:
        for fam, n in passing:
            n_ok = fam_ok.get(fam, 0)
            lines.append("- %s: %d/%d gate_pass%s"
                         % (fam, n, n_ok, " low-n" if n_ok < 10 else ""))
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
    lines.append("ok 含描述性裁决。family_dead 只看 Dead families。")
    weak = [fam for fam, n in fam_ok.items()
            if n >= 4 and fam_pass.get(fam, 0) == 0]
    weak.sort()
    if weak:
        for fam in weak:
            n_ok = fam_ok[fam]
            lines.append("- %s: 0/%d gate_pass%s"
                         % (fam, n_ok, " low-n" if n_ok < 10 else ""))
    else:
        lines.append("- (none)")
    lines.append("")
    return lines


def _cross_matrix_lines(items, primary_fp, max_rows=None):
    """品种×族交叉矩阵（pass/n，仅当前协议主组）— T1 2026-10-05。

    只列有 ok 裁决的品种；每格 `fam p/n`，n<10 追加 low-n（不出现裸比率）。
    品种行数超出预算截断并注明。
    """
    counts = {}
    for v in items:
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        sym = str(v.get("symbol") or "").lower()
        fam = _verdict_family(v)
        if not sym or not fam:
            continue
        p, n = counts.get((sym, fam), (0, 0))
        counts[(sym, fam)] = (p + (1 if v.get("gate_pass") else 0), n + 1)
    lines = ["## Symbol x family (pass/n, current protocol)",
             _protocol_section_line(primary_fp)]
    if not counts:
        lines.append("- (none)")
        lines.append("")
        return lines
    if max_rows is None:
        max_rows = CROSS_MATRIX_MAX_ROWS
    try:
        max_rows = int(max_rows)
    except (TypeError, ValueError):
        max_rows = 0
    syms = sorted({s for (s, _f) in counts})
    shown = syms[:max(0, max_rows)]
    for sym in shown:
        fams = sorted(f for (s, f) in counts if s == sym)
        cells = []
        for fam in fams:
            p, n = counts[(sym, fam)]
            cell = "%s %d/%d" % (fam, p, n)
            if n < 10:
                cell += " low-n"
            cells.append(cell)
        lines.append("- %s: %s" % (sym, ", ".join(cells)))
    if len(syms) > len(shown):
        lines.append("cross_matrix_truncated=%d" % (len(syms) - len(shown)))
    lines.append("")
    return lines


def _prior_class(v):
    """旧协议先验的展示优先级：confirmation > gate_pass > 其余。"""
    if str(v.get("run_mode") or "") == "confirmation":
        return 0
    if v.get("gate_pass"):
        return 1
    return 2


def _old_protocol_prior_lines(rows, max_rows=None):
    """旧协议先验注记 — T1 2026-10-05。仅上下文，不构成当前证据，不进主排名。

    每 (symbol, cov_override) 取最优行（confirmation > gate_pass > 其余，
    同级取 decided_at 最新）；行数超出预算截断并注明。
    """
    if max_rows is None:
        max_rows = OLD_PRIORS_MAX_ROWS
    try:
        max_rows = int(max_rows)
    except (TypeError, ValueError):
        max_rows = 0
    lines = ["## Old-protocol priors (context only, NOT current evidence)",
             "旧协议 = protocol_fingerprint 不同的历史裁决；仅上下文，不构成当前证据。"]
    best = {}
    for v in rows:
        if not isinstance(v, dict):
            continue
        fp = v.get("protocol_fingerprint")
        if not (isinstance(fp, str) and fp):
            continue
        key = (str(v.get("symbol") or "").lower(),
               str(v.get("cov_override") or ""))
        cur = best.get(key)
        if (cur is None or _prior_class(v) < _prior_class(cur)
                or (_prior_class(v) == _prior_class(cur)
                    and str(v.get("decided_at") or "")
                    > str(cur.get("decided_at") or ""))):
            best[key] = v
    if not best:
        lines.append("- (none)")
        lines.append("")
        return lines
    ordered = sorted(best.values(),
                     key=lambda v: str(v.get("decided_at") or ""),
                     reverse=True)
    ordered.sort(key=_prior_class)  # 稳定排序：类内保持 decided_at 降序
    shown = ordered[:max(0, max_rows)]
    for v in shown:
        fp = v.get("protocol_fingerprint")
        da = _finite_dir_acc(v)
        lines.append(
            "- [%s] %s: symbol=%s cov=%s decided_at=%s gate_pass=%s "
            "dir_acc=%s — 仅上下文，不构成当前证据"
            % (fp[:12], v.get("variant_id"),
               str(v.get("symbol") or "").lower(),
               v.get("cov_override"), v.get("decided_at") or "n/a",
               bool(v.get("gate_pass")),
               ("%.3f" % da) if da is not None else "n/a"))
    if len(ordered) > len(shown):
        lines.append("old_priors_truncated=%d" % (len(ordered) - len(shown)))
    lines.append("")
    return lines


def load_covariate_pool():
    """读协变量池 covariate_pool.json → cov dict。fail-open 返回 {}。

    读取时校验 horizon_known 契约（spec §4.5 W5.1）。校验失败**不**阻断
    （与 fail-open 加载一致），但必须把问题打到 stderr —— 一个漏填证据的
    known_ahead 会让下游填充逻辑白得「未来已知」这个最强假设，
    静默通过等于把错误假设喂给消融实验。
    """
    try:
        with open(POOL_PATH, encoding="utf-8") as f:
            pool = json.load(f) or {}
    except Exception as e:
        print("[WARN] covariate pool load failed (fail-open): %s" % e, file=sys.stderr)
        return {}

    try:
        from cascade.cov_family import apply_horizon_known_downgrade
        # spec §4.5 W5.1：缺证据的 known_ahead **不得**保留该标签，
        # 须降级为 unknowable + WARN。仅打 WARN 不降级等于洞没关。
        for name, reason in apply_horizon_known_downgrade(pool):
            print("[WARN] horizon_known 降级: %s -> unknowable（%s）"
                  % (name, reason), file=sys.stderr)
    except Exception as e:  # 降级器本身出错不得阻断加载
        print("[WARN] horizon_known 降级未能执行: %s" % e, file=sys.stderr)

    return pool.get("covariates", {})


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
# 9 个信用品种 (1★ 过门目标); 不跟随 evaluator.ALLOWED_SYMBOLS 膨胀
GOAL_SYMBOLS_SET = frozenset({"m", "ss", "sr", "cj", "jd", "lh", "eg", "rb", "fu"})
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


_CONFIRMATORY_DM = frozenset({"ok", "set_mismatch_ok"})

# 2026-10-03：confirmation_not_enqueued 的节流状态（prereg_id -> 上次记账时间戳）
_CONFIRMATION_NOTICE: dict[str, float] = {}
_CONFIRMATION_NOTICE_TTL_S = 6 * 3600
# 2026-10-04（E2）：非终态确认结果的重派节流（prereg_id -> 上次派发时间戳）。
# 进程内状态：重启后各放行一次（有界），不落盘。
_CONFIRM_REDISPATCH: dict[str, float] = {}
_CONFIRM_REDISPATCH_TTL_S = 6 * 3600


def _is_confirmable_failure(v):
    """失败 = 未过门**且** DM 可确认。

    2026-10-03：描述性 DM（set_mismatch_descriptive）与 no_common_cutoff 不是
    检验结论，不能当失败用。确认产出前全库都是描述性行，若把它们算失败，
    _dead_families 会误杀整族、_sector_filter_check 会把板块推向断路器 ——
    与 2026-09-24 饿死同构的陷阱，只是高一层。
    """
    return not v.get("gate_pass") and v.get("dm_status") in _CONFIRMATORY_DM


def _family_confirmatory_counts(rows):
    """与 _dead_families 同一套行。返回 (fam_ok, fam_pass)。"""
    fam_ok = {}
    fam_pass = {}
    for v in rows or []:
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        if v.get("dm_status") not in _CONFIRMATORY_DM:
            continue
        fam = str(v.get("cov_family") or "").strip()
        if not fam:
            continue
        fam_ok[fam] = fam_ok.get(fam, 0) + 1
        if v.get("gate_pass"):
            fam_pass[fam] = fam_pass.get(fam, 0) + 1
    return fam_ok, fam_pass


def _dead_families(snapshot, min_ok=4):
    """一族至少 min_ok 条可确认 DM 的 ok 裁决且 0 条过门，才算死亡。

    dm_status 缺省、set_mismatch_descriptive、no_common_cutoff、
    insufficient_common 都不计数。min_ok 仍是 4。
    run_mode 不读：探索行上的可确认失败同样计数。
    pass 计数是 gate_pass，不调用 pass_variants。
    """
    rows = (snapshot or {}).values() if isinstance(snapshot, dict) else []
    fam_ok, fam_pass = _family_confirmatory_counts(rows)
    return {fam for fam, n in fam_ok.items()
            if n >= min_ok and fam_pass.get(fam, 0) == 0}


def _dead_family_lines(items, primary_fp, min_ok=4):
    """把 _dead_families 的结果写给 peer。不另数全部 ok 行。"""
    fam_ok, fam_pass = _family_confirmatory_counts(items)
    dead = sorted(
        fam for fam, n in fam_ok.items()
        if n >= min_ok and fam_pass.get(fam, 0) == 0)
    lines = [
        "## Dead families",
        _protocol_section_line(primary_fp),
        "判据与 family_dead 相同：只计 dm_status 为 ok 或 set_mismatch_ok 的 ok 行；"
        "条数达到 min_ok 且 gate_pass 为 0 才列入。描述性 DM 不计数。"
        "列入的族会被无条件拒绝。",
    ]
    if not dead:
        lines.append("- (none)")
    else:
        for fam in dead:
            lines.append("- %s: n_ok=%d, n_gate_pass=%d, min_ok=%d" % (
                fam, fam_ok[fam], fam_pass.get(fam, 0), min_ok))
    lines.append("")
    return lines



def _apply_prescreen_score(score, proposal_path):
    """TypeSafe Jev prescreen score adjustment (Phase 2)."""
    if not proposal_path:
        return score
    ps_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if not os.path.exists(ps_path):
        return score
    try:
        with open(ps_path, encoding="utf-8") as _f:
            ps = json.load(_f)
    except (json.JSONDecodeError, OSError):
        return score
    if not isinstance(ps, dict) or ps.get("status") != "success":
        return score
    skip = ps.get("skip_suggested")
    novelty = str(ps.get("novelty") or "").strip().lower()
    plausibility = ps.get("mechanism_plausibility")
    effect_size = ps.get("effect_size")
    if skip is True:
        if novelty == "invalid":
            return score - 100.0
        if novelty == "redundant" and (effect_size is None or effect_size <= 1):
            return score - 30.0
        if plausibility is not None and isinstance(plausibility, (int, float)) and plausibility < 0.4:
            return score - 20.0
        # skip 第 4 分支: effect==0 且 plausibility ∈ [0.4, 0.6) -- 无新增信息且可信度不足以补偿
        if (effect_size == 0
                and isinstance(plausibility, (int, float))
                and plausibility < 0.6):
            return score - 15.0
    if skip is False and isinstance(effect_size, (int, float)) and effect_size >= 2:
        score += 10.0
    if novelty in ("novel", "extension") and isinstance(plausibility, (int, float)) and plausibility > 0.6:
        score += 5.0
    return score

def _prescreen_async(p, proposal_path, symbol):
    """Fire-and-forget TypeSafe Jev prescreen (daemon thread, 不阻塞 harvest)。

    prescreen 是软建议伴随元数据，不应拖慢 supervisor 收割循环。
    - daemon=True: 进程退出时自动杀死，不阻塞 shutdown
    - 失败静默丢弃 (记录 warning)，不影响主流程
    - 幂等守卫: 已有 status=success 的结果则跳过，避免每轮重复付费调用
    - 仍通过原子写盘落盘，慢环读到的一定是完整结果
    - 注意: 因异步, 本轮 _proposal_priority_score 读不到刚写入的结果,
      Phase2 降权在下一个收割周期才生效 (新提案首次调度用未调整分)。
    """
    # 幂等守卫 (WARN-3): 已有成功 prescreen 结果则不再重复调用
    try:
        from cascade.typesafe_prescreen import prescreen_and_save
    except Exception as _e:
        logging.warning("TypeSafe 预筛导入失败 (%s): %s", proposal_path, _e)
        return

    _existing_ps = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if os.path.exists(_existing_ps):
        try:
            with open(_existing_ps, encoding="utf-8") as _f:
                if json.load(_f).get("status") == "success":
                    return
        except (json.JSONDecodeError, OSError):
            pass  # 损坏/失败结果 → 允许重试

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _verdicts_path = os.path.join(_root, "task_FM", "config", "aligned_verdicts.jsonl")
    _menu_path = os.path.join(_root, "task_FM", "covariate_menu.inc.md")

    def _run():
        try:
            _history = []
            if os.path.exists(_verdicts_path):
                with open(_verdicts_path, encoding="utf-8") as f:
                    _history = [json.loads(l) for l in f if l.strip()]
            _menu = {}
            if os.path.exists(_menu_path):
                with open(_menu_path, encoding="utf-8") as f:
                    _menu = {"text": f.read()}
            prescreen_and_save(
                proposal=p,
                proposal_path=proposal_path,
                symbol=symbol,
                verdict_history=_history,
                covariate_menu=_menu,
            )
        except Exception as _e:
            logging.warning("TypeSafe 预筛异步调用失败 (%s): %s", proposal_path, _e)

    threading.Thread(target=_run, daemon=True).start()


def _proposal_priority_score(prop, cov, symbol, snapshot, status_map=None, repeat_counts=None, proposal_path=None):
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
    # 注: 此 vid 是与快环 shared_findings.variant_name (旧式 symbol_cov) 的 join 键,
    # 不是 W6.4 实验身份 —— 勿改 build_variant_id, 否则 repeat penalty 静默失效。
    vid = "%s_%s" % (symbol, cov)
    repeat_counts = repeat_counts or {}
    n_runs = repeat_counts.get(vid, 0)
    if n_runs >= 3:
        score -= 20.0 + 10.0 * (n_runs - 3)  # 3→-20, 4→-30, 5→-40
    elif n_runs >= 2:
        score -= 8.0
    score = _apply_prescreen_score(score, proposal_path)
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

# ---------------------------------------------------------------------------
# PR-B6 提案质量门
# ---------------------------------------------------------------------------
# 口径说明: v2 verdict (fm.aligned_verdict.v2) 不含 pf/ev/ic —— 生产 registry
# 143 条全为 v2。因此评分与过滤一律基于 v2 可观测字段 (gate_pass / dir_acc /
# decided_at / cov_override / symbol)，不引入不可得字段。

MIN_QUALITY_SCORE = 0.0        # score < 该值 → 拒绝 (0.0 = 仅拦截净负分提案)
# T1 (2026-10-05): known_verdicts 注入通道行数预算（module 常量，供测试 monkeypatch）
CROSS_MATRIX_MAX_ROWS = 40     # 品种×族矩阵最多列出的品种行数（超出截断注明）
OLD_PRIORS_MAX_ROWS = 20       # 旧协议先验注记最多行数（超出截断注明）
LOCKED_WINDOW_MAX_ROWS = 40    # 同窗锁定组合最多行数（超出截断注明）
# T2 (2026-10-05): 已成功组合复跑的 success_delta 增量论证最少字数
SUCCESS_DELTA_MIN_CHARS = 20
STALE_DATA_DAYS = 3            # 上海日历年龄 > 此值 → data_stale 放行；等于此值不放行
# SECTOR_BLOCK_MIN_FAILED 已废弃: 改为 sector_map 定义的全部品种都失败才拦截
# (见 _sector_filter_check 的 circuit-breaker 注释)
COV_CROSS_FAIL_MIN = 3         # 该协变量在其他品种失败 >= N 次且从无过门 → 拦截
SYMBOL_FAIL_WINDOW = 5         # 品种最近 N 次裁决全失败 → 扣分
COV_FAIL_WINDOW = 3            # 协变量在其他品种最近 N 次全失败 → 扣分


def _verdict_sort_key(v):
    """按 decided_at 排序；缺失/非字符串视为最早（确定性，无隐式时区假设）。"""
    d = v.get("decided_at")
    return d if isinstance(d, str) else ""


def _latest_verdict_per_symbol(snapshot):
    """每个品种最近一次 ok 裁决 → {symbol: verdict}

    当 decided_at 相同（或缺失导致都排序为 ""）时，取**最后**遇到的裁决
    (使用 `>=` 而非 `>`)。jsonl 是追加写入，同 key 时后到的通常更新，
    因此 `>=` 在 ties 时给出更符合直觉的"最新"裁决。
    """
    latest = {}
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        s = str(v.get("symbol") or "").lower().strip()
        if not s:
            continue
        cur = latest.get(s)
        if cur is None or _verdict_sort_key(v) >= _verdict_sort_key(cur):
            latest[s] = v
    return latest


def _recent_ok_verdicts(snapshot, predicate, n):
    """最近 n 条满足 predicate 的 ok 裁决（按 decided_at 升序取尾部）。"""
    rows = [v for v in (snapshot or {}).values()
            if isinstance(v, dict) and v.get("status", "ok") == "ok" and predicate(v)]
    rows.sort(key=_verdict_sort_key)
    return rows[-n:] if n > 0 else []


def _prescreen_plausibility(proposal_path):
    """读取 prescreen 侧写的 mechanism_plausibility；缺失/非法 → None。"""
    if not proposal_path:
        return None
    ps_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if not os.path.exists(ps_path):
        return None
    try:
        with open(ps_path, encoding="utf-8") as f:
            ps = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(ps, dict) or ps.get("status") != "success":
        return None
    p = ps.get("mechanism_plausibility")
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        return None
    p = float(p)
    if not (0.0 <= p <= 1.0):
        return None
    return p


def _sector_filter_check(symbol, snapshot):
    """板块级拦截 (circuit-breaker 语义)。

    该品种所属板块在 config.sector_map 中定义的**全部**品种（不是仅有裁决的）
    其最近一次裁决均未过门 → 拦截。未观察到的品种视为"未评估"，不参与失败计数，
    因此未评估的品种不触发拦截。

    这是防饿死设计: 若仅凭 "≥N 个品种失败" 拦截，生产快照中所有三个板块都
    ≥3 失败 → 所有提案被拦 → 慢环饿死 (与 2026-09-24 no_failure_delta 饿死同构)。
    改为 "全部已观察品种 + 全部未观察品种都等于板块成员全集失败" 才拦，
    即只有板块真死透了才拦。

    T7 新增: 当失败数 >= 板块规模 50% 但未达全失败时，打 WARN 预警板块部分退化。

    Returns: (blocked, sector, n_failed)
    """
    from config.sector_map import SECTORS, sector_of
    sector = sector_of(symbol)
    if sector == "other":
        return False, sector, 0
    sector_size = len(SECTORS[sector])  # 板块在 sector_map 中定义的品种总数
    latest = _latest_verdict_per_symbol(snapshot)
    # 2026-10-03：失败数只认可确认的 DM 失败（见 _is_confirmable_failure）。
    # 否则描述性行会把板块推向断路器，而断路器一拦就是全局饿死。
    n_failed = sum(1 for s, v in latest.items()
                   if sector_of(s) == sector and _is_confirmable_failure(v))

    # T7: 板块部分退化预警（50% 阈值）
    if n_failed >= sector_size * 0.5 and n_failed < sector_size:
        logging.warning(
            f"Sector partial degradation: {sector} has {n_failed}/{sector_size} "
            f"symbols failed ({100*n_failed/sector_size:.0f}%). "
            f"Approaching circuit-breaker threshold."
        )

    # 仅当失败数 >= 板块成员总数时拦截（即全部成员都失败，包括未观察到的）
    return n_failed >= sector_size, sector, n_failed


def _covariate_filter_check(cov, symbol, snapshot):
    """协变量跨品种失败拦截。

    该协变量在**其他**品种上失败 >= COV_CROSS_FAIL_MIN 次，且从未在任一品种
    过门 → 拦截。有任一品种过门即放行（品种特异性优先于跨品种共性）。

    Returns: (blocked, n_other_fail, n_pass)
    """
    n_fail = 0
    n_pass = 0
    sym = str(symbol).lower().strip()
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        if str(v.get("cov_override") or "") != cov:
            continue
        if v.get("gate_pass"):
            n_pass += 1
        elif str(v.get("symbol") or "").lower().strip() != sym and _is_confirmable_failure(v):
            # 2026-10-04（E4）：同 _sector_filter_check —— 失败数只认可确认的
            # DM 失败（dm_status ∈ {ok, set_mismatch_ok}）。描述性行（dm_status
            # 缺省 / set_mismatch_descriptive / no_common_cutoff）不得把协变量
            # 推向跨品种拦截。
            n_fail += 1
    return (n_pass == 0 and n_fail >= COV_CROSS_FAIL_MIN), n_fail, n_pass


def _proposal_quality_gate(prop, snapshot, proposal_path=None):
    """基于历史表现的提案质量评分 (PR-B6)。

    评分项（全部基于 v2 可观测字段）：
      +5    该品种有过成功协变量 (gate_pass=True)
      +3    该组合从未测过 (新颖性)
      +3    机制论证完整 (symbol_fit/kill_condition/promote_condition 齐全)
      +10 * prescreen mechanism_plausibility
      -20   该协变量在其他品种最近 COV_FAIL_WINDOW 次裁决全失败
      -15   该品种最近 SYMBOL_FAIL_WINDOW 次裁决全失败

    Returns: (score, breakdown dict)
    """
    symbol = str(prop.get("symbol") or "").lower().strip()
    cov = str(prop.get("cov_override") or "").strip()
    snap = snapshot or {}
    bd = {}

    # +5 该品种有过成功协变量（必须与 pass_variants 严格定义一致，排除探索运行）
    # §1.4: 探索运行不得出现在任何"已确认"表述中
    sym_pass = any(
        isinstance(v, dict)
        and v.get("status", "ok") == "ok"
        and v.get("run_mode") in rl.RUN_MODES
        and v.get("run_mode") != "exploration"
        and v.get("gate_pass")
        and v.get("fdr_pass")
        and v.get("p_value") is not None
        and str(v.get("symbol") or "").lower().strip() == symbol
        for v in snap.values()
    )
    bd["symbol_has_pass"] = 5.0 if sym_pass else 0.0

    # +3 新颖性: 该组合从未出现在 snapshot
    bd["novel_combo"] = 3.0 if ("%s_%s" % (symbol, cov)) not in snap else 0.0

    # +3 机制论证完整
    complete = all(str(prop.get(k) or "").strip()
                   for k in ("symbol_fit", "kill_condition", "promote_condition"))
    bd["mechanism_complete"] = 3.0 if complete else 0.0

    # +10 * prescreen plausibility
    plaus = _prescreen_plausibility(proposal_path)
    bd["prescreen"] = 10.0 * plaus if plaus is not None else 0.0

    # -20 该协变量在其他品种最近 N 次全失败
    cov_recent = _recent_ok_verdicts(
        snap,
        lambda v: str(v.get("cov_override") or "") == cov
        and str(v.get("symbol") or "").lower().strip() != symbol,
        COV_FAIL_WINDOW)
    bd["cov_recent_fail"] = -20.0 if (
        len(cov_recent) == COV_FAIL_WINDOW
        and not any(v.get("gate_pass") for v in cov_recent)) else 0.0

    # -15 该品种最近 M 次全失败
    sym_recent = _recent_ok_verdicts(
        snap,
        lambda v: str(v.get("symbol") or "").lower().strip() == symbol,
        SYMBOL_FAIL_WINDOW)
    bd["symbol_recent_fail"] = -15.0 if (
        len(sym_recent) == SYMBOL_FAIL_WINDOW
        and not any(v.get("gate_pass") for v in sym_recent)) else 0.0

    return sum(bd.values()), bd


def _symbol_has_current_nocov_baseline(symbol, root):
    """当前协议的无协变量基线在，才占慢环座位。指纹算不出来时放行。不生成基线。"""
    fp = _current_protocol_fingerprint()
    if fp is None:
        return True
    from cascade.baseline_paths import baseline_filename
    path = os.path.join(root, "task_FM", "config", baseline_filename(symbol, None))
    status, got = _baseline_protocol_fingerprint(path)
    return status == "ok" and got == fp


def _prior_success_row(snapshot, symbol, cov):
    """snapshot 内该 (symbol, cov_override) 最新一条 ok+gate_pass=True 裁决。

    T2 (2026-10-05)：与失败侧 (_has_prior_failure) 刻意不同口径——成功侧要求
    **品种与协变量同时**命中（失败侧是「品种或协变量」）。理由：已过硬门的
    组合复跑必须有增量论证；仅"品种有过成功"或"协变量在别处成功"不构成
    挤占席位的重复提案。
    """
    best = None
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if v.get("status", "ok") != "ok" or not v.get("gate_pass"):
            continue
        if str(v.get("symbol") or "").lower() != str(symbol or "").lower():
            continue
        if str(v.get("cov_override") or "") != str(cov or ""):
            continue
        if best is None or _verdict_sort_key(v) >= _verdict_sort_key(best):
            best = v
    return best


def _row_eval_end_ts(v, cache=None, root=None):
    """裁决行的评估窗锚 eval_end_ts。

    行字段优先（T2 起由 aligned_slow_loop 落章）；缺失时兜底查 checkpoint：
    行内 checkpoint_path 字段 → root 相对 data/cache/aligned_checkpoints/<vid>.jsonl。
    checkpoint 按行扫描，**末行胜出**（同 run 同锚；续跑多 run 取最新）。
    找不到 → None（调用方 fail-open，不用墙钟猜）。
    """
    ts = v.get("eval_end_ts")
    if isinstance(ts, str) and ts:
        return ts
    vid = str(v.get("variant_id") or "")
    if not vid:
        return None
    cache = {} if cache is None else cache
    row_ts = cache.setdefault("_row_ts", {})
    if vid in row_ts:
        return row_ts[vid]
    ts_found = None
    cands = []
    cp = v.get("checkpoint_path")
    if isinstance(cp, str) and cp:
        cands.append(cp)
    if root:
        cands.append(os.path.join(str(root), "data", "cache",
                                  "aligned_checkpoints", vid + ".jsonl"))
    for path in cands:
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        rec = json.loads(ln)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(rec, dict):
                        t = rec.get("eval_end_ts")
                        if isinstance(t, str) and t:
                            ts_found = t
        # T2c (2026-10-05 审计): UnicodeDecodeError 是 ValueError 子类——
        # 撕裂 checkpoint（崩溃多字节字符）不得穿透炸 harvest。撕裂点前的
        # 可信行保留；候选文件整体不可读时弃读（部分读语义与 OSError 一致）。
        except (OSError, ValueError):
            continue
        if ts_found is not None:
            break
    row_ts[vid] = ts_found
    return ts_found


def _current_window_anchor(snapshot, cache=None, root=None):
    """当前评估窗锚（近似）：全部 ok 裁决行 eval_end_ts 的最大值。

    存量行普遍缺 eval_end_ts 时（T2 上线前）锚可能为 None → 调用方
    fail-open。不引入墙钟：没有可靠锚就不执法。
    """
    anchor = None
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        ts = _row_eval_end_ts(v, cache, root)
        if isinstance(ts, str) and ts and (anchor is None or ts > anchor):
            anchor = ts
    return anchor



def _today_shanghai():
    """上海日历日。测试钉这一个函数，不钉 datetime.now。

    ZoneInfo 不可用时回退 UTC 日历日。这是防御，不是预期失败：
    zoneinfo 与 datetime 都是标准库。
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def _kline_1h_max_dt(symbol):
    """只读 kline_1h 的 MAX(dt)。缺库、空表、SQL 错误 → None。不建库。"""
    import sqlite3
    try:
        from data.config import get_db_path
        path = get_db_path(str(symbol or ""))
    except Exception:
        return None
    if path is None or not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row or row[0] is None:
        return None
    return str(row[0])


def _symbol_data_stale(symbol, cache):
    """日历年龄 > STALE_DATA_DAYS 时为真。读失败、日期坏、未来 bar 都为假。

    cache['_kline_max'] 按 symbol 记原始 MAX(dt)。
    cache['_stale_logged'] 保证同一 cache 里每个 symbol 只打一条 WARNING。
    cache['_probe'] 为真时不打日志（物化锁定名单只探门，不假装有提案被拒）。
    """
    if cache is None:
        cache = {}
    key = str(symbol or "").lower()
    maxes = cache.setdefault("_kline_max", {})
    if key not in maxes:
        maxes[key] = _kline_1h_max_dt(key)
    raw = maxes[key]
    if not isinstance(raw, str) or len(raw) < 10:
        return False
    try:
        bar_day = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    today = _today_shanghai()
    age = (today - bar_day).days
    if age <= STALE_DATA_DAYS:
        return False
    if not cache.get("_probe"):
        logged = cache.setdefault("_stale_logged", set())
        if key not in logged:
            logged.add(key)
            logging.warning(
                "success_gate: %s 数据末端 %s 距上海日历 %s 已 %d 天 > %d → data_stale 放行",
                key, raw, today.isoformat(), age, STALE_DATA_DAYS)
    return True


def _prior_success_class(prior):
    """known_verdicts 图例口径：确认且过 FDR 才是 v2-pass。"""
    if (isinstance(prior, dict)
            and prior.get("fdr_pass")
            and prior.get("p_value") is not None
            and prior.get("run_mode") == "confirmation"):
        return "v2-pass"
    return "hard-gate-but-losing"


def _success_delta_gate(prop, symbol, cov, snapshot, root=None, cache=None):
    """T2 (2026-10-05): 已成功组合的增量论证门。

    同 (symbol, cov_override) 在当前评估窗口已有 ok+gate_pass=True 裁决时，
    复跑提案必须用 success_delta (>=SUCCESS_DELTA_MIN_CHARS 字) 写清相对
    上次成功的增量，否则拒收 no_success_delta。
    逃逸阀（fail-open）：评估窗已平移（prior_ts != anchor）或锚不可得
    （行字段与 checkpoint 均缺失）时放行——这两条不看墙钟。窗口平移后旧成功
    不再是当前窗证据（2026-10-04 审计：09-23→09-30 15:00 窗整体更换同理）。
    数据末端距上海日历超过 STALE_DATA_DAYS 天时另放行 data_stale：锚钉死、
    窗口无法平移，空 success_delta 不再把复跑全部拒掉。新 bar 进入 3 天内
    后这条旁路自行关闭。
    返回 (reject_reason_or_None, state)；state 计入 stats["success_gate_states"]：
    no_prior_success / window_moved / anchor_unavailable / data_stale /
    success_delta_ok / no_success_delta。
    """
    prior = _prior_success_row(snapshot, symbol, cov)
    if prior is None:
        return None, "no_prior_success"
    cache = {} if cache is None else cache
    if "anchor" not in cache:
        cache["anchor"] = _current_window_anchor(snapshot, cache, root)
    anchor = cache["anchor"]
    prior_ts = _row_eval_end_ts(prior, cache, root)
    if prior_ts is None or anchor is None:
        return None, "anchor_unavailable"
    if prior_ts != anchor:
        return None, "window_moved"
    if _symbol_data_stale(symbol, cache):
        return None, "data_stale"
    delta = str((prop or {}).get("success_delta") or "").strip()
    if len(delta) >= SUCCESS_DELTA_MIN_CHARS:
        return None, "success_delta_ok"
    # T2b: 拒收信息带先验分类与 run_mode（known_verdicts 图例口径）——
    # 探索先验（gate 过但 fdr/p_value 缺）不得在日志里被封账为成功。
    # 物化锁定名单会以空 success_delta 探门，cache['_probe'] 时不打拒收日志。
    if not cache.get("_probe"):
        logging.warning(
            "success_gate: %s_%s 复跑缺 success_delta (len=%d < %d) → 拒收 (no_success_delta)；"
            "prior=%s class=%s run_mode=%s eval_end_ts=%s",
            str(symbol or ""), str(cov or ""), len(delta), SUCCESS_DELTA_MIN_CHARS,
            str(prior.get("variant_id") or ""),
            _prior_success_class(prior),
            str(prior.get("run_mode") or "None"), prior_ts)
    return "no_success_delta", "no_success_delta"


def _locked_success_rows(snapshot, root, cache=None):
    """同窗已成功、空 success_delta 会被拒的 prior，每个 (symbol, cov) 一条。

    data_stale / window_moved / anchor_unavailable 不进名单，名单与门同一谓词。
    """
    cache = {} if cache is None else cache
    # 原地写入：_symbol_data_stale 会往这份 cache 填 _kline_max / _stale_logged，这里再写 _probe。
    cache["_probe"] = True
    keys = set()
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if v.get("status", "ok") != "ok" or not v.get("gate_pass"):
            continue
        symbol = str(v.get("symbol") or "").lower()
        cov = str(v.get("cov_override") or "")
        if symbol:
            keys.add((symbol, cov))
    locked = []
    for symbol, cov in sorted(keys):
        reason, state = _success_delta_gate(
            {"success_delta": ""}, symbol, cov, snapshot, root, cache)
        if reason == "no_success_delta" and state == "no_success_delta":
            prior = _prior_success_row(snapshot, symbol, cov)
            if prior is not None:
                locked.append(prior)
    return locked


def _locked_window_lines(snapshot, root):
    """## Locked this window 段落。不含墙钟，保证除 generated_at 外物化幂等。"""
    rows = _locked_success_rows(snapshot, root, cache={})
    lines = [
        "## Locked this window",
        "同评估窗已有 gate_pass=True 的 (symbol, cov)。复跑必须写 success_delta（≥20 字）"
        "并点名 prior。空 success_delta 会被拒 (no_success_delta)。"
        "数据末端距上海日历超过 %d 天时此名单为空。" % STALE_DATA_DAYS,
    ]
    if not rows:
        lines.append("- (none)")
    else:
        cache = {"_probe": True}
        shown = rows[:max(0, LOCKED_WINDOW_MAX_ROWS)]
        for prior in shown:
            symbol = str(prior.get("symbol") or "").lower()
            cov = str(prior.get("cov_override") or "")
            prior_ts = _row_eval_end_ts(prior, cache, root)
            lines.append(
                "- %s cov=%s prior=%s class=%s eval_end_ts=%s" % (
                    symbol, cov, prior.get("variant_id"),
                    _prior_success_class(prior), prior_ts))
        rest = len(rows) - len(shown)
        if rest > 0:
            lines.append("locked_window_truncated=%d" % rest)
    lines.append("")
    return lines


def harvest_proposals(root, snapshot, dead, existing, pool, top_k,
                      aligned_max_points=600, priority_symbols=None,
                      search_policy="off"):
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
             "reject_reasons": {},
             # spec 2026-10-05 §6.1：档位随收割留档（off|shadow|enforce）
             "search_policy": search_policy,
             # PR-B6 质量门计数（键名与 reject_reasons 一致，防止两套计数漂移）
             "quality_below_threshold": 0, "sector_blocked": 0, "cov_cross_fail": 0,
             # T2 (2026-10-05): success 门分类计数（放行侧也计数，供观察口径是否过宽）
             "success_gate_states": {}}
    _sg_cache = {}  # T2: 单次 harvest 内复用评估窗锚与行级 eval_end_ts
    passing_ids = {v["variant_id"] for v in rl.pass_variants(snapshot or {})}
    archived = getattr(ev, "ARCHIVED_COVARIATES", {}) if ev else {}
    valid_covs = getattr(ev, "VALID_COVARIATES", None) if ev else None
    allowed_syms = getattr(ev, "ALLOWED_SYMBOLS", None) if ev else None
    # ── P2.2 / P2.9 (spec §6.2 / §6.1) 搜索树资格门。
    # enforce：拒绝生效，guard-pass 即内存建树/占座。
    # shadow：同一套检查只记「本会拒绝」，不拒绝、不把树字段带进队列、不写账。
    # off：不构造守卫。──
    search_guard = None
    shadow_guard = None
    if search_policy == "enforce":
        search_guard = st.SearchGuard.load(SEARCH_COMMITMENTS_PATH, snapshot or {})
    elif search_policy == "shadow":
        shadow_guard = st.SearchGuard.load(SEARCH_COMMITMENTS_PATH, snapshot or {})
        stats["search_would_reject"] = {}
        stats["search_shadow_log"] = []

    def _reject(reason):
        stats["rejected"] += 1
        stats["reject_reasons"][reason] = stats["reject_reasons"].get(reason, 0) + 1

    candidates = []
    seen_vids = set()
    run_dirs = sorted(glob.glob(os.path.join(root, "task_FM", "experiments", "run_*")),
                      key=os.path.getmtime, reverse=True)
    for run_dir in run_dirs:
        if _SHUTDOWN_REQUESTED:
            # 长扫描不得吃掉停机信号：立刻中止，且不返回半份候选（避免停机途中入队）
            stats["aborted_by_shutdown"] = True
            return [], stats
        for sp in glob.glob(os.path.join(run_dir, "results", "**", "proposals", "*.json"),
                            recursive=True):
            if _SHUTDOWN_REQUESTED:
                stats["aborted_by_shutdown"] = True
                return [], stats
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
            # ── P2.2 (spec §6.2) 树资格检查钉在管道最前（先于池/机制长度/族
            # 死亡/去重/质量门/成功门）。族未解析时跳过守卫，归因仍走下方既有
            # family_unresolved（树拒绝码不覆盖非树归因）。──
            search_info = None
            if search_guard is not None:
                _fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
                if _fam:
                    _pid = os.path.relpath(sp, root)
                    _sr, search_info = search_guard.check(
                        p, symbol, _fam, cov, _pid)
                    if _sr is not None:
                        _reject(_sr); continue
                    # P2.3 (spec §6.7)：落账辅助字段（spec 三字段之外的记账
                    # 辅助）——写入器按行落 accept 时不再反查 pool/relpath。
                    search_info["search_family"] = _fam
                    search_info["search_proposal_id"] = _pid
            if shadow_guard is not None:
                _fam_s = ((pool.get(cov, {}) or {}).get("family")
                          or p.get("covariate_family") or "")
                if _fam_s:
                    _sr_s, _shadow_info = shadow_guard.check(
                        p, symbol, _fam_s, cov, os.path.relpath(sp, root))
                    if _sr_s is not None:
                        bucket = stats["search_would_reject"]
                        bucket[_sr_s] = bucket.get(_sr_s, 0) + 1
                        stats["search_shadow_log"].append(
                            "%s %s" % (_sr_s, os.path.relpath(sp, root)))
            if allowed_syms is not None and symbol not in allowed_syms:
                _reject("symbol_not_allowed"); continue
            if cov in archived:
                _reject("cov_archived"); continue
            if valid_covs is not None and cov not in valid_covs:
                _reject("cov_not_in_active_pool"); continue
            if not _symbol_has_current_nocov_baseline(symbol, root):
                _reject("no_current_baseline"); continue
            if len(mechanism) < 40:
                _reject("mechanism_too_short"); continue
            sym_st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
            if sym_st == "DEAD":
                _reject("symbol_dead"); continue
            if sym_st == "HOLD":
                _reject("symbol_hold"); continue
            # DEAD family check: 4+ ok verdicts, 0 pass → family is dead
            dead_fams = _dead_families(snapshot or {})
            fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
            if not fam:
                _reject("family_unresolved"); continue
            if fam in dead_fams:
                _reject("family_dead"); continue
            # W6.4 (spec §4.5): vid = 实验身份 {symbol}_{cov_family}_{experiment_fp[:12]},
            # 非请求名拼接; 身份要素不可解析 → 拒收, 禁止回退旧式 symbol_cov。
            fp = _experiment_fp_for(symbol, cov)
            if fp is None:
                _reject("experiment_fp_unavailable"); continue
            vid = ef.build_variant_id(symbol, fam, fp)
            if _has_prior_failure(snapshot or {}, symbol, cov):
                delta = str(p.get("failure_delta") or "").strip()
                if len(delta) < 20:
                    _reject("no_failure_delta"); continue
            if vid in dead or vid in existing or vid in passing_ids or vid in seen_vids:
                _reject("dedup"); continue
            seen_vids.add(vid)

            # ── PR-B6 提案质量门 (在 dedup 之后，保证既有 reject 归因不变) ──
            _snap = snapshot or {}
            sec_blocked, sector, _sec_failed = _sector_filter_check(symbol, _snap)
            if sec_blocked:
                stats["sector_blocked"] += 1
                _reject("sector_blocked"); continue
            cov_blocked, _cov_fail_n, _cov_pass_n = _covariate_filter_check(cov, symbol, _snap)
            if cov_blocked:
                stats["cov_cross_fail"] += 1
                _reject("cov_cross_fail"); continue
            quality_score, _quality_bd = _proposal_quality_gate(p, _snap, proposal_path=sp)
            if quality_score < MIN_QUALITY_SCORE:
                stats["quality_below_threshold"] += 1
                _reject("quality_below_threshold"); continue

            # ── T2 (2026-10-05) 已成功组合增量论证门（dedup+PR-B6 之后、
            # prescreen 之前——只作用于此前会被选中的提案，既有 reject 归因
            # 绝对不变）──
            _sg_reason, _sg_state = _success_delta_gate(
                p, symbol, cov, _snap, root, cache=_sg_cache)
            stats["success_gate_states"][_sg_state] = \
                stats["success_gate_states"].get(_sg_state, 0) + 1
            if _sg_reason is not None:
                _reject(_sg_reason); continue

            family = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or "other"
            repeat_counts = _cross_run_repeat_counts()
            score = _proposal_priority_score(p, cov, symbol, snapshot or {},
                                            status_map=status_map,
                                            repeat_counts=repeat_counts,
                                            proposal_path=sp)
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
            _cand = {
                "variant_id": vid, "symbol": symbol, "cov_override": cov,
                "max_points": int(aligned_max_points), "stage": "aligned",
                "checkpoint_path": "", "enqueued_at": _now_iso(),
                "src_run": os.path.basename(run_dir), "source": "peer_proposal",
                # PR-B6 质量门留痕 (队列行，供宿主审查门是否过严)
                "quality_score": round(quality_score, 4), "sector": sector,
                "_family": family, "_score": score, "_tier": tier,
                "_proposal_path": sp}
            if search_info is not None:
                # P2.2 (spec §6.2): enforce 档队列行携带树三字段（2.3 落账依据）；
                # off/shadow 不带（S1：off 下行形状与今日相同）
                _cand.update(search_info)
            candidates.append(_cand)
            # ── TypeSafe 预筛触发 (fire-and-forget, 不阻塞 harvest) ──
            _prescreen_async(p, sp, symbol)

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

_FP_WEIGHTS_CACHE: dict = {}
_FP_TARGET_CACHE: dict = {}


def _experiment_fp_for(symbol, cov):
    """W6.4 实验身份要素: 权重目录 + 品种 1H close 序列 + 慢环窗口常数 + 请求协变量。

    compute_experiment_fingerprint 唯一家在 cascade/experiment_fingerprint.py,
    本函数是其 supervisor 侧装配者; build_variant_id 的 fp 入参即返回值。
    任何一环不可解析 → None (fail-visible), 调用方必须拒绝候选,
    禁止回退旧式 symbol_cov 身份 (spec §4.5 W6.4)。
    weights 解析一次缓存; target 逐品种缓存 (ALLOWED_SYMBOLS 有界)。
    """
    try:
        import data.config as dc
        from config.backtest_config import CONTEXT_BARS, HORIZON, STEP
        wdir = _FP_WEIGHTS_CACHE.get("weights_dir")
        if wdir is None:
            wdir = dc.get_timesfm_model_path()
            if not wdir or not Path(wdir).is_dir():
                return None
            _FP_WEIGHTS_CACHE["weights_dir"] = wdir
        target = _FP_TARGET_CACHE.get(symbol)
        if target is None:
            from data.data_store import DataStore
            store = DataStore(symbol)
            try:
                h1 = store.get_main_contract_1h(limit=99999)
            finally:
                store.close()
            if h1 is None or h1.empty:
                return None
            target = [float(x) for x in h1["close_price"].tolist()]
            if not target:
                return None
            _FP_TARGET_CACHE[symbol] = target
        return ef.compute_experiment_fingerprint(
            wdir, target, CONTEXT_BARS, HORIZON, STEP, [cov])
    except Exception:
        return None


def _symbol_n_table():
    """[(symbol, valid_n)] for evaluator-allowed symbols; [] if evaluator unavailable."""
    ev = _load_evaluator()
    syms = sorted(getattr(ev, "ALLOWED_SYMBOLS", None) or [])
    return [(s, _valid_n_for_symbol(s)) for s in syms]

def _retest_candidates(snapshot):
    """gate 仅因 n 不足而失败的近失误最新裁决。

    v1 (schema != v2): ic>=0.05, ev>0, pf/incumbent>1.05 (遗留判据)
    v2 (schema == fm.aligned_verdict.v2): dir_acc>=0.50 (v23 口径)

    本函数仅用于 gate 仅差 n (n < RETEST_GATE_N) 的复测扫描。
    语义即 'inconclusive, retest when more data'。snapshot 按 variant_id 保留
    最新裁决。no_data 已被排除 (status != ok)；gate 因质量指标不足而失败者
    不入选 (加样本也救不回)。
    """
    out = []
    for vid, v in snapshot.items():
        if v.get("status", "ok") != "ok" or v.get("gate_pass") is not False:
            continue
        # 2026-10-04（E3）：确认通道的行不进探索复测。peek（status=ok、
        # gate_pass=False、0<n<RETEST_GATE_N）天然满足复测入选条件，被当
        # 探索复测会生成无 run_mode/prereg_id 的同 vid 探索行，快照
        # last-wins 覆盖 peek → prereg_id 从快照消失 → 去重失效 → 振荡。
        if v.get("run_mode") == "confirmation" or v.get("prereg_id"):
            continue
        n = int(v.get("n") or 0)
        if n <= 0 or n >= RETEST_GATE_N:
            continue
        # Dispatch by schema version
        is_v2 = v.get("schema") == "fm.aligned_verdict.v2"
        if is_v2:
            # v2: use dir_acc as quality signal
            dir_acc = float(v.get("dir_acc") or 0.0)
            if dir_acc >= 0.50:
                out.append(v)
        else:
            # v1 legacy: use ic/ev/pf
            ic = float(v.get("ic") or 0.0)
            ev = float(v.get("ev") or 0.0)
            ratio = float(v.get("pf") or 0.0) / INCUMBENT_PF.get(v.get("symbol"), 1.0)
            if ic >= RETEST_GATE_IC and ev > 0 and ratio > RETEST_PF_RATIO:
                out.append(v)
    return out

def _active_protocol_snapshot(path):
    """收割和复测只看当前协议。无指纹与旧指纹留在 jsonl，不参与拒绝或复测。"""
    return rl.load_snapshot(path, only_protocol=_current_protocol_fingerprint())


def plan_sample_retests(goal):
    """只读：返回当前可排队的 (row, last_n, current_n) 复测计划 (不写队列)。"""
    cad = goal.get("cadence") or {}
    margin = int(cad.get("retest_min_new_points", 1))
    inflight = rl.in_flight_ids(QUEUE, INPROGRESS)
    snap = _active_protocol_snapshot(REGISTRY)
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
        # v2 verdicts don't have max_points; use cadence default
        row = {"variant_id": vid, "symbol": v["symbol"],
               "cov_override": v["cov_override"],
               "max_points": int(cad.get("aligned_max_points", 600)),
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


def _token_budget_hit(tok_spend, tok_unknown, budgets):
    """Return (hit, cap). null cancels the cap; a missing key keeps the default 80.

    An unknown token read never counts as a hit. A non-numeric cap raises.
    """
    if tok_unknown:
        return False, None
    if not isinstance(budgets, dict) or "token_budget_m" not in budgets:
        cap = 80
    else:
        cap = budgets.get("token_budget_m")
    if cap is None:
        return False, None
    try:
        cap_n = float(cap)
    except (TypeError, ValueError):
        raise ValueError("token_budget_m must be a number or null")
    return float(tok_spend) >= cap_n, cap_n


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
    snap_now = _active_protocol_snapshot(REGISTRY)
    dead = rl.dead_variants(snap_now)
    # 修复：existing 包含当前协议的历史裁决（避免重复入队）
    in_flight = rl.in_flight_ids(QUEUE, INPROGRESS)
    historical = set(snap_now.keys())
    existing = in_flight | historical
    pool = load_covariate_pool()
    rows, pstats = harvest_proposals(
        FM_ROOT, snap_now, dead, existing, pool,
        top_k=cad.get("survivors_per_cycle", 2),
        aligned_max_points=cad.get("aligned_max_points", 400),
        priority_symbols=cad.get("priority_symbols"),
        search_policy=_norm_search_policy(goal))
    return rows, dead, existing, pstats

def _commit_search_accepts(rows, dead=None, existing=None):
    """对将真实入队的搜索行落 accept（spec §6.7；P2.3）。

    镜像 rl.queue_enqueue 的 vid 去重（dead/existing/在队/批内首见，
    first-wins）——被去重拦下的行不落账，防「成员永不评估」的持久幻影
    占位（2.2 审核 MINOR 的持久化防线）。置于 queue_enqueue 之前：
    崩溃重放时已入队的 vid 在此被跳过（不重复落账）、未入队的重写
    （成员集合语义幂等）。off/shadow 行无 search_role → 空操作。
    写入 OSError 向上抛：main() 顶层 re-raise → 进程退出 → 由外部重启
    （宿主/服务）重放整轮收割，accept 落账幂等（同 vid 集合语义）。
    """
    dead = dead or set()
    existing = existing or set()
    queued = {r.get("variant_id") for r in rl.queue_load(QUEUE)}
    n, seen = 0, set()
    for r in rows:
        vid = r.get("variant_id")
        if not r.get("search_role") or not vid:
            continue
        # N4（P2.3 审核）：病态行防御——守卫恒随 search_role 一起给出
        # search_tree_id，缺键跳过不落账，不 KeyError。
        if not r.get("search_tree_id"):
            continue
        if vid in dead or vid in existing or vid in queued or vid in seen:
            continue
        seen.add(vid)
        st.append_commitment(
            SEARCH_COMMITMENTS_PATH, "accept",
            tree_id=r["search_tree_id"], symbol=r.get("symbol") or "",
            family=r.get("search_family") or "",
            proposal_id=r.get("search_proposal_id") or "",
            variant_id=vid, search_role=r.get("search_role") or "",
            search_parent_id=r.get("search_parent_id") or "")
        n += 1
    return n

def _sweep_search_stops(goal, log, snapshot):
    """P2.4（spec §6.5）：巡检未停止树的停止条件并落 stop 行（enforce-only）。

    主循环每轮调用（materialize 之后、同轮收割之前——停止先于新 admit）。
    snapshot 用主循环当前协议视图（snap["variants"]），族死亡判据照旧
    _dead_families(min_ok=4)。promoted 不在此判定（§6.6 晋升是 2.7 的
    事件驱动落账，promote 行同为终态）。写入失败向上抛：main() 顶层
    re-raise → 进程退出 → 由外部重启重放整轮（sweep 幂等：已停止树
    不再巡检，重放只补缺失的 stop 行）。
    """
    if _norm_search_policy(goal) != "enforce":
        return 0
    index = st.load_tree_index(SEARCH_COMMITMENTS_PATH)
    if not index.unstopped():
        return 0
    stops = st.evaluate_tree_stops(index, snapshot or {},
                                   _dead_families(snapshot or {}))
    for tid, reason in stops:
        tree = index.trees[tid]
        st.append_commitment(SEARCH_COMMITMENTS_PATH, "stop",
                             tree_id=tid, symbol=tree.symbol,
                             family=tree.family, stop_reason=reason)
        _log_decision(log, "search_stop",
                      "tree=%s reason=%s symbol=%s family=%s"
                      % (tid, reason, tree.symbol, tree.family))
    return len(stops)


def _append_jsonl(path, row):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _sweep_search_promotions(goal, log, snapshot):
    """P2.7（spec §6.6）：未停止树上六条件都成立则追加一行预注册并写 promote。

    只在 enforce 下写。off / shadow 不追加、不落账。提案文本读不到则跳过
    这一棵（fail-closed），不发明 mechanism。
    """
    if _norm_search_policy(goal) != "enforce":
        return 0
    index = st.load_tree_index(SEARCH_COMMITMENTS_PATH)
    if not index.unstopped():
        return 0
    registry = load_preregistry(PREREGISTRY_PATH)
    promoted = 0
    for tree in list(index.unstopped()):
        decision = search_promote.evaluate_tree_promotion(
            tree, snapshot or {}, registry)
        if decision is None:
            continue
        mechanism, direction = search_promote.read_proposal_copy(
            FM_ROOT, decision.get("proposal_id") or "")
        if not mechanism or not direction:
            if isinstance(log, str) and log:
                _log_decision(log, "search_promote_skip",
                              "tree=%s missing proposal text" % tree.tree_id)
            continue
        row = search_promote.build_promotion_prereg(
            decision, mechanism=mechanism, predicted_direction=direction,
            registered_at=_now_iso(), prereg_id=uuid.uuid4().hex)
        # 先写 promote：该事件把树标成终态。若随后预注册追加失败，
        # 下一轮不会再晋升，避免同一棵树追加第二行。
        st.append_commitment(
            SEARCH_COMMITMENTS_PATH, "promote",
            tree_id=tree.tree_id, symbol=decision["symbol"],
            family=tree.family,
            proposal_id=decision.get("proposal_id") or "",
            variant_id=decision["variant_id"],
            stop_reason="promoted",
            delta_post=decision["delta_post"],
            n_required=decision["n_required"])
        _append_jsonl(PREREGISTRY_PATH, row)
        registry.append(row)
        index.stopped.add(tree.tree_id)
        if isinstance(log, str) and log:
            _log_decision(log, "search_promote",
                          "tree=%s vid=%s n=%s" % (
                              tree.tree_id, decision["variant_id"],
                              decision["n_confirm_required"]))
        promoted += 1
    return promoted


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
    if pstats and pstats.get("search_shadow_log"):
        _log_decision(log, "search_shadow",
                      "would_reject=%s" % (pstats.get("search_would_reject"),))
    if rows:
        # P2.3 (spec §6.7)：先落搜索 accept 再入队（顺序依据见
        # _commit_search_accepts docstring：崩溃重放幂等；且必须在
        # _merge_save 之前完成，防 accept 因 harvested_already 永久丢失）。
        n_acc = _commit_search_accepts(rows, dead, existing)
        n = rl.queue_enqueue(QUEUE, rows, dead, existing)
        _log_decision(log, "harvested_proposals", f"enqueued {n}",
                      [r["variant_id"] for r in rows])
        if n_acc:
            _log_decision(log, "search_accepts", f"committed {n_acc}",
                          [r["variant_id"] for r in rows
                           if r.get("search_role")])
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


def _baseline_protocol_fingerprint(points_path):
    """读取基线首行的 protocol_fingerprint。

    Returns:
        (status, fp):
          ("ok", <str>)      指纹存在
          ("missing", None)  首行无该键（pre-A1 遗留基线）
          ("unreadable", None) 文件不可读 / 首行非法 JSON

    2026-09-28 新增（T1a 实测发现的缺口）:
      原先 ensure_baselines 只按 n_lines<100 判断，导致 PR-A1 引入
      protocol_v2 后，rb 的旧基线（588 行、protocol_v1 指纹）被**静默保留**，
      与其他 7 份新基线跨协议不可比。本函数用于补上该层校验。
    """
    try:
        with open(points_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    return ("unreadable", None)
                fp = rec.get("protocol_fingerprint")
                return ("ok", fp) if fp else ("missing", None)
    except OSError:
        return ("unreadable", None)
    return ("missing", None)


def _current_protocol_fingerprint():
    """当前协议指纹；不可得时返回 None（此时跳过指纹校验并告警）。"""
    try:
        from task_FM.evaluations.fm_eval.evaluator import (
            compute_protocol_fingerprint,
        )
        return compute_protocol_fingerprint()
    except Exception as e:            # noqa: BLE001
        print(f"[WARN] ensure_baselines: 无法计算当前协议指纹 ({e})；跳过指纹校验",
              file=sys.stderr)
        return None


def ensure_baselines(symbols, root):
    """Check baseline_metrics.json + baseline_points_{symbol}.jsonl validity.

    For each symbol, check that baseline_metrics has a valid entry AND
    baseline_points_{symbol}.jsonl has >= 100 valid lines **AND its
    protocol_fingerprint matches the current one**. If any check fails,
    serially call generate_baseline_points.generate.

    2026-09-28 修正（T1a 实测发现）:
      原实现只检查行数，不检查协议指纹。PR-A1 将指纹升级为 protocol_v2 后，
      已有足够行数的旧基线（如 rb，588 行 / protocol_v1）被静默跳过，
      导致其与新生基线跨协议不可比 —— 而 comparable() 会因此拒绝配对，
      表现为 dm_status=protocol_mismatch，难以归因。现补上指纹校验。
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
    cur_fp = _current_protocol_fingerprint()
    for sym in sorted(symbols):
        sym_lower = sym.lower()
        points_path = os.path.join(config_dir, gbp.baseline_filename(sym_lower, None))
        met = metrics.get(sym_lower, {})
        if not isinstance(met, dict) or not met.get("n") or int(met.get("n", 0)) <= 0:
            try:
                gbp.generate(sym_lower, None, root)   # E7: 无协变量基线
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
                gbp.generate(sym_lower, None, root)   # E7: 无协变量基线
            except Exception as e:
                print(f"[ERROR] ensure_baselines: generate failed for {sym_lower} (n_lines={n_lines}): {e}", file=sys.stderr)
            continue

        # ── 协议指纹校验（2026-09-28 新增）──
        # 行数够不等于可用：指纹不符则跨协议不可比，必须重生。
        if cur_fp is None:
            continue
        status, base_fp = _baseline_protocol_fingerprint(points_path)
        if status != "ok":
            reason = ("首行缺 protocol_fingerprint（pre-A1 遗留基线）"
                      if status == "missing" else "基线首行不可读")
            print(f"[WARN] ensure_baselines: {sym_lower} {reason} → 重生",
                  file=sys.stderr)
        elif base_fp != cur_fp:
            print(
                f"[WARN] ensure_baselines: {sym_lower} 基线协议指纹不符 "
                f"({base_fp[:16]}… != {cur_fp[:16]}…) → 重生（跨协议不可比）",
                file=sys.stderr,
            )
        else:
            continue          # 行数与指纹均合格
        try:
            gbp.generate(sym_lower, None, root)
        except Exception as e:
            print(f"[ERROR] ensure_baselines: generate failed for {sym_lower} "
                  f"(fingerprint mismatch): {e}", file=sys.stderr)



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
                # 2026-10-04（E5）：墓碑保身份（与 _no_data_verdict 的 D2 同型）。
                # 确认行的 timeout 墓碑必须带 prereg_id/run_mode，否则快照
                # last-wins 会把确认身份冲掉。batch_records 来自派发行；
                # 探索行此处取到 None，与旧行为一致。
                tomb["run_mode"] = r.get("run_mode")
                tomb["prereg_id"] = r.get("prereg_id")
                tomb["confirm_from_ts"] = r.get("confirm_from_ts")
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
        batch_verdicts = []
        try:
            all_verdicts = rl.read_verdicts(REGISTRY)
            batch_verdicts = [v for v in all_verdicts if v.get("batch_id") == batch_id]
            if batch_verdicts and bh_fdr_promote is not None:
                updates = promote_batch_for_persistence(batch_verdicts)
                if updates:
                    rl.update_batch_verdicts(REGISTRY, batch_id, updates)
                    _log_decision(log, "batch_fdr_promote",
                                 f"batch={batch_id} promoted={len(updates)}")
        except Exception as e:
            _log_decision(log, "batch_fdr_error", str(e))
        try:
            members = load_family_members(FAMILY_REGISTRY)
            now = datetime.now(timezone.utc)
            touched = False
            for verdict in batch_verdicts:
                if not isinstance(verdict, dict) or verdict.get("run_mode") != "confirmation":
                    continue
                try:
                    symbol = verdict.get("symbol")
                    if isinstance(symbol, str) and symbol:
                        family_key = family_key_for(symbol)
                    else:
                        family_key = None
                        vid = verdict.get("variant_id")
                        for member in members:
                            if member.get("variant_id") == vid:
                                family_key = member.get("family_key")
                                break
                    family_members = [
                        member for member in members
                        if family_key is not None and member.get("family_key") == family_key
                    ]
                    result = _finalize_confirmation_verdict(verdict, family_members, now)
                    if not isinstance(result, dict) or not isinstance(result.get("members"), list):
                        continue
                    if family_key is None:
                        continue
                    members = _merge_family_members(members, family_key, result["members"])
                    touched = True
                except Exception as e:
                    _log_decision(log, "confirmation_finalize_error", str(e),
                                  [str(verdict.get("variant_id") or "")])
            if touched:
                save_family_members(FAMILY_REGISTRY, members)
        except Exception as e:
            _log_decision(log, "confirmation_finalize_error", str(e))
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
    # 物化给 peer 看的证据同样只认当前协议；被排除的行显式报数，不静默。
    _cur_fp = _current_protocol_fingerprint()
    _full = snap
    if _cur_fp is not None:
        snap = {vid: v for vid, v in snap.items()
                if v.get("protocol_fingerprint") == _cur_fp}
        _hist = rl.protocol_histogram(_full)
        if len(snap) != len(_full):
            print("[INFO] 物化证据按 protocol 过滤: active=%d/%d fp=%s… 排除=%s"
                  % (len(snap), len(_full), _cur_fp[:16],
                     " ".join("%s:%d" % (k, v) for k, v in sorted(_hist.items()))))
    # T1 (2026-10-05): 被过滤的旧协议行作为「仅上下文」注记传入，不再静默丢弃。
    # 指纹不可得（fail-open 未过滤）时传 None，由 materialize 走输入内兜底推导。
    _excl = ({vid: v for vid, v in _full.items()
              if v.get("protocol_fingerprint") != _cur_fp}
             if _cur_fp is not None else None)
    materialize_known_verdicts(
        snap, VERDICTS_INC,
        status_map=load_symbol_status(),
        queue_ids=rl.in_flight_ids(QUEUE, INPROGRESS),
        proposed_ids=collect_proposed_variant_ids(FM_ROOT),
        root=FM_ROOT,
        excluded_items=_excl,
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
        goal_for_baselines = load_goal(args.goal)
        ensure_baselines(_goal_target_symbols(goal_for_baselines), args.root)
    except Exception as e:
        print(f"[ERROR] ensure_baselines pre-flight failed: {e}", file=sys.stderr)
    while True:
        _write_heartbeat()
        code = _shutdown_exit()
        if code is not None:
            return code
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
        tok_hit, tok_budget = _token_budget_hit(tok_spend, tok_unknown, b)
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

        materialize_covariate_menu(load_covariate_pool(), MENU_INC)
        # P2.4（spec §6.5）：每轮巡检未停止树的停止条件，先于同轮收割
        # （停止先于新 admit；enforce-only 在函数内门控；写失败向上传播）。
        # 停止先于晋升：本轮刚撞上预算/上界/家族死亡的树不再晋升（§6.5 序、§6.6 条件 1）。
        _sweep_search_stops(goal, log, snap["variants"])
        _sweep_search_promotions(goal, log, snap["variants"])
        # 树节写在停止和晋升之后，本轮刚关闭的树不再留给同伴当父节点。
        # T1 (2026-10-05): 主循环物化同样注记旧协议行。snap["variants"] 已按
        # 当前协议过滤——从其唯一指纹反查全量 registry 求差（不重算指纹）；
        # 指纹不可得或混合时留空，由 materialize 走输入内兜底推导。
        _mb_kwargs = {}
        _fps_mb = {v.get("protocol_fingerprint")
                   for v in snap["variants"].values()
                   if isinstance(v, dict)}
        if len(_fps_mb) == 1 and None not in _fps_mb:
            _only_fp_mb = next(iter(_fps_mb))
            _full_mb = rl.load_snapshot(REGISTRY)
            _mb_kwargs["excluded_items"] = {
                vid: v for vid, v in _full_mb.items()
                if v.get("protocol_fingerprint") != _only_fp_mb}
        materialize_known_verdicts(
            snap["variants"], VERDICTS_INC,
            status_map=load_symbol_status(),
            queue_ids=rl.in_flight_ids(QUEUE, INPROGRESS),
            proposed_ids=collect_proposed_variant_ids(FM_ROOT),
            root=FM_ROOT,
            **_mb_kwargs)
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
                code = _shutdown_exit()
                if code is not None:
                    return code
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
                    fresh_tok_hit, fresh_tok_budget = _token_budget_hit(
                        fresh_tok_spend, fresh_tok_unknown, fresh_b)
                    budget_hit = (fresh_cycles >= (args.max_cycles or goal["budgets"]["max_cycles"])
                                  or fresh_cpu_h >= fresh_b.get("cpu_hours", 60)
                                  or fresh_tok_hit or _deadline_passed(fresh_b))
                    # Update outer-scope vars so the budget_exhausted report (if still hit) is accurate
                    cycles, cpu_h, tok_spend, snap = fresh_cycles, fresh_cpu_h, fresh_tok_spend, fresh_snap
                    tok_unknown, tok_hit, tok_budget = fresh_tok_unknown, fresh_tok_hit, fresh_tok_budget
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
        code = _shutdown_exit()
        if code is not None:
            return code
        if not _run_active():
            _maybe_harvest(st, goal, log)
        # n-不足型近失误自动复测 (本地慢环, 不受 LLM 暂停/failover 影响)。
        try:
            _maybe_enqueue_retests(goal, log)
        except Exception as e:
            _log_decision(log, "retest_scan_error", str(e))
        try:
            _maybe_enqueue_confirmations(log, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            _log_decision(log, "confirmation_enqueue_error", str(e))
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
        _sleep_interruptible(max(1, sleep_s))

if __name__ == "__main__":
    sys.exit(main() or 0)
