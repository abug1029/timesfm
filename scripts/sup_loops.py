import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
del _repo_root

import registry_lib as rl
import search_promote
import search_trees as st
from goal_dsl import evaluate_goal

try:
    from cascade.statistical_tests import bh_fdr_promote
except ImportError:
    bh_fdr_promote = None

import sup_env
import sup_evidence
import aggregate_rejection_stats
import sup_family
import sup_harvest
import sup_lifecycle
import sup_paths
import sup_provider
import sup_state

# P2.2 (spec 2026-10-05 §6.7): 搜索树事件账（append-only；写入侧 2.3 落地）


# 复测触发判据：只保留"仅差样本量"的近失误筛选 (RETEST_GATE_N)。
# 非 v23 gate 镜像（v23 口径见
# docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md）。
# 宿主侧仅用于识别"仅差样本"的近失误裁决并安排复测，不改变慢环硬门本身。
#
# 2026-10-08（技术债债 2 裁定 C+a）：删除 v1 遗留的 ic/ev/pf 判据
#   （RETEST_GATE_IC / RETEST_PF_RATIO / INCUMBENT_PF）。
#   理由二条，任一独立成立：
#   1) 指标已退役 —— evaluator 契约明写"主指标 dir_acc/endpoint_mape/path_corr,
#      PF/EV/MaxDD 已退役"，门却仍用 ic/ev/pf；
#   2) 分母已损坏 —— L1 经济判决缺失使 knowledge_base.json 全表 historical_pf
#      为 null，INCUMBENT_PF 恒空，`.get(sym, 1.0)` 静默把"PF 相对 incumbent
#      超过 105%"改写成"PF 绝对值 > 1.05"，导致退化裁决被过度复测。
#   现只认 v2 schema 的 dir_acc 口径；非 v2 行显式排除而非静默改判。




def quota_gate(goal, now=None):
    """return (window_ok, sleep_seconds_if_blocked). Windows refill at reset+N*win_h."""
    cad = goal.get("cadence") or {}
    run_h = float(cad.get("run_budget_hours", 2.0))
    win_h = float(cad.get("quota_window_hours", 5.0))
    margin_h = float(cad.get("quota_margin_min", 30)) / 60.0
    need = run_h + margin_h
    reset = sup_provider._latest_429_reset()
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




def _retest_candidates(snapshot):
    """gate 仅因 n 不足而失败的近失误最新裁决。

    只认 v2 schema：dir_acc >= 0.50（v23 口径）。
    v1 legacy 的 ic/ev/pf 判据已于 2026-10-08 移除（债 2 裁定 C+a）：PF/EV/IC
    已退役，且 INCUMBENT_PF 因 L1 经济判决缺失恒空，`.get(sym, 1.0)` 会把
    "相对 incumbent 超 105%"静默改写成"PF 绝对值 > 1.05"造成过度复测。

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
        if n <= 0 or n >= sup_paths.RETEST_GATE_N:
            continue
        # 2026-10-08（债 2 裁定 C+a）：只认 v2 schema 的 dir_acc 口径。
        # 非 v2 行（v1 legacy 判据用 ic/ev/pf，指标已退役且分母被空 KB 损坏）
        # 显式排除，不再 fallback 到任何默认分母。
        if v.get("schema") != "fm.aligned_verdict.v2":
            continue
        dir_acc = float(v.get("dir_acc") or 0.0)
        if dir_acc >= 0.50:
            out.append(v)
    return out


def plan_sample_retests(goal):
    """只读：返回当前可排队的 (row, last_n, current_n) 复测计划 (不写队列)。"""
    cad = goal.get("cadence") or {}
    margin = int(cad.get("retest_min_new_points", 1))
    inflight = rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS)
    snap = sup_evidence._active_protocol_snapshot(sup_paths.REGISTRY)
    plan = []
    for v in _retest_candidates(snap):
        vid = v["variant_id"]
        if vid in inflight:
            continue
        cur_n = sup_evidence._valid_n_for_symbol(v["symbol"])
        if not cur_n or cur_n < sup_paths.RETEST_GATE_N:
            continue
        if cur_n - int(v.get("n") or 0) < margin:
            continue
        # v2 verdicts don't have max_points; use cadence default
        row = {"variant_id": vid, "symbol": v["symbol"],
               "cov_override": v["cov_override"],
               "max_points": sup_state._cad_int(cad, "aligned_max_points"),
               "stage": "aligned", "checkpoint_path": "",
               "enqueued_at": sup_lifecycle._now_iso(), "src_run": "supervisor_retest",
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
    added = rl.queue_enqueue(sup_paths.QUEUE, [row for row, _, _ in plan],
                             dead=set(), existing=set())
    if added:
        sup_state._merge_save({"phase": "slow"})
        for row, last_n, cur_n in plan:
            sup_lifecycle._log_decision(log, "sample_retest_enqueued",
                          "%s n %d->%d (gate_n=%d); checkpoint resume, 只算新点"
                          % (row["variant_id"], last_n, cur_n, sup_paths.RETEST_GATE_N),
                          [row["variant_id"]])
            sup_lifecycle._emit_event("action", "sample_retest_enqueued",
                        {"variant_id": row["variant_id"],
                         "last_n": last_n, "current_n": cur_n})
    return added

def _read_cpu_hours():
    p = os.path.join(sup_paths.FM_ROOT, "data", "cache", "slow_loop_metrics.jsonl")
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
    lock_path = os.path.join(sup_paths.FM_ROOT, "data", "cache", "aligned_slow_loop.lock")
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
    return bool(rl.queue_load(sup_paths.QUEUE) + rl.queue_load(sup_paths.INPROGRESS))

def _slow_drain_complete():
    return (not _queue_busy()) and (not _slow_loop_alive())

def ensure_phase(st):
    """Fill st['phase']. Queued/running aligned always wins (local CPU drain).

    wait_quota / paused_429 / failover must NOT block already-enqueued slow work.
    """
    if _queue_busy() or _slow_loop_alive():
        st["phase"] = "slow"
        return st
    if st.get("phase") in sup_paths.PHASES:
        return st
    if st.get("paused_429") and not sup_provider._run_active():
        if sup_provider._failover_configured() or sup_provider._llm_provider(st) == "failover":
            st["phase"] = "fast"
        else:
            st["phase"] = "wait_quota"
    else:
        st["phase"] = "fast"
    return st

def write_stop_report(kind, snap, why, budgets_line):
    os.makedirs(sup_paths.REPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(sup_paths.REPORT_DIR, f"supervisor_{kind}_{ts}.md")
    body = ["# Supervisor {0}".format(kind), "",
            "- ts: {0}".format(sup_lifecycle._now_iso()),
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
        with open(sup_paths.STATE_MD, "a", encoding="utf-8") as f:
            f.write("\n## Supervisor {0} ({1})\n\nSee {2}\n".format(kind, ts, path))
    except OSError as e:
        print(f"[WARN] Failed to write state file: {e}", file=sys.stderr)
    return path

def decide_fast_loop(goal, dry_run=False, now=None):
    """纯决策: 返回 actions 列表 [{action, reason, refs, argv?}]. dry_run 不调用 praxist。

    429 path: if FAILOVER_*/ANTHROPIC_FAILOVER_* configured, set llm_provider=failover,
    overlay BASE_URL+KEY+MODEL into env, and resume/start — do not wait_quota-only for Ark.
    Revert to primary only on the next NEW run_started when Ark quota is ok (no mid-run thrash).
    """
    actions = []
    ok, sleep_s = quota_gate(goal, now=now)
    active = sup_provider._run_active()
    meta = sup_provider._active_run_meta() if active else None
    st = ensure_phase(sup_state.load_state())
    failover_ok = sup_provider._failover_configured()
    provider_now = sup_provider._llm_provider(st)

    def _resume_argv(rd, provider):
        return [
            "resume", rd, "--daemonize", "--json",
            "--model-provider", "model_provider:anthropic_messages",
            *sup_provider._model_argv(provider),
        ]

    def _start_argv(provider):
        tag = "failover_qwen" if provider == "failover" else "primary"
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = os.path.join(
            sup_paths.FM_ROOT, "task_FM", "experiments", f"run_{ts}_{tag}_task_FM",
        )
        return [
            "start", "--task-path", os.path.join(sup_paths.FM_ROOT, "task_FM"),
            "--run-dir", run_dir,
            "--daemonize", "--json",
            "--model-provider", "model_provider:anthropic_messages",
            *sup_provider._model_argv(provider),
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
            r = sup_env._praxist(argv, env=sup_provider._praxist_env(provider))
            if r.get("ok"):
                upd = {"paused_429": False, "phase": "fast", **sup_provider._provider_state(provider)}
                sup_state._merge_save(upd)
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
            r = sup_env._praxist(argv, env=sup_provider._praxist_env(provider))
            if r.get("ok"):
                updates = {"paused_429": False, "phase": "fast", **sup_provider._provider_state(provider)}
                sup_lifecycle._emit_event("info", "run_started", {"provider": provider, "reason": reason})
                try:
                    js = json.loads(r["stdout"] or "{}")
                    if isinstance(js, dict):
                        if js.get("run_dir"):
                            updates["last_run_dir"] = js["run_dir"]
                        if js.get("run_id"):
                            updates["last_run_id"] = js["run_id"]
                except json.JSONDecodeError:
                    pass
                sup_state._merge_save(updates)
            return r
        return None

    # --- Active run + Ark quota banned ---
    if active and not ok:
        run_id = (meta or {}).get("run_id") or st.get("last_run_id")
        run_dir = (meta or {}).get("run_dir") or st.get("last_run_dir")
        if provider_now == "primary" and failover_ok and run_dir:
            stop_argv = ["stop", str(run_id)] if run_id else None
            can_resume = sup_provider._failover_can_resume_same_run(run_dir)
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
                    sup_env._praxist(["stop", str(run_id)])
                sup_state._merge_save({
                    "paused_429": False,
                    "last_run_dir": run_dir,
                    "last_run_id": run_id,
                    "phase": "fast",
                    **sup_provider._provider_state("failover"),
                })
                r = sup_env._praxist(continue_argv, env=sup_provider._praxist_env("failover"))
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
                            sup_state._merge_save(upd)
                    except json.JSONDecodeError:
                        pass
                if not r.get("ok"):
                    actions.append({
                        "action": "run_paused_429",
                        "reason": "failover continue failed; wait Ark reset",
                        "refs": [run_id, run_dir, (r.get("stderr") or "")[:200]],
                        "sleep_s": sleep_s,
                    })
                    sup_state._merge_save({"paused_429": True, **sup_provider._provider_state("failover")})
                sup_lifecycle._emit_event("action", "provider_switch", {"from": "primary", "to": "failover", "reason": "429_rate_limit"})
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
            r = sup_env._praxist(["stop", str(run_id)])
            if r.get("ok"):
                sup_state._merge_save({
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
                    if sup_provider._failover_can_resume_same_run(rd):
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
                sup_state._merge_save({"phase": "fast", **sup_provider._provider_state("failover")})
            if rd and not active and sup_provider._failover_can_resume_same_run(rd):
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
            sup_state._merge_save({"phase": "fast"})
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
    ap.add_argument("--goal", default=os.path.join(sup_paths.FM_ROOT, "scripts", "praxist_goal.yaml"))
    ap.add_argument("--root", default=sup_paths.FM_ROOT)
    ap.add_argument("--max-cycles", type=int, default=None)
    args = ap.parse_args(argv)
    # 目标品种集契约校验（L3）：goal.cadence.target_symbols 缺失即启动失败。
    # 放在 env 检查之前 —— 契约错误不该被"仅告警"的 env 分支吞掉。
    sup_state._assert_goal_symbols_contract(sup_state.load_goal(args.goal), args.goal)
    # Self-healing: load .env.praxist so startup doesn't depend on shell source.
    # Uses args.root so tests with --root tmp_path don't FATAL-exit.
    env_loaded = sup_env._load_dotenv(root=getattr(args, "root", None))
    missing_req, missing_rec = sup_env._check_required_env()
    if missing_req and env_loaded:
        # .env.praxist EXISTS but is missing required keys -> real config error.
        print("[FATAL] .env.praxist exists but required vars missing: %s"
              % ", ".join(missing_req), file=sys.stderr)
        sys.exit(2)
    if missing_req and not env_loaded:
        # No .env.praxist at this root (tests / non-standard setup). Warn only.
        print("[WARN] No .env.praxist at %s and required vars not in env: %s"
              % (getattr(args, "root", sup_paths.FM_ROOT), ", ".join(missing_req)),
              file=sys.stderr)
    if missing_rec:
        print("[WARN] Recommended env vars missing: %s (will use code defaults)"
              % ", ".join(missing_rec), file=sys.stderr)
    sup_lifecycle._arm_handlers()
    if args.root != sup_paths.FM_ROOT:
        # 测试可把模块级路径 monkeypatch; --root 仅给 harvest 用
        pass
    os.makedirs(os.path.dirname(sup_paths.LOCK_PATH), exist_ok=True)
    lock = open(sup_paths.LOCK_PATH, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another supervisor holds the lock; exit")
        sup_lifecycle._emit_event("info", "lock_contention", {"reason": "another supervisor holds the lock"})
        # 主动避让不是崩溃: 标记后退出, atexit 不得误报 unexpected_exit。
        sup_lifecycle._mark_stop_emitted()
        return 0
    try:
        return _main_locked(args)
    except Exception as e:
        sup_lifecycle._emit_event("critical", "error", {
            "exception": str(e),
            "traceback": traceback.format_exc()[-500:],
            "uptime_s": round(time.time() - sup_lifecycle._START_TIME, 1),
        })
        raise
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

def _harvest_rows(goal):
    cad = goal.get("cadence") or {}
    snap_now = sup_evidence._active_protocol_snapshot(sup_paths.REGISTRY)
    dead = rl.dead_variants(snap_now)
    # 修复：existing 包含当前协议的历史裁决（避免重复入队）
    in_flight = rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS)
    historical = set(snap_now.keys())
    existing = in_flight | historical
    pool = sup_evidence.load_covariate_pool()
    rows, pstats = sup_harvest.harvest_proposals(
        sup_paths.FM_ROOT, snap_now, dead, existing, pool,
        top_k=sup_state._cad_int(cad, "survivors_per_cycle"),
        aligned_max_points=sup_state._cad_int(cad, "aligned_max_points"),
        priority_symbols=cad.get("priority_symbols"),
        search_policy=sup_state._norm_search_policy(goal))
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
    queued = {r.get("variant_id") for r in rl.queue_load(sup_paths.QUEUE)}
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
            sup_paths.SEARCH_COMMITMENTS_PATH, "accept",
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
    if sup_state._norm_search_policy(goal) != "enforce":
        return 0
    index = st.load_tree_index(sup_paths.SEARCH_COMMITMENTS_PATH)
    if not index.unstopped():
        return 0
    stops = st.evaluate_tree_stops(index, snapshot or {},
                                   sup_evidence._dead_families(snapshot or {}))
    for tid, reason in stops:
        tree = index.trees[tid]
        st.append_commitment(sup_paths.SEARCH_COMMITMENTS_PATH, "stop",
                             tree_id=tid, symbol=tree.symbol,
                             family=tree.family, stop_reason=reason)
        sup_lifecycle._log_decision(log, "search_stop",
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
    if sup_state._norm_search_policy(goal) != "enforce":
        return 0
    index = st.load_tree_index(sup_paths.SEARCH_COMMITMENTS_PATH)
    if not index.unstopped():
        return 0
    registry = sup_state.load_preregistry(sup_paths.PREREGISTRY_PATH)
    promoted = 0
    for tree in list(index.unstopped()):
        decision = search_promote.evaluate_tree_promotion(
            tree, snapshot or {}, registry)
        if decision is None:
            continue
        mechanism, direction = search_promote.read_proposal_copy(
            sup_paths.FM_ROOT, decision.get("proposal_id") or "")
        if not mechanism or not direction:
            if isinstance(log, str) and log:
                sup_lifecycle._log_decision(log, "search_promote_skip",
                              "tree=%s missing proposal text" % tree.tree_id)
            continue
        row = search_promote.build_promotion_prereg(
            decision, mechanism=mechanism, predicted_direction=direction,
            registered_at=sup_lifecycle._now_iso(), prereg_id=uuid.uuid4().hex)
        # 先写 promote：该事件把树标成终态。若随后预注册追加失败，
        # 下一轮不会再晋升，避免同一棵树追加第二行。
        st.append_commitment(
            sup_paths.SEARCH_COMMITMENTS_PATH, "promote",
            tree_id=tree.tree_id, symbol=decision["symbol"],
            family=tree.family,
            proposal_id=decision.get("proposal_id") or "",
            variant_id=decision["variant_id"],
            stop_reason="promoted",
            delta_post=decision["delta_post"],
            n_required=decision["n_required"])
        _append_jsonl(sup_paths.PREREGISTRY_PATH, row)
        registry.append(row)
        index.stopped.add(tree.tree_id)
        if isinstance(log, str) and log:
            sup_lifecycle._log_decision(log, "search_promote",
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
    if sup_provider._run_active() or not last or harvested_already:
        return False
    rows, dead, existing, pstats = _harvest_rows(goal)
    if pstats and pstats.get("seen"):
        sup_lifecycle._log_decision(log, "proposal_scan",
                      "seen=%(seen)d rejected=%(rejected)d backlog=%(backlog)d reasons=%(reject_reasons)s" % pstats,
                      [])
    if pstats and pstats.get("search_shadow_log"):
        sup_lifecycle._log_decision(log, "search_shadow",
                      "would_reject=%s" % (pstats.get("search_would_reject"),))
    if rows:
        # P2.3 (spec §6.7)：先落搜索 accept 再入队（顺序依据见
        # _commit_search_accepts docstring：崩溃重放幂等；且必须在
        # _merge_save 之前完成，防 accept 因 harvested_already 永久丢失）。
        n_acc = _commit_search_accepts(rows, dead, existing)
        n = rl.queue_enqueue(sup_paths.QUEUE, rows, dead, existing)
        sup_lifecycle._log_decision(log, "harvested_proposals", f"enqueued {n}",
                      [r["variant_id"] for r in rows])
        if n_acc:
            sup_lifecycle._log_decision(log, "search_accepts", f"committed {n_acc}",
                          [r["variant_id"] for r in rows
                           if r.get("search_role")])
        sup_state._merge_save({"last_harvested_run_id": last, "phase": "slow"})
        try:
            from praxist_assets_archive import archive_fast_harvest
            archive_fast_harvest(last, rows, sup_state.load_state())
        except Exception as e:
            sup_lifecycle._log_decision(log, "assets_archive_error", f"harvest: {e}")
    else:
        sup_lifecycle._log_decision(log, "harvest_empty",
                      "finished run produced 0 valid proposals "
                      "(need results/**/proposals/*.json; reject_reasons=%s)"
                      % (pstats.get("reject_reasons") if pstats else {}))
        gate_ok, _ = quota_gate(goal)
        fresh = sup_state.load_state()
        fresh["cycles_done"] = int(fresh.get("cycles_done") or 0) + 1
        fresh["last_harvested_run_id"] = last
        fresh["phase"] = "fast" if gate_ok else "wait_quota"
        sup_state.save_state(fresh)
    return True


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
    st = sup_state.load_state()
    if st.get("phase") != "slow":
        return
    if not _queue_busy() or _slow_loop_alive():
        return
    out_path = os.path.join(sup_paths.FM_ROOT, "data", "cache", "slow_loop.out")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_fp = open(out_path, "ab")
    try:
        project_python = os.path.join(sup_paths.FM_ROOT, ".venv", "bin", "python")
        if not os.path.isfile(project_python):
            project_python = sys.executable
        batch_id = "batch_" + uuid.uuid4().hex[:8]
        # Capture current queue records for batch tracking
        try:
            batch_records = rl.queue_load(sup_paths.QUEUE) + rl.queue_load(sup_paths.INPROGRESS)
        except Exception:
            batch_records = []

        # 批次 A2：两段式写入 active_runs.json（防硬杀孤儿）
        # 第一步：Popen 前写意图记录（含 batch_id）
        active_runs_path = os.path.join(sup_paths.FM_ROOT, "data", "cache", "active_runs.json")
        intent_record = {
            "batch_id": batch_id,
            "status": "starting",
            "start_intent_ts": int(time.time())
        }
        try:
            import json
            with open(active_runs_path, "w") as f:
                json.dump(intent_record, f)
        except Exception as e:
            sup_lifecycle._log_decision(log, "active_runs_intent_write_failed", str(e))

        proc = subprocess.Popen(
            [project_python, os.path.join(sup_paths.HERE, "aligned_slow_loop.py"),
             "--batch-id", batch_id],
            stdout=out_fp, stderr=subprocess.STDOUT, start_new_session=True)

        # 第二步：Popen 后补 pid + 进程创建时刻
        try:
            import json
            complete_record = {
                "batch_id": batch_id,
                "pid": proc.pid,
                "status": "running",
                "start_intent_ts": intent_record["start_intent_ts"],
                "pid_assigned_ts": int(time.time()),
                "cmdline": " ".join([project_python, os.path.join(sup_paths.HERE, "aligned_slow_loop.py"), "--batch-id", batch_id])
            }
            with open(active_runs_path, "w") as f:
                json.dump(complete_record, f)
        except Exception as e:
            sup_lifecycle._log_decision(log, "active_runs_complete_write_failed", str(e))

        # Persist batch_id for FDR promotion on completion
        fresh = sup_state.load_state()
        fresh["current_batch_id"] = batch_id
        fresh["current_batch_records"] = [
            {"variant_id": r.get("variant_id"), "symbol": r.get("symbol", "") or ""}
            for r in batch_records if r.get("variant_id")]
        sup_state.save_state(fresh)
    finally:
        out_fp.close()
    sup_lifecycle._log_decision(log, "slow_loop_started", "phase=slow, queue busy")

def _maybe_finish_slow(goal, log):
    st = sup_state.load_state()
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
                    for vrec in rl.read_verdicts(sup_paths.REGISTRY):
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
                wait_for_batch(batch_id, batch_records, sup_paths.REGISTRY, timeout=0)
        except Exception as e:
            sup_lifecycle._log_decision(log, "wait_for_batch_error", str(e))
    # Batch completion: apply FDR promotion to batch verdicts
    if batch_id:
        batch_verdicts = []
        try:
            all_verdicts = rl.read_verdicts(sup_paths.REGISTRY)
            batch_verdicts = [v for v in all_verdicts if v.get("batch_id") == batch_id]
            if batch_verdicts and bh_fdr_promote is not None:
                updates = sup_family.promote_batch_for_persistence(batch_verdicts)
                if updates:
                    rl.update_batch_verdicts(sup_paths.REGISTRY, batch_id, updates)
                    sup_lifecycle._log_decision(log, "batch_fdr_promote",
                                 f"batch={batch_id} promoted={len(updates)}")
        except Exception as e:
            sup_lifecycle._log_decision(log, "batch_fdr_error", str(e))
        try:
            members = sup_family.load_family_members(sup_paths.FAMILY_REGISTRY)
            now = datetime.now(timezone.utc)
            touched = False
            for verdict in batch_verdicts:
                if not isinstance(verdict, dict) or verdict.get("run_mode") != "confirmation":
                    continue
                try:
                    symbol = verdict.get("symbol")
                    if isinstance(symbol, str) and symbol:
                        family_key = sup_family.family_key_for(symbol)
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
                    result = sup_family._finalize_confirmation_verdict(verdict, family_members, now)
                    if not isinstance(result, dict) or not isinstance(result.get("members"), list):
                        continue
                    if family_key is None:
                        continue
                    members = sup_family._merge_family_members(members, family_key, result["members"])
                    touched = True
                except Exception as e:
                    sup_lifecycle._log_decision(log, "confirmation_finalize_error", str(e),
                                  [str(verdict.get("variant_id") or "")])
            if touched:
                sup_family.save_family_members(sup_paths.FAMILY_REGISTRY, members)
        except Exception as e:
            sup_lifecycle._log_decision(log, "confirmation_finalize_error", str(e))
        try:
            cleanup_batch_workers(batch_id)
        except Exception as e:
            sup_lifecycle._log_decision(log, "cleanup_batch_error", str(e))
        # Clear batch tracking from state
        fresh = sup_state.load_state()
        fresh.pop("current_batch_id", None)
        fresh.pop("current_batch_records", None)
        fresh.pop("current_batch_variant_ids", None)  # legacy key
        sup_state.save_state(fresh)
    snap = rl.load_snapshot(sup_paths.REGISTRY)
    # 物化给 peer 看的证据同样只认当前协议；被排除的行显式报数，不静默。
    _cur_fp = sup_evidence._current_protocol_fingerprint()
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
    sup_evidence.materialize_known_verdicts(
        snap, sup_paths.VERDICTS_INC,
        status_map=sup_evidence.load_symbol_status(),
        queue_ids=rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS),
        proposed_ids=sup_evidence.collect_proposed_variant_ids(sup_paths.FM_ROOT),
        root=sup_paths.FM_ROOT,
        excluded_items=_excl,
    )
    aggregate_rejection_stats.main()  # M3: 刷新拒收摘要
    sup_harvest.materialize_covariate_menu(sup_evidence.load_covariate_pool(), sup_paths.MENU_INC)
    gate_ok, _ = quota_gate(goal)
    fresh = sup_state.load_state()
    fresh["cycles_done"] = int(fresh.get("cycles_done") or 0) + 1
    fresh["phase"] = "fast" if gate_ok else "wait_quota"
    sup_state.save_state(fresh)
    sup_lifecycle._log_decision(log, "slow_drain_complete",
                  "queue empty, slow idle, cycle+1 phase={0}".format(fresh["phase"]))
    try:
        from praxist_assets_archive import archive_slow_cycle
        archive_slow_cycle(fresh, goal)
    except Exception as e:
        sup_lifecycle._log_decision(log, "assets_archive_error", f"slow: {e}")
    return True

def _main_locked(args):
    log = os.path.join(sup_paths.FM_ROOT, ".omc", "supervisor_decisions.jsonl")
    one_shot = args.dry_run or args.once
    # Pre-flight: ensure baseline metrics/points exist for all goal symbols
    try:
        goal_for_baselines = sup_state.load_goal(args.goal)
        sup_evidence.ensure_baselines(sup_state._goal_target_symbols(goal_for_baselines), args.root)
    except Exception as e:
        print(f"[ERROR] ensure_baselines pre-flight failed: {e}", file=sys.stderr)
    while True:
        sup_lifecycle._write_heartbeat()
        code = sup_lifecycle._shutdown_exit()
        if code is not None:
            return code
        # Reload goal every poll so hot token_budget_m / max_cycles edits apply
        # without restart (2026-09-08: stale 50 in-memory while disk was 80 → false
        # budget_exhausted at tok_m=52.516).
        goal = sup_state.load_goal(args.goal)
        max_cycles = args.max_cycles or goal["budgets"]["max_cycles"]
        st = sup_state.load_state()
        cycles = int(st.get("cycles_done") or 0)
        cpu_h = _read_cpu_hours()
        tok_m, tok_unknown = sup_state._read_token_m()
        tok_spend = sup_state._token_spend_m(st, tok_m)
        snap = sup_evidence.build_snapshot(sup_paths.REGISTRY, cycles, cpu_h, tok_spend)
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
            sup_lifecycle._mark_stop_emitted()
            return 0

        sup_harvest.materialize_covariate_menu(sup_evidence.load_covariate_pool(), sup_paths.MENU_INC)
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
            _full_mb = rl.load_snapshot(sup_paths.REGISTRY)
            _mb_kwargs["excluded_items"] = {
                vid: v for vid, v in _full_mb.items()
                if v.get("protocol_fingerprint") != _only_fp_mb}
        sup_evidence.materialize_known_verdicts(
            snap["variants"], sup_paths.VERDICTS_INC,
            status_map=sup_evidence.load_symbol_status(),
            queue_ids=rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS),
            proposed_ids=sup_evidence.collect_proposed_variant_ids(sup_paths.FM_ROOT),
            root=sup_paths.FM_ROOT,
            **_mb_kwargs)
        aggregate_rejection_stats.main()  # M3: 刷新拒收摘要
        if ok:
            rec = sup_lifecycle._log_decision(log, "goal_reached", "; ".join(why) or "all conditions met")
            write_stop_report("goal_reached", snap, why, rec["reason"])
            sup_lifecycle._emit_event("critical", "goal_reached", {
                "why": why, "cycles_done": cycles, "cpu_h": cpu_h, "tok_m": tok_spend,
                "symbols_hit": sorted(snap.get("symbols_hit") or []),
                "uptime_s": round(time.time() - sup_lifecycle._START_TIME, 1),
            })
            # 干净终止: 先标记, 否则 atexit 兜底会误报 supervisor_stopped/unexpected_exit。
            sup_lifecycle._mark_stop_emitted()
            print(json.dumps(rec, ensure_ascii=False))
            return 0
        if budget_hit:
            # If a fast run is still alive, do NOT exit — wait for it to finish so we
            # can harvest→slow before any budget_exhausted return (2026-09-07 lesson:
            # exited at tok>budget while failover run lived → missed harvest).
            if sup_provider._run_active():
                sup_lifecycle._log_decision(
                    log, "budget_hit_wait_run",
                    f"cycles={cycles}/{max_cycles} cpu_h={cpu_h} "
                    f"tok_m={tok_spend}/{tok_budget}; "
                    "defer exit until active run ends then harvest/slow",
                )
                budget_hit = False
            else:
                # Drain finished-run harvest + local slow queue BEFORE exiting on budget.
                st_pre = sup_state.load_state()
                code = sup_lifecycle._shutdown_exit()
                if code is not None:
                    return code
                _maybe_harvest(st_pre, goal, log)
            st_pre = sup_state.load_state()
            if st_pre.get("phase") == "slow" or _queue_busy() or _slow_loop_alive():
                if st_pre.get("phase") != "slow":
                    sup_state._merge_save({"phase": "slow"})
                    sup_lifecycle._emit_event("action", "phase_change", {"from": "fast", "to": "slow"})
                _maybe_start_slow_loop(goal, log)
                # One-shot drain wait is not appropriate here; leave slow running and
                # only exit once queue is empty. If still draining, keep process alive.
                if not _slow_drain_complete():
                    sup_lifecycle._log_decision(
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
                    fresh_cycles = int(sup_state.load_state().get("cycles_done") or 0)
                    fresh_cpu_h = _read_cpu_hours()
                    fresh_tok_m, fresh_tok_unknown = sup_state._read_token_m()
                    fresh_tok_spend = sup_state._token_spend_m(sup_state.load_state(), fresh_tok_m)
                    fresh_snap = sup_evidence.build_snapshot(sup_paths.REGISTRY, fresh_cycles, fresh_cpu_h, fresh_tok_spend)
                    fresh_ok, fresh_why = evaluate_goal(goal["success_condition"], fresh_snap)
                    if fresh_ok:
                        rec = sup_lifecycle._log_decision(log, "goal_reached",
                                            "; ".join(fresh_why) or "all conditions met (post-slow-drain)")
                        write_stop_report("goal_reached", fresh_snap, fresh_why, rec["reason"])
                        sup_lifecycle._emit_event("critical", "goal_reached", {
                            "why": fresh_why, "cycles_done": fresh_cycles,
                            "cpu_h": fresh_cpu_h, "tok_m": fresh_tok_spend,
                            "source": "budget_hit_post_slow_drain",
                        })
                        sup_lifecycle._mark_stop_emitted()
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
                rec = sup_lifecycle._log_decision(log, "budget_exhausted",
                                    f"cycles={cycles}/{max_cycles} cpu_h={cpu_h} "
                                    f"tok_m={tok_spend}/{tok_budget} tok_unknown={tok_unknown} "
                                    f"tok_hit={tok_hit}")
                write_stop_report("budget_exhausted", snap, [rec["reason"]], rec["reason"])
                sup_lifecycle._emit_event("critical", "budget_exhausted", {
                    "cycles": cycles, "cpu_h": cpu_h, "tok_m": tok_spend,
                    "tok_unknown": tok_unknown,
                    "uptime_s": round(time.time() - sup_lifecycle._START_TIME, 1),
                })
                # 干净终止: 先标记, 否则 atexit 兜底会误报 supervisor_stopped/unexpected_exit。
                sup_lifecycle._mark_stop_emitted()
                print(json.dumps(rec, ensure_ascii=False))
                return 0

        st = ensure_phase(sup_state.load_state())
        st = sup_state._merge_save({"phase": st["phase"]})
        # Harvest finished runs even during paused_429 / wait_quota.
        code = sup_lifecycle._shutdown_exit()
        if code is not None:
            return code
        if not sup_provider._run_active():
            _maybe_harvest(st, goal, log)
        # n-不足型近失误自动复测 (本地慢环, 不受 LLM 暂停/failover 影响)。
        try:
            _maybe_enqueue_retests(goal, log)
        except Exception as e:
            sup_lifecycle._log_decision(log, "retest_scan_error", str(e))
        try:
            sup_family._maybe_enqueue_confirmations(log, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            sup_lifecycle._log_decision(log, "confirmation_enqueue_error", str(e))
        st = sup_state.load_state()
        # Local aligned drain is never blocked by LLM pause/failover.
        if st.get("phase") == "slow" or _queue_busy() or _slow_loop_alive():
            if st.get("phase") != "slow":
                sup_state._merge_save({"phase": "slow"})
            _maybe_start_slow_loop(goal, log)
            _maybe_finish_slow(goal, log)
        planned = decide_fast_loop(goal, dry_run=False)
        for a in planned:
            print(json.dumps(a, ensure_ascii=False, default=str))
            sup_lifecycle._log_decision(log, a["action"], a.get("reason", ""), a.get("refs") or [])

        # Session unstick (ops nudge / optional disk backfill). Safe no-op when healthy.
        try:
            from praxist_session_unstick import detect_and_act as _session_unstick
            _u = _session_unstick(dry_run=False, force=False)
            if _u.get("action") not in (None, "noop") or _u.get("escalate"):
                sup_lifecycle._log_decision(
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
            sup_lifecycle._log_decision(log, "session_unstick_error", str(e))

        if one_shot:
            sup_lifecycle._mark_stop_emitted()
            return 0
        sleep_s = sup_paths.POLL_S
        for a in planned:
            if a.get("sleep_s"):
                sleep_s = min(sleep_s, int(a["sleep_s"]))
        sup_lifecycle._sleep_interruptible(max(1, sleep_s))
