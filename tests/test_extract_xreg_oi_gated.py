"""oi_gated_momentum 步骤四注册校验测试 (TDD, 先红后绿)。

上游:
- spec: docs/2026-09-18-oi-gated-momentum-spec.md §4/§5
- 计划步骤四: docs/2026-09-18-oi-gated-momentum-impl-plan.md
- 模块: cascade/oi_gated_momentum.py compute_oi_gated_momentum (步骤二交付, 参数冻结)

断言面:
1. extract_xreg 读 main_continuous_1d.close_price + index_continuous_1d.open_interest
   (KQ.i@m 总持仓) 经 compute_oi_gated_momentum 计算, 写 xreg_factors
2. 注册值与模块直接调用逐位一致 (冻结默认参数, 无运行时注入)
3. 异构源日历 (spec §3.4): 价格日历为基准 left join, OI 缺失日 → NaN 信号不落表 (禁 ffill)
4. 预热期 NaN 不落表
5. pool 条目契约: status=experimental / gated=True / family=momentum / mechanism 含 spec 路径
6. evaluator._load_gated_covariates 可发现 gated 声明
7. menu materialize 渲染 experimental (host testing) 栏 (dry-run 到 tmp, 不触生产 menu)
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

POOL_PATH = ROOT / "task_FM" / "config" / "covariate_pool.json"


def _make_db(tmp_path, price_rows, oi_rows):
    """tmp sqlite 库: main_continuous_1d + index_continuous_1d + xreg_factors。

    price_rows/oi_rows: list[(dt, value)]。
    """
    import sqlite3
    db = tmp_path / "futures_m.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE main_continuous_1d (dt TEXT PRIMARY KEY, close_price REAL)")
    c.execute("CREATE TABLE index_continuous_1d (dt TEXT PRIMARY KEY, open_interest REAL)")
    c.execute("CREATE TABLE xreg_factors (dt TEXT, symbol TEXT, factor_name TEXT, "
              "factor_value REAL, PRIMARY KEY (dt, symbol, factor_name))")
    c.executemany("INSERT INTO main_continuous_1d VALUES (?, ?)", price_rows)
    c.executemany("INSERT INTO index_continuous_1d VALUES (?, ?)", oi_rows)
    c.commit()
    c.close()
    return db


def _load_tmp_conn(db):
    import sqlite3
    return sqlite3.connect(str(db))


@pytest.fixture
def synth_db(tmp_path, monkeypatch):
    """合成 200 日 price/oi 数据 + tmp 库; monkeypatch extract_xreg.get_conn。"""
    import extract_xreg
    dates = pd.bdate_range("2020-01-01", periods=200).strftime("%Y-%m-%d")
    rng = np.random.default_rng(42)
    price = 3000 + np.cumsum(rng.normal(0, 20, 200))
    oi = 1_500_000 + np.cumsum(rng.normal(0, 15000, 200))
    price_rows = [(d, float(p)) for d, p in zip(dates, price)]
    oi_rows = [(d, float(o)) for d, o in zip(dates, oi)]
    db = _make_db(tmp_path, price_rows, oi_rows)
    conn = _load_tmp_conn(db)
    monkeypatch.setattr(extract_xreg, "get_conn", lambda s: conn)
    yield conn
    conn.close()


def test_registration_matches_direct_module_call(synth_db):
    """注册值 == compute_oi_gated_momentum(price, oi) 直接调用, 逐位一致。"""
    import extract_xreg
    n = extract_xreg.extract_oi_gated_momentum("m")
    assert n > 0
    price_df = pd.read_sql_query(
        "SELECT dt, close_price FROM main_continuous_1d WHERE close_price IS NOT NULL ORDER BY dt",
        synth_db)
    oi_df = pd.read_sql_query(
        "SELECT dt, open_interest FROM index_continuous_1d ORDER BY dt", synth_db)
    from cascade.oi_gated_momentum import compute_oi_gated_momentum
    price = pd.Series(price_df["close_price"].values,
                      index=pd.to_datetime(price_df["dt"]))
    total_oi = pd.Series(oi_df["open_interest"].values,
                         index=pd.to_datetime(oi_df["dt"]))
    expected = compute_oi_gated_momentum(price, total_oi)
    got = pd.read_sql_query(
        "SELECT dt, factor_value FROM xreg_factors WHERE factor_name='oi_gated_momentum' ORDER BY dt",
        synth_db)
    assert len(got) == int(expected.notna().sum())
    exp_valid = expected.dropna()
    got_vals = got["factor_value"].values
    assert np.array_equal(got_vals, exp_valid.values)
    got_dates = list(got["dt"])
    exp_dates = [d.strftime("%Y-%m-%d") for d in exp_valid.index]
    assert got_dates == exp_dates


def test_frozen_params_no_runtime_override(synth_db, monkeypatch):
    """生产注册必须用冻结默认参数 (spec §4: 慢环无调参自由度)。"""
    import cascade.oi_gated_momentum as oigm
    orig = oigm.compute_oi_gated_momentum
    captured = {}

    def fake_compute(price, total_oi, **kw):
        captured.update(kw)
        return orig(price, total_oi)

    monkeypatch.setattr(oigm, "compute_oi_gated_momentum", fake_compute)
    import extract_xreg
    extract_xreg.extract_oi_gated_momentum("m")
    assert captured == {}


def test_calendar_left_join_fail_closed(synth_db):
    """OI 表缺一个中间日 → 该日及后续 5 日信号 NaN 不落表 (禁 ffill, fail-closed)。"""
    import extract_xreg
    conn = synth_db
    conn.execute("DELETE FROM index_continuous_1d WHERE dt='2020-07-06'")
    conn.commit()
    n = extract_xreg.extract_oi_gated_momentum("m")
    got = pd.read_sql_query(
        "SELECT dt FROM xreg_factors WHERE factor_name='oi_gated_momentum' ORDER BY dt",
        conn)
    dates = set(got["dt"])
    # 缺失日及后 5 日 (pct_change 窗口跨缺日) 必须无信号行 (fail-closed, 禁 ffill)
    for d in pd.bdate_range("2020-07-06", periods=5).strftime("%Y-%m-%d"):
        assert d not in dates, f"缺失日后窗口日 {d} 不应有信号 (禁 ffill)"
    assert n > 0


def test_warmup_nan_not_written(synth_db):
    """预热期 (定标窗口不足) NaN 不落表。"""
    import extract_xreg
    extract_xreg.extract_oi_gated_momentum("m")
    got = pd.read_sql_query(
        "SELECT MIN(dt) AS first_dt FROM xreg_factors WHERE factor_name='oi_gated_momentum'",
        synth_db)
    first_dt = got["first_dt"].iloc[0]
    dates = pd.bdate_range("2020-01-01", periods=200).strftime("%Y-%m-%d")
    idx = list(dates).index(first_dt)
    # 结构性预热: pct_change(5) 从 idx5 有效, shift(1)→idx6, rolling(120) 需 120 个
    # 非 NaN → 首个有效信号 idx = 6+120-1 = 125
    assert idx >= 125, f"首个信号日应在预热期之后 (实际 idx={idx}, dt={first_dt})"


def test_pool_entry_contract():
    """pool 条目: experimental / gated=True / family=momentum / mechanism 含 spec 路径。"""
    with open(POOL_PATH, encoding="utf-8") as f:
        pool = json.load(f)
    e = pool["covariates"].get("oi_gated_momentum")
    assert e, "covariate_pool.json 缺 oi_gated_momentum 条目"
    assert e["status"] == "experimental"
    assert e["gated"] is True
    assert e["family"] == "momentum"
    assert len(e["mechanism"]) >= 15
    assert "docs/2026-09-18-oi-gated-momentum-spec.md" in e["mechanism"]


def test_gated_declaration_discoverable():
    """evaluator._load_gated_covariates 从池中读出 gated 声明。"""
    sys.path.insert(0, str(ROOT / "task_FM" / "evaluations" / "fm_eval"))
    import evaluator as ev
    names, err = ev._load_gated_covariates()
    assert err is None
    assert "oi_gated_momentum" in names


def test_menu_materialize_experimental_section(tmp_path):
    """menu materialize dry-run: experimental 栏渲染 (tmp 目标, 不触生产 menu)。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import praxist_supervisor as sup
    with open(POOL_PATH, encoding="utf-8") as f:
        pool = json.load(f)
    dest = tmp_path / "menu_dryrun.inc.md"
    sup.materialize_covariate_menu(pool["covariates"], str(dest))
    text = dest.read_text(encoding="utf-8")
    marker = "### experimental (host testing"
    assert marker in text, "experimental 栏未渲染"
    sec = text.split(marker, 1)[1].split("###", 1)[0]
    assert "- oi_gated_momentum" in sec
