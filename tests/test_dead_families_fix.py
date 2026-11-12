"""Tests for _dead_families fix — spec §4.6

Binds to real _dead_families() and _family_confirmatory_counts() in sup_evidence.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from scripts.sup_evidence import _dead_families, _family_confirmatory_counts
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, effective_n,
)

_FP = CURRENT_PROTOCOL_FINGERPRINT


def _make_row(symbol="jd", cov="vor", cov_family="momentum",
              status="ok", gate_pass=False, n=500, n_eff=None,
              fp=None, dm_status="ok", admissibility_rule="some_rule"):
    """Helper to build a verdict-like row for _family_confirmatory_counts."""
    row = {
        "symbol": symbol,
        "cov_override": cov,
        "covariate": cov,
        "cov_family": cov_family,
        "status": status,
        "gate_pass": gate_pass,
        "n": n,
        "protocol_fingerprint": fp or _FP,
        "dm_status": dm_status,
        "admissibility_rule": admissibility_rule,
    }
    if n_eff is not None:
        row["n_eff"] = n_eff
    return row


class TestFamilyConfirmatoryCounts:
    """Tests for _family_confirmatory_counts — the core counting function."""

    def test_duplicate_rows_counted_once_per_unique_cov(self):
        """4 duplicate rows for same (symbol, cov) → fam_ok=1, not 4."""
        rows = [
            _make_row(cov="vor", cov_family="momentum"),
            _make_row(cov="vor", cov_family="momentum"),
            _make_row(cov="vor", cov_family="momentum"),
            _make_row(cov="vor", cov_family="momentum"),
        ]
        fam_ok, fam_pass = _family_confirmatory_counts(rows)
        assert fam_ok.get("momentum", 0) == 1  # only 1 unique cov

    def test_unknown_cov_excluded(self):
        """3 real covs + 1 UNKNOWN → fam_ok=3 (UNKNOWN excluded)."""
        rows = [
            _make_row(cov="vor", cov_family="momentum"),
            _make_row(cov="rsi", cov_family="momentum"),
            _make_row(cov="macd", cov_family="momentum"),
            _make_row(cov="", cov_family="momentum"),  # UNKNOWN cov
        ]
        fam_ok, fam_pass = _family_confirmatory_counts(rows)
        assert fam_ok.get("momentum", 0) == 3

    def test_terminal_status_excluded(self):
        """status in TERMINAL_STATUSES → excluded from counting."""
        rows = [
            _make_row(cov="vor", cov_family="momentum", status="error"),
            _make_row(cov="rsi", cov_family="momentum", status="insufficient_data"),
            _make_row(cov="macd", cov_family="momentum", status="fatal_error"),
            _make_row(cov="atr", cov_family="momentum", status="ok"),
        ]
        fam_ok, fam_pass = _family_confirmatory_counts(rows)
        assert fam_ok.get("momentum", 0) == 1  # only "atr" is status=ok

    def test_old_fp_excluded(self):
        """Old protocol fingerprint → excluded."""
        rows = [
            _make_row(cov="vor", fp="old_fp_1"),
            _make_row(cov="rsi", fp="old_fp_2"),
            _make_row(cov="macd", fp=_FP),  # current fp
        ]
        fam_ok, fam_pass = _family_confirmatory_counts(rows)
        assert fam_ok.get("momentum", 0) == 1  # only current fp

    def test_n_lt_350_excluded(self):
        """n < 350 → excluded from effective rows."""
        rows = [
            _make_row(cov="vor", n=200),
            _make_row(cov="rsi", n=100),
            _make_row(cov="macd", n=500),  # n >= 350
        ]
        fam_ok, fam_pass = _family_confirmatory_counts(rows)
        assert fam_ok.get("momentum", 0) == 1  # only macd passes n filter

    def test_gate_pass_counted(self):
        """gate_pass=True rows counted in fam_pass."""
        rows = [
            _make_row(cov="vor", gate_pass=True),
            _make_row(cov="rsi", gate_pass=False),
            _make_row(cov="macd", gate_pass=True),
        ]
        fam_ok, fam_pass = _family_confirmatory_counts(rows)
        assert fam_ok.get("momentum", 0) == 3
        assert fam_pass.get("momentum", 0) == 2


class TestDeadFamilies:
    """Tests for _dead_families — the public API."""

    def test_4_unique_covs_triggers_death(self):
        """4 unique valid covs with status=ok + 0 gate_pass → dead."""
        snapshot = {
            f"key_{i}": _make_row(cov=f"cov_{i}", cov_family="momentum")
            for i in range(4)
        }
        dead = _dead_families(snapshot)
        assert "momentum" in dead

    def test_3_unique_covs_not_dead(self):
        """3 unique covs → not dead (need >= 4)."""
        snapshot = {
            f"key_{i}": _make_row(cov=f"cov_{i}", cov_family="momentum")
            for i in range(3)
        }
        dead = _dead_families(snapshot)
        assert "momentum" not in dead

    def test_duplicates_dont_trigger_death(self):
        """4 rows but only 1 unique cov → not dead."""
        snapshot = {
            f"key_{i}": _make_row(cov="vor", cov_family="momentum")
            for i in range(4)
        }
        dead = _dead_families(snapshot)
        assert "momentum" not in dead

    def test_gate_pass_prevents_death(self):
        """4 unique covs but 1 gate_pass → not dead."""
        snapshot = {
            "k0": _make_row(cov="cov_0", gate_pass=False),
            "k1": _make_row(cov="cov_1", gate_pass=False),
            "k2": _make_row(cov="cov_2", gate_pass=False),
            "k3": _make_row(cov="cov_3", gate_pass=True),  # 1 pass
        }
        dead = _dead_families(snapshot)
        assert "momentum" not in dead
