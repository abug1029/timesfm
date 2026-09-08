"""协变量池注册表测试 (2026-09-08)

断言 covariate_pool.json 契约:
- schema/family/status/mechanism 合法
- active 协变量 == evaluator.VALID_COVARIATES (active ∩ 已实现)
- archived 协变量被拒绝并给出明确原因
- 每个 active 协变量在 features.py 有显式分派 (单路径不再静默降级 CCL)
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "task_FM", "evaluations", "fm_eval"))
sys.path.insert(0, ROOT)

import evaluator as ev  # noqa: E402

POOL_PATH = os.path.join(ROOT, "task_FM", "config", "covariate_pool.json")


@pytest.fixture(scope="module")
def pool():
    with open(POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


def active_set(pool):
    return {n for n, v in pool["covariates"].items() if v.get("status") == "active"}


def archived_set(pool):
    return {n for n, v in pool["covariates"].items() if v.get("status") == "archived"}


def test_pool_schema(pool):
    assert pool.get("schema") == "fm.covariate_pool.v1"
    fams = set(pool["families"])
    covs = pool["covariates"]
    assert len(covs) >= 30
    for name, v in covs.items():
        assert v.get("family") in fams, f"{name} family 非法"
        assert v.get("status") in {"active", "experimental", "archived"}, f"{name} status 非法"
        assert v.get("mechanism") and len(v["mechanism"]) >= 15, f"{name} mechanism 缺失/过短"


def test_active_equals_valid_covariates(pool):
    # active ∩ 已实现 应恰好等于 evaluator 校验集
    assert active_set(pool) == ev.VALID_COVARIATES


def test_no_archived_in_valid(pool):
    assert not (archived_set(pool) & ev.VALID_COVARIATES)


def test_archived_candidate_rejected(monkeypatch):
    monkeypatch.setitem(ev.ARCHIVED_COVARIATES, "vor", "测试归档原因")
    monkeypatch.setattr(ev, "VALID_COVARIATES", ev.VALID_COVARIATES - {"vor"})
    ok, msg = ev.validate_candidate(
        {"symbol": "m", "cov_override": "vor", "max_points": 400, "stage": "aligned"})
    assert not ok
    assert "归档" in msg


def test_unknown_candidate_rejected():
    ok, msg = ev.validate_candidate(
        {"symbol": "m", "cov_override": "bogus_covariate", "max_points": 400, "stage": "aligned"})
    assert not ok


def test_active_covariates_have_features_dispatch(pool):
    src = open(os.path.join(ROOT, "cascade", "features.py"), encoding="utf-8").read()
    missing = [n for n in active_set(pool) if ('"%s"' % n) not in src]
    assert not missing, f"协变量在 features.py 无显式分派: {missing}"
