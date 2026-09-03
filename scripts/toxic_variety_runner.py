#!/usr/bin/env python3
"""
toxic_variety_runner.py - AO 氧化铝 + JD 鸡蛋 有毒品种协变量替代验证

单次加载 TimesFM, 顺序跑 baseline + 候选, 396pt walk-forward 回测,
结果追加 JSONL, 断点续跑 (按 (sym,label) 去重)。

用法:
  python scripts/toxic_variety_runner.py
  python scripts/toxic_variety_runner.py --sym ao
  python scripts/toxic_variety_runner.py --sym jd
  python scripts/toxic_variety_runner.py --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, FM_ROOT)
os.chdir(FM_ROOT)

import torch  # noqa: E402
from scripts.monthly_backtest import run_symbol_backtest, summarize  # noqa: E402

RESULTS_JSONL = os.path.join(FM_ROOT, "reports", "toxic_variety_results.jsonl")
LOG_PATH = os.path.join(FM_ROOT, "reports", "toxic_variety.log")


def _job(sym, label, mode, covs):
    return {"sym": sym, "label": label, "mode": mode, "covs": covs}


def build_jobs():
    """返回按品种排序的作业清单。每品种 baseline 在前 (同窗口 A/B 基准)。"""
    jobs = []

    # ═══ AO 氧化铝 (current: hourly_slope, DirAcc 56.0%) ═══
    s = "ao"
    jobs += [
        _job(s, "baseline", "baseline", None),                          # hourly_slope (scheme)
        _job(s, "ha_body", "single", "ha_body"),                        # Phase 9 已失败 (对照)
        _job(s, "ao_accel", "single", "ao_accel"),                      # 对 UR 有效 (70%)
        _job(s, "vor", "single", "vor"),                                # 波动率比率
        _job(s, "bb_squeeze", "single", "bb_squeeze"),                  # 布林带突破
        _job(s, "reversal_shadow", "single", "reversal_shadow"),        # 影线反转
        _job(s, "calendar_cyclical", "single", "calendar_cyclical"),    # 日历周期
        _job(s, "hourly_slope+oi", "combo", ["hourly_slope", "oi"]),
        _job(s, "hourly_slope+calendar", "combo", ["hourly_slope", "calendar_cyclical"]),
        _job(s, "hourly_slope+reversal_shadow", "combo", ["hourly_slope", "reversal_shadow"]),
    ]

    # ═══ JD 鸡蛋 (current: rsi_state+oi, DirAcc 52.0%) ═══
    s = "jd"
    jobs += [
        _job(s, "baseline", "baseline", None),                          # rsi_state+oi (scheme)
        _job(s, "calendar_cyclical", "single", "calendar_cyclical"),    # 季节性
        _job(s, "gated_slope", "single", "gated_slope"),                # Phase 4d-2 旧配置
        _job(s, "calendar_cyclical+gated_slope", "combo", ["calendar_cyclical", "gated_slope"]),
        _job(s, "ao_accel", "single", "ao_accel"),
        _job(s, "bb_squeeze", "single", "bb_squeeze"),
        _job(s, "reversal_shadow", "single", "reversal_shadow"),
        _job(s, "hourly_slope+oi", "combo", ["hourly_slope", "oi"]),
        _job(s, "rsi_state+oi+calendar", "combo", ["rsi_state", "oi", "calendar_cyclical"]),
    ]

    return jobs


def load_completed():
    done = set()
    if not os.path.exists(RESULTS_JSONL):
        return done
    with open(RESULTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "OK":
                    done.add((rec["sym"], rec["label"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def append_result(rec):
    os.makedirs(os.path.dirname(RESULTS_JSONL), exist_ok=True)
    with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_job(job, daily_model, hourly_model):
    sym = job["sym"]
    mode = job["mode"]
    covs = job["covs"]
    cov_override = None
    cov_combo = None
    if mode == "single":
        cov_override = covs
    elif mode == "combo":
        cov_combo = covs

    t0 = time.time()
    data = run_symbol_backtest(
        sym, daily_model, hourly_model,
        cov_override=cov_override, cov_combo=cov_combo,
        clip_gap=None, cache_interval=10,
    )
    elapsed = time.time() - t0
    if data is None:
        return {"status": "SKIP", "elapsed": round(elapsed, 1)}
    s = summarize(data)
    if s is None:
        return {"status": "FAIL", "elapsed": round(elapsed, 1)}
    return {
        "status": "OK",
        "n": s["n"],
        "dir_acc": round(s["dir_acc"], 4),
        "dir12_acc": round(s.get("dir12_acc", 0), 4),
        "mape": round(s["mape"], 2),
        "ev_ratio": round(s["ev_ratio"], 4),
        "profit_factor": round(s["profit_factor"], 4),
        "max_dd": round(s["max_dd"], 4),
        "win_rate": round(s["win_rate"], 4),
        "decay": round(s["decay"], 2),
        "elapsed": round(elapsed, 1),
    }


def main():
    ap = argparse.ArgumentParser(description="AO+JD 有毒品种协变量替代验证")
    ap.add_argument("--sym", choices=["ao", "jd"], help="仅跑指定品种")
    ap.add_argument("--dry-run", action="store_true", help="仅打印作业清单")
    args = ap.parse_args()

    all_jobs = build_jobs()
    if args.sym:
        all_jobs = [j for j in all_jobs if j["sym"] == args.sym]

    if args.dry_run:
        print(f"# 作业清单: {len(all_jobs)} 条")
        cur_sym = None
        for j in all_jobs:
            if j["sym"] != cur_sym:
                cur_sym = j["sym"]
                print(f"\n## {cur_sym.upper()}")
            cov_disp = j["covs"] if isinstance(j["covs"], str) else (
                "+".join(j["covs"]) if isinstance(j["covs"], list) else "(scheme baseline)")
            print(f"  - {j['label']:36} [{j['mode']}] {cov_disp}")
        print(f"\n总计 {len(all_jobs)} 作业, 预估 ~{len(all_jobs)*18//60}h (18min/作业)")
        return

    completed = load_completed()
    pending = [j for j in all_jobs if (j["sym"], j["label"]) not in completed]

    log("=" * 70)
    log("AO+JD 有毒品种协变量替代验证 队列启动")
    log(f"总作业: {len(all_jobs)} | 已完成: {len(completed)} | 待跑: {len(pending)}")
    log(f"预估: ~{len(pending)*18//60}h (18min/作业, 顺序执行)")
    log("=" * 70)

    if not pending:
        log("全部作业已完成。")
        return

    log("[模型] 加载 TimesFM 2.5 ...")
    t0 = time.time()
    torch.set_float32_matmul_precision("high")
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    log(f"[模型] 加载完成 ({time.time()-t0:.0f}s)")

    for i, job in enumerate(pending, 1):
        sym = job["sym"]
        label = job["label"]
        cov_disp = job["covs"] if isinstance(job["covs"], str) else (
            "+".join(job["covs"]) if isinstance(job["covs"], list) else "baseline")
        log(f"[{i}/{len(pending)}] {sym.upper()} {label} [{cov_disp}] ...")

        try:
            res = run_job(job, daily_model, hourly_model)
        except Exception as e:
            res = {"status": "ERROR", "error": str(e), "elapsed": 0}

        rec = {
            "sym": sym,
            "label": label,
            "mode": job["mode"],
            "covs": cov_disp,
            "ts": datetime.now().isoformat(timespec="seconds"),
            **res,
        }
        append_result(rec)

        if res.get("status") == "OK":
            log(f"  -> OK  n={res['n']} DirAcc={res['dir_acc']:.1%} MAPE={res['mape']:.2f}% "
                f"EV={res['ev_ratio']:+.3f} PF={res['profit_factor']:.2f} "
                f"MaxDD={res['max_dd']:.2%} WR={res['win_rate']:.0%} ({res['elapsed']:.0f}s)")
        else:
            log(f"  -> {res.get('status')} {res.get('error','')}")

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    log("=" * 70)
    log(f"队列完成。结果: {RESULTS_JSONL}")
    log("=" * 70)


if __name__ == "__main__":
    main()
