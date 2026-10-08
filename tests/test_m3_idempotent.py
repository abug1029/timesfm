"""
批次 F (F.5)：M3 物化幂等测试

验证：
1. 除 `generated_at` 外，两次物化结果字节一致
2. 主窗口和对照段均满足幂等
3. 日志轮转/截断时降级为空段
"""
import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path

# 添加 scripts 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_materialization_idempotent():
    """M3 物化应幂等（除 generated_at 外）"""
    from aggregate_rejection_stats import aggregate_rejections, render_markdown

    # 第一次物化
    stats1 = aggregate_rejections()
    md1 = render_markdown(stats1)

    # 第二次物化
    stats2 = aggregate_rejections()
    md2 = render_markdown(stats2)

    # 移除 generated_at 行后应完全一致
    def remove_generated_at(md):
        lines = md.split("\n")
        return "\n".join(line for line in lines if not line.startswith("_Generated at:"))

    assert remove_generated_at(md1) == remove_generated_at(md2), \
        "M3 物化不幂等：两次渲染结果不同（除 generated_at 外）"


def test_empty_log_degrades_gracefully():
    """日志不存在或为空时应降级为空段"""
    from aggregate_rejection_stats import aggregate_rejections, render_markdown, DECISIONS_LOG

    # 备份原始日志
    if os.path.exists(DECISIONS_LOG):
        backup = DECISIONS_LOG + ".backup"
        shutil.copy(DECISIONS_LOG, backup)
        try:
            # 删除日志
            os.remove(DECISIONS_LOG)

            # 应降级为空段
            stats = aggregate_rejections()
            assert stats["main_window"]["total"] == 0
            assert stats["cumulative"]["total"] == 0
            assert stats["sample_count"] == 0

            md = render_markdown(stats)
            assert "本轮无拒收记录" in md
        finally:
            # 恢复日志
            shutil.move(backup, DECISIONS_LOG)
    else:
        # 日志本就不存在
        stats = aggregate_rejections()
        assert stats["main_window"]["total"] == 0
        assert stats["cumulative"]["total"] == 0


def test_cumulative_segment_included():
    """对照段应包含在输出中"""
    from aggregate_rejection_stats import aggregate_rejections, render_markdown

    stats = aggregate_rejections()
    md = render_markdown(stats)

    # 对照段应存在
    assert "跨轮累计" in md or "本轮无拒收记录" in md

    # 如果有数据，对照段应显示 since 时间
    if stats["cumulative"]["total"] > 0:
        assert "since" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
