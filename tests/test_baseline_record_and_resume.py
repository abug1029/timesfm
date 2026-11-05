import json
from pathlib import Path

import numpy as np
import pandas as pd


def test_record_omits_missing_new_keys_and_rejects_bad_cutoff():
    from cascade.baseline_paths import baseline_jsonl_record
    rec = baseline_jsonl_record(
        {"cutoff": "2026-01-01 10:00:00", "dir_ok": True, "delta_pred": 1, "delta_real": 2},
        "fp",
    )
    assert set(rec) == {"cutoff", "dir_ok", "delta_pred", "delta_real", "protocol_fingerprint"}
    assert rec["dir_ok"] is True
    full = baseline_jsonl_record(
        {"cutoff": "2026-01-01 10:00:00", "dir_ok": False, "delta_pred": -1,
         "delta_real": 2, "endpoint_delta": 0.5, "position_sign": -1},
        "fp",
    )
    assert full["endpoint_delta"] == 0.5
    assert full["position_sign"] == -1.0
    try:
        baseline_jsonl_record(
            {"cutoff": "2026-01-01", "dir_ok": True, "delta_pred": 1, "delta_real": 1},
            "fp",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("日期而不是收盘时间戳时必须拒绝")


def test_both_writers_call_record_and_incremental_does_not_rephase(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp
    import scripts.incremental_baseline as ib
    import scripts.monthly_backtest as mb

    seen = []

    def _rec(point, fp):
        seen.append(point["cutoff"])
        return {
            "cutoff": point["cutoff"],
            "dir_ok": bool(point["dir_ok"]),
            "delta_pred": float(point["delta_pred"]),
            "delta_real": float(point["delta_real"]),
            "protocol_fingerprint": fp,
        }

    monkeypatch.setattr("cascade.baseline_paths.baseline_jsonl_record", _rec)
    monkeypatch.setattr(gbp, "baseline_jsonl_record", _rec, raising=False)
    points = [{
        "cutoff": "2026-02-01 10:00:00", "dir_ok": True,
        "delta_pred": 1.0, "delta_real": 1.0,
        "pred_end": 101.0, "real_end": 101.0, "base": 100.0,
        "dir12_ok": True, "mae": 1.0, "mape": 1.0, "mae_h1": 1.0, "mae_h2": 1.0,
        "coverage": 20, "real_range": 1.0,
    }]
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {
        "points": points, "symbol": "SS", "name": "不锈钢", "contract": "x", "total_bars": 1,
    })

    class _Model:
        def __init__(self, *a, **k):
            self.model = None

    monkeypatch.setattr("cascade.daily_model.DailyModel", _Model)
    monkeypatch.setattr("cascade.hourly_model.HourlyModel", _Model)
    captured = {}

    def _bt(*a, **k):
        captured.update(k)
        return {"points": points, "symbol": "SS", "name": "不锈钢", "contract": "x", "total_bars": 1}

    monkeypatch.setattr(mb, "run_symbol_backtest", _bt)
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True)
    (cfg / "baseline_points_jd_nocov.jsonl").write_text(
        json.dumps({"cutoff": "2026-01-01 10:00:00", "dir_ok": True,
                    "delta_pred": 1.0, "delta_real": 1.0,
                    "protocol_fingerprint": "fp"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "task_FM.evaluations.fm_eval.evaluator.compute_protocol_fingerprint",
        lambda: "fp",
    )
    monkeypatch.setattr(
        "cascade.eval_grid.baseline_eval_cutoffs",
        lambda symbol: ["2026-01-01 10:00:00"],
    )
    ib.incremental_generate("jd", None, str(tmp_path), finalize=False)
    # 断言临时文件存在，活文件仍是夹具里的旧行
    live = cfg / "baseline_points_jd_nocov.jsonl"
    tmp = cfg / ".baseline_points_jd_nocov.jsonl.tmp"
    assert tmp.exists(), "finalize=False 时应留下临时文件"
    live_lines = [l for l in live.open(encoding="utf-8") if l.strip()]
    assert len(live_lines) == 1, "活文件应仍是夹具里的旧行"
    old_rec = json.loads(live_lines[0])
    assert old_rec["cutoff"] == "2026-01-01 10:00:00"
    assert "eval_start_ts" not in captured
    assert "completed" not in captured
    assert captured["resumed_points"]
    gbp.generate("ss", cov="ccl", root=str(tmp_path))
    assert seen, "两个写入者都要调用投影"
    gen_src = Path("scripts/generate_baseline_points.py").read_text(encoding="utf-8")
    inc_src = Path("scripts/incremental_baseline.py").read_text(encoding="utf-8")
    assert "baseline_jsonl_record" in gen_src
    assert "baseline_jsonl_record" in inc_src
    assert '"protocol_fingerprint": _proto' not in gen_src
    assert '"protocol_fingerprint": _proto' not in inc_src
    assert "resumed_as_points" not in inc_src
    assert "timedelta(hours=2)" not in inc_src


def test_resumed_points_merge_without_completed(monkeypatch):
    import scripts.monthly_backtest as mb
    from tests.test_v4_window_anchor import _FakeStore, _hourly_df, _daily_df

    h1 = _hourly_df(80)
    monkeypatch.setattr(mb, "DataStore", lambda symbol: _FakeStore(h1, _daily_df()))
    monkeypatch.setattr(mb, "CONTEXT_BARS", 20)
    monkeypatch.setattr(mb, "CONTEXT_DAYS", 10)
    monkeypatch.setattr(mb, "HORIZON", 4)
    monkeypatch.setattr(mb, "HORIZON_DAYS", 2)
    monkeypatch.setattr(mb, "STEP", 5)
    monkeypatch.setattr(mb, "EVAL_WINDOW_BARS", 40)
    indices = mb.select_eval_indices(h1["dt"])
    cutoffs = []
    for idx in indices:
        bar = pd.Timestamp(h1["dt"].iloc[idx])
        cutoffs.append((bar + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"))
    resumed = {}
    for cutoff in cutoffs:
        resumed[("ss", cutoff)] = {
            "cutoff": cutoff, "base": 100.0, "pred_end": 101.0, "real_end": 101.0,
            "delta_pred": 1.0, "delta_real": 1.0, "dir_ok": True, "dir12_ok": True,
            "mae": 1.0, "mape": 1.0, "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 4,
            "pnl": 1.0, "real_range": 2.0, "roll_in_horizon": False,
            "endpoint_mape": 1.0, "endpoint_bias_pct": 0.0, "path_corr": None,
            "covariates_used": False, "context_hash": "a" * 16, "ablation_mode": "full",
            "protocol_fingerprint": "should-drop", "symbol": "ss", "idx": 0,
        }
    data = mb.run_symbol_backtest(
        "ss", None, None, cov_override="none", resumed_points=resumed,
    )
    assert data is not None
    assert [p["cutoff"] for p in data["points"]] == cutoffs
    assert "protocol_fingerprint" not in data["points"][0]

    completed = {("ss", c) for c in cutoffs}
    skipped = mb.run_symbol_backtest(
        "ss", None, None, cov_override="none", completed=completed,
    )
    assert skipped is not None
    assert skipped["points"] == []


def test_incremental_reuses_only_grid_rows(tmp_path, monkeypatch):
    import json
    import scripts.incremental_baseline as ib
    import scripts.monthly_backtest as mb

    class _Model:
        def __init__(self, *a, **k):
            self.model = None

    monkeypatch.setattr("cascade.daily_model.DailyModel", _Model)
    monkeypatch.setattr("cascade.hourly_model.HourlyModel", _Model)
    monkeypatch.setattr(
        "task_FM.evaluations.fm_eval.evaluator.compute_protocol_fingerprint",
        lambda: "fp",
    )
    grid = ["2026-02-01 10:00:00", "2026-02-01 12:00:00"]
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    captured = {}

    def _bt(*a, **k):
        captured.update(k)
        return {"points": [
            {"cutoff": c, "dir_ok": True, "delta_pred": 1.0, "delta_real": 1.0}
            for c in grid
        ]}

    monkeypatch.setattr(mb, "run_symbol_backtest", _bt)
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True)
    rows = [
        {"cutoff": "2026-01-01 10:00:00", "dir_ok": True, "delta_pred": 1.0,
         "delta_real": 1.0, "protocol_fingerprint": "fp"},
        {"cutoff": "2026-02-01 10:00:00", "dir_ok": True, "delta_pred": 1.0,
         "delta_real": 1.0, "protocol_fingerprint": "fp"},
        {"cutoff": "2026-02-01 12:00:00", "dir_ok": True, "delta_pred": 1.0,
         "delta_real": 1.0, "protocol_fingerprint": "old"},
    ]
    (cfg / "baseline_points_jd_nocov.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8",
    )
    ib.incremental_generate("jd", None, str(tmp_path), finalize=False)
    assert "eval_start_ts" not in captured
    keys = set(captured["resumed_points"])
    assert keys == {("jd", "2026-02-01 10:00:00")}


def test_error_point_deletes_preexisting_incremental_temp(tmp_path, monkeypatch):
    import scripts.incremental_baseline as ib
    import scripts.monthly_backtest as mb

    class _Model:
        def __init__(self, *a, **k):
            self.model = None

    monkeypatch.setattr("cascade.daily_model.DailyModel", _Model)
    monkeypatch.setattr("cascade.hourly_model.HourlyModel", _Model)
    monkeypatch.setattr(
        "task_FM.evaluations.fm_eval.evaluator.compute_protocol_fingerprint",
        lambda: "fp",
    )
    monkeypatch.setattr(
        "cascade.eval_grid.baseline_eval_cutoffs",
        lambda symbol: ["2026-02-01 10:00:00"],
    )
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: {
        "points": [{"cutoff": "2026-02-01 10:00:00", "error": "fresh point failed"}],
    })
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True)
    live = cfg / "baseline_points_jd_nocov.jsonl"
    tmp = cfg / ".baseline_points_jd_nocov.jsonl.tmp"
    live_body = '{"cutoff": "2026-01-01 10:00:00", "dir_ok": true}' + chr(10)
    live.write_text(live_body, encoding="utf-8")
    tmp.write_text('{"cutoff": "2026-01-02 10:00:00", "dir_ok": true}' + chr(10), encoding="utf-8")
    got = ib.incremental_generate("jd", None, str(tmp_path), finalize=False)
    assert got is None
    assert not tmp.exists()
    assert live.read_text(encoding="utf-8") == live_body


def test_fresh_eval_point_keeps_endpoint_fields_and_short_horizon_dir12(monkeypatch):
    import dataclasses
    import re

    import scripts.monthly_backtest as mb
    from cascade.eval_grid import filter_by_daily_sufficiency
    from config.prediction_scheme import get_scheme
    from tests.test_v4_window_anchor import _FakeStore, _daily_df, _hourly_df

    h1 = _hourly_df(80)
    monkeypatch.setattr(mb, "DataStore", lambda symbol: _FakeStore(h1, _daily_df()))
    monkeypatch.setattr(mb, "BacktestDataStore", lambda *a, **k: object())
    monkeypatch.setattr(mb, "CONTEXT_BARS", 20)
    monkeypatch.setattr(mb, "CONTEXT_DAYS", 10)
    monkeypatch.setattr(mb, "HORIZON", 4)
    monkeypatch.setattr(mb, "HORIZON_DAYS", 2)
    monkeypatch.setattr(mb, "STEP", 5)
    monkeypatch.setattr(mb, "EVAL_WINDOW_BARS", 40)
    scheme = dataclasses.replace(get_scheme("ss"), short_horizon_only=True)
    monkeypatch.setattr(mb, "get_scheme", lambda symbol: scheme)

    indices = mb.select_eval_indices(h1["dt"], max_points=1)
    kept = filter_by_daily_sufficiency(
        indices, h1["dt"], _daily_df(), max(mb.CONTEXT_DAYS - mb.HORIZON_DAYS, 100),
    )
    assert kept
    idx = kept[0]
    base = float(h1["close_price"].iloc[idx])
    real = h1["close_price"].iloc[idx + 1:idx + 1 + mb.HORIZON].to_numpy()
    pred = np.array([base + 30.0, base - 10.0, base, base + 1.0])

    class _Daily:
        def predict(self, *a, **k):
            return type("DailyResult", (), {"horizon_slope": 0.0})()

    class _Hourly:
        def predict(self, *a, **k):
            return type("HourlyResult", (), {
                "point_forecast": pred,
                "quantile_forecast": None,
                "ablation_mode": "full",
                "xreg_fallback": False,
                "covariates": None,
            })()

    data = mb.run_symbol_backtest(
        "ss", _Daily(), _Hourly(), cov_override="none", max_points=1,
    )
    assert data is not None
    assert len(data["points"]) == 1
    point = data["points"][0]
    assert "error" not in point
    assert "endpoint_delta" in point
    assert "position_sign" in point
    half = mb.HORIZON // 2
    d12_pred = float(np.mean(pred[:half]) - base)
    d12_real = float(real[half - 1] - base)
    assert d12_real != 0
    assert np.sign(pred[half - 1] - base) != np.sign(d12_pred)
    assert point["dir12_ok"] is True
    assert point["dir12_ok"] is bool(np.sign(d12_pred) == np.sign(d12_real))
    src = Path("scripts/monthly_backtest.py").read_text(encoding="utf-8")
    assert not re.search(r"(?<![A-Za-z0-9_])_sig(?![A-Za-z0-9_])", src)
