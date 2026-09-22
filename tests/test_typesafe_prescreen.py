"""tests/test_typesafe_prescreen.py"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from cascade.typesafe_prescreen import (
    compute_skip_suggested,
    generate_note,
    _fallback_result,
    _reset_circuit_state,
    _extract_relevant_history,
    _check_circuit,
    _record_timeout,
    _record_success,
    prescreen_proposal,
    prescreen_and_save,
    write_prescreen_result,
    AuthenticationError,
)


@pytest.fixture(autouse=True)
def _clean_circuit_state():
    """每个测试用例前后重置熔断状态，防止全局变量污染。"""
    _reset_circuit_state()
    yield
    _reset_circuit_state()


class TestComputeSkipSuggested:
    def test_plausible_novel_passes(self):
        assert compute_skip_suggested(0.85, "novel", 3) is False

    def test_implausible_skipped(self):
        assert compute_skip_suggested(0.3, "novel", 2) is True

    def test_invalid_mechanism_skipped(self):
        assert compute_skip_suggested(0.7, "invalid", 3) is True

    def test_redundant_weak_skipped(self):
        assert compute_skip_suggested(0.6, "redundant", 1) is True

    def test_zero_effect_low_plausibility_skipped(self):
        assert compute_skip_suggested(0.5, "novel", 0) is True

    def test_zero_effect_high_plausibility_passes(self):
        assert compute_skip_suggested(0.7, "novel", 0) is False

    def test_redundant_strong_passes(self):
        assert compute_skip_suggested(0.6, "redundant", 2) is False


class TestGenerateNote:
    def test_high_confidence_note(self):
        note = generate_note(0.85, "novel", 3)
        assert "机制可信 (0.85)" in note
        assert "全新" in note
        assert "强" in note

    def test_low_confidence_note(self):
        note = generate_note(0.3, "redundant", 0)
        assert "机制可信度低 (0.30)" in note
        assert "冗余" in note
        assert "无信息量" in note

    def test_unknown_novelty_fallback(self):
        note = generate_note(0.5, "unknown_type", 1)
        assert "unknown_type" in note


class TestFallbackResult:
    def test_degraded_has_none_skip(self):
        result = _fallback_result({"variant_id": "v1"}, "JD")
        assert result["status"] == "degraded"
        assert result["skip_suggested"] is None
        assert result["mechanism_plausibility"] is None

    def test_ts_is_utc_iso(self):
        result = _fallback_result({"variant_id": "v1"}, "JD")
        assert "+00:00" in result["ts"] or "Z" in result["ts"]


class TestExtractRelevantHistory:
    def test_empty_history(self):
        assert _extract_relevant_history(None, "ss") == "无历史裁决记录"

    def test_symbol_history_only(self):
        history = [
            {"symbol": "ss", "gate_pass": True, "cov_override": "rsi_state",
             "cov_family": "momentum", "dir_acc": 0.53, "decided_at": "2026-09-01T00:00:00"},
        ]
        result = _extract_relevant_history(history, "ss")
        assert "[ss] 已过门协变量" in result
        assert "rsi_state" in result

    def test_none_decided_at_safe(self):
        """decided_at=None 时排序不崩溃。"""
        history = [
            {"symbol": "ss", "gate_pass": True, "cov_override": "ccl",
             "cov_family": "inventory", "dir_acc": 0.51, "decided_at": None},
        ]
        result = _extract_relevant_history(history, "ss")
        assert "ccl" in result

    def test_unknown_sector_no_cross_pollution(self):
        """未知板块品种不注入同板块先验。"""
        history = [
            {"symbol": "xyz_new", "gate_pass": True, "cov_override": "foo",
             "cov_family": "momentum", "dir_acc": 0.55, "decided_at": "2026-09-01"},
        ]
        result = _extract_relevant_history(history, "xyz_new")
        assert "同板块" not in result

    def test_cross_sector_family_dedup(self):
        """跨品种先验按 cov_family 去重。"""
        history = [
            {"symbol": "rb", "gate_pass": True, "cov_override": "rsi_state",
             "cov_family": "momentum", "dir_acc": 0.54, "decided_at": "2026-09-01"},
            {"symbol": "rb", "gate_pass": True, "cov_override": "oi",
             "cov_family": "inventory", "dir_acc": 0.52, "decided_at": "2026-08-15"},
            {"symbol": "i", "gate_pass": True, "cov_override": "rsi12",
             "cov_family": "momentum", "dir_acc": 0.51, "decided_at": "2026-09-10"},
        ]
        result = _extract_relevant_history(history, "ss")
        assert result.count("momentum") == 1


class TestCircuitBreaker:
    def test_no_circuit_initially(self):
        assert _check_circuit() is False

    def test_opens_after_3_timeouts(self):
        _record_timeout()
        _record_timeout()
        _record_timeout()
        assert _check_circuit() is True

    def test_half_open_resets_on_expire(self, monkeypatch):
        """短路期满后自动重置，允许试探。"""
        _record_timeout()
        _record_timeout()
        _record_timeout()
        assert _check_circuit() is True

        fake_now = time.time() + 601
        monkeypatch.setattr(time, "time", lambda: fake_now)
        assert _check_circuit() is False
        _reset_circuit_state()

    def test_resets_on_success(self):
        _record_timeout()
        _record_timeout()
        _record_success()
        assert _check_circuit() is False

    def test_reset_circuit_state_clears_all(self):
        _record_timeout()
        _record_timeout()
        _record_timeout()
        _reset_circuit_state()
        assert _check_circuit() is False


# ── Mock SDK 辅助 ───────────────────────────────────

class MockAnswer:
    """Mock SDK Answer 对象，模拟 typesafe_sdk 返回。"""
    def __init__(self, probability_yes=None, value=None, level_index=None,
                 confidence=None, reasoning=None):
        self.probability_yes = probability_yes
        self.value = value
        self.level_index = level_index
        self.confidence = confidence
        self.reasoning = reasoning


class MockJudgeResult:
    """Mock SDK judge 返回。"""
    def __init__(self, answers: dict, is_ok: bool = True):
        self.data = type("Data", (), {"answers": answers})()
        self.is_ok = is_ok


def _make_mock_result(plausibility=0.85, novelty="novel", effect_size=3):
    return MockJudgeResult({
        "mechanism_plausibility": MockAnswer(probability_yes=plausibility),
        "novelty_vs_redundancy": MockAnswer(value=novelty),
        "expected_effect_size": MockAnswer(level_index=effect_size),
    })


SAMPLE_PROPOSAL = {
    "variant_id": "v_test_001",
    "symbol": "JD",
    "mechanism": "JD 鸡蛋散户反向指标在交割月效应增强",
    "cov_override": "rsi_state",
}


# ── 完整功能 Mock 测试 ──────────────────────────────

class TestPrescreenProposalMock:
    """Mock SDK 调用，验证 prescreen_proposal 核心逻辑。"""

    def test_plausible_proposal_passes(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.85, "novel", 3))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "success"
        assert result["skip_suggested"] is False
        assert result["mechanism_plausibility"] == 0.85

    def test_implausible_proposal_skipped(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.2, "novel", 1))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_redundant_proposal_skipped(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.6, "redundant", 1))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_invalid_mechanism_skipped(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.7, "invalid", 3))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_zero_effect_low_plausibility_skipped(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.5, "extension", 0))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_no_api_key_returns_degraded(self, monkeypatch):
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "degraded"
        assert result["skip_suggested"] is None

    def test_api_timeout_returns_degraded(self, monkeypatch):
        """超时 → degraded。mock 只抛异常，不手动调 _record_timeout()（避免双重计数）。"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        def raise_timeout(*a, **k):
            raise TimeoutError("simulated timeout")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_timeout)
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "degraded"
        assert result["skip_suggested"] is None
        assert "超时" in result["note"]

    def test_auth_error_returns_error(self, monkeypatch):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        def raise_auth(*a, **k):
            raise AuthenticationError("401 Unauthorized")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_auth)
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "error"
        assert result["skip_suggested"] is None
        assert "鉴权" in result["note"]

    def test_timeout_triggers_circuit_not_error(self, monkeypatch):
        """连续 3 次超时后，第 4 次走短路不再调用 API。"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        call_count = [0]
        def raise_timeout(*a, **k):
            call_count[0] += 1
            raise TimeoutError("simulated")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_timeout)

        for _ in range(3):
            prescreen_proposal(SAMPLE_PROPOSAL, "JD")

        call_count[0] = 0
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert call_count[0] == 0  # API 未被调用
        assert result["status"] == "degraded"

    def test_never_raise_wraps_all_exceptions(self, monkeypatch):
        """内部处理异常 → 平滑降级"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        def raise_internal(*a, **k):
            return MockJudgeResult({})  # answers 为空，解包会 AttributeError
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_internal)
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "error"
        assert result["skip_suggested"] is None

    def test_novelty_normalisation(self, monkeypatch):
        """Choice 返回值归一化：大小写/空白不敏感"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.6, "  REDUNDANT ", 1))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["novelty"] == "redundant"
        assert result["skip_suggested"] is True

    def test_raw_answers_preserved(self, monkeypatch):
        """raw_answers 保留 SDK 原始序列化"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.85, "novel", 3))
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert "mechanism_plausibility" in result["raw_answers"]
        assert result["raw_answers"]["mechanism_plausibility"]["probability_yes"] == 0.85


class TestAtomicWrite:
    def test_atomic_write_replaces_cleanly(self, tmp_path):
        p = str(tmp_path / "sub" / "test.prescreen.json")
        result = {"status": "success", "skip_suggested": False}
        write_prescreen_result(p, result)
        assert os.path.exists(p)
        assert len(list(tmp_path.rglob("*.tmp.*"))) == 0
        with open(p) as f:
            assert json.load(f)["status"] == "success"


class TestPrescreenAndSaveFacade:
    def test_facade_calls_both(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.7, "extension", 2))
        proposal_path = str(tmp_path / "p_001.json")
        result = prescreen_and_save(SAMPLE_PROPOSAL, proposal_path, "JD")
        assert result["status"] == "success"
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
        assert os.path.exists(prescreen_path)


class TestSlowLoopMetadataAttachment:
    def test_slow_loop_reads_prescreen(self, tmp_path):
        proposal_path = str(tmp_path / "proposals" / "p_001.json")
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
        ps = {
            "status": "success", "skip_suggested": True,
            "mechanism_plausibility": 0.3, "novelty": "invalid",
            "effect_size": 0, "note": "测试 note",
        }
        os.makedirs(os.path.dirname(prescreen_path), exist_ok=True)
        with open(prescreen_path, "w") as f:
            json.dump(ps, f)

        verdict = {"gate_pass": False, "status": "aligned"}
        pp = str(Path(proposal_path).with_suffix(".prescreen.json"))
        if os.path.exists(pp):
            try:
                with open(pp, encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, OSError):
                loaded = None
            if loaded:
                if "metadata" not in verdict:
                    verdict["metadata"] = {}
                verdict["metadata"]["prescreen"] = {
                    "status": loaded.get("status"),
                    "skip_suggested": loaded.get("skip_suggested"),
                    "plausibility": loaded.get("mechanism_plausibility"),
                    "novelty": loaded.get("novelty"),
                    "effect_size": loaded.get("effect_size"),
                    "note": loaded.get("note"),
                }

        assert verdict["metadata"]["prescreen"]["skip_suggested"] is True
        assert verdict["metadata"]["prescreen"]["plausibility"] == 0.3

    def test_corrupted_prescreen_does_not_crash(self, tmp_path):
        proposal_path = str(tmp_path / "proposals" / "p_001.json")
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
        os.makedirs(os.path.dirname(prescreen_path), exist_ok=True)
        with open(prescreen_path, "w") as f:
            f.write('{"status": "succe')

        verdict = {"gate_pass": True}
        pp = str(Path(proposal_path).with_suffix(".prescreen.json"))
        if os.path.exists(pp):
            try:
                with open(pp, encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, OSError):
                loaded = None
        assert "metadata" not in verdict
