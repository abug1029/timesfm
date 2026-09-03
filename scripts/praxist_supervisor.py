#!/usr/bin/env python3
"""三环监督环: goal 判定 + 两环调度, 纯 Python 0 token"""
import argparse, fcntl, glob, json, os, re, subprocess, sys, time
from datetime import datetime, timedelta
import yaml
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
import registry_lib as rl
from goal_dsl import evaluate_goal

PRAXIST = "/root/.praxist-venv/bin/praxist"
QUEUE = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl")
INPROGRESS = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl")
REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")
STATE_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_state.json")
LOCK_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor.lock")
VERDICTS_INC = os.path.join(FM_ROOT, "task_FM", "known_verdicts.inc.md")
REPORT_DIR = os.path.join(FM_ROOT, "docs", "superpowers", "reports")
STATE_MD = os.path.join(FM_ROOT, "STATE.md")
POLL_S = 300
PHASES = ("fast", "slow", "wait_quota")

with open(os.path.join(FM_ROOT, "config", "knowledge_base.json"), encoding="utf-8") as _f:
    _kb = json.load(_f)
INCUMBENT_PF = {sym: float(rec["historical_pf"])
                for sym, rec in _kb["symbols"].items()
                if rec.get("historical_pf") is not None}

def _now_iso():
    return datetime.now().isoformat()

def parse_429_reset(log_text):
    m = re.search(r"reset at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})", log_text)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")

def load_state():
    if not os.path.exists(STATE_PATH):
        st = {"cycles_done": 0, "last_run_dir": None, "last_run_id": None,
              "last_harvested_run_id": None, "paused_429": False, "phase": "fast"}
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

def _praxist_env():
    env = dict(os.environ)
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    if key:
        env["ANTHROPIC_API_KEY"] = key
    # Volcengine relay needs VOLCENGINE_API_KEY
    volc_key = os.environ.get("VOLCENGINE_API_KEY")
    if volc_key:
        env["VOLCENGINE_API_KEY"] = volc_key
    return env

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
    return {
        "variants": snap,
        "symbols_hit": {v["symbol"] for v in passing},
        "families_hit": {v["cov_override"] for v in passing},
        "pass_variant_pf_ratios": [v["pf"] / INCUMBENT_PF.get(v["symbol"], 1.0)
                                   for v in passing],
        "cycles_done": cycles_done,
        "cpu_hours_used": cpu_hours_used,
        "tokens_used_m": tokens_used_m,
    }

def harvest_survivors(root, snapshot, dead, existing, top_k, aligned_max_points=400):
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
            ev = float(metrics.get("ev_after_slippage") or metrics.get("ev")
                       or d.get("ev") or 0.0)
            if ev <= 0:
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
                        "_ev": ev})
    out.sort(key=lambda r: -r["_ev"])
    for r in out:
        r.pop("_ev", None)
    return out[:top_k]

def materialize_known_verdicts(snapshot, dest_path):
    lines = ["## Known aligned verdicts (supervisor snapshot)",
             "gate_pass=True: already solved, do NOT re-propose.",
             "gate_pass=False: DEAD, revive only with PI mechanism correction.",
             ""]
    items = list(snapshot.values()) if isinstance(snapshot, dict) else []
    items.sort(key=lambda v: (not v.get("gate_pass", False), -float(v.get("ev") or 0)))
    if not items:
        lines.append("(no aligned verdicts yet)")
    for v in items[:20]:
        lines.append("- {0}: gate_pass={1}, ev={2}, n={3}, status={4}".format(
            v.get("variant_id"), v.get("gate_pass"), v.get("ev"),
            v.get("n"), v.get("status", "ok")))
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

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
        for line in open(p, encoding="utf-8"):
            if line.strip():
                try:
                    total += float(json.loads(line).get("elapsed_s", 0)) / 3600.0
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
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
    f = open(lock_path, "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    finally:
        f.close()

def _queue_busy():
    return bool(rl.queue_load(QUEUE) + rl.queue_load(INPROGRESS))

def _slow_drain_complete():
    return (not _queue_busy()) and (not _slow_loop_alive())

def ensure_phase(st):
    """Fill st['phase'] for legacy state. Does not write disk."""
    if st.get("phase") in PHASES:
        return st
    if _queue_busy() or _slow_loop_alive():
        st["phase"] = "slow"
    elif st.get("paused_429") and not _run_active():
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
    except OSError:
        pass
    return path

def _merge_save(updates):
    fresh = load_state()
    fresh.update(updates)
    save_state(fresh)
    return fresh

def decide_fast_loop(goal, dry_run=False, now=None):
    """纯决策: 返回 actions 列表 [{action, reason, refs, argv?}]. dry_run 不调用 praxist。"""
    actions = []
    ok, sleep_s = quota_gate(goal, now=now)
    active = _run_active()
    meta = _active_run_meta() if active else None
    st = ensure_phase(load_state())
    if active and not ok:
        run_id = (meta or {}).get("run_id") or st.get("last_run_id")
        run_dir = (meta or {}).get("run_dir") or st.get("last_run_dir")
        actions.append({"action": "run_paused_429", "reason": "quota banned; stop then wait reset",
                        "refs": [run_id, run_dir], "argv": ["stop", str(run_id)] if run_id else None,
                        "sleep_s": sleep_s})
        if not dry_run and run_id:
            r = _praxist(["stop", str(run_id)])
            if r.get("ok"):
                _merge_save({"paused_429": True, "last_run_dir": run_dir, "last_run_id": run_id})
        return actions
    if st.get("phase") == "slow":
        return actions
    if st.get("paused_429"):
        rd = st.get("last_run_dir") or st.get("last_run_id")
        if (not active) and ok and rd:
            actions.append({"action": "run_resumed", "reason": "quota window ok; resume same run_dir",
                            "refs": [rd],
                            "argv": ["resume", rd, "--daemonize", "--json"]})
            if not dry_run:
                r = _praxist(["resume", rd, "--daemonize", "--json"], env=_praxist_env())
                if r.get("ok"):
                    _merge_save({"paused_429": False})
            return actions
        if not ok:
            actions.append({"action": "wait_quota", "reason": "quota window insufficient",
                            "refs": [], "sleep_s": sleep_s})
        return actions
    if st.get("phase") == "wait_quota":
        if not ok:
            actions.append({"action": "wait_quota", "reason": "quota window insufficient",
                            "refs": [], "sleep_s": sleep_s})
            return actions
        if not dry_run:
            _merge_save({"phase": "fast"})
        st = dict(st)
        st["phase"] = "fast"
    if (not active) and ok:
        last = st.get("last_run_id")
        harvested_already = (not last) or st.get("last_harvested_run_id") == last
        if harvested_already and st.get("phase") != "slow":
            actions.append({"action": "run_started", "reason": "window ok, no active run",
                            "refs": [],
                            "argv": ["start", "--task-path", os.path.join(FM_ROOT, "task_FM"),
                                     "--daemonize", "--json"]})
            if not dry_run:
                r = _praxist(["start", "--task-path", os.path.join(FM_ROOT, "task_FM"),
                              "--daemonize", "--json"], env=_praxist_env())
                if r.get("ok"):
                    updates = {"paused_429": False}
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
        return actions
    if not ok:
        actions.append({"action": "wait_quota", "reason": "quota window insufficient",
                        "refs": [], "sleep_s": sleep_s})
    return actions

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--goal", default=os.path.join(FM_ROOT, "scripts", "praxist_goal.yaml"))
    ap.add_argument("--root", default=FM_ROOT)
    ap.add_argument("--max-cycles", type=int, default=None)
    args = ap.parse_args(argv)
    if args.root != FM_ROOT:
        # 测试可把模块级路径 monkeypatch; --root 仅给 harvest 用
        pass
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock = open(LOCK_PATH, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another supervisor holds the lock; exit")
        return 0
    try:
        return _main_locked(args)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

def _harvest_rows(goal):
    cad = goal.get("cadence") or {}
    snap_now = rl.load_snapshot(REGISTRY)
    dead = rl.dead_variants(snap_now)
    existing = rl.in_flight_ids(QUEUE, INPROGRESS)
    rows = harvest_survivors(
        FM_ROOT, snap_now, dead, existing,
        top_k=cad.get("survivors_per_cycle", 2),
        aligned_max_points=cad.get("aligned_max_points", 400))
    return rows, dead, existing

def _maybe_harvest(st, goal, log):
    """Harvest a finished unpaused run. Returns True if a cycle was counted."""
    last = st.get("last_run_id")
    harvested_already = bool(last) and st.get("last_harvested_run_id") == last
    if _run_active() or st.get("paused_429") or not last or harvested_already:
        return False
    rows, dead, existing = _harvest_rows(goal)
    if rows:
        n = rl.queue_enqueue(QUEUE, rows, dead, existing)
        _log_decision(log, "harvested", f"enqueued {n}",
                      [r["variant_id"] for r in rows])
        _merge_save({"last_harvested_run_id": last, "phase": "slow"})
    else:
        _log_decision(log, "harvest_empty",
                      "finished run produced 0 diagnostic survivors "
                      "(need results/**/evaluation_summary.json)")
        gate_ok, _ = quota_gate(goal)
        fresh = load_state()
        fresh["cycles_done"] = int(fresh.get("cycles_done") or 0) + 1
        fresh["last_harvested_run_id"] = last
        fresh["phase"] = "fast" if gate_ok else "wait_quota"
        save_state(fresh)
    return True

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
        subprocess.Popen(
            [sys.executable, os.path.join(HERE, "aligned_slow_loop.py")],
            stdout=out_fp, stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        out_fp.close()
    _log_decision(log, "slow_loop_started", "phase=slow, queue busy")

def _maybe_finish_slow(goal, log):
    st = load_state()
    if st.get("phase") != "slow":
        return False
    if not _slow_drain_complete():
        return False
    snap = rl.load_snapshot(REGISTRY)
    materialize_known_verdicts(snap, VERDICTS_INC)
    gate_ok, _ = quota_gate(goal)
    fresh = load_state()
    fresh["cycles_done"] = int(fresh.get("cycles_done") or 0) + 1
    fresh["phase"] = "fast" if gate_ok else "wait_quota"
    save_state(fresh)
    _log_decision(log, "slow_drain_complete",
                  "queue empty, slow idle, cycle+1 phase={0}".format(fresh["phase"]))
    return True

def _main_locked(args):
    goal = load_goal(args.goal)
    log = os.path.join(FM_ROOT, ".omc", "supervisor_decisions.jsonl")
    max_cycles = args.max_cycles or goal["budgets"]["max_cycles"]
    one_shot = args.dry_run or args.once
    while True:
        st = load_state()
        cycles = int(st.get("cycles_done") or 0)
        cpu_h = _read_cpu_hours()
        tok_m, tok_unknown = _read_token_m()
        tok_spend = _token_spend_m(st, tok_m)
        snap = build_snapshot(REGISTRY, cycles, cpu_h, tok_spend)
        ok, why = evaluate_goal(goal["success_condition"], snap)
        b = goal["budgets"]
        tok_hit = (not tok_unknown) and tok_spend >= b.get("token_budget_m", 80)
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
            rows, _, _ = _harvest_rows(goal)
            print(json.dumps({"action": "harvest_plan", "n": len(rows),
                              "vids": [r["variant_id"] for r in rows]}, ensure_ascii=False))
            planned = decide_fast_loop(goal, dry_run=True)
            for a in planned:
                print(json.dumps(a, ensure_ascii=False, default=str))
            return 0

        materialize_known_verdicts(snap["variants"], VERDICTS_INC)
        if ok:
            rec = _log_decision(log, "goal_reached", "; ".join(why) or "all conditions met")
            write_stop_report("goal_reached", snap, why, rec["reason"])
            print(json.dumps(rec, ensure_ascii=False))
            return 0
        if budget_hit:
            rec = _log_decision(log, "budget_exhausted",
                                f"cycles={cycles} cpu_h={cpu_h} tok_m={tok_spend} tok_unknown={tok_unknown}")
            write_stop_report("budget_exhausted", snap, [rec["reason"]], rec["reason"])
            print(json.dumps(rec, ensure_ascii=False))
            return 0

        st = ensure_phase(load_state())
        _merge_save({"phase": st["phase"]})
        st = load_state()
        if st.get("phase") == "fast":
            _maybe_harvest(st, goal, log)
        st = load_state()
        if st.get("phase") == "slow":
            _maybe_start_slow_loop(goal, log)
            _maybe_finish_slow(goal, log)
        planned = decide_fast_loop(goal, dry_run=False)
        for a in planned:
            print(json.dumps(a, ensure_ascii=False, default=str))
            _log_decision(log, a["action"], a.get("reason", ""), a.get("refs") or [])

        if one_shot:
            return 0
        sleep_s = POLL_S
        for a in planned:
            if a.get("sleep_s"):
                sleep_s = min(sleep_s, int(a["sleep_s"]))
        time.sleep(max(1, sleep_s))

if __name__ == "__main__":
    sys.exit(main() or 0)
