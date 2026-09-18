"""oi_gated_momentum 单路径/combo 分派接线测试 (2026-09-18, 方案 A 接线)。

回归保护 (spec §4/§5 调用方契约):
- 返回 dict 的 key 必须**逐字**为 "oi_gated_momentum" — scripts/monthly_backtest.py
  的 _point_signal 与 fm_eval.evaluator.is_gated_covariate 都按该字符串取值,
  一旦改名 → signal 恒 None → 全部点落 n_nan 桶 → 硬门必挂 (最关键一条);
- 输出必须有限 (NaN 不得进模型: hourly_model 的 XReg 无 NaN 防护, NaN 会静默传播);
- 缺表 / 日历长度不匹配 → 全零降级, 不抛异常;
- 持仓缺失日不得 ffill (spec §3.4: 错行比缺行危险);
- 日线→1H 映射: 每根 context bar 的值 == 该 bar 日期(含)之前最近一个已收盘日的信号。

不加载 TimesFM。
"""
import logging
import sqlite3

import numpy as np
import pandas as pd
import pytest

import cascade.oi_gated_momentum as oigm
from cascade.features import (
    build_combo_covariate_matrix,
    build_covariate_matrix,
)
from cascade.oi_gated_momentum import compute_oi_gated_momentum

HORIZON = 24
LIMIT = 480
KEY = "oi_gated_momentum"
LAST_1H = pd.Timestamp("2026-03-01 14:00:00")


def _df_1h(n=LIMIT, last_dt=LAST_1H):
    dts = pd.date_range(end=last_dt, periods=n, freq="h")
    close = 3000.0 + 20.0 * np.sin(np.arange(n, dtype=float) / 3.0)
    return pd.DataFrame({
        "dt": dts,
        "open": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "close_price": close,
        "volume": np.full(n, 1000.0),
        "open_interest": 80_000 + np.arange(n, dtype=float),
    })


def _daily(n=200, end="2026-03-01"):
    """日线价格 (hist 用) + 总持仓 (index_continuous_1d 用), 同一日历。

    总持仓设计为强单边增仓 (ΔOI_5d 恒正) —— 门控在 cutoff bar 必然激活,
    否则 1H 映射断言会退化成"全零对全零"的空跑。
    """
    dates = pd.date_range(end=pd.Timestamp(end), periods=n, freq="D")
    close = 2000.0 + np.linspace(0.0, 600.0, n) + 15.0 * np.sin(np.arange(n, dtype=float))
    oi = 1_000_000.0 + np.linspace(0.0, 300_000.0, n) + 2_000.0 * np.cos(np.arange(n, dtype=float))
    return dates, close, oi


def _oi_frame(dates, oi):
    return pd.DataFrame({
        "dt": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates],
        "close_price": np.full(len(dates), 2300.0),
        "volume": np.full(len(dates), 1e6),
        "open_interest": np.asarray(oi, dtype=float),
    })


class FakeStore:
    """FakeStore 风格同 tests/test_combo_parity.py。"""

    def __init__(self, df_1h, oi_df=None, raise_operational=False):
        self.df_1h = df_1h
        self.oi_df = oi_df
        self.raise_operational = raise_operational
        self.oi_calls = 0

    def get_main_contract_1h(self, limit=480):
        return self.df_1h.tail(int(limit)).reset_index(drop=True)

    def get_index_continuous_daily(self, limit=None, **kwargs):
        self.oi_calls += 1
        if self.raise_operational:
            raise sqlite3.OperationalError("no such table: index_continuous_1d")
        if self.oi_df is None:
            return pd.DataFrame(columns=["dt", "close_price", "volume", "open_interest"])
        return self.oi_df


def _call_single(store, dates, close, **kw):
    return build_covariate_matrix(
        "m", store, np.asarray(close, dtype=float), np.array([close[-1], close[-1] + 5.0]),
        dates, horizon=HORIZON, limit=LIMIT, covariate_type=KEY, **kw,
    )


def _ctx_days():
    return pd.to_datetime(_df_1h()["dt"]).dt.normalize()


# ══════════════════════════════════════════════════════════
#  1. 单路径: key 名 / 长度 / 有限性
# ══════════════════════════════════════════════════════════

def test_single_key_is_exactly_oi_gated_momentum():
    """关键回归锁: key 不得改名 (monthly_backtest._point_signal 按此字符串取值)。"""
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    res = _call_single(store, dates, close)

    assert KEY in res, f"key 必须逐字为 {KEY!r}, 实际 keys={sorted(res)}"
    assert "oi_gated" not in res and "oi_gated_momentum_pct" not in res
    assert set(res) == {"daily_slope", KEY}


def test_single_length_and_finiteness():
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    res = _call_single(store, dates, close)

    arr = res[KEY]
    assert len(arr) == len(res["daily_slope"])
    assert len(arr) == LIMIT + HORIZON
    assert np.isfinite(arr).all(), "NaN/inf 不得进入协变量矩阵 (XReg 无 NaN 防护)"
    assert np.isfinite(res["daily_slope"]).all()


def test_horizon_segment_is_zero():
    """horizon 段补零, 与 oi / ccl 同惯例。"""
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    arr = _call_single(store, dates, close)[KEY]
    np.testing.assert_array_equal(arr[LIMIT:], np.zeros(HORIZON))


# ══════════════════════════════════════════════════════════
#  2. 缺表 / 读表异常 / 日历长度不匹配 → 全零降级, 不抛
# ══════════════════════════════════════════════════════════

def test_missing_table_returns_zeros(caplog):
    dates, close, _ = _daily()
    store = FakeStore(_df_1h(), None)  # 空 DataFrame (表不存在)
    with caplog.at_level(logging.WARNING):
        res = _call_single(store, dates, close)
    assert KEY in res
    np.testing.assert_array_equal(res[KEY], np.zeros(LIMIT + HORIZON))
    assert any("总持仓" in r.getMessage() for r in caplog.records)


def test_operational_error_is_swallowed(caplog):
    dates, close, _ = _daily()
    store = FakeStore(_df_1h(), raise_operational=True)
    with caplog.at_level(logging.WARNING):
        res = _call_single(store, dates, close)  # 不得抛出
    np.testing.assert_array_equal(res[KEY], np.zeros(LIMIT + HORIZON))
    assert any("读取失败" in r.getMessage() for r in caplog.records)


def test_daily_dates_length_mismatch_returns_zeros(caplog):
    """daily_model 的 closes dropna 但 dates 不 dropna → 长度可能不匹配。

    此路径禁止按日期配对 (会静默错配), 必须全零降级。
    """
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    with caplog.at_level(logging.WARNING):
        res = build_covariate_matrix(
            "m", store, np.asarray(close, dtype=float), np.array([close[-1]]),
            dates[:-3],  # 长度不匹配
            horizon=HORIZON, limit=LIMIT, covariate_type=KEY,
        )
    np.testing.assert_array_equal(res[KEY], np.zeros(LIMIT + HORIZON))
    assert store.oi_calls == 0, "长度不匹配时不得进入按日期配对流程"
    assert any("长度不匹配" in r.getMessage() for r in caplog.records)


# ══════════════════════════════════════════════════════════
#  3. 日历对齐: 缺失日不得 ffill (spec §3.4)
# ══════════════════════════════════════════════════════════

def test_missing_oi_day_is_passed_as_nan_not_ffilled(monkeypatch):
    """删掉某个 OI 日 → 交给 compute_oi_gated_momentum 的 total_oi 在该日必须为 NaN。

    直接检查接线契约本身 (join 输出), 而非只看输出差异 —— 输出差异对
    "ffill 一个伪造值" 与 "留 NaN" 两种实现都可能成立, 判别力不足。
    """
    dates, close, oi = _daily()
    drop_idx = 150
    kept = [i for i in range(len(dates)) if i != drop_idx]
    store = FakeStore(_df_1h(), _oi_frame(dates[kept], np.asarray(oi)[kept]))

    captured = {}
    real = oigm.compute_oi_gated_momentum

    def spy(price, total_oi, **kw):
        captured["price"] = price
        captured["total_oi"] = total_oi
        return real(price, total_oi, **kw)

    monkeypatch.setattr(oigm, "compute_oi_gated_momentum", spy)
    _call_single(store, dates, close)

    total_oi = captured["total_oi"]
    drop_day = pd.Timestamp(dates[drop_idx])
    assert drop_day in total_oi.index, "价格日历为基准: 缺失日必须仍在索引上"
    assert pd.isna(total_oi.loc[drop_day]), (
        "缺失的 OI 日被 ffill 成陈旧值 (spec §3.4 禁止: 错行比缺行危险)"
    )
    # 非缺失日必须是真实值
    kept_day = pd.Timestamp(dates[drop_idx + 1])
    assert total_oi.loc[kept_day] == pytest.approx(float(oi[drop_idx + 1]))
    # 索引与价格腿逐位一致 (模块入口硬校验)
    assert total_oi.index.equals(captured["price"].index)
    # NaN 传播: 该日信号不可用
    assert pd.isna(real(captured["price"], total_oi).loc[drop_day])


def test_missing_oi_day_changes_downstream_signal():
    """缺失日 → 定标窗口污染 → 信号与完整数据不同; 且差异不早于被删日。"""
    dates, close, oi = _daily()
    drop_idx = 150
    kept = [i for i in range(len(dates)) if i != drop_idx]
    arr_gap = _call_single(
        FakeStore(_df_1h(), _oi_frame(dates[kept], np.asarray(oi)[kept])), dates, close)[KEY]
    arr_full = _call_single(
        FakeStore(_df_1h(), _oi_frame(dates, oi)), dates, close)[KEY]

    assert not np.allclose(arr_gap, arr_full), "缺失日未产生任何影响, 断言退化"
    before = (_ctx_days() < pd.Timestamp(dates[drop_idx])).values
    np.testing.assert_allclose(arr_gap[:LIMIT][before], arr_full[:LIMIT][before])


# ══════════════════════════════════════════════════════════
#  4. 1H 映射正确性: 每 bar == 该日(含)前最近已收盘日的信号
# ══════════════════════════════════════════════════════════

def test_context_bars_follow_daily_signal_by_day():
    """手算基准: 直接用 compute_oi_gated_momentum 逐日算, 再按日查表比对。"""
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    arr = _call_single(store, dates, close)[KEY]

    price = pd.Series(np.asarray(close, dtype=float), index=pd.DatetimeIndex(dates))
    total_oi = pd.Series(np.asarray(oi, dtype=float), index=pd.DatetimeIndex(dates))
    expected_daily = compute_oi_gated_momentum(price, total_oi)

    last_v = 0.0
    hits = 0
    for i, d in enumerate(_ctx_days()):
        v = expected_daily.get(d)
        if v is not None and pd.notna(v):
            last_v = float(v)
            hits += 1
        assert arr[i] == pytest.approx(last_v, abs=0.0), f"bar {i} ({d}) 映射错误"
    assert hits > 0, "夹具退化: 无任何 bar 命中日线信号"


def test_gate_active_at_cutoff_bar():
    """门控在 cutoff bar 激活 (arr[ctx-1] != 0) — 保证映射断言非空跑。"""
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    arr = _call_single(store, dates, close)[KEY]
    assert arr[LIMIT - 1] != 0.0, "总持仓夹具未激活门控, 上游断言会退化为全零对比"


def test_prewarmup_nan_is_filled_with_zero_and_warned(caplog):
    """日线预热期不足 (K=120 定标窗未满) → 日线信号全 NaN → 1H 段必须填 0 且告警。

    这是 NaN 安全网真正被走到的路径 (不是死代码): 若安全网被删, 此处会漏出 NaN。
    """
    dates, close, oi = _daily(n=90)  # < K+5, 定标窗永不满 → 日线信号全 NaN
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    with caplog.at_level(logging.WARNING):
        arr = _call_single(store, dates, close)[KEY]
    assert np.isfinite(arr).all(), "NaN 漏进协变量矩阵"
    np.testing.assert_array_equal(arr, np.zeros(LIMIT + HORIZON))
    assert any("NaN" in r.getMessage() for r in caplog.records), "NaN 填充未告警"


def test_zero_signal_semantics_for_flat_oi():
    """总持仓完全走平 → ΔOI=0 → 门控精确归零 (spec §2.1 减仓/平仓→衰减至零)。"""
    dates, close, oi = _daily()
    flat_oi = np.full(len(dates), 1_000_000.0)
    store = FakeStore(_df_1h(), _oi_frame(dates, flat_oi))
    arr = _call_single(store, dates, close)[KEY]
    np.testing.assert_array_equal(arr, np.zeros(LIMIT + HORIZON))


# ══════════════════════════════════════════════════════════
#  5. combo 路径
# ══════════════════════════════════════════════════════════

def test_combo_key_reachable_and_matches_single_path():
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    single = _call_single(store, dates, close)
    combo = build_combo_covariate_matrix(
        "m", store, np.asarray(close, dtype=float), np.array([close[-1], close[-1] + 5.0]),
        dates, horizon=HORIZON, limit=LIMIT, covariate_types=[KEY],
    )
    assert KEY in combo, f"combo 路径缺 key {KEY!r}, keys={sorted(combo)}"
    assert len(combo[KEY]) == len(combo["daily_slope"])
    assert np.isfinite(combo[KEY]).all()
    np.testing.assert_allclose(combo[KEY], single[KEY])


def test_combo_with_other_covariate():
    dates, close, oi = _daily()
    store = FakeStore(_df_1h(), _oi_frame(dates, oi))
    combo = build_combo_covariate_matrix(
        "m", store, np.asarray(close, dtype=float), np.array([close[-1], close[-1] + 5.0]),
        dates, horizon=HORIZON, limit=LIMIT, covariate_types=[KEY, "oi"],
    )
    assert set(combo) == {"daily_slope", KEY, "oi_pct_change"}
