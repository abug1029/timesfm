"""PR-A1 验证: 协议指纹包含 cutoff 约定（D5 修复）"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_FM.evaluations.fm_eval.evaluator import (
    compute_protocol_fingerprint,
    PROTOCOL_FINGERPRINT_VERSION
)


def test_protocol_fingerprint_version_is_v4():
    """PR-A1 → PR-A5 → v4 收口：协议指纹版本应为 v4（窗口锚语义入指纹）。

    v2 加入 cutoff_convention (D5)；v3 补齐 spec 七组件表（H3 / PR-A5）；
    v4 加入 window_anchor（发现 B：窗口随数据末端滑动 → resume 混窗）。
    """
    assert PROTOCOL_FINGERPRINT_VERSION == "protocol_v4"


def test_protocol_fingerprint_includes_cutoff_convention():
    """PR-A1: 协议指纹应包含 cutoff 约定"""
    fp_open = compute_protocol_fingerprint(cutoff_convention="bar_open")
    fp_close = compute_protocol_fingerprint(cutoff_convention="bar_close")

    # 不同的 cutoff 约定应产生不同的指纹
    assert fp_open != fp_close, "cutoff_convention 未影响协议指纹"


def test_protocol_fingerprint_default_is_bar_close():
    """PR-A1: 默认 cutoff 约定应为 bar_close（D5 修复后）"""
    fp_default = compute_protocol_fingerprint()
    fp_close = compute_protocol_fingerprint(cutoff_convention="bar_close")

    # 默认值应与 bar_close 相同
    assert fp_default == fp_close, "默认 cutoff_convention 不是 bar_close"


def test_protocol_fingerprint_deterministic():
    """PR-A1: 协议指纹应是确定性的"""
    fp1 = compute_protocol_fingerprint(cutoff_convention="bar_close")
    fp2 = compute_protocol_fingerprint(cutoff_convention="bar_close")

    assert fp1 == fp2, "协议指纹非确定性"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
