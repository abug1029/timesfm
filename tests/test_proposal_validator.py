"""提案验证器测试。

覆盖:
  1. 有效提案通过验证
  2. 无效 JSON 被拒绝
  3. 缺少必填字段被拒绝
  4. 类型错误被拒绝
  5. 中文 mechanism 被拒绝
  6. 中文 symbol_fit 被拒绝
  7. 批量验证正确
  8. contains_chinese 函数正确性
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

from proposal_validator import (
    contains_chinese,
    validate_proposal,
    validate_proposal_dict,
)


def _make_proposal(**overrides):
    """构建最小有效提案。"""
    p = {
        "schema": "fm.hypothesis_proposal.v1",
        "symbol": "m",
        "cov_override": "vol",
        "mechanism": "volatility drives price changes through liquidity gaps",
        "symbol_fit": "fits commodity futures with high turnover",
        "predicted_direction": "up",
        "proposal_id": "test-001",
    }
    p.update(overrides)
    return p


class TestValidProposal:
    """有效提案通过验证。"""

    def test_valid_proposal(self):
        result = validate_proposal_dict(_make_proposal())
        assert result["valid"] is True
        assert result["errors"] == []

    def test_valid_with_extra_fields(self):
        result = validate_proposal_dict(_make_proposal(covariate_family="volatility"))
        assert result["valid"] is True


class TestInvalidJson:
    """无效 JSON 被拒绝。"""

    def test_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json", encoding="utf-8")
        result = validate_proposal(str(bad_file))
        assert result["valid"] is False
        assert any("unparseable_json" in e for e in result["errors"])

    def test_io_error(self):
        result = validate_proposal("/nonexistent/proposal.json")
        assert result["valid"] is False
        assert any("io_error" in e for e in result["errors"])


class TestMissingFields:
    """缺少必填字段被拒绝。"""

    def test_missing_symbol(self):
        result = validate_proposal_dict(_make_proposal(symbol=None))
        assert result["valid"] is False
        assert any("missing_required:symbol" in e for e in result["errors"])

    def test_missing_cov_override(self):
        result = validate_proposal_dict(_make_proposal(cov_override=None))
        assert result["valid"] is False
        assert any("missing_required:cov_override" in e for e in result["errors"])

    def test_missing_mechanism(self):
        result = validate_proposal_dict(_make_proposal(mechanism=None))
        assert result["valid"] is False
        assert any("missing_required:mechanism" in e for e in result["errors"])

    def test_missing_predicted_direction(self):
        result = validate_proposal_dict(_make_proposal(predicted_direction=None))
        assert result["valid"] is False
        assert any("missing_required:predicted_direction" in e for e in result["errors"])

    def test_multiple_missing_fields(self):
        result = validate_proposal_dict({})
        assert result["valid"] is False
        assert len(result["errors"]) == 5


class TestTypeErrors:
    """类型错误被拒绝。"""

    def test_symbol_as_int(self):
        result = validate_proposal_dict(_make_proposal(symbol=123))
        assert result["valid"] is False
        assert any("type_error:symbol" in e for e in result["errors"])

    def test_cov_override_as_list(self):
        result = validate_proposal_dict(_make_proposal(cov_override=["vol"]))
        assert result["valid"] is False
        assert any("type_error:cov_override" in e for e in result["errors"])

    def test_predicted_direction_as_int(self):
        result = validate_proposal_dict(_make_proposal(predicted_direction=1))
        assert result["valid"] is False
        assert any("type_error:predicted_direction" in e for e in result["errors"])

    def test_mechanism_as_dict(self):
        result = validate_proposal_dict(_make_proposal(mechanism={"text": "x"}))
        assert result["valid"] is False
        assert any("type_error:mechanism" in e for e in result["errors"])


class TestChineseDetection:
    """中英门禁：中文字段被拒绝。"""

    def test_chinese_mechanism(self):
        result = validate_proposal_dict(
            _make_proposal(mechanism="波动率通过流动性缺口驱动价格变化")
        )
        assert result["valid"] is False
        assert any("chinese_field:mechanism" in e for e in result["errors"])

    def test_chinese_symbol_fit(self):
        result = validate_proposal_dict(
            _make_proposal(symbol_fit="适合高换手率商品期货")
        )
        assert result["valid"] is False
        assert any("chinese_field:symbol_fit" in e for e in result["errors"])

    def test_english_mechanism_passes(self):
        result = validate_proposal_dict(
            _make_proposal(mechanism="Volatility drives price through liquidity")
        )
        assert result["valid"] is True
        assert not any("chinese_field" in e for e in result["errors"])

    def test_mixed_chinese_and_english(self):
        result = validate_proposal_dict(
            _make_proposal(mechanism="volatility 波动率 drives price")
        )
        assert result["valid"] is False
        assert any("chinese_field:mechanism" in e for e in result["errors"])


class TestContainsChinese:
    """contains_chinese 函数正确性。"""

    def test_pure_english(self):
        assert contains_chinese("hello world") is False

    def test_pure_chinese(self):
        assert contains_chinese("你好世界") is True

    def test_mixed(self):
        assert contains_chinese("hello 世界") is True

    def test_empty_string(self):
        assert contains_chinese("") is False

    def test_punctuation_only(self):
        assert contains_chinese("...") is False

    def test_chinese_punctuation(self):
        assert contains_chinese("。") is True

    def test_fullwidth_chars(self):
        assert contains_chinese("！＠＃") is True


class TestBatchValidation:
    """批量验证。"""

    def test_batch_all_valid(self, tmp_path):
        proposals_dir = tmp_path / "task_FM" / "experiments" / "run_test" / "results" / "peer0" / "proposals"
        proposals_dir.mkdir(parents=True)

        for i in range(3):
            p = _make_proposal(proposal_id="test-%d" % i)
            (proposals_dir / ("prop%d.json" % i)).write_text(
                json.dumps(p), encoding="utf-8"
            )

        from validate_all_proposals import scan_proposals, validate_all

        files = scan_proposals(str(tmp_path))
        assert len(files) == 3

        results = validate_all(files)
        assert len(results) == 3
        assert all(r["valid"] for r in results)

    def test_batch_mixed(self, tmp_path):
        proposals_dir = tmp_path / "task_FM" / "experiments" / "run_test" / "results" / "peer0" / "proposals"
        proposals_dir.mkdir(parents=True)

        # valid
        (proposals_dir / "good.json").write_text(
            json.dumps(_make_proposal()), encoding="utf-8"
        )
        # invalid JSON
        (proposals_dir / "bad.json").write_text("{bad", encoding="utf-8")
        # missing fields
        (proposals_dir / "empty.json").write_text("{}", encoding="utf-8")

        from validate_all_proposals import scan_proposals, validate_all

        files = scan_proposals(str(tmp_path))
        assert len(files) == 3

        results = validate_all(files)
        valid_count = sum(1 for r in results if r["valid"])
        assert valid_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
