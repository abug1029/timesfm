import json
from datetime import datetime, timedelta
from pathlib import Path

from cascade.eval_grid import accept_baseline_file


def _grid(n, start="2026-01-01 10:00:00"):
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def _write(path, cutoffs, fp="fp", **extra):
    with open(path, "w", encoding="utf-8") as f:
        for cutoff in cutoffs:
            row = {"cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                   "delta_real": 1.0, "protocol_fingerprint": fp}
            row.update(extra)
            f.write(json.dumps(row) + "\n")


def test_accept_requires_exact_grid_and_fingerprint(tmp_path):
    grid = _grid(4)
    path = tmp_path / "ok.jsonl"
    _write(path, grid, fp="fp")
    ok, _ = accept_baseline_file(str(path), grid, "fp")
    assert ok is True
    bad, reason = accept_baseline_file(str(path), grid, "")
    assert bad is False
    assert "指纹" in reason
    short, _ = accept_baseline_file(str(path), _grid(5), "fp")
    assert short is False
    superset = tmp_path / "super.jsonl"
    _write(superset, grid + ["2026-03-01 10:00:00"], fp="fp")
    over, _ = accept_baseline_file(str(superset), grid, "fp")
    assert over is False


def test_accept_allows_old_rows_without_new_keys(tmp_path):
    grid = _grid(2)
    path = tmp_path / "old.jsonl"
    _write(path, grid, fp="fp")
    ok, _ = accept_baseline_file(str(path), grid, "fp")
    assert ok is True
