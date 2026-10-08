"""paper_loop universe contract: core/watch 必须是已固化品种。

2026-10-08：原断言为 "core/watch stay in 2-star list"，依赖已退役的
`list_by_stars(2)`。改为断言落在已固化集合 `list_solidified()` 内 ——
这才是 paper_loop 真正需要的契约（有固化方案才能跑预测）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.prediction_scheme import list_solidified  # noqa: E402
from scripts.paper_loop import CORE, WATCH  # noqa: E402


class TestPaperLoopUniverse(unittest.TestCase):
    def test_core_and_watch_are_solidified(self):
        solidified = set(list_solidified())
        for s in CORE + WATCH:
            self.assertIn(s, solidified,
                          f"{s} 无固化方案，paper_loop 跑不了；请先固化或移出主盘")

    def test_core_excludes_boundary_eg_rb(self):
        self.assertNotIn("eg", CORE)
        self.assertNotIn("rb", CORE)

    def test_no_overlap_core_watch(self):
        self.assertFalse(set(CORE) & set(WATCH))


if __name__ == "__main__":
    unittest.main()