"""verdict 注册表与 aligned 队列的共享库 (三环文件总线)"""
import json, os, contextlib, fcntl, time, pathlib

VERDICT_FIELDS = {"variant_id", "symbol", "cov_override", "max_points", "n",
                  "pf", "ev", "maxdd", "dir_acc", "gate_pass", "ic",
                  "decided_at", "checkpoint_path", "slow_loop_pid", "git_rev",
                  "schema"}

VERDICT_FIELDS_V2 = {
    "schema", "variant_id", "symbol", "cov_override", "status", "stage",
    "batch_id", "n", "n_eff", "dir_acc", "gate_pass",
    "p_value", "fdr_pass", "migrated_pass",
    "endpoint_mape", "endpoint_bias_pct", "path_corr", "mae", "mape", "decay",
    "checkpoint_path", "slow_loop_pid", "git_rev", "decided_at",
}
VERDICT_FIELDS_V2_NULLABLE = {
    "path_corr", "mae", "mape", "decay", "p_value",
    "fdr_pass", "migrated_pass", "endpoint_mape", "endpoint_bias_pct",
}

QUEUE_FIELDS = {"variant_id", "symbol", "cov_override", "max_points",
                "stage", "checkpoint_path", "enqueued_at", "src_run"}

def append_verdict(registry_fp, verdict):
    errs = validate_verdict(verdict)
    if errs:
        raise ValueError(f"invalid verdict: {errs}")
    registry_fp.write(json.dumps(verdict, ensure_ascii=False) + "\n")
    registry_fp.flush()

def _iter_jsonl(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

def load_snapshot(path):
    snap = {}
    for v in _iter_jsonl(path) or []:
        try:
            snap[v["variant_id"]] = v
        except (KeyError, TypeError):
            continue
    return snap

def pass_variants(snapshot):
    out = []
    for v in snapshot.values():
        if v.get("status", "ok") != "ok":
            continue
        if v.get("gate_pass") and v.get("ev", 0) > 0:
            out.append(v)
    return out

def dead_variants(snapshot):
    return {vid for vid, v in snapshot.items()
            if v.get("status", "ok") == "ok" and v.get("gate_pass") is False}

def validate_verdict(v):
    errs = []
    missing = VERDICT_FIELDS - set(v)
    if missing:
        errs.append(f"missing fields: {sorted(missing)}")
    for k in ("n", "pf", "ev", "maxdd", "dir_acc", "ic"):
        if k in v and not isinstance(v[k], (int, float)):
            errs.append(f"{k} must be numeric")
    return errs

@contextlib.contextmanager
def _queue_lock(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock = open(path + ".lock", "a")
    import fcntl
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

def _write_rows(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)

def queue_load(path):
    return [r for r in (_iter_jsonl(path) or []) if isinstance(r, dict) and "variant_id" in r]

def queue_enqueue(path, rows, dead, existing):
    if not rows:
        return 0
    with _queue_lock(path):
        inq = {r["variant_id"] for r in queue_load(path)}
        added = 0
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                vid = r["variant_id"]
                if vid in dead or vid in existing or vid in inq:
                    continue
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                inq.add(vid)
                added += 1
    return added

def queue_claim(pending_path, inprogress_path):
    """把 pending 队首移入 inprogress; 两边同锁 (锁文件挂在 pending 上)。"""
    with _queue_lock(pending_path):
        inflight = queue_load(inprogress_path)
        if inflight:
            return inflight[0]
        rows = queue_load(pending_path)
        if not rows:
            return None
        row, rest = rows[0], rows[1:]
        # inprogress first: crash mid-claim leaves duplicate, recoverable via recover dedupe
        _write_rows(inprogress_path, [row])
        _write_rows(pending_path, rest)
        return row

def queue_ack(pending_path, inprogress_path, row, done_path):
    with _queue_lock(pending_path):
        # done first: at-least-once beats silent loss if crash before clearing inprogress
        parent = os.path.dirname(done_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(done_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        left = [r for r in queue_load(inprogress_path)
                if r.get("variant_id") != row.get("variant_id")]
        _write_rows(inprogress_path, left)

def queue_recover(pending_path, inprogress_path):
    with _queue_lock(pending_path):
        inflight = queue_load(inprogress_path)
        if not inflight:
            return 0
        pending = queue_load(pending_path)
        seen = {r["variant_id"] for r in inflight}
        merged = inflight + [r for r in pending if r["variant_id"] not in seen]
        _write_rows(pending_path, merged)
        _write_rows(inprogress_path, [])
        return len(inflight)

def in_flight_ids(pending_path, inprogress_path):
    return {r["variant_id"] for r in queue_load(pending_path) + queue_load(inprogress_path)}


# ---------------------------------------------------------------------------
# v2 support: path-based IO, tombstones, FDR update, v2-aware pass_variants
# ---------------------------------------------------------------------------

_v1_validate_verdict = validate_verdict
_v1_append_verdict = append_verdict
_v1_pass_variants = pass_variants


def validate_verdict_v2(v):
    errs = []
    missing = VERDICT_FIELDS_V2 - set(v)
    # For nullable fields, presence with None is acceptable; only complain if absent entirely.
    nullable_ok = missing - VERDICT_FIELDS_V2_NULLABLE
    if nullable_ok:
        errs.append(f"missing v2 fields: {sorted(nullable_ok)}")
    for k in ("n", "n_eff", "dir_acc", "p_value"):
        if k in v and v.get(k) is not None and not isinstance(v[k], (int, float)):
            errs.append(f"{k} must be numeric")
    return errs


def validate_verdict(v):
    if v.get("schema") == "fm.aligned_verdict.v2":
        return validate_verdict_v2(v)
    return _v1_validate_verdict(v)


def read_verdicts(path):
    """Read all verdicts from a JSONL path under shared lock; skip bad lines."""
    p = str(path)
    if not os.path.exists(p):
        return []
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock_f = open(p + ".lock", "a")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_SH)
        return list(_iter_jsonl(p))
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()


def append_verdict_path(registry, verdict):
    """Append verdict to path (str|Path) with exclusive lock, dedup by (batch_id, variant_id)."""
    p = str(registry)
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock_f = open(p + ".lock", "a")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        existing = list(_iter_jsonl(p)) if os.path.exists(p) else []
        new_bid = verdict.get("batch_id")
        new_vid = verdict.get("variant_id")
        if new_bid is not None and new_vid is not None:
            for e in existing:
                if e.get("batch_id") == new_bid and e.get("variant_id") == new_vid:
                    return  # first-write-wins
        tmp = f"{p}.{os.getpid()}.{time.time_ns()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for row in existing:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.write(json.dumps(verdict, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()


def append_verdict(registry_or_fp, verdict):
    if isinstance(registry_or_fp, (str, os.PathLike, pathlib.Path)):
        return append_verdict_path(registry_or_fp, verdict)
    return _v1_append_verdict(registry_or_fp, verdict)


def update_batch_verdicts(path, batch_id, updates):
    """Merge updates[variant_id] into verdicts matching batch_id.

    If verdict has a `metrics` sub-dict, mirror the same keys into it.
    Atomic write; lock held throughout; no reentrant flock.
    """
    p = str(path)
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock_f = open(p + ".lock", "a")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        rows = list(_iter_jsonl(p)) if os.path.exists(p) else []
        out = []
        for v in rows:
            if v.get("batch_id") != batch_id:
                out.append(v)
                continue
            vid = v.get("variant_id")
            upd = updates.get(vid)
            if not upd:
                out.append(v)
                continue
            merged = dict(v)
            for k, val in upd.items():
                merged[k] = val
            if "metrics" in merged and isinstance(merged["metrics"], dict):
                m = dict(merged["metrics"])
                for k, val in upd.items():
                    m[k] = val
                merged["metrics"] = m
            out.append(merged)
        tmp = f"{p}.{os.getpid()}.{time.time_ns()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for row in out:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()


def make_error_tombstone(symbol, variant_id, batch_id, exception):
    """v2 tombstone for a runtime error."""
    msg = f"{type(exception).__name__}: {exception}"
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": variant_id,
        "symbol": symbol,
        "batch_id": batch_id,
        "cov_override": None,
        "status": "error",
        "stage": "aligned",
        "n": 0,
        "n_eff": 0,
        "dir_acc": 0.0,
        "gate_pass": False,
        "p_value": 1.0,
        "fdr_pass": False,
        "migrated_pass": False,
        "endpoint_mape": None,
        "endpoint_bias_pct": None,
        "path_corr": None,
        "mae": None,
        "mape": None,
        "decay": None,
        "checkpoint_path": None,
        "slow_loop_pid": None,
        "git_rev": None,
        "decided_at": None,
        "error": msg,
        "metrics": {
            "batch_id": batch_id,
            "variant_id": variant_id,
            "symbol": symbol,
            "status": "error",
            "gate_pass": False,
            "p_value": 1.0,
            "fdr_pass": False,
            "migrated_pass": False,
        },
    }


def make_timeout_tombstone(symbol, variant_id, batch_id):
    """v2 tombstone for a timeout."""
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": variant_id,
        "symbol": symbol,
        "batch_id": batch_id,
        "cov_override": None,
        "status": "timeout",
        "stage": "aligned",
        "n": 0,
        "n_eff": 0,
        "dir_acc": 0.0,
        "gate_pass": False,
        "p_value": 1.0,
        "fdr_pass": False,
        "migrated_pass": False,
        "endpoint_mape": None,
        "endpoint_bias_pct": None,
        "path_corr": None,
        "mae": None,
        "mape": None,
        "decay": None,
        "checkpoint_path": None,
        "slow_loop_pid": None,
        "git_rev": None,
        "decided_at": None,
        "metrics": {
            "batch_id": batch_id,
            "variant_id": variant_id,
            "symbol": symbol,
            "status": "timeout",
            "gate_pass": False,
            "p_value": 1.0,
            "fdr_pass": False,
            "migrated_pass": False,
        },
    }


def pass_variants(snapshot):
    """v2-aware pass filter.

    v2: gate_pass AND (fdr_pass OR migrated_pass)
    v1: gate_pass AND ev > 0
    """
    out = []
    for v in snapshot.values():
        if v.get("status", "ok") != "ok":
            continue
        if v.get("schema") == "fm.aligned_verdict.v2":
            if v.get("gate_pass") and (v.get("fdr_pass") or v.get("migrated_pass")):
                out.append(v)
        else:
            if v.get("gate_pass") and v.get("ev", 0) > 0:
                out.append(v)
    return out
