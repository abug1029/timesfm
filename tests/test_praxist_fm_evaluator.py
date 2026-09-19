"""FM_a PRAXIST 评估器测试 (P2, TDD 2026-09-01; v23 2026-09-16)"""
import importlib.util
import json
import os
import tempfile

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "fm_evaluator",
    os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval", "evaluator.py"))
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)


def _summarize_v23(n=400, n_eff=400, dir_acc=0.56, endpoint_mape=0.4,
                   endpoint_bias_pct=0.1, path_corr=0.7, weighted_dir_acc=0.57,
                   mae=1.0, mape=0.4, decay=1.1):
    """v23 summary keys (PF/EV/MaxDD retired)."""
    return {
        "n": n, "n_eff": n_eff, "dir_acc": dir_acc,
        "endpoint_mape": endpoint_mape, "endpoint_bias_pct": endpoint_bias_pct,
        "path_corr": path_corr, "weighted_dir_acc": weighted_dir_acc,
        "mae": mae, "mape": mape, "decay": decay,
    }


# ── gate tests ──

def test_gate_unilateral_dir_acc():
    ok = {"n": 400, "n_eff": 400, "dir_acc": 0.53}
    assert fm.gate(ok) is True
    assert fm.gate({**ok, "dir_acc": 0.40}) is False
    assert fm.gate({**ok, "n": 80}) is False
    assert fm.gate({**ok, "n_eff": 10}) is False


def test_gate_accepts_DirAcc_alias():
    """D1b: gate 兼容慢环 summarize 的旧键 DirAcc."""
    assert fm.gate({"n": 400, "n_eff": 400, "DirAcc": 0.56}) is True
    assert fm.gate({"n": 400, "n_eff": 400, "DirAcc": 0.40}) is False


def test_gate_adaptive_baseline_lowers_floor():
    s = {"n": 400, "n_eff": 400, "dir_acc": 0.51}
    assert fm.gate(s, baseline_dir_acc=0.51) is True
    assert fm.gate(s, baseline_dir_acc=0.55) is False  # 仍受 0.52 底线
    assert fm.gate(s) is False  # 无 baseline 用 0.52


def test_gate_null_safe():
    assert fm.gate({"n": None, "n_eff": None, "dir_acc": None}) is False


def test_compute_effective_min_matches_v23():
    assert fm.compute_effective_min(0.52, 0.486) == 0.50
    assert fm.compute_effective_min(0.52, 0.502) == 0.502
    assert fm.compute_effective_min(0.52, 0.55) == 0.52
    assert fm.compute_effective_min(0.52, None) == 0.52


def test_gate_m_pca_momentum_repro():
    s = {"n": 588, "n_eff": 73, "dir_acc": 0.502}
    assert fm.gate(s, baseline_dir_acc=0.486) is True
    assert fm.gate(s) is False


def test_gate_sr_crack_spread_repro():
    s = {"n": 588, "n_eff": 73, "dir_acc": 0.510}
    assert fm.gate(s, baseline_dir_acc=0.502) is True
    assert fm.gate(s, baseline_dir_acc=0.55) is False


def test_build_summary_persists_effective_min(tmp_path):
    s = _summarize_v23(n=400, n_eff=400, dir_acc=0.502)
    cand = {"symbol": "m", "cov_override": "pca_momentum", "max_points": 6, "stage": "aligned"}
    out = fm.build_summary(s, cand, baseline_dir_acc=0.486, batch_id="b1")
    assert out["gate_pass"] is True
    assert out["baseline_dir_acc"] == 0.486
    assert out["effective_min"] == 0.50
    assert out["metrics"]["effective_min"] == 0.50
    assert out["metrics"]["baseline_dir_acc"] == 0.486


# ── map_summary tests ──

def test_map_summary_v23_keys():
    m = fm.map_summary(_summarize_v23())
    assert m["n"] == 400
    assert m["n_eff"] == 400
    assert m["dir_acc"] == 0.56
    assert m["endpoint_mape"] == 0.4
    assert m["endpoint_bias_pct"] == 0.1
    assert m["path_corr"] == 0.7
    assert m["weighted_dir_acc"] == 0.57
    assert m["mae"] == 1.0
    assert m["mape"] == 0.4
    assert m["decay"] == 1.1


def test_map_summary_no_pf_ev_maxdd():
    """PF/EV/MaxDD must not appear in v23 map_summary output."""
    m = fm.map_summary(_summarize_v23())
    assert "pf" not in m
    assert "ev" not in m
    assert "maxdd" not in m


# ── build_summary tests ──

def test_build_summary_pops_point_list_and_pairs():
    # Generate 120 unique timestamps with variance (variant mostly wins but not always)
    import random
    random.seed(42)
    variant_pts = []
    base_pts = []
    for i in range(120):
        ts = f"2024-06-15 {i//60:02d}:{i%60:02d}:00"
        # Variant: 70% correct, Baseline: 40% correct (with variance)
        v_ok = random.random() < 0.70
        b_ok = random.random() < 0.40
        variant_pts.append((ts, v_ok))
        base_pts.append({"cutoff": ts, "dir_ok": b_ok})

    s = {
        "n": 400, "n_eff": 400, "dir_acc": 0.56,
        "endpoint_mape": 0.4, "endpoint_bias_pct": 0.1,
        "path_corr": 0.7, "weighted_dir_acc": 0.57,
        "mae": 1.0, "mape": 0.4, "decay": 1.1,
        "point_dir_ok_list": variant_pts,
    }
    out = fm.build_summary(s, {"symbol": "m", "cov_override": "rsi_state",
                               "max_points": 400, "stage": "aligned"},
                           baseline_points=base_pts, baseline_dir_acc=0.50,
                           batch_id="b1")
    assert out["schema"] == "fm.aligned_verdict.v2"
    assert "point_dir_ok_list" not in out
    # DM test should run (120 paired points with variance)
    assert out["p_value"] is not None
    assert out["cov_family"] == "momentum"
    assert out["fdr_pass"] is None
    assert out["gate_pass"] is True


def test_build_summary_diagnostic_gate_always_false():
    """诊断档 gate_pass 必须 False (结构性)."""
    s = _summarize_v23()
    out = fm.build_summary(s, {"symbol": "m", "cov_override": "rsi_state",
                               "max_points": 6, "stage": "diagnostic"})
    assert out["gate_pass"] is False


def test_build_summary_no_baseline_no_pvalue():
    """缺少 baseline → p_value=None."""
    s = _summarize_v23()
    out = fm.build_summary(s, {"symbol": "m", "cov_override": "rsi_state",
                               "max_points": 400, "stage": "aligned"})
    assert out["p_value"] is None
    assert out["schema"] == "fm.aligned_verdict.v2"


def test_build_summary_fewer_than_100_pairs_no_pvalue():
    """配对 <100 → p_value=None."""
    s = _summarize_v23()
    s["point_dir_ok_list"] = [(f"2024-06-15 0{i//60:02d}:{i%60:02d}:00", True) for i in range(50)]
    base_pts = [{"cutoff": f"2024-06-15 0{i//60:02d}:{i%60:02d}:00", "dir_ok": False} for i in range(50)]
    out = fm.build_summary(s, {"symbol": "m", "cov_override": "rsi_state",
                               "max_points": 400, "stage": "aligned"},
                           baseline_points=base_pts)
    assert out["p_value"] is None


# ── load_baseline_points tests ──

def test_load_baseline_points_missing_file():
    """文件不存在 → 空列表."""
    result = fm.load_baseline_points("nonexistent_symbol_xyz")
    assert result == []


def test_load_baseline_points_valid_file():
    """正常 JSONL 加载."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "baseline_points_m.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"cutoff": "2024-06-15 09:00:00", "dir_ok": True}) + "\n")
            f.write(json.dumps({"cutoff": "2024-06-15 10:00:00", "dir_ok": False}) + "\n")
        result = fm.load_baseline_points("m", root=tmp)
        assert len(result) == 2
        assert result[0]["dir_ok"] is True
        assert result[1]["dir_ok"] is False


# ── validate_candidate tests ──

def test_invalid_candidate_rejected():
    ok, why = fm.validate_candidate({"cov_override": "rsi_state", "symbol": "m"})
    assert ok is True
    ok2, _ = fm.validate_candidate({"cov_override": "bogus_cov", "rubbish": 1})
    assert ok2 is False


# ── backward compat ──

def test_do_evaluate_live_summarize_keys_v23(monkeypatch):
    """monthly_backtest.summarize live keys must alias through do_evaluate → build_summary."""
    import importlib.util
    import sys

    scripts = os.path.join(FM_ROOT, "scripts")
    fm_eval = os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval")
    sys.path.insert(0, scripts)
    sys.path.insert(0, fm_eval)
    import monthly_backtest as mb

    monkeypatch.setattr(mb, "DailyModel", lambda: object())
    monkeypatch.setattr(mb, "HourlyModel", lambda: object())
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: {"points": [1]})
    monkeypatch.setattr(mb, "summarize", lambda data: {
        "n": 400, "dir_acc": 0.55, "n_eff": 380,
        "endpoint_mape": 0.3, "endpoint_bias_pct": 0.05,
        "path_corr": 0.6, "weighted_dir_acc": 0.56,
        "mae": 0.8, "mape": 0.3, "decay": 1.0,
    })
    run_path = os.path.join(fm_eval, "run.py")
    spec = importlib.util.spec_from_file_location("fm_eval_run", run_path)
    run_mod = importlib.util.module_from_spec(spec)
    sys.modules["fm_eval_run"] = run_mod
    spec.loader.exec_module(run_mod)
    out = run_mod.do_evaluate({
        "symbol": "m", "cov_override": "rsi_state",
        "max_points": 400, "stage": "aligned",
    })
    s = out["summary"]
    assert s["schema"] == "fm.aligned_verdict.v2"
    assert s["dir_acc"] == 0.55
    assert s["n"] == 400
    assert s["n_eff"] == 380
    assert "point_dir_ok_list" not in s
    # diagnostic stage would have gate_pass=False, but aligned can pass
    assert isinstance(s["gate_pass"], bool)
