"""Phase 1 (PR-C1) — detection_threshold 黄金用例与边界用例。

spec 8.3 行 690-715；黄金值行 1368-1370。
"""
from __future__ import annotations

import inspect
import textwrap

import numpy as np
import pytest

from cascade import statistical_tests as st
from cascade.statistical_tests import (
    compute_hac_se,
    compute_planning_vif,
    detection_threshold_vs_baseline,
    detection_threshold_vs_random,
    diebold_mariano_p,
    n_required,
)

# ── 黄金用例（spec 1368-1370 钦定）──────────────────────────────


def test_golden_vs_random_73():
    """spec 1369: detection_threshold_vs_random(n_eff=73) = 0.596。"""
    got = detection_threshold_vs_random(n_eff=73)
    assert got == pytest.approx(0.596, rel=0.01)


def test_golden_vs_baseline_rho05_n588():
    """spec 1369: rho=0.5、n=588 时 detection_threshold_vs_baseline ~= 0.096。

    构造：d_t = v_ok_t - b_ok_t 的稀疏序列，588 点中 2 点非零且相隔 > q
    （q=11），使 HAC 长程方差 ~= 样本方差 = 2/588。
    门槛 = 1.645 * sqrt(2/588) ~= 0.096。
    """
    d = np.zeros(588)
    d[100] = 1.0
    d[400] = -1.0
    threshold, se_hac = detection_threshold_vs_baseline(d)
    assert se_hac == pytest.approx(np.sqrt(2 / 588), rel=0.02)
    assert threshold == pytest.approx(0.096, rel=0.01)


def test_vs_baseline_is_not_vs_random_variant():
    """spec 1368: vs_baseline **不等于** baseline_dir_acc + 1.645*0.5/sqrt(n_eff)。

    后者是 vs_random 的加法变体，混淆二者会让"优于基线"被误读成"优于随机"。
    """
    d = np.zeros(588)
    d[100] = 1.0
    d[400] = -1.0
    threshold, _ = detection_threshold_vs_baseline(d)

    baseline_dir_acc = 0.50
    confusable = baseline_dir_acc + 1.645 * 0.5 / np.sqrt(73)

    assert threshold != pytest.approx(confusable, rel=0.01)


# ── 边界用例（spec 8.3 要求各一）────────────────────────────────


def test_boundary_negative_autocorrelation():
    """负自相关：HAC 长程方差应小于样本方差，门槛随之下降。"""
    rng = np.random.default_rng(20260929)
    e = rng.standard_normal(2000)
    x = np.zeros(2000)
    for t in range(1, 2000):
        x[t] = -0.5 * x[t - 1] + e[t]

    lr_neg = compute_hac_se(x)
    iid = rng.standard_normal(2000)
    lr_iid = compute_hac_se(iid)

    assert lr_neg < lr_iid, "负自相关序列的长程方差应低于独立序列"
    assert lr_neg > 0, "长程方差须为正（Bartlett 核保证半正定）"


def test_boundary_constant_series():
    """常数序列：去中心化后全零，长程方差为 0，门槛为 0（无信号可检测）。"""
    d = np.full(588, 0.25)
    threshold, se_hac = detection_threshold_vs_baseline(d)
    assert se_hac == 0.0
    assert threshold == 0.0


def test_boundary_insufficient_effective_samples():
    """有效样本不足：n_eff -> 0 时门槛发散，不得返回有限值。"""
    with pytest.raises(ValueError):
        detection_threshold_vs_random(n_eff=0.0)


def test_boundary_bandwidth_edge():
    """带宽边界：q 不得超过 n-1，否则重叠切片为空。"""
    x = np.array([1.0, -1.0, 0.5])
    # q 默认 11 > n-1=2，实现应收窄到 2 而非崩溃或返回负方差
    lr = compute_hac_se(x)
    assert np.isfinite(lr)
    assert lr >= 0


# ── 互斥口径：禁止「长程方差 x VIF」混用（spec 1329）──────────


def test_no_lr_variance_times_vif_mixing_path():
    """n_required 不得在内部把 HAC 长程方差与 VIF 相乘。

    spec 715-745 规定两条口径互斥：
      (a) 情景近似  n = Var(d) * VIF * (z_a+z_b)^2 / D^2
      (b) 先导估计  n = Var_LR(d) * (z_a+z_b)^2 / D^2   (VIF = 1)
    若 n_required 内部再乘一次 VIF，两条口径会塌回同一条，结果不可辨识。
    """
    src = textwrap.dedent(inspect.getsource(n_required))
    body = src.split('"""')[-1]  # 跳过 docstring，只看可执行体

    assert "compute_hac_se" not in body, (
        "n_required 不得调用 compute_hac_se：情景近似与先导估计必须互斥"
    )
    assert "compute_planning_vif" not in body, (
        "n_required 不得自行取 VIF：VIF 必须由调用方显式传入"
    )


def test_vif_one_reduces_to_pilot_estimate():
    """口径 (b) 的退化形式：VIF=1 时 n_required 即先导估计。"""
    a = n_required(var_d=0.25, vif=1.0, delta=0.10)
    b = n_required(var_d=0.25, delta=0.10)  # 默认 vif=1.0
    assert a == b


# ── 重叠预测：实测 HAC vs 名义 VIF（spec 8.3 出口 7）────────────


def test_nominal_vif_is_not_a_substitute_for_measured_hac():
    """名义 VIF（8.0278）不得用于检验校正。

    独立同分布序列的实测 HAC 长程方差 ~= 1.0；若误用名义 VIF 8.0278，
    门槛会被放大约 sqrt(8) = 2.83 倍。
    """
    rng = np.random.default_rng(20260930)
    iid = rng.standard_normal(2000)
    measured = compute_hac_se(iid)
    nominal_vif = compute_planning_vif(horizon=24, step=2)

    assert nominal_vif == pytest.approx(8.0278, rel=0.001)
    assert measured == pytest.approx(1.0, rel=0.15), (
        "独立序列的实测 HAC 应 ~= 1.0，与名义 VIF 8.03 相差一个量级"
    )
    assert abs(measured - nominal_vif) > 1.0


def test_dm_reuses_the_same_hac_estimator():
    """spec 4.1 W1.2：DM 与 n_eff 共用同一 HAC 估计量，禁止另写一套。"""
    src = textwrap.dedent(inspect.getsource(diebold_mariano_p))
    assert "compute_hac_se" in src, "DM 必须复用 compute_hac_se（唯一家）"


def test_vs_baseline_se_is_square_root_of_long_run_variance():
    """SE_HAC 是长程方差的平方根（与 DM 的 sqrt(V) 同一约定）。"""
    d = np.zeros(588)
    d[100] = 1.0
    d[400] = -1.0
    _, se_hac = detection_threshold_vs_baseline(d)
    assert se_hac == pytest.approx(np.sqrt(compute_hac_se(d)), rel=1e-9)
