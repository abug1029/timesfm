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

def test_set_intersection_tier_condition():
    tier1 = ['m', 'ss', 'sr', 'cj', 'jd', 'lh', 'eg', 'rb']
    expr = "len(symbols_hit & {%s}) >= 4" % ",".join(repr(x) for x in tier1)
    # 4 个 1 星 → 达成; 2 星品种 (ao/bu) 不凑数
    snap = dict(SNAP)
    snap["symbols_hit"] = {"ss", "m", "sr", "jd", "ao"}
    ok, _ = evaluate_goal([expr], snap)
    assert ok is True
    snap2 = dict(SNAP)
    snap2["symbols_hit"] = {"ss", "ao", "bu"}
    ok2, why2 = evaluate_goal([expr], snap2)
    assert ok2 is False and "unmet" in why2[0]
