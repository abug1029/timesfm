"""FM_a PRAXIST 评估器测试 (P2, TDD 2026-09-01)"""
import importlib.util
import os

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "fm_evaluator",
    os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval", "evaluator.py"))
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)


def _summarize_like(n=380, pf=1.08, ev=0.9, maxdd=-0.15, diracc=0.54):
    return {"n": n, "PF": pf, "EV": ev, "MaxDD": maxdd, "DirAcc": diracc}


def test_map_summary_to_metrics():
    m = fm.map_summary(_summarize_like())
    assert m["n"] == 380 and m["pf"] == 1.08
    assert m["ev"] == 0.9 and m["maxdd"] == -0.15


def test_gate_pass_and_fail():
    ok = fm.gate(_summarize_like(), min_n=350, min_ic=0.05)
    assert ok is True
    bad = fm.gate(_summarize_like(n=200), min_n=350, min_ic=0.05)
    assert bad is False


def test_invalid_candidate_rejected():
    ok, why = fm.validate_candidate({"cov_override": "rsi_state", "symbol": "m"})
    assert ok is True
    ok2, _ = fm.validate_candidate({"cov_override": "bogus_cov", "rubbish": 1})
    assert ok2 is False


def test_gate_uses_full_wf_requirement():
    """诊断级结果 n<350 必须被门拦下 (预注册契约)"""
    ok = fm.gate(_summarize_like(n=80), min_n=350, min_ic=0.05)
    assert ok is False


def test_do_evaluate_live_summarize_keys_yield_nonzero_ev(monkeypatch):
    """monthly_backtest.summarize live keys (profit_factor/ev/max_dd/dir_acc)
    must alias through do_evaluate → build_summary as nonzero ev / ev_after_slippage.
    """
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
        "n": 6, "profit_factor": 1.3, "ev": 0.05, "max_dd": -0.1, "dir_acc": 0.55,
    })
    run_path = os.path.join(fm_eval, "run.py")
    spec = importlib.util.spec_from_file_location("fm_eval_run", run_path)
    run_mod = importlib.util.module_from_spec(spec)
    sys.modules["fm_eval_run"] = run_mod
    spec.loader.exec_module(run_mod)
    out = run_mod.do_evaluate({
        "symbol": "m", "cov_override": "rsi_state",
        "max_points": 6, "stage": "diagnostic",
    })
    s = out["summary"]
    assert s["ev"] == 0.05
    assert s["metrics"]["ev_after_slippage"] == 0.05
    assert s["pf"] == 1.3
    assert s["dir_acc"] == 0.55
    assert s["ev"] != 0 and s["metrics"]["ev_after_slippage"] != 0
