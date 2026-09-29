"""Phase 2 (PR-C2) — 研究 family 的登记、封账与 BH-FDR。

spec §4.3 W3.6（v4/v5/v7/v8/v10），行 787-870。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cascade.research_family import (
    FAMILY_CLOSE_AFTER,
    FAMILY_MAX_MEMBERS,
    T_MAX,
    FieldFormatError,
    all_terminal,
    default_family_key,
    family_bh_fdr,
    family_close_at,
    family_report_scope,
    make_family_key,
    make_member,
    make_research_question,
    register_member,
    registration_open,
    research_target_hash,
    resolve_terminal_states,
    seal_deadline,
    seal_family,
)

T0 = datetime(2026, 9, 29, tzinfo=timezone.utc)
KEY = default_family_key("ss")


def _member(vid: str, days: int = 0, key: str = KEY) -> dict:
    return make_member(key, "ss", vid, T0 + timedelta(days=days))


# ── ① family 定义：只有确认检验进 family ────────────────────────


def test_exploration_results_cannot_enter_family():
    """探索期结果不是检验，不产生 p 值声称，不进 family。"""
    with pytest.raises(ValueError, match="探索期"):
        make_member(KEY, "ss", "v1", T0, run_mode="exploration")


def test_default_one_symbol_one_family():
    """默认：一个品种 = 一个研究问题 = 一个 family。"""
    assert default_family_key("ss") == default_family_key("ss")
    assert default_family_key("ss") != default_family_key("rb")


def test_key_is_normalized_but_distinct_per_symbol():
    assert default_family_key("SS ") == default_family_key("ss")
    assert default_family_key("ss") != default_family_key("rb")


# ── research_target_hash 的 v10 序列化规范 ─────────────────────


def test_research_target_hash_is_stable_and_order_frozen():
    a = research_target_hash("ss", "dir", "main_continuous", "v1")
    b = research_target_hash("SS", "DIR", " Main_Continuous ", "V1")
    assert a == b, "规范化应吃掉大小写与两端空白"
    assert len(a) == 64, "SHA-256 十六进制"


def test_research_target_hash_rejects_separator_in_field():
    """字段含 '|' 会造成碰撞，必须 fail-loud（v10 明文）。"""
    for bad in ("a|b", "x|y|z"):
        with pytest.raises(FieldFormatError):
            research_target_hash(bad, "dir", "main", "v1")


def test_research_target_hash_distinguishes_each_component():
    base = research_target_hash("ss", "dir", "main", "v1")
    assert base != research_target_hash("rb", "dir", "main", "v1")
    assert base != research_target_hash("ss", "mape", "main", "v1")
    assert base != research_target_hash("ss", "dir", "second", "v1")
    assert base != research_target_hash("ss", "dir", "main", "v2")


def test_research_target_hash_ignores_observation_content():
    """v8：只哈希研究目标本身，不含观测数据与截止时间。

    新增 cutoff / 修订历史 bar 不得创建新 family，否则同一研究问题被数据
    自然增长拆成多个 family，防规避意图被瓦解。
    """
    # 调用方传入的 data_version / sample_fingerprint 不参与本函数签名
    import inspect

    params = set(inspect.signature(research_target_hash).parameters)
    assert params == {
        "symbol",
        "target_var",
        "price_series_def",
        "adjust_roll_rule_version",
    }
    assert "cutoff" not in params
    assert "data_version" not in params


def test_family_key_change_only_on_research_question_change():
    """family 边界（v7）：换目标变量/期限开新 family，其余不开。"""
    rth = research_target_hash("ss", "dir", "main", "v1")
    base = make_family_key("ss", make_research_question("dir", 24, rth))
    same = make_family_key("ss", make_research_question("dir", 24, rth))
    other_horizon = make_family_key("ss", make_research_question("dir", 48, rth))
    other_target = make_family_key("ss", make_research_question("mape", 24, rth))
    assert base == same
    assert base != other_horizon
    assert base != other_target


# ── ② 注册截止：时间与成员上限并用，先到者为准 ─────────────────


def test_close_at_is_90_days_after_first_registration():
    members, _ = register_member([], _member("v1"), T0)
    assert family_close_at(members) == T0 + FAMILY_CLOSE_AFTER
    assert FAMILY_CLOSE_AFTER == timedelta(days=90)


def test_close_at_anchored_on_first_member_not_latest():
    """close_at 由**首**成员决定，后续成员不推迟截止。"""
    members, _ = register_member([], _member("v1", 0), T0)
    members, _ = register_member(members, _member("v2", 30), T0 + timedelta(days=30))
    assert family_close_at(members) == T0 + FAMILY_CLOSE_AFTER


def test_registration_open_before_close_at():
    members, _ = register_member([], _member("v1"), T0)
    ok, _ = registration_open(members, T0 + timedelta(days=89))
    assert ok


def test_registration_closed_at_close_at():
    members, _ = register_member([], _member("v1"), T0)
    ok, reason = registration_open(members, T0 + timedelta(days=90))
    assert not ok
    assert "close_at" in reason


def test_member_cap_is_20():
    members: list[dict] = []
    for i in range(FAMILY_MAX_MEMBERS):
        members, status = register_member(members, _member(f"v{i}"), T0)
        assert status == "registered"
    assert len(members) == 20
    ok, reason = registration_open(members, T0)
    assert not ok
    assert "max_members" in reason


def test_first_come_first_served_cap_beats_time():
    """并用、先到者为准：成员上限先触顶时，即使未到 90 天也不得再收。"""
    members: list[dict] = []
    for i in range(FAMILY_MAX_MEMBERS):
        members, _ = register_member(members, _member(f"v{i}"), T0)
    _, status = register_member(members, _member("overflow"), T0 + timedelta(days=1))
    assert status.startswith("rejected:")
    assert "max_members" in status


def test_rejected_member_not_added():
    members, _ = register_member([], _member("v1"), T0)
    after, status = register_member(members, _member("v2"), T0 + timedelta(days=200))
    assert status.startswith("rejected:")
    assert len(after) == 1


# ── 终态与 T_max ───────────────────────────────────────────────


def test_t_max_is_180_days_from_registration():
    assert T_MAX == timedelta(days=180)


def test_member_times_out_at_its_own_t_max():
    members, _ = register_member([], _member("v1", 0), T0)
    before = resolve_terminal_states(members, T0 + T_MAX - timedelta(days=1))
    assert before[0]["status"] == "registered"

    after = resolve_terminal_states(members, T0 + T_MAX)
    assert after[0]["status"] == "timeout"
    assert after[0]["p_value"] == 1.0


def test_t_max_anchored_per_member_not_family():
    """单成员时钟：晚注册的成员用自己的 registered_at 起算 T_max。"""
    members, _ = register_member([], _member("v1", 0), T0)
    members, _ = register_member(members, _member("v2", 60), T0 + timedelta(days=60))
    at_180 = resolve_terminal_states(members, T0 + T_MAX)
    assert at_180[0]["status"] == "timeout"
    assert at_180[1]["status"] == "registered", "v2 才注册 60 天，未到自身 T_max"


def test_terminal_states_are_the_four_declared():
    members = [
        {**_member("v1"), "status": "confirmed", "p_value": 0.01},
        {**_member("v2"), "status": "refuted", "p_value": 0.60},
        {**_member("v3"), "status": "abandoned", "p_value": 1.0},
        {**_member("v4"), "status": "timeout", "p_value": 1.0},
    ]
    assert all_terminal(members)
    sealed, adj = seal_family(members, T0)
    assert all(m["family_sealed_at"] for m in sealed)
    assert set(adj) == {"v1", "v2", "v3", "v4"}


def test_cannot_seal_before_all_terminal():
    members = [
        {**_member("v1"), "status": "confirmed", "p_value": 0.01},
        {**_member("v2"), "status": "registered", "p_value": None},
    ]
    with pytest.raises(ValueError, match="终态"):
        seal_family(members, T0)


def test_seal_deadline_is_close_at_plus_t_max():
    members, _ = register_member([], _member("v1"), T0)
    assert seal_deadline(members) == T0 + FAMILY_CLOSE_AFTER + T_MAX


# ── BH-FDR ─────────────────────────────────────────────────────


def test_bh_fdr_counts_abandoned_and_timeout_in_k():
    """abandoned / timeout 仍计入 K，否则「结果不好就丢掉」= 缩小 K = p-hacking。"""
    members = [
        {**_member("v1"), "status": "confirmed", "p_value": 0.01},
        {**_member("v2"), "status": "confirmed", "p_value": 0.02},
        {**_member("v3"), "status": "abandoned", "p_value": 1.0},
        {**_member("v4"), "status": "timeout", "p_value": 1.0},
    ]
    adj = family_bh_fdr(members, fdr_q=0.10)
    # K=4：p=0.01 -> 0.01*4/1=0.04；p=0.02 -> 0.02*4/2=0.04
    assert adj["v1"] == pytest.approx(0.04)
    assert adj["v2"] == pytest.approx(0.04)
    assert adj["v3"] == pytest.approx(1.0)
    assert adj["v4"] == pytest.approx(1.0)


def test_bh_fdr_is_monotone_in_sorted_order():
    members = [
        {**_member(f"v{i}"), "status": "confirmed", "p_value": p}
        for i, p in enumerate([0.001, 0.01, 0.05, 0.2, 0.9])
    ]
    adj = family_bh_fdr(members, fdr_q=0.10)
    ordered = [adj[f"v{i}"] for i in range(5)]
    assert ordered == sorted(ordered), "校正后 p 值应随原始 p 单调不减"


def test_bh_fdr_single_member_adjusted_equals_raw():
    """K=1 时 BH 无校正：p_adj = p * 1/1 = p。"""
    members = [{**_member("v1"), "status": "confirmed", "p_value": 0.9}]
    assert family_bh_fdr(members, fdr_q=0.10)["v1"] == pytest.approx(0.9)


def test_bh_fdr_never_exceeds_one():
    """p*K/i 可能远超 1，校正结果必须上截断到 1.0（不得报出 >1 的概率）。"""
    members = [
        {**_member(f"v{i}"), "status": "confirmed", "p_value": 0.6}
        for i in range(8)
    ]
    adj = family_bh_fdr(members, fdr_q=0.10)
    assert all(0.0 <= p <= 1.0 for p in adj.values())
    assert max(adj.values()) <= 1.0


def test_bh_fdr_equal_p_values_reduce_to_raw_p():
    """全部 p 相等时，step-up 后的最小候选是 p*K/K = p。"""
    members = [
        {**_member(f"v{i}"), "status": "confirmed", "p_value": 0.9}
        for i in range(4)
    ]
    adj = family_bh_fdr(members, fdr_q=0.10)
    assert all(p == pytest.approx(0.9) for p in adj.values())


def test_bh_fdr_missing_p_value_treated_as_one():
    members = [{**_member("v1"), "status": "confirmed", "p_value": None}]
    assert family_bh_fdr(members)["v1"] == 1.0


def test_empty_family_yields_no_correction():
    assert family_bh_fdr([]) == {}


def test_seal_is_one_shot_and_idempotent():
    members = [
        {**_member("v1"), "status": "confirmed", "p_value": 0.01},
        {**_member("v2"), "status": "refuted", "p_value": 0.5},
    ]
    sealed1, adj1 = seal_family(members, T0)
    sealed2, adj2 = seal_family(sealed1, T0)
    assert adj1 == adj2, "重复封账不得改变校正结果"
    assert [m["p_value_family_adjusted"] for m in sealed1] == [
        m["p_value_family_adjusted"] for m in sealed2
    ]


# ── 范围声明 ───────────────────────────────────────────────────


def test_cross_symbol_scope_statement_present():
    """跨品种错误率范围必须显式声明（spec W3.6①）。"""
    scope = family_report_scope()
    assert "不跨品种合并" in scope
    assert "品种内" in scope


def test_different_symbols_do_not_share_family():
    """默认不跨品种合并：两个品种的 family_key 必须不同。"""
    ss = default_family_key("ss")
    rb = default_family_key("rb")
    assert ss != rb
