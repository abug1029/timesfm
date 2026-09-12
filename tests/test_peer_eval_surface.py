"""Scheme A: peers never launch TimesFM (C5 / Task 7).

Locks the task-package capability surface:
- staged_protocols *.launch_allowed is false
- evaluation_tools.peer is not in the peer role tool_scope
- audit result_ownership is proposal files, not evaluation_summary.json
Host slow-loop still knows the evaluator via task_entrypoints + plugins.
"""
import os

import yaml

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = os.path.join(FM_ROOT, "task_FM", "task.yaml")
ROLE = os.path.join(FM_ROOT, "task_FM", "roles", "peer_generalist", "role.yaml")
AUDIT = os.path.join(
    FM_ROOT, "task_FM", "audit_rules", "scope_and_protocol", "audit.yaml"
)


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_all_staged_protocols_launch_allowed_false():
    stages = _load(TASK)["evaluation"]["staged_protocols"]
    assert stages, "staged_protocols must be non-empty"
    for name, proto in stages.items():
        assert proto.get("launch_allowed") is False, (
            f"{name}.launch_allowed must be false "
            "(scheme A: peers never launch TimesFM)"
        )


def test_peer_role_has_no_evaluation_tools():
    scope = _load(ROLE)["role"]["tool_scope"]
    assert "evaluation_tools.peer" not in scope


def test_audit_result_ownership_is_proposals_not_eval_summary():
    checks = {c["id"]: c for c in _load(AUDIT)["audit"]["checks"]}
    assert "result_ownership" in checks
    assert "immutable_boundary" in checks
    criteria = " ".join(checks["result_ownership"]["criteria"])
    assert "proposals" in criteria
    assert "results/**/proposals/*.json" in criteria
    assert "fm.hypothesis_proposal.v1" in criteria
    assert "evaluation_summary.json" not in criteria


def test_host_evaluator_entrypoint_retained():
    spec = _load(TASK)
    command = spec["task_entrypoints"]["evaluation"]["command"]
    assert command, "HOST slow loop still needs the evaluator command"
    plugins = spec["praxist_plugins"]["evaluations"]
    assert plugins, "HOST slow loop still needs praxist_plugins.evaluations"
