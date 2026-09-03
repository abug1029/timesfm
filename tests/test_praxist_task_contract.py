"""PRAXIST 任务包契约校验测试 (P0a, TDD 2026-09-01)

契约原则 (docs/praxist_integration_plan.md §2):
- 预注册: 评估口径先于实验锁定, GREEN 必须以全量 walk-forward + 经济口径为准
- 红线: peers 唯一可写区为 scripts/praxist_ws/ 与 reports/praxist/
"""
import os
import subprocess
import sys

import yaml

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(FM_ROOT, "config", "praxist_task.yaml")
VALIDATOR = os.path.join(FM_ROOT, "scripts", "praxist_validate_task.py")


def _load():
    with open(CONTRACT, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_contract_file_exists_and_parses():
    assert os.path.exists(CONTRACT), "config/praxist_task.yaml 不存在"
    data = _load()
    assert isinstance(data, dict) and data, "契约文件必须是非空映射"


def test_objective_pre_registered():
    d = _load()
    obj = d["objective"]
    # 预注册主指标: 扣滑点 EV 为主, PF 为次 (G004/Phase 11 裁决口径)
    assert obj["primary"] == "ev_after_slippage"
    assert obj["secondary"] == "profit_factor"
    # GREEN 必须全量 WF + 经济口径 (B1/Phase13/15 教训)
    assert obj["green_requires_full_walkforward"] is True


def test_constraints_thresholds():
    d = _load()
    c = d["constraints"]
    assert c["min_samples"] >= 350
    assert c["min_ic"] >= 0.05
    assert c["multiple_comparison"] in ("bonferroni", "holm", "benjamini-hochberg")
    assert c["maxdd_caliber"] == "cumprod_clamp"


def test_write_paths_within_redlines():
    d = _load()
    allowed = {"scripts/praxist_ws", "reports/praxist"}
    assert set(d["write_paths"]) <= allowed, "peers 可写区不得越红线"


def test_evidence_maturity_gates():
    d = _load()
    stages = {s["stage"]: s for s in d["evidence_maturity"]}
    assert "diagnostic" in stages
    assert "full_walkforward" in stages
    # 全量阶段必须有硬门
    assert stages["full_walkforward"]["gate"]


def test_generation_close_policy_sealed():
    d = _load()
    assert d["generation_close_policy"] == "sealed"


def test_validator_passes_real_contract():
    r = subprocess.run([sys.executable, VALIDATOR], capture_output=True, text=True)
    assert r.returncode == 0, f"validator 应通过真实契约: {r.stdout}{r.stderr}"


def test_validator_rejects_violations(tmp_path):
    bad_cases = [
        {"objective": {"primary": "diagnostic_pf"}, "constraints": {}, "write_paths": ["cascade/daily_model.py"], "evidence_maturity": [], "generation_close_policy": "open"},
    ]
    for i, case in enumerate(bad_cases):
        p = tmp_path / f"bad_{i}.yaml"
        p.write_text(yaml.safe_dump(case), encoding="utf-8")
        r = subprocess.run([sys.executable, VALIDATOR, str(p)], capture_output=True, text=True)
        assert r.returncode != 0, f"validator 必须拒绝违规契约: {case}"
