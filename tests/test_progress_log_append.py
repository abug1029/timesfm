import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import monthly_backtest as mb


def test_append_progress_keeps_prior_lines(tmp_path):
    p = tmp_path / "progress.log"
    mb._append_progress(p, "START\n")
    mb._append_progress(p, "SS START\n")
    text = p.read_text(encoding="utf-8")
    assert text.splitlines() == ["START", "SS START"]


def test_append_progress_swallows_oserror(tmp_path):
    p = tmp_path / "no_such_dir" / "progress.log"
    mb._append_progress(p, "X\n")  # 不得抛
