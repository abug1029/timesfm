"""FM_a PRAXIST 评估器核心 (P2, 2026-09-01)

契约: config/praxist_task.yaml (预注册口径)
- 主指标 ev_after_slippage (monthly_backtest.summarize 净口径, 统一秤)
- 硬门: n>=min_samples, IC>=min_ic (IC 由 DirAcc 距离 0.5 映射)
- 诊断级 (max_points 受限) 只产 incubator 证据, 永不过 Gem 门
"""
import json
import os

# evaluator.py 位于 <FM_ROOT>/task_FM/evaluations/fm_eval/，上溯 3 级到 FM_ROOT
FM_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir))

VALID_COVARIATES = {
    "rsi_state", "rsi_slope", "hourly_slope", "oi", "ccl", "basis_momentum",
    "ha_body", "calendar_cyclical", "reversal_shadow", "rsi6", "rsi12", "rsi24",
    # Plan B: features.py dispatch 支持但原 VALID_COVARIATES 缺失
    "pca_momentum", "hurst", "gated_slope", "regime_gated",
    "vor",
    "ao_accel", "bb_squeeze",
    "reversal_shadow_gated_02", "reversal_shadow_gated_03", "reversal_shadow_gated_05",
    "sar_dist",
    "crack_spread_slope", "crack_spread_level", "crack_spread_zscore",
    "nvi", "qstick", "vwap_deviation", "stddev",
}

# Plan C: 动态协变量发现 (模块加载时执行一次)
_DYNAMIC_DISCOVERY_ERROR = None

try:
    def _discover_covariates_from_features():
        import ast
        features_path = os.path.join(FM_ROOT, "cascade", "features.py")
        if not os.path.exists(features_path):
            return set()
        with open(features_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename="features.py")
        covariates = set()
        _EXCLUDE = {"slope_only", "none", "baseline", "slope", "level", "zscore", "decay"}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.IfExp)):
                continue
            test = node.test
            if isinstance(test, ast.Compare):
                if isinstance(test.ops[0], ast.Eq):
                    cmp = test.comparators[0]
                    if isinstance(cmp, ast.Constant) and isinstance(cmp.value, str):
                        val = cmp.value
                        if val not in _EXCLUDE:
                            covariates.add(val)
                elif isinstance(test.ops[0], ast.In):
                    cmp = test.comparators[0]
                    if isinstance(cmp, (ast.List, ast.Tuple, ast.Set)):
                        for elt in cmp.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                val = elt.value
                                if val not in _EXCLUDE:
                                    covariates.add(val)
        return covariates

    _discovered = _discover_covariates_from_features()
    if _discovered:
        # 二次过滤: 排除 mode 参数 (可能是 mode 参数而非 covariate_type)
        _valid_discovered = {v for v in _discovered if len(v) >= 3 and v not in {"slope", "level", "zscore", "decay"}}
        _missing_in_static = _valid_discovered - VALID_COVARIATES
        VALID_COVARIATES |= _valid_discovered
except Exception:
    _DYNAMIC_DISCOVERY_ERROR = "dynamic discovery failed"

# 清理临时命名
for _n in ["_discover_covariates_from_features", "_discovered", "_missing_in_static"]:
    globals().pop(_n, None)


# Plan D: 协变量策略池 (task_FM/config/covariate_pool.json)
# 池是 peer 可提议协变量的单一事实源: status=active 可提议, archived 全局退役。
# AST 发现只做并集(只会加), 归档必须在此显式差集, 否则删静态项无效。
POOL_PATH = os.path.join(FM_ROOT, "task_FM", "config", "covariate_pool.json")
ARCHIVED_COVARIATES = {}   # name -> archived_reason
_POOL_ERROR = None


def _load_covariate_pool():
    """读 covariate_pool.json → (active_set, archived{name:reason}, err)。
    fail-open: 文件缺失/解析失败返回 (None, {}, err)，调用方不做任何归档/收窄。"""
    try:
        with open(POOL_PATH, "r", encoding="utf-8") as f:
            pool = json.load(f)
        covs = pool.get("covariates", {})
        active = {n for n, v in covs.items() if v.get("status") == "active"}
        archived = {n: str(v.get("archived_reason", "已归档"))
                    for n, v in covs.items() if v.get("status") == "archived"}
        return active, archived, None
    except Exception as e:
        return None, {}, str(e)


try:
    _active_pool, ARCHIVED_COVARIATES, _pool_err = _load_covariate_pool()
    if _active_pool is not None:
        # active 池 ∩ 已实现分派(static∪AST)，再剔归档：
        # 新 features.py 分支须先在池注册 active 才能被 peer 提议
        VALID_COVARIATES &= _active_pool
        VALID_COVARIATES -= set(ARCHIVED_COVARIATES)
    elif _pool_err:
        _POOL_ERROR = _pool_err
        import sys
        print("[WARN] covariate_pool.json 加载失败, fail-open 不收窄: %s" % _pool_err,
              file=sys.stderr)
except Exception as e:
    _POOL_ERROR = "covariate pool apply failed: %s" % e
    import sys
    print("[WARN] 协变量池应用失败, fail-open: %s" % e, file=sys.stderr)


# P2 试运行范围: 信用>=2星品种 (loop-constraints 允许, 数据质量已核)
ALLOWED_SYMBOLS = {"ao", "bu", "cf", "fg", "fu", "i", "jm", "ma", "p", "sh", "sp", "ta", "ur", "m", "ss", "sr", "cj", "jd", "lh", "eg", "rb"}

# 证据阶梯 (2026-09-02 G6): 诊断档筛除 → aligned 档过硬门
STAGE_POINTS = {
    "diagnostic": (1, 6),      # 快筛: max_points 1..6, 永不过硬门 (结构性)
    "aligned": (350, 600),     # 近全量: max_points >= gate min_n=350, 可过预注册硬门 (2026-09-09 用户批 500→600)
}
DEFAULT_STAGE = "diagnostic"


def validate_candidate(c):
    """候选 {symbol, cov_override, max_points[, stage]}; 非法候选拒绝"""
    if not isinstance(c, dict):
        return False, "candidate must be a mapping"
    if str(c.get("symbol", "")).lower() not in ALLOWED_SYMBOLS:
        return False, "symbol 不在允许清单"
    cov = c.get("cov_override")
    if cov in ARCHIVED_COVARIATES:
        return False, "covariate 已归档(archived): %s — %s" % (cov, ARCHIVED_COVARIATES[cov])
    if cov not in VALID_COVARIATES:
        return False, "cov_override 不在预注册协变量清单(active 池)"
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
