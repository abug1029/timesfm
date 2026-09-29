"""Phase 1 (PR-C1) — n_required 功效规划黄金用例与自洽性。

spec 8.3 行 711；黄金值行 1370。
"""
from __future__ import annotations

import inspect
import textwrap

import pytest

from cascade.statistical_tests import (
    compute_planning_vif,
    detection_threshold_vs_random,
    n_required,
)

# spec 1370 情景表的两个锚点
VAR_D = 0.25
VIF = 8.028


# ── 黄金用例（spec 1370）────────────────────────────────────────


def test_golden_n_required_delta_002():
    """spec 1370: Delta=0.02, rho=0.5, 80% 功效 -> n ~= 31,000 (+/-5%)。"""
    got = n_required(var_d=VAR_D, vif=VIF, delta=0.02)
    assert got == pytest.approx(31_000, rel=0.05)


def test_golden_n_required_delta_010():
    """spec 1370: Delta=0.10, rho=0.5 -> n ~= 1,240 (+/-5%)。

    Q1 裁定（2026-09-29）把 0.10 定为阶段 4 确认目标，本例即该口径下的规划值。
    """
    got = n_required(var_d=VAR_D, vif=VIF, delta=0.10)
    assert got == pytest.approx(1_240, rel=0.05)


# ── 数学自洽性 ──────────────────────────────────────────────────


def test_delta_squared_inverse_relationship():
    """n 与 Delta^2 成反比：Delta 放大 5 倍，n 缩小 25 倍。"""
    n_small = n_required(var_d=VAR_D, vif=VIF, delta=0.02)
    n_large = n_required(var_d=VAR_D, vif=VIF, delta=0.10)
    assert n_small / n_large == pytest.approx(25.0, rel=0.01)


def test_n_eff_73_corresponds_to_n_588_under_vif():
    """闭环自验：VIF=8.028、n=588 -> n_eff ~= 73，与 vs_random(73)=0.596 同源。

    这条把 spec 情景表的三个数字（n=588 / VIF=8.0278 / n_eff=73）绑在一起，
    任一常量被改动都会在此暴露。
    """
    n_eff = 588 / compute_planning_vif(horizon=24, step=2)
    assert n_eff == pytest.approx(73.0, rel=0.01)
    # 同一 n_eff 推出的门槛应等于 spec 钦定的 0.596
    assert detection_threshold_vs_random(n_eff=n_eff) == pytest.approx(0.596, rel=0.01)


def test_q1_target_n_required_is_under_t_max_budget():
    """Q1 裁定 Δ=0.10：n_required ~= 1240，配对确认集当前 n=588。

    差值 ~650 点，按 STEP=2 每品种每天约 12 点 -> 约 54 天，
    落在 PR-C2 的 T_max=180 天内（第五轮审计的裁定依据）。
    """
    n_needed = n_required(var_d=VAR_D, vif=VIF, delta=0.10)
    n_current = 588
    assert n_needed > n_current, "0.10 口径下仍需前向累积"
    assert (n_needed - n_current) / 12 / 2 < 180, "应能在 T_max=180 天内到达功效"


# ── 边界与防护 ──────────────────────────────────────────────────


def test_vif_scales_linearly():
    """VIF 只做一次乘法，不参与 Delta 的幂次。"""
    a = n_required(var_d=VAR_D, vif=1.0, delta=0.10)
    b = n_required(var_d=VAR_D, vif=2.0, delta=0.10)
    assert b == pytest.approx(2 * a, rel=0.01)


def test_zero_delta_rejected():
    """Delta=0 会发散，必须拒绝而不是返回 inf。"""
    with pytest.raises(ValueError):
        n_required(var_d=VAR_D, vif=VIF, delta=0.0)


def test_negative_delta_rejected():
    with pytest.raises(ValueError):
        n_required(var_d=VAR_D, vif=VIF, delta=-0.10)


def test_documented_default_delta_matches_q1_ruling():
    """默认 Delta 必须是 Q1 裁定的 0.10，不得回落到旧的 0.05/0.02。"""
    sig = inspect.signature(n_required)
    assert sig.parameters["delta"].default == 0.10


def test_docstring_states_all_four_required_elements():
    """spec 强制黄金用例 docstring 四要素。"""
    doc = inspect.getdoc(n_required)
    for element in ("带宽约定", "均值中心化", "样本方差分母", "有限样本修正"):
        assert element in doc, f"docstring 缺要素: {element}"


def test_result_is_ceiling_of_required_sample_size():
    """返回值向上取整，不得截断（截断会让 n 低于功效所需）。"""
    exact = n_required(var_d=VAR_D, vif=VIF, delta=0.10)
    raw = VAR_D * VIF * (1.645 + 0.842) ** 2 / 0.10 ** 2
    assert exact >= raw
    assert exact - raw < 1.0


def test_no_internal_hac_call():
    """情景近似口径不得在内部混入 HAC 估计（spec 715-745 互斥要求）。"""
    body = textwrap.dedent(inspect.getsource(n_required)).split('"""')[-1]
    assert "compute_hac_se" not in body
