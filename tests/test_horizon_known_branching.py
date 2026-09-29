"""Phase 3 (PR-C6) — horizon 尾填充契约与前视防护。

spec §4.5 W5.1-W5.3，行 942-1010。
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cascade.features import _enforce_horizon_contract
from cascade.horizon_fill import (
    FILL_PERSISTENCE,
    FILL_REAL_FUTURE,
    FILL_SELF_REFERENTIAL,
    HORIZON_KNOWN_VOCAB,
    HorizonContractError,
    fill_horizon,
    get_horizon_known,
    horizon_exogenous,
    verify_horizon_invariant,
    _load_pool,
)

POOL = json.load(
    open(
        Path(__file__).resolve().parent.parent
        / "task_FM" / "config" / "covariate_pool.json",
        encoding="utf-8",
    )
)["covariates"]

NON_KNOWN_AHEAD = [c for c in POOL if POOL[c].get("horizon_known") != "known_ahead"]
KNOWN_AHEAD = [c for c in POOL if POOL[c].get("horizon_known") == "known_ahead"]


# ── W5.1 唯一家：分类只写在 pool，代码不得按名硬编码 ─────────────


def test_every_pool_covariate_has_controlled_vocabulary():
    """W5.1：四选一受控词表，缺失即失败（禁止默认值兜底）。"""
    for name, entry in POOL.items():
        hk = entry.get("horizon_known")
        assert hk in HORIZON_KNOWN_VOCAB, f"{name}: horizon_known={hk!r} 非法"


def test_known_ahead_requires_evidence():
    """W5.1：known_ahead 是唯一引入未来信息的类，准入须有可核验证据。"""
    for name in KNOWN_AHEAD:
        assert POOL[name].get("known_ahead_evidence"), f"{name} 缺 known_ahead_evidence"


def test_reader_rejects_unknown_covariate():
    with pytest.raises(HorizonContractError, match="无 .* 条目"):
        get_horizon_known("__no_such_covariate__")


def test_fill_function_does_not_branch_on_covariate_name():
    """W5.3①：填充函数只接受 horizon_known 决定分支，不接受协变量名。"""
    sig = inspect.signature(fill_horizon)
    assert "covariate_type" not in sig.parameters
    assert "covariate_name" not in sig.parameters
    assert "horizon_known" in sig.parameters


def test_features_helper_resolves_class_from_pool_not_from_a_name_table():
    """唯一家：features.py 侧不得维护自己的 名称->分类 映射。"""
    src = inspect.getsource(_enforce_horizon_contract)
    assert "get_horizon_known" in src, "必须走 pool 唯一家"
    # 不得出现按名硬编码的分支
    for name in ("rsi_state", "ha_body", "ccl", "vor"):
        assert f'"{name}"' not in src, f"features 侧不得按名硬编码 {name}"


# ── W5.2 填充策略 ──────────────────────────────────────────────


def test_known_ahead_takes_real_future_values():
    ctx = np.array([1.0, 2.0, 3.0])
    rf = np.array([9.0, 8.0, 7.0, 6.0])
    hz, tag = fill_horizon(ctx, 4, "known_ahead", real_future=rf)
    assert tag == FILL_REAL_FUTURE
    assert np.array_equal(hz, rf)


def test_known_ahead_without_real_future_is_rejected():
    """W5.2：禁止从任何含未来数据的表取值 —— 没有可核验来源就必须拒绝。"""
    with pytest.raises(HorizonContractError, match="real_future"):
        fill_horizon(np.array([1.0, 2.0]), 3, "known_ahead")


@pytest.mark.parametrize("hk", ["persistence", "unknowable", "self_referential"])
def test_non_known_ahead_fills_last_value(hk):
    """W5.2：其余三类填末值（替代历史 zeros / decay）。"""
    ctx = np.array([1.0, 2.0, 3.5])
    hz, tag = fill_horizon(ctx, 5, hk)
    assert np.allclose(hz, 3.5), "horizon 段必须逐值等于 context 末值"
    expected = FILL_SELF_REFERENTIAL if hk == "self_referential" else FILL_PERSISTENCE
    assert tag == expected


@pytest.mark.parametrize("hk", ["persistence", "unknowable", "self_referential"])
def test_non_known_ahead_rejects_real_future(hk):
    """非 known_ahead 携带真实未来值 = 前视泄漏，必须拒绝。"""
    with pytest.raises(HorizonContractError, match="不得引入未来信息"):
        fill_horizon(np.array([1.0, 2.0]), 2, hk, real_future=np.array([9.0, 9.0]))


# ── W5.3② 前视防护：非 known_ahead 逐值等于 context 末值 ─────────


@pytest.mark.parametrize("covariate_type", NON_KNOWN_AHEAD)
def test_invariant_holds_for_every_non_known_ahead_covariate(covariate_type):
    """W5.3②：对每个非 known_ahead 协变量，horizon 段逐值等于 context 末值。"""
    ctx = np.array([1.0, 2.0, 4.0])
    hz, _ = fill_horizon(ctx, 24, get_horizon_known(covariate_type))
    full = np.concatenate([ctx, hz])
    assert verify_horizon_invariant(covariate_type, full, len(ctx), 24) is not None
    assert np.allclose(full[len(ctx):], full[len(ctx) - 1])


def test_invariant_violation_is_detected():
    """构造泄漏用例：horizon 段不是末值常量 -> 必须报错。"""
    leaky = np.concatenate([np.array([1.0, 2.0, 3.0]), np.array([2.9, 2.8, 2.7])])
    with pytest.raises(HorizonContractError, match="非 persistence"):
        verify_horizon_invariant("rsi_state", leaky, 3, 3)


def test_enforcement_normalizes_incoming_decay_fill():
    """历史分支用 _decay_fill，接入后必须被归一化为末值并告警。"""
    ctx = np.array([1.0, 2.0, 4.0])
    decay_tail = 4.0 * (0.5 ** (np.arange(24) / 12.0))  # 历史 decay 填充
    full = np.concatenate([ctx, decay_tail])

    fixed, tag = _enforce_horizon_contract("rsi_state", full, len(ctx), 24)
    assert tag == FILL_PERSISTENCE
    assert np.allclose(fixed[len(ctx):], 4.0)


def test_enforcement_rejects_wrong_length():
    with pytest.raises((ValueError, HorizonContractError)):
        _enforce_horizon_contract("rsi_state", np.zeros(10), 3, 24)


# ── W5.3③ known_ahead 的 horizon 可由 cutoff 已知输入重算 ────────


def test_known_ahead_calendar_recomputable_from_dates_only():
    """W5.3③：改变 cutoff 之后的价格，horizon 填充值不得改变。

    日历是唯一 known_ahead 类；它的未来值只由日期决定，与价格无关。
    """
    from cascade.features import calc_calendar_cyclical

    idx = pd.date_range("2026-09-29 09:00", periods=48, freq="1h")
    df_a = pd.DataFrame({"dt": idx, "close_price": np.linspace(3000, 3100, 48)})
    df_b = pd.DataFrame({"dt": idx, "close_price": np.linspace(9999, 1, 48)})

    cyc_a = calc_calendar_cyclical(df_a, 24)
    cyc_b = calc_calendar_cyclical(df_b, 24)

    assert np.allclose(cyc_a, cyc_b), "horizon 值只依赖日期，不得随 cutoff 后价格变化"


def test_known_ahead_allows_non_constant_horizon():
    """W5.2：horizon_std > 0 只允许出现在 known_ahead 类。"""
    ctx = np.array([1.0, 2.0, 3.0])
    rf = np.sin(np.linspace(0, 6.28, 24))
    hz, tag = fill_horizon(ctx, 24, "known_ahead", real_future=rf)
    full = np.concatenate([ctx, hz])
    assert float(np.std(full[3:])) > 0
    assert verify_horizon_invariant("calendar_cyclical", full, 3, 24) == FILL_REAL_FUTURE


# ── W5.3④ verdict 落 horizon_exogenous ────────────────────────


def test_horizon_exogenous_true_only_for_known_ahead():
    assert horizon_exogenous(["calendar_cyclical"]) is True
    assert horizon_exogenous(["rsi_state"]) is False
    assert horizon_exogenous(["rsi_state", "calendar_cyclical"]) is True
    assert horizon_exogenous([]) is False
    assert horizon_exogenous(None) is False


def test_hourly_result_declares_horizon_exogenous():
    """W5.3④：HourlyResult 承载该诊断字段。"""
    from cascade.hourly_model import HourlyResult

    assert "horizon_exogenous" in HourlyResult.__dataclass_fields__


# ── pool 覆盖度 ────────────────────────────────────────────────


def test_all_pool_covariates_resolvable():
    for name in POOL:
        assert get_horizon_known(name) in HORIZON_KNOWN_VOCAB


def test_known_ahead_set_is_small_and_auditable():
    """只有日历类应被标 known_ahead；数量膨胀意味着有人在偷看未来。"""
    assert len(KNOWN_AHEAD) <= 3, f"known_ahead 数量异常: {KNOWN_AHEAD}"
