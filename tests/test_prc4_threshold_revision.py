"""PR-C4 测试：门槛一致性 + 历史修订防护 + 预训练登记"""

import pytest
import numpy as np
from task_FM.evaluations.fm_eval.evaluator import _compute_context_hash


def test_compute_context_hash_with_points():
    """逐点摘要在写入点算好，本函数只汇总。"""
    points = [
        {"cutoff": 1000, "context_hash": "aaaa1111"},
        {"cutoff": 1001, "context_hash": "bbbb2222"},
    ]

    hash1 = _compute_context_hash(points)
    assert hash1 is not None
    assert len(hash1) == 16  # SHA-256 前 16 位

    # 相同输入应产生相同哈希
    hash2 = _compute_context_hash(points)
    assert hash1 == hash2


def test_compute_context_hash_different_context():
    """不同 context 摘要 → 不同汇总哈希"""
    points1 = [{"cutoff": 1000, "context_hash": "aaaa1111"}]
    points2 = [{"cutoff": 1000, "context_hash": "cccc3333"}]

    assert _compute_context_hash(points1) != _compute_context_hash(points2)


def test_compute_context_hash_order_invariant():
    """点序不同不影响汇总 —— 否则 resume 顺序会伪造「数据修订」。"""
    a = [{"cutoff": 1000, "context_hash": "aaaa1111"},
         {"cutoff": 1001, "context_hash": "bbbb2222"}]
    b = list(reversed(a))
    assert _compute_context_hash(a) == _compute_context_hash(b)


def test_compute_context_hash_ignores_future_fields():
    """防回归：W6.7 是历史修订防护，**不得**混入未来真值。

    生产 checkpoint 逐点只有 real_end（未来真值）而没有 context 摘要。
    若把 real_end 当作 fallback 哈希基底，则「结果变了」会被误读成
    「context 修订了」—— 用未来信息判历史，逻辑上不成立。
    """
    points = [{"cutoff": 1000, "real_endpoint": 50.0},
              {"cutoff": 1001, "real_endpoint": 51.0}]
    assert _compute_context_hash(points) is None

    # 同 cutoff、仅未来值不同 → 仍无摘要（不得产生哈希）
    changed = [{"cutoff": 1000, "real_endpoint": 99.0}]
    assert _compute_context_hash(changed) is None


def test_compute_context_hash_legacy_point_returns_none():
    """旧 checkpoint 无 context 摘要时诚实返回 None，不拿别的量冒充。"""
    assert _compute_context_hash([{"cutoff": 1000, "real_end": 50.0}]) is None


def test_compute_context_hash_empty():
    """测试空 points 返回 None"""
    assert _compute_context_hash(None) is None
    assert _compute_context_hash([]) is None


def test_threshold_basis_baseline():
    """W6.6 门槛一致性：有基线时 threshold_basis='baseline'。

    注意键名是 threshold_basis 而非 gate_basis —— 后者的既有词表
    （active / full_fallback）说的是「用哪个总体口径」，与「阈值参照是否
    缺失」不是一回事，混用会让无基线的 run 被误读成 gated pool 加载失败。
    """
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
    assert verdict["threshold_basis"] == "baseline"


def test_threshold_basis_fallback():
    """W6.6：无基线时 threshold_basis='fallback_0.52'"""
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
    assert verdict["threshold_basis"] == "fallback_0.52"


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


def test_data_revised_is_unknown_not_false():
    """data_revised 缺省必须是 None（尚未比对），不是 False。

    W6.7 的比对发生在**重算路径**（拿历史 verdict 的 context_hash 比对新值），
    单次 build_summary 内无从得知。恒写 False 等于把「没查过」伪装成
    「查过且未修订」—— 那正是 W6.7 要防的事。
    """
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
    assert verdict["data_revised"] is None


def test_context_hash_in_verdict():
    """逐点带 context 摘要时，汇总哈希出现在 verdict 中"""
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
    points = [{"cutoff": 1000, "context_hash": "aaaa1111"},
              {"cutoff": 1001, "context_hash": "bbbb2222"}]

    verdict = build_summary(s, cand, points=points)

    assert "context_hash" in verdict
    assert verdict["context_hash"] is not None
    assert len(verdict["context_hash"]) == 16


def test_context_hash_none_for_legacy_points():
    """无逐点摘要时 context_hash 为 None —— W6.7 未生效是**可见**的，不是静默通过。"""
    from task_FM.evaluations.fm_eval.evaluator import build_summary

    s = {
        "n": 100, "n_eff": 80, "dir_acc": 0.6, "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6, "n_roll_excluded": 0, "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0, "endpoint_bias_pct": 0.5, "path_corr": 0.8,
        "weighted_dir_acc": 0.6, "mae": 0.5, "mape": 1.0, "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}
    verdict = build_summary(s, cand, points=[{"cutoff": 1000, "real_end": 50.0}])
    assert verdict["context_hash"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
