"""指纹去重逻辑测试（PR-B1）"""

import pytest
import tempfile
from pathlib import Path
from scripts.fingerprint_lib import compute_variant_id


class TestVariantIdDedup:
    """测试 variant_id 去重逻辑"""

    def test_same_config_same_vid(self):
        """相同配置生成相同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            cov_config = {"type": "rsi_state", "horizon": 24}
            protocol_config = {"min_n": 350, "stage": "aligned"}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config, str(weights_dir)
            )

            assert vid1 == vid2

    def test_different_cov_config_different_vid(self):
        """不同协变量配置生成不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            protocol_config = {"min_n": 350}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", {"type": "rsi", "horizon": 24},
                protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state", {"type": "rsi", "horizon": 48},
                protocol_config, str(weights_dir)
            )

            assert vid1 != vid2

    def test_different_protocol_config_different_vid(self):
        """不同协议配置生成不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            cov_config = {"type": "rsi_state"}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", cov_config,
                {"min_n": 350}, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state", cov_config,
                {"min_n": 400}, str(weights_dir)
            )

            assert vid1 != vid2

    def test_different_weights_different_vid(self):
        """不同权重生成不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir1 = Path(tmpdir) / "dir1"
            weights_dir1.mkdir()
            (weights_dir1 / "model.safetensors").write_bytes(b"weights v1")

            weights_dir2 = Path(tmpdir) / "dir2"
            weights_dir2.mkdir()
            (weights_dir2 / "model.safetensors").write_bytes(b"weights v2")

            cov_config = {"type": "rsi_state"}
            protocol_config = {"min_n": 350}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config, str(weights_dir1)
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config, str(weights_dir2)
            )

            assert vid1 != vid2

    def test_different_symbol_different_vid(self):
        """不同品种生成不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            cov_config = {"type": "rsi_state"}
            protocol_config = {"min_n": 350}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "rb", "rsi_state", cov_config, protocol_config, str(weights_dir)
            )

            assert vid1 != vid2

    def test_different_cov_different_vid(self):
        """不同协变量生成不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            protocol_config = {"min_n": 350}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", {"type": "rsi"},
                protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "oi", {"type": "oi"},
                protocol_config, str(weights_dir)
            )

            assert vid1 != vid2

    def test_different_seed_different_vid(self):
        """不同种子生成不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            cov_config = {"type": "rsi_state"}
            protocol_config = {"min_n": 350}

            vid1, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config,
                str(weights_dir), seed=42
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config,
                str(weights_dir), seed=43
            )

            assert vid1 != vid2

    def test_config_order_insensitive(self):
        """配置顺序不影响 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            protocol_config = {"min_n": 350}

            # 配置键顺序不同
            vid1, _ = compute_variant_id(
                "ss", "rsi_state",
                {"type": "rsi", "horizon": 24, "period": 14},
                protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state",
                {"period": 14, "type": "rsi", "horizon": 24},
                protocol_config, str(weights_dir)
            )

            # 应该相同
            assert vid1 == vid2

    def test_semantically_same_different_string_different_vid(self):
        """语义相同但字符串不同，variant_id 不同

        这是设计决策：字符串表示不同就视为不同实验。
        例如 "0.05" 和 "0.050" 虽然数值相同，但字符串不同，
        应该生成不同的 variant_id。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test weights")

            protocol_config = {"min_n": 350}

            # 字符串表示不同
            vid1, _ = compute_variant_id(
                "ss", "rsi_state",
                {"type": "rsi", "threshold": "0.05"},
                protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "rsi_state",
                {"type": "rsi", "threshold": "0.050"},
                protocol_config, str(weights_dir)
            )

            # 应该不同（字符串表示不同）
            assert vid1 != vid2


class TestVariantIdFormat:
    """测试 variant_id 格式"""

    def test_format_with_fingerprint(self):
        """带指纹的格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test")

            vid, _ = compute_variant_id(
                "ss", "rsi_state",
                {"type": "rsi"},
                {"min_n": 350},
                str(weights_dir)
            )

            # 应该包含指纹部分
            assert vid.startswith("ss_rsi_state_cov_")
            assert "_proto_" in vid
            assert "_wt_" in vid

    def test_format_with_seed(self):
        """带种子的格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test")

            vid, _ = compute_variant_id(
                "ss", "rsi_state",
                {"type": "rsi"},
                {"min_n": 350},
                str(weights_dir),
                seed=42
            )

            # 应该包含种子部分
            assert "_seed_" in vid

    def test_format_fallback(self):
        """回退格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            # 不创建模型文件，触发回退

            vid, fingerprints = compute_variant_id(
                "ss", "rsi_state",
                {"type": "rsi"},
                {"min_n": 350},
                str(weights_dir)
            )

            # 应该回退到简单格式
            assert vid == "ss_rsi_state"
            assert fingerprints is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
