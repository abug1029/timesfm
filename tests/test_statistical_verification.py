"""Phase 6 — §8.3 出口核验（spec 1528-1552）。

本文件是 spec §8.3 的**集成验证入口**：确保 Phase 1 的 3 套公式 + Phase 3 的 horizon
契约 + Phase 5 的指纹 bump 三者协同工作，符合 spec 的整体设计。

独立手算对账记录见 `docs/superpowers/reports/2026-09-29-stage3-verification-record.md`。
"""
from __future__ import annotations

import numpy as np
import pytest

from cascade.evaluation_metrics import measured_n_eff
from cascade.horizon_fill import get_horizon_known, horizon_exogenous
from cascade.statistical_tests import (
    compute_hac_se,
    compute_planning_vif,
    detection_threshold_vs_baseline,
    detection_threshold_vs_random,
    n_required,
)
from task_FM.evaluations.fm_eval.evaluator import (
    PROTOCOL_FINGERPRINT_VERSION,
    compute_protocol_fingerprint,
)


# ── §8.3 出口 1-7 已通过 Phase 1 测试覆盖，此处做闭环自验 ───


def test_stage3_exit_8_n_eff_closed_loop():
    """闭环自验：n=588, VIF=8.0278 → n_eff≈73 → vs_random(73)=0.596。

    spec 钦定的三个数字（588 / 8.0278 / 73）必须相互自洽。
    """
    n = 588
    vif = compute_planning_vif(horizon=24, step=2)
    assert vif == pytest.approx(8.0278, rel=0.001)

    n_eff = n / vif
    assert n_eff == pytest.approx(73.0, rel=0.05)

    thr = detection_threshold_vs_random(n_eff=n_eff)
    assert thr == pytest.approx(0.596, rel=0.01)


def test_stage3_horizon_and_statistical_contracts_coexist():
    """horizon 契约（W5）与统计契约（§8.3）不得互相冲突。

    验证：horizon_known 分类能正常读取，与统计公式共用同一套输入。
    """
    # horizon 契约正常
    assert get_horizon_known("rsi_state") in ("persistence", "self_referential", "unknowable", "known_ahead")
    assert get_horizon_known("calendar_cyclical") == "known_ahead"

    # 统计公式正常
    thr = detection_threshold_vs_random(n_eff=73)
    assert 0.5 < thr < 1.0

    # horizon_exogenous 与统计无冲突
    assert horizon_exogenous(["rsi_state"]) is False
    assert horizon_exogenous(["calendar_cyclical"]) is True


def test_stage3_protocol_fingerprint_v3_includes_all_spec_components():
    """spec 七组件表（H3 补齐）全部进入 fingerprint。

    改动任一组件，fingerprint 必须变化。
    """
    base = compute_protocol_fingerprint()
    assert PROTOCOL_FINGERPRINT_VERSION == "protocol_v3"

    # 逐一验证每个组件参与
    assert base != compute_protocol_fingerprint(metric_version="v2")
    assert base != compute_protocol_fingerprint(cov_fill_version="v999")
    assert base != compute_protocol_fingerprint(horizon=999)
    assert base != compute_protocol_fingerprint(step=99)
    assert base != compute_protocol_fingerprint(cutoff_convention="bar_open")
    assert base != compute_protocol_fingerprint(context_bars=999)
    assert base != compute_protocol_fingerprint(context_days=99)
    assert base != compute_protocol_fingerprint(adjustment_rule_version="v2")
    assert base != compute_protocol_fingerprint(roll_guard_version="v2")


def test_stage3_research_target_hash_stable_across_protocol_bump():
    """H6：protocol_fingerprint 变化不得影响 research_target_hash。

    research_target_hash = 研究问题**身份**（稳定），protocol_fingerprint = 评估口径（可变）。
    二者解耦是 family 边界的基础（spec v8）。
    """
    from cascade.research_family import research_target_hash

    rth_a = research_target_hash("ss", "dir", "main_continuous", "v1")
    # 即使 protocol_fingerprint bump（Phase 5 已做），rth 不受影响
    # （rth 参数里没有 fingerprint 相关字段）
    import inspect
    sig = inspect.signature(research_target_hash)
    assert "protocol_fingerprint" not in sig.parameters
    assert "cutoff_convention" not in sig.parameters

    # 同参数同结果
    rth_b = research_target_hash("ss", "dir", "main_continuous", "v1")
    assert rth_a == rth_b


def test_stage3_exit_gate_all_eight_pass():
    """§8.3 八项核验全部通过的总入口断言。

    实际核验在 Phase 1 测试 + 本文件 + 手算对账记录中。本断言确保：
    - Phase 1 公式可正常调用
    - 黄金值在容差内
    - 闭环自验通过
    - 互斥口径断言通过
    """
    # 4 黄金值
    assert detection_threshold_vs_random(73) == pytest.approx(0.596, rel=0.01)
    # 2.10: spec 真实构造（rho=0.5 AR(1)，sigma_LR^2 ~= 0.25*8.028），替换稀疏构造
    rng = np.random.default_rng(42)
    n, burn = 588, 2000
    e = rng.standard_normal(burn + n) * np.sqrt(0.669 * 0.75)
    d = np.zeros(burn + n)
    for t in range(1, burn + n):
        d[t] = 0.5 * d[t - 1] + e[t]
    d = d[burn:]
    thr, _ = detection_threshold_vs_baseline(d)
    assert thr == pytest.approx(0.096, rel=0.01)
    assert n_required(var_d=0.25, vif=8.028, delta=0.02) == pytest.approx(31000, rel=0.05)
    assert n_required(var_d=0.25, vif=8.028, delta=0.10) == pytest.approx(1240, rel=0.05)

    # 闭环
    n_eff = 588 / compute_planning_vif(24, 2)
    assert detection_threshold_vs_random(n_eff) == pytest.approx(0.596, rel=0.01)

    # 互斥口径（Phase 1 已覆盖，此处再断言一次确保未被破坏）
    import inspect, textwrap
    body = textwrap.dedent(inspect.getsource(n_required)).split('"""')[-1]
    assert "compute_hac_se" not in body
    assert "compute_planning_vif" not in body
