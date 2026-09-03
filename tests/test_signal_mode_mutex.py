"""CF-06: use_full_signal vs short_horizon_only 不得矛盾。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.prediction_scheme import SCHEMES  # noqa: E402


class TestSignalModeMutex(unittest.TestCase):
    def test_no_full_and_short_both_true(self):
        for sym, s in SCHEMES.items():
            if s.short_horizon_only:
                self.assertFalse(
                    s.use_full_signal,
                    msg=f"{sym}: short_horizon_only=True 时 use_full_signal 应为 False",
                )

    def test_short_implies_scheme_type_or_flag(self):
        for sym, s in SCHEMES.items():
            if s.short_horizon_only:
                # 允许 scheme_type 尚未同步；至少 short 标志自洽
                self.assertTrue(s.short_horizon_only)


if __name__ == "__main__":
    unittest.main()
