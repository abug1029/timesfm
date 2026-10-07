"""子任务 2.5 — delta_post_shrunk 落账 + n_required 途径 B（spec 2026-10-05 §5/§6.3/§7 T5/T6/T10）。

锁定：
- §6.3 缩水公式 δ_post = δ·τ²/(τ²+se²)（τ=0.04, τ²=0.0016）；T5/T6 数例
  δ_post=0.0384 / 0.096，n_required 大于 / 小于 1,199（jd 已锁定样本量）。
- §5 se = sqrt(compute_hac_se(d_t)/T)：T<2 或长程方差非有限正 → se 不可算
  （None），delta_post_shrunk 同落 None。
- §6.3 n_required 途径 B：var_d = compute_hac_se(d_t)（长程方差本身）、vif 恒 1；
  δ_post<=0 时不调用、直接不晋升（T10：vif 与长程方差不同时进入同一次调用）。
- 落账：build_summary 顶层写 se / delta_post_shrunk；registry 追加/回读保真；
  历史行缺这两键仍合法（可选字段）。
"""
from __future__ import annotations

import copy
import inspect
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cascade import statistical_tests as st  # noqa: E402
from task_FM.evaluations.fm_eval import evaluator as fm  # noqa: E402
import registry_lib as rl  # noqa: E402


TAU2 = 0.04 ** 2
T_FIXED = 588


# ── 辅助：构造有方差的配对序列 ────────────────────────────────

def _pairs(n=120, v_thresh=6, b_thresh=4):
    """确定性配对序列：变体命中率 v_thresh/10，基线 b_thresh/10，共同 cutoff。"""
    v = [("2024-06-15 %02d:%02d:00" % (i // 60, i % 60), (i % 10) < v_thresh)
         for i in range(n)]
    b = [{"cutoff": ts, "dir_ok": (i % 10) < b_thresh}
         for i, (ts, _) in enumerate(v)]
    return v, b


def _series_for(v_pts, b_pts):
    diag = st.pair_dir_ok_series_with_diagnostics(v_pts, b_pts)
    return diag, [a - b for a, b in
                  zip(diag["variant_series"], diag["baseline_series"])]


# ══════════════════ §6.3 缩水公式 T5/T6 ══════════════════

def test_t5_shrink_numeric():
    """T5: δ=0.06, se=0.03 → δ_post = 0.06·0.0016/(0.0016+0.0009) = 0.0384。"""
    got = st.shrink_delta_post(0.06, 0.03)
    assert got == pytest.approx(0.0384, rel=1e-9)


def test_t6_shrink_numeric():
    """T6: δ=0.12, se=0.02 → δ_post = 0.12·0.0016/(0.0016+0.0004) = 0.096。"""
    got = st.shrink_delta_post(0.12, 0.02)
    assert got == pytest.approx(0.096, rel=1e-9)


def test_shrink_same_sign_and_smaller_magnitude():
    """δ_post 与 δ 同号、绝对值更小（§6.3）。"""
    for delta, se in ((0.06, 0.03), (0.12, 0.02), (-0.05, 0.01)):
        post = st.shrink_delta_post(delta, se)
        assert post is not None
        assert post * delta >= 0
        assert abs(post) < abs(delta)


def test_shrink_none_when_se_uncomputable():
    """se 不可算（None）→ δ_post 落 None，不臆造。"""
    assert st.shrink_delta_post(0.06, None) is None
    assert st.shrink_delta_post(None, 0.03) is None
    assert st.shrink_delta_post(0.06, float("inf")) is None
    assert st.shrink_delta_post(0.06, float("nan")) is None


def test_tau_is_frozen_004():
    """τ=0.04（τ²=0.0016）写死，不估计（spec §5/§8）。"""
    assert st.SHRINK_TAU_SD == 0.04
    assert TAU2 == pytest.approx(0.0016)


# ══════════════════ §5 se 可算口径 ══════════════════

def test_paired_delta_se_formula_matches_production_hac():
    """se = sqrt(compute_hac_se(d_t)/T)，走生产 compute_hac_se。"""
    _v, _b = _pairs()
    _diag, d_t = _series_for(*_pairs())
    got = st.paired_delta_se(d_t)
    expected = (st.compute_hac_se(d_t) / len(d_t)) ** 0.5
    assert got == pytest.approx(expected, rel=1e-12)
    assert got > 0


def test_paired_delta_se_none_when_short_or_degenerate():
    """T<2 / 常数序列（长程方差为 0）→ None（§5 fail-closed）。"""
    assert st.paired_delta_se([]) is None
    assert st.paired_delta_se([1.0]) is None
    assert st.paired_delta_se([1.0, 1.0, 1.0]) is None  # 方差 0


def test_paired_delta_se_none_when_non_finite():
    assert st.paired_delta_se([1.0, float("nan"), 0.0, 1.0]) is None


# ══════════════════ T5/T6 功效判断（生产 n_required）══════════════════

def test_t5_var_d_relationship_and_n_exceeds_budget():
    """T5: T=588, se=0.03 → var_d=se²·T=0.5292；n_required > 1,199，不晋升。"""
    se, T = 0.03, T_FIXED
    var_d = se ** 2 * T
    assert var_d == pytest.approx(0.5292, rel=1e-9)
    n = st.n_required(var_d=var_d, vif=1.0, z_alpha=1.645, z_beta=0.842,
                      delta=st.shrink_delta_post(0.06, se))
    assert n > 1199


def test_t6_var_d_relationship_and_n_below_budget():
    """T6: T=588, se=0.02 → var_d=0.2352；n_required < 1,199。"""
    se, T = 0.02, T_FIXED
    var_d = se ** 2 * T
    assert var_d == pytest.approx(0.2352, rel=1e-9)
    n = st.n_required(var_d=var_d, vif=1.0, z_alpha=1.645, z_beta=0.842,
                      delta=st.shrink_delta_post(0.12, se))
    assert n < 1199


# ══════════════════ n_required 途径 B（T10）══════════════════

def test_via_b_skips_when_delta_post_nonpositive(monkeypatch):
    """δ_post<=0 时不调用 n_required，直接不晋升（返回 None）。"""
    def _boom(*a, **k):
        raise AssertionError("δ_post<=0 不得调用 n_required")
    monkeypatch.setattr(st, "n_required", _boom)
    _diag, d_t = _series_for(*_pairs())
    assert st.n_required_via_long_run(d_t, 0.0) is None
    assert st.n_required_via_long_run(d_t, -0.05) is None
    assert st.n_required_via_long_run(d_t, None) is None


def test_via_b_uses_vif_one_and_long_run_variance(monkeypatch):
    """T10: 途径 B 恒 vif=1，var_d=compute_hac_se(d_t)（长程方差本身）。"""
    captured = {}

    def _capture(var_d, vif=1.0, z_alpha=1.645, z_beta=0.842, delta=0.10):
        captured.update(var_d=var_d, vif=vif, delta=delta)
        return 4242

    monkeypatch.setattr(st, "n_required", _capture)
    _diag, d_t = _series_for(*_pairs())
    got = st.n_required_via_long_run(d_t, 0.05)
    assert got == 4242
    assert captured["vif"] == 1.0
    assert captured["var_d"] == pytest.approx(st.compute_hac_se(d_t), rel=1e-12)
    assert captured["delta"] == 0.05


def test_via_b_no_mixed_vif_and_hac_path():
    """T10: 途径 B 的调用只走 vif=1 单路径，不引入规划 VIF。"""
    src = inspect.getsource(st.n_required_via_long_run)
    assert "vif=1.0" in src
    assert "compute_planning_vif" not in src
    # n_required 本体仍不得内部调 HAC（既有互斥约束）
    body = inspect.getsource(st.n_required)
    assert "compute_hac_se" not in body


def test_via_b_none_when_var_unavailable():
    """var_d 不可用（T<2/退化）→ None，不调用 n_required。"""
    assert st.n_required_via_long_run([], 0.05) is None
    assert st.n_required_via_long_run([1.0, 1.0, 1.0], 0.05) is None


# ══════════════════ build_summary 落账 ══════════════════

def _summary(dir_acc=0.56, **kw):
    base = {"n": 400, "n_eff": 400, "dir_acc": dir_acc,
            "endpoint_mape": 0.4, "endpoint_bias_pct": 0.1, "path_corr": 0.7,
            "weighted_dir_acc": dir_acc, "mae": 1.0, "mape": 0.4, "decay": 1.1,
            "n_dir_total": 400, "n_dir_active": 400, "n_zero_move": 0,
            "n_zero_ratio": 0.0}
    base.update(kw)
    return base


def _cand():
    return {"symbol": "m", "cov_override": "rsi_state", "max_points": 400,
            "stage": "aligned"}


def test_build_summary_writes_se_and_delta_post_shrunk():
    v_pts, b_pts = _pairs()
    diag, d_t = _series_for(v_pts, b_pts)
    exp_se = st.paired_delta_se(d_t)
    exp_dp = st.shrink_delta_post(0.56 - 0.50, exp_se)
    assert exp_se is not None and exp_dp is not None

    s = _summary(dir_acc=0.56, point_dir_ok_list=v_pts)
    out = fm.build_summary(s, _cand(), baseline_points=b_pts,
                           baseline_dir_acc=0.50, batch_id="b1")
    assert out["se"] == pytest.approx(exp_se, rel=1e-9)
    assert out["delta_post_shrunk"] == pytest.approx(exp_dp, rel=1e-9)
    assert out["search_var_lr"] == pytest.approx(st.compute_hac_se(d_t), rel=1e-9)
    # 与 delta 同号、更小
    assert out["delta_post_shrunk"] < (0.56 - 0.50)


def test_build_summary_null_without_baseline():
    s = _summary(point_dir_ok_list=[])
    out = fm.build_summary(s, _cand(), batch_id="b1")
    assert "se" in out and out["se"] is None
    assert "delta_post_shrunk" in out and out["delta_post_shrunk"] is None


def test_build_summary_null_when_series_too_short():
    """配对点 <2 → se 不可算 → delta_post_shrunk=null。"""
    v_pts = [("2024-06-15 00:00:00", True)]
    b_pts = [{"cutoff": "2024-06-15 00:00:00", "dir_ok": False}]
    s = _summary(point_dir_ok_list=v_pts)
    out = fm.build_summary(s, _cand(), baseline_points=b_pts,
                           baseline_dir_acc=0.50, batch_id="b1")
    assert out["se"] is None
    assert out["delta_post_shrunk"] is None


def test_build_summary_se_matches_spec_via_b_flow():
    """端到端：build_summary 的 se → 途径 B n_required 与 §6.3 公式闭环。"""
    v_pts, b_pts = _pairs()
    _diag, d_t = _series_for(v_pts, b_pts)
    s = _summary(dir_acc=0.56, point_dir_ok_list=v_pts)
    out = fm.build_summary(s, _cand(), baseline_points=b_pts,
                           baseline_dir_acc=0.50, batch_id="b1")
    n = st.n_required_via_long_run(d_t, out["delta_post_shrunk"])
    assert n is not None and n > 0


# ══════════════════ registry 追加/回读往返 ══════════════════

def _transport(summary):
    row = copy.deepcopy(summary)
    row.update({"variant_id": "m_rsi_state_p400", "checkpoint_path": None,
                "slow_loop_pid": None, "git_rev": None,
                "decided_at": "2026-10-06T00:00:00"})
    return row


def test_registry_roundtrip_preserves_new_fields(tmp_path):
    v_pts, b_pts = _pairs()
    s = _summary(dir_acc=0.56, point_dir_ok_list=v_pts)
    out = fm.build_summary(s, _cand(), baseline_points=b_pts,
                           baseline_dir_acc=0.50, batch_id="b1")
    assert out["delta_post_shrunk"] is not None
    row = _transport(out)
    assert rl.validate_verdict(row) == []

    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        rl.append_verdict(f, row)
    snap = rl.load_snapshot(str(reg))
    got = snap["m_rsi_state_p400"]
    assert got["se"] == pytest.approx(out["se"], rel=1e-12)
    assert got["delta_post_shrunk"] == pytest.approx(
        out["delta_post_shrunk"], rel=1e-12)
    assert got["delta_post_shrunk"] is not None


def test_registry_backward_compatible_without_new_fields(tmp_path):
    """历史行缺 se/delta_post_shrunk 仍合法（登记为可选字段，fail-closed 不破）。"""
    row = {"schema": "fm.aligned_verdict.v2", "variant_id": "old",
           "symbol": "m", "cov_override": "rsi_state", "cov_family": "momentum",
           "status": "ok", "stage": "aligned", "batch_id": "b",
           "n": 400, "n_eff": 400, "dir_acc": 0.56, "weighted_dir_acc": 0.57,
           "gate_pass": True, "p_value": 0.01, "fdr_pass": None,
           "migrated_pass": None, "endpoint_mape": None,
           "endpoint_bias_pct": None, "path_corr": None, "mae": None,
           "mape": None, "decay": None, "checkpoint_path": None,
           "slow_loop_pid": None, "git_rev": None, "decided_at": "t",
           "baseline_dir_acc": 0.5, "effective_min": 0.5,
           "run_mode": "exploration", "run_label": "exploratory_unconfirmed",
           "dir_acc_full": 0.55, "dir_acc_ex_roll": 0.55, "n_roll_excluded": 0,
           "n_roll_ratio": 0.0, "n_dir_total": 400, "n_dir_active": 400,
           "n_zero_move": 0, "n_zero_ratio": 0.0,
           "protocol_fingerprint": "fp", "sample_fingerprint": None,
           "cov_fingerprint": None, "weight_fingerprint": None,
           "seed_fingerprint": None, "dm_status": "set_mismatch_descriptive",
           "dm_common_count": 50, "dm_unmatched_variant": 0,
           "dm_unmatched_baseline": 0, "pair_set_hash": None,
           "raw_cutoff_set_hash": None, "d_series_n_eff": 50,
           "d_bar_le_zero": False, "n_avail_variant": 50,
           "n_avail_baseline": 50, "missingness_admissible": False,
           "covariates_used": True, "pairing_valid": False,
           "xreg_fallback_count": None, "xreg_fallback_rate": None}
    assert rl.validate_verdict(row) == []
    assert "se" not in row and "delta_post_shrunk" not in row


def test_new_fields_registered_optional_in_schema():
    """新字段登记进 VERDICT_FIELDS_V2 且为 nullable（可选），不改既有必填。"""
    assert "se" in rl.VERDICT_FIELDS_V2
    assert "delta_post_shrunk" in rl.VERDICT_FIELDS_V2
    assert "se" in rl.VERDICT_FIELDS_V2_NULLABLE
    assert "delta_post_shrunk" in rl.VERDICT_FIELDS_V2_NULLABLE
