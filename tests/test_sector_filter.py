"""PR-B6 板块级提案拦截测试

板块由 config/sector_map.py 唯一决定（全项目唯一板块表）。
口径: v2 无 ev 字段，"失败" = status=ok 且 gate_pass=False。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402
from config.sector_map import SECTORS, sector_of  # noqa: E402


def _v(symbol, cov, gate_pass, decided_at, status="ok"):
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": "%s_%s" % (symbol, cov),
        "symbol": symbol, "cov_override": cov, "cov_family": "f",
        "status": status, "gate_pass": gate_pass, "decided_at": decided_at,
    }


# agri 板块成员（取自 sector_map，避免测试内硬编码板块表）
AGRI = [s for s in SECTORS["agri"]][:4]


class TestSectorFilter:
    def test_blocks_when_three_sector_symbols_failed(self):
        """同板块 >=3 品种最近裁决未过门 → 拦截"""
        assert len(AGRI) >= 3, "agri 板块成员不足以构造该场景"
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(AGRI[:3])}

        blocked, sector, n_failed = S._sector_filter_check(AGRI[3], snap)
        assert sector == sector_of(AGRI[3])
        assert n_failed == 3
        assert blocked is True

    def test_not_blocked_when_only_two_failed(self):
        """仅 2 个品种失败 → 放行"""
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(AGRI[:2])}

        blocked, _, n_failed = S._sector_filter_check(AGRI[3], snap)
        assert n_failed == 2
        assert blocked is False

    def test_pass_breaks_sector_block(self):
        """板块内任一品种过门 → 不拦截（避免误伤）"""
        snap = {
            AGRI[0] + "_c": _v(AGRI[0], "c", False, "2026-09-01T00:00:00"),
            AGRI[1] + "_c": _v(AGRI[1], "c", False, "2026-09-02T00:00:00"),
            AGRI[2] + "_c": _v(AGRI[2], "c", True, "2026-09-03T00:00:00"),
        }
        blocked, _, n_failed = S._sector_filter_check(AGRI[3], snap)
        assert n_failed == 2
        assert blocked is False

    def test_other_sector_failures_do_not_count(self):
        """其他板块的失败不计入本板块"""
        # 3 个 black_metals 失败，但查询的是 agri 品种
        black = SECTORS["black_metals"][:3]
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(black)}

        blocked, sector, n_failed = S._sector_filter_check("m", snap)
        assert sector == "agri"
        assert n_failed == 0
        assert blocked is False

    def test_unknown_symbol_never_blocked(self):
        """未知品种 (sector='other') 不拦截 —— 板块规则无法适用"""
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(SECTORS["agri"][:3])}

        blocked, sector, _ = S._sector_filter_check("zzz", snap)
        assert sector == "other"
        assert blocked is False

    def test_uses_latest_verdict_per_symbol(self):
        """每品种只看最近一次：早先失败 + 最近过门 → 该品种不算失败"""
        snap = {
            AGRI[0] + "_a": _v(AGRI[0], "a", False, "2026-01-01T00:00:00"),
            AGRI[0] + "_b": _v(AGRI[0], "b", True, "2026-09-01T00:00:00"),
            AGRI[1] + "_a": _v(AGRI[1], "a", False, "2026-09-01T00:00:00"),
            AGRI[2] + "_a": _v(AGRI[2], "a", False, "2026-09-01T00:00:00"),
        }
        blocked, _, n_failed = S._sector_filter_check(AGRI[3], snap)
        assert n_failed == 2, "AGRI[0] 最近一次是过门，不应计入失败"
        assert blocked is False

    def test_error_verdicts_ignored(self):
        """error 裁决不算'失败'，也不参与最近一次判定"""
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1),
                               status="error")
                for i, s in enumerate(AGRI[:3])}
        blocked, _, n_failed = S._sector_filter_check(AGRI[3], snap)
        assert n_failed == 0
        assert blocked is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
