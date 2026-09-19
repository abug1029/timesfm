import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from registry_lib import (
    append_verdict, load_snapshot, pass_variants, dead_variants,
    queue_enqueue, queue_claim, queue_ack, queue_recover, queue_load,
    in_flight_ids, validate_verdict,
    read_verdicts, update_batch_verdicts,
    make_error_tombstone, make_timeout_tombstone,
)

def _v(vid, **kw):
    base = {"variant_id": vid, "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "n": 380, "pf": 1.2, "ev": 0.02, "maxdd": -0.1,
            "dir_acc": 0.55, "gate_pass": True, "ic": 0.1, "decided_at": "t",
            "checkpoint_path": "cp", "slow_loop_pid": 1, "git_rev": "-",
            "schema": "fm.aligned_verdict.v1", "status": "ok"}
    base.update(kw); return base

def _row(vid="v1"):
    return {"variant_id": vid, "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "stage": "aligned", "checkpoint_path": "cp/v1.jsonl",
            "enqueued_at": "t1", "src_run": "r1"}

def test_validate_and_append(tmp_path):
    reg = tmp_path / "verdicts.jsonl"
    assert validate_verdict(_v("x")) == []
    errs = validate_verdict({"variant_id": "x"})
    assert any("missing" in e for e in errs)
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("x"))
    snap = load_snapshot(str(reg))
    assert snap["x"]["pf"] == 1.2

def test_snapshot_latest_wins(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("x", pf=1.0))
        append_verdict(f, _v("x", pf=1.5))
    assert load_snapshot(str(reg))["x"]["pf"] == 1.5

def test_pass_dead_split_no_data_not_dead(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("a", gate_pass=True, ev=0.02))
        append_verdict(f, _v("b", gate_pass=False, ev=-0.01))
        append_verdict(f, _v("c", gate_pass=False, n=0, status="no_data"))
    snap = load_snapshot(str(reg))
    assert [v["variant_id"] for v in pass_variants(snap)] == ["a"]
    assert dead_variants(snap) == {"b"}
    assert "c" not in dead_variants(snap)

def test_queue_claim_ack_recover(tmp_path):
    pending = str(tmp_path / "pending.jsonl")
    inflight = str(tmp_path / "inprogress.jsonl")
    done = str(tmp_path / "done.jsonl")
    assert queue_enqueue(pending, [_row("v1"), _row("v2")], dead=set(), existing=set()) == 2
    row = queue_claim(pending, inflight)
    assert row["variant_id"] == "v1"
    assert [r["variant_id"] for r in queue_load(pending)] == ["v2"]
    assert [r["variant_id"] for r in queue_load(inflight)] == ["v1"]
    assert in_flight_ids(pending, inflight) == {"v1", "v2"}
    # 崩溃: recover 把 v1 前置回 pending
    n = queue_recover(pending, inflight)
    assert n == 1
    assert [r["variant_id"] for r in queue_load(pending)] == ["v1", "v2"]
    assert queue_load(inflight) == []
    row = queue_claim(pending, inflight)
    queue_ack(pending, inflight, row, done)
    assert queue_load(inflight) == []
    assert "v1" in open(done, encoding="utf-8").read()
    assert [r["variant_id"] for r in queue_load(pending)] == ["v2"]
    # 去重
    assert queue_enqueue(pending, [_row("v2")], dead=set(), existing=set()) == 0

def test_mid_claim_crash_recoverable(tmp_path):
    """Simulate crash after inprogress write but before pending trim; recover dedupes."""
    pending = str(tmp_path / "pending.jsonl")
    inflight = str(tmp_path / "inprogress.jsonl")
    assert queue_enqueue(pending, [_row("v1"), _row("v2")], dead=set(), existing=set()) == 2
    # mid-claim state: row already in inprogress, still at head of pending
    with open(inflight, "w", encoding="utf-8") as f:
        f.write(json.dumps(_row("v1"), ensure_ascii=False) + "\n")
    assert [r["variant_id"] for r in queue_load(pending)] == ["v1", "v2"]
    assert [r["variant_id"] for r in queue_load(inflight)] == ["v1"]
    n = queue_recover(pending, inflight)
    assert n == 1
    assert [r["variant_id"] for r in queue_load(pending)] == ["v1", "v2"]
    assert queue_load(inflight) == []

def test_tolerates_partial_line(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("a"))
        f.write('{"variant_id": "partial')
    assert set(load_snapshot(str(reg))) == {"a"}
    q = str(tmp_path / "pending.jsonl")
    with open(q, "a", encoding="utf-8") as f:
        f.write(json.dumps(_row()) + "\n")
        f.write('{"variant_id": "hal')
    assert [r["variant_id"] for r in queue_load(q)] == ["v1"]
    assert queue_enqueue(q, [_row()], dead=set(), existing=set()) == 0


# ---------------------------------------------------------------------------
# v2 tests
# ---------------------------------------------------------------------------

def test_read_verdicts_skips_bad_line(tmp_path):
    p = tmp_path / "v.jsonl"
    p.write_text(
        '{"variant_id": "v1", "batch_id": "b1"}\n'
        "not json\n"
        '{"variant_id": "v2", "batch_id": "b1"}\n',
        encoding="utf-8",
    )
    recs = read_verdicts(str(p))
    assert [r["variant_id"] for r in recs] == ["v1", "v2"]


def _v2_complete(vid="v1", bid="b1", **kw):
    """Complete v2 verdict with all required fields."""
    base = {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": vid,
        "symbol": "m",
        "cov_override": None,
        "cov_family": "unknown",
        "status": "ok",
        "stage": "aligned",
        "batch_id": bid,
        "n": 100,
        "n_eff": 80,
        "dir_acc": 0.55,
        "weighted_dir_acc": 0.6,
        "gate_pass": True,
        "p_value": 0.01,
        "fdr_pass": None,
        "migrated_pass": None,
        "endpoint_mape": None,
        "endpoint_bias_pct": None,
        "path_corr": None,
        "mae": None,
        "mape": None,
        "decay": None,
        "checkpoint_path": None,
        "slow_loop_pid": None,
        "git_rev": None,
        "decided_at": None,
    }
    base.update(kw)
    return base


def test_append_verdict_path_dedup(tmp_path):
    p = str(tmp_path / "v.jsonl")
    append_verdict(p, _v2_complete("v1", "b1"))
    append_verdict(p, _v2_complete("v1", "b1"))
    assert len(read_verdicts(p)) == 1


def test_update_batch_verdicts_metrics_sync(tmp_path):
    p = str(tmp_path / "v.jsonl")
    append_verdict(p, _v2_complete("v1", "b1", metrics={"dir_acc": 0.5}))
    update_batch_verdicts(p, "b1", {"v1": {"fdr_pass": True}})
    rec = read_verdicts(p)[0]
    assert rec["fdr_pass"] is True
    assert rec["metrics"]["fdr_pass"] is True
    assert rec["metrics"]["dir_acc"] == 0.5


def test_update_batch_no_metrics_key_does_not_invent(tmp_path):
    p = str(tmp_path / "v.jsonl")
    append_verdict(p, _v2_complete("v1", "b1"))
    update_batch_verdicts(p, "b1", {"v1": {"fdr_pass": True}})
    rec = read_verdicts(p)[0]
    assert rec["fdr_pass"] is True
    assert "metrics" not in rec  # do not invent if missing


def test_pass_variants_v2_needs_fdr(tmp_path):
    snap = {
        "a": {
            "variant_id": "a",
            "schema": "fm.aligned_verdict.v2",
            "status": "ok",
            "gate_pass": True,
            "fdr_pass": True,
        },
        "b": {
            "variant_id": "b",
            "schema": "fm.aligned_verdict.v2",
            "status": "ok",
            "gate_pass": True,
            "fdr_pass": False,
        },
        "c": {
            "variant_id": "c",
            "schema": "fm.aligned_verdict.v2",
            "status": "ok",
            "gate_pass": True,
            "migrated_pass": True,
            "fdr_pass": True,
        },
    }
    assert {v["variant_id"] for v in pass_variants(snap)} == {"a", "c"}


def test_error_tombstone_has_metrics():
    t = make_error_tombstone("m", "m_rsi", "b1", RuntimeError("boom"))
    assert t["schema"] == "fm.aligned_verdict.v2"
    assert t["status"] == "error" and t["gate_pass"] is False and t["p_value"] == 1.0
    assert t["metrics"]["batch_id"] == "b1"
    assert t.get("baseline_dir_acc") is None
    assert t.get("effective_min") is None
    assert t["metrics"]["baseline_dir_acc"] is None
    assert t["metrics"]["effective_min"] is None
