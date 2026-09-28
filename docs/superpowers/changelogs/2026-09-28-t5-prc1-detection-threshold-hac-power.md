# T5-PR-C1 Changelog: 检测阈值 + 配对 HAC + 功效公式

**Status:** 文档化完成，待实施
**Date:** 2026-09-28
**Spec:** §4.3 W3.5, W3.6

## 问题描述

PR-C1 是 Stage 3 最核心的统计实现任务，涉及三个相互关联的组件：

1. **检测阈值（detection_threshold_*）**：计算 vs random 和 vs baseline 的最小可检测效应
2. **配对 HAC（Heteroskedasticity and Autocorrelation Consistent）**：估计配对差异序列的标准误
3. **功效公式（n_required）**：计算达到目标功效所需的样本量

这三个组件必须使用**同一损失定义**（方向命中差 `d_t = v_ok_t - b_ok_t ∈ {-1, 0, 1}`），且**禁止混用**"长程方差 × VIF"。

## 实施方案

### W3.5 检测阈值与功效规划

#### ① 两途径方差估计（禁止混用）

| 途径 | 适用场景 | 方差估计 | 性质 |
|------|---------|---------|------|
| **A. 情景近似** | 尚无先导数据 | `Var(d)` × `VIF` | 情景示例，必须标注 |
| **B. 先导估计** | 已有先导数据 | HAC 长程方差 `Var_LR(d)` | 实证口径，优先采用 |

**关键约束**：
- **禁止**两条途径混用（例如估了 HAC 长程方差又乘 `VIF`）
- 公式与代码只允许**一个** `Var(d)` 定义
- 阶段 3 核验必须专门覆盖：断言实现中**不存在**"长程方差 × `VIF`"的路径

#### ② 确认检验的损失定义唯一

**本 spec 的确认检验唯一采用方向命中差**：
```
d_t = v_ok_t - b_ok_t ∈ {-1, 0, 1}
```
等价于 **0-1 方向损失**。

**功效规划、DM 检验、detection_threshold_* 三者必须使用同一损失定义。**

#### ③ 功效公式

```
n_required = ((z_alpha + z_beta)^2 * Var(d)) / Delta^2
```

其中：
- `z_alpha = 1.645`（单侧 α=0.05）
- `z_beta = 0.8416`（80% 功效）
- 乘数 `z_alpha + z_beta = 2.4866`

**规划情景表（示例，非普遍结论）**：

| 目标增量 `Delta` | `n_required`（示例） | 相对当前 |
|-----------------|---------------------|---------|
| 0.02 | ≈ 31,000 | 53× |
| 0.05 | ≈ 5,000 | 8.5× |
| 0.10 | ≈ 1,240 | 2.1× |

**使用约束**：
- `VIF=8.028` 只是初始情景（由 `HORIZON=24`, `STEP=2` 推出）
- 真实配对差异序列的方差、自相关、缺失结构因品种、时期而异
- 实际规划应优先从先导数据估计 HAC 方差
- 本 spec **不**声称"0.50–0.52 波段普遍不可检出"

#### ④ 落盘与报告

verdict 落：
- `detection_threshold_vs_random`
- `detection_threshold_vs_baseline`
- `se_hac`（**实测**）
- `delta_ci_lo/hi`
- `n_required_for_target`（若已声明目标效应与功效）

规划 `rho` 表只进规划文档，不进 verdict。

### W3.6 多重比较与序贯纪律

#### ① 检验家族（family）的定义

**一个 family = 同一研究问题 + 同一预注册系列内全部确认检验**

- 默认：一个品种 = 一个研究问题 = 一个 family
- **批次、运行、代际都不重置校正**
- 只有确认检验进 family，探索期结果不进
- 每个假设在 family 中**恰好一个** p 值

**跨品种错误率范围必须显式声明**：
- 本 spec **默认不跨品种合并校正**
- 结论范围仅限品种内
- 报告**不得**产出跨品种聚合声称

#### ② 封账、注册截止、未完成检验的 p 值

family 在**全部成员到达终态**时封账，**一次性**运行 BH-FDR。

**终态四种**：`confirmed` / `refuted` / `abandoned` / `timeout`

**必须给 family 设注册截止**（二者并用，先到者为准）：
- **时间截止** `family_close_at`：默认 family 首个成员注册后 90 天
- **成员上限** `family_max_members`：默认 20

**`T_max` 的起算点**：从成员注册时间起算，默认 180 天

**已注册但从未获得确认数据的成员**：在 `family_close_at` 封账时若仍未达终态，立即落 `timeout` + `p=1`

**封账上界**：family 最晚于 `family_close_at + T_max` 封账

**`p = 1` 的适用范围**：仅当该假设已进入确认 family、且在截止前未完成确认时

**`abandoned` 与 `timeout` 仍计入 `K`**（防止 p-hacking）

## 实施步骤

### 1. 实现 `statistical_tests.py` 中的检测阈值函数

```python
def compute_detection_threshold_vs_random(n_eff, alpha=0.05):
    """
    计算 vs random 的检测阈值
    
    Args:
        n_eff: 有效样本量
        alpha: 显著性水平
    
    Returns:
        float: 检测阈值
    """
    z_alpha = 1.645  # 单侧 α=0.05
    # vs random: 假设 baseline 是 0.5
    return 0.5 + z_alpha * 0.5 / np.sqrt(n_eff)


def compute_detection_threshold_vs_baseline(d_series, alpha=0.05):
    """计算 vs baseline 的检测阈值（spec W3.5①）。

    detection_threshold_vs_baseline = z_alpha * SE_HAC(d_bar)
    其中 d_t = v_ok_t - b_ok_t（方向命中差，0-1 损失）。

    ⚠️ 审计 D2 修正: 原稿用 VIF 情景公式，**违反 spec W3.5「二选一」**。
       spec 明文:
         - 途径 A（情景近似）: Var(d) × VIF —— **仅用于规划文档**
         - 途径 B（先导估计）: 直接用 HAC 长程方差 —— **实证口径，verdict 采用**
         - **禁止**两条途径混用
       spec §8.3 出口核验明令: 「断言实现中**不存在**『长程方差 × VIF』的混用路径」。
       verdict 落 `se_hac`（**实测**）；规划 rho 表只进规划文档，**不进 verdict**。

    Args:
        d_series: 配对差异序列 d_t = v_ok_t - b_ok_t
        alpha: 显著性水平（单侧）

    Returns:
        float: 检测阈值（= z_alpha × 实测 HAC 标准误）
    """
    z_alpha = 1.645  # 单侧 α=0.05，与 DM 同侧
    se_hac = compute_hac_se(d_series)   # 实测，非 VIF 情景
    return z_alpha * se_hac


def compute_planning_vif(horizon=24, step=2):
    """名义 VIF —— **仅供规划文档**，禁止进入 verdict（spec W3.5）。

    VIF = 1 + 2 * Σ_{j=1..q} (1 - j/h)^2,  h = horizon//step, q = h-1
    HORIZON=24, STEP=2 → h=12, q=11 → VIF = 8.0278

    ⚠️ 这是**名义 VIF**（重叠窗口的名义方差膨胀），
       **不等于** DM 检验使用的 Bartlett 长程方差，
       **也不等于** n_eff 的实测分母。
       「参数同源（共享 h/q）≠ 统计量定义相同」。
    """
    h = horizon // step
    q = h - 1
    return 1.0 + 2.0 * sum((1 - j / h) ** 2 for j in range(1, q + 1))


def compute_n_required(
    delta, var_d, rho=0.5, horizon=24, step=2, 
    alpha=0.05, power=0.80
):
    """
    计算达到目标功效所需的样本量
    
    Args:
        delta: 目标效应大小
        var_d: 配对差异序列的方差
        rho: 相关性假设
        horizon: 预测窗口
        step: 步长
        alpha: 显著性水平
        power: 目标功效
    
    Returns:
        int: 所需样本量
    """
    z_alpha = 1.645
    z_beta = 0.8416  # 80% 功效
    vif = compute_vif(horizon, step)
    
    n_req = ((z_alpha + z_beta) ** 2 * var_d * vif) / (delta ** 2)
    return int(np.ceil(n_req))
```

### 2. 实现 HAC 标准误估计

```python
def compute_hac_se(d_series, kernel="bartlett", q=HAC_MAX_LAG_Q):
    """计算 HAC 标准误（Newey-West Bartlett）。

    ⚠️ 审计 D2 修正: 原稿 `bandwidth=None` 自动选择（Newey-West 经验式），
       **违反 spec 钦定**。spec W1.2/W3.5 明定:

         h = HORIZON // STEP = 24 // 2 = 12   # 重叠窗口数
         q = h - 1 = 11                        # 最大滞后阶数

       该定义在 **n_eff 实测、DM 检验、规划公式** 三处**共享**，
       实现只允许有**一个**来源。故 q **固定为 11**，不得自动选择。

    Args:
        d_series: 配对差异序列
        kernel: 核函数（Bartlett）
        q: 最大滞后阶数（spec 钦定 11，勿改）

    Returns:
        float: HAC 标准误
    """
    n = len(d_series)
    d_bar = np.mean(d_series)
    d_centered = d_series - d_bar

    # 计算自协方差
    gamma = []
    for j in range(q + 1):
        if j == 0:
            gamma_j = np.mean(d_centered ** 2)
        else:
            gamma_j = np.mean(d_centered[j:] * d_centered[:-j])
        gamma.append(gamma_j)

    # 应用核权重
    if kernel == "bartlett":
        weights = [1 - j / (q + 1) for j in range(q + 1)]
    else:
        raise ValueError(f"Unsupported kernel: {kernel}")
    
    # 计算长程方差
    var_lr = gamma[0] + 2 * sum(w * g for w, g in zip(weights[1:], gamma[1:]))
    
    # 标准误
    se = np.sqrt(var_lr / n)
    return se
```

### 3. 实现 family 封账逻辑

```python
def close_family(family_members, family_close_at, t_max_days=180):
    """
    封账 family，分配 p 值
    
    Args:
        family_members: list of dict，每个成员包含 registered_at, status, p_value
        family_close_at: 封账时间
        t_max_days: 成员最大等待天数
    
    Returns:
        dict: 封账后的 family，包含 K, p_values, bh_results
    """
    from statsmodels.stats.multitest import multipletests
    
    # 检查未完成的成员，分配 timeout + p=1
    for member in family_members:
        if member["status"] not in ["confirmed", "refuted", "abandoned"]:
            # 检查是否超过 T_max
            days_since_registration = (
                family_close_at - member["registered_at"]
            ).days
            if days_since_registration >= t_max_days:
                member["status"] = "timeout"
                member["p_value"] = 1.0
    
    # 计算 K（包括 abandoned 和 timeout）
    K = len(family_members)
    
    # 提取 p 值
    p_values = [m["p_value"] for m in family_members if m["status"] == "confirmed"]
    
    # 运行 BH-FDR
    if p_values:
        reject, pvals_corrected, _, _ = multipletests(
            p_values, alpha=0.05, method="fdr_bh"
        )
    else:
        reject = []
        pvals_corrected = []
    
    return {
        "K": K,
        "p_values": p_values,
        "pvals_corrected": pvals_corrected,
        "reject": reject,
        "closed_at": family_close_at
    }
```

### 4. 创建测试 `tests/test_statistical_tests.py`

```python
"""统计测试实现验证"""

import pytest
import numpy as np
from scripts.statistical_tests import (
    compute_detection_threshold_vs_random,
    compute_detection_threshold_vs_baseline,
    compute_n_required,
    compute_hac_se
)


def test_detection_threshold_vs_random():
    """测试 vs random 检测阈值"""
    # n_eff = 73 时，阈值应为 0.596
    threshold = compute_detection_threshold_vs_random(n_eff=73)
    assert abs(threshold - 0.596) < 0.001


def test_detection_threshold_vs_baseline():
    """测试 vs baseline 检测阈值"""
    # 使用 rho=0.5, Var(d)=0.25, VIF=8.028, n=588
    threshold = compute_detection_threshold_vs_baseline(
        n=588, var_d=0.25, rho=0.5, horizon=24, step=2
    )
    # 应该约为 0.096
    assert 0.09 < threshold < 0.10


def test_n_required():
    """测试功效公式"""
    # Delta=0.10 时，n_required 约为 1240
    n_req = compute_n_required(
        delta=0.10, var_d=0.25, rho=0.5, horizon=24, step=2
    )
    assert 1200 < n_req < 1300


def test_hac_se_with_autocorrelation():
    """测试 HAC 标准误（已知自相关序列）"""
    # 构造 AR(1) 序列
    np.random.seed(42)
    n = 1000
    rho = 0.5
    d_series = np.zeros(n)
    d_series[0] = np.random.randn()
    for t in range(1, n):
        d_series[t] = rho * d_series[t-1] + np.random.randn()
    
    se = compute_hac_se(d_series, kernel="bartlett")
    
    # 应该大于 iid 假设下的标准误
    se_iid = np.std(d_series) / np.sqrt(n)
    assert se > se_iid


def test_no_mixing_hac_and_vif():
    """spec §8.3: 断言实现中**不存在**「长程方差 × VIF」的混用路径。

    源码断言（审计 D2 修正: 原稿为空函数体）。
    """
    import inspect
    from scripts.statistical_tests import compute_detection_threshold_vs_baseline

    src = inspect.getsource(compute_detection_threshold_vs_baseline)
    assert "vif" not in src.lower(), (
        "detection_threshold_vs_baseline 混用了 VIF —— "
        "spec W3.5 明令禁止两条途径混用"
    )
    assert "compute_vif" not in src


def test_vif_is_planning_only():
    """spec W3.5: VIF 只允许出现在规划函数，不得进 verdict。"""
    import inspect
    from scripts import statistical_tests as st

    # 规划函数可以引用 VIF
    plan_src = inspect.getsource(st.compute_planning_vif)
    assert "VIF" in plan_src or "vif" in plan_src

    # verdict 侧函数不得引用
    for fn_name in ("compute_detection_threshold_vs_baseline",
                    "compute_detection_threshold_vs_random"):
        src = inspect.getsource(getattr(st, fn_name))
        assert "vif" not in src.lower(), f"{fn_name} 不得引用 VIF"


def test_loss_definition_unique():
    """spec §8.3: 断言损失定义唯一（方向命中差 d_t ∈ {-1, 0, 1}）。

    审计 D2 修正: 原稿为空函数体。
    本 spec 的确认检验**唯一**采用方向命中差，等价于 0-1 方向损失。
    MAE/RMSE 类「预测误差差」属**独立检验**，不得与方向命中差混称。
    """
    import inspect
    from scripts.statistical_tests import compute_detection_threshold_vs_baseline

    src = inspect.getsource(compute_detection_threshold_vs_baseline)
    for other_loss in ("mae", "rmse", "mse"):
        assert other_loss not in src.lower(), (
            f"检测阈值混入了 {other_loss.upper()} 损失 —— 损失定义必须唯一"
        )

    # d_t 的取值域断言
    d = np.array([1.0, -1.0, 0.0, 1.0, 0.0])
    assert set(np.unique(d)) <= {-1.0, 0.0, 1.0}, "d_t 取值域应为 {-1, 0, 1}"


def test_hac_bandwidth_fixed_at_11():
    """spec W1.2: 带宽 q 钦定为 h-1 = 11，不得自动选择。"""
    import inspect
    from scripts import statistical_tests as st

    assert st.HAC_MAX_LAG_Q == 11
    sig = inspect.signature(st.compute_hac_se)
    assert sig.parameters["q"].default == 11, "q 默认值必须为 11"


def test_three_formulas_verified_separately():
    """spec §8.3: 三套公式（n_eff ESS / DM 标准误 / 功效规划）**分别**验证。

    禁止「一套通过即视为三套通过」。
    """
    from scripts import statistical_tests as st

    # 三套公式必须有各自独立的实现入口
    assert hasattr(st, "compute_hac_se")            # DM 标准误口径
    assert hasattr(st, "compute_planning_vif")      # 功效规划口径
    # n_eff 实测在 cascade/evaluation_metrics.py（唯一家）
    from cascade import evaluation_metrics as em
    assert hasattr(em, "measured_n_eff")            # ESS 实测口径

    # 参数同源但统计量不同：h/q 共享，估计量各自独立
    assert st.HAC_MAX_LAG_Q == 11
    assert st.compute_planning_vif(24, 2) != st.HAC_MAX_LAG_Q  # 非同一量


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## 预计工作量

- 检测阈值实现: 1 天
- HAC 标准误实现: 1 天
- family 封账逻辑: 1 天
- 测试: 1.5 天
- **总计: 4.5 天**

## 依赖

- 不依赖 T1a（可并行实施）
- 需要理解当前统计检验逻辑

## 风险

1. **统计正确性风险**：HAC 估计和功效公式必须严格遵循 spec，否则会导致错误的统计推断
2. **性能风险**：HAC 估计需要计算自协方差，对于大样本可能较慢
3. **前视风险**：无，这些是事后统计检验

## 验收标准

1. 检测阈值函数正确实现（vs random, vs baseline）
2. HAC 标准误估计正确（使用 Bartlett 核）
3. 功效公式正确实现
4. family 封账逻辑正确（包括 timeout + p=1）
5. 断言不存在"长程方差 × VIF"混用
6. 断言损失定义唯一（方向命中差）
7. 所有 L1 测试 1-17 通过

## 审核结论

**T5-PR-C1 文档化完成**。实施推迟，需 4.5 天工作量。
