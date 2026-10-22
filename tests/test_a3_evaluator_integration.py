"""A3 集成测试：proposal_gate plugin 接入 Praxist 原生 evaluator Step 0。

验证:
1. 脏提案不进 frontier（validate_proposal 返回 invalid）
2. 合法提案通过 evaluator Step 0
3. run.py 入口正确调用 Step 0（dirty proposal exit code 3）
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(FM_ROOT, "task_FM", ".praxist", "plugins")
EVAL_DIR = os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval")

sys.path.insert(0, PLUGIN_DIR)
sys.path.insert(0, os.path.join(FM_ROOT, "scripts"))

from proposal_gate.validate import validate_proposal


class TestStep0Direct:
    """Direct plugin invocation tests."""

    def test_dirty_proposal_not_in_frontier_via_evaluator(self):
        """脏提案不进 frontier（接入 Praxist 原生 evaluator Step 0）。"""
        proposal = {"variant_id": "dirty", "stem": "测试"}
        result = validate_proposal(proposal)
        assert result["valid"] is False
        assert "validation_signal" in result

    def test_clean_proposal_passes_evaluator(self):
        """合法提案通过 evaluator Step 0。"""
        proposal = {
            "variant_id": "RB_rsi_state",
            "stem": "rb",
            "mechanism": "momentum-based signal on RSI divergence",
            "symbol_fit": "rb",
            "symbol": "RB",
            "cov_override": "rsi_state",
            "predicted_direction": "up",
        }
        result = validate_proposal(proposal)
        assert result["valid"] is True, f"clean proposal rejected: {result}"

    def test_chinese_in_rejected_field(self):
        """中文泄漏被拦截。"""
        proposal = {
            "variant_id": "test_zh",
            "mechanism": "动量信号",  # Chinese in mechanism
            "symbol_fit": "rb",
            "symbol": "RB",
            "cov_override": "rsi_state",
            "predicted_direction": "up",
        }
        result = validate_proposal(proposal)
        assert result["valid"] is False
        assert "validation_signal" in result


class TestStep0Wiring:
    """Test run.py wiring: dirty proposal exits with code 3."""

    def test_run_py_rejects_dirty_proposal(self):
        """run.py Step 0 rejects dirty proposal with exit code 3."""
        dirty = {
            "variant_id": "dirty_test",
            "mechanism": "测试机制",  # Chinese = dirty
            "symbol_fit": "rb",
            "symbol": "RB",
            "cov_override": "rsi_state",
            "predicted_direction": "up",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cand_path = os.path.join(tmpdir, "cand.json")
            with open(cand_path, "w") as f:
                json.dump(dirty, f)
            env = {
                **os.environ,
                "PYTHONPATH": f"{PLUGIN_DIR}:{os.path.join(FM_ROOT, 'scripts')}:{EVAL_DIR}",
                "FM_EVAL_SLOT_HELD": "1",  # bypass mem_guard eval slot check
            }
            result = subprocess.run(
                [sys.executable, os.path.join(EVAL_DIR, "run.py"),
                 "--output-dir", tmpdir, "--candidate", cand_path],
                capture_output=True, text=True,
                cwd=EVAL_DIR,
                env=env,
            )
            assert result.returncode == 3, f"expected exit 3, got {result.returncode}: {result.stderr}"
            out_file = os.path.join(tmpdir, "evaluation_summary.json")
            assert os.path.exists(out_file)
            with open(out_file) as f:
                summary = json.load(f)
            assert summary["status"] == "invalid_proposal"


class TestA4BackupGate:
    """Verify sup_harvest.py still has A4 backup gate."""

    def test_sup_harvest_retains_validate_call(self):
        """sup_harvest.py 仍调用 validate_proposal_dict（A4 备用闸）。"""
        harvest_path = os.path.join(FM_ROOT, "scripts", "sup_harvest.py")
        with open(harvest_path, encoding="utf-8") as f:
            content = f.read()
        assert "validate_proposal_dict" in content, "A4 backup gate missing from sup_harvest.py"
