"""PR-C4 测试：门槛一致性 + 历史修订防护 + 预训练登记"""

import pytest
import numpy as np
from task_FM.evaluations.fm_eval.evaluator import _compute_context_hash


def test_compute_context_hash_with_points():
    """测试有 points 时的 context_hash 计算"""
    points = [
        {"cutoff": 1000, "real_endpoint": 50.0, "context_window": np.array([1.0, 2.0, 3.0])},
        {"cutoff": 1001, "real_endpoint": 51.0, "context_window": np.array([2.0, 3.0, 4.0])},
    ]

    hash1 = _compute_context_hash(points)
    assert hash1 is not None
    assert len(hash1) == 16  # SHA-256 前 16 位

    # 相同输入应产生相同哈希
    hash2 = _compute_context_hash(points)
    assert hash1 == hash2


def test_compute_context_hash_different_context():
    """测试不同 context 产生不同哈希"""
    points1 = [
        {"cutoff": 1000, "real_endpoint": 50.0, "context_window": np.array([1.0, 2.0, 3.0])},
    ]
    points2 = [
        {"cutoff": 1000, "real_endpoint": 51.0, "context_window": np.array([1.0, 2.0, 4.0])},
    ]

    hash1 = _compute_context_hash(points1)
    hash2 = _compute_context_hash(points2)

    assert hash1 != hash2, "不同 context 应产生不同哈希"


def test_compute_context_hash_fallback():
    """测试 fallback 路径（无 context_window 时用 cutoff + real_endpoint）"""
    points = [
        {"cutoff": 1000, "real_endpoint": 50.0},
        {"cutoff": 1001, "real_endpoint": 51.0},
    ]

    hash1 = _compute_context_hash(points)
    assert hash1 is not None
    assert len(hash1) == 16


def test_compute_context_hash_empty():
    """测试空 points 返回 None"""
    assert _compute_context_hash(None) is None
    assert _compute_context_hash([]) is None


def test_gate_basis_baseline():
    """测试 gate_basis 标记：有基线时为 'baseline'"""
    from task_FM.evaluations.fm_eval.evaluator import build_summary

    # 构造模拟数据
    s = {
        "n": 100,
        "n_eff": 80,
        "dir_acc": 0.6,
        "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6,
        "n_roll_excluded": 0,
        "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0,
        "endpoint_bias_pct": 0.5,
        "path_corr": 0.8,
        "weighted_dir_acc": 0.6,
        "mae": 0.5,
        "mape": 1.0,
        "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}

    # 有基线
    verdict = build_summary(s, cand, baseline_dir_acc=0.55)
    assert verdict["gate_basis"] == "baseline"


def test_gate_basis_fallback():
    """测试 gate_basis 标记：无基线时为 'fallback_0.52'"""
    from task_FM.evaluations.fm_eval.evaluator import build_summary

    s = {
        "n": 100,
        "n_eff": 80,
        "dir_acc": 0.6,
        "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6,
        "n_roll_excluded": 0,
        "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0,
        "endpoint_bias_pct": 0.5,
        "path_corr": 0.8,
        "weighted_dir_acc": 0.6,
        "mae": 0.5,
        "mape": 1.0,
        "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}

    # 无基线
    verdict = build_summary(s, cand, baseline_dir_acc=None)
    assert verdict["gate_basis"] == "fallback_0.52"


def test_pretrain_risk_field():
    """测试预训练风险登记字段存在"""
    from task_FM.evaluations.fm_eval.evaluator import build_summary

    s = {
        "n": 100,
        "n_eff": 80,
        "dir_acc": 0.6,
        "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6,
        "n_roll_excluded": 0,
        "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0,
        "endpoint_bias_pct": 0.5,
        "path_corr": 0.8,
        "weighted_dir_acc": 0.6,
        "mae": 0.5,
        "mape": 1.0,
        "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}

    verdict = build_summary(s, cand)

    assert "pretrain_risk" in verdict
    assert verdict["pretrain_risk"]["status"] == "registered"
    assert "model_card_cutoffs" in verdict["pretrain_risk"]
    assert "eval_window" in verdict["pretrain_risk"]
    assert verdict["pretrain_risk"]["gap_years"] == 2


def test_data_revised_default():
    """测试 data_revised 默认为 False"""
    from task_FM.evaluations.fm_eval.evaluator import build_summary

    s = {
        "n": 100,
        "n_eff": 80,
        "dir_acc": 0.6,
        "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6,
        "n_roll_excluded": 0,
        "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0,
        "endpoint_bias_pct": 0.5,
        "path_corr": 0.8,
        "weighted_dir_acc": 0.6,
        "mae": 0.5,
        "mape": 1.0,
        "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}

    verdict = build_summary(s, cand)

    assert "data_revised" in verdict
    assert verdict["data_revised"] is False


def test_context_hash_in_verdict():
    """测试 context_hash 出现在 verdict 中"""
    from task_FM.evaluations.fm_eval.evaluator import build_summary

    s = {
        "n": 100,
        "n_eff": 80,
        "dir_acc": 0.6,
        "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6,
        "n_roll_excluded": 0,
        "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0,
        "endpoint_bias_pct": 0.5,
        "path_corr": 0.8,
        "weighted_dir_acc": 0.6,
        "mae": 0.5,
        "mape": 1.0,
        "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}
    points = [{"cutoff": 1000, "real_endpoint": 50.0}]

    verdict = build_summary(s, cand, points=points)

    assert "context_hash" in verdict
    assert verdict["context_hash"] is not None
    assert len(verdict["context_hash"]) == 16


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
