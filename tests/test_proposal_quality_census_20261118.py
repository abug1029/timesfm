"""只读计数。census 不读期望数字，也不决定退出码。"""
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from proposal_quality_census import RUN_IDS, census

FP = "f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5"


def _layout(root, with_prescreen):
    run_id = RUN_IDS[0]
    dest = root / "task_FM" / "experiments" / run_id / "results" / "gen_0" / "peer0" / "proposals"
    dest.mkdir(parents=True)
    (dest / "m_vor.json").write_text(
        json.dumps({"schema": "fm.hypothesis_proposal.v1", "symbol": "m"}),
        encoding="utf-8")
    (dest / "bad.json").write_text("{", encoding="utf-8")
    if with_prescreen:
        (dest / "m_vor.prescreen.json").write_text(
            json.dumps({"status": "degraded", "note": "TypeSafe API 超时"}),
            encoding="utf-8")
    verdicts = root / "task_FM" / "config" / "aligned_verdicts.jsonl"
    verdicts.parent.mkdir(parents=True)
    rows = [
        {"status": "ok", "protocol_fingerprint": FP, "dir_acc": 0},
        {"status": "ok", "protocol_fingerprint": FP, "dir_acc": False},
        {"status": "ok", "protocol_fingerprint": FP},
    ]
    verdicts.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    done = root / "data" / "cache" / "aligned_pending.done.jsonl"
    done.parent.mkdir(parents=True)
    done.write_text(
        json.dumps({"enqueued_at": "2026-11-17T01:00:00", "src_run": run_id}) + "\n"
        + json.dumps({"enqueued_at": "2026-11-18T01:00:00", "src_run": "other"}) + "\n",
        encoding="utf-8")


def test_census_fixture_counts_and_missing_runs_are_zero(tmp_path):
    _layout(tmp_path, True)
    body = census(str(tmp_path))
    assert body["proposal_json_excluding_prescreen"] == 2
    assert body["hypothesis_v1"] == 1
    assert body["unparseable_proposal_json"] == 1
    assert body["prescreen_files"] == 1
    assert body["prescreen_all_degraded_timeout"] is True
    assert body["dir_acc_zero_rows_current_ok"] == 1
    assert body["direction_field"] == "dir_acc"
    assert body["done_enqueued_at_on_2026_11_17_or_18"] == 2
    assert body["done_src_run_in_window"] == 1
    assert len(body["runs"]) == 15
    assert body["runs"][0]["proposal_json_excluding_prescreen"] == 2
    assert all(row["proposal_json_excluding_prescreen"] == 0 for row in body["runs"][1:])
    assert "dir_ok" not in json.dumps(body)


def test_prescreen_flag_false_when_no_prescreen_files(tmp_path):
    _layout(tmp_path, False)
    assert census(str(tmp_path))["prescreen_all_degraded_timeout"] is False


def test_script_source_has_no_dir_ok_and_ledger_lives_in_main():
    text = Path(ROOT, "scripts", "proposal_quality_census.py").read_text(encoding="utf-8")
    assert "dir_ok" not in text
    before_main = text.split("def main")[0]
    for number in ("894", "879", "196"):
        assert number not in before_main
    supervised = list(Path(ROOT, "scripts").glob("sup_*.py"))
    supervised.append(Path(ROOT, "scripts", "praxist_supervisor.py"))
    for script in supervised:
        assert "proposal_quality_census" not in script.read_text(encoding="utf-8")
