"""三路消融系统集成测试（PR-B5 step 4-6）

覆盖：
- 审计集配置文件有效性（真实 config/ablation_audit_config.json）
- HourlyModel.predict() 的 ablation_mode 接线（full/baseline/content/structural）
- 未知消融模式的 fail-fast
- 回测 checkpoint 保留消融标签
"""
import json
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cascade.ablation import (  # noqa: E402
    AblationMode,
    is_audit_candidate,
    load_ablation_audit_config,
)
from cascade.hourly_model import HourlyModel, HourlyResult  # noqa: E402


# ---------------------------------------------------------------------------
# 审计集配置
# ---------------------------------------------------------------------------

def test_real_audit_config_exists_and_valid():
    """真实配置文件存在且结构合法（不是静默回退到默认值）"""
    cfg_path = os.path.join(ROOT, "config", "ablation_audit_config.json")
    assert os.path.exists(cfg_path), "config/ablation_audit_config.json 缺失"

    cfg = load_ablation_audit_config()
    assert cfg["schema"] == "fm.ablation_audit.v1"
    assert cfg["symbols"], "审计集品种不能为空"
    assert cfg["covariates"], "审计集协变量不能为空"
    # 四种模式必须齐全，否则消融对照不完整
    assert set(cfg["modes"]) == {m.value for m in AblationMode}


def test_audit_config_symbols_are_known():
    """审计集品种必须在 sector_map 中有归属（防止拼错品种代码）"""
    from config.sector_map import sector_of

    cfg = load_ablation_audit_config()
    unknown = [s for s in cfg["symbols"] if sector_of(s) == "other"]
    assert not unknown, f"审计集含未知品种: {unknown}"


def test_audit_config_covariates_are_in_pool():
    """审计集协变量必须在 covariate_pool 中（防止拼错协变量名）"""
    pool_path = os.path.join(ROOT, "config", "covariate_pool.json")
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)
    covs = pool["covariates"]
    available = set(covs) if isinstance(covs, dict) else {c["name"] for c in covs}

    cfg = load_ablation_audit_config()
    unknown = [c for c in cfg["covariates"] if c not in available]
    assert not unknown, f"审计集含未知协变量: {unknown}"


def test_is_audit_candidate_against_real_config():
    """真实配置驱动 is_audit_candidate"""
    cfg = load_ablation_audit_config()
    sym, cov = cfg["symbols"][0], cfg["covariates"][0]

    assert is_audit_candidate(sym, cov, cfg) is True
    assert is_audit_candidate("__nope__", cov, cfg) is False
    assert is_audit_candidate(sym, "__nope__", cfg) is False


# ---------------------------------------------------------------------------
# 轻量接口测试
# ---------------------------------------------------------------------------

def test_hourly_result_default_ablation_mode_is_full():
    """HourlyResult 默认 full，保证旧调用方行为不变"""
    r = HourlyResult(
        symbol="m", point_forecast=np.zeros(24), quantile_forecast=None,
        covariates={}, context_len=48, horizon=24,
    )
    assert r.ablation_mode == "full"


def test_checkpoint_keys_include_ablation_mode():
    """回测 checkpoint 需保留消融标签（否则 resume 后无法区分模式）"""
    from scripts.monthly_backtest import _CHECKPOINT_POINT_KEYS

    assert "ablation_mode" in _CHECKPOINT_POINT_KEYS


class TestResumeModeConflict:
    """resume 时消融模式不一致必须中止（防止不同模式的点被静默复用）"""

    def test_same_mode_no_conflict(self):
        from scripts.monthly_backtest import _resume_mode_conflict

        assert _resume_mode_conflict({"content"}, "content") == set()
        assert _resume_mode_conflict(set(), "full") == set()

    def test_mixed_modes_conflict(self):
        from scripts.monthly_backtest import _resume_mode_conflict

        assert _resume_mode_conflict({"full", "content"}, "content") == {"full"}

    def test_legacy_checkpoint_defaults_to_full(self):
        """旧 checkpoint 无 ablation_mode 键 → 归一为 full，与 full 运行不冲突"""
        from scripts.monthly_backtest import _resume_mode_conflict

        # 读取侧把缺失键归一为 "full" 后再调用
        observed = {str(rec.get("ablation_mode", "full"))
                    for rec in ({"symbol": "m"}, {"ablation_mode": "full"})}
        assert observed == {"full"}
        assert _resume_mode_conflict(observed, "full") == set()
        # 但 legacy checkpoint 对 baseline 运行即为冲突
        assert _resume_mode_conflict(observed, "baseline") == {"full"}


def test_unknown_ablation_mode_raises_fast():
    """未知模式必须在触碰 store/model 之前 fail-fast"""
    class _NeverUsed:
        def __getattr__(self, name):
            raise AssertionError(f"不应触碰 {name}")

    hm = HourlyModel(shared_model=_NeverUsed())
    with pytest.raises(ValueError, match="unknown ablation_mode"):
        hm.predict("m", None, None, ablation_mode="bogus")


# ---------------------------------------------------------------------------
# predict() 集成（patch 掉数据校验，注入 fake model/store）
# ---------------------------------------------------------------------------

class _FakeForecast:
    def __init__(self, forecast, quantiles=None):
        self.forecast = forecast
        self.quantiles = quantiles


class _RecordingModel:
    """记录每次 predict 收到的协变量矩阵"""

    def __init__(self):
        self.calls = []

    def predict(self, context, horizon, past_future_covariates=None,
                return_quantiles=True):
        self.calls.append(
            None if past_future_covariates is None
            else np.array(past_future_covariates, dtype=np.float64, copy=True)
        )
        n = len(context)
        base = float(context[-1])
        fc = np.full(horizon, base + 1.0)
        q = np.tile(fc[:, None], (1, 10))
        return _FakeForecast(fc, q)


@dataclass
class _FakeDailyResult:
    historical_closes: np.ndarray
    forecast: np.ndarray
    historical_dates: pd.DatetimeIndex


class _FakeStore:
    def __init__(self, df):
        self._df = df

    def get_main_contract_1h(self, limit=480):
        return self._df.tail(limit).reset_index(drop=True)

    def get_basis_1h(self, *a, **k):
        return pd.DataFrame()


@pytest.fixture
def ablation_env(monkeypatch):
    """构造 predict() 可跑通的最小环境"""
    import cascade.data_validator as dv

    class _VR:
        ok = True
        warnings = []
        contract_1h = "m_MAIN"
        contract_daily = "m_MAIN"

    monkeypatch.setattr(dv, "validate_prediction_data", lambda symbol, store, **k: _VR())

    np.random.seed(7)
    n = 120
    dt = pd.date_range("2026-09-01", periods=n, freq="h")
    close = 3000 + np.cumsum(np.random.randn(n) * 5)
    df = pd.DataFrame({
        "dt": dt,
        "close_price": close,
        "ccl_value": np.linspace(50000, 55000, n) + np.random.randn(n) * 200,
    })

    model = _RecordingModel()
    hm = HourlyModel(shared_model=model)
    store = _FakeStore(df)

    hist = close[::24][:25].astype(float)
    pred = close[-24::24].astype(float)
    daily = _FakeDailyResult(
        historical_closes=hist,
        forecast=pred,
        historical_dates=pd.date_range("2026-09-01", periods=len(hist), freq="D"),
    )
    return hm, store, daily, model


def _run(env, mode):
    hm, store, daily, model = env
    return hm.predict("m", store, daily, horizon=24, visualize=False,
                      covariate_type="ccl", verbose=False,
                      ablation_mode=mode), model


def test_predict_full_mode_passes_real_covariates(ablation_env):
    """full 模式：协变量矩阵非零且非平凡"""
    res, model = _run(ablation_env, "full")

    assert res.ablation_mode == "full"
    assert res.xreg_fallback is False
    mat = model.calls[-1]
    assert mat is not None
    assert not np.all(mat == 0), "full 模式不应全零"


def test_predict_structural_mode_zeros_all_channels(ablation_env):
    """structural 模式：走 XReg 相同代码路径，但矩阵全零"""
    res, model = _run(ablation_env, "structural")

    assert res.ablation_mode == "structural"
    assert res.xreg_fallback is False, "structural 不是回退，是主动置零"
    mat = model.calls[-1]
    assert mat is not None, "structural 仍需走 XReg 路径"
    assert np.all(mat == 0), "structural 应全零"

    full_mat = _run(ablation_env, "full")[1].calls[-1]
    assert mat.shape == full_mat.shape, "structural 必须保持 shape 以走相同路径"


def test_predict_content_mode_preserves_shape_not_content(ablation_env):
    """content 模式：shape 不变、边际分布保留，但内容被破坏"""
    res, model = _run(ablation_env, "content")

    assert res.ablation_mode == "content"
    mat = model.calls[-1]
    full_mat = _run(ablation_env, "full")[1].calls[-1]

    assert mat.shape == full_mat.shape, "content 必须保持 shape"
    assert not np.allclose(mat, full_mat), "content 内容应与 full 不同"
    # 每个通道的排序后取值应一致（仅顺序被打乱）
    for a, b in zip(mat, full_mat):
        assert np.allclose(np.sort(a), np.sort(b)), "content 应保留边际分布"


def test_predict_baseline_mode_skips_covariates(ablation_env):
    """baseline 模式：不构建协变量，纯 TimesFM"""
    res, model = _run(ablation_env, "baseline")

    assert res.ablation_mode == "baseline"
    assert res.covariates == {}
    assert res.xreg_fallback is False, "baseline 是主动选择，非回退"
    assert res.last_covariate_input is None
    assert model.calls[-1] is None, "baseline 不应传协变量矩阵"
    assert res.cov_effective == 0


def test_predict_default_mode_is_full(ablation_env):
    """不传 ablation_mode 时行为与 full 一致（向后兼容）"""
    hm, store, daily, model = ablation_env

    res_default = hm.predict("m", store, daily, horizon=24, visualize=False,
                             covariate_type="ccl", verbose=False)
    default_mat = model.calls[-1]
    res_full, _ = _run(ablation_env, "full")

    assert res_default.ablation_mode == "full"
    assert np.allclose(default_mat, model.calls[-1])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
