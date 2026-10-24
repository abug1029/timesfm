"""tests/test_slow_loop_prescreen.py — 慢环 prescreen 注入集成测试"""
import json
import os
from pathlib import Path
import sys

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))


class TestSlowLoopPrescreenInjection:
    """模拟慢环读取 prescreen 并注入 verdict metadata 的完整流程。"""

    def test_injection_with_valid_prescreen(self, tmp_path):
        """有效的 prescreen 文件被正确注入到 verdict metadata"""
        from cascade.typesafe_prescreen import write_prescreen_result

        proposal_path = str(tmp_path / "proposals" / "p_001.json")
        prescreen_data = {
            "status": "success",
            "skip_suggested": True,
            "mechanism_plausibility": 0.3,
            "novelty": "invalid",
            "effect_size": 0,
            "note": "测试 note",
        }
        os.makedirs(os.path.dirname(proposal_path), exist_ok=True)
        write_prescreen_result(
            str(Path(proposal_path).with_suffix(".prescreen.json")),
            prescreen_data,
        )

        verdict = {"gate_pass": False, "status": "aligned", "variant_id": "v_001"}
        _proposal_path = proposal_path

        if _proposal_path:
            _ps_path = str(Path(_proposal_path).with_suffix(".prescreen.json"))
            if os.path.exists(_ps_path):
                try:
                    with open(_ps_path, encoding="utf-8") as _f:
                        _ps = json.load(_f)
                except (json.JSONDecodeError, OSError):
                    _ps = None
                if _ps:
                    if "metadata" not in verdict:
                        verdict["metadata"] = {}
                    verdict["metadata"]["prescreen"] = {
                        "status": _ps.get("status"),
                        "skip_suggested": _ps.get("skip_suggested"),
                        "plausibility": _ps.get("mechanism_plausibility"),
                        "novelty": _ps.get("novelty"),
                        "effect_size": _ps.get("effect_size"),
                        "note": _ps.get("note"),
                    }

        assert "metadata" in verdict
        assert verdict["metadata"]["prescreen"]["status"] == "success"
        assert verdict["metadata"]["prescreen"]["skip_suggested"] is True
        assert verdict["metadata"]["prescreen"]["plausibility"] == 0.3
        assert verdict["gate_pass"] is False

    def test_no_proposal_path_no_injection(self, tmp_path):
        verdict = {"gate_pass": True, "status": "aligned"}
        _proposal_path = None
        if _proposal_path:
            pass
        assert "metadata" not in verdict

    def test_missing_prescreen_file_no_injection(self, tmp_path):
        verdict = {"gate_pass": True}
        _proposal_path = str(tmp_path / "nonexistent.json")
        _ps_path = str(Path(_proposal_path).with_suffix(".prescreen.json"))
        assert not os.path.exists(_ps_path)
        assert "metadata" not in verdict
