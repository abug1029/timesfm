"""品种分级与有界目标。只调用不读文件的 symbol_goal_tier。"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import yaml

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

import preregistry as pr  # noqa: E402
import praxist_supervisor as sup  # noqa: E402

GOAL_YAML = project_root / "scripts" / "praxist_goal.yaml"


def _passing_row(**overrides):
    row = {
        "symbol": "ss",
        "run_mode": "confirmation",
        "contaminated": False,
        "early_sealed": False,
        "n_confirm_actual": 1116,
        "n_confirm_required": 1116,
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
        "fdr_pass": True,
    }
    row.update(overrides)
    return row


def test_three_tiers_use_the_fixed_labels():
    success = _passing_row(fdr_pass=True)
    predictable = sup.symbol_goal_tier([success], "ss")
    assert predictable["tier"] == "可预测"
    assert predictable["n_confirmed_variants"] == 1

    needs_more = sup.symbol_goal_tier([], "ss")
    assert needs_more["tier"] == "需更多样本"
    assert needs_more["n_confirmed_variants"] == 0
    assert "效应无效" not in needs_more["tier"]

    n_required = pr.n_confirm_required_for_symbol("ss")
    capped = sup.symbol_goal_tier([], "ss", max_history_n=n_required)
    assert capped["tier"] == "需更多样本"
    short = sup.symbol_goal_tier([], "ss", max_history_n=n_required - 1)
    assert short["tier"] == "当前不可验证"
    assert short["n_confirmed_variants"] == 0

    # 已有成功变体时，历史上限再短也是可预测。
    still = sup.symbol_goal_tier([success], "ss", max_history_n=n_required - 1)
    assert still["tier"] == "可预测"
    assert still["n_confirmed_variants"] == 1


def test_missing_fdr_pass_is_not_a_success():
    false_row = _passing_row(fdr_pass=False)
    none_row = _passing_row(fdr_pass=None)
    missing = _passing_row()
    del missing["fdr_pass"]
    exploratory = _passing_row(run_mode="exploration", fdr_pass=True)
    out = sup.symbol_goal_tier(
        [false_row, none_row, missing, exploratory], "ss")
    assert out["n_confirmed_variants"] == 0
    assert out["tier"] == "需更多样本"
    assert pr.classify_confirmation(false_row) == "confirmed"
    assert pr.counts_as_success(false_row) is False

    counted = sup.symbol_goal_tier(
        [false_row, missing, _passing_row(fdr_pass=True)], "ss")
    assert counted["n_confirmed_variants"] == 1
    assert counted["tier"] == "可预测"


def test_ss_threshold_comes_from_n_confirm_required_for_symbol(monkeypatch):
    assert pr.n_confirm_required_for_symbol("ss") == 1116
    seen = []

    def wrapped(symbol):
        seen.append(symbol)
        return 1116

    monkeypatch.setattr(pr, "n_confirm_required_for_symbol", wrapped)
    short = sup.symbol_goal_tier([], "ss", max_history_n=1115)
    assert seen == ["ss"]
    assert short["tier"] == "当前不可验证"
    assert sup.symbol_goal_tier([], "ss", max_history_n=1116)["tier"] == "需更多样本"

    # 门槛必须采用函数返回值，不能在分级里另写 1115 或 1116。
    seen.clear()

    def sentinel(symbol):
        seen.append(symbol)
        return 50

    monkeypatch.setattr(pr, "n_confirm_required_for_symbol", sentinel)
    assert sup.symbol_goal_tier([], "ss", max_history_n=49)["tier"] == "当前不可验证"
    assert sup.symbol_goal_tier([], "ss", max_history_n=50)["tier"] == "需更多样本"
    assert seen == ["ss", "ss"]


def test_tier_function_does_not_read_symbol_status():
    src = inspect.getsource(sup.symbol_goal_tier)
    assert "symbol_status" not in src
    assert "open(" not in src
    snap = inspect.getsource(sup.build_snapshot)
    assert "symbol_goal_tier(" in snap
    assert "0.51" not in snap
    assert "n_gate_pass >= 10" not in snap
    assert "n_tier_a_or_b >= 8" not in snap
    assert "symbol_status" not in snap
    assert "phase2_pass = False" in snap
    assert "phase3_pass = False" in snap


def test_goal_yaml_drops_old_bar_and_unbounded_budget():
    raw = GOAL_YAML.read_text(encoding="utf-8")
    assert "0.51" not in raw
    assert "999999" not in raw
    assert "2099-12-31" not in raw
    assert "每品种至少 1 个经 family 封账的确认变体" in raw
    assert "tier>=8" in raw
    assert "multi_seed" in raw
    assert "decay" in raw
    goal = yaml.safe_load(raw)["goal"]
    assert goal["success_condition"] == ["all_symbols_pass_phase1"]
    assert goal["budgets"]["max_cycles"] == 2000
    assert goal["budgets"]["cpu_hours"] == 2000
    assert goal["budgets"]["token_budget_m"] == 200
    assert goal["budgets"]["deadline"] == "2028-10-02"
    assert goal["cadence"]["survivors_per_cycle"] == 3
    assert len(goal["cadence"]["target_symbols"]) == 24
