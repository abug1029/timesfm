"""T7: 板块部分退化 WARN 测试

PR-B6 评审建议: n_failed >= sector_size * 0.5 时打 WARN，
用于预警「板块部分退化」（当前 circuit-breaker 是二元 block/pass，无预警能力）。
"""
import pytest
import logging
from unittest import mock


def test_sector_partial_degradation_warn(caplog):
    """T7: 当板块失败数 >= 50% 但未达 100% 时，应打 WARN"""
    from scripts.praxist_supervisor import _sector_filter_check

    # 构造 snapshot: black_metals 板块有 4 个品种 (rb, i, jm, ss)
    # 让 2 个失败 (50% >= 50%)，2 个成功
    snapshot = {
        "rb_rsi": {
            "symbol": "rb", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
        "i_rsi": {
            "symbol": "i", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
        "jm_rsi": {
            "symbol": "jm", "cov_override": "rsi", "status": "ok",
            "gate_pass": True, "decided_at": "2026-09-28T10:00:00"
        },
        "ss_rsi": {
            "symbol": "ss", "cov_override": "rsi", "status": "ok",
            "gate_pass": True, "decided_at": "2026-09-28T10:00:00"
        },
    }

    with caplog.at_level(logging.WARNING):
        blocked, sector, n_failed = _sector_filter_check("rb", snapshot)

    # 不应拦截（还有 2 个成功）
    assert not blocked, "Should not block when 2/4 symbols pass"
    assert sector == "black_metals"
    assert n_failed == 2

    # 应打 WARN（2/4 = 50% >= 50%）
    assert any("Sector partial degradation" in record.message for record in caplog.records), \
        "Should log warning for partial sector degradation"
    assert any("black_metals" in record.message for record in caplog.records), \
        "Warning should mention the sector name"


def test_sector_full_failure_no_warn(caplog):
    """T7: 当板块全部失败（触发 circuit-breaker）时，不打 WARN（直接拦截）"""
    from scripts.praxist_supervisor import _sector_filter_check

    # 构造 snapshot: black_metals 板块 4 个品种全失败
    snapshot = {
        "rb_rsi": {
            "symbol": "rb", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
        "i_rsi": {
            "symbol": "i", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
        "jm_rsi": {
            "symbol": "jm", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
        "ss_rsi": {
            "symbol": "ss", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
    }

    with caplog.at_level(logging.WARNING):
        blocked, sector, n_failed = _sector_filter_check("rb", snapshot)

    # 应拦截（全部失败）
    assert blocked, "Should block when all symbols fail"
    assert n_failed == 4

    # 不打 WARN（直接拦截，无需预警）
    assert not any("Sector partial degradation" in record.message for record in caplog.records), \
        "Should not log partial degradation warning when fully blocked"


def test_sector_below_threshold_no_warn(caplog):
    """T7: 当板块失败数 < 50% 时，不打 WARN"""
    from scripts.praxist_supervisor import _sector_filter_check

    # 构造 snapshot: black_metals 板块 4 个品种，1 个失败 (25% < 50%)
    snapshot = {
        "rb_rsi": {
            "symbol": "rb", "cov_override": "rsi", "status": "ok",
            "gate_pass": False, "decided_at": "2026-09-28T10:00:00"
        },
        "i_rsi": {
            "symbol": "i", "cov_override": "rsi", "status": "ok",
            "gate_pass": True, "decided_at": "2026-09-28T10:00:00"
        },
        "jm_rsi": {
            "symbol": "jm", "cov_override": "rsi", "status": "ok",
            "gate_pass": True, "decided_at": "2026-09-28T10:00:00"
        },
        "ss_rsi": {
            "symbol": "ss", "cov_override": "rsi", "status": "ok",
            "gate_pass": True, "decided_at": "2026-09-28T10:00:00"
        },
    }

    with caplog.at_level(logging.WARNING):
        blocked, sector, n_failed = _sector_filter_check("rb", snapshot)

    # 不应拦截
    assert not blocked
    assert n_failed == 1

    # 不打 WARN（1/4 = 25% < 50%）
    assert not any("Sector partial degradation" in record.message for record in caplog.records), \
        "Should not log warning when failure rate < 50%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
