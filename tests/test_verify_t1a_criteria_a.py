"""T1a 判据验证脚本测试（M4）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.registry_lib import A1_REQUIRED_FIELDS  # noqa: E402
from scripts.verify_t1a_criteria_a import (  # noqa: E402
    build_report,
    check_criteria_a,
    check_criteria_b_prime,
    is_new_a1_verdict,
    is_no_data_tombstone,
)


def _complete_verdict(**overrides) -> dict:
    """构造 A1 完整的裁决（18 字段齐备）。"""
    v = {k: "x" for k in A1_REQUIRED_FIELDS}
    v.update({
        "variant_id": "ss_rsi_state",
        "symbol": "ss",
        "status": "ok",
        "n": 588,
        "dir_acc": 0.53,
        "run_mode": "exploration",
        "covariates_used": True,
        "dm_status": "ok",
        "pair_set_hash": "abc123",
        "pairing_valid": True,
        "p_value": 0.01,
        "dm_common_count": 500,
        "decided_at": "2026-09-28T12:00:00",
    })
    v.update(overrides)
    return v


def _legacy_verdict(**overrides) -> dict:
    """构造 pre-A1 遗留裁决（无 protocol_fingerprint）。"""
    v = {
        "variant_id": "ss_vor",
        "symbol": "ss",
        "status": "ok",
        "dir_acc": 0.50,
        "n": 588,
        "protocol_fingerprint": None,
        "run_mode": None,
        "decided_at": "2026-09-24T06:25:39",
    }
    v.update(overrides)
    return v


def _write_registry(path: Path, verdicts: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for v in verdicts:
            fp.write(json.dumps(v, ensure_ascii=False) + "\n")


# ── 新裁决识别 ──────────────────────────────────────────────────────────

def test_legacy_verdict_not_new():
    assert is_new_a1_verdict(_legacy_verdict(), None) is False


def test_a1_verdict_is_new():
    assert is_new_a1_verdict(_complete_verdict(), None) is True


def test_since_filter_excludes_older():
    v = _complete_verdict(decided_at="2026-09-28T10:00:00")
    assert is_new_a1_verdict(v, "2026-09-28T11:49:00") is False
    assert is_new_a1_verdict(v, "2026-09-28T09:00:00") is True


# ── no-data 墓碑 ────────────────────────────────────────────────────────

def test_error_status_is_tombstone():
    assert is_no_data_tombstone({"status": "error", "dir_acc": 0.5}) is True


def test_no_data_status_is_tombstone():
    assert is_no_data_tombstone({"status": "no_data"}) is True


def test_evaluated_verdict_not_tombstone():
    assert is_no_data_tombstone(_complete_verdict()) is False


# ── 判据 A ──────────────────────────────────────────────────────────────

def test_criteria_a_passes_on_complete_verdict():
    rep = check_criteria_a([_complete_verdict()])
    assert rep["passed"] is True
    assert rep["n_failed"] == 0


def test_criteria_a_fails_when_field_missing():
    v = _complete_verdict()
    del v["dir_acc_full"]
    rep = check_criteria_a([v])
    assert rep["passed"] is False
    assert rep["n_failed"] == 1
    assert any("dir_acc_full" in i for i in rep["failures"][0]["issues"])


def test_criteria_a_fails_when_run_mode_not_exploration():
    rep = check_criteria_a([_complete_verdict(run_mode="confirmation")])
    assert rep["passed"] is False
    assert any("run_mode" in i for i in rep["failures"][0]["issues"])


def test_criteria_a_fails_when_dm_status_missing_key():
    v = _complete_verdict()
    del v["dm_status"]
    rep = check_criteria_a([v])
    assert rep["passed"] is False


def test_criteria_a_allows_nullable_cov_fingerprint():
    """cov_fingerprint 在 A1_NULLABLE 内 → null 不算失败。"""
    rep = check_criteria_a([_complete_verdict(cov_fingerprint=None)])
    assert rep["passed"] is True


def test_criteria_a_empty_input_not_passed():
    """空输入不得判 PASS（防「0 条也通过」的假闭合）。"""
    rep = check_criteria_a([])
    assert rep["passed"] is False


# ── 判据 B' ─────────────────────────────────────────────────────────────

def test_criteria_b_prime_passes_with_valid_p():
    rep = check_criteria_b_prime([_complete_verdict()])
    assert rep["passed"] is True
    assert rep["n_with_valid_p"] == 1


def test_criteria_b_prime_fails_without_p():
    v = _complete_verdict(p_value=None, pairing_valid=False)
    rep = check_criteria_b_prime([v])
    assert rep["passed"] is False


def test_criteria_b_prime_excludes_no_baseline():
    v = _complete_verdict(dm_status="no_baseline", p_value=None)
    rep = check_criteria_b_prime([v])
    assert rep["n_pairable"] == 0
    assert rep["passed"] is False


def test_criteria_b_prime_excludes_no_common_cutoff():
    v = _complete_verdict(dm_status="no_common_cutoff", p_value=None)
    rep = check_criteria_b_prime([v])
    assert rep["n_pairable"] == 0


# ── 端到端 ──────────────────────────────────────────────────────────────

def test_report_no_new_verdicts_on_legacy_registry(tmp_path):
    reg = tmp_path / "aligned_verdicts.jsonl"
    _write_registry(reg, [_legacy_verdict(), _legacy_verdict(variant_id="sr_vor")])
    rep = build_report(reg, None)
    assert rep["status"] == "NO_NEW_VERDICTS"
    assert rep["n_total_in_registry"] == 2
    assert rep["n_new_a1_verdicts"] == 0


def test_report_pass_on_complete_new_verdict(tmp_path):
    reg = tmp_path / "aligned_verdicts.jsonl"
    _write_registry(reg, [_legacy_verdict(), _complete_verdict()])
    rep = build_report(reg, None)
    assert rep["status"] == "PASS"
    assert rep["n_new_a1_verdicts"] == 1
    assert rep["criteria_a"]["passed"] is True
    assert rep["criteria_b_prime"]["passed"] is True


def test_report_partial_when_a_passes_but_b_fails(tmp_path):
    """判据 A 过、B' 不过 → PARTIAL（不得报 PASS）。"""
    reg = tmp_path / "aligned_verdicts.jsonl"
    _write_registry(reg, [_complete_verdict(p_value=None, pairing_valid=False,
                                            dm_status="insufficient_common")])
    rep = build_report(reg, None)
    assert rep["status"] == "PARTIAL"
    assert rep["criteria_a"]["passed"] is True
    assert rep["criteria_b_prime"]["passed"] is False


def test_tombstones_excluded_from_denominator(tmp_path):
    reg = tmp_path / "aligned_verdicts.jsonl"
    _write_registry(reg, [
        _complete_verdict(),
        _complete_verdict(variant_id="jd_x", status="error"),
    ])
    rep = build_report(reg, None)
    assert rep["n_new_a1_verdicts"] == 2
    assert rep["n_no_data_tombstones"] == 1
    assert rep["n_evaluated"] == 1


def test_malformed_json_fails_loud(tmp_path):
    reg = tmp_path / "aligned_verdicts.jsonl"
    reg.write_text('{"ok": 1}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="非法 JSON"):
        build_report(reg, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
