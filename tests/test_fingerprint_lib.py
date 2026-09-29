"""指纹系统单元测试（PR-B1）"""

import pytest
import tempfile
from pathlib import Path
from scripts.fingerprint_lib import (
    compute_cov_config_fingerprint,
    compute_protocol_config_fingerprint,
    compute_weight_fingerprint,
    compute_seed_fingerprint,
    compute_variant_id,
    _canonical_serialize,
    _compute_sha256
)


class TestCanonicalSerialize:
    """测试规范序列化"""

    def test_dict_sorted_by_keys(self):
        """dict 按键排序"""
        obj = {"b": 2, "a": 1, "c": 3}
        result = _canonical_serialize(obj)
        # JSON dumps 时按键排序
        keys = list(result.keys())
        assert keys == ["a", "b", "c"]

    def test_nan_to_string(self):
        """NaN 转为字符串"""
        obj = {"value": float('nan')}
        result = _canonical_serialize(obj)
        assert result["value"] == "<NaN>"

    def test_inf_raises_error(self):
        """Inf 抛 ValueError"""
        obj = {"value": float('inf')}
        with pytest.raises(ValueError, match="Infinite values not allowed"):
            _canonical_serialize(obj)

    def test_negative_inf_raises_error(self):
        """-Inf 抛 ValueError"""
        obj = {"value": float('-inf')}
        with pytest.raises(ValueError, match="Infinite values not allowed"):
            _canonical_serialize(obj)

    def test_nested_dict(self):
        """嵌套 dict 递归处理"""
        obj = {"outer": {"b": 2, "a": 1}}
        result = _canonical_serialize(obj)
        inner_keys = list(result["outer"].keys())
        assert inner_keys == ["a", "b"]

    def test_list_processing(self):
        """list 递归处理"""
        obj = {"items": [1, 2, float('nan')]}
        result = _canonical_serialize(obj)
        assert result["items"][2] == "<NaN>"


class TestComputeSha256:
    """测试 SHA-256 计算"""

    def test_deterministic(self):
        """相同输入相同输出"""
        data = "test data"
        hash1 = _compute_sha256(data)
        hash2 = _compute_sha256(data)
        assert hash1 == hash2

    def test_16_hex_chars(self):
        """返回 16 位十六进制"""
        hash_val = _compute_sha256("test")
        assert len(hash_val) == 16
        # 验证是十六进制
        int(hash_val, 16)

    def test_different_input_different_hash(self):
        """不同输入不同哈希"""
        hash1 = _compute_sha256("data1")
        hash2 = _compute_sha256("data2")
        assert hash1 != hash2


class TestComputeCovFingerprint:
    """测试协变量配置指纹"""

    def test_basic(self):
        """基本功能"""
        config = {"covariate_type": "rsi_state", "horizon": 24}
        result = compute_cov_config_fingerprint(config)

        assert "keys_sha256" in result
        assert "n_channels" in result
        assert "hash_version" in result
        assert result["hash_version"] == "v1"
        assert result["n_channels"] == 1  # 默认值

    def test_nan_handling(self):
        """NaN 处理"""
        config = {"value": float('nan'), "type": "test"}
        result = compute_cov_config_fingerprint(config)
        # 应该成功，NaN 被转为字符串
        assert "keys_sha256" in result

    def test_inf_rejects(self):
        """Inf 拒绝"""
        config = {"value": float('inf')}
        with pytest.raises(ValueError):
            compute_cov_config_fingerprint(config)

    def test_deterministic(self):
        """确定性"""
        config = {"type": "rsi_state", "horizon": 24}
        result1 = compute_cov_config_fingerprint(config)
        result2 = compute_cov_config_fingerprint(config)
        assert result1["keys_sha256"] == result2["keys_sha256"]

    def test_different_order_same_hash(self):
        """不同顺序相同哈希"""
        config1 = {"a": 1, "b": 2}
        config2 = {"b": 2, "a": 1}
        result1 = compute_cov_config_fingerprint(config1)
        result2 = compute_cov_config_fingerprint(config2)
        # 应该相同，因为规范序列化会按键排序
        assert result1["keys_sha256"] == result2["keys_sha256"]

    def test_custom_n_channels(self):
        """自定义通道数"""
        config = {"type": "test", "n_channels": 3}
        result = compute_cov_config_fingerprint(config)
        assert result["n_channels"] == 3


class TestComputeProtocolFingerprint:
    """测试协议配置指纹"""

    def test_basic(self):
        """基本功能"""
        config = {"min_n": 350, "min_ic": 0.05, "stage": "aligned"}
        result = compute_protocol_config_fingerprint(config)

        assert "protocol_sha256" in result
        assert "hash_version" in result
        assert result["hash_version"] == "v1"

    def test_deterministic(self):
        """确定性"""
        config = {"min_n": 350}
        result1 = compute_protocol_config_fingerprint(config)
        result2 = compute_protocol_config_fingerprint(config)
        assert result1["protocol_sha256"] == result2["protocol_sha256"]

    def test_inf_rejects(self):
        """Inf 拒绝"""
        config = {"value": float('inf')}
        with pytest.raises(ValueError):
            compute_protocol_config_fingerprint(config)


class TestComputeWeightFingerprint:
    """测试模型权重指纹"""

    def test_basic(self):
        """基本功能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test data 1")
            (weights_dir / "model.bin").write_bytes(b"test data 2")

            result = compute_weight_fingerprint(str(weights_dir))

            assert "weights_sha256" in result
            assert "n_files" in result
            assert result["n_files"] == 2

    def test_directory_not_found(self):
        """目录不存在"""
        with pytest.raises(FileNotFoundError):
            compute_weight_fingerprint("/nonexistent/path")

    def test_no_model_files(self):
        """无模型文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "readme.txt").write_text("not a model")

            with pytest.raises(FileNotFoundError, match="No model files found"):
                compute_weight_fingerprint(str(weights_dir))

    def test_tail_change_detected_same_size(self):
        """PR-B1 评审修复: 文件大小不变、仅尾部变化也必须检出。

        原实现只哈希前 4KB + 文件大小，对"仅末层权重变化"的重训练
        会给出相同指纹 → 不同模型被误判为同一实验（假去重）。
        """
        head = b"H" * 8192          # 前 8KB 完全相同（远超原 4KB 窗口）
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "model.safetensors").write_bytes(head + b"A" * 4096)
            fp1 = compute_weight_fingerprint(str(d))["weights_sha256"]

            # 同样大小，仅尾部不同
            (d / "model.safetensors").write_bytes(head + b"B" * 4096)
            fp2 = compute_weight_fingerprint(str(d))["weights_sha256"]

            assert fp1 != fp2, "尾部变化未被检出（仍在截断哈希）"

    def test_identical_files_same_fingerprint(self):
        """内容相同 → 指纹相同（防止修复引入随机性）"""
        payload = b"X" * 10000
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "model.safetensors").write_bytes(payload)
            fp1 = compute_weight_fingerprint(str(d))["weights_sha256"]
            fp2 = compute_weight_fingerprint(str(d))["weights_sha256"]
            assert fp1 == fp2

    def test_deterministic(self):
        """确定性"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test data")

            result1 = compute_weight_fingerprint(str(weights_dir))
            result2 = compute_weight_fingerprint(str(weights_dir))
            assert result1["weights_sha256"] == result2["weights_sha256"]

    def test_different_content_different_hash(self):
        """不同内容不同哈希"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir1 = Path(tmpdir) / "dir1"
            weights_dir1.mkdir()
            (weights_dir1 / "model.safetensors").write_bytes(b"data 1")

            weights_dir2 = Path(tmpdir) / "dir2"
            weights_dir2.mkdir()
            (weights_dir2 / "model.safetensors").write_bytes(b"data 2")

            result1 = compute_weight_fingerprint(str(weights_dir1))
            result2 = compute_weight_fingerprint(str(weights_dir2))
            assert result1["weights_sha256"] != result2["weights_sha256"]


class TestComputeSeedFingerprint:
    """测试随机种子指纹"""

    def test_basic(self):
        """基本功能"""
        result = compute_seed_fingerprint(42)

        assert result["seed"] == 42
        assert "seed_sha256" in result
        assert result["hash_version"] == "v1"

    def test_deterministic(self):
        """确定性"""
        result1 = compute_seed_fingerprint(42)
        result2 = compute_seed_fingerprint(42)
        assert result1["seed_sha256"] == result2["seed_sha256"]

    def test_different_seeds_different_hash(self):
        """不同种子不同哈希"""
        result1 = compute_seed_fingerprint(42)
        result2 = compute_seed_fingerprint(43)
        assert result1["seed_sha256"] != result2["seed_sha256"]

    def test_invalid_type(self):
        """无效类型"""
        with pytest.raises(TypeError):
            compute_seed_fingerprint("not an int")


class TestComputeVariantId:
    """测试 variant_id 计算"""

    def test_basic_with_fingerprint(self):
        """基本功能（带指纹）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test")

            cov_config = {"type": "rsi_state"}
            protocol_config = {"min_n": 350}

            vid, fingerprints = compute_variant_id(
                "ss", "rsi_state", cov_config, protocol_config, str(weights_dir)
            )

            # 应该包含指纹
            assert "cov_" in vid
            assert "proto_" in vid
            assert "wt_" in vid
            assert fingerprints is not None
            assert "cov_fingerprint" in fingerprints

    def test_with_seed(self):
        """带种子"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test")

            cov_config = {"type": "test"}
            protocol_config = {"min_n": 350}

            vid, fingerprints = compute_variant_id(
                "ss", "test", cov_config, protocol_config, str(weights_dir), seed=42
            )

            assert "seed_" in vid
            assert fingerprints["seed_fingerprint"] is not None

    def test_raises_on_error_fail_loud(self):
        """spec W6.4 fail-loud：错误时必须抛出，不得静默回退。

        H3 移除了 silent fallback。此测试验证 fail-loud 契约。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            # 不创建模型文件，会触发 FileNotFoundError

            import pytest
            with pytest.raises(FileNotFoundError):
                compute_variant_id(
                    "ss", "test",
                    {"type": "test"}, {"min_n": 350},
                    str(weights_dir)
                )

    def test_different_configs_different_vid(self):
        """不同配置不同 variant_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_dir = Path(tmpdir)
            (weights_dir / "model.safetensors").write_bytes(b"test")

            protocol_config = {"min_n": 350}

            vid1, _ = compute_variant_id(
                "ss", "test", {"type": "rsi"}, protocol_config, str(weights_dir)
            )
            vid2, _ = compute_variant_id(
                "ss", "test", {"type": "oi"}, protocol_config, str(weights_dir)
            )

            assert vid1 != vid2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
