"""PR-B6 提案质量门评分测试

口径: v2 verdict 不含 pf/ev/ic，评分一律基于 gate_pass / decided_at /
cov_override / symbol 等 v2 可观测字段。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402


def _v(symbol, cov, gate_pass, decided_at, status="ok", vid=None):
    """创建 verdict 测试夹具。

    当 gate_pass=True 时，必须包含 pass_variants 严格定义所需的全部字段：
    - run_mode="confirmation" (排除 exploration)
    - fdr_pass=True
    - p_value=0.01 (非 None)
    否则 symbol_has_pass 不会计入该 verdict。
    """
    v = {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": vid or ("%s_%s" % (symbol, cov)),
        "symbol": symbol, "cov_override": cov, "cov_family": "f",
        "status": status, "gate_pass": gate_pass, "decided_at": decided_at,
    }
    # 当 gate_pass=True 时，补充 pass_variants 严格定义所需字段
    if gate_pass:
        v["run_mode"] = "confirmation"
        v["fdr_pass"] = True
        v["p_value"] = 0.01
    return v


def _prop(symbol="m", cov="vor", **over):
    p = {"schema": "fm.hypothesis_proposal.v1", "symbol": symbol,
         "cov_override": cov, "covariate_family": "volatility",
         "mechanism": "x" * 50,
         "symbol_fit": "适配", "kill_condition": "ev<0",
         "promote_condition": "gate"}
    p.update(over)
    return p


class TestQualityScoreComponents:
    """逐项评分"""

    def test_novel_combo_gets_novelty_bonus(self):
        """未测过的组合 +3"""
        score, bd = S._proposal_quality_gate(_prop(cov="brand_new"), {})
        assert bd["novel_combo"] == 3.0

    def test_tested_combo_loses_novelty_bonus(self):
        """已测过的组合无新颖分"""
        snap = {"m_vor": _v("m", "vor", False, "2026-09-01T00:00:00")}
        _, bd = S._proposal_quality_gate(_prop(cov="vor"), snap)
        assert bd["novel_combo"] == 0.0

    def test_symbol_with_pass_gets_bonus(self):
        """该品种有过成功协变量 +5"""
        snap = {"m_oi": _v("m", "oi", True, "2026-09-01T00:00:00")}
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["symbol_has_pass"] == 5.0

    def test_symbol_without_pass_no_bonus(self):
        """该品种无成功协变量 → 无加分"""
        snap = {"m_oi": _v("m", "oi", False, "2026-09-01T00:00:00")}
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["symbol_has_pass"] == 0.0

    def test_mechanism_complete_gets_bonus(self):
        """机制论证齐全 +3"""
        _, bd = S._proposal_quality_gate(_prop(), {})
        assert bd["mechanism_complete"] == 3.0

    def test_mechanism_incomplete_no_bonus(self):
        """缺 promote_condition → 无机制分"""
        _, bd = S._proposal_quality_gate(_prop(promote_condition=""), {})
        assert bd["mechanism_complete"] == 0.0

    def test_prescreen_plausibility_bonus(self, tmp_path):
        """prescreen plausibility=0.8 → +8"""
        pdir = tmp_path / "proposals"
        pdir.mkdir()
        prop_path = pdir / "m_vor.json"
        prop_path.write_text("{}", encoding="utf-8")
        prop_path.with_suffix(".prescreen.json").write_text(
            json.dumps({"status": "success", "mechanism_plausibility": 0.8}),
            encoding="utf-8")

        _, bd = S._proposal_quality_gate(_prop(), {}, proposal_path=str(prop_path))
        assert bd["prescreen"] == pytest.approx(8.0)

    def test_prescreen_missing_is_zero_not_error(self):
        """无 prescreen 文件 → 0 分，不抛异常"""
        _, bd = S._proposal_quality_gate(_prop(), {}, proposal_path="/nonexistent/x.json")
        assert bd["prescreen"] == 0.0

    def test_prescreen_out_of_range_ignored(self, tmp_path):
        """plausibility 超出 [0,1] → 视为缺失（防止污染评分）"""
        prop_path = tmp_path / "m_vor.json"
        prop_path.write_text("{}", encoding="utf-8")
        prop_path.with_suffix(".prescreen.json").write_text(
            json.dumps({"status": "success", "mechanism_plausibility": 7.5}),
            encoding="utf-8")

        _, bd = S._proposal_quality_gate(_prop(), {}, proposal_path=str(prop_path))
        assert bd["prescreen"] == 0.0


class TestQualityPenalties:
    """失败惩罚"""

    def test_cov_recent_fail_penalty(self):
        """该 cov 在其他品种最近 3 次全失败 → -20"""
        snap = {
            "a_vor": _v("a", "vor", False, "2026-09-01T00:00:00"),
            "b_vor": _v("b", "vor", False, "2026-09-02T00:00:00"),
            "c_vor": _v("c", "vor", False, "2026-09-03T00:00:00"),
        }
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["cov_recent_fail"] == -20.0

    def test_cov_recent_fail_needs_full_window(self):
        """只有 2 次失败（不足窗口）→ 不扣分"""
        snap = {
            "a_vor": _v("a", "vor", False, "2026-09-01T00:00:00"),
            "b_vor": _v("b", "vor", False, "2026-09-02T00:00:00"),
        }
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["cov_recent_fail"] == 0.0

    def test_cov_recent_fail_broken_by_one_pass(self):
        """窗口内有任一次过门 → 不扣分"""
        snap = {
            "a_vor": _v("a", "vor", False, "2026-09-01T00:00:00"),
            "b_vor": _v("b", "vor", True, "2026-09-02T00:00:00"),
            "c_vor": _v("c", "vor", False, "2026-09-03T00:00:00"),
        }
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["cov_recent_fail"] == 0.0

    def test_symbol_recent_fail_penalty(self):
        """该品种最近 5 次全失败 → -15"""
        snap = {}
        for i in range(5):
            snap["m_c%d" % i] = _v("m", "c%d" % i, False,
                                   "2026-09-0%dT00:00:00" % (i + 1))
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["symbol_recent_fail"] == -15.0

    def test_symbol_recent_fail_uses_most_recent(self):
        """窗口取最近 5 条：早先的过门不在窗口内，仍扣分"""
        snap = {"m_old": _v("m", "old", True, "2026-01-01T00:00:00")}
        for i in range(5):
            snap["m_c%d" % i] = _v("m", "c%d" % i, False,
                                   "2026-09-0%dT00:00:00" % (i + 1))
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["symbol_recent_fail"] == -15.0

    def test_non_ok_verdicts_ignored(self):
        """error/timeout 裁决不计入失败窗口（不是'失败'，是无效）"""
        snap = {
            "a_vor": _v("a", "vor", False, "2026-09-01T00:00:00", status="error"),
            "b_vor": _v("b", "vor", False, "2026-09-02T00:00:00", status="timeout"),
            "c_vor": _v("c", "vor", False, "2026-09-03T00:00:00", status="error"),
        }
        _, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert bd["cov_recent_fail"] == 0.0

    def test_score_is_sum_of_breakdown(self):
        """总分等于各项之和"""
        snap = {
            "a_vor": _v("a", "vor", False, "2026-09-01T00:00:00"),
            "b_vor": _v("b", "vor", False, "2026-09-02T00:00:00"),
            "c_vor": _v("c", "vor", False, "2026-09-03T00:00:00"),
        }
        score, bd = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert score == pytest.approx(sum(bd.values()))

    def test_worst_case_is_negative(self):
        """最差组合（跨品种全败 + 品种全败）应为净负 → 会被阈值拦截"""
        snap = {}
        for i in range(5):
            snap["m_c%d" % i] = _v("m", "c%d" % i, False,
                                   "2026-09-0%dT00:00:00" % (i + 1))
        for i, s in enumerate(["a", "b", "c"]):
            snap["%s_vor" % s] = _v(s, "vor", False,
                                    "2026-09-0%dT00:00:00" % (i + 1))
        score, _ = S._proposal_quality_gate(_prop(symbol="m", cov="vor"), snap)
        assert score < S.MIN_QUALITY_SCORE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
