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


def test_spec_9_3_keywords():
    """Spec §9.3 name_hints should match"""
    # Empty pool, rely on heuristic
    assert resolve_cov_family({"cov_override": "roc_x"}) == "momentum"
    assert resolve_cov_family({"cov_override": "ema_cross"}) == "momentum"
    assert resolve_cov_family({"cov_override": "holiday"}) == "calendar"
    assert resolve_cov_family({"cov_override": "spread_x"}) == "term_structure"


# ── D2: task_FM/config/covariate_pool.json 对齐 6 族受控词表 ──

import json
import os

from cascade.cov_family import ALLOWED_FAMILIES

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_task_fm_pool():
    with open(os.path.join(_ROOT, "task_FM", "config", "covariate_pool.json"),
              encoding="utf-8") as f:
        return json.load(f)


def test_task_fm_pool_families_in_controlled_vocab():
    """task_FM 池每个 covariate 的 family 必须落在 6 族受控词表内."""
    pool_json = _load_task_fm_pool()
    for name, v in pool_json["covariates"].items():
        assert v.get("family") in ALLOWED_FAMILIES, name


def test_active_covariates_resolve_no_unknown():
    """D2: task_FM 池 active 协变量逐个 resolve_cov_family, 断言无 unknown 且与池登记一致."""
    pool_json = _load_task_fm_pool()
    list_pool = [{"name": n, "family": v["family"]}
                 for n, v in pool_json["covariates"].items()
                 if v.get("status") == "active"]
    assert list_pool
    for cov in list_pool:
        fam = resolve_cov_family({"cov_override": cov["name"]}, list_pool)
        assert fam != "unknown", cov["name"]
        assert fam == cov["family"], cov["name"]


def test_root_pool_matches_task_fm_pool():
    """根目录 config/covariate_pool.json (cov_family 默认池) 与 task_FM 池保持一致."""
    task_fm = _load_task_fm_pool()
    with open(os.path.join(_ROOT, "config", "covariate_pool.json"),
              encoding="utf-8") as f:
        root = json.load(f)
    root_by_name = {c["name"]: c["family"] for c in root["covariates"]}
    for name, v in task_fm["covariates"].items():
        if v.get("status") == "active":
            assert root_by_name.get(name) == v["family"], name
