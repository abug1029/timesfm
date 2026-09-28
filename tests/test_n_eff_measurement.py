"""n_eff 实测测试 — PR-C3 实施验收"""

import pytest
import numpy as np
from cascade.evaluation_metrics import measured_n_eff, compute_meets_min_info


def test_measured_n_eff_iid():
    """IID 序列的 n_eff 应等于 n。

    状态可能是 "ok" 也可能是 "clamped_to_n"：IID 序列的真实长程方差就是
    σ0²，但**样本** Bartlett 估计会因抽样噪声略低于 σ0²，于是 n_eff 略超 n
    而触发夹取。spec §4.1 边界表把这一情形单列为 `clamped_to_n`，
    报 "ok" 反而是把「夹取触发过」藏起来。
    """
    np.random.seed(42)
    x = np.random.randn(1000)
    n_eff, status = measured_n_eff(x)

    assert status in ("ok", "clamped_to_n")
    assert n_eff == 1000


def test_measured_n_eff_iid_is_not_rejected_by_min_info():
    """IID 序列不得被信息门误杀 —— clamped_to_n 属有效估计。"""
    np.random.seed(42)
    x = np.random.randn(1000)
    n_eff, status = measured_n_eff(x)
    assert compute_meets_min_info(n=1000, n_eff=n_eff, n_eff_status=status,
                                  dm_common_count=1000) is True


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
        # 分母统一用 n（与 compute_hac_se 的 Newey-West 约定一致）。
        # 曾用 np.mean(x_c[j:] * x_c[:-j]) 即 n-j 约定，与生产不同源。
        gamma0 = np.sum(x_c ** 2) / len(x_c)
        lr = gamma0 + 2 * sum(
            (1 - j / (q + 1)) * np.sum(x_c[j:] * x_c[:len(x_c) - j]) / len(x_c)
            for j in range(1, q + 1)
        )
        if lr < 0:
            found = True
            break

    if not found:
        pytest.skip("无法构造出负长程方差的序列（Bartlett 核正半定性保护）")

    n_eff, status = measured_n_eff(x)
    # 状态名须与 spec §4.1 边界表一致。旧名 clipped_to_iid 已废弃；
    # 此处曾被 pytest.skip 恒定掩盖，改名回归因此不可见。
    assert status == "hac_nonpositive_clamped", (
        "负长程方差必须走夹取分支，实际 status=%r" % status)
    assert n_eff is not None
    assert n_eff <= n


def test_negative_variance_branch_status_name_is_not_stale():
    """防回归：夹取分支的状态名不得回退为已废弃的 clipped_to_iid。

    原 `test_measured_n_eff_negative_variance` 因负长程方差在 Bartlett 核
    正半定性下几乎不可达，`pytest.skip` 恒定触发，其中的断言从不执行 ——
    状态名改名后该断言若运行必红，却被 skip 掩盖。此测试不依赖构造成功，
    直接断言源码里不再出现旧名。
    """
    import inspect
    from cascade import evaluation_metrics as em

    src = inspect.getsource(em)
    assert "clipped_to_iid" not in src, "旧状态名 clipped_to_iid 残留"


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


# ── spec §8.3 黄金用例：已知自相关序列手算长程方差，与代码结果比较 ──────
#
# 手算依据：AR(1) x_t = rho·x_{t-1} + e_t, e_t ~ N(0,1)
#   平稳方差  sigma0^2 = 1 / (1 - rho^2)
#   自协方差  gamma_j  = sigma0^2 · rho^j
#   Bartlett  LR       = sigma0^2 · (1 + 2·Σ_{j=1..q} (1 - j/(q+1))·rho^j)
# rho=0.5, q=11 → LR = 1.3333 × 2.666748 = 3.555664
#                → n_eff = n·sigma0^2/LR = 1000 / 2.666748 = 374.99
def _analytic_bartlett_lr(rho, q):
    """AR(1) 的 Bartlett HAC 长程方差解析值（单位创新方差）。"""
    sigma0_sq = 1.0 / (1.0 - rho ** 2)
    return sigma0_sq * (1.0 + 2.0 * sum(
        (1.0 - j / (q + 1)) * rho ** j for j in range(1, q + 1)))


def test_hac_se_matches_hand_computed_golden_value():
    """黄金用例：估计量在大样本上应收敛到手算解析值（spec §8.3）。"""
    from cascade.statistical_tests import HAC_MAX_LAG_Q, compute_hac_se

    rho = 0.5
    analytic = _analytic_bartlett_lr(rho, HAC_MAX_LAG_Q)
    assert analytic == pytest.approx(3.555664, abs=1e-5)

    rng = np.random.default_rng(20260928)
    vals = []
    for _ in range(60):
        e = rng.standard_normal(8000)
        x = np.empty(8000)
        x[0] = e[0]
        for t in range(1, 8000):
            x[t] = rho * x[t - 1] + e[t]
        vals.append(compute_hac_se(x, q=HAC_MAX_LAG_Q))

    mc_mean = float(np.mean(vals))
    mc_se = float(np.std(vals)) / np.sqrt(len(vals))
    assert mc_mean == pytest.approx(analytic, abs=5 * mc_se), (
        "MC 均值 %.6f ± %.6f 偏离手算值 %.6f" % (mc_mean, mc_se, analytic))


def test_n_eff_golden_value_for_ar1():
    """黄金用例：AR(1) rho=0.5 的 n_eff 应约为 n / 2.666748。

    单次抽样有 ~3% 噪声（q+1 个自协方差项的估计误差），故取多次抽样均值
    与解析值比较 —— 检验的是**估计量的期望**，这才是黄金用例要对的东西。
    """
    n, rho, reps = 8000, 0.5, 40
    expected = n / (1.0 + 2.0 * sum(
        (1.0 - j / 12) * rho ** j for j in range(1, 12)))

    rng = np.random.default_rng(7)
    vals = []
    for _ in range(reps):
        e = rng.standard_normal(n)
        x = np.empty(n)
        x[0] = e[0]
        for t in range(1, n):
            x[t] = rho * x[t - 1] + e[t]
        n_eff, status = measured_n_eff(x)
        assert status == "ok"
        vals.append(n_eff)

    mc_mean = float(np.mean(vals))
    mc_se = float(np.std(vals)) / np.sqrt(reps)
    assert mc_mean == pytest.approx(expected, abs=4 * mc_se), (
        "MC 均值 %.1f ± %.1f 偏离解析值 %.1f" % (mc_mean, mc_se, expected))


def test_dm_and_n_eff_share_one_hac_estimator():
    """spec §4.1 W1.2：DM 与 n_eff 共用同一 HAC 实现。

    两处曾各写一套自协方差（分母分别用 n-j 和 T），产出不同长程方差。
    本测试从外部锁死该契约：DM 的 p 值必须等于「用 compute_hac_se 算出的
    长程方差 / T」所推出的 DM 统计量。
    """
    from cascade.statistical_tests import compute_hac_se, diebold_mariano_p
    from scipy.stats import t as student_t

    rng = np.random.default_rng(11)
    T = 200
    b = rng.integers(0, 2, size=T).astype(float)
    d = rng.binomial(1, 0.6, size=T) - b   # 配对损失差
    v = b + d                              # 还原 variant，使 d = v - b

    p = diebold_mariano_p(v.tolist(), b.tolist(), horizon=24, step=2)

    # 独立复算：复用 compute_hac_se → V → DM 统计量 → HLN → t 分布
    q = 11
    V = compute_hac_se(d, q=q) / T
    d_bar = float(np.mean(d))
    h = 24 // 2
    k_hln = np.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    dm_adj = (d_bar / np.sqrt(V)) * k_hln
    expected = float(np.clip(student_t.sf(dm_adj, df=T - 1), 0.0, 1.0))

    assert p == pytest.approx(expected, rel=1e-12)


def test_hac_max_lag_matches_backtest_config():
    """带宽常数不得与 backtest_config 漂移（spec §4.1 W1.2）。

    `HAC_MAX_LAG_Q = 11` 是写死的，而 spec 的定义是 q = h - 1
    = HORIZON//STEP - 1。若有人改了 HORIZON 或 STEP 而忘了改这里，
    n_eff 与 DM 会静默用错带宽。此处把二者钉死 —— 比让 cascade
    反向依赖 config 更安全（statistical_tests 里 backtest_config
    是刻意延迟导入的）。
    """
    from cascade.statistical_tests import HAC_MAX_LAG_Q
    from config import backtest_config

    expected = backtest_config.HORIZON // backtest_config.STEP - 1
    assert HAC_MAX_LAG_Q == expected, (
        "HAC_MAX_LAG_Q=%d 与 HORIZON//STEP-1=%d 不一致"
        % (HAC_MAX_LAG_Q, expected))


def test_measured_n_eff_q_derives_from_h():
    """q 缺省时必须是 h - 1（spec W1.2 唯一带宽约定）。"""
    np.random.seed(3)
    x = np.random.randn(200)
    assert measured_n_eff(x, h=12) == measured_n_eff(x, h=12, q=11)


def test_measured_n_eff_status_names_match_spec():
    """状态名必须与 spec §4.1 边界表逐字一致。

    曾用 `clipped_to_iid`，而 spec 钦定 `hac_nonpositive_clamped`；
    且 spec 把「n_eff > n 夹取」单列为 `clamped_to_n`，曾与 `ok` 混为一谈。
    """
    from cascade.evaluation_metrics import compute_meets_min_info

    valid = {"ok", "clamped_to_n", "hac_nonpositive_clamped", "degenerate_constant"}
    # 逐项构造：只有 VALID_ESTIMATE 内的状态能通过信息门
    base = dict(n=1000, n_eff=500.0, dm_common_count=500)
    for st in valid:
        assert compute_meets_min_info(n_eff_status=st, **base) is True, st
    for st in ("insufficient_n", "nonfinite", "estimation_failed", "bogus"):
        assert compute_meets_min_info(n_eff_status=st, **base) is False, st


def test_n_eff_actually_uses_shared_hac_estimator():
    """spec §4.1 W1.2 的原文是「n_eff 与 DM 共用同一估计量」。

    已有测试只锁了 DM 一侧（DM 必须委托 compute_hac_se）。
    本测试锁 n_eff 一侧：从外部用 compute_hac_se 复算
    n_eff = n * sigma0^2 / sigma_LR^2，须与 measured_n_eff 一致。
    若有人给 measured_n_eff 另写一套自协方差，此处会分叉。
    """
    from cascade.statistical_tests import HAC_MAX_LAG_Q, compute_hac_se

    rng = np.random.default_rng(5)
    for n in (200, 500):
        x = rng.standard_normal(n)
        for t in range(1, n):
            x[t] = 0.5 * x[t - 1] + rng.standard_normal()

        n_eff, status = measured_n_eff(x)
        assert status == "ok", status

        sigma0_sq = np.var(x)                      # ddof=0，与 gamma_0 同约定
        sigma_lr_sq = compute_hac_se(x, q=HAC_MAX_LAG_Q)
        assert n_eff == pytest.approx(n * sigma0_sq / sigma_lr_sq, rel=1e-12)

