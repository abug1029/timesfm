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
    def test_blocks_only_when_all_sector_members_failed(self):
        """板块在 sector_map 中定义的全部品种最近裁决未过门 → 拦截。

        circuit-breaker: 不是"≥ N 个失败"，而是"板块全集失败"。
        防止 2026-09-24 提案饿死重演（当时 ≥3 阈值让三板块全被拦）。
        """
        from config.sector_map import SECTORS
        # 用最小的板块 black_metals (4 个: rb, i, jm, ss) 构造全集失败
        bm = SECTORS["black_metals"]
        assert len(bm) == 4
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(bm)}

        # 查询板块内任一品种
        for sym in bm:
            blocked, sector, n_failed = S._sector_filter_check(sym, snap)
            assert sector == "black_metals"
            assert n_failed == 4
            assert blocked is True

    def test_partial_failure_does_not_block(self):
        """板块部分失败（即便 ≥ 3）不拦截。

        旧语义 "≥3 失败即拦" 导致生产快照三板块全拦（每板块 ≥3 失败）→ 饿死。
        新语义要求板块全集失败才拦，避免这种系统性阻塞。
        """
        # agri 板块 10 个成员, 让其中 9 个失败 → 仍不拦（10 个中 9 个 < 10）
        agri = SECTORS["agri"]
        snap = {"%s_c" % s: _v(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
                for i, s in enumerate(agri[:9])}

        blocked, _, n_failed = S._sector_filter_check("m", snap)
        assert n_failed == 9
        assert blocked is False, "部分失败不得拦截（否则生产快照会全板块被拦）"

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

    def test_sector_with_no_verdicts_never_blocked(self):
        """板块完全没有裁决 → 不拦截（冷启动不应被门挡住）

        无 verdict 时 _latest_verdict_per_symbol 对板块返回空，n_failed=0，
        0 < sector_size → 放行。这是正确的冷启动语义。
        """
        # 空 snapshot：所有板块都没有裁决
        blocked, _, n_failed = S._sector_filter_check("m", {})
        assert n_failed == 0
        assert blocked is False

        # 仅其他板块有裁决，本板块为空
        snap = {"rb_c": _v("rb", "c", False, "2026-09-01T00:00:00"),
                "i_c": _v("i", "c", False, "2026-09-02T00:00:00")}
        # "m" 是 agri 板块，agri 在 snapshot 中无裁决
        blocked, _, n_failed = S._sector_filter_check("m", snap)
        assert n_failed == 0
        assert blocked is False

    def test_only_one_symbol_in_sector_with_verdict(self):
        """板块只有 1 个品种有裁决且失败 → 不拦截（板块未全集失败）

        防止"只观察到一个品种失败就拦整个板块"的过度敏感拦截。
        """
        # black_metals 4 个成员，只有 ss 一个有裁决且失败
        snap = {"ss_c": _v("ss", "c", False, "2026-09-01T00:00:00")}
        blocked, _, n_failed = S._sector_filter_check("rb", snap)
        assert n_failed == 1  # 仅 ss 失败
        assert blocked is False, "板块未全集失败不得拦截"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
