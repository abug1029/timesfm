"""combo 路径协变量分派补齐 + 单路径未知协变量显式报错测试 (2026-09-08)

回归保护:
- rsi6/rsi12/rsi24 在 build_combo_covariate_matrix 可用 (此前仅单路径有, combo raise)
- 单路径未知 covariate_type 不再静默降级 CCL, 而是 raise ValueError
- ccl 单路径显式分支仍正常
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cascade import features  # noqa: E402


@pytest.fixture
def fake_inputs():
    np.random.seed(42)
    n = 600
    dt = pd.date_range("2026-01-01", periods=n, freq="h")
    close = 3000 + np.cumsum(np.random.randn(n) * 5)
    df = pd.DataFrame({
        "dt": dt,
        "open": close + np.random.randn(n),
        "high": close + np.abs(np.random.randn(n) * 3),
        "low": close - np.abs(np.random.randn(n) * 3),
        "close": close,
        "close_price": close,
        "volume": np.random.randint(1000, 5000, n),
        "open_interest": np.linspace(100000, 120000, n) + np.random.randn(n) * 500,
        "ccl_value": np.linspace(50000, 55000, n) + np.random.randn(n) * 200,
    })

    class FakeStore:
        def get_main_contract_1h(self, limit=480):
            return df.tail(limit).reset_index(drop=True)

        def get_basis_1h(self, *a, **k):
            return pd.DataFrame()

    store = FakeStore()
    hist = close[::24][:25].astype(float)
    pred = close[-24::24].astype(float)
    ddates = pd.date_range("2026-01-01", periods=len(hist), freq="D")
    return store, hist, pred, ddates


def test_single_ccl_explicit(fake_inputs):
    s, h, p, d = fake_inputs
    r = features.build_covariate_matrix("m", s, h, p, d, horizon=24, limit=480,
                                        covariate_type="ccl")
    assert "ccl_pct" in r


def test_single_unknown_raises(fake_inputs):
    s, h, p, d = fake_inputs
    with pytest.raises(ValueError, match="不支持 covariate_type"):
        features.build_covariate_matrix("m", s, h, p, d, horizon=24, limit=480,
                                        covariate_type="bogus_covariate_xyz")


@pytest.mark.parametrize("cov", ["rsi6", "rsi12", "rsi24"])
def test_single_rsi_variants(fake_inputs, cov):
    s, h, p, d = fake_inputs
    r = features.build_covariate_matrix("m", s, h, p, d, horizon=24, limit=480,
                                        covariate_type=cov)
    assert cov in r


@pytest.mark.parametrize("cov", ["rsi6", "rsi12", "rsi24"])
def test_combo_rsi_variants(fake_inputs, cov):
    s, h, p, d = fake_inputs
    r = features.build_combo_covariate_matrix("m", s, h, p, d, horizon=24, limit=480,
                                              covariate_types=[cov, "oi"])
    assert cov in r
    assert "oi_pct_change" in r


@pytest.mark.parametrize("cov", ["basis_momentum", "ccl", "gated_slope", "regime_gated"])
def test_combo_new_covariates(fake_inputs, cov):
    """2026-09-11: 新增 4 个协变量到 combo 路径"""
    s, h, p, d = fake_inputs
    r = features.build_combo_covariate_matrix("m", s, h, p, d, horizon=24, limit=480,
                                              covariate_types=[cov])
    assert cov in r
    assert len(r[cov]) == len(r["daily_slope"])

def test_combo_unsupported_raises(fake_inputs):
    s, h, p, d = fake_inputs
    # 真正不支持的协变量 — 必须显式 raise 而非静默错误
    with pytest.raises(ValueError):
        features.build_combo_covariate_matrix("m", s, h, p, d, horizon=24, limit=480,
                                              covariate_types=["bogus_covariate_xyz"])
