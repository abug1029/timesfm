import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import sup_evidence


def _row(**kw):
    base = {
        "status": "ok",
        "dm_status": "ok",
        "gate_pass": False,
        "dir_acc": 0.45,
        "baseline_dir_acc": 0.40,
        "effective_min": 0.52,
        "p_value": None,
    }
    base.update(kw)
    return base


def test_non_ok_without_dir_acc_is_not_insufficient():
    text = sup_evidence.format_verdict_diag_label(
        _row(status="error", dir_acc=None, gate_pass=False))
    assert text == "本行不是有效裁决，不写成机制失败"


def test_unconfirmable_dm_without_dir_acc_is_not_insufficient():
    text = sup_evidence.format_verdict_diag_label(
        _row(dm_status="no_baseline", dir_acc=None, gate_pass=False))
    assert text == "DM 不可确认。不计作机制失败。这种 DM 状态不计入家族死亡"
    assert "方向低于" not in text


def test_missing_dir_acc_on_ok_confirmable_row():
    assert sup_evidence.format_verdict_diag_label(
        _row(dir_acc=None)) == "不足以归因"


def test_nan_dir_acc_is_insufficient():
    assert sup_evidence.format_verdict_diag_label(
        _row(dir_acc=float("nan"))) == "不足以归因"


def test_unconfirmable_dm_does_not_add_mechanism_label():
    text = sup_evidence.format_verdict_diag_label(
        _row(dm_status="no_baseline", dir_acc=0.30, baseline_dir_acc=0.40))
    assert text.startswith("DM 不可确认")
    assert "方向低于" not in text


def test_gate_pass_with_significant_p_is_not_confirmation():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dir_acc=0.55, p_value=0.04))
    assert "p ≤ 0.05" in text
    assert "不是确认成功" in text
    assert "已经解决" not in text


def test_gate_pass_with_large_p():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dir_acc=0.55, p_value=0.20))
    assert text == "过硬门。本行 DM 未显示 p ≤ 0.05。硬门本身不读 DM，这也不是确认成功"


def test_gate_pass_with_unconfirmable_dm_stays_a_pass():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dm_status="no_baseline", dir_acc=0.55))
    assert text.startswith("过硬门")
    assert "DM 不可确认" in text
    assert "机制失败" in text


def test_gate_pass_unconfirmable_dm_ignores_descriptive_p_value():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dm_status="set_mismatch_descriptive",
             dir_acc=0.55, p_value=0.01))
    assert text.startswith("过硬门。DM 不可确认")
    assert "p ≤ 0.05" not in text


def test_nan_p_value_falls_through_to_unstable_label():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.45, baseline_dir_acc=0.40, effective_min=0.52,
             p_value=float("nan")))
    assert text == "方向不低于基线，未过自适应门槛，DM 未显示稳定优势"


def test_significant_p_below_near_miss_band():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.40, baseline_dir_acc=0.30, effective_min=0.52,
             p_value=0.01))
    assert text == "DM 显著改善，但方向准确率未达自适应门槛"
    assert "近失" not in text


def test_significant_p_inside_near_miss_band():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.50, baseline_dir_acc=0.40, effective_min=0.52,
             p_value=0.01))
    assert text == "DM 显著改善，但方向准确率未达自适应门槛。近失，距该品种门槛只差一截"


def test_below_baseline_inside_near_miss_band():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.50, baseline_dir_acc=0.55, effective_min=0.52,
             p_value=0.20))
    assert text == "方向低于无协变量基线。近失，距该品种门槛只差一截"


def test_dir_acc_at_threshold_but_gate_failed_is_not_blamed_on_dm():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.55, baseline_dir_acc=0.40, effective_min=0.52,
             gate_pass=False, p_value=0.20))
    assert text.startswith("方向达到自适应门槛，但硬门未过")
    assert "败于" not in text
    assert "本行 DM 亦未显示 p ≤ 0.05" in text


def test_nan_p_value_on_gate_sized_failure_adds_no_p_clause():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.55, baseline_dir_acc=0.40, effective_min=0.52,
             gate_pass=False, p_value=float("nan")))
    assert text == "方向达到自适应门槛，但硬门未过。硬门还检查样本量与有效样本，不读 DM"
    assert math.isnan(float("nan"))


def _picked(**kw):
    row = {
        "symbol": "jd",
        "cov_override": "rsi_state",
        "status": "ok",
        "dm_status": "ok",
        "gate_pass": False,
        "dir_acc": 0.50,
        "baseline_dir_acc": 0.40,
        "effective_min": 0.52,
        "variant_id": "jd_rsi",
    }
    row.update(kw)
    return row


def test_negative_prefers_same_symbol_ordinary_failure_over_cross():
    near = _picked(variant_id="near", dir_acc=0.50)
    low = _picked(variant_id="low", dir_acc=0.40)
    other = _picked(symbol="rb", variant_id="rb_low", dir_acc=0.48)
    got = sup_evidence.select_symbol_diag_pair([near, low], [other])
    assert got["positive"] is near or got["positive"]["variant_id"] == "near"
    assert got["negative"]["variant_id"] == "low"
    assert got["cross_symbol"] is False
    assert got["repeat_n"] == 0


def test_only_near_miss_used_as_positive_still_crosses():
    only = _picked(variant_id="only", dir_acc=0.51)
    other = _picked(symbol="rb", variant_id="rb_hit", dir_acc=0.42)
    got = sup_evidence.select_symbol_diag_pair([only], [other])
    assert got["positive"] is only
    assert got["negative"] is other
    assert got["cross_symbol"] is True
    assert got["repeat_n"] == 1
    assert got["negative_empty"] is None


def test_cross_symbol_picks_highest_and_counts_repeats():
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass")
    low = _picked(symbol="rb", variant_id="rb_low", dir_acc=0.41)
    high = _picked(symbol="m", variant_id="m_high", dir_acc=0.47)
    got = sup_evidence.select_symbol_diag_pair([pos], [low, high])
    assert got["negative"]["variant_id"] == "m_high"
    assert got["repeat_n"] == 2
    assert got["cross_symbol"] is True


def test_blank_symbol_uses_fixed_empty_reasons():
    got = sup_evidence.select_symbol_diag_pair([], [])
    assert got["positive"] is None
    assert got["negative"] is None
    assert got["positive_empty"] == "本品种无通过、无近失"
    assert got["negative_empty"] == "本品种尚无有效失败记录"


def test_selector_does_not_mutate_rows():
    only = _picked()
    snapshot = dict(only)
    sup_evidence.select_symbol_diag_pair([only], [])
    assert only == snapshot


def test_incomplete_higher_dir_acc_loses_to_complete_row():
    broken = _picked(variant_id="broken", dir_acc=0.60, baseline_dir_acc=None,
                     gate_pass=True)
    whole = _picked(variant_id="whole", dir_acc=0.55, gate_pass=True)
    got = sup_evidence.select_symbol_diag_pair([broken, whole], [])
    assert got["positive"]["variant_id"] == "whole"


def test_no_positive_single_cov_crosses_two_covs_do_not():
    local = _picked(dm_status="no_baseline", dir_acc=0.40, variant_id="local",
                    cov_override="rsi_state")
    other = _picked(symbol="rb", variant_id="rb", dir_acc=0.43,
                    cov_override="rsi_state")
    got = sup_evidence.select_symbol_diag_pair([local], [other])
    assert got["positive"] is None
    assert got["negative"]["variant_id"] == "rb"
    assert got["cross_symbol"] is True
    second = _picked(dm_status="no_baseline", dir_acc=0.41, variant_id="local2",
                     cov_override="vwap_deviation")
    got2 = sup_evidence.select_symbol_diag_pair([local, second], [other])
    assert got2["positive"] is None
    assert got2["negative"] is None
    assert got2["cross_symbol"] is False


def test_equal_dir_acc_prefers_smaller_symbol_name():
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass")
    rb = _picked(symbol="rb", variant_id="rb", dir_acc=0.44)
    em = _picked(symbol="m", variant_id="m", dir_acc=0.44)
    got = sup_evidence.select_symbol_diag_pair([pos], [rb, em])
    assert got["negative"]["variant_id"] == "m"


def test_equal_dir_acc_ignores_symbol_case():
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass")
    upper = _picked(symbol="M", variant_id="z", dir_acc=0.44)
    lower = _picked(symbol="m", variant_id="a", dir_acc=0.44)
    got = sup_evidence.select_symbol_diag_pair([pos], [upper, lower])
    assert got["negative"]["variant_id"] == "a"


def test_materialize_inserts_diag_section_without_mutating_rows(tmp_path, monkeypatch):
    import sup_state
    monkeypatch.setattr(sup_state, "GOAL_SYMBOLS_SET", {"jd"})
    only = {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": "jd_only",
        "symbol": "jd",
        "cov_override": "rsi_state",
        "cov_family": "momentum",
        "status": "ok",
        "gate_pass": False,
        "dir_acc": 0.51,
        "baseline_dir_acc": 0.40,
        "effective_min": 0.52,
        "p_value": 0.20,
        "dm_status": "ok",
        "protocol_fingerprint": "f" * 64,
        "run_mode": "exploration",
        "decided_at": "2026-11-01T00:00:00",
        "fdr_pass": False,
        "n": 400,
        "ev": 0.0,
    }
    other = dict(only)
    other.update({"variant_id": "rb_only", "symbol": "rb", "dir_acc": 0.44})
    before = (dict(only), dict(other))
    dest = tmp_path / "known_verdicts.inc.md"
    sup_evidence.materialize_known_verdicts(
        {"jd_only": only, "rb_only": other}, str(dest),
        proposed_ids=set(), status_map={}, queue_ids=set())
    text = dest.read_text(encoding="utf-8")
    assert text.index("## Effective clues") < text.index("## 诊断样本")
    assert "jd 正面：" in text
    assert "jd 反面（跨品种 rb）：" in text
    assert "同协变量可确认失败 n=1" not in text
    assert "mechanism" not in text.split("## 诊断样本", 1)[1].split("\n## ", 1)[0]
    assert only == before[0]
    assert other == before[1]


def test_repeat_count_is_written_only_when_at_least_two():
    import sup_state
    # 不跑 materialize。渲染函数直接吃 select 的结果。
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass",
                  decided_at="2026-11-01T00:00:00")
    a = _picked(symbol="rb", variant_id="a", dir_acc=0.42,
                decided_at="2026-11-02T00:00:00")
    b = _picked(symbol="m", variant_id="b", dir_acc=0.46,
                decided_at="2026-11-03T00:00:00")
    picked = sup_evidence.select_symbol_diag_pair([pos], [a, b])
    line = sup_evidence._format_diag_bullet("jd", "反面", picked)
    assert "反面（跨品种 m）" in line
    assert "同协变量可确认失败 n=2" in line
    assert "decided_at=2026-11-03T00:00:00" in line
