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
import hashlib
from typing import Optional

import numpy as np

# evaluator.py 位于 <FM_ROOT>/task_FM/evaluations/fm_eval/，上溯 3 级到 FM_ROOT
FM_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir))

# 导入统计检验模块
sys.path.insert(0, os.path.join(FM_ROOT, "cascade"))
try:
    from statistical_tests import (
        detection_threshold_vs_random, detection_threshold_vs_baseline, n_required,
        pair_dir_ok_series, diebold_mariano_p,
        pair_dir_ok_series_with_diagnostics,
        paired_delta_se, shrink_delta_post, compute_hac_se,
    )
    from cov_family import resolve_cov_family
except ImportError as e:
    print(f"[WARN] 统计检验模块加载失败: {e}", file=sys.stderr)
    pair_dir_ok_series = None
    diebold_mariano_p = None
    pair_dir_ok_series_with_diagnostics = None
    resolve_cov_family = None
    paired_delta_se = None
    shrink_delta_post = None
    compute_hac_se = None

# §1.4 双运行模式：导入 RUN_LABEL_EXPLORATION
sys.path.insert(0, FM_ROOT)
try:
    from scripts.registry_lib import RUN_LABEL_EXPLORATION
except ImportError as e:
    print(f"[WARN] RUN_LABEL_EXPLORATION 加载失败: {e}", file=sys.stderr)
    RUN_LABEL_EXPLORATION = "exploratory_unconfirmed"  # fallback

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

# N5: 权重指纹缓存哨兵 —— 区分「尚未计算」与「计算结果为 None」
_NOT_COMPUTED = object()

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


_GOAL_YAML_PATH = os.path.join(FM_ROOT, "scripts", "praxist_goal.yaml")


def _load_allowed_symbols(path=None):
    """候选准入门 = praxist_goal.yaml 的 goal.cadence.target_symbols（唯一来源）。

    2026-10-08：此前此处是一份独立硬编码，且内容恰好等于 config/prediction_scheme.py
    的 SCHEMES（21 个，信用档表），而非攻坚目标（24 个）。后果是双向割裂：
      - 只在目标里的 oi/px/y 任何候选都在第一道 validate_candidate 检查被拒，
        即 goal 要求它们达标、却无法为它们产生任何候选；
      - 只在准入门里的 jm 能过门、但不被 goal 统计（孤儿）。
    两套集合归一后，本函数与 praxist_supervisor._load_goal_symbols 读同一字段。
    缺失即抛错（fail loud）：静默回退到任何内置副本都会让割裂重新出现。
    """
    import yaml  # 局部导入：仅本函数需要，不给 evaluator 其余部分增加依赖
    p = path or _GOAL_YAML_PATH
    with open(p, encoding="utf-8") as f:
        goal = (yaml.safe_load(f) or {}).get("goal") or {}
    raw = ((goal.get("cadence") or {}).get("target_symbols")) or []
    syms = frozenset(str(s).strip().lower() for s in raw if str(s).strip())
    if not syms:
        raise ValueError(
            "目标品种集契约缺失：%s 的 goal.cadence.target_symbols 为空。"
            "候选准入门不得回退内置副本。" % p)
    return syms


ALLOWED_SYMBOLS = _load_allowed_symbols()

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


def load_baseline_points(symbol, root=None, cov=None):
    """Load baseline points from JSONL file.

    cov=None -> 无协变量基线（E7）。
    """
    if root is None:
        root = os.path.join(FM_ROOT, "task_FM", "config")
    from cascade.baseline_paths import baseline_filename
    _fname = baseline_filename(symbol, cov)
    path = os.path.join(root, _fname)
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
                        f"{_fname} 第 {line_no} 行 JSON 损坏: {e} "
                        "— DM 对照序列禁止静默部分加载, 请修复文件后重跑") from e
    return points



# v3: 补 spec 七组件表缺失项（CONTEXT_BARS / CONTEXT_DAYS / 复权+换月规则版本）
#     与 Phase 3 合并重生（H1）；H6 约束：复权/换月规则版本只记录，不得改变值
# v4（2026-09-30 收口 2.3 / 发现 B）：评估窗口锚语义入指纹 —— v3 及之前窗口随
#     运行时数据末端滑动，resume 会把不同窗口的点拼进同一 verdict；v4 起窗口 =
#     锚的纯函数，锚逐行持久化于 checkpoint（eval_end_ts）。锚语义变则不可比。
PROTOCOL_FINGERPRINT_VERSION = "protocol_v4"
WINDOW_ANCHOR_VERSION = "eval_end_persisted_v1"
COV_MATRIX_HASH_VERSION = "cov_matrix_hash_v1"
COV_FILL_VERSION = "v2"      # 唯一来源（D4 语义变更）
# H6：以下两值只记录、不改变。改变则所有现存 research_family 分裂。
ADJUSTMENT_RULE_VERSION = "v1"    # 复权规则版本
ROLL_GUARD_VERSION = "v1"         # 换月守卫版本


def compute_protocol_fingerprint(metric_version="v1",
                                 cov_fill_version=COV_FILL_VERSION,
                                 eval_window_bars=None, step=None, horizon=None,
                                 cutoff_convention="bar_close",
                                 context_bars=None, context_days=None,
                                 adjustment_rule_version=ADJUSTMENT_RULE_VERSION,
                                 roll_guard_version=ROLL_GUARD_VERSION,
                                 window_anchor=WINDOW_ANCHOR_VERSION):
    """协议指纹：决定两次评估是否可比（W1.5）。

    v2 变更: 加入 cutoff_convention 参数（D5 修复后默认为 bar_close）。
    v3 变更（PR-A5 / spec 七组件表补齐）：
      - context_bars / context_days（变则不可比）
      - adjustment_rule_version / roll_guard_version（H6：只记录不改变）
    v4 变更（2026-09-30 收口 2.3 / 发现 B）：
      - window_anchor：评估窗口锚语义。v3 及之前窗口随运行时数据末端滑动；
        v4 起窗口 = 锚的纯函数，锚逐行持久化于 checkpoint（eval_end_ts）。
    """
    from config import backtest_config
    ctx_bars = context_bars if context_bars is not None else backtest_config.CONTEXT_BARS
    ctx_days = context_days if context_days is not None else backtest_config.CONTEXT_DAYS
    parts = [
        PROTOCOL_FINGERPRINT_VERSION,
        f"metric={metric_version}",
        f"cov_fill={cov_fill_version}",
        f"window={eval_window_bars if eval_window_bars is not None else backtest_config.EVAL_WINDOW_BARS}",
        f"step={step if step is not None else backtest_config.STEP}",
        f"horizon={horizon if horizon is not None else backtest_config.HORIZON}",
        f"cutoff={cutoff_convention}",
        f"context_bars={ctx_bars}",
        f"context_days={ctx_days}",
        f"adj_rule={adjustment_rule_version}",
        f"roll_guard={roll_guard_version}",
        f"anchor={window_anchor}",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def compute_sample_fingerprint(points):
    """样本指纹：本次评估实际用到的 cutoff 集合。"""
    cutoffs = sorted(str(p.get("cutoff")) for p in (points or [])
                     if isinstance(p, dict) and p.get("cutoff") is not None)
    return hashlib.sha256("|".join(cutoffs).encode("utf-8")).hexdigest()


def compute_cov_fingerprint(matrix, keys):
    """协变量输入矩阵的规范哈希（C2 / W2.1）。"""
    import numpy as _np
    arr = _np.asarray(matrix, dtype="<f4")
    if not _np.all(_np.isfinite(arr)):
        raise ValueError("cov matrix contains Inf/NaN payload")
    arr = _np.where(arr == 0.0, 0.0, arr)
    blob = b"|".join([COV_MATRIX_HASH_VERSION.encode()]
                     + [str(k).encode("utf-8") for k in keys]
                     + [arr.tobytes(order="C")])
    return {"keys": list(keys),
            "matrix_sha256": hashlib.sha256(blob).hexdigest(),
            "n_channels": len(list(keys)),
            "hash_version": COV_MATRIX_HASH_VERSION}


def _compute_context_hash(points) -> Optional[str]:
    """汇总 context 窗口内容哈希（PR-C4 W6.7 历史修订防护）。

    逐点摘要在**回测写入点**由 `monthly_backtest` 就地计算
    （480 根 1H 收盘序列的 SHA-256 前 16 位），本函数只做逐点摘要的汇总。

    为什么不就地算：verdict 侧拿不到 context 窗口原文 —— checkpoint 逐点只存
    `real_end`（**未来真值**）。曾有一版 fallback 用 `real_endpoint` 兜底，
    那是把未来信息混入历史修订判据，且生产点根本没有该键，导致哈希恒为 None、
    W6.7 防护全程惰性。现改为：拿不到摘要就诚实返回 None（未知），
    不拿别的量冒充。

    Args:
        points: 预测点列表

    Returns:
        汇总哈希前 16 位；无任何点带摘要时返回 None
    """
    if not points:
        return None

    digests = []
    n_dict = 0
    for p in points:
        if isinstance(p, dict):
            n_dict += 1
            ch = p.get("context_hash")
            if ch:
                digests.append(str(ch))

    # 覆盖不全时返回 None（未知），**不**返回一个只覆盖子集的哈希。
    # 跨本字段引入点的 `--resume` 必然产生「部分点有摘要」的混合 verdict；
    # 此时给出一个看似正常的 16 位哈希，读者无从知道它只覆盖了一部分
    # —— 那是把「不完整」伪装成「完整」，正是 fail-visible 要防的。
    if len(digests) != n_dict:
        return None

    # 按摘要排序后汇总，保证点序不同不影响结果
    digests.sort()
    return hashlib.sha256("|".join(digests).encode("utf-8")).hexdigest()[:16]


# ── N5 修复：权重指纹 (PR-B1 接线) ─────────────────────────────────
# 缓存模块级结果，避免每个 verdict 重复扫描+哈希大文件
_WEIGHT_FINGERPRINT_CACHE = {"value": _NOT_COMPUTED}


def _compute_weight_fingerprint_safe():
    """计算 TimesFM 基础模型权重指纹。

    路径来源：data.config.get_timesfm_model_path()，解析顺序为
    环境变量 FM_TIMESFM_MODEL_PATH / TIMESFM_MODEL_PATH / TIMESFM_WEIGHTS_DIR
    → 本地 models/timesfm-3.0-pytorch/ → HF hub id。

    区分两种 None：
    - 路径是 HF hub id（非本地目录）→ 无法哈希，返回 None + WARN
    - 路径是本地目录但无模型文件 → compute_weight_fingerprint 抛 FileNotFoundError，
      捕获后返回 None + WARN
    - 计算成功 → 返回 dict {"weights_sha256": "...", "n_files": N, "hash_version": "v1"}

    结果缓存在模块级 _WEIGHT_FINGERPRINT_CACHE，同进程内只算一次。
    """
    if _WEIGHT_FINGERPRINT_CACHE["value"] is not _NOT_COMPUTED:
        return _WEIGHT_FINGERPRINT_CACHE["value"]

    try:
        from data.config import get_timesfm_model_path
        from scripts.fingerprint_lib import compute_weight_fingerprint
    except ImportError as e:
        print(f"[WARN] weight_fingerprint: 依赖导入失败 ({e})，落 None", file=sys.stderr)
        _WEIGHT_FINGERPRINT_CACHE["value"] = None
        return None

    model_path = get_timesfm_model_path()

    # get_timesfm_model_path 可能返回 HF hub id（如 "google/timesfm-3.0-pytorch"），
    # 那不是本地路径，无法哈希
    if not os.path.isdir(model_path):
        print(f"[WARN] weight_fingerprint: 模型路径不是本地目录 ({model_path})，"
              f"无法计算权重指纹，落 None", file=sys.stderr)
        _WEIGHT_FINGERPRINT_CACHE["value"] = None
        return None

    try:
        fp = compute_weight_fingerprint(model_path)
        _WEIGHT_FINGERPRINT_CACHE["value"] = fp
        return fp
    except (FileNotFoundError, OSError) as e:
        print(f"[WARN] weight_fingerprint: 计算失败 ({e})，落 None", file=sys.stderr)
        _WEIGHT_FINGERPRINT_CACHE["value"] = None
        return None


def build_summary(s, cand, *, baseline_points=None, baseline_dir_acc=None, batch_id=None, run_mode="exploration", points=None, cov_matrix=None, cov_keys=None):
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
    # ── E6/W1.5: DM 显式状态机 ──
    # PR-A1 前 dm_status 会频繁落 insufficient_common/no_common_cutoff——
    # 这是 fail-loud 设计行为, 运维侧禁止过滤该 WARN.
    p_value = None
    dm_diag = {"dm_status": "no_baseline", "dm_common_count": 0,
               "dm_unmatched_variant": 0, "dm_unmatched_baseline": 0,
               "pair_set_hash": None, "raw_cutoff_set_hash": None,
               "pairing_valid": False, "missingness_admissible": False,
               "d_series_n_eff": None, "d_bar_le_zero": None,
               "n_avail_variant": 0, "n_avail_baseline": 0}
    if (baseline_points is not None and
            pair_dir_ok_series_with_diagnostics is not None):
        point_dir_ok_list = s.get("point_dir_ok_list") or []  # 键存在但值为 None 时也回退 (审计 bug #4)
        try:
            _base_proto = next(
                (p.get("protocol_fingerprint") for p in baseline_points
                 if isinstance(p, dict) and p.get("protocol_fingerprint")), None)
            dm_diag = pair_dir_ok_series_with_diagnostics(
                point_dir_ok_list, baseline_points,
                variant_protocol=compute_protocol_fingerprint(),
                baseline_protocol=_base_proto)
            v_series, b_series = dm_diag["variant_series"], dm_diag["baseline_series"]
            if (dm_diag["dm_status"] not in ("protocol_mismatch", "no_baseline")
                    and len(v_series) >= 100 and diebold_mariano_p is not None):
                p_value = diebold_mariano_p(v_series, b_series)
        except Exception as e:
            print(f"[WARN] DM test failed: {e}", file=sys.stderr)
    if dm_diag["dm_status"] in ("insufficient_common", "no_common_cutoff",
                                "protocol_mismatch"):
        print(f"[WARN] dm_status={dm_diag['dm_status']} "
              f"common={dm_diag['dm_common_count']} — DM 不可用于确认",
              file=sys.stderr)
    cov_family = "unknown"
    if resolve_cov_family is not None:
        try:
            cov_family = resolve_cov_family(cand)
        except Exception as e:
            print(f"[WARN] resolve_cov_family failed: {e}", file=sys.stderr)
    s.pop("point_dir_ok_list", None)
    # ── 2.5 (spec 2026-10-05 §5/§6.3): 缩水增量 δ_post 与 se 落账 ──
    # d_t = 变体对该变体的配对差序列（v_series − b_series，与 DM 同一家）；
    # se = sqrt(compute_hac_se(d_t)/T)。se 不可算（无配对序列 / T<2 /
    # 长程方差非有限正）→ se 与 delta_post_shrunk 均落 None，不参与 6.6 条件 1
    # 的树内比较与 6.5 条件 3 的上界比较。
    # 口径说明：生产诊断的 missingness_admissible 保守默认 False，dm_status
    # 落 set_mismatch_descriptive（实测 169/376）；se 是配对差序列的统计属性，
    # 与 missingness 可采纳性正交，故按 §5 由序列本身判定可算性，不额外用
    # dm_status ∈ {ok, set_mismatch_ok} 收窄——否则生产恒 None，2.4 dominated
    # 与 2.7 晋升永久休眠。协议不匹配/无共同 cutoff 时序列为空 → None。
    _d_t = None
    _vs = dm_diag.get("variant_series")
    _bs = dm_diag.get("baseline_series")
    if _vs and _bs and len(_vs) == len(_bs):
        _d_t = [a - b for a, b in zip(_vs, _bs)]
    _se = (paired_delta_se(_d_t)
           if (paired_delta_se is not None and _d_t is not None) else None)
    _delta_post_shrunk = None
    if _se is not None and baseline_dir_acc is not None and shrink_delta_post is not None:
        _delta_post_shrunk = shrink_delta_post(
            m["dir_acc"] - baseline_dir_acc, _se)
    _search_var_lr = None
    if _se is not None and compute_hac_se is not None and _d_t is not None:
        try:
            _var = float(compute_hac_se(_d_t))
        except (TypeError, ValueError):
            _var = None
        if _var is not None and _var > 0 and _var == _var and _var != float("inf"):
            _search_var_lr = _var
    effective_min = compute_effective_min(0.52, baseline_dir_acc)
    out = {
        "schema": "fm.aligned_verdict.v2",
        "status": "ok",
        "run_mode": run_mode,
        "run_label": RUN_LABEL_EXPLORATION if run_mode == "exploration" else None,
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
        "dir_acc_full": m["dir_acc_full"],
        "dir_acc_ex_roll": m["dir_acc_ex_roll"],
        "n_roll_excluded": m["n_roll_excluded"],
        "n_roll_ratio": m["n_roll_ratio"],
        "endpoint_mape": m["endpoint_mape"],
        "endpoint_bias_pct": m["endpoint_bias_pct"],
        "path_corr": m["path_corr"],
        "weighted_dir_acc": m["weighted_dir_acc"],
        "mae": m["mae"],
        "mape": m["mape"],
        "decay": m["decay"],
        "gate_pass": gate_pass,
        "baseline_dir_acc": baseline_dir_acc,
        "effective_min": effective_min,
        # 2.5 (spec 2026-10-05 §6.3): 缩水增量与配对差标准误。se 不可算时均 None。
        "se": _se,
        "delta_post_shrunk": _delta_post_shrunk,
        "search_var_lr": _search_var_lr,
        "p_value": p_value,
        "fdr_pass": None,
        "migrated_pass": None,
        "protocol_fingerprint": compute_protocol_fingerprint(),
        "sample_fingerprint": compute_sample_fingerprint(points or s.get("points")),
        "cov_fingerprint": (compute_cov_fingerprint(cov_matrix, cov_keys)
                            if cov_matrix is not None and cov_keys else None),
        # N5 修复 (PR-B1 接线)：权重指纹从 TimesFM 基础模型目录计算。
        # 路径来源：data.config.get_timesfm_model_path()（环境变量 → 本地 models/ → HF hub id）。
        # 若路径非本地目录或计算失败，_compute_weight_fingerprint_safe() 返回 None 并打 WARN ——
        # fail-visible，不静默吞错。
        "weight_fingerprint": _compute_weight_fingerprint_safe(),
        # N5: 种子指纹。当前系统无 per-verdict 随机种子 —— hourly_model.py 仅有硬编码
        # seed=42 用于消融（ablate_content_covariates），不随 verdict 变化。
        # 因此 seed_fingerprint 恒为 None 是**设计正确的**（无种子可指纹），不是 bug。
        # 若未来引入 per-verdict seed（如 ensemble 随机化），需在此处接线 compute_seed_fingerprint()。
        "seed_fingerprint": None,
        # M1: 保留 None(未知) 诚实暴露旧 checkpoint 缺该键；True/False 仅当全点有明确值

        "covariates_used": (None if s.get("covariates_used") is None
                                    else bool(s.get("covariates_used"))),
        # PR-B3: xreg_fallback 统计，缺失时报告 None（未知）而非 0（否认）
        "xreg_fallback_count": s.get("xreg_fallback_count"),
        "xreg_fallback_rate": s.get("xreg_fallback_rate"),
        # E6: DM 配对诊断 (variant_series/baseline_series 是中间产物, 不落 verdict)
        **{k: v for k, v in dm_diag.items()
           if k not in ("variant_series", "baseline_series")},
        # PR-C4 W6.6: 门槛一致性。**不写 gate_basis** —— 那个键的既有词表
        # （active / full_fallback）说的是「用哪个**总体口径**当门参照」，
        # 与 W6.6 的「**阈值参照**是否缺失」是两件事；混用一个键会让无基线的
        # 非 gated run 落 gate_basis="fallback_0.52"，被误读成 gated pool 加载失败。
        # 故独立成键：baseline=有基线，fallback_0.52=无基线（不参与跨品种比较与成功判定）。
        # v4 收口 2.6（发现 E）: 四分母顶层化 —— VERDICT_FIELDS 与 A1 校验都按
        # **顶层**取键；此前只落 metrics 子 dict，18/18 v3 行 a1_missing_fields
        # 恒报缺失（实测 metrics.n_dir_total 非空而顶层 None）。
        "n_dir_total": m.get("n_dir_total"),
        "n_dir_active": m.get("n_dir_active"),
        "n_zero_move": m.get("n_zero_move"),
        "n_zero_ratio": m.get("n_zero_ratio"),
        "threshold_basis": "baseline" if baseline_dir_acc is not None else "fallback_0.52",
        # PR-C4 W6.7: 历史修订防护（context_hash）
        "context_hash": _compute_context_hash(points or s.get("points")),
        # W6.7 的比对发生在**重算路径**（拿历史 verdict 的 context_hash 比对），
        # 不在单次 build_summary 内。None = 「尚未比对」，不是「未修订」；
        # 恒写 False 会把未知伪装成已证否。
        "data_revised": None,
        # PR-C4 W6.8: 预训练污染登记（仅登记，不做诊断性检验）
        "pretrain_risk": {
            "status": "registered",
            "model_card_cutoffs": {
                "wikipedia_pageviews": "Nov 2023",
                "google_trends": "EoY 2022"
            },
            "eval_window": "2026-01 to 2026-09",
            "gap_years": 2,
            "gift_eval_pretrain_cutoff": "unlabeled"
        },
        "metrics": {
            "n": m["n"],
            "n_eff": m["n_eff"],
            "dir_acc": m["dir_acc"],
            "dir_acc_full": m["dir_acc_full"],
            "dir_acc_ex_roll": m["dir_acc_ex_roll"],
            # PR-B4 (spec W6.5) 主口径分母构成 —— 与 dir_acc 同进 verdict，
            # 否则读者无法判断这个分式剔掉了多少点。
            "n_dir_total": m.get("n_dir_total"),
            "n_dir_active": m.get("n_dir_active"),
            "n_zero_move": m.get("n_zero_move"),
            "n_zero_ratio": m.get("n_zero_ratio"),
            "n_roll_excluded": m["n_roll_excluded"],
            "n_roll_ratio": m["n_roll_ratio"],
            "endpoint_mape": m["endpoint_mape"],
            "endpoint_bias_pct": m["endpoint_bias_pct"],
            "path_corr": m["path_corr"],
            "weighted_dir_acc": m["weighted_dir_acc"],
            "mae": m["mae"],
            "mape": m["mape"],
            "decay": m["decay"],
            "gate_pass": gate_pass,
            "baseline_dir_acc": baseline_dir_acc,
            "effective_min": effective_min,
            # M1: 保留 None(未知) 诚实暴露旧 checkpoint 缺该键；True/False 仅当全点有明确值

            "covariates_used": (None if s.get("covariates_used") is None

                                        else bool(s.get("covariates_used"))),
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
        "dir_acc_full": _f(s.get("dir_acc_full", s.get("dir_acc")), 0.5),
        "dir_acc_ex_roll": _f(s.get("dir_acc_ex_roll", s.get("dir_acc")), 0.5),
        "n_roll_excluded": _i(s.get("n_roll_excluded"), 0),
        "n_roll_ratio": _f(s.get("n_roll_ratio"), 0.0),
        # PR-B4 (spec W6.5①) 主口径分母构成。**显式传 None 作默认值** ——
        # `_i` 的默认是 0，而旧裁决根本没有这些键，用 0 冒充「剔了 0 个点」
        # 是把「未知」伪装成「已知且为零」。与本项目 M1 字段同一原则。
        # 注：此映射是链条的一环，漏了它则 build_summary 侧取到恒 None
        # （审计 N1 的断链点就在此处）。
        "n_dir_total": _i(s.get("n_dir_total"), None),
        "n_dir_active": _i(s.get("n_dir_active"), None),
        "n_zero_move": _i(s.get("n_zero_move"), None),
        "n_zero_ratio": _f(s.get("n_zero_ratio")),
        "endpoint_mape": _f(s.get("endpoint_mape"), 0.0),
        "endpoint_bias_pct": _f(s.get("endpoint_bias_pct"), 0.0),
        "path_corr": _f(s.get("path_corr")),
        "weighted_dir_acc": _f(s.get("weighted_dir_acc", s.get("dir_acc")), 0.5),
        "mae": _f(s.get("mae"), 0.0),
        "mape": _f(s.get("mape"), 0.0),
        "decay": _f(s.get("decay"), 1.0),
    }


def compute_effective_min(min_dir_acc=0.52, baseline_dir_acc=None):
    if baseline_dir_acc is not None:
        return max(0.50, min(float(min_dir_acc), float(baseline_dir_acc)))
    return float(min_dir_acc)


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
    effective_min = compute_effective_min(min_dir_acc, baseline_dir_acc)
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
