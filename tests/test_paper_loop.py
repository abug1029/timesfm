"""paper_loop universe contract: core/watch stay in 2-star list."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.prediction_scheme import list_by_stars  # noqa: E402
from scripts.paper_loop import CORE, WATCH  # noqa: E402


class TestPaperLoopUniverse(unittest.TestCase):
    def test_core_and_watch_are_two_star(self):
        two = set(list_by_stars(2))
        for s in CORE + WATCH:
            self.assertIn(s, two, f"{s} left 2-star list; update paper_loop + docs")

    def test_core_excludes_boundary_eg_rb(self):
        self.assertNotIn("eg", CORE)
        self.assertNotIn("rb", CORE)


if __name__ == "__main__":
    unittest.main()
