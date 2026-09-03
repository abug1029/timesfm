import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from goal_dsl import evaluate_goal

SNAP = {"symbols_hit": {"m", "rb"}, "families_hit": {"rsi_state", "ccl"},
        "pass_variant_pf_ratios": [1.2, 1.08],
        "variants": {"a": {"pf": 1.2}},
        "cycles_done": 1, "cpu_hours_used": 4.0, "tokens_used_m": 12.0}

def test_all_conditions_met():
    ok, _ = evaluate_goal(["len(symbols_hit) >= 2",
                           "min(pass_variant_pf_ratios) > 1.05"], SNAP)
    assert ok is True

def test_condition_unmet():
    ok, why = evaluate_goal(["len(symbols_hit) >= 3"], SNAP)
    assert ok is False and "len(symbols_hit) >= 3" in why[0]

def test_empty_min_is_unmet_not_error():
    snap = dict(SNAP)
    snap["pass_variant_pf_ratios"] = []
    ok, why = evaluate_goal(["min(pass_variant_pf_ratios) > 1.05"], snap)
    assert ok is False
    assert any("unmet" in w and "forbidden" not in w and "eval error" not in w for w in why)

def test_variants_name_allowed():
    ok, _ = evaluate_goal(["len(variants) >= 1"], SNAP)
    assert ok is True

def test_injection_rejected():
    for expr in ["__import__('os').system('x')", "(lambda: 1)()",
                 "open('/etc/passwd')", "symbols_hit.__class__"]:
        ok, why = evaluate_goal([expr], SNAP)
        assert ok is False and any("forbidden" in w for w in why)
