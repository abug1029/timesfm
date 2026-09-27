"""PR-B6 协变量跨品种失败拦截测试

规则: 该协变量在其他品种失败 >= 3 次且从未在任一品种过门 → 拦截。
例外: 任一品种过门即放行（品种特异性优先）。
口径: v2 无 ev 字段，"失败" = status=ok 且 gate_pass=False。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402


def _v(symbol, cov, gate_pass, decided_at, status="ok"):
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": "%s_%s" % (symbol, cov),
        "symbol": symbol, "cov_override": cov, "cov_family": "f",
        "status": status, "gate_pass": gate_pass, "decided_at": decided_at,
    }


class TestCovariateFilter:
    def test_blocks_after_three_cross_symbol_failures(self):
        """3 个其他品种失败且无过门 → 拦截"""
        snap = {"%s_vor" % s: _v(s, "vor", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(["a", "b", "c"])}

        blocked, n_fail, n_pass = S._covariate_filter_check("vor", "m", snap)
        assert (n_fail, n_pass) == (3, 0)
        assert blocked is True

    def test_two_failures_not_enough(self):
        """仅 2 次失败 → 放行"""
        snap = {"%s_vor" % s: _v(s, "vor", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(["a", "b"])}

        blocked, n_fail, _ = S._covariate_filter_check("vor", "m", snap)
        assert n_fail == 2
        assert blocked is False

    def test_any_pass_anywhere_exempts(self):
        """该协变量在任一品种过门 → 不拦截（品种特异性例外）"""
        snap = {
            "a_vor": _v("a", "vor", True, "2026-09-01T00:00:00"),
            "b_vor": _v("b", "vor", False, "2026-09-02T00:00:00"),
            "c_vor": _v("c", "vor", False, "2026-09-03T00:00:00"),
            "d_vor": _v("d", "vor", False, "2026-09-04T00:00:00"),
        }
        blocked, n_fail, n_pass = S._covariate_filter_check("vor", "m", snap)
        assert (n_fail, n_pass) == (3, 1)
        assert blocked is False

    def test_own_symbol_failures_not_counted(self):
        """本品种自身的失败不计入跨品种计数"""
        snap = {
            "m_vor": _v("m", "vor", False, "2026-09-01T00:00:00"),
            "a_vor": _v("a", "vor", False, "2026-09-02T00:00:00"),
            "b_vor": _v("b", "vor", False, "2026-09-03T00:00:00"),
        }
        blocked, n_fail, _ = S._covariate_filter_check("vor", "m", snap)
        assert n_fail == 2, "m 自身的失败不应计入"
        assert blocked is False

    def test_other_covariate_failures_not_counted(self):
        """其他协变量的失败不计入"""
        snap = {"%s_oi" % s: _v(s, "oi", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(["a", "b", "c"])}

        blocked, n_fail, _ = S._covariate_filter_check("vor", "m", snap)
        assert n_fail == 0
        assert blocked is False

    def test_error_verdicts_not_counted(self):
        """error/timeout 裁决不算失败"""
        snap = {"%s_vor" % s: _v(s, "vor", False, "2026-09-0%dT00:00:00" % (i + 1),
                                 status="error")
                for i, s in enumerate(["a", "b", "c"])}

        blocked, n_fail, _ = S._covariate_filter_check("vor", "m", snap)
        assert n_fail == 0
        assert blocked is False

    def test_empty_snapshot_not_blocked(self):
        """空快照 → 放行（冷启动不得被门挡住）"""
        blocked, n_fail, n_pass = S._covariate_filter_check("vor", "m", {})
        assert (blocked, n_fail, n_pass) == (False, 0, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
