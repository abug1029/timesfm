# N5: weight_fingerprint 接线集成测试
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest


def test_weight_fingerprint_safe_returns_real_value():
    """_compute_weight_fingerprint_safe() 在生产环境下应返回真实指纹, 非 None.

    前置条件: models/timesfm-3.0-pytorch/ 存在且有模型文件.
    若路径不存在则 skip (环境依赖), 但一旦执行, 必须断言非 None.
    """
    from task_FM.evaluations.fm_eval.evaluator import (
        _compute_weight_fingerprint_safe, _WEIGHT_FINGERPRINT_CACHE, _NOT_COMPUTED
    )
    # 清缓存确保真算一次
    _WEIGHT_FINGERPRINT_CACHE["value"] = _NOT_COMPUTED
    result = _compute_weight_fingerprint_safe()
    # 生产环境 models/ 有模型文件 → 应返回 dict
    if result is None:
        pytest.skip("models/timesfm-3.0-pytorch 不存在或为空, 跳过生产环境断言")
    assert isinstance(result, dict)
    assert "weights_sha256" in result
    assert len(result["weights_sha256"]) >= 16
    assert result["n_files"] >= 1
    assert result["hash_version"] == "v1"


def test_weight_fingerprint_safe_caches_result():
    """同进程内第二次调用应返回同一对象 (缓存命中)."""
    from task_FM.evaluations.fm_eval.evaluator import (
        _compute_weight_fingerprint_safe, _WEIGHT_FINGERPRINT_CACHE, _NOT_COMPUTED
    )
    _WEIGHT_FINGERPRINT_CACHE["value"] = _NOT_COMPUTED
    r1 = _compute_weight_fingerprint_safe()
    r2 = _compute_weight_fingerprint_safe()
    assert r1 is r2, "缓存未生效: 两次调用返回不同对象"


def test_weight_fingerprint_safe_fail_visible_on_bad_path(monkeypatch):
    """路径不存在时应返回 None 且打 WARN, 不抛异常."""
    from task_FM.evaluations.fm_eval import evaluator

    # 让 get_timesfm_model_path 返回不存在的路径
    def fake_path():
        return "/nonexistent/model/path"

    monkeypatch.setattr("data.config.get_timesfm_model_path", fake_path)
    # 清缓存
    evaluator._WEIGHT_FINGERPRINT_CACHE["value"] = evaluator._NOT_COMPUTED
    result = evaluator._compute_weight_fingerprint_safe()
    assert result is None, "路径不存在时应返回 None (fail-visible)"
    # 缓存 None 也生效
    assert evaluator._WEIGHT_FINGERPRINT_CACHE["value"] is None


def test_seed_fingerprint_deliberately_none():
    """seed_fingerprint 恒为 None 是设计正确, 非 bug.

    当前系统无 per-verdict 随机种子. hourly_model.py 仅有硬编码 seed=42
    用于消融, 不随 verdict 变化. 此测试防止未来误接线.
    """
    from task_FM.evaluations.fm_eval.evaluator import build_summary
    s = {
        "n": 100, "n_eff": 80, "dir_acc": 0.6, "dir_acc_full": 0.6,
        "dir_acc_ex_roll": 0.6, "n_roll_excluded": 0, "n_roll_ratio": 0.0,
        "endpoint_mape": 1.0, "endpoint_bias_pct": 0.5, "path_corr": 0.8,
        "weighted_dir_acc": 0.6, "mae": 0.5, "mape": 1.0, "decay": 1.0,
        "covariates_used": True,
    }
    cand = {"symbol": "ss", "cov_override": "rsi_state", "stage": "aligned"}
    verdict = build_summary(s, cand)
    assert verdict["seed_fingerprint"] is None, (
        "seed_fingerprint 应恒为 None (无 per-verdict seed), "
        "若此测试失败说明有人接线了但未更新此测试"
    )
