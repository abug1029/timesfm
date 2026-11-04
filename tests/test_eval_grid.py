import pandas as pd
import pytest


def test_select_eval_indices_right_bound_is_not_the_harvest_stop():
    from cascade.eval_grid import select_eval_indices
    total = 10000
    horizon = 24
    dts = (
        pd.date_range("2024-01-01", periods=total, freq="h")
        .strftime("%Y-%m-%d %H:%M:%S")
        .tolist()
    )
    indices = select_eval_indices(
        dts, context_bars=480, horizon=horizon, step=2, eval_window_bars=1200,
    )
    assert indices[-1] <= total - horizon - 1
    assert (total - horizon) not in indices


def test_baseline_eval_cutoffs_rejects_empty_read(monkeypatch):
    import pandas as pd
    from cascade import eval_grid

    class _Empty:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get_main_contract_1h(self, limit=99999):
            return pd.DataFrame()
        def get_main_continuous(self, limit=99999):
            return pd.DataFrame()

    monkeypatch.setattr(eval_grid, "DataStore", lambda symbol: _Empty())
    with pytest.raises(RuntimeError):
        eval_grid.baseline_eval_cutoffs("jd")


def test_eval_grid_does_not_import_torch_or_monthly_backtest():
    from pathlib import Path
    text = Path("cascade/eval_grid.py").read_text(encoding="utf-8")
    assert "import torch" not in text
    assert "monthly_backtest" not in text
