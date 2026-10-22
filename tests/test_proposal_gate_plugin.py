"""Tests for proposal_gate plugin (Task 1-3 A2)."""
import json
import os
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "task_FM", ".praxist", "plugins"))

from proposal_gate.validate import validate_proposal


def _valid_proposal(**overrides):
    p = {
        "symbol": "m",
        "cov_override": "vol",
        "mechanism": "volatility drives price through liquidity gaps",
        "symbol_fit": "m is a liquid commodity future",
        "predicted_direction": "up",
    }
    p.update(overrides)
    return p


class TestValidProposal:
    def test_passes(self):
        result = validate_proposal(_valid_proposal(variant_id="m_vol_001"))
        assert result["valid"] is True

    def test_without_variant_id_passes(self):
        result = validate_proposal(_valid_proposal())
        assert result["valid"] is True


class TestInvalidProposal:
    def test_missing_fields_rejected_with_signal(self):
        result = validate_proposal({"variant_id": "v2"})
        assert result["valid"] is False
        assert "validation_signal" in result
        assert any("missing_required" in e for e in result["validation_signal"]["errors"])

    def test_chinese_field_rejected(self):
        result = validate_proposal(_valid_proposal(mechanism="测试机制"))
        assert result["valid"] is False
        assert result["reason"] == "chinese_field:mechanism"


class TestLayaProhibitedWords:
    def test_laya_prohibited_word_rejected(self):
        # Use notes (not in CHINESE_GATED_FIELDS) to isolate R5 from chinese_field gate
        result = validate_proposal(_valid_proposal(
            notes="训练 Laya 提升预测"
        ))
        assert result["valid"] is False
        assert any("laya_prohibited_word" in e for e in result["validation_signal"]["errors"])

    def test_不可学习_not_rejected(self):
        """「不可学习」不应触发 R5 — 负向先行断言 (?<!不) 排除"""
        result = validate_proposal(_valid_proposal(
            notes="该系统不可学习但Laya可以判断"
        ))
        assert result["valid"] is True

    def test_laya_in_nested_field(self):
        result = validate_proposal(_valid_proposal(
            notes="这是可学习Laya的系统"  # 绑定 Laya 上下文
        ))
        assert result["valid"] is False
        assert any("laya_prohibited_word" in e for e in result["validation_signal"]["errors"])


class TestStemVariantIdConsistency:
    def test_matching_stem_passes(self):
        result = validate_proposal(_valid_proposal(variant_id="m_vol_001"))
        assert result["valid"] is True

    def test_mismatching_stem_rejected(self):
        result = validate_proposal(_valid_proposal(variant_id="rb_oi_001"))
        assert result["valid"] is False
        assert any("variant_id_mismatch" in e for e in result["validation_signal"]["errors"])


class TestValidationSignalPersistence:
    def test_signal_written_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            signal_path = os.path.join(tmpdir, "validation_signals.jsonl")
            # Monkey-patch the signal path
            import proposal_gate.validate as mod
            orig = mod.VALIDATION_SIGNAL_PATH
            mod.VALIDATION_SIGNAL_PATH = signal_path
            try:
                validate_proposal({"variant_id": "test_sig"})
                assert os.path.exists(signal_path)
                with open(signal_path) as f:
                    line = f.readline()
                record = json.loads(line)
                assert record["variant_id"] == "test_sig"
                assert "errors" in record
                assert "timestamp" in record
            finally:
                mod.VALIDATION_SIGNAL_PATH = orig

    def test_valid_proposal_no_signal_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            signal_path = os.path.join(tmpdir, "validation_signals.jsonl")
            import proposal_gate.validate as mod
            orig = mod.VALIDATION_SIGNAL_PATH
            mod.VALIDATION_SIGNAL_PATH = signal_path
            try:
                validate_proposal(_valid_proposal(variant_id="m_vol_001"))
                assert not os.path.exists(signal_path)
            finally:
                mod.VALIDATION_SIGNAL_PATH = orig
