"""FM_a PRAXIST 评估器核心 (P2, 2026-09-01)

契约: config/praxist_task.yaml (预注册口径)
- 主指标 ev_after_slippage (monthly_backtest.summarize 净口径, 统一秤)
- 硬门: n>=min_samples, IC>=min_ic (IC 由 DirAcc 距离 0.5 映射)
- 诊断级 (max_points 受限) 只产 incubator 证据, 永不过 Gem 门
"""
import json
import os

FM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

VALID_COVARIATES = {
    "rsi_state", "rsi_slope", "hourly_slope", "oi", "ccl", "basis_momentum",
    "ha_body", "calendar_cyclical", "reversal_shadow", "rsi6", "rsi12", "rsi24",
}

# P2 试运行范围: 信用>=2星品种 (loop-constraints 允许, 数据质量已核)
ALLOWED_SYMBOLS = {"ao", "bu", "cf", "fg", "fu", "i", "jm", "ma", "p", "sh", "sp", "ta", "ur", "m", "ss", "sr", "cj", "jd", "lh", "eg", "rb"}

# 证据阶梯 (2026-09-02 G6): 诊断档筛除 → aligned 档过硬门
STAGE_POINTS = {
    "diagnostic": (1, 6),      # 快筛: max_points 1..6, 永不过硬门 (结构性)
    "aligned": (350, 500),     # 近全量: max_points >= gate min_n=350, 可过预注册硬门
}
DEFAULT_STAGE = "diagnostic"


def validate_candidate(c):
    """候选 {symbol, cov_override, max_points[, stage]}; 非法候选拒绝"""
    if not isinstance(c, dict):
        return False, "candidate must be a mapping"
    if str(c.get("symbol", "")).lower() not in ALLOWED_SYMBOLS:
        return False, "symbol 不在允许清单"
    if c.get("cov_override") not in VALID_COVARIATES:
        return False, "cov_override 不在预注册协变量清单"
    stage = c.get("stage", DEFAULT_STAGE)
    if stage not in STAGE_POINTS:
        return False, f"stage 必须是 {'/'.join(STAGE_POINTS)}"
    lo, hi = STAGE_POINTS[stage]
    mp = c.get("max_points", 6 if stage == "diagnostic" else 400)
    if not isinstance(mp, int) or not (lo <= mp <= hi):
        return False, f"max_points 必须是 {lo}..{hi} (stage={stage}, 硬门要求 n>=350)"
    return True, "ok"


def build_summary(s, cand):
    """monthly_backtest.summarize 输出 + 候选 → 证据完整摘要

    run_summary.json 需含 variant_name/metrics/stage, 才能被 materializer
    可靠地物化为 result finding 并挂上指标 (2026-09-02 run 教训)。
    """
    m = map_summary(s)
    stage = cand.get("stage", DEFAULT_STAGE)
    variant = "{}_{}_{}_p{}".format(
        cand["symbol"], cand["cov_override"], stage, cand.get("max_points", 6)
    )
    gate_pass = gate(s, min_n=350, min_ic=0.05)
    return {
        "status": "ok",
        "usage_unknown": False,
        "stage": stage,
        "variant_name": variant,
        "symbol": cand["symbol"],
        "cov_override": cand["cov_override"],
        "n": m["n"],
        "pf": m["pf"],
        "ev": m["ev"],
        "maxdd": m["maxdd"],
        "dir_acc": m["dir_acc"],
        "gate_pass": gate_pass,
        "metrics": {
            "ev_after_slippage": m["ev"],
            "pf": m["pf"],
            "maxdd": m["maxdd"],
            "n": m["n"],
            "dir_acc": m["dir_acc"],
            "gate_pass": gate_pass,
        },
    }


def map_summary(s):
    """monthly_backtest.summarize 输出 → PRAXIST 指标命名"""
    return {
        "n": int(s.get("n", 0)),
        "pf": float(s.get("PF", 0.0)),
        "ev": float(s.get("EV", 0.0)),
        "maxdd": float(s.get("MaxDD", 0.0)),
        "dir_acc": float(s.get("DirAcc", 0.5)),
    }


def gate(s, min_n=350, min_ic=0.05):
    """预注册硬门: n 与方向性 IC(=2*|DirAcc-0.5|)"""
    m = s if "dir_acc" in s else map_summary(s)
    ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)
    return m["n"] >= min_n and ic >= min_ic
