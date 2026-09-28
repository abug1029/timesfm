"""n_eff 实测测试 — PR-C3 实施验收"""

import pytest
import numpy as np
from cascade.evaluation_metrics import measured_n_eff, compute_meets_min_info


def test_measured_n_eff_iid():
    """测试 IID 序列的 n_eff"""
    np.random.seed(42)
    x = np.random.randn(1000)
    n_eff, status = measured_n_eff(x)

    # IID 序列的 n_eff 应该接近 n
    assert status == "ok"
    assert 900 < n_eff < 1100


def test_measured_n_eff_ar1():
    """测试 AR(1) 序列的 n_eff"""
    np.random.seed(42)
    n = 1000
    rho = 0.5
    x = np.zeros(n)
    x[0] = np.random.randn()
    for t in range(1, n):
        x[t] = rho * x[t-1] + np.random.randn()

    n_eff, status = measured_n_eff(x)

    # AR(1) 序列的 n_eff 应该小于 n
    assert status == "ok"
    assert n_eff < n


def test_measured_n_eff_constant():
    """测试常数序列的 n_eff"""
    x = np.ones(100)
    n_eff, status = measured_n_eff(x)

    assert status == "degenerate_constant"
    assert n_eff == 1.0


def test_measured_n_eff_insufficient_n():
    """测试样本不足的 n_eff"""
    x = np.random.randn(20)
    n_eff, status = measured_n_eff(x)

    assert status == "insufficient_n"
    assert n_eff is None


def test_measured_n_eff_nonfinite():
    """测试非有限值的 n_eff"""
    x = np.array([1.0, 2.0, np.nan, 4.0])
    n_eff, status = measured_n_eff(x)

    assert status == "nonfinite"
    assert n_eff is None


def test_measured_n_eff_negative_variance():
    """测试长程方差为负时的夹取行为。

    审计 D8 修正: 原测试用 `np.random.randn(100)` —— 那是**近似白噪声**，
    其长程方差**不会**为负，因此该测试根本没走到夹取分支（vacuous test）。

    构造真正产生负长程方差的序列：交替符号的强负自相关序列。
    注意：Bartlett 核设计为保证正半定性，实际上很难构造出负长程方差的平稳序列。
    若构造失败则跳过此测试（标记为 xfail）。
    """
    n = 500
    np.random.seed(42)

    # 尝试多种构造方法
    candidates = []

    # 方法 1: 强负自相关 AR(1)
    rho = -0.95
    x1 = np.zeros(n)
    x1[0] = np.random.randn()
    for t in range(1, n):
        x1[t] = rho * x1[t - 1] + np.random.randn() * 0.05
    candidates.append(x1)

    # 方法 2: 交替符号序列 + 噪声
    x2 = np.array([(-1)**t * (1.0 + 0.1 * np.random.randn()) for t in range(n)])
    candidates.append(x2)

    # 方法 3: 高频振荡
    x3 = np.sin(np.arange(n) * np.pi) + 0.1 * np.random.randn(n)
    candidates.append(x3)

    # 找到第一个产生负长程方差的序列
    found = False
    for x in candidates:
        x_c = x - np.mean(x)
        q = 11
        gamma0 = np.mean(x_c ** 2)
        lr = gamma0 + 2 * sum(
            (1 - j / (q + 1)) * np.mean(x_c[j:] * x_c[:-j])
            for j in range(1, q + 1)
        )
        if lr < 0:
            found = True
            break

    if not found:
        pytest.skip("无法构造出负长程方差的序列（Bartlett 核正半定性保护）")

    n_eff, status = measured_n_eff(x)
    assert status == "clipped_to_iid", "负长程方差必须走夹取分支"
    assert n_eff is not None
    assert n_eff <= n


def test_meets_min_info_all_conditions_met():
    """测试所有条件都满足的情况"""
    result = compute_meets_min_info(
        n=100,
        n_eff=73,
        n_eff_status="ok",
        dm_common_count=60
    )
    assert result is True


def test_meets_min_info_n_too_small():
    """测试样本量太小"""
    result = compute_meets_min_info(
        n=20,
        n_eff=73,
        n_eff_status="ok",
        dm_common_count=60
    )
    assert result is False


def test_meets_min_info_n_eff_too_small():
    """测试 n_eff 太小"""
    result = compute_meets_min_info(
        n=100,
        n_eff=30,
        n_eff_status="ok",
        dm_common_count=60
    )
    assert result is False


def test_meets_min_info_dm_common_count_too_small():
    """测试 DM 配对数量太小"""
    result = compute_meets_min_info(
        n=100,
        n_eff=73,
        n_eff_status="ok",
        dm_common_count=30
    )
    assert result is False


def test_meets_min_info_invalid_n_eff_status():
    """测试无效的 n_eff_status"""
    result = compute_meets_min_info(
        n=100,
        n_eff=73,
        n_eff_status="insufficient_n",
        dm_common_count=60
    )
    assert result is False


def test_meets_min_info_degenerate_constant():
    """测试常数序列（degenerate_constant）"""
    result = compute_meets_min_info(
        n=100,
        n_eff=1,
        n_eff_status="degenerate_constant",
        dm_common_count=60
    )
    # degenerate_constant 是有效估计，但 n_eff=1 < 50
    assert result is False


def test_n_eff_le_n():
    """测试 n_eff <= n 的数学保证"""
    np.random.seed(42)
    for _ in range(10):
        x = np.random.randn(1000)
        n_eff, status = measured_n_eff(x)
        if status == "ok":
            assert n_eff <= len(x)


def test_parameter_sharing():
    """spec §8.3: 断言 h/q 三处同源，但**统计量各自独立**。

    审计 D8 修正: 原为空函数体（...），无任何断言。
    spec 关键区分（v7 第 5 轮审核）: 「参数同源」≠「统计量定义相同」。
    """
    import inspect
    from cascade import evaluation_metrics as em
    from cascade import statistical_tests as st

    # 1) 参数同源：q 必须是单一常量来源（spec W1.2 钦定 h-1 = 11）
    assert st.HAC_MAX_LAG_Q == 11, "q 必须钦定为 11（h = HORIZON//STEP = 12）"

    # 2) DM 侧使用 Bartlett 核（与 n_eff 实测共用同一估计量）
    dm_src = inspect.getsource(st.compute_hac_se)
    assert "bartlett" in dm_src.lower(), "DM 标准误须用 Bartlett 核"

    # 3) 「参数同源 ≠ 统计量定义相同」：VIF ≠ HAC 长程方差
    vif = st.compute_planning_vif(horizon=24, step=2)
    assert abs(vif - 8.0278) < 1e-3, "名义 VIF 应为 8.0278"
    # VIF 是名义方差膨胀因子（线性衰减假设的**平方**权重），
    # 与标准 Bartlett HAC 核（**线性**权重 1 - l/(L+1)）不是同一个量。
    # 禁止声称「规划 VIF = DM 长程方差」。
    assert vif != st.HAC_MAX_LAG_Q

    # 4) 三套公式各有独立入口（ESS / DM 标准误 / 功效规划）
    assert hasattr(em, "measured_n_eff"), "缺 ESS 实测入口"
    assert hasattr(st, "compute_hac_se"), "缺 DM 标准误入口"
    assert hasattr(st, "compute_planning_vif"), "缺功效规划入口"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
