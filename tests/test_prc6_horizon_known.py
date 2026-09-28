"""PR-C6 测试：horizon_known 分类系统"""

import pytest
import json
from pathlib import Path


def test_covariate_pool_has_horizon_known():
    """测试 covariate_pool.json 所有协变量都有 horizon_known 字段"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    covariates = pool.get("covariates", {})
    assert len(covariates) > 0, "协变量池不应为空"

    for cov_name, cov_config in covariates.items():
        assert "horizon_known" in cov_config, f"{cov_name} 缺少 horizon_known 字段"
        assert cov_config["horizon_known"] in {
            "known_ahead", "persistence", "self_referential", "unknowable"
        }, f"{cov_name} 的 horizon_known 值不合法: {cov_config['horizon_known']}"


def test_known_ahead_has_evidence():
    """测试 known_ahead 协变量必须有 known_ahead_evidence"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    covariates = pool.get("covariates", {})

    for cov_name, cov_config in covariates.items():
        if cov_config.get("horizon_known") == "known_ahead":
            assert "known_ahead_evidence" in cov_config, (
                f"{cov_name} 标为 known_ahead 但缺少 known_ahead_evidence"
            )
            evidence = cov_config["known_ahead_evidence"]
            # 检查证据必填字段
            required_fields = ["source", "publication_rule", "publication_lag",
                             "reconstructable", "verified_by", "verified_at"]
            for field in required_fields:
                assert field in evidence, f"{cov_name} 的 evidence 缺少 {field}"


def test_host_rulings_respected():
    """测试宿主裁定被正确落实"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    covariates = pool.get("covariates", {})

    # 宿主裁定（2026-09-28）
    expected = {
        "calendar_cyclical": "known_ahead",
        "rsi_state": "self_referential",
        "hourly_slope": "self_referential",
        "ccl": "unknowable",
        "oi": "unknowable",
    }

    for cov_name, expected_hk in expected.items():
        assert cov_name in covariates, f"{cov_name} 不在协变量池中"
        actual_hk = covariates[cov_name].get("horizon_known")
        assert actual_hk == expected_hk, (
            f"{cov_name} 的 horizon_known 应为 {expected_hk}，实际为 {actual_hk}"
        )


def test_calendar_cyclical_evidence_content():
    """测试 calendar_cyclical 的证据内容符合宿主裁定"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    cal_config = pool["covariates"]["calendar_cyclical"]
    evidence = cal_config.get("known_ahead_evidence", {})

    assert evidence.get("source") == "交易所交易日历"
    assert evidence.get("verified_by") == "host"
    assert evidence.get("verified_at") == "2026-09-28"


def test_schema_version_bumped():
    """测试 schema 版本已升级"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    # PR-C6 应 bump 到 v2
    assert pool.get("schema") == "fm.covariate_pool.v2"
    assert pool.get("updated") == "2026-09-28"


def test_horizon_known_distribution():
    """测试 horizon_known 分布合理"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    covariates = pool.get("covariates", {})

    counts = {}
    for cov_config in covariates.values():
        hk = cov_config.get("horizon_known", "unknown")
        counts[hk] = counts.get(hk, 0) + 1

    # 应有至少 1 个 known_ahead（calendar_cyclical）
    assert counts.get("known_ahead", 0) >= 1
    # 应有多个 self_referential（价格衍生类）
    assert counts.get("self_referential", 0) >= 10
    # 应有多个 unknowable（库存/基差类）
    assert counts.get("unknowable", 0) >= 5


def test_no_persistence_in_current_pool():
    """测试当前协变量池无 persistence 分类（设计选择）"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    covariates = pool.get("covariates", {})

    # 当前所有协变量要么是 known_ahead / self_referential / unknowable
    # persistence 是预留分类，当前未使用
    for cov_name, cov_config in covariates.items():
        hk = cov_config.get("horizon_known")
        assert hk != "persistence", (
            f"{cov_name} 不应标为 persistence（当前设计选择）"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
