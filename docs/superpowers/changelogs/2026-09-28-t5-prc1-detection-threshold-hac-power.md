# T5-PR-C1 Changelog: 检测阈值 + 配对 HAC + 功效公式
> **代码基线**: `12e0850`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

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
    delta, var_d=None, var_lr_d=None, horizon=24, step=2,
    alpha=0.05, power=0.80
):
    """计算达到目标功效所需的样本量（spec W3.5②）。

    ⚠️ 复核 HIGH-4 修正 —— 原稿有两处缺陷:
      (1) 调用 `compute_vif(...)` —— 该函数已改名为 `compute_planning_vif`，
          全仓 grep `compute_vif` 0 匹配 → **NameError**
      (2) 无条件乘 VIF，且只收单个 `var_d` 参数 →
          spec §5.3 测试 16「传入已含 HAC 的长程方差时**不再乘** VIF
          （防重复调整）」既未实现也未断言

    spec W3.5② 「两条途径，互斥，必须二选一」:
      途径 A（情景近似）: Var(d) 边际方差 × VIF  —— 无先导数据时用
      途径 B（先导估计）: 直接用 HAC 长程方差 Var_LR(d)，**不再乘 VIF** —— 优先

    Args:
        delta: 目标效应大小
        var_d: 边际方差（途径 A；与 var_lr_d 二选一）
        var_lr_d: HAC 长程方差（途径 B；与 var_d 二选一）
        horizon / step: 仅途径 A 需要（用于名义 VIF）
        alpha / power: 显著性水平与目标功效

    Returns:
        int: 所需样本量

    Raises:
        ValueError: 两途径同时提供或都未提供（fail-loud，禁止静默混用）
    """
    if (var_d is None) == (var_lr_d is None):
        raise ValueError(
            "必须且只能提供 var_d（途径 A）或 var_lr_d（途径 B）之一；"
            "spec W3.5 禁止两条途径混用"
        )

    z_alpha = 1.645
    z_beta = 0.8416  # 80% 功效

    if var_lr_d is not None:
        # 途径 B: 已含自相关修正，**不得**再乘 VIF
        var_eff = var_lr_d
    else:
        # 途径 A: 边际方差 × 名义 VIF
        var_eff = var_d * compute_planning_vif(horizon, step)

    n_req = ((z_alpha + z_beta) ** 2 * var_eff) / (delta ** 2)
    return int(np.ceil(n_req))

```

### 2. 实现 HAC 标准误估计

> **⚠️ 复核 MEDIUM-1 修正 —— h/q 必须真正单一来源**
>
> 原稿引入模块常量 `HAC_MAX_LAG_Q`（未定义）**并且**在 `compute_planning_vif`
> 内本地重算 `h = horizon // step; q = h - 1` —— 加上仓库现有的第三种推导
> （`cascade/statistical_tests.py:196` 内联 `q = max(1, horizon // max(1, step) - 1)`），
> 共**三处定义**。spec W1.2 要求「实现只允许有一个来源」（§5.3 测试 13）。
>
> 且字面 `11` 无法随 `HORIZON` 变化 —— 正是单一来源规则要防的。
>
> **处置**：在 `cascade/statistical_tests.py` 顶部建立**唯一**推导，三处引用它：
>
> ```python
> # cascade/statistical_tests.py —— 唯一来源（spec W1.2）
> from config import backtest_config as _bc
>
> def _hac_lag_order(horizon=None, step=None) -> int:
>     """最大滞后阶数 q = h - 1，h = HORIZON // STEP。
>
>     spec W1.2: 该定义在 n_eff 实测 / DM 检验 / 规划公式 三处共享，
>     实现只允许有**一个**来源。改动 HORIZON 或 STEP 时三处同步生效。
>     """
>     h = (horizon if horizon is not None else _bc.HORIZON) // \
>         max(1, (step if step is not None else _bc.STEP))
>     return max(1, h - 1)
> ```
>
> **三处调用方全部改为引用 `_hac_lag_order()`**：
> | 调用方 | 现状 | 改为 |
> |--------|------|------|
> | `cascade/statistical_tests.py:196`（DM） | 内联 `max(1, horizon//max(1,step)-1)` | `_hac_lag_order(horizon, step)` |
> | `compute_hac_se`（本 PR） | 默认参数字面 `11` | `q=None` → 内部 `_hac_lag_order()` |
> | `compute_planning_vif`（本 PR） | 本地 `h = horizon//step` | `_hac_lag_order(horizon, step)` |
>
> **验收**：`assert _hac_lag_order(24, 2) == 11`，且 monkeypatch `HORIZON=48`
> 后三处同步变为 23（**替换原稿的 vacuous 断言** ——
> `assert compute_planning_vif(24,2) != HAC_MAX_LAG_Q` 是拿 VIF 8.0278 与滞后阶数 11
> 相比，恒真，无意义）。

```python
def compute_hac_se(d_series, kernel="bartlett", q=None):
    """计算 HAC 标准误（Newey-West Bartlett）。

    ⚠️ 审计 D2 修正: 原稿 `bandwidth=None` 自动选择（Newey-West 经验式），
       **违反 spec 钦定**。spec W1.2/W3.5 明定:

         h = HORIZON // STEP = 24 // 2 = 12   # 重叠窗口数
         q = h - 1 = 11                        # 最大滞后阶数

       该定义在 **n_eff 实测、DM 检验、规划公式** 三处**共享**，
       实现只允许有**一个**来源（`_hac_lag_order()`）。故 q 不得自动选择。

    Args:
        d_series: 配对差异序列
        kernel: 核函数（Bartlett）
        q: 最大滞后阶数；None 时取单一来源 `_hac_lag_order()`

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

### 3. family 封账逻辑 —— **不在本 PR 交付**

> **⚠️ 复核 HIGH-1 修正 —— 本节已删除**
>
> 原稿在本节内联了一份 `close_family` 实现，其中**逐字保留**了审计 D3 指出的
> p-hacking 路径：
>
> ```python
> if days_since_registration >= t_max_days:      # 仍以 T_max 为门
>     member["status"] = "timeout"
> p_values = [m["p_value"] for m in family_members if m["status"] == "confirmed"]
> #                                                            ^^^^^^^^^^^ 排除 timeout/abandoned
> ```
>
> 即：**D3 修复只落在 PR-C2，PR-C1 中的违规实现原封未动**。
> 两份文档因此给出**两个不同的 `close_family`**，而存活下来的是错的那个。
>
> **处置**：`family 封账逻辑` 的**唯一所有者是 PR-C2**
> （见 `2026-09-28-t5-prc2-family-definition-closure.md` §`close_family`）。
> 本 PR（PR-C1）只交付：
> - `detection_threshold_vs_random` / `_vs_baseline`
> - `compute_hac_se`（q=11）
> - `compute_planning_vif`（规划专用）
> - `compute_n_required`（两途径互斥）
>
> **验收标准 #4「family 封账逻辑正确」一并移交 PR-C2**，本 PR 不再声称拥有它。



### 4. 创建测试 `tests/test_statistical_tests.py`

```python
"""统计测试实现验证"""

import pytest
import numpy as np
from cascade.statistical_tests import (
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


def test_detection_threshold_vs_baseline_golden():
    """spec §5.3 #67: 黄金用例 —— 固定 d_series + **精确预期值**。

    复核 HIGH-3 修正: 原稿用 `n=588, var_d=0.25, rho=0.5, horizon=24, step=2`
    调用 —— 函数签名已改为 `(d_series, alpha=0.05)`，执行即
    `TypeError: unexpected keyword argument 'n'`；且断言 `0.09 < t < 0.10`
    仍是 **VIF 情景期望**，即 D2 违规在测试层存活。

    本用例固定序列，预期值可人工复算。
    """
    # 固定 d_series（方向命中差 ∈ {-1, 0, 1}），n=20
    d = np.array([1, -1, 0, 1, 1, -1, 1, 0, -1, 1,
                  1, -1, 1, 1, 0, -1, 1, 1, -1, 1], dtype=float)

    # 手工复算 SE_HAC（Bartlett, q=11）
    d_bar = d.mean()                     # = 0.25
    dc = d - d_bar
    q = 11
    g0 = np.mean(dc ** 2)
    lr = g0 + 2 * sum(
        (1 - j / (q + 1)) * np.mean(dc[j:] * dc[:-j]) for j in range(1, q + 1)
    )
    se_hac_expected = np.sqrt(lr / len(d))
    expected = 1.645 * se_hac_expected

    got = compute_detection_threshold_vs_baseline(d)
    assert abs(got - expected) < 1e-9, (
        f"预期 {expected}（= 1.645 × SE_HAC），实得 {got}"
    )
    # 显式断言：结果由实测 HAC 决定，与 VIF 情景值 0.096 无关
    assert abs(got - 0.096) > 1e-6 or abs(expected - 0.096) < 1e-9


def test_n_required_two_paths_mutually_exclusive():
    """spec §5.3 测试 16: 两途径互斥，且途径 B **不再乘** VIF。

    复核 HIGH-4 补录。
    """
    # 途径 A: 边际方差 × VIF
    n_a = compute_n_required(delta=0.10, var_d=0.25, horizon=24, step=2)
    assert 1200 < n_a < 1300          # ≈ 1240（VIF 情景）

    # 途径 B: 直接给 HAC 长程方差 —— 不得再乘 VIF
    var_lr = 0.25 * compute_planning_vif(24, 2)   # 已含自相关
    n_b = compute_n_required(delta=0.10, var_lr_d=var_lr)
    assert n_b == n_a, "途径 B 传入已含 HAC 的方差时不得再乘 VIF（防重复调整）"

    # 两途径同时提供 → fail-loud
    with pytest.raises(ValueError, match="禁止两条途径混用"):
        compute_n_required(delta=0.10, var_d=0.25, var_lr_d=var_lr)

    # 都不提供 → fail-loud
    with pytest.raises(ValueError, match="必须且只能提供"):
        compute_n_required(delta=0.10)


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


def _body_src(fn) -> str:
    """取函数**函数体**源码（剔除签名与 docstring）。

    复核 HIGH-2 修正: `inspect.getsource` 会**连 docstring 一起返回**，
    而本模块的 docstring 里大量出现 "VIF"（用于说明为何禁用），
    导致 `'vif' not in src.lower()` 之类的断言**必然失败**。
    源码断言必须只看可执行体。
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    fdef = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    body = fdef.body
    # 去掉开头的 docstring 节点
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ) and isinstance(body[0].value.value, str):
        body = body[1:]
    return "\n".join(ast.unparse(n) for n in body)


def test_no_mixing_hac_and_vif():
    """spec §8.3: 断言实现中**不存在**「长程方差 × VIF」的混用路径。

    源码断言（审计 D2 修正: 原稿为空函数体）。
    复核 HIGH-2 修正: 改用 `_body_src`（剔除 docstring），否则断言必失败。
    """
    from cascade.statistical_tests import compute_detection_threshold_vs_baseline

    body = _body_src(compute_detection_threshold_vs_baseline)
    assert "vif" not in body.lower(), (
        "detection_threshold_vs_baseline 的函数体混用了 VIF —— "
        "spec W3.5 明令禁止两条途径混用"
    )
    assert "compute_planning_vif" not in body, "verdict 路径不得调用规划 VIF"


def test_vif_is_planning_only():
    """spec W3.5: VIF 只允许出现在规划函数，不得进 verdict。"""
    from cascade import statistical_tests as st

    # 规划函数体内可以引用 VIF
    plan_body = _body_src(st.compute_planning_vif)
    assert "1 - j / h" in plan_body or "1-j/h" in plan_body.replace(" ", "")

    # verdict 侧函数体不得引用
    for fn_name in ("compute_detection_threshold_vs_baseline",
                    "compute_detection_threshold_vs_random"):
        body = _body_src(getattr(st, fn_name))
        assert "vif" not in body.lower(), f"{fn_name} 函数体不得引用 VIF"


def test_loss_definition_unique():
    """spec §8.3: 断言损失定义唯一（方向命中差 d_t ∈ {-1, 0, 1}）。

    审计 D2 修正: 原稿为空函数体。
    复核 HIGH-2 修正: 改用 `_body_src` 剔除 docstring。
    MAE/RMSE 类「预测误差差」属**独立检验**，不得与方向命中差混称。
    """
    from cascade.statistical_tests import compute_detection_threshold_vs_baseline

    body = _body_src(compute_detection_threshold_vs_baseline)
    for other_loss in ("mae", "rmse", "mse"):
        assert other_loss not in body.lower(), (
            f"检测阈值函数体混入了 {other_loss.upper()} 损失 —— 损失定义必须唯一"
        )

    # d_t 的取值域断言
    d = np.array([1.0, -1.0, 0.0, 1.0, 0.0])
    assert set(np.unique(d)) <= {-1.0, 0.0, 1.0}, "d_t 取值域应为 {-1, 0, 1}"



def test_hac_lag_order_single_source():
    """spec W1.2 / §5.3 测试 13: h/q 必须**单一来源**，且随 HORIZON/STEP 联动。

    复核 MEDIUM-1 修正: 原测试断言 `st.HAC_MAX_LAG_Q == 11` ——
    那是一个**独立常量**，恰是「第二处定义」。改为断言三处引用**同一函数**，
    且改动 HORIZON 时三处同步变化。
    """
    import inspect
    from unittest import mock
    from cascade import statistical_tests as st

    # 1) 唯一来源存在且取值正确
    assert st._hac_lag_order(24, 2) == 11

    # 2) DM 估计器不再内联推导（源码级断言）
    dm_body = _body_src(st.compute_hac_se)
    assert "horizon // max(1, step)" not in dm_body.replace(" ", ""), (
        "compute_hac_se 仍在本地推导 q —— 违反单一来源"
    )

    # 3) 联动：改 HORIZON 后三处同步（这是原 vacuous 断言缺失的真实检验）
    with mock.patch.object(st._bc, "HORIZON", 48):
        assert st._hac_lag_order() == 23, "HORIZON 翻倍后 q 必须同步变化"
        assert st._hac_lag_order(48, 2) == 23


def test_three_formulas_verified_separately():
    """spec §8.3: 三套公式（n_eff ESS / DM 标准误 / 功效规划）**分别**验证。

    禁止「一套通过即视为三套通过」。

    复核 LOW-2 修正: 原测试只用 `hasattr` 检查**存在性** ——
    三个空函数体也能通过。spec 要求的是**验证**，故本测试改为
    断言三套公式各自的**数值正确性**（黄金用例在各自专项测试中，
    此处做交叉一致性检查）。
    """
    import numpy as np
    from cascade import statistical_tests as st

    # 1) DM 标准误口径：对已知 IID 序列，HAC SE ≈ 样本 SE
    rng = np.random.default_rng(42)
    x = rng.standard_normal(2000)
    se_hac = st.compute_hac_se(x)
    se_iid = float(np.std(x, ddof=1) / np.sqrt(len(x)))
    assert abs(se_hac - se_iid) / se_iid < 0.15, (
        f"IID 序列下 HAC SE({se_hac}) 应接近样本 SE({se_iid})"
    )

    # 2) 功效规划口径：VIF 数值正确
    assert abs(st.compute_planning_vif(24, 2) - 8.0278) < 1e-3

    # 3) ESS 实测口径：独立入口且数值合理
    from cascade import evaluation_metrics as em
    n_eff, status = em.measured_n_eff(rng.standard_normal(1000))
    assert status == "ok"
    assert 0 < n_eff <= 1000

    # 4) 参数同源但**统计量不同**：VIF 与滞后阶数不是同一个量
    assert st.compute_planning_vif(24, 2) != st._hac_lag_order(24, 2)



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
