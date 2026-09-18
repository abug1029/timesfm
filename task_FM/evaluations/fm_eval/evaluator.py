"""FM_a PRAXIST 评估器核心 (P2, 2026-09-01; v23 2026-09-16)

契约: config/praxist_task.yaml (预注册口径)
- 主指标: dir_acc, endpoint_mape, path_corr (PF/EV/MaxDD 已退役)
- 硬门: n>=min_n, n_eff>=min_n_eff, dir_acc>=adaptive_threshold
- DM 检验: pair_dir_ok_series + diebold_mariano_p
- 诊断级 (max_points 受限) 只产 incubator 证据, 永不过 Gem 门
"""
import json
import math
import os
import sys

import numpy as np

# evaluator.py 位于 <FM_ROOT>/task_FM/evaluations/fm_eval/，上溯 3 级到 FM_ROOT
FM_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir))

# 导入统计检验模块
sys.path.insert(0, os.path.join(FM_ROOT, "cascade"))
try:
    from statistical_tests import pair_dir_ok_series, diebold_mariano_p
    from cov_family import resolve_cov_family
except ImportError as e:
    print(f"[WARN] 统计检验模块加载失败: {e}", file=sys.stderr)
    pair_dir_ok_series = None
    diebold_mariano_p = None
    resolve_cov_family = None

VALID_COVARIATES = {
    "rsi_state", "rsi_slope", "hourly_slope", "oi", "ccl", "basis_momentum",
    "ha_body", "calendar_cyclical", "reversal_shadow", "rsi6", "rsi12", "rsi24",
    "pca_momentum", "hurst", "gated_slope", "regime_gated",
    "vor",
    "ao_accel", "bb_squeeze",
    "reversal_shadow_gated_02", "reversal_shadow_gated_03", "reversal_shadow_gated_05",
    "sar_dist",
    "crack_spread_slope", "crack_spread_level", "crack_spread_zscore",
    "nvi", "qstick", "vwap_deviation", "stddev",
}

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
        _valid_discovered = {v for v in _discovered if len(v) >= 3 and v not in {"slope", "level", "zscore", "decay"}}
        VALID_COVARIATES |= _valid_discovered
except Exception:
    _DYNAMIC_DISCOVERY_ERROR = "dynamic discovery failed"

for _n in ["_discover_covariates_from_features", "_discovered", "_missing_in_static"]:
    globals().pop(_n, None)

POOL_PATH = os.path.join(FM_ROOT, "task_FM", "config", "covariate_pool.json")
ARCHIVED_COVARIATES = {}
_POOL_ERROR = None

def _load_covariate_pool():
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
        VALID_COVARIATES &= _active_pool
        VALID_COVARIATES -= set(ARCHIVED_COVARIATES)
    elif _pool_err:
        _POOL_ERROR = _pool_err
        print("[WARN] covariate_pool.json 加载失败, fail-open 不收窄: %s" % _pool_err,
              file=sys.stderr)
except Exception as e:
    _POOL_ERROR = "covariate pool apply failed: %s" % e
    print("[WARN] 协变量池应用失败, fail-open: %s" % e, file=sys.stderr)

# ── gated 协变量通用声明 (spec §5: covariate_pool.json 条目声明 "gated": true) ──
def _load_gated_covariates():
    """读取 covariate_pool.json 中声明 "gated": true 的协变量名集合.

    返回 (names, err): err 非 None 表示加载失败 — fail-open 空集 (不收窄既有行为,
    误判为非 gated 仅意味着走既有全量 dir_acc 口径) + stderr WARN (评审 MEDIUM-1:
    失败不得静默, 对齐 _load_covariate_pool 的 [WARN] 告警风格).
    """
    try:
        with open(POOL_PATH, "r", encoding="utf-8") as f:
            pool = json.load(f)
        covs = pool.get("covariates", {})
        return ({n for n, v in covs.items()
                 if isinstance(v, dict) and v.get("gated") is True}, None)
    except Exception as e:
        print("[WARN] gated 协变量声明加载失败, fail-open 全量口径: %s" % e, file=sys.stderr)
        return set(), str(e)


GATED_COVARIATES, _GATED_POOL_ERROR = _load_gated_covariates()
# 评审 MEDIUM-1: 导入期加载失败标记 — build_summary 据此把该 run 的全量口径 verdict
# 落 gate_basis="full_fallback", 使 gated 候选被静默误判为全量口径这一 fail-open 可见.
# (声明加载失败时无法按候选识别 gated, 故 run 级整体标记.)
_GATED_POOL_LOAD_FAILED = _GATED_POOL_ERROR is not None


def is_gated_covariate(name):
    """covariate 是否声明 gated (通用开关, 非按名特判)."""
    return name in GATED_COVARIATES


def attach_gated_metrics(s, cov_name, points):
    """注入 gated 协变量 Active Mask 统计到 summary 草稿 s (两入口共用).

    run.py do_evaluate 与 aligned_slow_loop._run_inner 共用本函数, 注入条件
    单一事实源, 消除双写漂移 (评审 2026-09-18 HIGH).
    gated → s["gated_metrics"] = active_mask_metrics(points) (build_summary 消费后 pop);
    非 gated → s 原样返回 (零改动).
    """
    if is_gated_covariate(cov_name):
        s["gated_metrics"] = active_mask_metrics(points)
    return s


def active_mask_metrics(points):
    """gated 协变量 Active Mask 统计 (spec §5 Active DirAcc, 2026-09-18).

    分类口径 (互斥分区, n_active + n_zero + n_nan == n_total):
    - Signal != 0 且非 NaN 且 dir_ok 可评 → active (active_dir_acc 分母)
    - Signal == 0 (含 -0.0) → n_zero (门控未激活)
    - Signal NaN/缺失/非法, 或目标不可评 (dir_ok 缺失) → n_nan (标尺失效)

    n_active == 0 → active_dir_acc = NaN (fail-closed, 下游硬门自然拒),
    绝不触发 ZeroDivisionError. error 点不计入任何计数.
    """
    n_total = n_active = n_zero = n_nan = n_ok = 0
    for p in points:
        if not isinstance(p, dict) or "error" in p:
            continue
        n_total += 1
        raw = p.get("signal")
        if isinstance(raw, bool):
            # spec §3.3 信号为 float; bool 的 float(True)=1.0 不得伪装激活 → NaN 桶
            sig = float("nan")
        else:
            try:
                sig = float(raw)
            except (TypeError, ValueError):
                sig = float("nan")
        if math.isnan(sig):
            n_nan += 1
        elif sig == 0.0:
            n_zero += 1
        elif p.get("dir_ok") is None:
            n_nan += 1
        else:
            n_active += 1
            if bool(p.get("dir_ok")):
                n_ok += 1
    return {
        "active_dir_acc": (n_ok / n_active) if n_active > 0 else float("nan"),
        "n_active": n_active,
        "n_total": n_total,
        "n_zero": n_zero,
        "n_nan": n_nan,
    }


ALLOWED_SYMBOLS = {"ao", "bu", "cf", "fg", "fu", "i", "jm", "ma", "p", "sh", "sp", "ta", "ur", "m", "ss", "sr", "cj", "jd", "lh", "eg", "rb"}

STAGE_POINTS = {
    "diagnostic": (1, 6),
    "aligned": (350, 600),
}
DEFAULT_STAGE = "diagnostic"


def validate_candidate(c):
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
    if isinstance(mp, bool) or not isinstance(mp, int) or not (lo <= mp <= hi):
        return False, f"max_points 必须是 {lo}..{hi} (stage={stage}, 硬门要求 n>=350)"
    return True, "ok"


def load_baseline_points(symbol, root=None):
    """Load baseline points from JSONL file."""
    if root is None:
        root = os.path.join(FM_ROOT, "task_FM", "config")
    path = os.path.join(root, f"baseline_points_{symbol}.jsonl")
    if not os.path.exists(path):
        return []
    points = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    points.append(json.loads(line))
                except ValueError as e:
                    # fail-fast: 中途坏行静默截断会让 DM 配对样本无声缩水 (审计 bug #3)
                    raise ValueError(
                        f"baseline_points_{symbol}.jsonl 第 {line_no} 行 JSON 损坏: {e} "
                        "— DM 对照序列禁止静默部分加载, 请修复文件后重跑") from e
    return points


def build_summary(s, cand, *, baseline_points=None, baseline_dir_acc=None, batch_id=None):
    """Build complete verdict summary with DM test and adaptive gate."""
    m = map_summary(s)
    stage = cand.get("stage", DEFAULT_STAGE)
    variant = "{}_{}_{}_p{}".format(
        cand["symbol"], cand["cov_override"], stage, cand.get("max_points", 6)
    )
    gate_pass = gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52,
                     baseline_dir_acc=baseline_dir_acc)
    gm = s.pop("gated_metrics", None)
    if gm is not None:
        # gated 协变量: 硬门挂 active 口径 (plan 步骤三 n 门挂 n_active>=350);
        # gate() 本体语义零改动, 仅换输入为 active 统计. NaN → fail-closed.
        #
        # n_eff 口径显式声明 (评审 2026-09-18 MEDIUM-2, 行为不变):
        # 硬门 n_eff = min(全量 Bartlett ESS, n_active) — 启发式意图: ESS 上限不超过
        # active 样本数. 已知风险: gated 激活样本时间成簇 (门控事件驱动), 激活段内
        # 自相关可能高于全量序列, 全量 Bartlett ESS 或高估 active 子集真实 ESS → 门偏松.
        # 候选修正 fallback_n_eff(n_active) (active 子集独立重算 ESS) 待宿主裁定口径,
        # 登记于 docs/2026-09-18-oi-gated-momentum-spec.md §7 开放问题 #4.
        _n_active = gm.get("n_active", 0)
        gate_pass = gate(
            {"n": _n_active, "n_eff": min(m["n_eff"], _n_active),
             "dir_acc": gm.get("active_dir_acc")},
            min_n=350, min_n_eff=50, min_dir_acc=0.52,
            baseline_dir_acc=baseline_dir_acc)
    if stage == "diagnostic":
        gate_pass = False
    p_value = None
    if (baseline_points is not None and
        pair_dir_ok_series is not None and
        diebold_mariano_p is not None):
        point_dir_ok_list = s.get("point_dir_ok_list") or []  # 键存在但值为 None 时也回退 (审计 bug #4)
        if len(point_dir_ok_list) >= 100 and len(baseline_points) >= 100:
            try:
                v_series, b_series = pair_dir_ok_series(point_dir_ok_list, baseline_points)
                if len(v_series) >= 100:
                    p_value = diebold_mariano_p(v_series, b_series)
            except Exception as e:
                print(f"[WARN] DM test failed: {e}", file=sys.stderr)
    cov_family = "unknown"
    if resolve_cov_family is not None:
        try:
            cov_family = resolve_cov_family(cand)
        except Exception as e:
            print(f"[WARN] resolve_cov_family failed: {e}", file=sys.stderr)
    s.pop("point_dir_ok_list", None)
    out = {
        "schema": "fm.aligned_verdict.v2",
        "status": "ok",
        "usage_unknown": False,
        "stage": stage,
        "variant_name": variant,
        "symbol": cand["symbol"],
        "cov_override": cand["cov_override"],
        "cov_family": cov_family,
        "batch_id": batch_id,
        "n": m["n"],
        "n_eff": m["n_eff"],
        "dir_acc": m["dir_acc"],
        "endpoint_mape": m["endpoint_mape"],
        "endpoint_bias_pct": m["endpoint_bias_pct"],
        "path_corr": m["path_corr"],
        "weighted_dir_acc": m["weighted_dir_acc"],
        "mae": m["mae"],
        "mape": m["mape"],
        "decay": m["decay"],
        "gate_pass": gate_pass,
        "p_value": p_value,
        "fdr_pass": None,
        "migrated_pass": None,
        "metrics": {
            "n": m["n"],
            "n_eff": m["n_eff"],
            "dir_acc": m["dir_acc"],
            "endpoint_mape": m["endpoint_mape"],
            "endpoint_bias_pct": m["endpoint_bias_pct"],
            "path_corr": m["path_corr"],
            "weighted_dir_acc": m["weighted_dir_acc"],
            "mae": m["mae"],
            "mape": m["mape"],
            "decay": m["decay"],
            "gate_pass": gate_pass,
        },
    }
    if gm is not None:
        _active_fields = {
            "gate_basis": "active",
            "active_dir_acc": gm.get("active_dir_acc"),
            "n_active": gm.get("n_active", 0),
            "n_total": gm.get("n_total", 0),
            "n_zero": gm.get("n_zero", 0),
            "n_nan": gm.get("n_nan", 0),
        }
        out.update(_active_fields)
        out["metrics"].update(_active_fields)
    elif _GATED_POOL_LOAD_FAILED:
        # 评审 MEDIUM-1: pool 加载失败的 run 内, 全量口径 verdict 误分类可见化 —
        # 本 verdict 走的全量口径不可信 (gated 声明未能加载, 无法按候选识别)
        out["gate_basis"] = "full_fallback"
        out["metrics"]["gate_basis"] = "full_fallback"
    return out


def map_summary(s):
    """monthly_backtest.summarize 输出 → PRAXIST 指标命名 (v23)"""
    def _f(val, default=None):
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _i(val, default=0):
        # 整数字段防护与浮点字段 _f 一致: 非法值回退默认, 不让 ValueError 上抛 (审计 bug #5)
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    return {
        "n": _i(s.get("n"), 0),
        "n_eff": _i(s.get("n_eff"), _i(s.get("n"), 0)),
        "dir_acc": _f(s.get("dir_acc", s.get("DirAcc")), 0.5),
        "endpoint_mape": _f(s.get("endpoint_mape"), 0.0),
        "endpoint_bias_pct": _f(s.get("endpoint_bias_pct"), 0.0),
        "path_corr": _f(s.get("path_corr")),
        "weighted_dir_acc": _f(s.get("weighted_dir_acc", s.get("dir_acc")), 0.5),
        "mae": _f(s.get("mae"), 0.0),
        "mape": _f(s.get("mape"), 0.0),
        "decay": _f(s.get("decay"), 1.0),
    }


def gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52, baseline_dir_acc=None):
    """Hard gate for variant promotion."""
    n = s.get("n")
    n_eff = s.get("n_eff")
    dir_acc = s.get("dir_acc", s.get("DirAcc"))
    if n is None or n_eff is None or dir_acc is None:
        return False
    # 非有限值 (NaN/inf) 统一 fail-closed (审计 bug #1/#2):
    # NaN 比较恒 False 会让 n=NaN 绕过硬门 fail-open, dir_acc=inf 数学上无意义
    if not (math.isfinite(n) and math.isfinite(n_eff) and math.isfinite(dir_acc)):
        return False
    if n < min_n or n_eff < min_n_eff:
        return False
    if baseline_dir_acc is not None:
        effective_min = max(0.50, min(min_dir_acc, baseline_dir_acc))
    else:
        effective_min = min_dir_acc
    return dir_acc >= effective_min


def effective_sample_size(nominal_n, horizon, step, residual_autocorr=None):
    """Bartlett full-kernel effective sample size for overlapping windows."""
    if step <= 0:
        # 非法参数显式抛 ValueError, 不再以 ZeroDivisionError 崩溃 (审计 bug #7)
        raise ValueError(f"step 必须为正, got step={step}")
    if step >= horizon:
        return nominal_n
    if residual_autocorr is None:
        residual_autocorr = 0.9
    max_overlap_step = (horizon - 1) // step
    kernel_sum = 0.0
    for k in range(1, max_overlap_step + 1):
        weight = 1.0 - (k / (max_overlap_step + 1))
        kernel_sum += weight * (residual_autocorr ** k)
    variance_inflation_factor = 1.0 + 2.0 * kernel_sum
    n_eff = nominal_n / variance_inflation_factor
    return max(1, int(n_eff))
