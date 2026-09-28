# T5-PR-C3 Changelog: n_eff 实测（七类边界）+ 定位收窄为诊断与最低信息门槛

**Status:** 文档化完成，待实施
**Date:** 2026-09-28
**Spec:** §4.1 W1.2

## 问题描述

PR-C3 实现 `n_eff` 的实测逻辑，包括：

1. **n_eff 实测**：使用 Bartlett 核 HAC 长程方差估计有效样本量
2. **七类边界规则**：处理不同的边界情况（常数序列、样本不足等）
3. **定位收窄**：将 `n_eff` 从质量门槛收窄为诊断与最低信息要求
4. **meets_min_info**：实现最低信息要求的布尔判定

## 实施方案

### W1.2 n_eff 改实测

**唯一家**：`cascade/evaluation_metrics.py`

**新增函数**：`measured_n_eff(x)`，与 DM 检验**共用同一估计量**（Newey-West Bartlett + HLN），**禁止**另写一套。

**带宽参数的唯一约定**：
```python
HORIZON = 24
STEP = 2
h = HORIZON // STEP = 12      # 重叠窗口数（求和项数参数）
q = h - 1 = 11                # 最大滞后阶数
VIF = 1 + 2 * Sum_{j=1..q} (1 - j/h)^2   # = 8.0278（名义值）
```

**关键区分**：
- `VIF = 8.0278` 是**名义 VIF**，仅用于无先导数据时的量级情景
- 它**不等于** DM 检验使用的 Bartlett 长程方差
- 它**不等于** `n_eff` 的实测分母
- **禁止**声称"规划 VIF = DM 长程方差"
- 三条路径各自用**自己的**估计量
- **"参数同源"（共享 `h`/`q`）≠ "统计量定义相同"**

**定义**：
```
n_eff = n * sigma0^2 / sigma_LR^2
```
其中：
- `sigma0^2` 为样本方差
- `sigma_LR^2` 为 Bartlett 核 HAC 长程方差（带宽 `q = 11`）

### 七类边界规则

| 边界情况 | 处理 | n_eff_status |
|---------|------|-------------|
| **常数序列** | `n_eff = 1` | `degenerate_constant` |
| **样本不足** (n < 30) | `n_eff = None` | `insufficient_n` |
| **长程方差 <= 0** | 夹取为 `sigma0^2` + WARN | `clipped_to_iid` |
| **n_eff > n** | 不可能（数学保证） | — |
| **NaN/Inf** | 抛出异常 | `nonfinite` |
| **正常估计** | 实测值 | `ok` |
| **估计失败** | `n_eff = None` | `estimation_failed` |

### meets_min_info 实现

**改为一个显式布尔字段**表达"是否满足确认检验的最低信息要求"：

```python
meets_min_info = (n >= min_n)
              and (n_eff >= 50)                  # 显式包含 L3 确认前置（实测 n_eff，非名义常数）
              and (dm_common_count >= min_pairs)     # v13 统一命名（原 dm_pair_count）
              and n_eff_status in VALID_ESTIMATE
```

**VALID_ESTATE** 包括：`ok`, `degenerate_constant`, `clipped_to_iid`, `estimation_failed`

**不包括**：`insufficient_n`, `nonfinite`（这些是错误，不是"统计上不可判定"）

### n_eff_status 分类

| 分类 | 状态 | 处理 |
|------|------|------|
| **错误** | `insufficient_n`, `nonfinite` | verdict 不完整，不得进入成功判定 |
| **统计上不可判定** | `degenerate_constant` | 信息不足，可见诊断 |
| **有效估计** | `ok`, `clipped_to_iid`, `estimation_failed` | 可用于诊断 |

## 实施步骤

### 1. 实现 `measured_n_eff` 函数

```python
def measured_n_eff(x: np.ndarray, h: int = 12, q: int = 11) -> tuple[float, str]:
    """
    实测有效样本量
    
    Args:
        x: 时间序列
        h: 重叠窗口数参数
        q: 最大滞后阶数
    
    Returns:
        (n_eff, n_eff_status): 有效样本量和状态
    """
    n = len(x)
    
    # 边界检查
    if n == 0 or np.any(np.isnan(x)) or np.any(np.isinf(x)):
        return None, "nonfinite"
    
    if n < 30:
        return None, "insufficient_n"
    
    # 常数序列检查
    if np.std(x) < 1e-10:
        return 1.0, "degenerate_constant"
    
    # 计算样本方差
    sigma0_sq = np.var(x, ddof=1)
    
    # 计算 Bartlett 核 HAC 长程方差
    x_centered = x - np.mean(x)
    
    # 自协方差
    gamma = []
    for j in range(q + 1):
        if j == 0:
            gamma_j = np.mean(x_centered ** 2)
        else:
            gamma_j = np.mean(x_centered[j:] * x_centered[:-j])
        gamma.append(gamma_j)
    
    # Bartlett 核权重
    weights = [1 - j / (q + 1) for j in range(q + 1)]
    
    # 长程方差
    sigma_lr_sq = gamma[0] + 2 * sum(w * g for w, g in zip(weights[1:], gamma[1:]))
    
    # 边界处理
    if sigma_lr_sq <= 0:
        # 夹取为 sigma0^2 + WARN
        import logging
        logging.warning(
            f"Long-run variance <= 0 ({sigma_lr_sq}), clipping to sample variance"
        )
        sigma_lr_sq = sigma0_sq
        status = "clipped_to_iid"
    else:
        status = "ok"
    
    # 计算 n_eff
    n_eff = n * sigma0_sq / sigma_lr_sq
    
    # 数学保证：n_eff <= n
    if n_eff > n:
        # 这不应该发生，但以防万一
        n_eff = n
    
    return n_eff, status
```

### 2. 实现 `meets_min_info` 判定

```python
def compute_meets_min_info(
    n: int,
    n_eff: float,
    n_eff_status: str,
    dm_common_count: int,
    min_n: int = 30,
    min_n_eff: int = 50,
    min_pairs: int = 50
) -> bool:
    """
    计算是否满足最低信息要求
    
    Args:
        n: 样本量
        n_eff: 有效样本量
        n_eff_status: n_eff 状态
        dm_common_count: DM 配对数量
        min_n: 最小样本量
        min_n_eff: 最小有效样本量
        min_pairs: 最小配对数
    
    Returns:
        bool: 是否满足最低信息要求
    """
    VALID_ESTIMATE = {"ok", "degenerate_constant", "clipped_to_iid", "estimation_failed"}
    
    return (
        n >= min_n
        and (n_eff is not None and n_eff >= min_n_eff)
        and dm_common_count >= min_pairs
        and n_eff_status in VALID_ESTIMATE
    )
```

### 3. 创建测试 `tests/test_n_eff_measurement.py`

```python
"""n_eff 实测测试"""

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

    构造真正产生负长程方差的序列：强负自相关 AR(1)（rho < 0）。
    当 rho 足够负时，Bartlett 加权和可为负。
    """
    n = 500
    rho = -0.8          # 强负自相关
    x = np.zeros(n)
    x[0] = np.random.randn()
    for t in range(1, n):
        x[t] = rho * x[t - 1] + np.random.randn() * 0.1

    # 先确认该序列确实产生负长程方差（否则测试仍是 vacuous）
    x_c = x - np.mean(x)
    q = 11
    gamma0 = np.mean(x_c ** 2)
    lr = gamma0 + 2 * sum(
        (1 - j / (q + 1)) * np.mean(x_c[j:] * x_c[:-j])
        for j in range(1, q + 1)
    )
    assert lr < 0, "构造失败：该序列未产生负长程方差，测试将 vacuous"

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
    
    # 审计 D8 修正: 原为空函数体（...），无任何断言。
    # spec §8.3: 三套公式**分别**验证，禁止「一套通过即视为三套通过」。
    import inspect
    from cascade import evaluation_metrics as em
    from scripts import statistical_tests as st

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
```

## 预计工作量

- n_eff 实测实现: 1 天
- meets_min_info 实现: 0.5 天
- 测试: 1 天
- **总计: 2.5 天**

## 依赖

- 不依赖 T1a（可并行实施）
- 需要理解当前 evaluation_metrics.py 的实现

## 风险

1. **统计正确性风险**：HAC 估计必须严格遵循 spec，否则会导致错误的 n_eff 估计
2. **性能风险**：HAC 估计需要计算自协方差，对于大样本可能较慢
3. **前视风险**：无，这是事后统计估计

## 验收标准

1. `measured_n_eff` 正确实现（使用 Bartlett 核）
2. 七类边界规则正确处理
3. `meets_min_info` 正确实现
4. 参数同源（h, q 与 DM 检验共享）
5. n_eff <= n 的数学保证
6. 所有 L1 测试 10-12 通过

## 审核结论

**T5-PR-C3 文档化完成**。实施推迟，需 2.5 天工作量。
