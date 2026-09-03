#!/usr/bin/env python3
"""
two_star_candidate_runner.py - 2星->3星 协变量优化队列运行器

单次加载 TimesFM 模型, 按品种优先级 (DirAcc 距 65% 最近优先) 顺序跑
baseline + 候选协变量配置, 全量 396pt walk-forward 回测, 结果追加 JSONL。

特性:
  - 单模型加载, 避免每候选重启 (省 ~60s/候选 × N)
  - JSONL 原子追加, 断点续跑 (按 (sym,label) 去重跳过)
  - baseline (无 override, 用 scheme) + 候选 (--combo/--cov-override) 同窗口 A/B
  - 3 星硬约束: DirAcc>=65% (build_knowledge_base._stars_from_metrics)

用法:
  python scripts/two_star_candidate_runner.py                 # 全部作业
  python scripts/two_star_candidate_runner.py --tier A        # 仅 Tier A (距65%<=8pp)
  python scripts/two_star_candidate_runner.py --sym fu rb     # 指定品种
  python scripts/two_star_candidate_runner.py --dry-run       # 仅打印作业清单
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

# ── 路径设置 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, FM_ROOT)
os.chdir(FM_ROOT)

import numpy as np  # noqa: E402
import torch  # noqa: E402

# 复用 monthly_backtest 的回测逻辑 (同窗口, 同指标口径)
from scripts.monthly_backtest import run_symbol_backtest, summarize  # noqa: E402

RESULTS_JSONL = os.path.join(FM_ROOT, "reports", "two_star_results.jsonl")
LOG_PATH = os.path.join(FM_ROOT, "reports", "two_star_runner.log")


# ─────────────────────────────────────────────────────────
# 候选作业清单
# 设计原则 (Phase 9 经验):
#   1. ha_body 是历史最强 DirAcc 推升器 (SS +5.1pp, TA +2pp, EG/JD 改善)
#   2. 正交三角: 方向动量(ha_body) + 资金流(oi) + 均值回归(reversal_shadow)
#   3. 同一协变量对不同品种效果相反 -> 必须实测, 不假设
#   4. 3 星需 DirAcc>=65%, 重点推方向准确率
# 优先级: Tier A (距65%<=8pp) > B (9-13pp) > C (>=15pp, 文档化天花板)
# ─────────────────────────────────────────────────────────

def _job(sym, label, mode, covs):
    """构造一条作业。mode: baseline|single|combo; covs: None|str|list"""
    return {"sym": sym, "label": label, "mode": mode, "covs": covs}


def build_jobs():
    """返回按优先级排序的作业清单。每品种 baseline 在前 (同窗口 A/B 基准)。"""
    jobs = []

    # ═══ Tier A: DirAcc 57-59%, 距 65% <=8pp (3 星现实候选) ═══

    # FU 燃料油 59.1% (current: rsi_state+oi+bb_squeeze)
    s = "fu"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "ha_body+oi+reversal_shadow", "combo", ["ha_body", "oi", "reversal_shadow"]),
        _job(s, "ha_body+calendar", "combo", ["ha_body", "calendar_cyclical"]),
    ]

    # RB 螺纹钢 59.1% (current: ha_body)
    s = "rb"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "ha_body+oi+reversal_shadow", "combo", ["ha_body", "oi", "reversal_shadow"]),
        _job(s, "ha_body+calendar", "combo", ["ha_body", "calendar_cyclical"]),
        _job(s, "rsi_state+oi+ha_body", "combo", ["rsi_state", "oi", "ha_body"]),
    ]

    # FG 玻璃 59.1% (current: reversal_shadow)
    s = "fg"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "ha_body+oi+reversal_shadow", "combo", ["ha_body", "oi", "reversal_shadow"]),
        _job(s, "reversal_shadow+oi", "combo", ["reversal_shadow", "oi"]),
        _job(s, "ha_body+calendar", "combo", ["ha_body", "calendar_cyclical"]),
    ]

    # TA PTA 58% (current: ha_body, Phase 9 已优化, 精简候选)
    s = "ta"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "ha_body+oi+reversal_shadow", "combo", ["ha_body", "oi", "reversal_shadow"]),
        _job(s, "ha_body+calendar", "combo", ["ha_body", "calendar_cyclical"]),
    ]

    # LH 生猪 57% (current: reversal_shadow)
    s = "lh"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "ha_body+oi+reversal_shadow", "combo", ["ha_body", "oi", "reversal_shadow"]),
        _job(s, "reversal_shadow+oi", "combo", ["reversal_shadow", "oi"]),
    ]

    # ═══ Tier B: DirAcc 52-56%, 距 65% 9-13pp (困难) ═══

    # M 豆粕 56% (current: calendar_cyclical)
    s = "m"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+calendar", "combo", ["ha_body", "calendar_cyclical"]),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "rsi_state+oi", "combo", ["rsi_state", "oi"]),
        _job(s, "vor", "single", "vor"),
    ]

    # CF 棉花 56% (current: ha_body+calendar_cyclical)
    s = "cf"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+oi+calendar", "combo", ["ha_body", "oi", "calendar_cyclical"]),
        _job(s, "ha_body+reversal_shadow+calendar", "combo", ["ha_body", "reversal_shadow", "calendar_cyclical"]),
        _job(s, "rsi_state+oi+calendar", "combo", ["rsi_state", "oi", "calendar_cyclical"]),
    ]

    # EG 乙二醇 55% (current: ha_body+oi+reversal_shadow, Phase 9 已优化)
    s = "eg"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body+oi+reversal_shadow+calendar", "combo", ["ha_body", "oi", "reversal_shadow", "calendar_cyclical"]),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "rsi_state+oi+reversal_shadow", "combo", ["rsi_state", "oi", "reversal_shadow"]),
    ]

    # CJ 红枣 53% (current: reversal_shadow_gated_05)
    s = "cj"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+reversal_shadow_gated_05", "combo", ["ha_body", "reversal_shadow_gated_05"]),
        _job(s, "reversal_shadow", "single", "reversal_shadow"),
        _job(s, "ha_body+oi+reversal_shadow_gated_05", "combo", ["ha_body", "oi", "reversal_shadow_gated_05"]),
    ]

    # JD 鸡蛋 52% (current: rsi_state+oi, Phase 9 已优化)
    s = "jd"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "rsi_state+oi+calendar", "combo", ["rsi_state", "oi", "calendar_cyclical"]),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "rsi_state+oi+reversal_shadow", "combo", ["rsi_state", "oi", "reversal_shadow"]),
        _job(s, "rsi_state+oi+ha_body", "combo", ["rsi_state", "oi", "ha_body"]),
    ]

    # ═══ Tier C: DirAcc <=50%, 距 65% >=15pp (文档化天花板) ═══

    # JM 焦煤 50% (current: ha_body)
    s = "jm"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "rsi_state+oi+ha_body", "combo", ["rsi_state", "oi", "ha_body"]),
    ]

    # I 铁矿石 45.5% (current: rsi_state+oi+ha_body)
    s = "i"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+oi+reversal_shadow", "combo", ["ha_body", "oi", "reversal_shadow"]),
        _job(s, "ha_body+calendar", "combo", ["ha_body", "calendar_cyclical"]),
    ]

    # BU 沥青 45.5% (current: ha_body)
    s = "bu"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "bb_squeeze+ha_body", "combo", ["bb_squeeze", "ha_body"]),
    ]

    # P 棕榈油 45.5% (current: ha_body)
    s = "p"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
        _job(s, "ha_body+reversal_shadow", "combo", ["ha_body", "reversal_shadow"]),
        _job(s, "rsi_state+oi+ha_body", "combo", ["rsi_state", "oi", "ha_body"]),
    ]

    # AO 氧化铝 36.4% (current: hourly_slope)
    s = "ao"
    jobs += [
        _job(s, "baseline", "baseline", None),
        _job(s, "ha_body", "single", "ha_body"),
        _job(s, "ha_body+hourly_slope", "combo", ["ha_body", "hourly_slope"]),
        _job(s, "ha_body+oi", "combo", ["ha_body", "oi"]),
    ]

    return jobs


# Tier 分组 (按 DirAcc 距 65% 分)
TIER_A = {"fu", "rb", "fg", "ta", "lh"}
TIER_B = {"m", "cf", "eg", "cj", "jd"}
TIER_C = {"jm", "i", "bu", "p", "ao"}


def load_completed() -> set[tuple[str, str]]:
    """读 JSONL, 返回已完成的 (sym, label) 集合 (断点续跑)。"""
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


def append_result(rec: dict):
    """原子追加一条结果到 JSONL。"""
    os.makedirs(os.path.dirname(RESULTS_JSONL), exist_ok=True)
    with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_job(job, daily_model, hourly_model):
    """运行单条作业, 返回指标 dict。"""
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
    ap = argparse.ArgumentParser(description="2星->3星 协变量优化队列")
    ap.add_argument("--tier", choices=["A", "B", "C"], help="仅跑指定 Tier")
    ap.add_argument("--sym", nargs="*", help="仅跑指定品种")
    ap.add_argument("--dry-run", action="store_true", help="仅打印作业清单")
    args = ap.parse_args()

    all_jobs = build_jobs()

    # 过滤
    if args.tier:
        tier_set = {"A": TIER_A, "B": TIER_B, "C": TIER_C}[args.tier]
        all_jobs = [j for j in all_jobs if j["sym"] in tier_set]
    if args.sym:
        sym_set = {s.lower() for s in args.sym}
        all_jobs = [j for j in all_jobs if j["sym"] in sym_set]

    if args.dry_run:
        print(f"# 作业清单: {len(all_jobs)} 条")
        cur_sym = None
        for j in all_jobs:
            if j["sym"] != cur_sym:
                cur_sym = j["sym"]
                tier = "A" if cur_sym in TIER_A else "B" if cur_sym in TIER_B else "C"
                print(f"\n## {cur_sym.upper()} (Tier {tier})")
            cov_disp = j["covs"] if isinstance(j["covs"], str) else (
                "+".join(j["covs"]) if isinstance(j["covs"], list) else "(scheme baseline)")
            print(f"  - {j['label']:32} [{j['mode']}] {cov_disp}")
        print(f"\n总计 {len(all_jobs)} 作业, 预估 ~{len(all_jobs)*18//60}h (18min/作业)")
        return

    # 断点续跑
    completed = load_completed()
    pending = [j for j in all_jobs if (j["sym"], j["label"]) not in completed]

    log("=" * 70)
    log(f"2星->3星 协变量优化队列启动")
    log(f"总作业: {len(all_jobs)} | 已完成: {len(completed)} | 待跑: {len(pending)}")
    log(f"预估: ~{len(pending)*18//60}h (18min/作业, 顺序执行)")
    log("=" * 70)

    if not pending:
        log("全部作业已完成。")
        return

    # 加载模型 (一次)
    log("[模型] 加载 TimesFM 2.5 ...")
    t0 = time.time()
    torch.set_float32_matmul_precision("high")
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    log(f"[模型] 加载完成 ({time.time()-t0:.0f}s)")

    # 顺序执行
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

        # GPU 缓存清理
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    log("=" * 70)
    log(f"队列完成。结果: {RESULTS_JSONL}")
    log("=" * 70)


if __name__ == "__main__":
    main()
