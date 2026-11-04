"""ensure_baselines post-condition tests (Task 10).

Tests the new ensure_baselines flow:
- accept_baseline_file as the single post-condition
- grid read error skips symbol without stall
- write exception stalls without a second generate
- publishable temp does not call generate
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import sup_evidence
import sup_lifecycle
import sup_state


def _grid(n=4):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as handle:
        for cutoff in cutoffs:
            handle.write(json.dumps({
                "cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                "delta_real": 1.0, "protocol_fingerprint": fp,
            }) + "\n")


def _prepare(root, symbol="jd", cutoffs=None, fp="fp_test"):
    config = os.path.join(root, "task_FM", "config")
    os.makedirs(config, exist_ok=True)
    with open(os.path.join(config, "baseline_metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({symbol: {"n": 4}}, handle)
    path = os.path.join(config, f"baseline_points_{symbol}_nocov.jsonl")
    _write_points(path, cutoffs if cutoffs is not None else ["2026-10-21 10:00:00"], fp=fp)
    return path


class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root, finalize=False):
        self.calls.append((sym, cov, finalize))


def _arm(monkeypatch, root, data_dt="2026-10-09 14:00:00", grid=None, incremental=None):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: data_dt)
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)
    chosen = grid if grid is not None else _grid()
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(chosen))
    calls = {"incremental": 0}

    def _incremental(*args, **kwargs):
        calls["incremental"] += 1
        if incremental is not None:
            return incremental(*args, **kwargs)
        return None

    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", _incremental)
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    return fake, calls


def test_incremental_none_runs_generate_once_and_stalls_only_after_it_fails(tmp_path, monkeypatch):
    _prepare(str(tmp_path))
    fake, calls = _arm(monkeypatch, str(tmp_path))
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == [("jd", None, False)]
    fake.calls.clear()
    calls["incremental"] = 0
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 0
    assert fake.calls == []


def test_publishable_temp_does_not_call_generate(tmp_path, monkeypatch):
    grid = _grid()
    path = _prepare(str(tmp_path), cutoffs=["2026-10-21 10:00:00"])

    def _write_temp(symbol, cov, root, finalize=False):
        tmp = os.path.join(root, "task_FM", "config", ".baseline_points_jd_nocov.jsonl.tmp")
        _write_points(tmp, grid)
        return grid[-1]

    fake, calls = _arm(monkeypatch, str(tmp_path), grid=grid, incremental=_write_temp)
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == []
    assert [json.loads(line)["cutoff"] for line in open(path, encoding="utf-8")] == grid
    breaker = os.path.join(str(tmp_path), "data", "cache", "baseline_regen_breaker.json")
    if os.path.exists(breaker):
        assert "jd" not in json.load(open(breaker, encoding="utf-8"))
    calls["incremental"] = 0
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 0
    assert fake.calls == []


def test_grid_read_error_skips_symbol_without_stall(tmp_path, monkeypatch):
    grid = _grid()
    _prepare(str(tmp_path), symbol="bb", cutoffs=grid)
    config = os.path.join(str(tmp_path), "task_FM", "config")
    with open(os.path.join(config, "baseline_metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({"aa": {"n": 4}, "bb": {"n": 4}}, handle)
    _write_points(os.path.join(config, "baseline_points_aa_nocov.jsonl"), ["2026-10-21 10:00:00"])
    state = {"fail_aa": True}

    def _grid_for(symbol):
        if symbol == "aa" and state["fail_aa"]:
            raise RuntimeError("db down")
        return list(grid)

    fake, calls = _arm(monkeypatch, str(tmp_path), grid=grid)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", _grid_for)
    sup_evidence.ensure_baselines(["aa", "bb"], str(tmp_path))
    assert fake.calls == []
    assert calls["incremental"] == 0
    state["fail_aa"] = False
    sup_evidence.ensure_baselines(["aa", "bb"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == [("aa", None, False)]


def test_write_exception_stalls_without_a_second_generate(tmp_path, monkeypatch):
    _prepare(str(tmp_path))

    def _boom(*args, **kwargs):
        raise RuntimeError("write exploded")

    fake, calls = _arm(monkeypatch, str(tmp_path), incremental=_boom)
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == []
    calls["incremental"] = 0
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 0
    assert fake.calls == []
