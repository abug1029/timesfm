"""Tests for covariate family resolver."""
from cascade.cov_family import resolve_cov_family, load_covariate_pool


def test_pool_exact_match():
    pool = load_covariate_pool()
    assert resolve_cov_family({"cov_override": "calendar_cyclical"}, pool) == "calendar"
    assert resolve_cov_family({"cov_override": "oi"}, pool) == "inventory"


def test_name_heuristic():
    assert resolve_cov_family({"cov_override": "new_atr_x", "variant_id": "m_new_atr_x"}) == "volatility"


def test_unknown_fallback():
    assert resolve_cov_family({"cov_override": "zzz", "variant_id": "foo"}) == "unknown"


def test_pool_format_pool_key():
    """Test dict format with 'pool' key (using name that heuristic can't match)"""
    pool_data = {"pool": [{"name": "custom_x", "family": "calendar"}]}
    # Level 1 should match "custom_x" -> "calendar" (no heuristic keyword matches)
    assert resolve_cov_family({"cov_override": "custom_x"}, pool_data) == "calendar"


def test_pool_format_list():
    """Test list format (using name that heuristic can't match)"""
    pool_data = [{"name": "custom_y", "family": "term_structure"}]
    assert resolve_cov_family({"cov_override": "custom_y"}, pool_data) == "term_structure"


def test_level1_invalid_family_fallback():
    """Level 1 match but invalid family should fall through to Level 2"""
    pool = {"covariates": [{"name": "test_cov", "family": "invalid_family"}]}
    # Should skip Level 1 (invalid family) and match via heuristic (atr -> volatility)
    assert resolve_cov_family({"cov_override": "test_cov_atr"}, pool) == "volatility"


def test_empty_inputs():
    """Empty cov_override and variant_id"""
    assert resolve_cov_family({}) == "unknown"
    assert resolve_cov_family({"cov_override": "", "variant_id": ""}) == "unknown"


def test_no_substring_false_positives():
    """Short keywords should not match substrings"""
    # "oi" should NOT match "point" or "voice"
    assert resolve_cov_family({"cov_override": "point", "variant_id": "voice"}) == "unknown"
    # "vol" should NOT match "evolve"
    assert resolve_cov_family({"cov_override": "evolve"}) == "unknown"
    # "bb" should NOT match "cabbage"
    assert resolve_cov_family({"cov_override": "cabbage"}) == "unknown"
    # "std" should NOT match "standard"
    assert resolve_cov_family({"cov_override": "standard"}) == "unknown"
