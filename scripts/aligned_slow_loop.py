#!/usr/bin/env python3
"""aligned slow loop: claim-driven, checkpoint resume, verdicts (0 token)"""
import argparse, fcntl, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
sys.path.insert(0, os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval"))
import monthly_backtest as mb
import registry_lib as rl
import numpy as np
from evaluator import build_summary, effective_sample_size
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from cascade.evaluation_metrics import calc_margin_maxdd_robust
from config.prediction_scheme import get_scheme
from config.backtest_config import TICK_SIZES, SLIPPAGE_TICKS

_MODELS = None

def _net_pnl_pts(points, symbol):
    """Gross p['pnl'] minus tick_size * SLIPPAGE_TICKS (same cost as calc_net_metrics)."""
    tick = TICK_SIZES.get(str(symbol).lower(), 1.0)
    slip = float(tick) * float(SLIPPAGE_TICKS)
    return np.array([float(p["pnl"]) - slip for p in points], dtype=float)

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

def _no_data_verdict(row):
    return {"variant_id": row["variant_id"], "symbol": row["symbol"],
            "cov_override": row["cov_override"], "max_points": row["max_points"],
            "n": 0, "pf": 0.0, "ev": 0.0, "maxdd": 0.0, "dir_acc": 0.5,
            "gate_pass": False, "ic": 0.0, "decided_at": _now(),
            "checkpoint_path": "", "slow_loop_pid": os.getpid(),
            "git_rev": _git_rev(), "schema": "fm.aligned_verdict.v1",
            "status": "no_data"}  # dead_variants 忽略 no_data

def run_aligned_candidate(row, daily_cache_dir, checkpoint_dir, registry_path):
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
        v = _no_data_verdict(row)
    else:
        s = mb.summarize(data)
        if s is None:
            v = _no_data_verdict(row)
        else:
            s = dict(s)
            s.setdefault("PF", s.get("profit_factor", 0.0))
            s.setdefault("EV", s.get("ev", 0.0))
            s.setdefault("MaxDD", s.get("max_dd", 0.0))
            s.setdefault("DirAcc", s.get("dir_acc", 0.5))
            v = build_summary(s, {"symbol": row["symbol"], "cov_override": row["cov_override"],
                                  "max_points": row["max_points"], "stage": "aligned"})
            v.setdefault("status", "ok")
            v["variant_id"] = row["variant_id"]
            v.setdefault("symbol", row["symbol"])
            v.setdefault("cov_override", row["cov_override"])
            v.setdefault("max_points", row["max_points"])
            v.setdefault("ic", round(2 * abs(float(v.get("dir_acc", 0.5)) - 0.5), 10))
            v.setdefault("decided_at", _now())
            v.setdefault("schema", "fm.aligned_verdict.v1")
            # SPEC-004: n_eff integration point
            v["n_eff"] = effective_sample_size(v.get("n", 0), horizon=24, step=2)
            v["n_eff_method"] = "bartlett_full_kernel_rho0.9"
            # SPEC-008: margin-based MaxDD with non-overlapping stride
            _ok_pts = [p for p in data["points"] if "error" not in p]
            _pnl_arr = _net_pnl_pts(_ok_pts, row["symbol"])
            _base_arr = np.array([p["base"] for p in _ok_pts])
            _scheme_obj = get_scheme(row["symbol"].upper())
            _cm = getattr(_scheme_obj, "contract_multiplier", 10.0) if _scheme_obj else 10.0
            v["margin_maxdd"] = calc_margin_maxdd_robust(
                net_pnl_pts=_pnl_arr, base_prices=_base_arr,
                contract_multiplier=_cm, horizon=24, step=2,
            )
    v["checkpoint_path"] = cp
    v["slow_loop_pid"] = os.getpid()
    v["git_rev"] = _git_rev()
    os.makedirs(os.path.dirname(registry_path) or ".", exist_ok=True)
    with open(registry_path, "a", encoding="utf-8") as f:
        rl.append_verdict(f, v)
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
            try:
                verdict = run_aligned_candidate(row, args.daily_cache_dir,
                                                args.checkpoint_dir, args.registry)
            except Exception as e:
                print(json.dumps({"variant_id": row["variant_id"], "error": str(e)}))
                # 不 ack: inprogress 残留, 下次启动 recover 重试。不写死亡 verdict。
                return 1
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
