"""Tests for registry_lib shared constants and helpers — SSOT."""
import pytest
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode, effective_n,
)


def test_terminal_statuses_contents():
    assert TERMINAL_STATUSES == frozenset({"insufficient_data", "error", "fatal_error"})


def test_current_fingerprint():
    assert CURRENT_PROTOCOL_FINGERPRINT == "f02b2a43"


def test_canonical_cov_override_priority():
    assert canonical_cov({"cov_override": "rsi", "covariate": "macd"}) == "rsi"


def test_canonical_cov_fallback_to_covariate():
    assert canonical_cov({"covariate": "macd"}) == "macd"


def test_canonical_cov_default_unknown():
    assert canonical_cov({}) == "UNKNOWN"


def test_canonical_mode_run_mode_priority():
    assert canonical_mode({"run_mode": "exploration", "mode": "confirmatory"}) == "exploration"


def test_canonical_mode_fallback_to_mode():
    assert canonical_mode({"mode": "confirmatory"}) == "confirmatory"


def test_canonical_mode_default_confirmatory():
    assert canonical_mode({}) == "confirmatory"


def test_effective_n_normal():
    assert effective_n({"n_eff": 73}) == 73


def test_effective_n_fallback_to_n():
    assert effective_n({"n": 588}) == 588


def test_effective_n_string_conversion():
    assert effective_n({"n_eff": "350"}) == 350


def test_effective_n_none_returns_zero():
    assert effective_n({"n_eff": None}) == 0


def test_effective_n_missing_returns_zero():
    assert effective_n({}) == 0


def test_effective_n_invalid_string_returns_zero():
    assert effective_n({"n_eff": "abc"}) == 0
