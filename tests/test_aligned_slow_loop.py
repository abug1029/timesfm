import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import aligned_slow_loop as asl
import registry_lib as rl

def _row():
    return {"variant_id": "m_rsi_state", "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "stage": "aligned",
            "checkpoint_path": "", "enqueued_at": "t1", "src_run": "r1"}

class _FakeResult:
    pass

def _fake_data():
    return {"contract": "M", "points": [{"n": 400, "PF": 1.2, "EV": 0.02,
                                         "MaxDD": -0.1, "DirAcc": 0.55,
                                         "delta_pred": 1, "delta_real": 1}]}

def test_run_aligned_candidate(tmp_path, monkeypatch):
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 400, "PF": 1.2, "EV": 0.02,
                                                       "MaxDD": -0.1, "DirAcc": 0.55})
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    monkeypatch.setattr(asl, "build_summary",
                        lambda s, c: {"status": "ok", "gate_pass": True, "ev": 0.02,
                                      "pf": 1.2, "n": 400, "maxdd": -0.1, "dir_acc": 0.55})
    reg = tmp_path / "verdicts.jsonl"
    verdict = asl.run_aligned_candidate(
        _row(), daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(reg))
    assert verdict["gate_pass"] is True
    assert verdict["variant_id"] == "m_rsi_state"
    snap = rl.load_snapshot(str(reg))
    assert snap["m_rsi_state"]["gate_pass"] is True

def test_once_mode_claim_ack(tmp_path, monkeypatch):
    reg = tmp_path / "verdicts.jsonl"
    pending = tmp_path / "pending.jsonl"
    inflight = tmp_path / "inprogress.jsonl"
    with open(pending, "a", encoding="utf-8") as f:
        f.write(json.dumps(_row()) + "\n")
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 400, "PF": 1.2, "EV": 0.02,
                                                       "MaxDD": -0.1, "DirAcc": 0.55})
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    rc = asl.main(["--once", "--queue", str(pending), "--inprogress", str(inflight),
                   "--registry", str(reg),
                   "--checkpoint-dir", str(tmp_path / "cp"),
                   "--daily-cache-dir", str(tmp_path / "dc")])
    assert rc == 0
    assert os.path.getsize(str(pending)) == 0
    assert (not os.path.exists(str(inflight))) or os.path.getsize(str(inflight)) == 0

def test_recover_then_claim_after_crash(tmp_path, monkeypatch):
    """inprogress 残留 + checkpoint 存在时, 启动 recover 再跑, 不得丢候选。"""
    pending = tmp_path / "pending.jsonl"
    inflight = tmp_path / "inprogress.jsonl"
    inflight.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 400, "PF": 1.2, "EV": 0.02,
                                                       "MaxDD": -0.1, "DirAcc": 0.55})
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    rc = asl.main(["--once", "--queue", str(pending), "--inprogress", str(inflight),
                   "--registry", str(tmp_path / "verdicts.jsonl"),
                   "--checkpoint-dir", str(tmp_path / "cp"),
                   "--daily-cache-dir", str(tmp_path / "dc")])
    assert rc == 0
    snap = rl.load_snapshot(str(tmp_path / "verdicts.jsonl"))
    assert "m_rsi_state" in snap

def test_live_summarize_keys_aliased(tmp_path, monkeypatch):
    """monthly_backtest.summarize live keys must reach verdict pf/ev/dir_acc/ic."""
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {
        "n": 400, "profit_factor": 1.2, "ev": 0.02, "max_dd": -0.1, "dir_acc": 0.55,
    })
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    verdict = asl.run_aligned_candidate(
        _row(), daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(tmp_path / "verdicts.jsonl"))
    assert verdict["pf"] == 1.2
    assert verdict["ev"] == 0.02
    assert verdict["dir_acc"] == 0.55
    assert verdict["ic"] == 0.1

def test_eval_exception_no_ack_no_verdict(tmp_path, monkeypatch):
    """eval raise: rc=1, inprogress keeps the row, no death verdict written."""
    pending = tmp_path / "pending.jsonl"
    inflight = tmp_path / "inprogress.jsonl"
    reg = tmp_path / "verdicts.jsonl"
    with open(pending, "a", encoding="utf-8") as f:
        f.write(json.dumps(_row()) + "\n")
    import monthly_backtest as mb
    def _boom(*a, **k):
        raise RuntimeError("eval boom")
    monkeypatch.setattr(mb, "run_symbol_backtest", _boom)
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    rc = asl.main(["--once", "--queue", str(pending), "--inprogress", str(inflight),
                   "--registry", str(reg),
                   "--checkpoint-dir", str(tmp_path / "cp"),
                   "--daily-cache-dir", str(tmp_path / "dc")])
    assert rc == 1
    assert [r["variant_id"] for r in rl.queue_load(str(inflight))] == ["m_rsi_state"]
    assert rl.load_snapshot(str(reg)) == {}

@pytest.mark.slow
def test_run_aligned_candidate_real_data(tmp_path, monkeypatch):
    row = {"variant_id": "it_m_rsi", "symbol": "m", "cov_override": "rsi_state",
           "max_points": 2, "stage": "aligned",
           "checkpoint_path": "", "enqueued_at": "t", "src_run": "integration"}
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    kw = dict(daily_cache_dir=str(tmp_path / "dc"),
              checkpoint_dir=str(tmp_path / "cp"),
              registry_path=str(tmp_path / "verdicts.jsonl"))
    v1 = asl.run_aligned_candidate(row, **kw)
    assert v1["status"] == "ok"
    assert rl.validate_verdict(v1) == []
    assert v1["variant_id"] == "it_m_rsi"
    assert isinstance(v1["gate_pass"], bool)
    cp = tmp_path / "cp" / "it_m_rsi.jsonl"
    assert cp.exists() and cp.stat().st_size > 0
    v2 = asl.run_aligned_candidate(row, **kw)
    assert v2["status"] == "ok" and rl.validate_verdict(v2) == []
