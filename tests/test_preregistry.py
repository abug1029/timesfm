"""预注册纯逻辑（spec §5.3 测试 37/38/40/44/68 + 裁定 (a′)）。

不覆盖 39、41–43、45–67、69–70。
"""
from __future__ import annotations

import dataclasses
import inspect
import re
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from cascade.statistical_tests import n_required  # noqa: E402

import preregistry as pr  # noqa: E402


REFUTED_NOTE = "未在预定样本量上检出优于基线的效应；不得表述为小效应无效"

_SYMBOL_VAR_LR = {
    "jd": 1.240,
    "m": 1.056,
    "rb": 1.223,
    "sr": 1.020,
    "ss": 1.154,
}
_SYMBOL_N = {
    "jd": 1199,
    "m": 1021,
    "rb": 1182,
    "sr": 986,
    "ss": 1116,
}


def _fields(**overrides):
    base = {
        "symbol": "jd",
        "cov_fingerprint": "cov-jd-vor",
        "model_fingerprint": "model-a",
        "predict_params": {"signal_weight": 1.0},
        "horizon": 24,
        "metric_version": "dir_v1",
        "registered_at": "2026-10-01T00:00:00Z",
        "confirm_from_ts": "2026-10-01 00:00:00",
        "delta_star": 0.08,
        "power": 0.80,
        "alpha": 0.05,
        "var_lr": 1.240,
        "kill_condition": {"field": "dir_acc", "threshold": 0.5},
        "promote_condition": {"field": "d_mean", "threshold": 0.08},
        "mechanism": "近月偏紧",
        "predicted_direction": "up",
    }
    base.update(overrides)
    return base


def _passing_row(**overrides):
    row = {
        "run_mode": "confirmation",
        "contaminated": False,
        "early_sealed": False,
        "n_confirm_actual": 1199,
        "n_confirm_required": 1199,
        "common_insufficient": False,
        "meets_min_info": True,
        "gate_pass": True,
        "p_value": 0.01,
        "covariates_used": True,
        "pairing_valid": True,
        "missingness_admissible": True,
        "protocol_compatible": True,
        "dm_significant": True,
        "dm_status": "ok",
        "fdr_pass": False,
    }
    row.update(overrides)
    return row


def _later_kwargs():
    return {
        "confirm_from_ts": "2026-10-02 00:00:00",
        "registered_at": "2026-10-02T00:00:00Z",
    }


# ── (a′) 样本量：必须来自 n_required，不另写公式 ──────────────


def test_a_prime_symbol_n_matches_n_required():
    for symbol, var_lr in _SYMBOL_VAR_LR.items():
        got = pr.n_confirm_required_for_symbol(symbol)
        via = n_required(var_d=var_lr, vif=1.0, delta=0.08)
        assert got == via
        # Q7 memo prints 1115, and n_required ceil of var_lr=1.154 is 1116, so the function wins.
        assert got == _SYMBOL_N[symbol]
        assert pr.n_confirm_required(var_lr) == via


def test_a_prime_unlisted_symbols_use_conservative_default():
    default_n = n_required(var_d=1.240, vif=1.0, delta=0.08)
    assert default_n == 1199
    for symbol in ("cj", "eg", "fu", "lh", "au"):
        assert pr.n_confirm_required_for_symbol(symbol) == default_n


def test_n_confirm_required_delegates_to_n_required():
    src = inspect.getsource(pr.n_confirm_required)
    assert "n_required(" in src
    assert "vif=1.0" in src
    assert "delta=0.08" in src
    assert "z_alpha" not in src
    assert "z_beta" not in src
    module = Path(pr.__file__).read_text(encoding="utf-8")
    assert "datetime" not in module
    assert "(z_alpha + z_beta)" not in module


# ── 37：入队模式 + registered_at 写保护 ───────────────────────


def test_37_confirmation_without_locked_id_is_rejected():
    rec = pr.register(_fields(), [])
    registry = [rec]
    missing = pr.queue_decision({}, registry, run_mode="confirmation")
    assert missing.accepted is False
    assert missing.reason == "no_prereg_id"

    unknown = pr.queue_decision(
        {"prereg_id": "not-registered"}, registry, run_mode="confirmation")
    assert unknown.accepted is False
    assert unknown.reason == "no_prereg_id"

    unlocked = pr.queue_decision(
        {"prereg_id": "abc"},
        [{"prereg_id": "abc", "registered_at": None}],
        run_mode="confirmation",
    )
    assert unlocked.accepted is False
    assert unlocked.reason == "no_prereg_id"

    blank = pr.queue_decision(
        {"prereg_id": "abc"},
        [{"prereg_id": "abc", "registered_at": ""}],
        run_mode="confirmation",
    )
    assert blank.accepted is False
    assert blank.reason == "no_prereg_id"


def test_37_exploration_without_id_is_accepted():
    decision = pr.queue_decision({}, [], run_mode="exploration")
    assert decision.accepted is True
    assert decision.run_label == "exploratory_unconfirmed"
    assert decision.reason is None

    with_id = pr.queue_decision(
        {"prereg_id": "anything"}, [], run_mode="exploration")
    assert with_id.accepted is True
    assert with_id.run_label == "exploratory_unconfirmed"


def test_37_registered_at_change_is_immutable():
    rec = pr.register(_fields(), [])
    claimed = dataclasses.asdict(rec)
    claimed["registered_at"] = "2026-10-03T00:00:00Z"
    with pytest.raises(ValueError, match="prereg_immutable"):
        pr.validate_reuse(rec, claimed)
    assert rec.registered_at == "2026-10-01T00:00:00Z"


def test_37_confirmation_with_locked_id_is_accepted():
    existing = []
    rec = pr.register(_fields(), existing)
    assert existing == []
    assert re.fullmatch(r"[0-9a-f]{32}", rec.prereg_id)
    decision = pr.queue_decision(
        {"prereg_id": rec.prereg_id}, [rec], run_mode="confirmation")
    assert decision.accepted is True
    assert decision.reason is None
    assert decision.prereg_id == rec.prereg_id


# ── 38：冻结字段只能换新 id ──────────────────────────────────


def test_38_frozen_change_mints_new_id_and_old_id_is_rejected():
    old = pr.register(_fields(jev={"plausibility": "suggest"}), [])
    mutations = {
        "symbol": "sr",
        "cov_fingerprint": "cov-sr-vwap",
        "model_fingerprint": "model-b",
        "predict_params": {"signal_weight": 0.5},
        "horizon": 12,
        "metric_version": "dir_v2",
        "delta_star": 0.10,
        "power": 0.9,
        "alpha": 0.01,
        "var_lr": 1.020,
    }
    for field, value in mutations.items():
        new = pr.new_preregistration(old, {field: value}, **_later_kwargs())
        assert new.prereg_id != old.prereg_id
        assert re.fullmatch(r"[0-9a-f]{32}", new.prereg_id)
        assert getattr(new, field) == value
        assert new.confirm_from_ts == "2026-10-02 00:00:00"
        assert new.registered_at == "2026-10-02T00:00:00Z"
        assert new.terminal_state is None
        assert new.jev == old.jev
        assert old.prereg_id != new.prereg_id
        assert getattr(old, field) != value
        claimed = dataclasses.asdict(old)
        claimed[field] = value
        with pytest.raises(ValueError, match="prereg_immutable"):
            pr.validate_reuse(old, claimed)
    assert old.confirm_from_ts == "2026-10-01 00:00:00"
    assert old.horizon == 24


def test_38_var_lr_change_recomputes_n_and_rejects_mismatch():
    old = pr.register(_fields(), [])
    new = pr.new_preregistration(old, {"var_lr": 1.020}, **_later_kwargs())
    assert new.n_confirm_required == n_required(var_d=1.020, vif=1.0, delta=0.08)
    assert new.n_confirm_required == 986
    with pytest.raises(ValueError):
        pr.new_preregistration(
            old,
            {"var_lr": 1.020, "n_confirm_required": 1199},
            **_later_kwargs(),
        )


def test_38_same_frozen_fields_may_reuse_id():
    old = pr.register(_fields(), [])
    pr.validate_reuse(old, dataclasses.asdict(old))


def test_register_rejects_delta_star_other_than_008():
    with pytest.raises(ValueError):
        pr.register(_fields(delta_star=0.10), [])
    with pytest.raises(ValueError):
        pr.register(_fields(power=0.9), [])
    with pytest.raises(ValueError):
        pr.register(_fields(alpha=0.01), [])
    # 0.80 == 0.8，字面量比较必须放行。
    rec = pr.register(_fields(power=0.8), [])
    assert rec.power == 0.8
    assert rec.delta_star == 0.08
    assert rec.alpha == 0.05


def test_mechanism_round_trips_through_register():
    rec = pr.register(
        _fields(mechanism="库存下降抬升近月", predicted_direction="up", n_planned=12),
        [],
    )
    assert rec.mechanism == "库存下降抬升近月"
    assert rec.predicted_direction == "up"
    assert rec.n_planned == 12
    copied = pr.new_preregistration(rec, {"horizon": 12}, **_later_kwargs())
    assert copied.mechanism == rec.mechanism
    assert copied.predicted_direction == rec.predicted_direction
    assert copied.n_planned == rec.n_planned
    assert copied.horizon == 12
    with pytest.raises(ValueError):
        pr.new_preregistration(rec, {"mechanism": "另一条机制"}, **_later_kwargs())
    with pytest.raises(ValueError):
        pr.register(_fields(mechanism=""), [])
    with pytest.raises(ValueError):
        pr.register(_fields(predicted_direction=""), [])
    with pytest.raises(ValueError):
        pr.register(_fields(n_planned=-1), [])
    with pytest.raises(ValueError):
        pr.register(_fields(n_planned=True), [])
    assert pr.register(_fields(), []).n_planned is None
    assert pr.register(_fields(n_planned=0), []).n_planned == 0


def test_register_rejects_mismatched_n_and_free_text_conditions():
    with pytest.raises(ValueError):
        pr.register(_fields(n_confirm_required=10), [])
    with pytest.raises(ValueError):
        pr.register(_fields(kill_condition="dir_acc below 0.5"), [])
    with pytest.raises(ValueError):
        pr.register(_fields(promote_condition="looks good"), [])
    with pytest.raises(ValueError):
        pr.register(_fields(kill_condition={"field": "dir_acc"}), [])
    with pytest.raises(ValueError):
        pr.register(_fields(promote_condition={"threshold": 0.08}), [])
    with pytest.raises(ValueError):
        pr.register(
            _fields(kill_condition={"field": 1, "threshold": 0.5}), [])
    with pytest.raises(ValueError):
        pr.register(
            _fields(promote_condition={"field": "d_mean", "threshold": True}),
            [],
        )


def test_register_freezes_matching_n_and_leaves_existing_untouched():
    existing = []
    rec = pr.register(_fields(n_confirm_required=1199), existing)
    assert existing == []
    assert rec.n_confirm_required == 1199
    assert rec.confirm_from_ts.encode("utf-8") == b"2026-10-01 00:00:00"
    assert rec.registered_at.encode("utf-8") == b"2026-10-01T00:00:00Z"
    assert rec.terminal_state is None
    assert rec.jev is None
    again = pr.register(_fields(), [rec])
    assert again.prereg_id != rec.prereg_id


def test_new_preregistration_rejects_non_forward_boundary_and_non_frozen_changes():
    old = pr.register(_fields(), [])
    with pytest.raises(ValueError):
        pr.new_preregistration(
            old, {},
            confirm_from_ts=old.confirm_from_ts,
            registered_at="2026-10-02T00:00:00Z",
        )
    with pytest.raises(ValueError):
        pr.new_preregistration(
            old, {"horizon": 12},
            confirm_from_ts="2026-09-01 00:00:00",
            registered_at="2026-10-02T00:00:00Z",
        )
    with pytest.raises(ValueError):
        pr.new_preregistration(
            old, {"confirm_from_ts": "2026-11-01 00:00:00"},
            **_later_kwargs(),
        )
    with pytest.raises(ValueError):
        pr.new_preregistration(old, {"jev": {"status": "degraded"}}, **_later_kwargs())
    with pytest.raises(ValueError):
        pr.new_preregistration(old, {"kill_condition": {"field": "x", "threshold": 1}}, **_later_kwargs())


# ── 40：no-peek 与提前封账 ────────────────────────────────────


def test_40_peek_gate_rejects_before_n_and_records_audit():
    decision = pr.peek_gate(1198, 1199)
    assert decision.allowed is False
    assert decision.audit["event"] == "no_peek_rejected"
    assert decision.audit["n_actual"] == 1198
    assert decision.audit["n_required"] == 1199

    reached = pr.peek_gate(1199, 1199)
    assert reached.allowed is True
    assert reached.audit is None


def test_40_early_seal_is_underpowered_only_before_n():
    seal = pr.early_seal(500, 1199)
    assert seal.terminal_state == "underpowered"
    assert seal.n_confirm_actual == 500
    assert seal.n_confirm_required == 1199
    assert seal.n_confirm_actual < seal.n_confirm_required
    with pytest.raises(ValueError):
        pr.early_seal(1199, 1199)
    with pytest.raises(ValueError):
        pr.early_seal(1200, 1199)


# ── 44：终态强制只在 require_terminal=True ────────────────────


def test_44_open_row_allowed_until_terminal_required():
    open_row = pr.register(_fields(), [])
    pr.validate_registry([open_row], require_terminal=False)
    with pytest.raises(ValueError):
        pr.validate_registry([open_row], require_terminal=True)

    closed = dataclasses.asdict(open_row)
    closed["terminal_state"] = "underpowered"
    pr.validate_registry([closed], require_terminal=True)
    pr.validate_registry([closed], require_terminal=False)

    mixed_open = dataclasses.asdict(open_row)
    mixed_open["prereg_id"] = "a" * 32
    mixed_open["terminal_state"] = None
    with pytest.raises(ValueError):
        pr.validate_registry([closed, mixed_open], require_terminal=True)
    pr.validate_registry([closed, mixed_open], require_terminal=False)


def test_44_duplicate_id_and_unknown_terminal_fail():
    rec = pr.register(_fields(), [])
    with pytest.raises(ValueError):
        pr.validate_registry([rec, dataclasses.asdict(rec)], require_terminal=False)
    bad = dataclasses.asdict(rec)
    bad["terminal_state"] = "exploratory_unconfirmed"
    with pytest.raises(ValueError):
        pr.validate_registry([bad], require_terminal=False)
    for state in (
        "confirmed",
        "refuted",
        "underpowered",
        "abandoned",
        "timeout",
        "refuted_by_contamination",
    ):
        row = dataclasses.asdict(rec)
        row["terminal_state"] = state
        pr.validate_registry([row], require_terminal=True)


# ── 68：确认集起点、交集、hash、无共同点 ─────────────────────


def test_68_confirm_from_ts_is_byte_stable_and_cutoffs_are_lexicographic():
    raw = "2026-10-01 00:00:00"
    rec = pr.register(_fields(confirm_from_ts=raw), [])
    planned = [
        "2026-09-15 00:00:00",
        "2026-10-01 00:00:00",
        "2026-10-01 02:00:00",
        "2026-09-20 00:00:00",
    ]
    got = pr.confirmation_cutoffs(planned, rec.confirm_from_ts)
    assert got == ["2026-10-01 00:00:00", "2026-10-01 02:00:00"]
    assert rec.confirm_from_ts.encode("utf-8") == raw.encode("utf-8")
    # 不按时间解析：未补零的字符串只做字典序，不得改写成规范时间。
    assert pr.confirmation_cutoffs(["2026-9-30"], "2026-10-01") == ["2026-9-30"]
    # 不靠两边第一个共同点来定起点。
    variant = ["2026-09-01", "2026-10-01", "2026-11-01"]
    baseline = ["2026-11-01", "2026-12-01"]
    assert pr.confirmation_cutoffs(variant, "2026-10-01") == ["2026-10-01", "2026-11-01"]
    assert "2026-11-01" in baseline


def test_68_pair_set_is_intersection_and_hash_tracks_it():
    variant = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    baseline = ["2026-10-03", "2026-10-01", "2026-10-05"]
    paired = pr.pair_cutoffs(variant, baseline)
    assert paired == ["2026-10-01", "2026-10-03"]
    digest = pr.pair_set_hash(paired)
    assert digest == pr.pair_set_hash(["2026-10-01", "2026-10-03"])
    assert digest != pr.pair_set_hash(["2026-10-01"])
    assert digest != pr.pair_set_hash(["2026-10-03", "2026-10-01"])
    assert pr.pair_set_hash([]) is None
    assert pr.pair_set_hash(()) is None
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_68_no_common_cutoff_is_underpowered():
    assert pr.pair_cutoffs(["2026-10-01", "2026-10-02"], ["2026-10-03"]) == []
    row = _passing_row(common_insufficient=True, dm_status="no_common_cutoff", p_value=None)
    assert pr.classify_confirmation(row) == "underpowered"
    assert pr.counts_as_success(row) is False


# ── 个体标签、成功计数、判负文案、Jev 不挡入队 ───────────────


def test_meets_min_info_false_stays_underpowered():
    row = _passing_row(meets_min_info=False, fdr_pass=True, dm_significant=True)
    assert pr.classify_confirmation(row) == "underpowered"
    assert pr.counts_as_success(row) is False


def test_meets_min_info_missing_is_underpowered():
    row = _passing_row(fdr_pass=True)
    del row["meets_min_info"]
    assert "meets_min_info" not in row
    assert pr.classify_confirmation(row) == "underpowered"
    assert pr.counts_as_success(row) is False
    other = _passing_row(meets_min_info="yes")
    assert pr.classify_confirmation(other) == "underpowered"


def test_confirmed_without_fdr_pass_is_not_success():
    row = _passing_row(fdr_pass=False)
    assert pr.classify_confirmation(row) == "confirmed"
    assert pr.counts_as_success(row) is False
    row["fdr_pass"] = None
    assert pr.counts_as_success(row) is False
    del row["fdr_pass"]
    assert pr.counts_as_success(row) is False
    row["fdr_pass"] = True
    assert pr.classify_confirmation(row) == "confirmed"
    assert pr.counts_as_success(row) is True


def test_invalid_test_is_underpowered_and_valid_miss_is_refuted():
    assert pr.classify_confirmation(_passing_row(pairing_valid=False)) == "underpowered"
    assert pr.classify_confirmation(
        _passing_row(missingness_admissible=False)) == "underpowered"
    assert pr.classify_confirmation(
        _passing_row(protocol_compatible=False)) == "underpowered"
    assert pr.classify_confirmation(
        _passing_row(dm_status="insufficient_common", p_value=None)) == "underpowered"
    assert pr.classify_confirmation(
        _passing_row(dm_status="set_mismatch_ok")) == "confirmed"
    assert pr.classify_confirmation(_passing_row(dm_significant=False)) == "refuted"
    assert pr.classify_confirmation(_passing_row(gate_pass=False)) == "refuted"
    assert pr.classify_confirmation(_passing_row(p_value=None)) == "refuted"
    assert pr.classify_confirmation(_passing_row(covariates_used=False)) == "refuted"
    assert pr.classify_confirmation(_passing_row(p_value=0.0)) == "confirmed"


def test_classify_priority_and_sample_shortfall():
    short = _passing_row(n_confirm_actual=10, contaminated=True)
    assert pr.classify_confirmation(short) == "refuted_by_contamination"
    assert pr.classify_confirmation(_passing_row(early_sealed=True)) == "underpowered"
    assert pr.classify_confirmation(
        _passing_row(n_confirm_actual=1198)) == "underpowered"
    with pytest.raises(ValueError):
        pr.classify_confirmation(_passing_row(run_mode="exploration"))
    refuted = _passing_row(dm_significant=False, fdr_pass=True)
    assert pr.classify_confirmation(refuted) == "refuted"
    assert pr.counts_as_success(refuted) is False


def test_judgment_note_refuted_is_fixed_text():
    assert pr.judgment_note("refuted") == REFUTED_NOTE
    assert "小效应无效" in pr.judgment_note("refuted")
    assert pr.judgment_note("refuted").startswith("未在预定样本量上检出优于基线的效应")


def test_skip_suggested_does_not_block_queue():
    rec = pr.register(_fields(), [])
    exploration = pr.queue_decision(
        {"skip_suggested": True}, [], run_mode="exploration")
    assert exploration.accepted is True
    assert exploration.run_label == "exploratory_unconfirmed"

    confirmation = pr.queue_decision(
        {"prereg_id": rec.prereg_id, "skip_suggested": True},
        [rec],
        run_mode="confirmation",
    )
    assert confirmation.accepted is True
    assert confirmation.reason is None

    blocked = pr.queue_decision(
        {"skip_suggested": True}, [rec], run_mode="confirmation")
    assert blocked.accepted is False
    assert blocked.reason == "no_prereg_id"
