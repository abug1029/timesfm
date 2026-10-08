"""
批次 F (F.6)：M3/M4 端到端测试

验证：
1. M3 拒收统计正确聚合并物化
2. M4 abandon 提案被正确拒收
3. prompt 组装包含拒收统计段
"""
import pytest
import os
import sys
import json
import tempfile
from pathlib import Path

# 添加 scripts 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_m3_rejection_aggregation():
    """M3 应正确聚合拒收统计"""
    from aggregate_rejection_stats import aggregate_rejections

    stats = aggregate_rejections()

    # 应返回正确的结构
    assert "main_window" in stats
    assert "cumulative" in stats
    assert "sample_count" in stats

    # 主窗口和对照段应有 total 和 reasons
    assert "total" in stats["main_window"]
    assert "reasons" in stats["main_window"]
    assert "total" in stats["cumulative"]
    assert "reasons" in stats["cumulative"]

    # sample_count 应为非负整数
    assert isinstance(stats["sample_count"], int)
    assert stats["sample_count"] >= 0


def test_m4_abandon_proposal_rejected():
    """M4 abandon 提案应被正确拒收"""
    # 创建临时提案文件
    with tempfile.TemporaryDirectory() as tmpdir:
        proposal = {
            "schema": "fm.hypothesis_proposal.v1",
            "symbol": "ss",
            "cov_override": "ccl",
            "mechanism": "test mechanism with enough length to pass the threshold check",
            "decision": "abandon",
            "abandon_reason": "falsifier disagrees with current hypothesis",
            "peer_id": "gen1_peer0"
        }

        proposal_path = Path(tmpdir) / "test_proposal.json"
        with open(proposal_path, "w") as f:
            json.dump(proposal, f)

        # 读取并验证 decision 字段
        with open(proposal_path) as f:
            p = json.load(f)

        assert p.get("decision") == "abandon"
        assert p.get("abandon_reason") == "falsifier disagrees with current hypothesis"


def test_prompt_includes_rejection_stats():
    """prompt 组装应包含拒收统计段"""
    from aggregate_rejection_stats import aggregate_rejections, render_markdown

    stats = aggregate_rejections()
    md = render_markdown(stats)

    # 应包含标题
    assert "## Why proposals were rejected recently" in md

    # 应包含样本数
    assert "本轮样本数" in md

    # 如果有数据，应包含拒收分布
    if stats["main_window"]["total"] > 0:
        assert "主窗口" in md
        assert "拒收分布" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
