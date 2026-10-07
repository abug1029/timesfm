"""Statistical tests for prediction quality evaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional, Union, Sequence
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo('Asia/Shanghai')

# spec §4.1 W1.2: 带宽参数唯一约定
# HORIZON = 24, STEP = 2 → h = HORIZON // STEP = 12, q = h - 1 = 11
HAC_MAX_LAG_Q = 11


def safe_normalize_cutoff(ts: Union[str, int, float, None]) -> Optional[int]:
    """Normalize cutoff timestamp to Unix seconds (Asia/Shanghai).

    Handles:
    - pd.Timestamp / datetime: naive->localize to Asia/Shanghai, aware->tz_convert
    - str: ISO format, or numeric string (unix seconds/ms, length>=9)
    - int/float: Unix seconds or milliseconds
    - numpy scalars
    - None -> None
    - Invalid -> None

    Spec 9.4: Use pd.Timestamp, naive->localize to Asia/Shanghai, aware->tz_convert.
    """
    if ts is None:
        return None

    # Handle numpy scalars (0-d arrays)
    if hasattr(ts, "ndim") and ts.ndim == 0:
        ts = ts.item()

    # Handle pd.Timestamp / datetime
    if isinstance(ts, (pd.Timestamp, datetime)):
        if pd.isna(ts):  # pd.NaT
            return None
        ts_pd = pd.Timestamp(ts)
        if ts_pd.tzinfo is None:
            # Naive -> localize to Asia/Shanghai
            ts_pd = ts_pd.tz_localize("Asia/Shanghai")
        else:
            # Aware -> convert to Asia/Shanghai
            ts_pd = ts_pd.tz_convert("Asia/Shanghai")
        return int(ts_pd.timestamp())

    # Handle numeric types
    if isinstance(ts, (int, float)):
        if ts > 1e11:  # milliseconds
            return int(ts / 1000)
        return int(ts)

    # Handle string
    if isinstance(ts, str):
        ts_stripped = ts.strip()

        # Reject all-digit strings that are too short to be unix timestamps
        # (e.g. "20240615" must NOT be parsed as a date by pd.Timestamp)
        if ts_stripped.isdigit() and len(ts_stripped) < 9:
            return None

        # Check if numeric string: isdigit and length >= 9
        if ts_stripped.isdigit():
            numeric = int(ts_stripped)
            if numeric > 1e11:  # milliseconds
                return numeric // 1000
            return numeric

        # Try float unix string (e.g. "1718413200.0")
        try:
            numeric = float(ts_stripped)
            if numeric > 1e11:  # milliseconds
                return int(numeric / 1000)
            elif len(ts_stripped) >= 9 and ts_stripped.replace(".", "", 1).isdigit():
                return int(numeric)
        except ValueError:
            pass

        # Try parsing as datetime via pd.Timestamp
        try:
            # Handle trailing Z (UTC indicator)
            ts_parse = ts_stripped
            if ts_parse.endswith("Z"):
                ts_parse = ts_parse[:-1] + "+00:00"

            ts_pd = pd.Timestamp(ts_parse)
            if ts_pd.tzinfo is None:
                ts_pd = ts_pd.tz_localize("Asia/Shanghai")
            else:
                ts_pd = ts_pd.tz_convert("Asia/Shanghai")
            return int(ts_pd.timestamp())
        except (ValueError, TypeError):
            return None

    return None



def pair_dir_ok_series(
    variant_points: Sequence,
    baseline_points: Sequence,
) -> tuple[list[int], list[int]]:
    """Pair dir_ok values by normalized cutoff (Inner Join, sorted by time).
    
    Args:
        variant_points: List of (cutoff, dir_ok) tuples or dicts with 'cutoff'/'dir_ok' keys
        baseline_points: Same format as variant_points
    
    Returns:
        (variant_dir_ok_list, baseline_dir_ok_list) - both aligned by common cutoffs, sorted ascending
    """
    def extract(point):
        if isinstance(point, dict):
            cutoff = point.get('cutoff')
            dir_ok = point.get('dir_ok')
            if cutoff is None or dir_ok is None:
                return None, None
            return cutoff, dir_ok
        else:
            if len(point) < 2:
                return None, None
            return point[0], point[1]
    
    # Build {normalized_ts: dir_ok} for both
    variant_map = {}
    for pt in variant_points:
        cutoff, dir_ok = extract(pt)
        if cutoff is None:
            continue
        ts = safe_normalize_cutoff(cutoff)
        if ts is not None:
            variant_map[ts] = int(dir_ok)
    
    baseline_map = {}
    for pt in baseline_points:
        cutoff, dir_ok = extract(pt)
        if cutoff is None:
            continue
        ts = safe_normalize_cutoff(cutoff)
        if ts is not None:
            baseline_map[ts] = int(dir_ok)
    
    # Inner join on common timestamps
    common_ts = sorted(variant_map.keys() & baseline_map.keys())
    
    variant_series = [variant_map[ts] for ts in common_ts]
    baseline_series = [baseline_map[ts] for ts in common_ts]
    
    return variant_series, baseline_series


from scipy.stats import t as student_t


def diebold_mariano_p(
    variant_dir_ok_list: Sequence[float],
    baseline_dir_ok_list: Sequence[float],
    horizon: int = None,
    step: int = None,
) -> float:
    """Diebold-Mariano test for predictive accuracy (one-sided).
    
    H0: variant is NOT better than baseline
    H1: variant IS better than baseline (higher dir_ok)
    
    Returns p-value in [0, 1].
    - p < alpha → reject H0, variant is significantly better
    - p >= alpha → fail to reject H0
    
    Implementation follows Harvey, Leybourne, Newbold (1997) and
    the project spec §4.2.2.
    """
    # Default values from backtest_config
    if horizon is None or step is None:
        from config import backtest_config
        if horizon is None:
            horizon = backtest_config.HORIZON
        if step is None:
            step = backtest_config.STEP
    
    v = np.asarray(variant_dir_ok_list, dtype=float).ravel()
    b = np.asarray(baseline_dir_ok_list, dtype=float).ravel()
    
    # Length check
    if len(v) != len(b) or len(v) < 100:
        return 1.0
    
    T = len(v)
    
    # Spec differential: d = v_ok - b_ok (larger is better)
    d = v - b
    d_bar = np.mean(d)
    
    # Variant worse or no difference → conservative return 1.0
    if d_bar <= 0:
        return 1.0
    
    # Lag order: q = max(1, horizon//step - 1)
    q = max(1, horizon // max(1, step) - 1)
    
    # Newey-West Bartlett HAC 长程方差 —— **复用 compute_hac_se**。
    # spec §4.1 W1.2：n_eff 与 DM 检验共用同一估计量，禁止另写一套。
    sigma_lr_sq = compute_hac_se(d, q=q)

    # 均值的方差（规格 §4.2.2 要求）
    V = sigma_lr_sq / T
    if V <= 1e-12:
        return 1.0
    
    # DM statistic
    dm_stat = d_bar / np.sqrt(V)
    
    # HLN adjustment factor (Harvey, Leybourne, Newbold 1997)
    h = horizon // max(1, step)
    k_hln = np.sqrt(max(1e-6, (T + 1 - 2*h + h*(h-1)/T) / T))  # max 防护
    dm_adj = dm_stat * k_hln
    
    # One-sided p-value (right-tail, since d_bar > 0 and larger is better)
    p_value = student_t.sf(dm_adj, df=T - 1)
    
    # Clamp to [0, 1]
    return float(np.clip(p_value, 0.0, 1.0))

def bh_fdr_promote(
    verdicts: Sequence[dict],
    fdr_q: float = 0.10,
    min_batch_size: int = 4,
    bonferroni_alpha: float = 0.025,
) -> dict[str, dict]:
    """Per-symbol BH-FDR correction for variant promotion.

    Args:
        verdicts: List of dicts with keys: variant_id, symbol, p_value, gate_pass
        fdr_q: FDR q-value (default 0.10)
        min_batch_size: Minimum batch size for BH; below uses Bonferroni (default 4)
        bonferroni_alpha: Bonferroni alpha threshold (default 0.025)

    Returns:
        Dict mapping variant_id -> {"fdr_pass": bool}
        - gate_pass=False -> fdr_pass=False (never passes)
        - K < min_batch_size -> Bonferroni correction
        - K >= min_batch_size -> BH-FDR correction
        - Duplicate variant_id: last write wins
    """
    if not verdicts:
        return {}

    # Group by symbol
    by_symbol: dict[str, list[dict]] = {}
    for v in verdicts:
        symbol = v.get("symbol", "unknown")
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(v)

    all_updates: dict[str, dict] = {}

    for symbol, group in by_symbol.items():
        # Deduplicate by variant_id (last write wins)
        seen: dict[str, dict] = {}
        for v in group:
            vid = v.get("variant_id")
            if vid is not None:
                seen[vid] = v
        deduped = list(seen.values())

        K = len(deduped)
        if K == 0:
            continue

        # Sort by (safe_p, variant_id) for deterministic ordering
        def safe_p(v):
            """Return p_value, but 1.0 if gate_pass=False (spec 4.2.3)."""
            if not v.get("gate_pass", False):
                return 1.0  # gate_fail variants sort to end
            p = v.get("p_value")
            return 1.0 if p is None else float(p)

        sorted_group = sorted(deduped, key=lambda v: (safe_p(v), v.get("variant_id", "")))

        # Determine threshold
        if K < min_batch_size:
            # Bonferroni correction
            threshold = bonferroni_alpha
            for v in sorted_group:
                vid = v.get("variant_id")
                gate_pass = v.get("gate_pass", False)
                p = safe_p(v)
                fdr_pass = gate_pass and (p <= threshold)
                all_updates[vid] = {"fdr_pass": fdr_pass}
        else:
            # BH-FDR correction
            # Find largest k such that p_(k) <= k/K * q
            thresholds = [(i + 1) / K * fdr_q for i in range(K)]
            max_pass_idx = -1
            for i, v in enumerate(sorted_group):
                p = safe_p(v)
                if p <= thresholds[i]:
                    max_pass_idx = i

            for i, v in enumerate(sorted_group):
                vid = v.get("variant_id")
                gate_pass = v.get("gate_pass", False)
                fdr_pass = gate_pass and (i <= max_pass_idx)
                all_updates[vid] = {"fdr_pass": fdr_pass}

    return all_updates

def pair_dir_ok_series_with_diagnostics(
    variant_points, baseline_points, *, dm_min_common: int = 50,
    effective_min_n: int = 50, missingness_admissible=None,
    variant_protocol=None, baseline_protocol=None,
):
    """共同 cutoff 配对 + 显式诊断（E6 / W1.5）。

    状态判定优先级（首个匹配者胜）：
      no_baseline -> protocol_mismatch -> no_common_cutoff -> insufficient_common
      -> set_mismatch_descriptive -> set_mismatch_ok -> ok
    """
    import hashlib

    def _norm(pts):
        m = {}
        for p in (pts or []):
            if isinstance(p, dict):
                ts = safe_normalize_cutoff(p.get("cutoff"))
                ok = p.get("dir_ok")
            elif isinstance(p, (tuple, list)) and len(p) >= 2:
                ts = safe_normalize_cutoff(p[0])
                ok = p[1]
            else:
                continue
            if ts is not None:
                m[ts] = bool(ok)
        return m

    if missingness_admissible is None:
        missingness_admissible = False

    vm, bm = _norm(variant_points), _norm(baseline_points)

    def _base(**over):
        out = {"dm_common_count": 0, "dm_unmatched_variant": 0,
               "dm_unmatched_baseline": 0, "pair_set_hash": None,
               "raw_cutoff_set_hash": None, "pairing_valid": False,
               "missingness_admissible": bool(missingness_admissible),
               "admissibility_rule": None,
               "d_series_n_eff": None, "d_bar_le_zero": None,
               "n_avail_variant": len(vm), "n_avail_baseline": len(bm),
               "variant_series": [], "baseline_series": []}
        out.update(over)
        return out

    if baseline_points is None:
        return _base(dm_status="no_baseline")

    if variant_protocol is not None and baseline_protocol is not None:
        if variant_protocol != baseline_protocol:
            return _base(dm_status="protocol_mismatch")

    common = sorted(vm.keys() & bm.keys())
    raw_hash = hashlib.sha256(
        "|".join(str(k) for k in sorted(vm.keys() | bm.keys())).encode()
    ).hexdigest()

    if not common:
        return _base(dm_status="no_common_cutoff", raw_cutoff_set_hash=raw_hash)

    pair_hash = hashlib.sha256("|".join(str(k) for k in common).encode()).hexdigest()
    v_series = [float(vm[k]) for k in common]
    b_series = [float(bm[k]) for k in common]
    counts = {"dm_common_count": len(common),
              "dm_unmatched_variant": len(vm.keys() - bm.keys()),
              "dm_unmatched_baseline": len(bm.keys() - vm.keys()),
              "pair_set_hash": pair_hash, "raw_cutoff_set_hash": raw_hash,
              "variant_series": v_series, "baseline_series": b_series}

    if len(common) < dm_min_common:
        return _base(dm_status="insufficient_common", **counts)

    import numpy as _np
    d = _np.asarray(v_series) - _np.asarray(b_series)
    counts["d_bar_le_zero"] = bool(d.mean() <= 0)
    counts["d_series_n_eff"] = int(len(d))
    if counts["d_series_n_eff"] < effective_min_n:
        return _base(dm_status="insufficient_common", **counts)

    if not missingness_admissible:
        return _base(dm_status="set_mismatch_descriptive", **counts)

    # ── 步③ B 边缘连续块 + 有界性检查（2026-10-07 裁定）──
    # 裁定 B：missingness_admissible=True 时，还需检查「变体侧最新连续块 /
    # 基线侧最旧连续块」+ 有界性双条件「每侧 ≤30 日期」，任一不满足落回
    # descriptive。
    #
    # 连续性：unmatched variant 必须是变体侧最新连续块（尾部），unmatched
    # baseline 必须是基线侧最旧连续块（头部）。窗内散点/中间缺失/交错缺失
    # → descriptive。
    #
    # 有界性：unmatched 计数是点数，每天约 3 点（STEP=2 bars = 2h，一天
    # 交易时段约 5.5h ≈ 3 点）。每侧 ≤30 日期 = ≤90 点。
    only_variant = sorted(vm.keys() - bm.keys())
    only_baseline = sorted(bm.keys() - vm.keys())
    all_variant = sorted(vm.keys())
    all_baseline = sorted(bm.keys())
    
    # 变体侧：unmatched 必须是尾部连续块
    tail_ok = (only_variant == all_variant[-len(only_variant):]) if only_variant else True
    # 基线侧：unmatched 必须是头部连续块
    head_ok = (only_baseline == all_baseline[:len(only_baseline)]) if only_baseline else True
    
    if not (tail_ok and head_ok):
        return _base(dm_status="set_mismatch_descriptive", **counts)
    
    _POINTS_PER_DAY = 3
    _MAX_UNMATCHED_DAYS = 30
    unmatched_variant_days = counts["dm_unmatched_variant"] / _POINTS_PER_DAY
    unmatched_baseline_days = counts["dm_unmatched_baseline"] / _POINTS_PER_DAY
    if unmatched_variant_days > _MAX_UNMATCHED_DAYS or unmatched_baseline_days > _MAX_UNMATCHED_DAYS:
        return _base(dm_status="set_mismatch_descriptive", **counts)

    set_mismatch = bool(counts["dm_unmatched_variant"]
                        or counts["dm_unmatched_baseline"])
    # R2 采集包：unmatched 位置信息（日期列表）
    unmatched_variant_dates = [str(c) for c in only_variant]
    unmatched_baseline_dates = [str(c) for c in only_baseline]
    return _base(dm_status="set_mismatch_ok" if set_mismatch else "ok",
                 pairing_valid=True, admissibility_rule="edge_continuous_block_30d",
                 unmatched_variant_dates=unmatched_variant_dates,
                 unmatched_baseline_dates=unmatched_baseline_dates,
                 **counts)


def compute_hac_se(
    x: np.ndarray,
    q: int = HAC_MAX_LAG_Q,
) -> float:
    """Bartlett 核 HAC 长程方差估计（spec §4.1 W1.2 唯一家）。

    与 `measured_n_eff` **和** `diebold_mariano_p` 共用同一实现，禁止另写一套。
    （DM 直接调用本函数取 sigma_LR^2，再除以 T 得均值方差 V。）

    Args:
        x: 时间序列
        q: 最大滞后阶数（默认 11，spec W1.2 钦定）

    Returns:
        长程方差估计值（sigma_LR^2）

    spec 关键区分:
        - 这是 Bartlett 核 HAC 长程方差（线性权重 1 - l/(L+1)）
        - 名义 VIF = 8.0278 是**线性衰减假设的平方权重**，两者不是同一个量
        - 禁止声称「规划 VIF = DM 长程方差」
    """
    x = np.asarray(x, dtype=float).ravel()
    n = len(x)

    if n < 2:
        return 0.0

    # 滞后阶数不得超过 n-1，否则重叠切片为空。
    q = int(min(q, n - 1))

    x_centered = x - np.mean(x)

    # 自协方差序列（Newey-West 约定：分母统一用 n，核正半定）
    # spec §4.1 W1.2「与 DM 检验共用同一估计量」——diebold_mariano_p
    # 复用本函数，**禁止**在此另立分母约定。
    gamma = np.zeros(q + 1)
    for j in range(q + 1):
        gamma[j] = np.sum(x_centered[j:] * x_centered[: n - j]) / n

    # Bartlett 核权重（线性衰减 1 - j/(q+1)）
    weights = np.array([1.0 - j / (q + 1) for j in range(q + 1)])

    # 长程方差 = gamma_0 + 2 * sum_{j=1}^q w_j * gamma_j
    sigma_lr_sq = gamma[0] + 2.0 * np.sum(weights[1:] * gamma[1:])

    return float(sigma_lr_sq)


def compute_planning_vif(
    horizon: int = 24,
    step: int = 2,
) -> float:
    """名义方差膨胀因子 VIF（spec §4.1 W1.2，仅用于情景规划）。

    定义: VIF = 1 + 2 * Sum_{j=1..q} (1 - j/h)^2
    其中 h = horizon // step, q = h - 1

    spec 关键区分:
        - 这是**名义 VIF**，基于线性衰减假设的**平方权重**
        - 不等于 Bartlett HAC 长程方差（线性权重 1 - l/(L+1)）
        - 仅用于无先导数据时的量级情景
        - 禁止声称「规划 VIF = DM 长程方差」

    Args:
        horizon: 预测视野（默认 24）
        step: 步长（默认 2）

    Returns:
        名义 VIF 值（horizon=24, step=2 时应为 8.0278）
    """
    h = horizon // max(1, step)
    q = h - 1

    if q < 1:
        return 1.0

    # VIF = 1 + 2 * sum_{j=1}^q (1 - j/h)^2
    vif = 1.0
    for j in range(1, q + 1):
        vif += 2.0 * (1.0 - j / h) ** 2

    return float(vif)



# ──────────────────────────────────────────────────────────────
# PR-C1: 统计公式（spec §8.3）
# ──────────────────────────────────────────────────────────────

def detection_threshold_vs_random(n_eff: float, z_alpha: float = 1.645) -> float:
    """随机基线的检测门槛（spec §8.3, 行 695）。

    公式: 0.5 + z_alpha * 0.5 / sqrt(n_eff)

    含义: 在 H0: dir_acc = 0.5（随机）下，单侧 z 检验的拒绝域下界。
    只有 dir_acc 超过此门槛，才能在 alpha 水平上声称"优于随机"。

    Args:
        n_eff: 有效样本量（经 HAC 校正后）
        z_alpha: 单侧检验的 z 临界值（默认 1.645 = 5% 显著性）

    Returns:
        门槛值（dir_acc 标度，0.5~1.0）

    Docstring 四要素（spec 强制）:
        - 带宽约定: 无（此公式不依赖 HAC，n_eff 已是校正后）
        - 均值中心化: H0 均值 = 0.5
        - 样本方差分母: 二项分布 Var = 0.25/n_eff（理论值）
        - 有限样本修正: 无（大样本渐近）

    Golden example (spec 1369):
        >>> detection_threshold_vs_random(n_eff=73)
        0.596  # +/-1%
    """
    n_eff = float(n_eff)
    if not np.isfinite(n_eff) or n_eff <= 0:
        raise ValueError(f"n_eff must be a positive finite number, got {n_eff!r}")
    return 0.5 + z_alpha * 0.5 / np.sqrt(n_eff)


def detection_threshold_vs_baseline(
    d_bar: np.ndarray, z_alpha: float = 1.645,
) -> tuple[float, float]:
    """基线增量的检测门槛（spec §8.3, 行 696；2.10 补 /n，发现 I）。

    公式: threshold = z_alpha * SE_HAC(d_bar_mean) = z_alpha * sqrt(sigma_LR^2 / n)
          where d_t = v_ok_t - b_ok_t（逐点差），n = len(d)

    含义: 在 H0: mean(d) = 0（与基线无差异）下，单侧 z 检验的最小可检测增量。

    Args:
        d_bar: 逐点差序列 d_t = v_ok_t - b_ok_t（一维 array）
        z_alpha: 单侧检验的 z 临界值

    含义补充: SE 是**均值**的标准误（逐点长程方差再除以 n），与 DM 检验内部
    「再除以 T 得均值方差」同一约定（发现 I：此前漏除 n，门槛高估 ~sqrt(n) 倍）。

    Returns:
        (threshold, se_hac): 门槛值 + 均值 HAC 标准误

    Docstring 四要素:
        - 带宽约定: Newey-West 自动带宽（与 compute_hac_se 一致）
        - 均值中心化: H0: mean(d) = 0
        - 样本方差分母: HAC 长程方差 / n（均值标度）
        - 有限样本修正: 无

    Golden example (spec 1369):
        rho=0.5 AR(1)（sigma_LR^2 ~= 0.25 * 8.028 = 2.007）、n=588 时:
        threshold ~= 0.096  # +/-1%

    约束（spec 1368）:
        此函数 **不等于** baseline_dir_acc + 1.645*0.5/sqrt(n_eff)
        （后者是 vs_random 的变体，不是 vs_baseline）
    """
    # compute_hac_se 返回长程**方差** sigma_LR^2（同 diebold_mariano_p 的用法）。
    # SE(d_bar_mean) = sqrt(sigma_LR^2 / n)：均值标度（2.10 发现 I——此前漏除 n，
    # 黄金测试的稀疏构造 gamma_0=2/588 恰好把 /n 烘进方差，掩盖了缺失）。
    arr = np.asarray(d_bar, dtype=float).ravel()
    if arr.size < 2:
        raise ValueError(f"d_bar needs at least 2 points, got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("d_bar contains non-finite values")

    var_lr = compute_hac_se(arr)
    se_hac = float(np.sqrt(var_lr / arr.size)) if var_lr > 0 else 0.0
    threshold = z_alpha * se_hac
    return threshold, se_hac


def n_required(
    var_d: float,
    vif: float = 1.0,
    z_alpha: float = 1.645,
    z_beta: float = 0.842,
    delta: float = 0.10,
) -> int:
    """功效规划所需样本量（spec §8.3, 行 711）。

    公式: n = Var(d) * VIF * (z_alpha + z_beta)^2 / Delta^2

    含义: 在给定效应量 Delta、显著性 alpha、功效 1-beta 下，所需的最小样本量。

    Args:
        var_d: d_t 的方差（情景近似用 Var~=0.25，或先导估计）
        vif: 方差膨胀因子（默认 1.0 = 无自相关；实测 VIF 由 compute_planning_vif 给出）
        z_alpha: 单侧检验的 z 临界值（默认 1.645 = 5%）
        z_beta: 功效的 z 值（默认 0.842 = 80% 功效）
        delta: 目标效应量（默认 0.10 = Q1 裁定值）

    Returns:
        所需样本量（向上取整）

    Docstring 四要素:
        - 带宽约定: 无（VIF 已包含自相关信息）
        - 均值中心化: 不适用
        - 样本方差分母: Var(d) 可以是情景近似（0.25）或先导估计
        - 有限样本修正: 无

    约束（spec §8.3）:
        Var(d) * VIF（情景近似）与 Var_LR(d)（先导 HAC 估计）二选一，**禁止**同时使用。
        须写断言测试确保不存在混用路径。

    Golden examples (spec 1370):
        >>> n_required(var_d=0.25, vif=8.028, delta=0.02)
        31000  # +/-5%
        >>> n_required(var_d=0.25, vif=8.028, delta=0.10)
        1240   # +/-5%
    """
    delta = float(delta)
    var_d = float(var_d)
    vif = float(vif)
    if not np.isfinite(delta) or delta <= 0:
        raise ValueError(f"delta must be a positive finite number, got {delta!r}")
    if not np.isfinite(var_d) or var_d < 0:
        raise ValueError(f"var_d must be a non-negative finite number, got {var_d!r}")
    if not np.isfinite(vif) or vif <= 0:
        raise ValueError(f"vif must be a positive finite number, got {vif!r}")

    n = var_d * vif * (z_alpha + z_beta) ** 2 / delta ** 2
    return int(np.ceil(n))


# ── 正期望协变量搜索（spec 2026-10-05 §5/§6.3）─────────────────────
# τ=0.04 写死（§5/§8）：打开开关前定值，不用本族裁决估计，打开后不得改。
SHRINK_TAU_SD = 0.04


def paired_delta_se(d_t) -> Optional[float]:
    """配对差序列的标准误（spec 2026-10-05 §5）。

    se = sqrt(compute_hac_se(d_t) / T)，与 DM 同一家（同一 HAC 实现）。
    compute_hac_se 返回长程**方差**，此处再除以 T 开方得**均值**标准误。

    T < 2、序列含非有限值、或长程方差非有限正数 → None（§5 fail-closed，
    晋升与停止都失败关闭，不换一套标准误）。
    """
    if d_t is None:
        return None
    arr = np.asarray(d_t, dtype=float).ravel()
    T = int(arr.size)
    if T < 2:
        return None
    if not np.all(np.isfinite(arr)):
        return None
    var_lr = compute_hac_se(arr)
    if not np.isfinite(var_lr) or var_lr <= 0:
        return None
    return float(np.sqrt(var_lr / T))


def shrink_delta_post(delta, se, tau_sd: float = SHRINK_TAU_SD) -> Optional[float]:
    """缩水增量 δ_post（spec 2026-10-05 §6.3）。

    δ_post = δ × τ² / (τ² + se²)，τ=0.04（τ²=0.0016）。与 δ 同号、绝对值更小；
    不估计 τ。se 不可算（None / 非有限）或 δ 不可算 → None。
    """
    if delta is None or se is None:
        return None
    delta = float(delta)
    se = float(se)
    if not (np.isfinite(delta) and np.isfinite(se)):
        return None
    tau2 = float(tau_sd) ** 2
    return delta * tau2 / (tau2 + se * se)


def n_required_via_long_run(d_t, delta_post) -> Optional[int]:
    """功效规划**途径 B**（spec 2026-10-05 §6.3）。

    n_required(var_d=compute_hac_se(d_t), vif=1, z_alpha=1.645, z_beta=0.842,
               delta=δ_post)

    - var_d 用长程方差**本身**（compute_hac_se 返回值），**不**再乘规划 VIF；
      vif 恒 1（长程方差已含自相关）。T10：vif 与长程方差不同时进入同一次
      n_required —— 本函数只走 vif=1 单路径。
    - δ_post <= 0（或 None/非有限）→ 直接返回 None，不调用 n_required（不晋升）。
    - d_t 不可用（T<2/非有限）或长程方差非有限正 → None。
    """
    if delta_post is None:
        return None
    delta_post = float(delta_post)
    if not np.isfinite(delta_post) or delta_post <= 0:
        return None
    if d_t is None:
        return None
    arr = np.asarray(d_t, dtype=float).ravel()
    if arr.size < 2 or not np.all(np.isfinite(arr)):
        return None
    var_lr = compute_hac_se(arr)
    if not np.isfinite(var_lr) or var_lr <= 0:
        return None
    return n_required(var_d=var_lr, vif=1.0, z_alpha=1.645, z_beta=0.842,
                      delta=delta_post)
