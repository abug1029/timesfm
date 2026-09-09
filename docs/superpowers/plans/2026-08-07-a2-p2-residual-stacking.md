# A2-P2 残差叠加架构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 LGBM 学习 TimesFM 纯预测的残差（`Y_residual = Y_actual - timesfm_pure_pred`），把 LGBM 残差预测叠加到 TimesFM 基线上，检验"残差叠加"能否在 5 个最接近 GO 的品种上击败 Scheme。

**Architecture:** 复用 A2-P1 全部硬化基础设施（RunConfig、单写入锁、fail-closed 报告、manifest）。不重新计算 TimesFM 特征--`timesfm_pure_pred` 已在 dense matrix 中。Worker 新增 `--mode residual`：训练目标从 `Y` 改为 `Y_residual`，最终预测 `= timesfm_pure_pred + lgbm_residual_pred`。三曲线对比：pure / scheme / stacked。

**Tech Stack:** Python 3.11、pandas、NumPy、LightGBM、SQLite（只读）；共享 TimesFM venv（CPU-only）；不重新加载 TimesFM 模型（复用缓存）。

## 门禁上下文（执行前必读）

- A2-P1 全量：20/20 NO-GO（真实 tick size 修正后）
- A2-P1.1 三项修复（Early Stopping CV、sqrt 权重、hour sin/cos）：0/5 GO
- 按用户预设门槛"≥2/5 GO 才启动 A2-P2"，**A2-P1.1 未达标**
- 本计划供用户审核，**执行前必须获得用户明确批准**
- A2-P2 目标品种：FG、TA、BU、AO、UR（与 A2-P1.1 相同，已知最接近 GO）

## Global Constraints

- 不重新计算 TimesFM 特征；复用 `reports/a2_p1_features/<symbol>_tsfm.jsonl` 和 `_market.parquet` 缓存。
- 不修改 A2-P1/A2-P1.1 的任何结果文件；A2-P2 输出隔离到 `reports/a2_p2_results/` 和 `reports/a2_p2_logs/`。
- 复用 A2-P1 的 `RunConfig`、`exclusive_result_lock`、`append_unique_record`、`validate_jsonl_records`、`validate_run_results`、`build_manifest`。
- 同一结果 JSONL 单写入者；锁失败 `sys.exit(1)` 不加载模型。
- 报告 fail-closed：任何品种校验失败不写报告。
- `TICK_SIZES` 来自 `config.backtest_config`，缺失抛 `RuntimeError`，不回退 1.0。
- 随机种子用 `stable_symbol_seed`（SHA256），LGBM `random_state=seed`。
- Scheme 异常三态（`scheme_ok` None/True/False），不伪装 `0.0`。
- 5 种终态：DONE/SKIP/FAILED/TIMEOUT/INVALID。
- 不启动 A2-P3，需用户另行批准。
- 任何真实回测启动前必须通知用户并获批准（项目记忆 [[notify-before-backtest-start]]）。

---

## 文件结构与职责

| 文件 | 职责 | 变更 |
|---|---|---|
| `scripts/a2_p1_runtime.py` | RunConfig 增加 `a2-p2` run_id | 修改 |
| `scripts/a2_p2_worker.py` | 残差模式 Worker（复用 A2-P1 Worker 大部分逻辑） | 新建 |
| `scripts/a2_p2_orchestrator.py` | A2-P2 编排器（复用 A2-P1 Orchestrator 框架） | 新建 |
| `scripts/a2_p2_generate_report.py` | 三曲线报告（pure/scheme/stacked） | 新建 |
| `tests/test_a2_p2_integrity.py` | A2-P2 专属测试 | 新建 |
| `docs/runbook.md` | A2-P2 工具说明 | 修改 |
| `STATE.md` | A2-P2 状态 | 修改 |
| `reports/research/20260807_a2_p2_verdict.md` | 最终裁决报告 | 生成 |

---

### Task 1: RunConfig 增加 a2-p2 run_id

**Files:**
- Modify: `scripts/a2_p1_runtime.py`（`RunConfig.for_run` 类方法）
- Test: `tests/test_a2_p2_integrity.py`（新建）

**Interfaces:**
- Produces: `RunConfig.for_run("a2-p2", symbols, root)` 返回 `results_dir=root/reports/a2_p2_results`、`logs_dir=root/reports/a2_p2_logs`、`report_path=root/reports/research/20260807_a2_p2_verdict.md`、`features_dir=root/reports/a2_p1_features`（共享缓存）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_a2_p2_integrity.py
from pathlib import Path
from scripts.a2_p1_runtime import RunConfig


def test_run_config_a2_p2_paths():
    root = Path("D:/FlyBuddy/fm_a")
    cfg = RunConfig.for_run("a2-p2", ["fg"], root)
    assert cfg.results_dir == root / "reports/a2_p2_results"
    assert cfg.logs_dir == root / "reports/a2_p2_logs"
    assert cfg.report_path == root / "reports/research/20260807_a2_p2_verdict.md"
    assert cfg.features_dir == root / "reports/a2_p1_features"
    assert cfg.results_dir != RunConfig.for_run("a2-p1", ["fg"], root).results_dir
    assert cfg.results_dir != RunConfig.for_run("a2-p1.1", ["fg"], root).results_dir


def test_run_config_a2_p2_features_dir_shared_with_a2_p1():
    root = Path("D:/FlyBuddy/fm_a")
    p2 = RunConfig.for_run("a2-p2", ["fg"], root)
    p1 = RunConfig.for_run("a2-p1", ["fg"], root)
    assert p2.features_dir == p1.features_dir  # 共享 TimesFM 缓存
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py -q`
Expected: `ValueError: unsupported run_id: a2-p2`

- [ ] **Step 3: 在 `RunConfig.for_run` 增加 a2-p2 分支**

在 `scripts/a2_p1_runtime.py` 的 `for_run` 类方法中，`a2-p1.1` 分支后增加：

```python
elif run_id == "a2-p2":
    suffix = "a2_p2"
    report = root / "reports/research/20260807_a2_p2_verdict.md"
```

注意 `features_dir` 保持 `root / "reports/a2_p1_features"`（所有 run_id 共享，已在现有代码中处理）。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/a2_p1_runtime.py tests/test_a2_p2_integrity.py
git commit -m "feat(a2-p2): RunConfig 增加 a2-p2 run_id"
```

---

### Task 2: 残差目标计算与 dense matrix 复用验证

**Files:**
- Modify: `scripts/a2_p2_worker.py`（新建，从 `a2_p1_worker.py` 派生）
- Test: `tests/test_a2_p2_integrity.py`

**Interfaces:**
- Produces: `compute_residual_target(dense_matrix) -> pd.DataFrame`，新增列 `Y_residual = Y - timesfm_pure_pred`。
- Produces: `stack_predictions(timesfm_pure_pred, lgbm_residual_pred) -> np.ndarray`，返回 `timesfm_pure_pred + lgbm_residual_pred`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_a2_p2_integrity.py（追加）
import numpy as np
import pandas as pd
from scripts.a2_p2_worker import compute_residual_target, stack_predictions


def test_residual_target_is_actual_minus_pure_pred():
    df = pd.DataFrame({
        "Y": [0.10, -0.05, 0.0],
        "timesfm_pure_pred": [0.04, -0.02, 0.01],
    })
    out = compute_residual_target(df)
    assert "Y_residual" in out.columns
    np.testing.assert_allclose(out["Y_residual"].values, [0.06, -0.03, -0.01])


def test_residual_target_handles_nan_pure_pred():
    df = pd.DataFrame({
        "Y": [0.10, 0.05],
        "timesfm_pure_pred": [np.nan, 0.02],
    })
    out = compute_residual_target(df)
    # NaN pure_pred -> residual 为 NaN，训练时由 LGBM 原生处理
    assert np.isnan(out["Y_residual"].iloc[0])
    np.testing.assert_allclose(out["Y_residual"].iloc[1], 0.03)


def test_stack_predictions_adds_residual_to_base():
    base = np.array([0.04, -0.02, 0.01])
    residual = np.array([0.01, 0.005, -0.002])
    stacked = stack_predictions(base, residual)
    np.testing.assert_allclose(stacked, [0.05, -0.015, 0.008])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py -q`
Expected: `ModuleNotFoundError: No module named 'scripts.a2_p2_worker'`

- [ ] **Step 3: 创建 `scripts/a2_p2_worker.py` 实现残差目标与堆叠函数**

```python
# scripts/a2_p2_worker.py
"""A2-P2 残差叠加 Worker：LGBM 学习 TimesFM 残差，叠加到基线预测。"""
from __future__ import annotations
import numpy as np
import pandas as pd


def compute_residual_target(dense_matrix: pd.DataFrame) -> pd.DataFrame:
    """计算残差目标 Y_residual = Y - timesfm_pure_pred。

    timesfm_pure_pred 为 NaN 时 Y_residual 也为 NaN，由 LGBM use_missing 原生处理。
    """
    out = dense_matrix.copy()
    out["Y_residual"] = out["Y"] - out["timesfm_pure_pred"]
    return out


def stack_predictions(timesfm_pure_pred: np.ndarray, lgbm_residual_pred: np.ndarray) -> np.ndarray:
    """堆叠预测 = TimesFM 基线 + LGBM 残差校正。"""
    return timesfm_pure_pred + lgbm_residual_pred
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/a2_p2_worker.py tests/test_a2_p2_integrity.py
git commit -m "feat(a2-p2): 残差目标计算与堆叠预测函数"
```

---

### Task 3: Worker 残差训练与堆叠预测主循环

**Files:**
- Modify: `scripts/a2_p2_worker.py`（追加主循环）
- Modify: `scripts/a2_p1_lgbm_baseline.py`（`train_lgbm_walkforward` 增加可选 `target_col` 参数）
- Test: `tests/test_a2_p2_integrity.py`

**Interfaces:**
- Consumes: `train_lgbm_walkforward(dense_matrix, eval_bar_indices, refit_every, random_state, target_col="Y")` -- 新增 `target_col` 参数，默认 `"Y"` 保持 A2-P1 向后兼容。
- Produces: `run_worker(symbol, dense_step, refit_every, dry_run, run_id="a2-p2")` -- A2-P2 Worker 主函数，输出 `reports/a2_p2_results/<symbol>.jsonl`，每行含 `stacked_pred_move`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_a2_p2_integrity.py（追加）
import inspect
from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward


def test_train_lgbm_walkforward_accepts_target_col():
    sig = inspect.signature(train_lgbm_walkforward)
    assert "target_col" in sig.parameters
    assert sig.parameters["target_col"].default == "Y"


def test_a2_p2_worker_main_exists():
    from scripts.a2_p2_worker import run_worker
    assert callable(run_worker)


def test_a2_p2_worker_uses_residual_target_in_source():
    import pathlib
    src = pathlib.Path("scripts/a2_p2_worker.py").read_text(encoding="utf-8")
    assert "compute_residual_target" in src
    assert "stack_predictions" in src
    assert "target_col" in src
    assert "stacked_pred_move" in src
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py -q`
Expected: 失败（`target_col` 参数不存在、`run_worker` 不存在）

- [ ] **Step 3: 修改 `train_lgbm_walkforward` 增加 `target_col` 参数**

在 `scripts/a2_p1_lgbm_baseline.py` 的 `train_lgbm_walkforward` 函数：

```python
def train_lgbm_walkforward(
    dense_matrix: pd.DataFrame,
    eval_bar_indices: list,
    refit_every: int = 10,
    random_state=None,
    target_col: str = "Y",  # 新增：A2-P2 残差模式用 "Y_residual"
) -> pd.DataFrame:
```

函数体内把所有 `train_df["Y"]` 替换为 `train_df[target_col]`，`mat["Y"]` 替换为 `mat[target_col]`。具体位置：
- 训练目标：`y_train = train_df[target_col].values.astype(float)`
- actual_move 还原：保持用 `"Y"`（actual 是真实收益，不是残差）

注意 `actual_move` 仍用 `Y`，因为评估时对比的是真实价格变动，不是残差。

- [ ] **Step 4: 实现 `run_worker` 主循环**

在 `scripts/a2_p2_worker.py` 追加，从 `a2_p1_worker.py` 的 `run_worker` 派生，关键差异：
1. `run_id="a2-p2"` 默认
2. 调 `compute_residual_target(mat)` 增加 `Y_residual` 列
3. `train_lgbm_walkforward(mat, all_eval_bars, refit_every=refit_every, random_state=seed, target_col="Y_residual")`
4. 逐 bar 评估时：
   - `pure_pred_move = timesfm_pure_pred * base_price`（与 A2-P1 相同）
   - `lgbm_residual_pred = lgbm_preds.get(t0, 0.0)`（LGBM 预测的是残差）
   - `stacked_pred_return = timesfm_pure_pred + lgbm_residual_pred`
   - `stacked_pred_move = stacked_pred_return * base_price`
   - `scheme_pred_move`（与 A2-P1 相同，Scheme 三态）
5. JSONL 记录字段：`bar_idx, pure_pred_move, scheme_pred_move, stacked_pred_move, lgbm_residual_pred_move, actual_move, base_price, atr, run_id, symbol, version, seed, scheme_ok, scheme_error`
6. 复用 `exclusive_result_lock`、`append_unique_record`、`stable_symbol_seed`
7. 复用 A2-P1 的 `features_dir` 缓存（`_tsfm.jsonl` 和 `_market.parquet`）

- [ ] **Step 5: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q`
Expected: 全部 PASS（A2-P1 回归不破坏）

- [ ] **Step 6: Commit**

```bash
git add scripts/a2_p2_worker.py scripts/a2_p1_lgbm_baseline.py tests/test_a2_p2_integrity.py
git commit -m "feat(a2-p2): Worker 残差训练与堆叠预测主循环"
```

---

### Task 4: A2-P2 编排器与三曲线报告生成器

**Files:**
- Create: `scripts/a2_p2_orchestrator.py`
- Create: `scripts/a2_p2_generate_report.py`
- Test: `tests/test_a2_p2_integrity.py`

**Interfaces:**
- Produces: `run_orchestrator(symbols, force, run_id="a2-p2")` -- 复用 A2-P1 Orchestrator 的锁、timeout、5 种终态、manifest 逻辑，调用 `a2_p2_worker.py`。
- Produces: `generate_report(config: RunConfig)` -- 三曲线对比（pure/scheme/stacked），gate 条件：`stacked PF > scheme PF AND stacked EV > 0 AND CI(stacked - scheme) > 0`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_a2_p2_integrity.py（追加）
def test_a2_p2_orchestrator_uses_run_level_lock():
    import pathlib
    src = pathlib.Path("scripts/a2_p2_orchestrator.py").read_text(encoding="utf-8")
    assert "exclusive_result_lock" in src
    assert "a2-p2" in src
    assert "--run-id" in src or 'run_id="a2-p2"' in src


def test_a2_p2_report_gate_uses_stacked_vs_scheme():
    import pathlib
    src = pathlib.Path("scripts/a2_p2_generate_report.py").read_text(encoding="utf-8")
    assert "stacked_pred_move" in src
    assert "evaluate_gate" in src or "stacked" in src.lower()
    assert "--run-id" in src
    assert "a2-p2" in src


def test_a2_p2_report_fail_closed_on_missing_symbol(tmp_path):
    # 复用 A2-P1 的 fail-closed 模式：缺 symbol 时不写报告
    from scripts.a2_p1_runtime import RunConfig
    from scripts.a2_p2_generate_report import generate_report
    import pytest
    cfg = RunConfig.for_run("a2-p2", ["fg"], tmp_path)
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    # 不写任何 JSONL
    with pytest.raises(RuntimeError):
        generate_report(cfg)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py -q`
Expected: 失败（orchestrator/report 模块不存在）

- [ ] **Step 3: 创建 `scripts/a2_p2_orchestrator.py`**

从 `a2_p1_orchestrator.py` 派生，关键差异：
- `run_id` 默认 `"a2-p2"`
- 调用 `a2_p2_worker.py` 而非 `a2_p1_worker.py`
- manifest 输出到 `reports/research/a2-p2.manifest.json`
- 报告生成调用 `a2_p2_generate_report.py --run-id a2-p2`

其余（运行级锁、`subprocess.TimeoutExpired` 捕获、5 种终态、报告前置校验）完全复用 A2-P1 逻辑。

- [ ] **Step 4: 创建 `scripts/a2_p2_generate_report.py`**

从 `a2_p1_generate_report.py` 派生，关键差异：
- 读取 `stacked_pred_move` 列作为 LGBM 曲线（替代 `lgbm_pred_move`）
- gate 比较：`stacked PF > scheme PF AND stacked EV > 0 AND CI(stacked_pnl - scheme_pnl) > 0`
- 报告表格列：`品种 | gate | stacked PF | scheme PF | pure PF | stacked EV | CI下界 | n | tick`
- 报告路径：`reports/research/20260807_a2_p2_verdict.md`
- 复用 `validate_run_results`、`TICK_SIZES`、`evaluate_gate`、原子写入

- [ ] **Step 5: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/a2_p2_orchestrator.py scripts/a2_p2_generate_report.py tests/test_a2_p2_integrity.py
git commit -m "feat(a2-p2): 编排器与三曲线报告生成器"
```

---

### Task 5: 5 品种定向执行与裁决（需用户批准）

**Files:**
- Run: `scripts/a2_p2_orchestrator.py`
- Generate: `reports/research/20260807_a2_p2_verdict.md`

**⚠️ 用户批准门禁：本 Task 启动前必须获得用户明确批准。**

- [ ] **Step 1: 通知用户并获批准**

向用户说明：
- 目标品种：FG、TA、BU、AO、UR
- 预计耗时：每品种 ~70 分钟（含冷启动），5 品种 ~6 小时
- 不重新计算 TimesFM（复用缓存），只训练 LGBM 残差
- 门禁：≥2/5 GO 则残差架构有潜力；<2/5 GO 则关闭 Track B

- [ ] **Step 2: 启动编排器（获批准后）**

```bash
cd D:/FlyBuddy/fm_a
nohup D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -u scripts/a2_p2_orchestrator.py fg ta bu ao ur --run-id a2-p2 > reports/a2_p2_orchestrator.log 2>&1 &
```

- [ ] **Step 3: 巡检进度**

```bash
wc -l reports/a2_p2_results/*.jsonl
tail -5 reports/a2_p2_logs/<symbol>.log
```

- [ ] **Step 4: 生成裁决报告**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe scripts/a2_p2_generate_report.py --run-id a2-p2
```

- [ ] **Step 5: 记录裁决**

在 `reports/research/20260807_a2_p2_verdict.md` 末尾追加：
- GO 数量
- 是否满足 ≥2/5 GO 门槛
- 是否启动 A2-P3（需用户另行批准）

- [ ] **Step 6: Commit**

```bash
git add reports/a2_p2_results/ reports/a2_p2_logs/ reports/research/20260807_a2_p2_verdict.md reports/research/a2-p2.manifest.json
git commit -m "data(a2-p2): 5 品种残差叠加裁决"
```

---

### Task 6: 文档与回归门禁

**Files:**
- Modify: `docs/runbook.md`
- Modify: `STATE.md`
- Modify: `docs/README.md`
- Test: `tests/test_a2_p2_integrity.py`, `tests/test_a2_p1_integrity.py`, `tests/test_a2_p1_runtime.py`

- [ ] **Step 1: 更新 `docs/runbook.md`**

新增 "A2-P2 残差叠加" 章节：
```bash
# 运行 5 品种（需用户批准）
python scripts/a2_p2_orchestrator.py fg ta bu ao ur --run-id a2-p2
# 生成裁决报告
python scripts/a2_p2_generate_report.py --run-id a2-p2
```

- [ ] **Step 2: 更新 `STATE.md`**

"A2-P1 通用 LGBM 门禁" 章节后新增 "A2-P2 残差叠加" 章节，记录：
- 5 品种裁决结果
- 是否满足 ≥2/5 GO 门槛
- A2-P3 未启动，需用户批准

- [ ] **Step 3: 运行完整回归测试**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p2_integrity.py tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -v
```

Expected: 全部 PASS（A2-P1 + A2-P2 无回归）

- [ ] **Step 4: 编译检查**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m py_compile scripts/a2_p2_worker.py scripts/a2_p2_orchestrator.py scripts/a2_p2_generate_report.py scripts/a2_p1_runtime.py scripts/a2_p1_lgbm_baseline.py
```

- [ ] **Step 5: Commit**

```bash
git add docs/runbook.md STATE.md docs/README.md
git commit -m "docs(a2-p2): 文档与回归门禁"
```

---

## Self-Review

### Spec coverage

- 残差叠加架构：Task 2（残差目标）+ Task 3（Worker 残差训练 + 堆叠预测）
- 复用 A2-P1 基础设施：Task 1（RunConfig）+ Task 3（锁/幂等/种子）+ Task 4（fail-closed 报告）
- 5 品种定向执行：Task 5（用户批准门禁 + 编排器 + 裁决）
- 文档与回归：Task 6
- 不重新计算 TimesFM：Task 1 共享 `features_dir` + Task 3 复用缓存

### Plan completeness scan

所有实现任务提供具体文件、接口、测试代码和命令。Task 5 的执行步骤因依赖用户批准而包含明确门禁说明，非占位符。

### Type consistency

- `RunConfig.for_run("a2-p2", ...)` 在 Task 1 定义，Task 4/5 使用
- `compute_residual_target(df) -> df` 在 Task 2 定义，Task 3 使用
- `stack_predictions(base, residual) -> ndarray` 在 Task 2 定义，Task 3 使用
- `train_lgbm_walkforward(..., target_col="Y")` 在 Task 3 定义，默认 `"Y"` 保持 A2-P1 向后兼容
- `stacked_pred_move` 字段在 Task 3 定义，Task 4 报告读取

### Scope boundary

本计划只实现残差叠加架构。不包含：
- 新特征工程（复用 A2-P1 的 13 维）
- 新模型（仍是 LightGBM）
- A2-P3（需用户另行批准）
- 全量 20 品种（只跑 5 个最接近 GO 的）

---

## 执行选择

**Plan complete and saved to `docs/superpowers/plans/2026-08-07-a2-p2-residual-stacking.md`. Two execution options:**

**1. Subagent-Driven（推荐）** - 每个 Task 派生新子代理，任务间独立复核

**2. Inline Execution** - 本会话按任务批次执行

**Which approach?**

注意：Task 5（5 品种定向执行）无论选哪种方式，启动前都必须获得用户明确批准。
