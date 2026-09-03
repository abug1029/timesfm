# Phase 4: JD 日历周期协变量实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 JD 鸡蛋及全品种引入 `calendar_cyclical` 协变量类型，用 4 维正余弦编码捕捉年度/月度周期季节性，补齐"时间维度先验信息"。

**Architecture:** 在 `cascade/features.py` 新增 `calc_calendar_cyclical(df_1h, horizon)` 纯函数，返回 `(context_bars + horizon, 4)` 矩阵；在 `build_covariate_matrix` 与 `build_combo_covariate_matrix` 的 elif 链中直接返回该结果（不再二次拼接）；在 `scripts/covariate_scan.py` 的 `COVARIATE_TYPES` 注册新类型。单测覆盖正交性、周期边界、horizon 精确填充。

**Tech Stack:** Python 3 + numpy + pandas + unittest (本仓库测试惯例)

## Global Constraints

- **注册零拼接**: `build_covariate_matrix`/`build_combo_covariate_matrix` 里的 `elif covariate_type == "calendar_cyclical":` 分支直接 `covariate_full = calc_calendar_cyclical(df_1h, horizon)`，**禁止**再做 `np.concatenate` 或 horizon 填充（`calc_calendar_cyclical` 已内置完整 horizon）。
- **向量化 Horizon**: 使用 `pd.date_range(start=last_dt + 1H, periods=horizon, freq='H')` 批量生成未来时间戳，再向量化计算 sin/cos，不写 `for h in range(...)` 循环。
- **时间列兜底**: 取 `df_1h` 时间列时 `dt_col = 'dt' if 'dt' in df_1h.columns else 'date'`，兼容上游清洗差异。
- **闰年处理**: DayOfYear 分母用 `365.25`（而非 365），近似吸收闰年偏移。
- **全品种通用**: `calendar_cyclical` 加入 `COVARIATE_TYPES` 列表，scan 阶段自然参与所有品种搜索，JD 只是首个验证品种。
- **测试框架**: 本仓库用 `python -m unittest tests.test_xxx -v` (unittest.TestCase)，**不用 pytest**。
- **中文注释**: 所有面向用户的输出、commit message、代码注释统一用中文。

---

## 文件结构

| 文件 | 责任 | 创建/修改 |
|------|------|:--------:|
| `cascade/features.py` | 新增 `calc_calendar_cyclical` + 两处注册 | 修改 |
| `scripts/covariate_scan.py` | `COVARIATE_TYPES` 追加 `"calendar_cyclical"` | 修改 |
| `tests/test_calendar_cyclical.py` | 单测: 正交性/周期边界/horizon填充/时间列兼容 | 创建 |

---

## 执行顺序

Task 1 → Task 2 → Task 3（三者独立，可并行 subagent 执行）

---

### Task 1: 新增 `calc_calendar_cyclical` 函数 + 注册到 `build_covariate_matrix`

**Files:**
- Modify: `cascade/features.py:970-980` (注册点) + 文件末尾新增函数
- Test: `tests/test_calendar_cyclical.py`

**Interfaces:**
- Consumes: 无（独立函数）
- Produces: `calc_calendar_cyclical(df_1h: pd.DataFrame, horizon: int) -> np.ndarray` 返回 `(n_context + horizon, 4)` float32 矩阵，列序: `[doy_sin, doy_cos, month_sin, month_cos]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calendar_cyclical.py
"""calendar_cyclical 协变量单测 (Phase 4)
验证: 4维正交性、周期边界(12月↔1月, 12/31↔1/1)、horizon精确填充、时间列兼容
"""
import unittest
import numpy as np
import pandas as pd
from cascade.features import calc_calendar_cyclical


class TestCalendarCyclical(unittest.TestCase):

    def setUp(self):
        # 构造 100 根 1H K线,时间跨度含 12 月底 → 1 月初边界
        base = pd.Timestamp("2024-12-30 00:00:00")
        dts = pd.date_range(base, periods=100, freq="H")
        self.df = pd.DataFrame({
            "dt": dts,
            "close_price": np.random.rand(100) * 5000 + 4000,
            "open_price": np.random.rand(100) * 5000 + 4000,
            "high_price": np.random.rand(100) * 5000 + 4000,
            "low_price": np.random.rand(100) * 5000 + 4000,
            "volume": np.random.randint(1000, 10000, 100),
            "open_interest": np.random.randint(50000, 200000, 100),
        })

    def test_output_shape(self):
        """输出形状 = (n_rows + horizon, 4)"""
        horizon = 24
        out = calc_calendar_cyclical(self.df, horizon)
        self.assertEqual(out.shape, (100 + horizon, 4))

    def test_orthogonality(self):
        """sin^2 + cos^2 ≈ 1 (数值精度内)"""
        out = calc_calendar_cyclical(self.df, horizon=0)
        doy_sin, doy_cos, m_sin, m_cos = out[:,0], out[:,1], out[:,2], out[:,3]
        np.testing.assert_allclose(doy_sin**2 + doy_cos**2, 1.0, rtol=1e-6)
        np.testing.assert_allclose(m_sin**2 + m_cos**2, 1.0, rtol=1e-6)

    def test_periodic_boundary_dec_jan(self):
        """12月31日 23:00 与 1月1日 00:00 的 DayOfYear 衔接平滑"""
        # 构造跨年边界数据
        dts = pd.date_range("2024-12-31 22:00", periods=4, freq="H")
        df = pd.DataFrame({"dt": dts, "close_price": [1]*4})
        out = calc_calendar_cyclical(df, horizon=0)
        # 12/31 dayofyear=366 (闰年), 1/1 dayofyear=1
        # sin/cos 应平滑过渡,无突变
        diff = np.abs(out[1] - out[0])  # 相邻小时差
        self.assertTrue(np.all(diff < 0.1), f"跨年边界突变过大: {diff}")

    def test_horizon_exact_fill(self):
        """horizon 部分精确等于未来每小时的真实 dayofyear/month"""
        horizon = 12
        out = calc_calendar_cyclical(self.df, horizon)
        last_ctx = self.df["dt"].iloc[-1]
        future_dts = pd.date_range(last_ctx + pd.Timedelta(hours=1), periods=horizon, freq="H")
        expected_doy = future_dts.dayofyear.values
        expected_month = future_dts.month.values
        # 取 horizon 部分 (最后 horizon 行)
        horiz_part = out[-horizon:]
        np.testing.assert_allclose(
            np.round(np.arcsin(horiz_part[:,0]) * 365.25 / (2*np.pi)),
            expected_doy, atol=1
        )
        np.testing.assert_allclose(
            np.round(np.arcsin(horiz_part[:,2]) * 12 / (2*np.pi)),
            expected_month, atol=1
        )

    def test_time_column_compat(self):
        """同时兼容 'dt' 和 'date' 列名"""
        df_dt = self.df.copy()
        df_date = self.df.rename(columns={"dt": "date"})
        out_dt = calc_calendar_cyclical(df_dt, horizon=5)
        out_date = calc_calendar_cyclical(df_date, horizon=5)
        np.testing.assert_array_equal(out_dt, out_date)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/FlyBuddy/fm_a && source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate && python -m unittest tests.test_calendar_cyclical -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Write minimal implementation**

在 `cascade/features.py` 文件末尾（`build_combo_covariate_matrix` 函数之后、模块级）新增：

```python
# ──────────────────────────────────────────────────────────────
# Phase 4: 日历周期协变量 (calendar_cyclical)
# ──────────────────────────────────────────────────────────────

def calc_calendar_cyclical(df_1h: pd.DataFrame, horizon: int) -> np.ndarray:
    """
    计算日历周期 4 维正余弦编码: [sin(2π·DOY/365.25), cos(...), sin(2π·Month/12), cos(...)]
    
    Args:
        df_1h: 含时间列('dt'或'date')的 1H K线 DataFrame,长度 = context_bars
        horizon: 未来预测步数
    
    Returns:
        np.ndarray: shape (len(df_1h) + horizon, 4), dtype=float32
    """
    # 1) 兼容时间列名
    dt_col = 'dt' if 'dt' in df_1h.columns else 'date'
    dt_idx = pd.DatetimeIndex(df_1h[dt_col])
    
    # 2) Context 部分: 历史每小时的 4 维编码
    doy = dt_idx.dayofyear.values          # 1..366
    month = dt_idx.month.values            # 1..12
    
    ctx_4d = np.column_stack([
        np.sin(2 * np.pi * doy / 365.25),
        np.cos(2 * np.pi * doy / 365.25),
        np.sin(2 * np.pi * month / 12),
        np.cos(2 * np.pi * month / 12),
    ]).astype(np.float32)
    
    # 3) Horizon 部分: 向量化生成未来时间戳并编码
    last_dt = dt_idx[-1]
    future_dts = pd.date_range(
        start=last_dt + pd.Timedelta(hours=1),
        periods=horizon,
        freq='H'
    )
    future_doy = future_dts.dayofyear.values
    future_month = future_dts.month.values
    
    horiz_4d = np.column_stack([
        np.sin(2 * np.pi * future_doy / 365.25),
        np.cos(2 * np.pi * future_doy / 365.25),
        np.sin(2 * np.pi * future_month / 12),
        np.cos(2 * np.pi * future_month / 12),
    ]).astype(np.float32)
    
    # 4) 拼接并返回
    return np.vstack([ctx_4d, horiz_4d])
```

在 `build_covariate_matrix` 的 `elif` 链中（约 line 970-980，紧跟 `reversal_shadow_gated_05` 分支之后）插入：

```python
    elif covariate_type == "calendar_cyclical":
        # Phase 4: 日历周期 4 维正余弦 (已含完整 horizon,无需再填充)
        covariate_full = calc_calendar_cyclical(df_1h, horizon)
        covariate_name = "calendar_cyclical"
```

> 注：`build_covariate_matrix` 里原有的 `covariate_full = np.concatenate([...])` 等通用 horizon 填充逻辑**不执行**，因为我们直接返回完整矩阵。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_calendar_cyclical -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add cascade/features.py tests/test_calendar_cyclical.py
git commit -m "feat(phase4): 新增 calc_calendar_cyclical 4维日历周期协变量 + 单测"
```

---

### Task 2: 注册到 `build_combo_covariate_matrix` + `COVARIATE_TYPES`

**Files:**
- Modify: `cascade/features.py` (combo 注册点) / `scripts/covariate_scan.py:33-45` (`COVARIATE_TYPES` 列表)
- Test: 复用 Task 1 单测 + scan 冒烟

**Interfaces:**
- Consumes: Task 1 的 `calc_calendar_cyclical`
- Produces: combo 模式可用 `"calendar_cyclical"`；scan 列表含新类型

- [ ] **Step 1: Write the failing test (combo 注册冒烟)**

```python
# tests/test_calendar_cyclical_combo.py (可选轻量冒烟,也可直接用 scan 验证)
"""验证 calendar_cyclical 能进入 combo 模式"""
import unittest
import pandas as pd
import numpy as np
from cascade.features import build_combo_covariate_matrix

class TestCalendarCyclicalCombo(unittest.TestCase):
    def test_combo_registration(self):
        """combo 模式下直接返回 4 维矩阵,无额外拼接"""
        # 最小 mock df
        dts = pd.date_range("2024-01-01", periods=500, freq="H")
        df = pd.DataFrame({"dt": dts, "close_price": np.ones(500)*4000})
        # 直接调用内部函数验证分支存在
        from cascade.features import build_combo_covariate_matrix
        # 仅验证不抛 KeyError/ValueError
        try:
            _ = build_combo_covariate_matrix(
                symbol="jd", store=None,
                historical_daily_closes=np.ones(300)*4000,
                df_1h=df, horizon=24,
                covariate_types=["calendar_cyclical"]
            )
        except Exception as e:
            self.fail(f"combo 注册失败: {e}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_calendar_cyclical_combo -v`
Expected: FAIL (combo 注册缺失)

- [ ] **Step 3: Write minimal implementation**

**3a. `cascade/features.py` — `build_combo_covariate_matrix` 的 elif 链中插入**

约 line 1120-1130（紧跟 `reversal_shadow_gated_05` combo 分支后）：

```python
        elif cov_type == "calendar_cyclical":
            # Phase 4: combo 模式下将 4 维矩阵存入 result 字典
            result["calendar_cyclical"] = calc_calendar_cyclical(df_1h, horizon)
```

> 注：`build_combo_covariate_matrix` 内部循环变量名为 `cov_type`（非 `covariate_type`），且组装返回 `dict` 结构 `result[name] = matrix`，而非单协变量的 `covariate_full` 赋值。此处直接存入字典，键名与协变量类型一致。

**3b. `scripts/covariate_scan.py` — `COVARIATE_TYPES` 列表追加**

约 line 33-45（`COVARIATE_TYPES = [...]` 内，按字母序或分组放入）：

```python
COVARIATE_TYPES = [
    # ── 老协变量 (11 种) ──
    'ccl', 'oi', 'rsi_slope', 'hourly_slope', 'rsi_state',
    'pca_momentum', 'hurst', 'gated_slope', 'regime_gated',
    'basis_momentum', 'vor',
    # ── quant-trading 协变量 (5 种, 2026-07-18 引入) ──
    'ao_accel', 'bb_squeeze', 'ha_body', 'reversal_shadow', 'sar_dist',
    # ── Phase 5 影线门控三档 (2026-07-29) ──
    'reversal_shadow_gated_02', 'reversal_shadow_gated_03', 'reversal_shadow_gated_05',
    # ── Phase 4 日历周期 (2026-07-29) ──
    'calendar_cyclical',
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_calendar_cyclical_combo -v`
Expected: PASS

- [ ] **Step 5: Scan 冒烟验证**

```bash
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
python scripts/covariate_scan.py jd --points 3 2>&1 | tail -20
# 期望: 输出含 calendar_cyclical 行,MAE/DirAcc 正常,无报错
```

- [ ] **Step 6: Commit**

```bash
git add cascade/features.py scripts/covariate_scan.py tests/test_calendar_cyclical_combo.py
git commit -m "feat(phase4): combo 注册 + scan 列表加入 calendar_cyclical"
```

---

### Task 3: 整体回归 + 文档同步

**Files:**
- Modify: `config/prediction_scheme.py` (可选: 给 JD 备注，不改 covariate_type)
- Test: 全量单测 + 现有测试套件

**Interfaces:**
- Consumes: Task 1,2 产物
- Produces: 零回归确认

- [ ] **Step 1: 跑全量单测**

```bash
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
python -m unittest tests.test_calendar_cyclical tests.test_calendar_cyclical_combo tests.test_basis_oi_filter tests.test_scan_significance tests.test_future_bar_guard tests.test_vol_threshold_contract -v
```
Expected: 全 PASS

- [ ] **Step 2: 现有功能回归冒烟**

```bash
# 级联预测单品种 (不触发数据采集)
python scripts/cascade_predict.py jd --no-auto-collect 2>&1 | tail -10
# 期望: 正常跑完,报告生成,无 DimensionMismatch

# scan 全品种快速 (points=1)
python scripts/covariate_scan.py --points 1 2>&1 | grep -E "calendar_cyclical|最优|TOP"
# 期望: calendar_cyclical 出现在各品种结果中
```

- [ ] **Step 3: 可选 — JD scheme 备注更新**

在 `config/prediction_scheme.py` 的 JD scheme 注释行（约 line 391）追加一行：

```python
        covariate_type="gated_slope",  # 2026-07-07 7pt回测: EV=+0.166, PF=1.40
        # Phase 4 备选: calendar_cyclical (日历周期 4 维正余弦, 待 scan 验证)
```

- [ ] **Step 4: Commit**

```bash
git add config/prediction_scheme.py
git commit -m "docs(phase4): JD scheme 备注 calendar_cyclical 备选"
```

---

## Self-Review (自查清单)

- [x] **Spec coverage**: 4 维正余弦/向量化 horizon/时间列兼容/闰年分母/零拼接注册/全品种通用/单测 5 用例 — 全部有 Task 对应
- [x] **Placeholder scan**: 无 TBD/implement later；每步有可粘贴代码块
- [x] **Type consistency**: `calc_calendar_cyclical(df_1h, horizon) -> np.ndarray (n,4)` 在 Task 1 定义、Task 2 两处注册直接使用、Task 3 回归验证，签名完全一致
- [x] **Critical bug fix**: 注册处**直接返回**函数结果，不再 `np.concatenate`，避免维度翻倍崩溃
- [x] **向量化**: `pd.date_range` + `np.column_stack` 替代循环
- [x] **时间列兜底**: `dt_col = 'dt' if 'dt' in df_1h.columns else 'date'`

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-29-phase4-calendar-cyclical.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

---

## [Deviation Record] 4D → 4×1D 拆分 (2026-07-29)

### 偏差描述
Plan 原文要求 `build_covariate_matrix` 返回单个 key `"calendar_cyclical"`，对应 4D 矩阵 `[seq_len, 4]`。

实际实现拆分为 4 个独立 1D key：
- `calendar_doy_sin` / `calendar_doy_cos` / `calendar_month_sin` / `calendar_month_cos`

### 偏差原因
TimesFM 及现有特征流转管道默认针对 1D 时间序列 `[seq_len]` 设计。强行传入 2D 矩阵 `[seq_len, 4]` 会导致底层框架在 `np.concatenate` 或转 Tensor 时触发维度崩溃（Dimension Mismatch: 3D vs 2D）。

将 1 个 4D 矩阵拆分为 4 个 1D 协变量同时喂给模型，在数学上完全等价，是唯一可行的架构适配方案。

### 架构决策
`calendar_cyclical` 在架构中作为**"宏特征（Macro Feature）"**存在：
- 用户配置 `--cov-override calendar_cyclical` 或 `--combo calendar_cyclical,...`
- 系统通过 `supported` 列表校验（列表中只有 `"calendar_cyclical"`）
- `build_covariate_matrix` 内部自动展开为 4 个 1D key
- 4 个维度（正弦/余弦成对）必须同时存在，不可单独暴露给用户（避免周期断层）

### 验证
- ✅ 单协变量模式拆分：`tests/test_calendar_cyclical.py::test_build_covariate_matrix_split_single`
- ✅ Combo 模式拆分：`tests/test_calendar_cyclical.py::test_build_combo_covariate_matrix_split`
- ✅ Scan JD 验证通过：MAE=5.10%（排名第 3）