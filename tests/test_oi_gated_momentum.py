"""oi_gated_momentum 模块 TDD 测试 (spec v2.1 §6.1 验收清单)。

Spec: docs/2026-09-18-oi-gated-momentum-spec.md
TDD: 先于实现编写并确认红灯 (模块不存在), 实现后转绿。

覆盖 (spec §6.1 全覆盖 + 宿主裁定复核项):
- 索引一致性: index 不一致 raise ValueError (宿主要求, 入口第一行)
- 门控四象限表逐格断言 (§2.1)
- 标尺无样本内污染 (§4.1): 扰动 bar t → scale 逐位不变; 扰动 t-1 → scale 变化
- 与 §4.1 标准实现口径逐位对照 (含 shift(1) 定标窗口与 pct_change(5) 算子)
- 非对称定标 (§2.3): 窗口注入极端负 ΔOI, scale_oi 与门控激活度不变
- 算子钉死: pct_change(5) 语义成立, diff(5) 语义下断言必失败
- NaN/inf/bool 输入 → NaN (fail-closed); 分位数 ≤1e-6 → NaN (不产生 inf)
- 预热期 (前 K 日 + 5 日窗) NaN
- 确定性: 同输入两次调用逐位相等
- 极端值数学行为: ΔOI=+51% 门控饱和 (>0.99); ΔOI=-30% 输出精确 0
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from cascade.oi_gated_momentum import compute_oi_gated_momentum  # noqa: E402

K, Q_PRICE, Q_OI = 120, 0.75, 0.85


def _idx(n):
    return pd.bdate_range("2020-01-01", periods=n)


def _make_data(n=300, seed=7, price_level=100.0, oi_level=1_000_000.0):
    """确定性 (固定种子) 价格/总持仓序列：价格日变动 ~±0.05%；
    OI 带 +0.2%/日漂移 (保证带符号 85% 分位恒为正, 避免 fail-closed 干扰断言)。"""
    rng = np.random.default_rng(seed)
    price = pd.Series(
        price_level * np.cumprod(1.0 + rng.normal(0.0, 0.0005, n)), index=_idx(n))
    oi = pd.Series(
        oi_level * np.cumprod(1.0 + rng.normal(0.002, 0.003, n)), index=_idx(n))
    return price, oi


def _ref_signal(price, total_oi, k=K, q_price=Q_PRICE, q_oi=Q_OI, oi_op="pct_change"):
    """按 spec §4.1 标准实现口径独立复算期望信号 (测试侧对照实现)。"""
    abs_delta_p = price.pct_change(5).abs()
    delta_oi = total_oi.pct_change(5) if oi_op == "pct_change" else total_oi.diff(5)
    q_p = abs_delta_p.shift(1).rolling(k).quantile(q_price)
    q_oi = delta_oi.shift(1).rolling(k).quantile(q_oi)
    scale_p = pd.Series(np.where(q_p > 1e-6, 1.0 / q_p, np.nan), index=price.index)
    scale_oi = pd.Series(np.where(q_oi > 1e-6, 1.0 / q_oi, np.nan), index=price.index)
    return np.tanh(price.pct_change(5) * scale_p) * np.maximum(
        0.0, np.tanh(delta_oi * scale_oi))


def _ref_scales(price, total_oi, k=K, q_price=Q_PRICE, q_oi=Q_OI):
    """按 §4.1 独立复算 scale_p/scale_oi (用于标尺扰动不变性断言)。"""
    q_p = price.pct_change(5).abs().shift(1).rolling(k).quantile(q_price)
    q_oi = total_oi.pct_change(5).shift(1).rolling(k).quantile(q_oi)
    return (
        pd.Series(np.where(q_p > 1e-6, 1.0 / q_p, np.nan), index=price.index),
        pd.Series(np.where(q_oi > 1e-6, 1.0 / q_oi, np.nan), index=price.index),
    )


# ══════════════════════════════════════════════════════
#  1. 输入契约与确定性
# ══════════════════════════════════════════════════════

class TestContract:
    def test_index_mismatch_raises_valueerror(self):
        """宿主要求: price 与 total_oi 索引不一致 → raise ValueError。"""
        price, oi = _make_data(260)
        oi_bad = oi.copy()
        oi_bad.index = pd.bdate_range("2020-01-02", periods=len(oi_bad))
        with pytest.raises(ValueError):
            compute_oi_gated_momentum(price, oi_bad)

    def test_index_check_precedes_input_sanitization(self):
        """索引校验是入口第一行: 即使输入另有问题 (bool 序列 + 错索引) 也先报 ValueError。"""
        price, oi = _make_data(260)
        price_bool = (price > price.mean()).astype(bool)
        price_bool.index = pd.bdate_range("2020-01-02", periods=len(price_bool))
        with pytest.raises(ValueError):
            compute_oi_gated_momentum(price_bool, oi)

    def test_deterministic_bitwise(self):
        price, oi = _make_data()
        a = compute_oi_gated_momentum(price, oi)
        b = compute_oi_gated_momentum(price, oi)
        assert a.equals(b)

    def test_output_contract(self):
        price, oi = _make_data()
        out = compute_oi_gated_momentum(price, oi)
        assert isinstance(out, pd.Series)
        assert out.index.equals(price.index)
        assert out.dtype == np.float64
        assert out.name == "oi_gated_momentum"


# ══════════════════════════════════════════════════════
#  2. 门控四象限表 (spec §2.1 机制表逐格)
# ══════════════════════════════════════════════════════

def test_four_quadrant_gating():
    """增仓上涨>0 / 减仓上涨=0 / 增仓下跌<0 / 减仓下跌=0 (精确零)。"""
    n = 300
    base_price, base_oi = _make_data(n)
    t = n - 1

    def run(price_factor, oi_factor):
        price = base_price.copy()
        oi = base_oi.copy()
        price.iloc[t] = price.iloc[t - 5] * price_factor
        oi.iloc[t] = oi.iloc[t - 5] * oi_factor
        return compute_oi_gated_momentum(price, oi).iloc[t]

    s_uu = run(1.05, 1.10)   # 增仓上涨
    s_ud = run(1.05, 0.80)   # 减仓上涨
    s_du = run(0.95, 1.10)   # 增仓下跌
    s_dd = run(0.95, 0.80)   # 减仓下跌

    assert s_uu > 0, f"增仓上涨应 >0, 实得 {s_uu}"
    assert s_ud == 0.0, f"减仓上涨应精确 0.0, 实得 {s_ud}"
    assert s_du < 0, f"增仓下跌应 <0, 实得 {s_du}"
    assert s_dd == 0.0, f"减仓下跌应精确 0.0, 实得 {s_dd}"


# ══════════════════════════════════════════════════════
#  3. 标尺无样本内污染 (spec §4.1) + §4.1 口径逐位对照
# ══════════════════════════════════════════════════════

def test_scale_pollution_and_spec_4_1_pinning():
    price, oi = _make_data(300)
    t = len(price) - 1
    # 构造 bar t-1 为定标窗口最大值（ΔOI=+5%、|ΔP|=2%，远大于噪声 ~0.7%/~0.1%），
    # 扰动后替换为深负/极小值，保证其秩位必然变化，断言才具有确定性
    price.iloc[t - 1] = price.iloc[t - 6] * 1.02
    oi.iloc[t - 1] = oi.iloc[t - 6] * 1.05

    # (a) 扰动当期 bar t: scale_p/scale_oi 逐位不变 (定标窗口 [t-K, t-1] 不含 bar t)
    sp_base, so_base = _ref_scales(price, oi)
    price2, oi2 = price.copy(), oi.copy()
    price2.iloc[t] *= 1.5
    oi2.iloc[t] *= 1.5
    sp_2, so_2 = _ref_scales(price2, oi2)
    np.testing.assert_array_equal(sp_base.values, sp_2.values)  # NaN 视为相等
    np.testing.assert_array_equal(so_base.values, so_2.values)

    # (b) 扰动 t-1: 位置 t 的 scale 必须变化
    price3, oi3 = price.copy(), oi.copy()
    price3.iloc[t - 1] = price3.iloc[t - 6] * 1.000001  # |ΔP_5d| ≈ 0 → 落入下尾
    oi3.iloc[t - 1] = oi3.iloc[t - 6] * 0.95            # ΔOI_5d = -5% → 落入下尾
    sp_3, so_3 = _ref_scales(price3, oi3)
    assert sp_3.iloc[t] != sp_base.iloc[t], "扰动 t-1 后 scale_p 应变化"
    assert so_3.iloc[t] != so_base.iloc[t], "扰动 t-1 后 scale_oi 应变化"

    # (c) 模块输出与 §4.1 标准口径逐位对照 (把模块钉死在 shift(1) 定标 + 当期因子上)
    out = compute_oi_gated_momentum(price, oi)
    expected = _ref_signal(price, oi)
    np.testing.assert_allclose(out.values, expected.values, rtol=0, atol=0)


# ══════════════════════════════════════════════════════
#  4. 非对称定标 (spec §2.3): 带符号 85% 分位免疫减仓下尾
# ══════════════════════════════════════════════════════

def test_asymmetric_scaling_immune_to_lower_tail():
    """窗口内注入极端负 ΔOI: 单日 -50% (A) vs -75% (B) 踩踏, 深度不影响 scale_oi
    与门控激活度 (注入值恒居下尾低秩, 不动 85% 分位)。"""
    n = 300
    base_price, base_oi = _make_data(n)
    j = n - 80  # 踩踏起点 (在定标窗口内, 距评估 bar t 充分远)
    t = n - 20

    def stepped(factor):
        # 单日 -X% 踩踏且不复位: m>=j 起水平下移, delta5 在 j..j+4 出现 5 个深负值
        oi = base_oi.copy()
        oi.iloc[j:] = oi.iloc[j:] * factor
        return base_price.copy(), oi

    pa, oa = stepped(0.5)
    pb, ob = stepped(0.25)
    out_a = compute_oi_gated_momentum(pa, oa)
    out_b = compute_oi_gated_momentum(pb, ob)

    # 门控激活度不变 (价格路径/ΔP/scale_p 全同, ΔOI_t 亦逐位同)
    assert out_a.iloc[t] == out_b.iloc[t], (
        f"极端负 ΔOI 注入深度不应影响门控: {out_a.iloc[t]} vs {out_b.iloc[t]}")
    # scale_oi 逐位不变
    _, so_a = _ref_scales(pa, oa)
    _, so_b = _ref_scales(pb, ob)
    assert so_a.iloc[t] == so_b.iloc[t], "scale_oi 应对下尾深度免疫 (逐位)"


# ══════════════════════════════════════════════════════
#  5. 算子钉死 (spec §2.3): pct_change(5), 禁 diff(5)
# ══════════════════════════════════════════════════════

def test_operator_pinned_pct_change_not_diff():
    """OI 强趋势 (日 +1%) 下 pct_change(5) 与 diff(5) 定标可分离:
    模块输出必须等于 pct_change 口径, 且与 diff 口径显著可分离 (diff 语义必失败)。"""
    n = 300
    base_price, base_oi = _make_data(n)
    t = n - 1
    oi = pd.Series(base_oi.iloc[0] * np.power(1.01, np.arange(n)), index=base_oi.index)
    price = base_price.copy()
    price.iloc[t] = price.iloc[t - 5] * 1.03

    out = compute_oi_gated_momentum(price, oi).iloc[t]
    ref_pct = _ref_signal(price, oi, oi_op="pct_change").iloc[t]
    ref_diff = _ref_signal(price, oi, oi_op="diff").iloc[t]

    np.testing.assert_allclose(out, ref_pct, rtol=0, atol=1e-12)
    assert abs(out - ref_diff) > 0.01, (
        f"模块输出与 diff(5) 口径不可分离 ({out} vs {ref_diff}), 算子钉死失效")


# ══════════════════════════════════════════════════════
#  6. fail-closed: NaN/inf/bool/非数值; 分位数退化; 预热期
# ══════════════════════════════════════════════════════

class TestFailClosed:
    def test_nan_input_propagates(self):
        price, oi = _make_data(300)
        j = 150  # 预热期 (K+5=125) 之后
        price_bad = price.copy()
        price_bad.iloc[j] = np.nan
        out = compute_oi_gated_momentum(price_bad, oi)
        assert out.iloc[K + 5:j].notna().all(), "污染点之前应正常输出"
        # NaN 经 pct_change 5 日窗 + K 日定标窗传播: j .. j+5+K 全 NaN
        assert out.iloc[j:j + K + 6].isna().all()

    def test_inf_input_fail_closed(self):
        price, oi = _make_data(300)
        j = 150  # 预热期 (K+5=125) 之后
        price_bad = price.copy()
        price_bad.iloc[j] = np.inf
        out = compute_oi_gated_momentum(price_bad, oi)
        assert out.iloc[K + 5:j].notna().all()
        assert out.iloc[j:j + K + 6].isna().all()
        assert not np.isinf(out.dropna()).any(), "输出不得含 inf"

    def test_bool_input_fail_closed(self):
        price, oi = _make_data(300)
        out = compute_oi_gated_momentum(price.astype(bool), oi)
        assert out.isna().all()
        out2 = compute_oi_gated_momentum(price, oi.astype(bool))
        assert out2.isna().all()

    def test_object_with_bool_and_str_fail_closed(self):
        """bool 是 int 子类: 混入 object 序列的 True 不得被当作 1.0 (本仓惯例)。"""
        price, oi = _make_data(300)
        price_obj = price.astype(object)
        price_obj.iloc[150] = True
        price_obj.iloc[151] = "oops"
        out = compute_oi_gated_momentum(price_obj, oi)
        assert out.iloc[K + 5:150].notna().all()
        assert out.iloc[150:156].isna().all(), "bool/str 位置起应 NaN 传播"
        assert not np.isinf(out.dropna()).any()

    def test_quantile_degenerate_no_inf(self):
        """常数序列 → 分位数 0 ≤ 1e-6 → scale NaN → 输出 NaN, 绝不产生 inf。"""
        idx = _idx(260)
        price = pd.Series(100.0, index=idx)
        oi = pd.Series(1_000_000.0, index=idx)
        out = compute_oi_gated_momentum(price, oi)
        assert out.iloc[K + 5:].isna().all()
        assert not np.isinf(out.values[np.isfinite(out.values)]).any()

    def test_warmup_nan_then_valid(self):
        price, oi = _make_data(300)
        out = compute_oi_gated_momentum(price, oi)
        assert out.iloc[:K + 5].isna().all(), "前 K 日 + 5 日窗为预热期, 应全 NaN"
        assert np.isfinite(out.iloc[K + 5]), "预热期结束应产出有效信号"
        assert out.iloc[K + 5:].notna().all()


# ══════════════════════════════════════════════════════
#  7. 极端值数学行为 (宿主裁定复核项)
# ══════════════════════════════════════════════════════

def test_extreme_positive_oi_gate_saturates():
    """ΔOI=+51% 场景 (2019-10 增仓潮量级): 门控 tanh 深度饱和, 信号 > 0.99。"""
    price, oi = _make_data(300)
    t = len(price) - 1
    oi2 = oi.copy()
    oi2.iloc[t] = oi.iloc[t - 5] * 1.51
    price2 = price.copy()
    price2.iloc[t] = price.iloc[t - 5] * 1.02
    out = compute_oi_gated_momentum(price2, oi2).iloc[t]
    assert out > 0.99, f"ΔOI=+51% 应门控饱和 (>0.99), 实得 {out}"


def test_extreme_negative_oi_exact_zero():
    """ΔOI=-30% 场景: 减仓 → 门控精确归零, 输出精确 0 (价格上涨亦不放大)。"""
    price, oi = _make_data(300)
    t = len(price) - 1
    oi2 = oi.copy()
    oi2.iloc[t] = oi.iloc[t - 5] * 0.70
    price2 = price.copy()
    price2.iloc[t] = price.iloc[t - 5] * 1.05
    out = compute_oi_gated_momentum(price2, oi2).iloc[t]
    assert out == 0.0, f"ΔOI=-30% 应精确 0.0, 实得 {out}"
