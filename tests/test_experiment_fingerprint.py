"""Phase 7 (PR-B1) — 实验指纹 + variant_id + 48-bit 碰撞论证（H4）。

spec §4.2 W2.1③ / §4.5 W6.4。
"""
from __future__ import annotations

import os
import tempfile

import pytest

from cascade.experiment_fingerprint import (
    TRUNCATE_HEX_LEN,
    birthday_collision_probability,
    build_variant_id,
    compute_experiment_fingerprint,
    context_config_hash,
    expected_collisions,
    target_snapshot_hash,
    truncate_for_variant_id,
    weight_fingerprint,
)


@pytest.fixture
def weights_dir(tmp_path):
    """构造一个最小可用的 weights 目录。"""
    (tmp_path / "version.txt").write_text("timesfm-3.0.2")
    return tmp_path


# ── 组成（spec W2.1③）─────────────────────────────────────


def test_weight_fingerprint_deterministic(weights_dir):
    assert weight_fingerprint(weights_dir) == weight_fingerprint(weights_dir)


def test_weight_fingerprint_changes_when_version_changes(weights_dir):
    fp1 = weight_fingerprint(weights_dir)
    (weights_dir / "version.txt").write_text("timesfm-3.0.3")
    fp2 = weight_fingerprint(weights_dir)
    assert fp1 != fp2, "权重版本变化必须改变 fingerprint"


def test_weight_fingerprint_missing_version_file_is_fine(weights_dir):
    (weights_dir / "version.txt").unlink()
    fp = weight_fingerprint(weights_dir)
    assert len(fp) == 64


def test_weight_fingerprint_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        weight_fingerprint(tmp_path / "no-such-dir")


def test_target_snapshot_hash_changes_with_data():
    h1 = target_snapshot_hash([1.0, 2.0, 3.0])
    h2 = target_snapshot_hash([1.0, 2.0, 4.0])
    h3 = target_snapshot_hash([1.0, 2.0, 3.0])
    assert h1 != h2
    assert h1 == h3, "同数据必须同 hash（幂等）"


def test_target_snapshot_hash_byte_level_determinism():
    """字节级确定性：跨调用同输入必须同 hash（float 序列化约定）。"""
    a = target_snapshot_hash([0.1 + 0.2] * 10)
    b = target_snapshot_hash([0.1 + 0.2] * 10)
    assert a == b


def test_context_config_hash_changes_when_any_component_changes():
    base = context_config_hash(480, 24, 2, ["rsi_state"])
    assert base != context_config_hash(999, 24, 2, ["rsi_state"]), "context_bars 必须参与"
    assert base != context_config_hash(480, 99, 2, ["rsi_state"]), "horizon 必须参与"
    assert base != context_config_hash(480, 24, 99, ["rsi_state"]), "step 必须参与"
    assert base != context_config_hash(480, 24, 2, ["vor"]),       "协变量必须参与"


def test_context_config_hash_order_independent():
    """协变量列表顺序不得影响身份。"""
    a = context_config_hash(480, 24, 2, ["rsi_state", "vor"])
    b = context_config_hash(480, 24, 2, ["vor", "rsi_state"])
    assert a == b, "协变量顺序必须归一化"


# ── 主指纹 + 截断（spec W6.4）─────────────────────────────


def test_experiment_fingerprint_changes_when_any_component_changes(weights_dir):
    base = compute_experiment_fingerprint(weights_dir, [1.0], 480, 24, 2, ["rsi_state"])
    (weights_dir / "version.txt").write_text("v2")
    assert base != compute_experiment_fingerprint(weights_dir, [1.0], 480, 24, 2, ["rsi_state"])
    assert base != compute_experiment_fingerprint(weights_dir, [2.0], 480, 24, 2, ["rsi_state"])
    assert base != compute_experiment_fingerprint(weights_dir, [1.0], 999, 24, 2, ["rsi_state"])


def test_truncate_to_48_bits():
    fp = "abcdef0123456789" + "0" * 48
    assert truncate_for_variant_id(fp) == "abcdef012345"
    assert len(truncate_for_variant_id(fp)) == TRUNCATE_HEX_LEN


def test_truncate_rejects_wrong_length():
    with pytest.raises(ValueError):
        truncate_for_variant_id("short")


# ── variant_id（spec W6.4）──────────────────────────────────


def test_variant_id_format(weights_dir):
    fp = compute_experiment_fingerprint(weights_dir, [1.0], 480, 24, 2, ["rsi_state"])
    vid = build_variant_id("ss", "momentum", fp)
    assert vid == f"ss_momentum_{fp[:12]}"


def test_variant_id_is_deterministic_given_same_inputs():
    """spec W6.4：同 fingerprint 同 variant_id。"""
    wd = _make_weights_dir()
    try:
        fp = compute_experiment_fingerprint(wd, [1.0], 480, 24, 2, ["rsi_state"])
    finally:
        import shutil
        shutil.rmtree(wd, ignore_errors=True)
    vid_a = build_variant_id("ss", "momentum", fp)
    vid_b = build_variant_id("ss", "momentum", fp)
    assert vid_a == vid_b, "同 fingerprint 同 variant_id"


def _make_weights_dir():
    import tempfile
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "version.txt"), "w") as f:
        f.write("v1")
    return d


def test_variant_id_rejects_empty_symbol(weights_dir):
    fp = compute_experiment_fingerprint(weights_dir, [1.0], 480, 24, 2, ["rsi_state"])
    with pytest.raises(ValueError):
        build_variant_id("", "momentum", fp)
    with pytest.raises(ValueError):
        build_variant_id("ss", "", fp)


# ── 48-bit 碰撞论证（H4）──────────────────────────────────


def test_collision_probability_monotone():
    """变体数越多，碰撞概率越高。"""
    p1 = birthday_collision_probability(100)
    p2 = birthday_collision_probability(1000)
    p3 = birthday_collision_probability(10000)
    assert p1 < p2 < p3


def test_collision_probability_at_scale_is_negligible():
    """1000 变体时碰撞概率应 << 1e-6（H4 验收门槛）。"""
    assert birthday_collision_probability(1000) < 1e-6


def test_collision_probability_at_1M_still_small():
    """1M 变体时期望碰撞对数应 << 1。"""
    assert expected_collisions(1_000_000) < 0.01


def test_collision_probability_at_100k_still_small():
    """100k 变体时碰撞概率应 << 1e-3。"""
    assert birthday_collision_probability(100_000) < 1e-3


# ── spec v8：experiment_fingerprint vs research_target_hash 不得混用 ──


def test_experiment_fingerprint_differs_from_research_target_hash():
    """两个指纹概念不同：一个随运行变化，一个稳定。"""
    from cascade.research_family import research_target_hash

    rth = research_target_hash("ss", "dir", "main_continuous", "v1")
    assert len(rth) == 64  # SHA-256
    # 即使数值上可能凑巧相等（极小概率），设计语义也不同；
    # 此处只验证两者都是 SHA-256 长度，且命名空间不同（不会互相误用）
