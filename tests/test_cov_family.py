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
