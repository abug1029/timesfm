"""数据级验收: index_continuous_1d (KQ.i@m 指数合约, open_interest=全市场总持仓)。

上游 spec: docs/2026-09-18-oi-gated-momentum-spec.md §3.1 / §3.4 / §6.2
回填脚本: scripts/fetch_index_continuous.py
TDD: 回填前运行, 因表不存在而失败; 回填后全绿。
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from data.config import get_db_path  # noqa: E402

DB_PATH = get_db_path("m")
REQUIRED_COLUMNS = {"dt", "close_price", "volume", "open_interest"}


@pytest.fixture(scope="module")
def conn():
    if not DB_PATH.exists():
        pytest.fail(f"数据库不存在: {DB_PATH}")
    c = sqlite3.connect(str(DB_PATH))
    yield c
    c.close()


@pytest.fixture(scope="module")
def index_df(conn) -> pd.DataFrame:
    """回填前表不存在 -> 本 fixture 直接失败 (TDD 红灯)。"""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='index_continuous_1d'"
    ).fetchone()
    if not exists:
        pytest.fail("index_continuous_1d 表不存在 (先运行 scripts/fetch_index_continuous.py 回填)")
    return pd.read_sql_query(
        "SELECT dt, close_price, volume, open_interest FROM index_continuous_1d ORDER BY dt",
        conn,
    )


@pytest.fixture(scope="module")
def main_dates(conn) -> set:
    """价格日历基准 (spec §3.4): main_continuous_1d 的 dt 集合。"""
    return set(pd.read_sql_query("SELECT dt FROM main_continuous_1d", conn)["dt"])


# ══════════════════════════════════════════════════════
#  1. 表结构: 存在 + dt 唯一键 (宿主硬性要求, 防 merge 笛卡尔积)
# ══════════════════════════════════════════════════════

def test_dt_is_unique_key(conn):
    cols = conn.execute("PRAGMA table_info(index_continuous_1d)").fetchall()
    col_names = {c[1].lower() for c in cols}
    assert REQUIRED_COLUMNS <= col_names, f"缺列: {REQUIRED_COLUMNS - col_names}"

    # dt 为单列主键
    pk_cols = [c[1].lower() for c in cols if c[5] > 0]
    if pk_cols == ["dt"]:
        return
    # 或 dt 上有单列 UNIQUE 索引
    for idx in conn.execute("PRAGMA index_list(index_continuous_1d)").fetchall():
        if idx[2]:  # unique=1
            idx_cols = [r[2].lower() for r in conn.execute(
                f"PRAGMA index_info('{idx[1]}')").fetchall()]
            if idx_cols == ["dt"]:
                return
    pytest.fail("dt 必须是 PRIMARY KEY 或带 UNIQUE 索引 (防 merge 笛卡尔积)")


def test_no_duplicate_dates(index_df):
    dup = index_df["dt"].duplicated().sum()
    assert dup == 0, f"dt 存在 {dup} 条重复 (merge 会产生笛卡尔积)"


def test_column_types(conn):
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='index_continuous_1d'"
    ).fetchone()[0]
    assert re.search(r"dt\s+TEXT", ddl, re.IGNORECASE), "dt 必须为 TEXT"
    for col in ("close_price", "volume", "open_interest"):
        assert re.search(rf"{col}\s+REAL", ddl, re.IGNORECASE), f"{col} 必须为 REAL"


# ══════════════════════════════════════════════════════
#  2. 覆盖区间: 2016-01-05 → 今 (回退硬线: 不晚于 2016-03-01)
# ══════════════════════════════════════════════════════

def test_coverage_range(index_df):
    first, last = index_df["dt"].min(), index_df["dt"].max()
    assert first <= "2016-03-01", (
        f"首根有效数据 {first} 晚于 2016-03-01 回退硬线 (KQ.i@m 历史深度不足, "
        f"须回退逐合约回填方案, 不得自行处理)"
    )
    assert first <= "2016-01-05", f"起点 {first} 应不晚于 2016-01-05"
    # 新鲜度: 最新日期距今天不超过 10 个自然日
    today = pd.Timestamp.today().normalize()
    assert pd.to_datetime(last) >= today - pd.Timedelta(days=10), (
        f"最新日期 {last} 距今超过 10 天, 数据不新鲜"
    )


# ══════════════════════════════════════════════════════
#  3. open_interest 卫生: 无 NaN/零/负值, 相对交易日历无空洞
# ══════════════════════════════════════════════════════

def test_oi_no_nan_zero_negative(index_df):
    oi = index_df["open_interest"]
    assert oi.notna().all(), f"open_interest 含 {oi.isna().sum()} 个 NaN"
    assert (oi > 0).all(), (
        f"open_interest 含 {(oi <= 0).sum()} 个零/负值: "
        f"{index_df.loc[oi <= 0, 'dt'].head(10).tolist()}"
    )


def test_price_volume_no_nan(index_df):
    for col in ("close_price", "volume"):
        assert index_df[col].notna().all(), f"{col} 含 NaN"


def test_no_gaps_vs_trading_calendar(index_df, main_dates):
    """相对交易日历 (价格日历为基准) 无缺失日。"""
    dates = set(index_df["dt"])
    first, last = min(dates), max(dates)
    expected = {d for d in main_dates if first <= d <= last}
    missing = sorted(expected - dates)
    assert not missing, (
        f"相对交易日历缺失 {len(missing)} 天 (连续缺失 >3 天触发回退线): {missing[:10]}"
    )


# ══════════════════════════════════════════════════════
#  4. 换月脉冲: 两级断言
#     (a) 硬线: 全表 |ΔOI^tot_5d| ≤ 100% (禁换月翻倍脉冲, spec §3.1)
#     (b) 包络: 全表 |ΔOI^tot_5d| ≤ 25% (宿主量化要求)
# ══════════════════════════════════════════════════════

def _delta5_abs(index_df: pd.DataFrame) -> pd.Series:
    """spec §2.3: ΔOI^tot_5d = OI_t/OI_{t-5} - 1 (pct_change(5), 非 diff)。"""
    oi = index_df.set_index(pd.to_datetime(index_df["dt"]))["open_interest"].sort_index()
    return oi.pct_change(5).abs()


def test_delta_oi_5d_no_rollover_pulse(index_df):
    """硬线: 主力单合约口径换月脉冲 max=154% (spec §3.1); 总持仓口径不应出现翻倍跳变。"""
    delta5 = _delta5_abs(index_df)
    ext = delta5.iloc[5:].max()  # 排除前 5 根预热
    top = delta5.iloc[5:].sort_values(ascending=False).head(5)
    detail = ", ".join(f"{d.date()}={v:.4f}" for d, v in top.items())
    assert ext <= 1.00, (
        f"ΔOI^tot_5d 极值 {ext:.4f} > 100% (主力换月翻倍脉冲特征, 总持仓口径不应出现): "
        f"top5: {detail}"
    )


@pytest.mark.xfail(strict=True, reason=(
    "宿主 25% 包络断言被真实行情击穿, 数据经核为真、非数据伪迹, 阈值待宿主重新裁定 "
    "(勿静默放宽): 全表 max 51.08% @2019-10-14 (10月增仓潮: 总OI 8日连续爬升 1.36M→2.16M, "
    "成交量同步放大 0.94M→2.0M, M_CONT 单合约同向增长 —— 真实市场事件); "
    "换月窗口(12/4/8月中旬) max 27.05% @2016-04-22 (2016-04 商品过热后交易所提保引发连续减仓, "
    "总OI 1.90M→1.36M 伴随巨量成交, 单合约同向)。明细见 "
    "docs/2026-09-18-oi-gated-momentum-data-quality-report.md §4"
))
def test_delta_oi_5d_envelope_25pct(index_df):
    """宿主包络: 全表 |ΔOI^tot_5d| ≤ 25%。实测 51.08%, 真实行情击穿 → xfail(宿主裁决项)。"""
    delta5 = _delta5_abs(index_df)
    ext = delta5.iloc[5:].max()
    top = delta5.iloc[5:].sort_values(ascending=False).head(5)
    detail = ", ".join(f"{d.date()}={v:.4f}" for d, v in top.items())
    assert ext <= 0.25, (
        f"ΔOI^tot_5d 极值 {ext:.4f} > 25% 绝对值: top5: {detail}"
    )


# ══════════════════════════════════════════════════════
#  5. 日历对齐: 与 main_continuous_1d 差集为空或可解释 (禁 ffill 语义)
# ══════════════════════════════════════════════════════

def test_calendar_alignment_with_main(conn, index_df, main_dates):
    dates = set(index_df["dt"])

    # (a) 价格日历有、指数无 -> 必须为空, 或缺失日以 NaN/空记录落表 (fail-closed)
    missing = sorted(main_dates - dates)
    if missing:
        ph = ",".join(["?"] * len(missing))
        rows = pd.read_sql_query(
            f"SELECT dt, close_price, open_interest FROM index_continuous_1d WHERE dt IN ({ph})",
            conn, params=missing,
        ).set_index("dt")
        unexplained = [
            d for d in missing
            if d not in rows.index or (pd.notna(rows.loc[d, "close_price"])
                                       and pd.notna(rows.loc[d, "open_interest"]))
        ]
        assert not unexplained, (
            f"与 main_continuous_1d 缺失 {len(missing)} 天且无 NaN 占位解释: {unexplained[:10]}"
        )

    # (b) 指数有、价格日历无 -> 仅允许晚于 main 最新日 (当日盘后新增, 主链未同步)
    extras = sorted(dates - main_dates)
    main_max = max(main_dates)
    mid_history_extras = [d for d in extras if d <= main_max]
    assert not mid_history_extras, (
        f"指数日历中存在价格日历没有的历史日 (疑似日历错位): {mid_history_extras[:10]}"
    )
