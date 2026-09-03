"""verdict 注册表与 aligned 队列的共享库 (三环文件总线)"""
import json, os, contextlib

VERDICT_FIELDS = {"variant_id", "symbol", "cov_override", "max_points", "n",
                  "pf", "ev", "maxdd", "dir_acc", "gate_pass", "ic",
                  "decided_at", "checkpoint_path", "slow_loop_pid", "git_rev",
                  "schema"}
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
