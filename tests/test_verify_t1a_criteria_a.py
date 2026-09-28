"""T1a 判据验证脚本测试（M4）。

覆盖复核（2026-09-28）指出的缺口:
  - pair_set_hash=None（HIGH 假 FAIL 路径）
  - status="timeout" tombstone（原 denylist 漏项）
  - protocol_mismatch 在 DM_NOT_PAIRABLE
  - 非 dict JSONL 行 / 缺文件
  - 全 tombstone registry
  - main() 退出码映射
  - A1_NOT_WIRED（时间基说新但缺指纹）
  - p_value NaN / bool
  - --since 格式校验
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.registry_lib import A1_REQUIRED_FIELDS  # noqa: E402
from scripts.verify_t1a_criteria_a import (  # noqa: E402
    EXIT_CODES,
    UsageError,
    _valid_p,
    build_report,
    check_criteria_a,
    check_criteria_b_prime,
    is_evaluated,
    is_new_a1_verdict,
    is_new_by_time,
    load_verdicts,
    main,
)

SCRIPT = REPO_ROOT / "scripts" / "verify_t1a_criteria_a.py"


def _complete_verdict(**overrides) -> dict:
    """构造**生产形状**的 A1 完整裁决（复核 MEDIUM-7: 不用 'x' 占位）。"""
    v = {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": "ss_rsi_state",
        "symbol": "ss",
        "cov_override": "rsi_state",
        "status": "ok",
        "n": 588,
        "n_eff": 73.0,
        "dir_acc": 0.53,
        "weighted_dir_acc": 0.53,
        "dir_acc_full": 0.52,
        "dir_acc_ex_roll": 0.53,
        "n_roll_excluded": 3,
        "n_roll_ratio": 0.0051,
        "gate_pass": True,
        "run_mode": "exploration",
        "run_label": "exploratory_unconfirmed",
        "covariates_used": True,
        "dm_status": "ok",
        "dm_common_count": 500,
        "n_avail_variant": 588,
        "n_avail_baseline": 588,
        "missingness_admissible": True,
        "d_series_n_eff": 71.0,
        "pair_set_hash": "abc123",
        "baseline_dir_acc": 0.50,
        "protocol_fingerprint": "fp_v2",
        "cov_fingerprint": "covfp",
        "pairing_valid": True,
        "p_value": 0.01,
        "decided_at": "2026-09-28T12:00:00",
    }
    # 保证 18 个 A1 字段齐备
    for k in A1_REQUIRED_FIELDS:
        v.setdefault(k, None)
    v.update(overrides)
    return v


def _legacy_verdict(**overrides) -> dict:
    v = {
        "schema": "fm.aligned_verdict.v2",
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


def _write_registry(path: Path, verdicts: list) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for v in verdicts:
            fp.write(json.dumps(v, ensure_ascii=False) + "\n")


# ── 判别器 ──────────────────────────────────────────────────────────────

def test_legacy_verdict_not_new():
    assert is_new_a1_verdict(_legacy_verdict()) is False


def test_a1_verdict_is_new():
    assert is_new_a1_verdict(_complete_verdict()) is True


def test_time_based_discriminator_independent():
    """时间基判别独立于指纹判别（复核 HIGH-2）。"""
    from datetime import datetime
    v = _legacy_verdict(decided_at="2026-09-28T12:00:00")
    since = datetime.fromisoformat("2026-09-28T11:49:00")
    assert is_new_by_time(v, since) is True     # 时间上是新的
    assert is_new_a1_verdict(v) is False        # 但缺指纹


def test_time_based_none_since():
    from datetime import datetime
    assert is_new_by_time(_complete_verdict(), None) is False


# ── 经评估白名单（复核 MEDIUM-3）───────────────────────────────────────

def test_only_ok_status_is_evaluated():
    assert is_evaluated({"status": "ok"}) is True
    assert is_evaluated({"status": "error"}) is False
    assert is_evaluated({"status": "no_data"}) is False
    assert is_evaluated({"status": "timeout"}) is False   # 原 denylist 漏项
    assert is_evaluated({"status": "skipped"}) is False   # 原可混入
    assert is_evaluated({}) is False


def test_timeout_tombstone_excluded_from_denominator(tmp_path):
    """registry_lib 的 timeout tombstone 不得计入判据分母。"""
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [
        _complete_verdict(),
        _complete_verdict(variant_id="jd_t", status="timeout"),
    ])
    rep = build_report(reg, None)
    assert rep["n_new_a1_verdicts"] == 2
    assert rep["n_evaluated"] == 1
    assert rep["n_excluded_not_evaluated"] == 1


# ── 判据 A ──────────────────────────────────────────────────────────────

def test_criteria_a_passes_on_production_shaped_verdict():
    rep = check_criteria_a([_complete_verdict()])
    assert rep["passed"] is True
    assert rep["n_failed"] == 0


def test_criteria_a_fails_when_field_missing():
    v = _complete_verdict()
    del v["dir_acc_full"]
    rep = check_criteria_a([v])
    assert rep["passed"] is False
    assert any("dir_acc_full" in i for i in rep["failures"][0]["issues"])


def test_criteria_a_fails_when_run_mode_not_exploration():
    rep = check_criteria_a([_complete_verdict(run_mode="confirmation")])
    assert rep["passed"] is False
    assert any("run_mode" in i for i in rep["failures"][0]["issues"])


def test_criteria_a_fails_when_dm_status_missing_key():
    v = _complete_verdict()
    del v["dm_status"]
    assert check_criteria_a([v])["passed"] is False


def test_criteria_a_allows_nullable_cov_fingerprint():
    assert check_criteria_a([_complete_verdict(cov_fingerprint=None)])["passed"] is True


def test_criteria_a_empty_input_not_passed():
    """防「0 条也通过」的假闭合。"""
    assert check_criteria_a([])["passed"] is False


def test_pair_set_hash_none_is_not_a_failure():
    """复核 HIGH-1: plan 原文是「不得为**缺键**」，值可为 None。

    statistical_tests.py:350 在非 ok 分支一律留 pair_set_hash=None，
    且 registry_lib.A1_NULLABLE 含该字段。原实现判 `is None` 会假 FAIL。
    """
    v = _complete_verdict(dm_status="no_common_cutoff", pair_set_hash=None,
                          pairing_valid=False, p_value=None)
    rep = check_criteria_a([v])
    assert rep["passed"] is True, rep["failures"]
    assert rep["n_failed"] == 0


def test_pair_set_hash_missing_key_is_a_failure():
    """缺键才是失败（plan 原文）。"""
    v = _complete_verdict()
    del v["pair_set_hash"]
    rep = check_criteria_a([v])
    assert rep["passed"] is False
    assert any("pair_set_hash" in i for i in rep["failures"][0]["issues"])


def test_no_baseline_verdict_passes_criteria_a():
    """plan 预测 cf/i/jm/ma/p/sh 会落 no_baseline —— 不得因此假 FAIL。"""
    v = _complete_verdict(dm_status="no_baseline", pair_set_hash=None,
                          baseline_dir_acc=None, pairing_valid=False, p_value=None)
    assert check_criteria_a([v])["passed"] is True


# ── 判据 B' ─────────────────────────────────────────────────────────────

def test_criteria_b_prime_passes_with_valid_p():
    rep = check_criteria_b_prime([_complete_verdict()])
    assert rep["passed"] is True
    assert rep["n_with_valid_p"] == 1


def test_criteria_b_prime_fails_without_p():
    rep = check_criteria_b_prime([_complete_verdict(p_value=None, pairing_valid=False)])
    assert rep["passed"] is False


def test_criteria_b_prime_excludes_no_baseline():
    rep = check_criteria_b_prime([_complete_verdict(dm_status="no_baseline", p_value=None)])
    assert rep["n_pairable"] == 0
    assert rep["passed"] is False


def test_criteria_b_prime_excludes_no_common_cutoff():
    rep = check_criteria_b_prime([_complete_verdict(dm_status="no_common_cutoff", p_value=None)])
    assert rep["n_pairable"] == 0
    assert rep["passed"] is False


def test_criteria_b_prime_excludes_protocol_mismatch():
    """复核 LOW-1: 补 protocol_mismatch 覆盖。"""
    rep = check_criteria_b_prime([_complete_verdict(dm_status="protocol_mismatch", p_value=None)])
    assert rep["n_pairable"] == 0
    assert rep["passed"] is False


def test_criteria_b_prime_rejects_nan_p():
    """复核 LOW-3: NaN 不是「产出了 p 值」的证据。"""
    rep = check_criteria_b_prime([_complete_verdict(p_value=float("nan"))])
    assert rep["passed"] is False
    assert rep["n_with_valid_p"] == 0


def test_criteria_b_prime_rejects_bool_p():
    assert check_criteria_b_prime([_complete_verdict(p_value=True)])["passed"] is False


def test_valid_p_boundaries():
    assert _valid_p(0.0) is True
    assert _valid_p(1.0) is True
    assert _valid_p(1.0001) is False
    assert _valid_p(-0.01) is False
    assert _valid_p(float("inf")) is False
    assert _valid_p(float("nan")) is False
    assert _valid_p(True) is False
    assert _valid_p("0.01") is False


# ── 端到端 ──────────────────────────────────────────────────────────────

def test_report_no_new_verdicts_on_legacy_registry(tmp_path):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_legacy_verdict(), _legacy_verdict(variant_id="sr_vor")])
    rep = build_report(reg, None)
    assert rep["status"] == "NO_NEW_VERDICTS"
    assert rep["n_new_a1_verdicts"] == 0


def test_report_a1_not_wired_when_time_new_but_no_fingerprint(tmp_path):
    """复核 HIGH-2: 接线回归必须报 A1_NOT_WIRED，不得静默「仍在等待」。"""
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [
        _legacy_verdict(decided_at="2026-09-28T12:00:00"),
        _legacy_verdict(variant_id="sr_vor", decided_at="2026-09-28T12:05:00"),
    ])
    rep = build_report(reg, "2026-09-28T11:49:00")
    assert rep["status"] == "A1_NOT_WIRED"
    assert rep["time_new_without_fingerprint"] == 2
    assert "接线可能失效" in rep["note"]


def test_report_pass_on_complete_new_verdict(tmp_path):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_legacy_verdict(), _complete_verdict()])
    rep = build_report(reg, None)
    assert rep["status"] == "PASS"


def test_report_partial_when_a_passes_but_b_fails(tmp_path):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict(
        p_value=None, pairing_valid=False, dm_status="insufficient_common")])
    rep = build_report(reg, None)
    assert rep["status"] == "PARTIAL"
    assert rep["criteria_a"]["passed"] is True
    assert rep["criteria_b_prime"]["passed"] is False


def test_all_tombstones_registry_is_fail(tmp_path):
    """复核 MEDIUM-7: 全 tombstone 路径不得 PASS。"""
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [
        _complete_verdict(status="error"),
        _complete_verdict(variant_id="x", status="timeout"),
    ])
    rep = build_report(reg, None)
    assert rep["status"] == "FAIL"
    assert rep["n_evaluated"] == 0


def test_excluded_variants_are_listed(tmp_path):
    """复核 LOW-4: 被排除的 tombstone 须逐条可见。"""
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict(status="timeout", variant_id="jd_t")])
    rep = build_report(reg, None)
    assert rep["excluded_variants"][0]["variant_id"] == "jd_t"
    assert rep["excluded_variants"][0]["status"] == "timeout"


# ── fail-loud ───────────────────────────────────────────────────────────

def test_malformed_json_fails_loud(tmp_path):
    reg = tmp_path / "r.jsonl"
    reg.write_text('{"ok": 1}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="非法 JSON"):
        load_verdicts(reg)


def test_non_dict_json_line_fails_loud(tmp_path):
    """复核 MEDIUM-6: `null` / `123` 是合法 JSON 但非对象 → fail-loud。"""
    for payload in ("null", "123", '["a"]'):
        reg = tmp_path / "r.jsonl"
        reg.write_text(payload + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="非 JSON 对象"):
            load_verdicts(reg)


def test_missing_registry_raises_usage_error(tmp_path):
    with pytest.raises(UsageError, match="registry 不存在"):
        load_verdicts(tmp_path / "nope.jsonl")


def test_bad_since_format_raises_usage_error(tmp_path):
    """复核 MEDIUM-5: --since 必须 ISO 解析，不得字典序静默漏判。"""
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict()])
    with pytest.raises(UsageError, match="不是合法 ISO"):
        build_report(reg, "2026/09/28")


def test_since_format_variants_compare_correctly(tmp_path):
    """空格分隔的 decided_at 与 T 分隔的 since 必须能正确比较。"""
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict(decided_at="2026-09-28 12:00:00")])
    rep = build_report(reg, "2026-09-28T11:49:00")
    assert rep["time_based_new_count"] == 1


# ── 退出码（复核 MEDIUM-4）──────────────────────────────────────────────

def test_exit_codes_are_distinct():
    vals = list(EXIT_CODES.values())
    assert len(vals) == len(set(vals)), "退出码必须互不冲突"
    assert EXIT_CODES["USAGE_ERROR"] not in (
        EXIT_CODES["PASS"], EXIT_CODES["PARTIAL"],
        EXIT_CODES["FAIL"], EXIT_CODES["NO_NEW_VERDICTS"],
    )


def test_main_exit_code_pass(tmp_path, monkeypatch, capsys):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict()])
    monkeypatch.setattr(sys, "argv", ["prog", "--registry", str(reg)])
    assert main() == EXIT_CODES["PASS"]


def test_main_exit_code_fail(tmp_path, monkeypatch):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict(p_value=None, pairing_valid=False,
                                            dm_status="insufficient_common",
                                            run_mode="confirmation")])
    monkeypatch.setattr(sys, "argv", ["prog", "--registry", str(reg)])
    assert main() == EXIT_CODES["FAIL"]


def test_main_exit_code_no_new(tmp_path, monkeypatch):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_legacy_verdict()])
    monkeypatch.setattr(sys, "argv", ["prog", "--registry", str(reg)])
    assert main() == EXIT_CODES["NO_NEW_VERDICTS"]


def test_main_exit_code_not_wired(tmp_path, monkeypatch):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_legacy_verdict(decided_at="2026-09-28T12:00:00")])
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--registry", str(reg), "--since", "2026-09-28T11:49:00"])
    assert main() == EXIT_CODES["A1_NOT_WIRED"]


def test_main_exit_code_usage_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--registry", str(tmp_path / "nope.jsonl")])
    assert main() == EXIT_CODES["USAGE_ERROR"]


def test_main_json_output_is_valid(tmp_path, monkeypatch, capsys):
    reg = tmp_path / "r.jsonl"
    _write_registry(reg, [_complete_verdict()])
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--registry", str(reg), "--json"])
    main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "PASS"


# ── 真实 registry 冒烟 ──────────────────────────────────────────────────

def test_real_registry_reports_no_new_verdicts():
    """对生产 registry 冒烟：143 条 pre-A1 遗留 → 必为 NO_NEW_VERDICTS。"""
    real = REPO_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
    if not real.exists():
        pytest.skip("生产 registry 不存在")
    rep = build_report(real, None)
    assert rep["status"] == "NO_NEW_VERDICTS"
    assert rep["n_total_in_registry"] == 143


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
