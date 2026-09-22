#!/usr/bin/env python3
"""aligned slow loop: claim-driven, checkpoint resume, verdicts (0 token)"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import argparse, fcntl, json, logging, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
sys.path.insert(0, os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval"))
import monthly_backtest as mb
import registry_lib as rl
from evaluator import (build_summary, effective_sample_size, load_baseline_points,
                       attach_gated_metrics)
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel

try:
    import torch
    torch.set_num_threads(4)
except ImportError:
    pass

_MODELS = None

_METRICS_PATH = os.path.join(FM_ROOT, "data", "cache", "slow_loop_metrics.jsonl")

def _get_models():
    global _MODELS
    if _MODELS is None:
        daily = DailyModel()
        _MODELS = (daily, HourlyModel(shared_model=daily.model))
    return _MODELS

def _now():
    import datetime
    return datetime.datetime.now().isoformat()

def _git_rev():
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, cwd=HERE).stdout.strip() or "-"
    except Exception:
        return "-"

def _record_elapsed(variant_id, elapsed_s):
    os.makedirs(os.path.dirname(_METRICS_PATH), exist_ok=True)
    with open(_METRICS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"variant_id": variant_id, "elapsed_s": elapsed_s,
                            "ts": _now()}, ensure_ascii=False) + "\n")

def _no_data_verdict(row, batch_id=None):
    bid = batch_id or row.get("batch_id")
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": row["variant_id"],
        "symbol": row["symbol"],
        "cov_override": row.get("cov_override"),
        "cov_family": "unknown",
        "batch_id": bid,
        "status": "no_data",
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
        "weighted_dir_acc": 0.0,
        "mae": None,
        "mape": None,
        "decay": None,
        "decided_at": _now(),
        "checkpoint_path": "",
        "slow_loop_pid": os.getpid(),
        "git_rev": _git_rev(),
        "metrics": {
            "batch_id": bid,
            "symbol": row["symbol"],
            "n": 0,
            "n_eff": 0,
            "dir_acc": 0.0,
            "status": "no_data",
            "gate_pass": False,
            "p_value": 1.0,
        },
    }

def run_aligned_candidate(row, daily_cache_dir, checkpoint_dir, registry_path, batch_id=None):
    bid = batch_id or row.get("batch_id")
    try:
        return _run_inner(row, daily_cache_dir, checkpoint_dir, registry_path, bid)
    except Exception as e:
        tombstone = rl.make_error_tombstone(row["symbol"], row["variant_id"], bid, e)
        rl.append_verdict(registry_path, tombstone)
        return tombstone

def _run_inner(row, daily_cache_dir, checkpoint_dir, registry_path, bid):
    vid = row["variant_id"]
    os.makedirs(checkpoint_dir, exist_ok=True)
    cp = os.path.join(checkpoint_dir, vid + ".jsonl")
    completed, resumed = set(), {}
    if os.path.exists(cp):
        for line in open(cp, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                key = (str(rec.get("symbol", "")).lower(), int(rec["idx"]))
                completed.add(key)
                if "delta_pred" in rec and "delta_real" in rec and "error" not in rec:
                    resumed[key] = rec
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue
    daily_model, hourly_model = _get_models()
    t0 = time.time()
    with open(cp, "a", encoding="utf-8") as checkpoint_fp:
        data = mb.run_symbol_backtest(
            row["symbol"].upper(), daily_model, hourly_model,
            cov_override=row["cov_override"], max_points=row["max_points"],
            daily_cache_dir=daily_cache_dir,
            completed=completed, checkpoint_fp=checkpoint_fp,
            resumed_points=resumed)
    elapsed_s = round(time.time() - t0, 3)
    if data is None:
        v = _no_data_verdict(row, batch_id=bid)
    else:
        s = mb.summarize(data)
        if s is None:
            v = _no_data_verdict(row, batch_id=bid)
        else:
            s = dict(s)
            # gated 协变量: 注入 Active Mask 统计 (对照 run.py 注入条件; 评审 2026-09-18 HIGH)
            attach_gated_metrics(s, row["cov_override"], data["points"])
            baseline_pts = load_baseline_points(row["symbol"])
            baseline_dir_acc = None
            if baseline_pts:
                ok_count = sum(1 for pt in baseline_pts if pt.get("dir_ok"))
                baseline_dir_acc = ok_count / len(baseline_pts)
            v = build_summary(s, {"symbol": row["symbol"], "cov_override": row["cov_override"],
                                  "max_points": row["max_points"], "stage": "aligned"},
                              batch_id=bid, baseline_points=baseline_pts,
                              baseline_dir_acc=baseline_dir_acc)
            v["variant_id"] = row["variant_id"]
            v.setdefault("decided_at", _now())
    v["checkpoint_path"] = cp
    v["slow_loop_pid"] = os.getpid()
    v["git_rev"] = _git_rev()
    # ── TypeSafe 预筛伴随文件注入 ──────────────────────
    _proposal_path = row.get("_proposal_path") or row.get("proposal_path")
    if _proposal_path:
        from pathlib import Path as _Path
        _ps_path = str(_Path(_proposal_path).with_suffix(".prescreen.json"))
        if os.path.exists(_ps_path):
            try:
                with open(_ps_path, encoding="utf-8") as _f:
                    _ps = json.load(_f)
            except (json.JSONDecodeError, OSError) as _e:
                logging.warning("prescreen 文件解析失败 (%s): %s", _ps_path, _e)
                _ps = None

            if _ps:
                if "metadata" not in v:
                    v["metadata"] = {}
                v["metadata"]["prescreen"] = {
                    "status": _ps.get("status"),
                    "skip_suggested": _ps.get("skip_suggested"),
                    "plausibility": _ps.get("mechanism_plausibility"),
                    "novelty": _ps.get("novelty"),
                    "effect_size": _ps.get("effect_size"),
                    "note": _ps.get("note"),
                }
    os.makedirs(os.path.dirname(registry_path) or ".", exist_ok=True)
    rl.append_verdict(registry_path, v)
    _record_elapsed(row["variant_id"], elapsed_s)
    return v

def main(argv=None):
    # Host mem guards (2026-09-04 policy): flock max 2 + MemAvailable>=2GiB.
    # RLIMIT_AS is OFF by default — TimesFM safetensors mmap needs VAS≫RSS.
    # Optional light RSS self-check between candidates (cheap).
    try:
        from mem_guard import apply_mem_guard, check_and_shed, self_rss_ok
        apply_mem_guard(apply_limit=False)
    except SystemExit:
        raise
    except Exception as e:
        print(f"mem_guard import/apply failed: {e}", flush=True)
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--queue", default=os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl"))
    ap.add_argument("--inprogress", default=os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl"))
    ap.add_argument("--registry", default=os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl"))
    ap.add_argument("--checkpoint-dir", default=os.path.join(FM_ROOT, "data", "cache", "aligned_checkpoints"))
    ap.add_argument("--daily-cache-dir", default=os.path.join(FM_ROOT, "data", "cache", "daily_pred"))
    ap.add_argument("--batch-id", default=None, help="batch id injected by supervisor")
    args = ap.parse_args(argv)
    os.makedirs(args.checkpoint_dir, exist_ok=True)
    lock_file = os.path.join(os.path.dirname(args.checkpoint_dir), "aligned_slow_loop.lock")
    lock = open(lock_file, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another slow loop instance holds the lock; exit")
        return 0
    try:
        rl.queue_recover(args.queue, args.inprogress)
        while True:
            row = rl.queue_claim(args.queue, args.inprogress)
            if row is None:
                print("queue empty; done")
                return 0
            # Cheap RSS hygiene between candidates (no tight RLIMIT_AS).
            try:
                check_and_shed()
                if not self_rss_ok():
                    print("mem_guard: self RSS over ~3.5GiB; exiting for shed", flush=True)
                    return 1
            except Exception as _e:
                print(f"mem_guard shed/self-check: {_e}", flush=True)
            verdict = run_aligned_candidate(row, args.daily_cache_dir,
                                            args.checkpoint_dir, args.registry,
                                            batch_id=args.batch_id)
            rl.queue_ack(args.queue, args.inprogress, row,
                         os.path.join(os.path.dirname(args.checkpoint_dir), "aligned_pending.done.jsonl"))
            print(json.dumps({"variant_id": verdict["variant_id"],
                              "gate_pass": verdict.get("gate_pass"),
                              "status": verdict.get("status")}))
            if args.once:
                return 0
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

if __name__ == "__main__":
    sys.exit(main() or 0)
