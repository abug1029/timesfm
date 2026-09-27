# FM_a 协变量研究可信度 — 阶段 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 FM_a 的"过门"（`gate_pass`）重新具备证据含义。阶段 1 闭合三项硬门中**不依赖 D5 裁定的部分**：因果与对齐（`bfill`、换月；cutoff 语义见附录 A）、比较对象（无协变量基线、DM 显式状态）、结果可追溯（协议/样本/协变量矩阵指纹）。

**Architecture:** 分四阶段，本计划只覆盖**阶段 1**（`[L1]`）。**8 个任务**：`run_mode` 双模式 + schema 波及面、`bfill` 因果化、换月量化与完整传输链、复权策略显式化、无协变量基线、指纹与接线、DM 状态机 + `covariates_used` + A1 完整性校验、出口核验。**推荐执行顺序 1→2→3→4→6→5→7→8**（Task 6 指纹先于 Task 5，因 Task 5 引用 `compute_protocol_fingerprint`；见 Task 5 前置依赖）。**PR-A1（cutoff 语义 + checkpoint 键）受 D5 阻断**，全部隔离在附录 A。

**Tech Stack:** Python 3.11（WSL2 `.venv`）、pandas 2.x（**必须 <3**）、numpy <3、TimesFM 3.0、pytest + unittest 混用。

**Spec:** `/home/abug/timesfm/docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v14）——执行者**必须同时读 spec**。

## Global Constraints

- **三项硬门（§1.1 L1）**：① 因果与对齐正确；② 比较对象正确；③ 结果可追溯。
- **`gate_pass` 是质量筛选器，不是科学结论**。L1 交付 `gate_pass` + A1 字段，**不是 `pass`**。
- **`run_mode` 是唯一枚举字段**（`"exploration"`/`"confirmation"`）；`run_label` 供人读。**禁止**用标签充当机器判据。
- **字段分级（§1.2）**：A1 缺失 → verdict **不完整**，不得进入成功判定；A2 仅确认运行强制；B 级缺失 → 有效但标"不可复现" + WARN；C 级缺失 → **完全有效**。
- **§8.6 实施层降级**：① 缺失机制核心强制字段仅 `n_avail_variant`/`n_avail_baseline`/`n_common` + 布尔 `missingness_admissible`；② 除 `research_target_hash`/`protocol_fingerprint` 外其余哈希为实现细节，**不进报告正文**，golden 精确值测试只保留 `research_target_hash`；③ `dm_status` 枚举 **7 个**，`d_bar_le_zero` 只落盘。
- **§8.5 硬约束**：D5 未裁定 → **PR-A1 与 PR-D2 不得实施**；目标效应未裁定 → PR-D2 不得实施；每个 PR 必须带绿测试。
- **环境**：WSL2 `/home/abug/timesfm` 是**唯一权威源**。命令走 `wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && ..."`。读文件**必须从 WSL 内读**。
- **测试**：扁平 `tests/`，无 `pytest.ini`。跑法 `python -m pytest tests/test_x.py -v`。常规回归加 `-m 'not slow'`。
- **提交**：每任务一次 commit，结尾附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

## 三条施工纪律（本计划因违反它们返工过一次，务必遵守）

1. **锚点必读源码**：本计划所有 `file:line` 与函数签名均已从 WSL 源码逐条核实。**若你在施工中发现任一锚点与源码不符，停下来报告**，不要即兴发挥。
2. **"Produces" 必须配完整传输链**：任何"verdict 新增字段 X"都必须有步骤说明 X 如何从数据源流到 verdict 键（源 → 中间函数 → 键）。**没有传输链的字段一律降级为"本阶段不交付"**。
3. **改动必查波及面**：每个任务有"波及面"节，列出该改动会让哪些既有构造器/测试/调用点失效。**这些文件必须进 Files 与 `git add`**，否则会出现"新字段让生产路径抛 ValueError"这类静默破坏。

---

## File Structure

| 文件 | 职责 | 本计划改动 |
|---|---|---|
| `task_FM/evaluations/fm_eval/evaluator.py` | verdict 汇总与门控 | `build_summary`/`map_summary` 增字段；`load_baseline_points` 增 `cov` 参数；DM 诊断接入；A1 完整性校验 |
| `cascade/statistical_tests.py` | DM 检验 + BH-FDR | 增配对诊断函数；**不改 DM 估计量** |
| `scripts/registry_lib.py` | verdict schema 与登记 | schema 增字段；`pass_variants` 去后门 + run_mode 守卫；**三个 v2 构造器同步** |
| `cascade/features.py` | 协变量构造 | `causal_ffill` 助手；`calc_ccl_pct` 因果化 |
| `cascade/evaluation_metrics.py` | 指标计算 | `calc_prediction_quality` 增 `roll_flags` 与四键 |
| `scripts/monthly_backtest.py` | 回测主循环 | `roll_in_horizon` + 逐点标记 + `summarize` 传输 |
| `data/data_store.py` | 数据读取与复权 | `resolve_adjustment_policy`；死表标注 |
| `scripts/generate_baseline_points.py` | 基线生成 | 无协变量模式 + 协议指纹 |
| `scripts/praxist_supervisor.py` | 三环监督 | `ensure_baselines` 改 nocov；排名守卫；头部文案 |
| `scripts/aligned_slow_loop.py` | 慢环执行 | 基线加载传 `cov`；`_no_data_verdict` 补字段 |
| `config/prediction_scheme.py` | 方案配置 | 删 `xreg_covariates`（**仅 :132-134**） |
| `tests/test_verdict_registry.py` | 既有测试 | `_v2_complete` fixture 与新 pass 语义同步 |

**新增测试**：`test_run_mode_field.py`、`test_bfill_causal.py`、`test_roll_guard.py`、`test_backward_adjustment_reachable.py`、`test_nocov_baseline.py`、`test_protocol_fingerprint.py`、`test_cov_fingerprint.py`、`test_dm_status.py`、`test_a1_completeness.py`。

---

## Task 1: `run_mode`/`run_label` + schema 波及面同步

**Files:**
- Modify: `scripts/registry_lib.py`（schema 常量、`pass_variants`、**`make_error_tombstone`、`make_timeout_tombstone`**）
- Modify: `scripts/aligned_slow_loop.py`（**`_no_data_verdict`**）
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`（`build_summary`）
- Modify: `tests/test_verdict_registry.py`（`_v2_complete` fixture + pass 语义测试）
- Test: `tests/test_run_mode_field.py`（新建）

**Interfaces:**
- Produces: `registry_lib.RUN_MODES: frozenset`；`registry_lib.RUN_LABEL_EXPLORATION: str`；`build_summary(..., run_mode="exploration")`；verdict 键 `run_mode: str|None`、`run_label: str|None`

**波及面（本任务必查）**：
| 受影响处 | 位置 | 为什么 |
|---|---|---|
| `make_error_tombstone` | `registry_lib.py:301` | 手写 v2 dict（30 键），无 `run_mode` |
| `make_timeout_tombstone` | `registry_lib.py:358` | 同上 |
| `_no_data_verdict` | `aligned_slow_loop.py:55` | 手写 v2 dict，无 `run_mode` |
| `_v2_complete` fixture | `tests/test_verdict_registry.py:120` | 无 `run_mode`，驱动 3+ 个测试 |
| `test_pass_variants_v2_needs_fdr` | `tests/test_verdict_registry.py:180+` | 断言 `migrated_pass=True` 可晋升——**新语义下必须失败** |

> **设计裁定（避免生产崩溃）**：`run_mode` **同时**加入 `VERDICT_FIELDS_V2` 与 `VERDICT_FIELDS_V2_NULLABLE`。理由：`validate_verdict_v2` 的 `nullable_ok = missing - VERDICT_FIELDS_V2_NULLABLE`（`registry_lib.py:164`）对 NULLABLE 字段容忍**缺失**，故 tombstone 等旧构造器不会抛 `ValueError`；而 `pass_variants` 的 `run_mode not in RUN_MODES → continue` 保证它们**永不晋升**。二者配合，既无破坏面又守住 A1。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_run_mode_field.py`：

```python
"""§1.4 双运行模式 + §1.2 A1 守卫。"""
import unittest

from scripts.registry_lib import (
    RUN_MODES, RUN_LABEL_EXPLORATION, VERDICT_FIELDS_V2, VERDICT_FIELDS_V2_NULLABLE,
)


class TestRunModeSchema(unittest.TestCase):
    def test_enum_is_exactly_two_modes(self):
        self.assertEqual(RUN_MODES, frozenset({"exploration", "confirmation"}))

    def test_schema_has_run_mode_and_tolerates_absence(self):
        self.assertIn("run_mode", VERDICT_FIELDS_V2)
        # 关键：在 NULLABLE 里 → tombstone 等旧构造器不会抛 ValueError
        self.assertIn("run_mode", VERDICT_FIELDS_V2_NULLABLE)

    def test_run_label_present_and_nullable(self):
        self.assertIn("run_label", VERDICT_FIELDS_V2)
        self.assertIn("run_label", VERDICT_FIELDS_V2_NULLABLE)


class TestRunModeOnVerdict(unittest.TestCase):
    def _verdict(self, run_mode):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55, "point_dir_ok_list": []}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        return build_summary(s, cand, run_mode=run_mode)

    def test_exploration_gets_label(self):
        v = self._verdict("exploration")
        self.assertEqual(v["run_mode"], "exploration")
        self.assertEqual(v["run_label"], RUN_LABEL_EXPLORATION)

    def test_confirmation_label_null_until_w34(self):
        v = self._verdict("confirmation")
        self.assertEqual(v["run_mode"], "confirmation")
        self.assertIsNone(v["run_label"])


class TestPassVariantsGuards(unittest.TestCase):
    def _snap(self, **kw):
        base = {"schema": "fm.aligned_verdict.v2", "status": "ok",
                "gate_pass": True, "fdr_pass": True, "p_value": 0.01,
                "migrated_pass": None, "run_mode": "confirmation"}
        base.update(kw)
        return {"v1": base}

    def test_confirmation_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(len(pass_variants(self._snap())), 1)

    def test_exploration_never_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(pass_variants(self._snap(run_mode="exploration")), [])

    def test_missing_run_mode_never_promotes(self):
        from scripts.registry_lib import pass_variants
        snap = self._snap()
        del snap["v1"]["run_mode"]
        self.assertEqual(pass_variants(snap), [])

    def test_invalid_run_mode_never_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(pass_variants(self._snap(run_mode="bogus")), [])


class TestTombstonesSurviveNewSchema(unittest.TestCase):
    """波及面守卫：schema 加字段后三个构造器必须仍能通过校验。"""

    def test_error_tombstone_validates(self):
        from scripts.registry_lib import make_error_tombstone, validate_verdict
        v = make_error_tombstone("rb", "v1", "b1", RuntimeError("x"))
        self.assertEqual(validate_verdict(v), [])

    def test_timeout_tombstone_validates(self):
        from scripts.registry_lib import make_timeout_tombstone, validate_verdict
        v = make_timeout_tombstone("rb", "v1", "b1")
        self.assertEqual(validate_verdict(v), [])

    def test_no_data_verdict_validates(self):
        from scripts.aligned_slow_loop import _no_data_verdict
        from scripts.registry_lib import validate_verdict
        row = {"symbol": "rb", "variant_id": "v1", "cov_override": "ccl",
               "max_points": 6}
        v = _no_data_verdict(row, batch_id="b1")
        self.assertEqual(validate_verdict(v), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_run_mode_field.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'RUN_MODES'`

- [ ] **Step 3: 实现 schema 与守卫**

在 `scripts/registry_lib.py` 的 `VERDICT_FIELDS`（第 4 行）之前插入：

```python
# §1.4 双运行模式：唯一机器枚举字段。成功判定读 run_mode，不读 run_label。
RUN_MODES = frozenset({"exploration", "confirmation"})
RUN_LABEL_EXPLORATION = "exploratory_unconfirmed"
```

把 `"run_mode", "run_label",` 加入 `VERDICT_FIELDS_V2`（第 9-16 行）**与** `VERDICT_FIELDS_V2_NULLABLE`（第 17-22 行）。

改 `pass_variants()`（第 414-430 行）v2 分支：

```python
        if v.get("schema") == "fm.aligned_verdict.v2":
            # §1.2 A1：缺 run_mode 或取值非法 → 不得进入成功判定
            if v.get("run_mode") not in RUN_MODES:
                continue
            if v.get("run_mode") == "exploration":
                continue
            # W1.1：migrated_pass 已退出成功判定
            if (v.get("gate_pass") and v.get("fdr_pass")
                    and v.get("p_value") is not None):
                out.append(v)
```

> **两条守卫缺一不可**。只留 `exploration` 检查会让缺 `run_mode` 的历史 verdict 静默晋升。

- [ ] **Step 4: 三个构造器补 `run_mode: None`**

`make_error_tombstone`（`registry_lib.py:301-355`）与 `make_timeout_tombstone`（`:358-411`）的返回 dict 与 `metrics` 子 dict 各加一行：

```python
        "run_mode": None,        # tombstone 非评估产物，无运行模式
        "run_label": None,
```

`_no_data_verdict`（`aligned_slow_loop.py:55-95`）同样加这两行。

> 加 `None` 而非 `"exploration"`：tombstone 是错误/超时记录，**不是**探索运行。`pass_variants` 的 `not in RUN_MODES` 会挡住 `None`。

- [ ] **Step 5: `build_summary` 落字段**

改签名（`evaluator.py:255`）与 `out` dict（`:303-344`）：

```python
def build_summary(s, cand, *, baseline_points=None, baseline_dir_acc=None,
                  batch_id=None, run_mode="exploration"):
```

在 `out` dict 的 `"schema"` 之后加：

```python
        "run_mode": run_mode,
        "run_label": RUN_LABEL_EXPLORATION if run_mode == "exploration" else None,
```

`evaluator.py` 顶部 import 区加：

```python
from scripts.registry_lib import RUN_LABEL_EXPLORATION
```

> **若循环 import**：`registry_lib` 不 import `evaluator`，方向安全。若仍报错，在 `evaluator.py` 内定义同值常量，并在测试中断言两者相等。

- [ ] **Step 6: 同步既有测试（M4 修复）**

改 `tests/test_verdict_registry.py`：

1. `_v2_complete`（`:120`）的 `base` dict 加 `"run_mode": "confirmation", "run_label": None,`；
2. `test_pass_variants_v2_needs_fdr`（`:180+`）改为新语义：

```python
def test_pass_variants_v2_needs_fdr(tmp_path):
    """W1.1：migrated_pass 不再是晋升通道；必须 fdr_pass 且 p_value 非空。"""
    from scripts.registry_lib import pass_variants
    # migrated_pass=True 但 fdr_pass=None → 不晋升
    snap = {"v1": _v2_complete("v1", "b1", migrated_pass=True, fdr_pass=None,
                               p_value=None)}
    assert pass_variants(snap) == []
    # fdr_pass=True 且 p_value 非空 → 晋升
    snap2 = {"v1": _v2_complete("v1", "b1", migrated_pass=None, fdr_pass=True,
                                p_value=0.01)}
    assert len(pass_variants(snap2)) == 1
```

> **先跑一遍这个文件看真实断言**（`sed -n '175,210p' tests/test_verdict_registry.py`），按其真实结构改写，不要照搬上面的示意。

- [ ] **Step 7: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_run_mode_field.py tests/test_verdict_registry.py tests/test_prediction_quality_e2e.py tests/test_fm_evaluator_gated.py tests/test_praxist_fm_evaluator.py -v"
```

Expected: 全 PASS。**`test_prediction_quality_e2e.py` 与 `test_verdict_registry.py` 必须在此命令里**——它们是 tombstone 破坏面的检测点。

- [ ] **Step 8: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_run_mode_field.py tests/test_verdict_registry.py scripts/registry_lib.py scripts/aligned_slow_loop.py task_FM/evaluations/fm_eval/evaluator.py && git commit -m 'feat(eval): run_mode/run_label 双模式 + schema 波及面同步 (§1.4/W1.1)

探索运行与缺 run_mode 的 verdict 恒不入成功判定；
migrated_pass 退出晋升通道。三个 v2 构造器与既有夹具同步。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 2: `bfill` 因果化 + `cov_fill_version` bump（D4/E9）

**Files:**
- Modify: `cascade/features.py`（`causal_ffill` 助手、`calc_ccl_pct:644`、`calc_ao_acceleration:1975`）
- Test: `tests/test_bfill_causal.py`（新建）

> **（修订）本任务不含 `evaluator.py`**——`COV_FILL_VERSION` 常量的**唯一**归属是 Task 6（与它的消费方 `compute_protocol_fingerprint` 同处）。本任务只改 `features.py` 并在 commit message 里声明"`cov_fill_version` 的 bump 随 Task 6 的指纹函数生效"。

**Interfaces:**
- Produces: `cascade.features.causal_ffill(series, cold_start_fill) -> pd.Series`；协议指纹的 `cov_fill_version` 由 `"v1"` → `"v2"`

**波及面**：
| 受影响处 | 为什么 |
|---|---|
| 全部历史 verdict 与基线 | `ccl_pct` 通道数值改变 → 与旧记录**不可比**（这正是 bump 的目的，不是副作用） |
| `cov_fill_version` 默认值 | 不改则新旧指纹相同 → 被判"可比" → **E9 静默架空** |
| 既有 `test_system_hardening.py` / features 测试 | 冷启动段数值会变 |

> **M5 的精确结论（经实测修正——不要写"输出中性"，那是错的）**：
> - **`calc_ccl_pct` 的 `bfill` 是真泄漏**：`oi_base.replace(0, np.nan).rolling(5, min_periods=1).mean()` 在 `oi` 前导为 0 时产出前导 NaN，`bfill()` 把**未来的**平滑 OI 搬回来当分母 → `ccl_pct` 前导段携带 cutoff 之后的信息。**可用截断不变性测试捕获**（`oi` 前 10 根为 0、`oi_smooth[0..9]=NaN`、首个有效在 index 10；截断到 5 根时无未来可搬、回落到冷启动 → 两版不同）。
> - **`calc_ao_acceleration` 的 `bfill` 是结构性前视，但被 tanh 饱和与近零分子掩盖，输出级无法稳定观测**（一条计划曾写错成"输出中性"）。结构：`acc` 从 index 2 起有值，而 `mad` 前导 NaN 是 index 0..3（`acc` 在 0..1 为 NaN → `rolling(100, min_periods=2).median()` 需 2 个非 NaN，index 4 才达标）→ `scale[2..3] = mad.bfill() = mad[4]`，**index 2 用了 index 4 的信息**。实测（带噪声正弦波）为什么截断后无差异：index 2..4 的 `acc≈0`（分子为零、分母无所谓），index 5+ 的 `mad` 极小导致 `tanh` 饱和 ±1 掩盖分母差异。**这个"看起来没泄漏"是靠饱和运气，不是保证**。
> - **检测策略**：`calc_ccl_pct` 用截断生命周期测试（真实捕获）；`calc_ao_acceleration` **只能用源码级断言**（`assertNotIn(".bfill()", src)`），不要写会假绿的截断测试。**修复**：两处一律 `causal_ffill`（消除前视本身，不因"观测不到"而放任）。commit message 写明"结构性前视、通常被 tanh 饱和掩盖、但仍须修复"。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_bfill_causal.py`：

```python
"""D4：禁止用未来值回填。"""
import inspect
import unittest

import numpy as np
import pandas as pd

from cascade.features import causal_ffill


class TestCausalFfill(unittest.TestCase):
    def test_leading_nan_uses_cold_start_not_future_value(self):
        out = causal_ffill(pd.Series([np.nan, np.nan, 3.0, 4.0]), cold_start_fill=1.0)
        self.assertEqual(list(out), [1.0, 1.0, 3.0, 4.0])

    def test_interior_nan_carries_forward(self):
        out = causal_ffill(pd.Series([1.0, np.nan, 3.0]), cold_start_fill=0.0)
        self.assertEqual(list(out), [1.0, 1.0, 3.0])

    def test_all_nan_becomes_cold_start(self):
        out = causal_ffill(pd.Series([np.nan, np.nan]), cold_start_fill=1.0)
        self.assertEqual(list(out), [1.0, 1.0])


class TestCclPctCausality(unittest.TestCase):
    """真泄漏点：oi 前导为 0 → replace(0,nan) → rolling NaN → bfill 搬未来值。"""

    def _df(self, n=60):
        rng = np.random.default_rng(0)
        oi = np.zeros(n)
        oi[10:] = rng.uniform(100, 200, n - 10)   # 前 10 根为 0
        return pd.DataFrame({
            "dt": pd.date_range("2026-01-01", periods=n, freq="h"),
            "ccl": rng.normal(0, 1, n),
            "oi": oi,
        })

    def test_ccl_pct_leading_segment_is_causal(self):
        from cascade.features import calc_ccl_pct
        df = self._df()
        full = calc_ccl_pct(df["ccl"], df["oi"])
        # 截断到冷启动段内（第 5 点）：此时未来数据尚不存在
        part = calc_ccl_pct(df["ccl"].iloc[:5], df["oi"].iloc[:5])
        for k in range(5):
            self.assertAlmostEqual(
                float(full.iloc[k]), float(part.iloc[k]), places=10,
                msg=f"ccl_pct 第 {k} 点依赖了未来数据（bfill 泄漏）")


class TestAoAccelBfillRemoved(unittest.TestCase):
    """结构性前视但被 tanh 饱和掩盖：只断言源码不再 bfill。"""

    def test_no_bfill_in_calc_ao_acceleration(self):
        from cascade.features import calc_ao_acceleration
        src = inspect.getsource(calc_ao_acceleration)
        self.assertNotIn(".bfill()", src)

    def test_no_bfill_in_calc_ccl_pct(self):
        from cascade.features import calc_ccl_pct
        src = inspect.getsource(calc_ccl_pct)
        self.assertNotIn(".bfill()", src)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_bfill_causal.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'causal_ffill'`；`test_ccl_pct_leading_segment_is_causal` 因 bfill 泄漏 FAIL；两条 `.bfill()` 源码断言 FAIL。

- [ ] **Step 3: 实现**

在 `cascade/features.py` 的 `EPSILON` 定义之后加：

```python
def causal_ffill(series: pd.Series, cold_start_fill: float) -> pd.Series:
    """因果前向填充（D4）：禁止 bfill 把未来值搬到过去。

    前导 NaN 用 cold_start_fill 常数冷启动（冷启动段本无可用信息），
    中间/尾部 NaN 用 ffill 前向携带（只用过去）。
    """
    return series.ffill().fillna(cold_start_fill)
```

改 `calc_ccl_pct` 第 644 行：

```python
        oi_smooth = causal_ffill(oi_smooth, cold_start_fill=1.0)
```

改 `calc_ao_acceleration` 第 1975 行：

```python
    scale = causal_ffill(mad, cold_start_fill=EPSILON)
```

- [ ] **Step 4: 声明 `cov_fill_version` 将 bump（常量归属 Task 6，本任务不建）**

> **（缺陷 A 修订）`COV_FILL_VERSION` 常量由 Task 6 定义（与 `compute_protocol_fingerprint` 同处，单一来源）**。本任务**不创建**它、不碰 `evaluator.py`。本步只需要求在 Task 6 落地时把该常量设为 `"v2"`，并在本任务 commit message 里声明因果链：

> **因果链（写进本任务 commit message，但不建常量）**：`ccl_pct` 通道数值改变 → 协变量矩阵改变 → 与 `cov_fill_version="v1"` 的旧 verdict/基线**不可比**。该 bump 由 Task 6（`compute_protocol_fingerprint` 的 `cov_fill_version` 引用 `COV_FILL_VERSION="v2"`）生效。**旧 `ccl` 基线在 Task 5 须重新生成。**

- [ ] **Step 5: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_bfill_causal.py -v && python -m pytest tests/ -m 'not slow' -q"
```

Expected: 新测试全 PASS。**若有既有测试失败**，逐个判定是"断言了旧 bfill 行为"（更新断言并在 commit 说明）还是真实回归（修实现）。

- [ ] **Step 6: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_bfill_causal.py cascade/features.py && git commit -m 'fix(features): ccl_pct bfill 因果化 (D4)

calc_ccl_pct 的 bfill 是真泄漏（oi 前导 0 → rolling NaN → 搬未来值当分母），
改用 causal_ffill + 常数冷启动。
calc_ao_acceleration 的 bfill 经实测为结构性前视（scale[2..3]=mad[4]），
但通常被 tanh 饱和与近零分子掩盖而输出级不可观测——仍须修复，检测用源码断言。
cov_fill_version 的 bump 随 Task 6 的 compute_protocol_fingerprint 生效
（ccl_pct 语义变更将使旧 verdict/基线不可比）。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 3: 换月量化与守卫 + 完整传输链（D1/D2）

**Files:**
- Modify: `scripts/monthly_backtest.py`（`roll_in_horizon`、`_CHECKPOINT_POINT_KEYS:96-101`、逐点构造 `:306-311`、`summarize:480-560`）
- Modify: `cascade/evaluation_metrics.py`（`calc_prediction_quality:399-470`）
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`（`map_summary:364-394`、`build_summary:303-344`）
- Modify: `scripts/registry_lib.py`（schema）
- Test: `tests/test_roll_guard.py`（新建）

**Interfaces:**
- Produces: `monthly_backtest.roll_in_horizon(contract_codes) -> bool`；`calc_prediction_quality(..., roll_flags=None)` 返回 dict 增 4 键

**传输链（本任务的核心，缺一段则该字段到不了 verdict）**：

```
all_1h["contract_code"][idx+1:idx+HORIZON]
  → roll_in_horizon(...)                        [monthly_backtest.py:306 一带]
  → point["roll_in_horizon"]                    [逐点 dict]
  → summarize(): roll_flags = [p.get("roll_in_horizon", False) for p in ok]
  → calc_prediction_quality(..., roll_flags=...) → 返回 4 键
  → summarize() 返回 dict 增 4 键               [monthly_backtest.py:535 一带]
  → map_summary(s) 映射 4 键                    [evaluator.py:364]
  → build_summary() out dict 落 4 键            [evaluator.py:303]
```

**波及面**：
| 受影响处 | 位置 | 为什么 |
|---|---|---|
| `calc_prediction_quality` 唯一生产调用点 | `monthly_backtest.py:497` | 真实签名是 `(pred_endpoints, real_endpoints, base_prices, pred_paths=None, real_paths=None)`——**追加关键字参数**，不得改前三个位置参数 |
| `map_summary` 的 10 键 | `evaluator.py:364-394` | 新增键必须在此映射，否则 `build_summary` 取不到 |
| 旧 checkpoint | `_CHECKPOINT_POINT_KEYS:962` 的 `if k in rec` | 旧 checkpoint 无 `roll_in_horizon` → 恢复时取默认 `False`（可接受，但要在核验报告里声明） |

- [ ] **Step 1: 写失败测试**

创建 `tests/test_roll_guard.py`：

```python
"""D1/D2：跨换月 cutoff 必须可识别、可剔除、剔除量可见。"""
import unittest

import numpy as np

from scripts.monthly_backtest import roll_in_horizon


class TestRollInHorizon(unittest.TestCase):
    def test_no_roll_when_single_contract(self):
        self.assertFalse(roll_in_horizon(["RB_MAIN"] * 24))

    def test_roll_detected_on_contract_change(self):
        self.assertTrue(roll_in_horizon(["RB2601"] * 10 + ["RB2605"] * 14))

    def test_empty_is_not_a_roll(self):
        self.assertFalse(roll_in_horizon([]))

    def test_change_at_second_position_counts(self):
        self.assertTrue(roll_in_horizon(["RB2601", "RB2605", "RB2605"]))


class TestDenominatorReporting(unittest.TestCase):
    """注意：真实签名是 (pred_endpoints, real_endpoints, base_prices, ...)。"""

    def _call(self, pred, real, base, roll_flags):
        from cascade.evaluation_metrics import calc_prediction_quality
        return calc_prediction_quality(pred, real, base, roll_flags=roll_flags)

    def test_counts_and_ratio_present(self):
        n = 20
        pred = [100.0] * n
        real = [100.1] * n
        base = [100.0] * n
        out = self._call(pred, real, base, [False] * 18 + [True] * 2)
        self.assertEqual(out["n_roll_excluded"], 2)
        self.assertAlmostEqual(out["n_roll_ratio"], 2 / n, places=10)

    def test_full_keeps_all_points(self):
        pred = [100.1, 100.1, 100.1]
        real = [100.1, 100.1, 99.9]
        base = [100.0, 100.0, 100.0]
        out = self._call(pred, real, base, [False, False, True])
        self.assertAlmostEqual(out["dir_acc_full"], 2 / 3, places=6)
        self.assertAlmostEqual(out["dir_acc_ex_roll"], 1.0, places=6)

    def test_roll_flags_none_preserves_old_behavior(self):
        pred, real, base = [100.1] * 5, [100.1] * 5, [100.0] * 5
        from cascade.evaluation_metrics import calc_prediction_quality
        out = calc_prediction_quality(pred, real, base)
        self.assertEqual(out["n_roll_excluded"], 0)
        self.assertEqual(out["dir_acc_full"], out["dir_acc"])
        self.assertEqual(out["dir_acc_ex_roll"], out["dir_acc"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_roll_guard.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'roll_in_horizon'`

- [ ] **Step 3: 实现 `roll_in_horizon` 与逐点标记**

在 `scripts/monthly_backtest.py` 的 `_CHECKPOINT_POINT_KEYS`（第 96 行）之前加：

```python
def roll_in_horizon(contract_codes) -> bool:
    """horizon 内是否发生合约切换（D1/D2 换月守卫）。

    跨换月的 cutoff 其 delta_real 混合两个合约的价格，方向标签不可比，
    必须从 dir_acc 分母中剔除（或单独成组报告）。
    """
    if not contract_codes:
        return False
    first = contract_codes[0]
    return any(c != first for c in contract_codes[1:])
```

`_CHECKPOINT_POINT_KEYS`（第 97-102 行）元组末尾加 `"roll_in_horizon",`。

在逐点构造处（`:306-311`，`base = float(...)` 之后）加：

```python
        _cc = all_1h["contract_code"].iloc[idx+1:idx+1+HORIZON].tolist()
        _roll = roll_in_horizon(_cc)
```

并把 `"roll_in_horizon": _roll,` 加进该点的 `point` dict。

- [ ] **Step 4: `calc_prediction_quality` 增关键字参数**

改 `cascade/evaluation_metrics.py:399-405` 的**签名**（保留前三个位置参数不变）：

```python
def calc_prediction_quality(
    pred_endpoints,
    real_endpoints,
    base_prices,
    pred_paths=None,
    real_paths=None,
    roll_flags=None,
) -> dict:
```

在 `dir_acc = float(np.mean(dir_ok)) if n > 0 else 0.0` 之后插入：

```python
    # D1/D2 分母口径：full 不剔除任何点；ex_roll 剔除跨换月点
    dir_acc_full = dir_acc
    if roll_flags is not None and len(roll_flags) == n:
        keep = ~np.asarray(roll_flags, dtype=bool)
        n_roll_excluded = int((~keep).sum())
        dir_acc_ex_roll = float(np.mean(dir_ok[keep])) if keep.any() else 0.0
    else:
        n_roll_excluded = 0
        dir_acc_ex_roll = dir_acc
    n_roll_ratio = (n_roll_excluded / n) if n > 0 else 0.0
```

在返回 dict（`:455-466`）中加：

```python
        "dir_acc_full": dir_acc_full,
        "dir_acc_ex_roll": dir_acc_ex_roll,
        "n_roll_excluded": n_roll_excluded,
        "n_roll_ratio": n_roll_ratio,
```

- [ ] **Step 5: 接传输链（三段，缺一不可）**

**(a) `summarize` 收集并传递** — 改 `scripts/monthly_backtest.py:497` 的调用与返回 dict：

```python
    _roll_flags = [bool(p.get("roll_in_horizon", False)) for p in ok]
    pq = calc_prediction_quality(pred_ends, real_ends, bases,
                                 roll_flags=_roll_flags)
```

在 `summarize` 的返回 dict（`:535` 一带，`"dir_acc"` 之后）加：

```python
        "dir_acc_full": round(pq["dir_acc_full"], 3),
        "dir_acc_ex_roll": round(pq["dir_acc_ex_roll"], 3),
        "n_roll_excluded": int(pq["n_roll_excluded"]),
        "n_roll_ratio": round(pq["n_roll_ratio"], 4),
```

**(b) `map_summary` 映射** — 在 `evaluator.py:385` 的返回 dict 中加：

```python
        "dir_acc_full": _f(s.get("dir_acc_full", s.get("dir_acc")), 0.5),
        "dir_acc_ex_roll": _f(s.get("dir_acc_ex_roll", s.get("dir_acc")), 0.5),
        "n_roll_excluded": _i(s.get("n_roll_excluded"), 0),
        "n_roll_ratio": _f(s.get("n_roll_ratio"), 0.0),
```

**(c) `build_summary` 落 verdict** — 在 `out` dict 与 `out["metrics"]` 各加：

```python
        "dir_acc_full": m["dir_acc_full"],
        "dir_acc_ex_roll": m["dir_acc_ex_roll"],
        "n_roll_excluded": m["n_roll_excluded"],
        "n_roll_ratio": m["n_roll_ratio"],
```

- [ ] **Step 6: schema**

`"dir_acc_full", "dir_acc_ex_roll", "n_roll_excluded", "n_roll_ratio",` 加入 `VERDICT_FIELDS_V2` **与** `VERDICT_FIELDS_V2_NULLABLE`（旧 verdict 无这些键，靠 NULLABLE 容忍缺失）。

- [ ] **Step 7: 加传输链端到端测试**

在 `tests/test_roll_guard.py` 追加：

```python
class TestTransmissionChain(unittest.TestCase):
    """C6 修复验证：字段必须能从 summarize 一路流到 verdict。"""

    def test_field_reaches_verdict(self):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55,
             "dir_acc_full": 0.54, "dir_acc_ex_roll": 0.56,
             "n_roll_excluded": 7, "n_roll_ratio": 0.0175,
             "point_dir_ok_list": []}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand)
        for k in ("dir_acc_full", "dir_acc_ex_roll",
                  "n_roll_excluded", "n_roll_ratio"):
            self.assertIn(k, v, f"{k} 未到达 verdict —— 传输链断了")
            self.assertIn(k, v["metrics"])
        self.assertEqual(v["n_roll_excluded"], 7)
```

- [ ] **Step 8: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_roll_guard.py -v && python -m pytest tests/test_evaluation_metrics.py tests/test_evaluation_metrics_contract.py tests/test_monthly_backtest_quality.py tests/test_fm_evaluator_gated.py -v"
```

Expected: 全 PASS；`test_roll_flags_none_preserves_old_behavior` 证明未传参时行为不变。

- [ ] **Step 9: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_roll_guard.py scripts/monthly_backtest.py cascade/evaluation_metrics.py task_FM/evaluations/fm_eval/evaluator.py scripts/registry_lib.py && git commit -m 'feat(eval): 换月量化与 roll_in_horizon 守卫 + 完整传输链 (D1/D2)

contract_code 此前读出未用；现标记跨换月点并落盘剔除量。
dir_acc_full 不剔除、dir_acc_ex_roll 剔除跨换月点。
传输链 summarize → map_summary → build_summary 三段齐备，
并加端到端测试钉住（此前计划只声明 Produces 却无传输步骤）。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 4: 复权策略显式化 + 死表死配置（D1/D3/C7）

**Files:**
- Modify: `data/data_store.py`（`resolve_adjustment_policy`、`:418-425`、`get_klines_1h:497-519`、三个 xreg 方法 docstring）
- Modify: `config/prediction_scheme.py`（**仅 `:132-134`**）
- Modify: `scripts/three_star_predict.py:376`
- Test: `tests/test_backward_adjustment_reachable.py`（新建）

**Interfaces:**
- Produces: `data_store.resolve_adjustment_policy(df) -> str`

**波及面**：
| 受影响处 | 位置 | 为什么 |
|---|---|---|
| `xreg_covariates` 字段**仅** :132-134 | `prediction_scheme.py` | **:129-131 是 `covariate_type`/`covariate_types`——生产在用（`monthly_backtest.py:281-291`）。按 :129-134 盲删会破坏协变量选择且测试照样绿** |
| `BacktestDataStore` 覆写 | `data_store.py:804+` | 子类覆写 `get_main_continuous`/`get_main_contract_1h`，attrs 落点须覆盖子类路径 |
| `df.attrs` 传播 | pandas 语义 | `.copy()` 后仍在，但 merge/assign 等可能静默丢失 |

> **本任务不擅自"修好"复权**——那会改变全部历史数值。只做两件可验证的低风险事：① 把"复权是否生效"变成**显式可见的事实**；② 死表/死配置标注。真正的复权修复属 PR-A1 之后的独立决策。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_backward_adjustment_reachable.py`：

```python
"""D1/D3/C7：复权是否生效必须显式可见；死表必须标注。"""
import inspect
import unittest

import pandas as pd

from data.data_store import DataStore, resolve_adjustment_policy


class TestAdjustmentPolicyVisible(unittest.TestCase):
    def test_raw_close_takes_precedence_over_empty(self):
        # 关键：列存在性判断必须先于 empty 判断（1 行与 0 行语义相同）
        df = pd.DataFrame({"dt": [], "close_price": [], "raw_close": []})
        self.assertEqual(resolve_adjustment_policy(df),
                         "skipped_raw_close_column_present")

    def test_eligible_when_no_raw_close(self):
        df = pd.DataFrame({"dt": [], "close_price": []})
        self.assertEqual(resolve_adjustment_policy(df), "eligible")

    def test_none_is_empty(self):
        self.assertEqual(resolve_adjustment_policy(None), "empty")


class TestAttrsPropagation(unittest.TestCase):
    def test_policy_survives_one_copy(self):
        df = pd.DataFrame({"dt": [], "close_price": []})
        df.attrs["adjustment_policy"] = "eligible"
        self.assertEqual(df.copy().attrs.get("adjustment_policy"), "eligible")


class TestDeadTableMarked(unittest.TestCase):
    def test_xreg_factors_docstring_marked_dead(self):
        src = inspect.getsource(DataStore.get_xreg_factors)
        self.assertIn("[DEAD TABLE", src)
        self.assertIn("预测路径不读取", src)

    def test_xreg_matrix_docstring_marked_dead(self):
        self.assertIn("[DEAD TABLE", inspect.getsource(DataStore.get_xreg_matrix))

    def test_store_xreg_factor_docstring_marked_dead(self):
        self.assertIn("[DEAD TABLE", inspect.getsource(DataStore.store_xreg_factor))


class TestDeadConfigRemoved(unittest.TestCase):
    def test_xreg_covariates_gone_but_live_knobs_remain(self):
        from config import prediction_scheme
        src = inspect.getsource(prediction_scheme)
        self.assertNotIn("xreg_covariates", src)
        # 活字段必须仍在（防止盲删区间）
        self.assertIn("covariate_type", src)
        self.assertIn("covariate_types", src)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_backward_adjustment_reachable.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'resolve_adjustment_policy'`

- [ ] **Step 3: 实现（注意列判断先于 empty 判断——C2 修复）**

在 `data/data_store.py` 的 `apply_backward_adjustment_robust`（第 113 行）之前加：

```python
def resolve_adjustment_policy(df: pd.DataFrame) -> str:
    """显式报告复权策略（D1）。

    历史上 `apply_backward_adjustment_robust` 因 `raw_close` 恒在
    `MAIN_COLUMNS`（data_store.py:49）而永不执行——"以为复权了、实际没有"
    是静默失效。本函数把该事实变成可见返回值。

    注意：列存在性判断**先于** empty 判断且**不特判行数**——0 行 df 只要
    列结构允许（无 raw_close）即"eligible"（M2 复审修正：删去 df.empty 分支，
    否则 0 行无 raw_close 的 df 会被误判 "empty" 而非 "eligible"）。
    """
    if df is None:
        return "empty"
    if "raw_close" in df.columns:
        return "skipped_raw_close_column_present"
    return "eligible"
```

- [ ] **Step 4: 把策略落到读取路径**

改 `data/data_store.py:418-425` 一带：

```python
        # [C10] raw_close 恒在 MAIN_COLUMNS → 生产 SELECT * 必带该列 →
        # 此处条件恒假，apply_backward_adjustment_robust 在生产路径从不执行。
        # 这不是"已复权"，而是"未复权且无标记"——现显式记录策略（D1）。
        adjustment_policy = resolve_adjustment_policy(df)
        if adjustment_policy == "eligible":
            roll_records = detect_rolls_from_price_gaps(df)
            if roll_records:
                df = apply_backward_adjustment_robust(df, roll_records)
                adjustment_policy = "applied"
        df.attrs["adjustment_policy"] = adjustment_policy
```

> **落点确认**：先跑 `sed -n '380,430p' data/data_store.py` 看清 `get_main_continuous` 的控制流——`attrs` 必须写在**所有 return 路径都会经过**的位置，否则提前 return 时丢失。若该方法有多条 return，改为在每条 return 前赋值，或把赋值提到唯一出口。**同时检查 `BacktestDataStore`（`:804+`）的覆写版本是否也需要同样处理。**

在 `get_klines_1h`（`:497-519`）返回前加 `df.attrs["adjustment_policy"] = "not_implemented_1h"`。

- [ ] **Step 5: 标注死表（C7）**

在 `get_xreg_factors`（`:460`）、`store_xreg_factor`（`:352`）、`get_xreg_matrix`（`:718`）三个 docstring 首行加：

```python
        """[DEAD TABLE — 预测路径不读取] 读取 XReg 因子
        ...
```

- [ ] **Step 6: 删死配置（**仅 :132-134**，M8 修复）**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && sed -n '128,136p' config/prediction_scheme.py"
```

先看清真实行号，再**只删 `xreg_covariates` 字段本身**（核实为 `:132-134`），保留 `covariate_type`（`:130`）与 `covariate_types`（`:131`）。同步删除 `scripts/three_star_predict.py:376` 的打印行。

- [ ] **Step 7: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_backward_adjustment_reachable.py -v && python -m pytest tests/test_system_hardening.py tests/test_kb_schemes_consistency.py tests/test_regime_routing.py -v"
```

Expected: 全 PASS。**`test_kb_schemes_consistency.py` 与 `test_regime_routing.py` 必须在此命令里**——它们消费 `covariate_type`/`covariate_types`，是 M8 盲删的检测点。

- [ ] **Step 8: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_backward_adjustment_reachable.py data/data_store.py config/prediction_scheme.py scripts/three_star_predict.py && git commit -m 'feat(data): 复权策略显式化 + 死表死配置标注 (D1/D3/C7)

resolve_adjustment_policy 把 raw_close 恒存在导致复权永不执行这一
静默事实变成可见返回值；列判断先于 empty 判断。
仅删除 xreg_covariates（:132-134），保留活字段 covariate_type(s)。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 5: 无协变量基线（E7）

> **前置依赖（必读）**：本任务 `generate()` 会 `from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint`，该函数**在 Task 6 建立**。故执行顺序必须是 **1→2→3→4→6→5→7→8**（Task 6 指纹先于 Task 5 基线），否则 Task 5 的 import 会 `ImportError`。

**Files:**
- Modify: `scripts/generate_baseline_points.py`
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`（**`load_baseline_points:233`——定义在此，不在 aligned_slow_loop**）
- Modify: `scripts/aligned_slow_loop.py:149`、`task_FM/evaluations/fm_eval/run.py:109`
- Modify: `scripts/praxist_supervisor.py:1978-2027`（`ensure_baselines`）
- Test: `tests/test_nocov_baseline.py`（新建）

**Interfaces:**
- Produces: `generate_baseline_points.baseline_filename(symbol, cov=None) -> str`；`evaluator.load_baseline_points(symbol, root=None, cov=None) -> list`；基线记录增 `protocol_fingerprint`

**波及面**：
| 受影响处 | 位置 | 为什么 |
|---|---|---|
| `load_baseline_points` **定义** | `evaluator.py:233` | 不在 `aligned_slow_loop.py`——签名改动落点在此，**必须进 Files 与 git add** |
| 两个调用点 | `aligned_slow_loop.py:149`、`run.py:109` | 不传 `cov` 会静默读旧 ccl 基线 |
| `cov_override=None` 的回落 | `monthly_backtest.py:281-291` | **`None` 会被当作"未指定"回落到 scheme 默认（多数品种 `"ccl"`）→ `_nocov` 文件里装的还是 ccl 数据**。必须显式传 `"none"` |
| 旧 ccl 基线 | `task_FM/config/baseline_points_*.jsonl` | Task 2 的 `cov_fill_version` bump 已使其作废，本任务重新生成 |

> **D5 依赖提示**：本任务基线沿用现有 cutoff 约定。若 D5 裁定改为 `bar_close`，这些基线必须**重新生成**——在 PR-A1 落地时一并处理。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_nocov_baseline.py`：

```python
"""E7：DM 的对照必须是无协变量 TimesFM 运行，不是另一个协变量变体。"""
import inspect
import unittest


class TestBaselineFilename(unittest.TestCase):
    def test_nocov_has_distinct_filename(self):
        from scripts.generate_baseline_points import baseline_filename
        self.assertEqual(baseline_filename("rb", "ccl"),
                         "baseline_points_rb.jsonl")
        self.assertEqual(baseline_filename("rb", None),
                         "baseline_points_rb_nocov.jsonl")

    def test_none_and_none_string_are_equivalent(self):
        # cov_override 可能以字符串 "none" 形式传入
        from scripts.generate_baseline_points import baseline_filename
        self.assertEqual(baseline_filename("rb", None),
                         baseline_filename("rb", "none"))

    def test_symbol_lowercased(self):
        from scripts.generate_baseline_points import baseline_filename
        self.assertEqual(baseline_filename("RB", None),
                         "baseline_points_rb_nocov.jsonl")


class TestNoCovIsExplicit(unittest.TestCase):
    def test_generate_maps_none_to_none_string(self):
        """M3 修复：None 会被 monthly_backtest 回落成 scheme 默认，
        必须显式转成 'none' 才能走到 features.py:1190 的 slope_only 分支。"""
        from scripts import generate_baseline_points as gbp
        src = inspect.getsource(gbp.generate)
        self.assertIn('"none"', src)


class TestSupervisorUsesNoCov(unittest.TestCase):
    def test_ensure_baselines_requests_nocov(self):
        from scripts import praxist_supervisor as ps
        src = inspect.getsource(ps.ensure_baselines)
        # 断言完整调用片段，而非弱断言 assertIn("None", src)
        self.assertIn("gbp.generate(sym_lower, None, root)", src)
        self.assertNotIn('gbp.generate(sym_lower, "ccl"', src)

    def test_validity_check_targets_nocov_file(self):
        from scripts import praxist_supervisor as ps
        src = inspect.getsource(ps.ensure_baselines)
        self.assertIn("baseline_filename", src)


class TestLoaderAcceptsCov(unittest.TestCase):
    def test_load_baseline_points_has_cov_param(self):
        import inspect as _i
        from task_FM.evaluations.fm_eval.evaluator import load_baseline_points
        params = _i.signature(load_baseline_points).parameters
        self.assertIn("cov", params)

    def test_callers_pass_cov(self):
        from scripts import aligned_slow_loop as asl
        self.assertIn("cov=None", inspect.getsource(asl))


class TestBaselineCarriesProtocolFingerprint(unittest.TestCase):
    def test_generate_writes_protocol_fingerprint(self):
        from scripts import generate_baseline_points as gbp
        self.assertIn("protocol_fingerprint", inspect.getsource(gbp.generate))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_nocov_baseline.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'baseline_filename'`

- [ ] **Step 3: 创建规范模块并实现 `baseline_filename`（C1 复审修复：单一口径）**

> **勿在 `generate_baseline_points.py` 本地定义 `baseline_filename`**——那会产生两份实现、文件名约定可漂移。规范定义必须放独立模块 `cascade/baseline_paths.py`，`generate_baseline_points.py` 与 `evaluator.load_baseline_points` **都从它导入**。

**创建 `cascade/baseline_paths.py`**：

```python
"""基线文件路径的唯一规范（E7）。

供 generate_baseline_points.py 与 evaluator.load_baseline_points 共同导入，
避免两份实现漂移导致文件名约定分叉。
"""


def baseline_filename(symbol: str, cov=None) -> str:
    """基线文件名。cov=None 或 "none" 表示无协变量基线（E7）。"""
    sym = symbol.lower()
    if cov is None or cov == "none":
        return f"baseline_points_{sym}_nocov.jsonl"
    return f"baseline_points_{sym}.jsonl"
```

在 `scripts/generate_baseline_points.py` 顶部加：

```python
from cascade.baseline_paths import baseline_filename
```

在 `generate()` 内、调用 `run_symbol_backtest` 之前加 **M3 修复**：

```python
    # M3：cov_override=None 会被 monthly_backtest.py:281-291 回落到 scheme
    # 默认（多数品种 "ccl"），使 _nocov 文件里装的仍是 ccl 数据。
    # 必须显式传 "none" 才能走到 cascade/features.py:1190 的 slope_only 分支。
    effective_cov = "none" if (cov is None or cov == "none") else cov
```

并把 `cov_override=cov` 改为 `cov_override=effective_cov`。

- [ ] **Step 4: 基线记录落协议指纹 + 写路径切到 `_nocov`（C1 复审修复）**

> **C1 修复（务必做，勿遗漏）**：`generate()` 的输出路径**硬编码**为 `f"baseline_points_{sym_lower}.jsonl"`（先 `grep -n 'baseline_points_{sym_lower}.jsonl' scripts/generate_baseline_points.py` 定位）——若不改，`baseline_filename` 的区分语义被架空，`_nocov.jsonl` 永不生成，但 supervisor 与 `load_baseline_points(cov=None)` 都去读它。**必须把写路径切到 `baseline_filename`**：

```python
    jsonl_file = config_dir / baseline_filename(sym_lower, cov)
```

> 同时落协议指纹：

```python
    from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint
    _proto = compute_protocol_fingerprint()
```

写记录处（`:114-120` 一带）加：

```python
            "protocol_fingerprint": _proto,
```

> **导入方向**：本脚本 → `evaluator.py` 单向，安全。若循环 import，把 `compute_protocol_fingerprint` 抽到 `cascade/protocol_fingerprint.py` 由两侧导入。

- [ ] **Step 5: `load_baseline_points` 增 `cov`（落点在 evaluator.py）**

改 `evaluator.py:233`：

```python
def load_baseline_points(symbol, root=None, cov=None):
    """Load baseline points from JSONL file.

    cov=None → 无协变量基线（E7）。
    """
    if root is None:
        root = os.path.join(FM_ROOT, "task_FM", "config")
    from cascade.baseline_paths import baseline_filename
    path = os.path.join(root, baseline_filename(symbol, cov))
```

> **循环 import（必须这样写，勿用 generate_baseline_points 的版本）**：`generate_baseline_points` 已 import `evaluator`。故 `load_baseline_points` **只能**从 `cascade/baseline_paths.py` 导入 `baseline_filename`（二者都依赖该独立模块），**不要** `from scripts.generate_baseline_points import baseline_filename`——那会成环。

> **`baseline_metrics.json` 键冲突声明**：`generate_baseline_points.py:138` 用 `metrics[sym_lower]` 单一键写指标——ccl 与 nocov 基线**共用该键、互相覆盖**。本任务不修（旧 ccl 基线已随 `cov_fill_version` bump 作废），但在 Task 8 核验报告里声明"ccl 与 nocov 基线经同一 `baseline_metrics.json` 键，现阶段以 nocov 为准"。

- [ ] **Step 6: 两个调用点传 `cov=None`**

`scripts/aligned_slow_loop.py:149`：

```python
            baseline_pts = load_baseline_points(row["symbol"], cov=None)  # E7
```

`task_FM/evaluations/fm_eval/run.py:109` 同样改为 `cov=None`。

> **注意**：`run.py` 是**诊断**入口。它会一并切到 nocov 基线——**这是有意为之**（诊断也应与确认同口径），在 commit message 里写明。

- [ ] **Step 7: supervisor 改用 nocov 并校验 nocov 文件**

改 `scripts/praxist_supervisor.py:2004-2025`：

```python
        if not isinstance(met, dict) or not met.get("n") or int(met.get("n", 0)) <= 0:
            try:
                gbp.generate(sym_lower, None, root)   # E7: 无协变量基线
...
        if n_lines < 100:
            try:
                gbp.generate(sym_lower, None, root)   # E7: 无协变量基线
```

并把完整性检查的文件路径改为 `gbp.baseline_filename(sym_lower, None)`。

- [ ] **Step 8: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_nocov_baseline.py tests/test_generate_baseline_points.py tests/test_slow_loop_prescreen.py -v"
```

Expected: 全 PASS。

- [ ] **Step 9: 单品种实跑验证（不可跳过）**

**先核实 CLI 入口**（`--symbol`/`--cov` 旗标是否真实存在，勿假设——Task 8 已证实 `monthly_backtest.py` 没有 `--symbol`）：

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && grep -n 'argv\|add_argument\|argparse' scripts/generate_baseline_points.py | head -15"
```

按核实到的入口形式写实跑命令（若入口是位置参数，则不用 `--` 前缀）：

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python scripts/generate_baseline_points.py rb none && ls -la task_FM/config/baseline_points_rb_nocov.jsonl && head -1 task_FM/config/baseline_points_rb_nocov.jsonl && wc -l task_FM/config/baseline_points_rb_nocov.jsonl"
```

> **`cov` 映射一致性（必须对上 Step 3 的 `effective_cov`）**：CLI 传来的值必须能在 `generate()` 里落到 `effective_cov = "none" if (cov is None or cov == "none") else cov`。若实跑用的是选项式（如 `--cov none`），确认其 parse 后 `cov=="none"` → Step 3 逻辑收到 `"none"`；若 CLI 会给默认值，确认默认**不是** `"ccl"`。

Expected: `_nocov.jsonl` 存在、行数 `>= 100`、首行含 `protocol_fingerprint`。

> **必须核验数据内容**：确认日志里**没有** `xreg_fallback` 警告、且 `covariates_used` 路径走的是 `slope_only`。若行数 < 100 或内容仍是 ccl，**停下来查明**——DM 会静默拿不到对照。
>
> **`slope_only` 的可执行断言（本步骤直接执行——Task 6 已先于本任务完成）**：生成时刻的协变量通道数无法从 `jsonl` 直接看（记录只含 `{cutoff, dir_ok, delta_pred, delta_real, protocol_fingerprint}`）。真正确认 `None → "none" → slope_only` 的钩子是 Task 6 的 `hourly_model.last_covariate_input`。**在本步骤直接跑一条断言**：用 `cov_override="none"` 跑一次 `run_symbol_backtest`，断言 `last_covariate_input[1] == ["daily_slope"]`（单通道）——否则 `effective_cov` 映射可能在 Task 6 的改造中又被改坏。

- [ ] **Step 10: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_nocov_baseline.py scripts/generate_baseline_points.py cascade/baseline_paths.py task_FM/evaluations/fm_eval/evaluator.py scripts/aligned_slow_loop.py task_FM/evaluations/fm_eval/run.py scripts/praxist_supervisor.py && git commit -m 'feat(eval): 同 cutoff 无协变量基线取代 ccl 基线 (E7)

新增 cascade/baseline_paths.py 承载文件名约定，避免 evaluator 与
generate_baseline_points 循环导入。
显式把 cov=None 映射为 \"none\"——否则 monthly_backtest 会回落成
scheme 默认 ccl，使 _nocov 文件里装的仍是 ccl 数据。
基线记录携带 protocol_fingerprint 供协议兼容性前置检查。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 6: 指纹与接线（E8/E9/C2）

**Files:**
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`（三个指纹函数、`build_summary`）
- Modify: `cascade/hourly_model.py`（暴露最后输入矩阵与有序键）
- Modify: `scripts/aligned_slow_loop.py:154`、`task_FM/evaluations/fm_eval/run.py:114`（传 `points`/`cov_matrix`/`cov_keys`）
- Modify: `scripts/praxist_supervisor.py`（`materialize_known_verdicts:667` 排名守卫 + **头部文案 :676-677**）
- Modify: `scripts/registry_lib.py`（schema）
- Test: `tests/test_protocol_fingerprint.py`、`tests/test_cov_fingerprint.py`（新建）

**Interfaces:**
- Produces: `compute_protocol_fingerprint() -> str`、`compute_sample_fingerprint(points) -> str`、`compute_cov_fingerprint(matrix, keys) -> dict`；`registry_lib.comparable(a, b) -> bool`；`hourly_model.HourlyModel.last_covariate_input -> tuple|None`

**传输链**：
```
hourly_model.predict() 内的 past_future_covariates / covariate_keys  [hourly_model.py:211-216]
  → self.last_covariate_input = (matrix, keys)                      [新增暴露]
  → 调用方取出并传给 build_summary(cov_matrix=..., cov_keys=...)
  → out["cov_fingerprint"] = compute_cov_fingerprint(...)
```

**波及面**：
| 受影响处 | 位置 | 为什么 |
|---|---|---|
| `materialize_known_verdicts` 真实结构 | `praxist_supervisor.py:667` | **不是**全局 `sorted(...)` 排名，而是**逐品种** best dir_acc 循环（`items` 在 `:684` 取出后进 symbol 循环）——代码片段必须按真实结构写 |
| 头部文案 | `praxist_supervisor.py:676-677` | 仍写 `(fdr_pass OR migrated_pass)`，Task 1/7 改语义后无人更新 |
| `sample_fingerprint` 空值 | — | 调用方不传 `points` 时是 `sha256(空串)` 常量 → 会静默；本任务必须接通两个调用点 |

- [ ] **Step 1: 写失败测试**

创建 `tests/test_protocol_fingerprint.py`：

```python
import unittest

from task_FM.evaluations.fm_eval.evaluator import (
    compute_protocol_fingerprint, compute_sample_fingerprint,
)


class TestProtocolFingerprint(unittest.TestCase):
    def test_stable_and_hex(self):
        fp = compute_protocol_fingerprint()
        self.assertEqual(fp, compute_protocol_fingerprint())
        self.assertEqual(len(fp), 64)
        int(fp, 16)

    def test_changes_with_metric_version(self):
        self.assertNotEqual(compute_protocol_fingerprint(metric_version="v1"),
                            compute_protocol_fingerprint(metric_version="v2"))

    def test_cov_fill_version_bumped_after_bfill_fix(self):
        """Task 2 改了 ccl_pct 语义 → COV_FILL_VERSION 默认 v2，否则新旧可比却不可比。"""
        from task_FM.evaluations.fm_eval.evaluator import COV_FILL_VERSION
        self.assertEqual(COV_FILL_VERSION, "v2")

    def test_fingerprint_default_uses_constant(self):
        """CPU 常量与 COV_FILL_VERSION 必须同源（防双字面量漂移）。"""
        from task_FM.evaluations.fm_eval.evaluator import (
            COV_FILL_VERSION, compute_protocol_fingerprint)
        self.assertEqual(compute_protocol_fingerprint(cov_fill_version=COV_FILL_VERSION),
                         compute_protocol_fingerprint())


class TestSampleFingerprint(unittest.TestCase):
    def _pts(self, n):
        return [{"cutoff": f"2026-01-{i:02d} 00:00:00", "dir_ok": True}
                for i in range(1, n + 1)]

    def test_same_input_same_value(self):
        self.assertEqual(compute_sample_fingerprint(self._pts(5)),
                         compute_sample_fingerprint(self._pts(5)))

    def test_different_input_different_value(self):
        self.assertNotEqual(compute_sample_fingerprint(self._pts(5)),
                            compute_sample_fingerprint(self._pts(6)))


class TestComparabilityGuard(unittest.TestCase):
    def test_same_protocol_different_sample_comparable(self):
        from scripts.registry_lib import comparable
        self.assertTrue(comparable({"protocol_fingerprint": "a", "sample_fingerprint": "s1"},
                                   {"protocol_fingerprint": "a", "sample_fingerprint": "s2"}))

    def test_different_protocol_not_comparable(self):
        from scripts.registry_lib import comparable
        self.assertFalse(comparable({"protocol_fingerprint": "a"},
                                    {"protocol_fingerprint": "b"}))


if __name__ == "__main__":
    unittest.main()
```

创建 `tests/test_cov_fingerprint.py`：

```python
import unittest

import numpy as np

from task_FM.evaluations.fm_eval.evaluator import compute_cov_fingerprint


class TestCovFingerprint(unittest.TestCase):
    def _m(self):
        return np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    def test_same_input_same_value(self):
        self.assertEqual(
            compute_cov_fingerprint(self._m(), ["daily_slope", "ccl"])["matrix_sha256"],
            compute_cov_fingerprint(self._m(), ["daily_slope", "ccl"])["matrix_sha256"])

    def test_different_input_different_value(self):
        self.assertNotEqual(
            compute_cov_fingerprint(self._m(), ["a", "b"])["matrix_sha256"],
            compute_cov_fingerprint(self._m() * 2, ["a", "b"])["matrix_sha256"])

    def test_negative_zero_normalized(self):
        self.assertEqual(
            compute_cov_fingerprint(np.array([[-0.0]], dtype=np.float32), ["c"])["matrix_sha256"],
            compute_cov_fingerprint(np.array([[0.0]], dtype=np.float32), ["c"])["matrix_sha256"])

    def test_key_order_is_semantic(self):
        self.assertNotEqual(
            compute_cov_fingerprint(self._m(), ["a", "b"])["matrix_sha256"],
            compute_cov_fingerprint(self._m(), ["b", "a"])["matrix_sha256"])

    def test_inf_fails_loud(self):
        with self.assertRaises(ValueError):
            compute_cov_fingerprint(np.array([[np.inf]], dtype=np.float32), ["c"])

    def test_shape_and_version_reported(self):
        out = compute_cov_fingerprint(self._m(), ["daily_slope", "ccl"])
        self.assertEqual(out["n_channels"], 2)
        self.assertEqual(out["hash_version"], "cov_matrix_hash_v1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_protocol_fingerprint.py tests/test_cov_fingerprint.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'compute_protocol_fingerprint'`

- [ ] **Step 3: 实现三个指纹**

在 `evaluator.py` 的 `build_summary` 之前加（`import hashlib` 加到顶部）：

```python
PROTOCOL_FINGERPRINT_VERSION = "protocol_v1"
COV_MATRIX_HASH_VERSION = "cov_matrix_hash_v1"
COV_FILL_VERSION = "v2"      # 唯一来源改在此处（D4 语义变更）；Task 2 只做 bfill 修复并声明随本函数生效

def compute_protocol_fingerprint(metric_version="v1",
                                 cov_fill_version=COV_FILL_VERSION,
                                 eval_window_bars=None, step=None, horizon=None):
    """协议指纹：决定"两次评估是否可比"（W1.5）。

    只含**不随数据增长而改变**的不变量。样本量、cutoff 列表、
    数据截止时间**不**进入——它们属 sample_fingerprint。
    """
    from config import backtest_config
    parts = [
        PROTOCOL_FINGERPRINT_VERSION,
        f"metric={metric_version}",
        f"cov_fill={cov_fill_version}",
        f"window={eval_window_bars if eval_window_bars is not None else backtest_config.EVAL_WINDOW_BARS}",
        f"step={step if step is not None else backtest_config.STEP}",
        f"horizon={horizon if horizon is not None else backtest_config.HORIZON}",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def compute_sample_fingerprint(points):
    """样本指纹：本次评估实际用到的 cutoff 集合（随数据累积变化）。"""
    cutoffs = sorted(str(p.get("cutoff")) for p in (points or [])
                     if isinstance(p, dict) and p.get("cutoff") is not None)
    return hashlib.sha256("|".join(cutoffs).encode("utf-8")).hexdigest()


def compute_cov_fingerprint(matrix, keys):
    """协变量输入矩阵的规范哈希（C2 / §4.2 W2.1①）。

    规范序列化：键序**保留**（顺序即通道语义）、float32 小端、
    `-0.0` 归一、Inf fail-loud。
    """
    import numpy as _np
    arr = _np.asarray(matrix, dtype="<f4")
    if not _np.all(_np.isfinite(arr)):
        raise ValueError("cov matrix contains Inf/NaN payload — fail-loud")
    arr = _np.where(arr == 0.0, 0.0, arr)
    blob = b"|".join([COV_MATRIX_HASH_VERSION.encode()]
                     + [str(k).encode("utf-8") for k in keys]
                     + [arr.tobytes(order="C")])
    return {"keys": list(keys),
            "matrix_sha256": hashlib.sha256(blob).hexdigest(),
            "n_channels": len(list(keys)),
            "hash_version": COV_MATRIX_HASH_VERSION}
```

- [ ] **Step 4: `build_summary` 落三个指纹**

签名追加：

```python
def build_summary(s, cand, *, baseline_points=None, baseline_dir_acc=None,
                  batch_id=None, run_mode="exploration", points=None,
                  cov_matrix=None, cov_keys=None):
```

`out` dict 加：

```python
        "protocol_fingerprint": compute_protocol_fingerprint(),
        "sample_fingerprint": compute_sample_fingerprint(points or s.get("points")),
        "cov_fingerprint": (compute_cov_fingerprint(cov_matrix, cov_keys)
                            if cov_matrix is not None and cov_keys else None),
```

- [ ] **Step 5: 暴露 `hourly_model` 的输入矩阵（M2 接线）**

在 `cascade/hourly_model.py` 的 `HourlyModel` 类中加一个字段（与 `xreg_fallback` 同处，`:35` 一带）：

```python
    last_covariate_input: tuple = None   # (matrix, keys) 最近一次送入模型的输入
```

在 `:214-216` 构造 `past_future_covariates` 之后加：

```python
        self.last_covariate_input = (past_future_covariates, list(covariate_keys))
```

在 `:235` 的回退分支加：

```python
            self.last_covariate_input = None
```

- [ ] **Step 6: 接通两个调用点**

`scripts/aligned_slow_loop.py:154` 一带：

```python
            _ci = getattr(hourly_model, "last_covariate_input", None)
            v = build_summary(s, {"symbol": row["symbol"], "cov_override": row["cov_override"],
                                  "max_points": row["max_points"], "stage": "aligned"},
                              batch_id=bid, baseline_points=baseline_pts,
                              baseline_dir_acc=baseline_dir_acc,
                              points=s.get("points"),
                              cov_matrix=(_ci[0] if _ci else None),
                              cov_keys=(_ci[1] if _ci else None))
```

`task_FM/evaluations/fm_eval/run.py:114` 同样处理。

> **若 `hourly_model` 在该作用域不可得**：读 `aligned_slow_loop.py` 的 `_run_inner` 看清模型实例变量名（`_get_models()` 返回 `daily_model, hourly_model`），用真实变量名。

- [ ] **Step 7: 排名守卫（按真实结构，M7 修复）**

先读真实结构：

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && sed -n '684,730p' scripts/praxist_supervisor.py"
```

`materialize_known_verdicts`（`:667`）的结构是 `items = list(snapshot.values())` 后**逐品种**循环取 best dir_acc。**M3（复审修复）**：多品种×多协议下"当前协议的组"无定义，必须给出确定规则，且守卫要复用 `comparable()`。在 `items` 取出后插入：

```python
    # W1.5 守卫：跨协议指纹禁止直接比较/排名（不同协议的 dir_acc 不可比）。
    # 协议一致性判定 = protocol_fingerprint 字符串相等（即 registry_lib.comparable 的语义）。
    # comparable() 保留在 registry_lib 作公共谓词，供报告其他交叉比较调用——
    # 本守卫用字符串分组，是该谓词的等价实现，**不重复 import 而不用**。
    _proto_groups = {}
    for _v in items:
        _fp = _v.get("protocol_fingerprint")
        _proto_groups.setdefault(_fp, []).append(_v)
    # 主协议组（报表排序基准）：优先"含确认运行"的组，否则成员最多的组。
    # 其余协议组的 verdict 不进主排名，单独标注（不进"best dir_acc"）。
    _primary_fp = next(
        (fp for fp, g in _proto_groups.items()
         if any(str(_v.get("run_mode")) == "confirmation" for _v in g)),
        None)
    if _primary_fp is None and _proto_groups:
        _primary_fp = max(_proto_groups, key=lambda f: len(_proto_groups[f]))
    _items = sorted(_proto_groups.get(_primary_fp, items),
                    key=lambda v: str(v.get("symbol") or "").lower())
    _other_proto_count = len(_proto_groups) - (1 if _primary_fp is not None else 0)
```

> **改哪几处 `for v in items`（务必只改排名字段）**：`materialize_known_verdicts` 里有**多处** `for v in items`（实函数约 `:690`、`:753` `items[:20]`、`:808`）与 `_effective_clue_lines(items)`。本守卫只约束 **best dir_acc 排名循环**（`:690` 一带、逐品种取 best 的那处）——把它改为 `for v in _items:`。其余 `for v in items` 与 `_effective_clue_lines(items)` **保留用 `items`**（它们不排名，不受跨协议约束）。**若排名字段在实函数中有别，先读源码再定，不要机械替换全部 `for v in items`。**

> **让 `_other_proto_count` 有消费点**：在 `lines=[...]` 初始化（实函数 `:676` 一带，`items`/分组之后）追加一行分组标注，使其余协议组的数量可见：

```python
    lines.append(
        f"按协议指纹分组排名；另有 {_other_proto_count} 个协议组的 verdict 未进主排名。"
    )
```

> 若该位置执行时取不到 `_other_proto_count`（作用域问题），把分组逻辑整体移到 `lines` 初始化之前。**以实函数结构为准，先读再放。**

**同任务更新头部文案**：`materialize_known_verdicts` 头部（`lines` 首行，含 `(fdr_pass OR migrated_pass)` 文案）现仍是旧 pass 语义。**用 grep 定位真实行号**（不要猜）：

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && grep -n 'fdr_pass OR migrated_pass' scripts/praxist_supervisor.py"
```

改为：

```python
             "v2 pass (gate_pass=True AND fdr_pass=True AND p_value NOT NULL AND run_mode='confirmation'): already solved, do NOT re-propose.",
             "v1 legacy: pass by ev>0 (legacy econ caliber, schema=v1 entries only).",
             "hard-gate-but-losing (gate_pass=True but not statistically confirmed): 过硬门但未过统计检验; not a success; do not re-propose as solved.",
```

- [ ] **Step 8: schema 与 `comparable`**

`"protocol_fingerprint", "sample_fingerprint", "cov_fingerprint",` 加入 `VERDICT_FIELDS_V2` **与** `VERDICT_FIELDS_V2_NULLABLE`。

在 `registry_lib.py` 加：

```python
def comparable(a, b) -> bool:
    """可比性只由协议指纹决定（W1.5）。

    sample_fingerprint 不同属正常（前向数据累积），不构成拒绝比较的理由。
    """
    return a.get("protocol_fingerprint") == b.get("protocol_fingerprint")
```

- [ ] **Step 9: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_protocol_fingerprint.py tests/test_cov_fingerprint.py tests/test_fm_evaluator_gated.py tests/test_praxist_fm_evaluator.py tests/test_validation_criteria.py tests/test_supervisor.py -v"
```

Expected: 全 PASS。`test_supervisor.py` 是排名守卫与头部文案的检测点。

- [ ] **Step 10: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_protocol_fingerprint.py tests/test_cov_fingerprint.py task_FM/evaluations/fm_eval/evaluator.py cascade/hourly_model.py scripts/aligned_slow_loop.py task_FM/evaluations/fm_eval/run.py scripts/praxist_supervisor.py scripts/registry_lib.py && git commit -m 'feat(eval): 协议/样本/协变量矩阵指纹与接线 (E8/E9/C2)

三个指纹落地并接通两个 build_summary 调用点；
hourly_model 暴露 last_covariate_input 供矩阵哈希。
排名守卫按 materialize_known_verdicts 真实结构（逐品种循环）实现；
同步更新其头部 pass 文案。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 7: DM 显式状态机 + `covariates_used` + A1 完整性校验（E4/E6）

**Files:**
- Modify: `cascade/statistical_tests.py`（新增诊断函数）
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`（DM 接入、`covariates_used`、A1 校验）
- Modify: `scripts/registry_lib.py`（schema）
- Test: `tests/test_dm_status.py`、`tests/test_a1_completeness.py`（新建）

**Interfaces:**
- Produces: `statistical_tests.pair_dir_ok_series_with_diagnostics(variant_points, baseline_points, *, dm_min_common=50, effective_min_n=50, missingness_admissible=None, variant_protocol=None, baseline_protocol=None) -> dict`；`evaluator.a1_missing_fields(verdict) -> list`；verdict 键 `dm_status` 等 11 个 + `covariates_used`

**传输链（`covariates_used`，M1 修复）**：
```
hourly_model.predict() 的 xreg_fallback                        [hourly_model.py:35/219/236/257]
  → 回测把 covariates_used = not xreg_fallback 放进 point dict  [monthly_backtest.py]
  → summarize() 聚合（全点皆 True 才为 True）                    [monthly_backtest.py]
  → map_summary 映射                                             [evaluator.py]
  → build_summary out["covariates_used"]                         [evaluator.py]
```

> **关键前置（spec §4.1 W1.3 作用域标记）**：本任务**只交付状态机 + 字段落盘 + fail-loud 告警**。窗口对齐根因属 PR-A1、受 D5 阻断，**不在本任务内**。
> **预期行为**：PR-A1 前 `dm_status` 会频繁落 `insufficient_common`/`no_common_cutoff`——**fail-loud 设计行为，不是缺陷**。运维侧**禁止**过滤该 WARN。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_dm_status.py`：

```python
"""E6：DM 配对状态必须显式。7 状态 + 首个匹配者胜。

注意：cutoff 必须用**合法**日期。'2026-01-32' 之类会被
safe_normalize_cutoff 判为 None 并静默丢弃（实测确认）。
"""
import unittest

import pandas as pd

from cascade.statistical_tests import pair_dir_ok_series_with_diagnostics

DM_STATUSES = {"ok", "set_mismatch_ok", "set_mismatch_descriptive",
               "insufficient_common", "no_common_cutoff", "protocol_mismatch",
               "no_baseline"}


def _cutoffs(n):
    """n 个合法的小时级 cutoff（跨月自动进位）。"""
    return [t.strftime("%Y-%m-%d %H:%M:%S")
            for t in pd.date_range("2026-01-01", periods=n, freq="h")]


def _pts(n, ok=True):
    return [{"cutoff": c, "dir_ok": ok} for c in _cutoffs(n)]


class TestCutoffValidity(unittest.TestCase):
    def test_helpers_produce_valid_cutoffs(self):
        from cascade.statistical_tests import safe_normalize_cutoff
        for c in _cutoffs(60):
            self.assertIsNotNone(safe_normalize_cutoff(c), f"{c} 非法")


class TestPairingDiagnostics(unittest.TestCase):
    def test_identical_sets_yield_ok(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(
            pts, list(pts), missingness_admissible=True)
        self.assertEqual(d["dm_status"], "ok")
        self.assertEqual(d["dm_common_count"], 60)
        self.assertTrue(d["pairing_valid"])

    def test_tuple_input_compatible_with_dict(self):
        """C2：生产 point_dir_ok_list 是 (cutoff, dir_ok) 元组——必须与 dict 同识别。"""
        dicts = [{"cutoff": c, "dir_ok": True} for c in _cutoffs(60)]
        tuples = [(c, True) for c in _cutoffs(60)]
        a = pair_dir_ok_series_with_diagnostics(
            dicts, list(dicts), missingness_admissible=True)
        b = pair_dir_ok_series_with_diagnostics(
            tuples, list(dicts), missingness_admissible=True)
        self.assertEqual(a["dm_status"], b["dm_status"])
        self.assertEqual(a["dm_common_count"], b["dm_common_count"])
        self.assertEqual(a["dm_common_count"], 60)

    def test_variant_has_extra_cutoffs(self):
        v, b = _pts(7), _pts(5)
        d = pair_dir_ok_series_with_diagnostics(
            v, b, dm_min_common=5, effective_min_n=5, missingness_admissible=True)
        self.assertEqual(d["dm_common_count"], 5)
        self.assertEqual(d["dm_unmatched_variant"], 2)
        self.assertEqual(d["dm_unmatched_baseline"], 0)
        self.assertEqual(d["dm_status"], "set_mismatch_ok")

    def test_pair_set_hash_differs_from_raw(self):
        v, b = _pts(7), _pts(5)
        d = pair_dir_ok_series_with_diagnostics(
            v, b, dm_min_common=5, effective_min_n=5, missingness_admissible=True)
        self.assertNotEqual(d["pair_set_hash"], d["raw_cutoff_set_hash"])

    def test_no_common_cutoffs(self):
        v = [{"cutoff": _cutoffs(1)[0], "dir_ok": True}]
        b = [{"cutoff": "2027-06-01 00:00:00", "dir_ok": True}]
        d = pair_dir_ok_series_with_diagnostics(v, b)
        self.assertEqual(d["dm_status"], "no_common_cutoff")
        self.assertIsNone(d["pair_set_hash"])

    def test_insufficient_common(self):
        pts = _pts(3)
        d = pair_dir_ok_series_with_diagnostics(pts, list(pts))
        self.assertEqual(d["dm_status"], "insufficient_common")
        self.assertFalse(d["pairing_valid"])

    def test_no_baseline(self):
        d = pair_dir_ok_series_with_diagnostics(_pts(1), None)
        self.assertEqual(d["dm_status"], "no_baseline")


class TestProtocolMismatch(unittest.TestCase):
    def test_mismatch_short_circuits(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(
            pts, list(pts), variant_protocol="aaa", baseline_protocol="bbb")
        self.assertEqual(d["dm_status"], "protocol_mismatch")
        self.assertFalse(d["pairing_valid"])
        self.assertEqual(d["variant_series"], [])

    def test_unknown_protocol_does_not_false_positive(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(
            pts, list(pts), variant_protocol="aaa", baseline_protocol=None,
            missingness_admissible=True)
        self.assertEqual(d["dm_status"], "ok")


class TestMissingnessGate(unittest.TestCase):
    def test_not_admissible_blocks_pairing(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(
            pts, list(pts), missingness_admissible=False)
        self.assertEqual(d["dm_status"], "set_mismatch_descriptive")
        self.assertFalse(d["pairing_valid"])

    def test_default_is_not_admissible_before_spec_7_8(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(pts, list(pts))
        self.assertFalse(d["missingness_admissible"])


class TestMigratedPassBackdoor(unittest.TestCase):
    def _snap(self, **kw):
        base = {"schema": "fm.aligned_verdict.v2", "status": "ok",
                "gate_pass": True, "fdr_pass": True, "p_value": 0.01,
                "migrated_pass": None, "run_mode": "confirmation"}
        base.update(kw)
        return {"v1": base}

    def test_migrated_pass_alone_does_not_promote(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(pass_variants(
            self._snap(fdr_pass=None, p_value=None, migrated_pass=True)), [])

    def test_confirmation_with_fdr_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(len(pass_variants(self._snap())), 1)

    def test_missing_run_mode_does_not_promote(self):
        from scripts.registry_lib import pass_variants
        snap = self._snap()
        del snap["v1"]["run_mode"]
        self.assertEqual(pass_variants(snap), [])


if __name__ == "__main__":
    unittest.main()
```

创建 `tests/test_a1_completeness.py`：

```python
"""§1.2 A1：缺失 A1 字段的 verdict 不得进入成功判定。"""
import unittest


class TestA1Completeness(unittest.TestCase):
    def test_missing_fields_reported(self):
        from scripts.registry_lib import a1_missing_fields
        v = {"protocol_fingerprint": "a", "dir_acc": 0.5, "dm_status": "ok"}
        missing = a1_missing_fields(v)
        self.assertIn("covariates_used", missing)
        self.assertIn("run_mode", missing)

    def test_complete_verdict_has_no_missing(self):
        from scripts.registry_lib import a1_missing_fields, A1_REQUIRED_FIELDS
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        self.assertEqual(a1_missing_fields(v), [])

    def test_nullable_field_present_as_none_is_ok(self):
        from scripts.registry_lib import a1_missing_fields, A1_REQUIRED_FIELDS
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        v["run_label"] = None          # 豁免：确认运行事后写入
        v["baseline_dir_acc"] = None   # 豁免：无基线时本就 null
        self.assertEqual(a1_missing_fields(v), [])

    def test_non_nullable_field_as_none_is_incomplete(self):
        from scripts.registry_lib import a1_missing_fields, A1_REQUIRED_FIELDS
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        v["dm_status"] = None          # 非豁免 → 不完整
        self.assertIn("dm_status", a1_missing_fields(v))

    def test_covariates_used_reaches_verdict(self):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55, "point_dir_ok_list": [],
             "covariates_used": True}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand)
        self.assertIs(v["covariates_used"], True)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_dm_status.py tests/test_a1_completeness.py -v"
```

Expected: FAIL — `ImportError: cannot import name 'pair_dir_ok_series_with_diagnostics'`

- [ ] **Step 3: 实现诊断函数**

在 `cascade/statistical_tests.py` 的 `pair_dir_ok_series`（第 98-148 行）之后加：

```python
def pair_dir_ok_series_with_diagnostics(
    variant_points, baseline_points, *, dm_min_common: int = 50,
    effective_min_n: int = 50, missingness_admissible=None,
    variant_protocol=None, baseline_protocol=None,
):
    """共同 cutoff 配对 + 显式诊断（E6 / W1.5）。

    状态判定优先级（首个匹配者胜，v12 链）：
      no_baseline → protocol_mismatch → no_common_cutoff → insufficient_common
      → set_mismatch_descriptive → set_mismatch_ok → ok
    """
    import hashlib

    def _norm(pts):
        """归一化为 {cutoff_ts: dir_ok_bool}。

        生产传入的 `point_dir_ok_list` 是 [(cutoff, dir_ok)] **元组**（月
        `monthly_backtest.py:500` `summarize` 构造），必须与 dict 兼容——
        C2 复审修复：只认 dict 会在真实运行中静默丢弃全部点，恒落 no_common_cutoff。
        """
        m = {}
        for p in (pts or []):
            if isinstance(p, dict):
                ts = safe_normalize_cutoff(p.get("cutoff"))
                ok = p.get("dir_ok")
            elif isinstance(p, (tuple, list)) and len(p) >= 2:
                ts = safe_normalize_cutoff(p[0])
                ok = p[1]
            else:
                continue
            if ts is not None:
                m[ts] = bool(ok)
        return m

    if missingness_admissible is None:
        # §7.8 裁定前保守默认：不能证明缺失随机 → 不可接受
        missingness_admissible = False

    vm, bm = _norm(variant_points), _norm(baseline_points)

    def _base(**over):
        out = {"dm_common_count": 0, "dm_unmatched_variant": 0,
               "dm_unmatched_baseline": 0, "pair_set_hash": None,
               "raw_cutoff_set_hash": None, "pairing_valid": False,
               "missingness_admissible": bool(missingness_admissible),
               "d_series_n_eff": None, "d_bar_le_zero": None,
               "n_avail_variant": len(vm), "n_avail_baseline": len(bm),
               "variant_series": [], "baseline_series": []}
        out.update(over)
        return out

    if baseline_points is None:
        return _base(dm_status="no_baseline")

    # 优先级 2：协议不兼容 → 不进入配对（E6 静默错误比较的正面防线）。
    # 两侧都给出指纹时才判定；任一侧缺失视为"未知"，不误报 mismatch。
    if variant_protocol is not None and baseline_protocol is not None:
        if variant_protocol != baseline_protocol:
            return _base(dm_status="protocol_mismatch")

    common = sorted(vm.keys() & bm.keys())
    raw_hash = hashlib.sha256(
        "|".join(str(k) for k in sorted(vm.keys() | bm.keys())).encode()
    ).hexdigest()

    if not common:
        return _base(dm_status="no_common_cutoff", raw_cutoff_set_hash=raw_hash)

    pair_hash = hashlib.sha256(
        "|".join(str(k) for k in common).encode()).hexdigest()
    v_series = [float(vm[k]) for k in common]
    b_series = [float(bm[k]) for k in common]
    counts = {"dm_common_count": len(common),
              "dm_unmatched_variant": len(vm.keys() - bm.keys()),
              "dm_unmatched_baseline": len(bm.keys() - vm.keys()),
              "pair_set_hash": pair_hash, "raw_cutoff_set_hash": raw_hash,
              "variant_series": v_series, "baseline_series": b_series}

    if len(common) < dm_min_common:
        return _base(dm_status="insufficient_common", **counts)

    import numpy as _np
    d = _np.asarray(v_series) - _np.asarray(b_series)
    counts["d_bar_le_zero"] = bool(d.mean() <= 0)
    counts["d_series_n_eff"] = int(len(d))   # 名义值，实测口径见 PR-C1
    if counts["d_series_n_eff"] < effective_min_n:
        return _base(dm_status="insufficient_common", **counts)

    if not missingness_admissible:
        # 缺失不可接受 → 只作描述性。集合是否一致不改变该结论。
        return _base(dm_status="set_mismatch_descriptive", **counts)

    set_mismatch = bool(counts["dm_unmatched_variant"]
                        or counts["dm_unmatched_baseline"])
    return _base(dm_status="set_mismatch_ok" if set_mismatch else "ok",
                 pairing_valid=True, **counts)
```

- [ ] **Step 4: 接入 evaluator**

改 `evaluator.py:283-294` 的 DM 块：

```python
    p_value = None
    dm_diag = {"dm_status": "no_baseline", "dm_common_count": 0,
               "dm_unmatched_variant": 0, "dm_unmatched_baseline": 0,
               "pair_set_hash": None, "raw_cutoff_set_hash": None,
               "pairing_valid": False, "missingness_admissible": False,
               "d_series_n_eff": None, "d_bar_le_zero": None,
               "n_avail_variant": 0, "n_avail_baseline": 0}
    if (baseline_points is not None and
            pair_dir_ok_series_with_diagnostics is not None):
        point_dir_ok_list = s.get("point_dir_ok_list") or []
        try:
            _base_proto = next(
                (p.get("protocol_fingerprint") for p in baseline_points
                 if isinstance(p, dict) and p.get("protocol_fingerprint")), None)
            dm_diag = pair_dir_ok_series_with_diagnostics(
                point_dir_ok_list, baseline_points,
                variant_protocol=compute_protocol_fingerprint(),
                baseline_protocol=_base_proto)
            v_series, b_series = dm_diag["variant_series"], dm_diag["baseline_series"]
            if (dm_diag["dm_status"] not in ("protocol_mismatch", "no_baseline")
                    and len(v_series) >= 100 and diebold_mariano_p is not None):
                p_value = diebold_mariano_p(v_series, b_series)
        except Exception as e:
            print(f"[WARN] DM test failed: {e}", file=sys.stderr)
    if dm_diag["dm_status"] in ("insufficient_common", "no_common_cutoff",
                                "protocol_mismatch"):
        print(f"[WARN] dm_status={dm_diag['dm_status']} "
              f"common={dm_diag['dm_common_count']} — DM 不可用于确认",
              file=sys.stderr)
```

把 `dm_diag` 的**全部键**（**除** `variant_series`/`baseline_series`——那是中间产物，不得落 verdict）并入 `out` dict。

> **歧义裁定（Ambiguity Risks 之一）**：`pairing_valid` **不加入** `VERDICT_FIELDS_V2`（它不是 spec 的 A1 字段），但**照常并入 out**（额外键对 `validate_verdict_v2` 无害，它只查缺失）。这样 WARN 日志与 verdict 都有该值。

- [ ] **Step 5: `covariates_used` 传输链（M1 修复）**

**(a) `monthly_backtest.py`**：`predict` 返回对象含 `xreg_fallback`（`hourly_model.py:257`）。在逐点构造处加：

```python
        point["covariates_used"] = not bool(getattr(result, "xreg_fallback", False))
```

> 先读 `monthly_backtest.py` 中调用 `hourly_model.predict(...)` 的那段（`grep -n "hourly_model.predict" scripts/monthly_backtest.py`），确认返回对象的变量名与 `xreg_fallback` 可达性，再按真实名字写。

**(b) `summarize()`** 返回 dict 加：

```python
        "covariates_used": bool(all(p.get("covariates_used", False) for p in ok)),
```

**(c) `map_summary`** 加：

```python
        "covariates_used": bool(s.get("covariates_used", False)),
```

**(d) `build_summary`** 的 `out` dict 加：

```python
        "covariates_used": m["covariates_used"],
```

- [ ] **Step 6: A1 完整性校验**

> **为避免循环 import，`A1_REQUIRED_FIELDS` 与 `a1_missing_fields` 定义在 `registry_lib.py`**（`evaluator` 已 import `registry_lib`，反向会成环）。`evaluator` 从那里导入。**两个测试文件也从 `scripts.registry_lib` 导入。**

在 `scripts/registry_lib.py` 加：

```python
# §1.2 A1 必交付字段。缺失 → verdict 不完整，不得进入成功判定。
A1_REQUIRED_FIELDS = (
    "protocol_fingerprint", "cov_fingerprint", "dir_acc", "dir_acc_full",
    "dir_acc_ex_roll", "n_roll_excluded", "n_roll_ratio", "dm_status",
    "dm_common_count", "n_avail_variant", "n_avail_baseline",
    "missingness_admissible", "d_series_n_eff", "pair_set_hash",
    "covariates_used", "baseline_dir_acc", "run_mode", "run_label",
)

# 允许为 None 但**必须存在键**的 A1 字段：
#   run_label  —— 确认运行的标签由 W3.4 事后写入
#   cov_fingerprint / pair_set_hash / d_series_n_eff / baseline_dir_acc
#              —— 无基线或未传矩阵时本就为 null
A1_NULLABLE = frozenset({"run_label", "cov_fingerprint", "pair_set_hash",
                         "d_series_n_eff", "baseline_dir_acc"})


def a1_missing_fields(verdict) -> list:
    """§1.2：返回缺失或非法为空的 A1 字段名列表。"""
    missing = []
    for k in A1_REQUIRED_FIELDS:
        if k not in verdict:
            missing.append(k)              # 键缺失 —— 一律不完整
        elif verdict.get(k) is None and k not in A1_NULLABLE:
            missing.append(k)              # 非豁免字段取 None —— 不完整
    return missing
```

在 `pass_variants` 的 v2 分支改（**守卫放在晋升分支内**——只有本会晋升的 verdict 才查 A1，避免把 gate_pass=False 的非法 verdict 也纳入 A1 判定；这正是反射式回退，语义与 §1.2"A1 缺失不得进入成功判定"一致）：

```python
        if v.get("run_mode") not in RUN_MODES:
            continue
        if v.get("run_mode") == "exploration":
            continue
        if v.get("gate_pass") and v.get("fdr_pass") and v.get("p_value") is not None:
            if a1_missing_fields(v):
                continue            # §1.2 A1：缺失 A1 字段 → verdict 不完整，不得晋升
            out.append(v)
```

> **M1（复审修复）—— 三处 promote 夹具必须补 A1 字段**：守卫进晋升分支后，`test_run_mode_field.TestPassVariantsGuards._snap()`、`test_dm_status.TestMigratedPassBackdoor._snap()`、`test_verdict_registry.test_pass_variants_v2_needs_fdr` 三处**断言能晋升的夹具**当前只含最小字段（无 A1 其余 17 键）→ `a1_missing_fields` 返回非空 → 全 FAIL。**必须给这三处补全 A1 字段**。最小补法：在各自 `_snap()`/`_v2_complete` 的 base dict 加：

```python
            "dir_acc": 0.55, "dir_acc_full": 0.55, "dir_acc_ex_roll": 0.55,
            "n_roll_excluded": 0, "n_roll_ratio": 0.0,
            "dm_status": "ok", "dm_common_count": 50,
            "n_avail_variant": 50, "n_avail_baseline": 50,
            "missingness_admissible": False, "d_series_n_eff": 50,
            "pair_set_hash": "ph", "covariates_used": True,
            "baseline_dir_acc": 0.5, "protocol_fingerprint": "pf",
            "cov_fingerprint": None, "run_label": None,
```

> **`dir_acc` 必补**（C1/M1 复审修复，勿漏）：`A1_REQUIRED_FIELDS` 含 `dir_acc`，**非 NULLABLE、且键必须存在**。三处 `_snap` base 都没 `dir_acc`，不补则 `a1_missing_fields` 返回 `["dir_acc"]` → promote 测试必 FAIL。`_v2_complete`（`tests/test_verdict_registry.py:133`）已自带，不用改。

> 注意 `cov_fingerprint` 与 `baseline_dir_acc` 在 `A1_NULLABLE` 里，可传 `None`。**先跑一遍测试看真实报错再补**，不要照抄键名——以 `A1_REQUIRED_FIELDS` 实际内容为准。
>
> **"先绿后红再绿"窗口期（预期，勿误判回归）**：A1 守卫在 Task 7 生效，而 `test_run_mode_field.py`/`test_verdict_registry.py` 的夹具要到本步才补全 → **若这两个文件在本步之前跑失败，属预期**（守卫已生效而夹具未补），不是回归。执行者可先补夹具再跑，或接受这步前的红、在本步后转绿。

> **豁免清单必须与 §1.2 的 A1 定义一致**。若你认为该豁免过宽或过窄，**停下来报告**，不要自行放宽——放宽会让"不完整 verdict"重新流入成功判定。

> **测试导入调整**：`tests/test_a1_completeness.py` 与 `tests/test_dm_status.py` 中，凡引用 `a1_missing_fields`/`A1_REQUIRED_FIELDS` 处一律用 `from scripts.registry_lib import ...`，不要从 `evaluator` 导入。

- [ ] **Step 7: schema**

11 个 `dm_*` 键 + `covariates_used` 加入 `VERDICT_FIELDS_V2` **与** `VERDICT_FIELDS_V2_NULLABLE`：

```python
    "dm_status", "dm_common_count", "dm_unmatched_variant", "dm_unmatched_baseline",
    "pair_set_hash", "raw_cutoff_set_hash", "d_series_n_eff", "d_bar_le_zero",
    "n_avail_variant", "n_avail_baseline", "missingness_admissible",
    "covariates_used",
```

- [ ] **Step 8: 跑测试确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python -m pytest tests/test_dm_status.py tests/test_a1_completeness.py tests/test_statistical_tests.py tests/test_run_mode_field.py tests/test_verdict_registry.py -v && python -m pytest tests/ -m 'not slow' -q"
```

Expected: 全 PASS。`test_verdict_registry.py` 必在（schema 与 pass 语义都改了）。

- [ ] **Step 9: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add tests/test_dm_status.py tests/test_a1_completeness.py tests/test_run_mode_field.py tests/test_verdict_registry.py cascade/statistical_tests.py task_FM/evaluations/fm_eval/evaluator.py scripts/registry_lib.py scripts/monthly_backtest.py && git commit -m 'feat(eval): DM 状态机 + covariates_used + A1 完整性校验 (E4/E6)

7 状态首个匹配者胜；协议不兼容短路不算 p 值；共同 cutoff 诊断落盘。
covariates_used 从 xreg_fallback 贯通到 verdict（此前 A1 清单列了却无实现）。
A1 完整性校验落地，pass_variants 拒绝不完整 verdict。
同步 test_run_mode_field.py / test_verdict_registry.py 的 promote 夹具
（补 A1 字段，防 A1 守卫使其误报）。
PR-A1 前 dm_status 将频繁落 insufficient_common/no_common_cutoff，
此为 fail-loud 设计行为，禁止过滤该 WARN。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## Task 8: 阶段 1 出口核验（§8.1）

**Files:**
- Create: `docs/2026-09-27-stage1-verification.md`

**Interfaces:**
- Consumes: Task 1–7 全部产物
- Produces: 核验报告

> **核验目标（spec §8.1）**：取 **2–3 个品种**、**固定窗口与 cutoff**、**手算核对一小批预测点**，证明**对齐与基线配对正确**。产出是"对齐与配对可信"的证据，**不是研究结论**。

- [ ] **Step 1: 固定窗口跑小批次**

`monthly_backtest.py` **没有 `--symbol` 旗标**（`main()` 只认 `--summary`/`--cov-override`/`--combo`/`--full-signal`/`--clip-gap`/`--cache-interval`/`--max-points`/`--resume`/`--with-baseline`）。用位置参数或直接调 `run_symbol_backtest`：

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python - <<'PY'
from cascade.hourly_model import HourlyModel
from cascade.daily_model import DailyModel
import scripts.monthly_backtest as mb
dm = DailyModel(); hm = HourlyModel(shared_model=dm.model)
for sym in ('RB', 'I', 'M'):
    r = mb.run_symbol_backtest(sym, dm, hm, max_points=20)
    s = mb.summarize(r) if r else None
    if s:
        print(sym, {k: s.get(k) for k in
              ('n','n_eff','dir_acc','dir_acc_full','dir_acc_ex_roll',
               'n_roll_excluded','n_roll_ratio','covariates_used')})
PY"
```

> 先跑 `grep -n "def run_symbol_backtest" -A 12 scripts/monthly_backtest.py` 核对真实签名与返回结构，再按真实名字写脚本。

- [ ] **Step 2: 手算核对 3–5 个点**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python - <<'PY'
from data.data_store import DataStore
with DataStore('rb') as s:
    df = s.get_main_contract_1h(limit=99999)
print('adjustment_policy =', df.attrs.get('adjustment_policy'))
print(df[['dt','close_price','contract_code']].tail(30).to_string())
PY"
```

逐点核对：`base` == 该 cutoff 的 `close_price`；`delta_real` == `close_price[idx+HORIZON] - base`；`roll_in_horizon` == `contract_contract[idx+1:idx+HORIZON]` 是否有切换。

- [ ] **Step 3: 核对基线配对**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && source .venv/bin/activate && python - <<'PY'
import json
vp = [json.loads(l) for l in open('task_FM/config/baseline_points_rb_nocov.jsonl') if l.strip()]
print('nocov lines =', len(vp))
print('keys =', sorted(vp[0].keys()))
print('proto =', vp[0].get('protocol_fingerprint'))
PY"
```

核对：基线 cutoff 与变体 cutoff 的**交集大小** == verdict 的 `dm_common_count`。

- [ ] **Step 4: 写核验报告**

创建 `docs/2026-09-27-stage1-verification.md`，必须包含：

1. 三品种指标表（含 `dm_status`、`dm_common_count`、`covariates_used`）；
2. 手算核对表（5 点 × {base, delta_real, roll_in_horizon} 三方一致）；
3. 基线配对核对（交集 == `dm_common_count`；基线带 `protocol_fingerprint`）；
4. **`dm_status` 降级声明**：若为 `insufficient_common`/`no_common_cutoff`，说明是 PR-A1 未实施导致的窗口漂移，**属预期**，附 `n_avail_variant`/`n_avail_baseline`/`dm_common_count` 三数；
5. **`d_series_n_eff` 名义值声明**：阶段 1 它是 `int(len(d))`，**不是实测 ESS**（实测口径在 PR-C1）。**禁止**当实测有效样本量引用；
6. **`adjustment_policy` 声明**：经 `df.attrs` 传递；读到 `None` 说明该路径 attrs 已丢，需改显式返回值；
7. **旧基线作废声明**：Task 2 的 `cov_fill_version` bump 使全部 v1 期 verdict 与旧 ccl 基线**不可比**，已重新生成；
8. **`cov_fingerprint` 豁免声明**：探索运行传不齐 `cov_matrix`/`cov_keys` 时 `cov_fingerprint=null`——按 `A1_NULLABLE` 属 A1 完整豁免。**必须在报告中显式声明**，否则审计会质疑"规范把 `cov_fingerprint.matrix_sha256` 列为 A1，这里却放行 null"；
9. **`baseline_metrics.json` 键冲突声明**：ccl 与 nocov 基线经同一 `metrics[symbol]` 键互相覆盖，现阶段以 nocov 为准；
10. **`_primary_fp` 主协议组选择规则声明（待宿主追认）**：Task 6 的"优先含确认运行的组、否则成员最多组"是**本计划新增的裁定**，spec §4.1 W1.5 无对应条款。必须在报告中注明"此规则本计划新增、待宿主追认"，避免它以未标注状态固化成惯例；
11. 三项硬门逐条闭合判定（硬门 1 的 cutoff 部分**明确标注为 D5 阻断、未闭合**）。

- [ ] **Step 5: 提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /home/abug/timesfm && git add docs/2026-09-27-stage1-verification.md && git commit -m 'docs: 阶段 1 出口核验报告

固定窗口手算核对对齐与配对；记录 dm_status 分布、d_series_n_eff
名义值、旧基线作废与 PR-A1 阻断导致的预期降级。

Co-Authored-By: Claude Code <noreply@anthropic.com>'"
```

---

## 附录 A: PR-A1 阻断说明（不在本计划范围）

PR-A1 覆盖 cutoff 语义（D5）与 checkpoint 键改造（X7），**受 D5 裁定阻断**。其内容（D5 裁定后另立计划）：

1. **D5 二选一**：cutoff 改为该 bar 的**收盘**时间（`dt + 1h`），或维持现状并在 verdict 落 `cutoff_convention="bar_open"` + 量化 1-bar 偏差。
2. **checkpoint 键改造** `(symbol, idx)` → `(symbol, cutoff_ts)`，**必须同时改四处**：
   - 写：`scripts/monthly_backtest.py:444`
   - 读：`scripts/monthly_backtest.py:960`（`(rec["symbol"], int(rec["idx"]))`）
   - 读：`scripts/aligned_slow_loop.py:123`（`(str(rec.get("symbol","")).lower(), int(rec["idx"]))`——**与上一处写法不一致，仅因写入时已 lower 才碰巧一致**）
   - 跳过判断 + 恢复过滤：`scripts/monthly_backtest.py:298-305` 与 `:964`
3. **`eval_start` 奇偶漂移**：`scripts/monthly_backtest.py:259` 的 `max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)` 改为按绝对 cutoff 时间戳对齐。
4. **基线重生成**：PR-A1 落地后，Task 5 的 nocov 基线必须**重新生成**。

## 附录 B: 测试对 PR-A1 的依赖（防"D5 前绿、D5 后黄"）

| 测试 | 依赖 PR-A1 | 说明 |
|---|---|---|
| `test_run_mode_field.py` | 否 | 枚举、schema、构造器校验 |
| `test_bfill_causal.py` | 否 | 截断不变性 + 源码断言 |
| `test_roll_guard.py` | 否 | 合约序列比对；端到端传输链 |
| `test_backward_adjustment_reachable.py` | 否 | 策略枚举、docstring、attrs |
| `test_nocov_baseline.py` | **部分** | 文件名/行为不依赖；**Step 9 实跑行数 ≥ 100** 依赖当前 cutoff 约定，PR-A1 后需重跑 |
| `test_protocol_fingerprint.py` | 否 | 指纹自洽性 |
| `test_cov_fingerprint.py` | 否 | 纯本地哈希 |
| `test_dm_status.py` | **部分** | 诊断逻辑不依赖；**真实数据的 `dm_status` 分布**在 PR-A1 前后会变（预期行为） |
| `test_a1_completeness.py` | 否 | 字段存在性 |

## 附录 C: 阶段 2/3/4 的 plan

- **阶段 2**（PR-B1…B6，`[L2 诊断]`）：本计划完成后即可写。不受 D5 阻断。
- **阶段 3**（PR-C1…C6，`[L3 前置]`）：写前须确认 `meets_min_info`、确认检验损失定义、family 归属、样本量口径全部统一（§8.5 硬约束 4）。**另须收敛现有三套并存的 n_eff 估计量**：`evaluation_metrics.fallback_n_eff:377`（平方权重）、`evaluator.effective_sample_size:420`（线性 Bartlett + `residual_autocorr=0.9`）、DM 的 HAC（`statistical_tests.py:200-211`）。spec line 270 要求"唯一家、与 DM 共用同一估计量、禁止另写一套"——PR-C3 必须**收敛掉另外两套**，否则新实现变第四套。
- **阶段 4**（PR-D1/D2）：需 §7 开放问题 1（D5）与 7（目标效应与功效）**均已裁定**。

## 附录 D: `cov_fingerprint` 阶段边界 — 已裁定采 (a)

**问题**：`cov_fingerprint.matrix_sha256` 是 §1.2 的 A1 必交付字段，但 spec §8.2 把它放在 PR-B1（阶段 2）。若按原切分，阶段 1 出关时该字段仍是 A1 不完整，且 Global Constraints 的 A1 清单会与本阶段实际交付**自相矛盾**。

**裁定：采 (a)——前移进阶段 1**。理由：计算协变量矩阵 sha256 是**纯本地哈希**，无模型依赖、无 D5 依赖，工程量与 Task 6 其余部分同量级。

**落地**：Task 6 已含 `compute_cov_fingerprint` + 接线步骤（`hourly_model.last_covariate_input` → 两个调用点）+ `tests/test_cov_fingerprint.py`。

**若改回 (b)**：必须同步从 Global Constraints 的 A1 清单移除该字段，并在 Task 8 报告模板中预置"硬门 3 部分闭合"声明。
