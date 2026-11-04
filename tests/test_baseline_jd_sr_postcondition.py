import json
import os
from datetime import datetime, timedelta

import scripts.sup_evidence as sup_evidence


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as handle:
        for cutoff in cutoffs:
            handle.write(json.dumps({
                "cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                "delta_real": 1.0, "protocol_fingerprint": fp,
            }) + "\n")


def _write_prereg(root, rows):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "preregistry.jsonl"), "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_jd_and_sr_share_one_postcondition(tmp_path, monkeypatch):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    grid = [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(8)]
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    _write_prereg(str(tmp_path), [
        {"prereg_id": "jd1", "symbol": "jd", "confirm_from_ts": "2026-10-03 00:00:00",
         "n_confirm_required": 1199},
        {"prereg_id": "sr1", "symbol": "sr", "confirm_from_ts": "2026-10-03 00:00:00",
         "n_confirm_required": 986},
    ])
    scar = ["2026-10-21 10:00:00", "2026-10-21 12:00:00", "2026-10-21 15:00:00"]
    for symbol in ("jd", "sr"):
        pts = tmp_path / f"baseline_points_{symbol}_nocov.jsonl"
        _write_points(pts, grid)
        before = pts.read_bytes()
        archive = tmp_path / f"baseline_points_{symbol}_nocov.archive_scar.jsonl"
        _write_points(archive, scar)
        tmp = tmp_path / f".baseline_points_{symbol}_nocov.jsonl.tmp"
        _write_points(tmp, scar)
        assert sup_evidence.finalize_baseline_write(symbol, str(pts), str(tmp_path), str(archive)) is False
        assert pts.read_bytes() == before
        assert not tmp.exists()
    source = open("scripts/sup_evidence.py", encoding="utf-8").read()
    accept = open("cascade/eval_grid.py", encoding="utf-8").read()
    finalize_src = source.split("def finalize_baseline_write", 1)[1].split("\ndef ", 1)[0]
    assert "jd" not in finalize_src
    assert "sr" not in finalize_src
    assert "jd" not in accept
    assert "sr" not in accept
