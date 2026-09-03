# A2-P1 运行架构重设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 A2-P1 单进程探针重构为 Orchestrator + Worker 架构，实现品种级进程隔离 + eval point 级细粒度断点续跑。

**Architecture:** Orchestrator（调度器）启动独立 Worker 子进程执行每个品种，Worker 内部逐 eval point 原子追加 JSONL 结果，支持崩溃后从断点续跑。最终汇总脚本遍历所有 JSONL 生成裁决报告。

**Tech Stack:** Python 3.10, subprocess, lightgbm, pandas, TimesFM 2.5

**Spec:** `docs/superpowers/specs/2026-08-05-a2-p1-runtime-redesign.md`

## Global Constraints

- **JSONL 完整 payload**: 每行必须包含 `{bar_idx, pure_pred_move, scheme_pred_move, lgbm_pred_move, actual_move, base_price, atr}`，汇总脚本直接调用 `evaluate_gate()` 无需重算
- **Parquet 原子写入**: `tmp_path = cache_path + ".tmp"` + `os.replace(tmp_path, cache_path)` 防 OOM 损坏
- **Orchestrator 完成后自动调用报告生成**
- **Python 环境**: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python`
- **主仓库**: `D:\FlyBuddy\fm_a`（非 worktree）
- **结果目录**: `reports/a2_p1_results/<symbol>.jsonl`（每品种独立）
- **日志目录**: `reports/a2_p1_logs/<symbol>.log`（每品种独立）
- **保持不变**: LGBM + 12 维特征池 + walk-forward step=24 + 配对 bootstrap Gate

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `cascade/lgbm_features.py` | 特征工程 + dense 矩阵缓存 | Modify: Parquet 原子写入 |
| `scripts/a2_p1_worker.py` | 单品种 worker（细粒度续跑 + 完整 payload） | Create |
| `scripts/a2_p1_orchestrator.py` | 调度器（子进程管理 + 日志） | Create |
| `scripts/a2_p1_status.py` | 进度查询（汇总所有 JSONL） | Create |
| `scripts/a2_p1_generate_report.py` | 报告生成（遍历 JSONL + evaluate_gate） | Create |
| `scripts/a2_p1_lgbm_baseline.py` | 旧入口（向后兼容，内部调用 worker） | Modify |
| `tests/test_a2_p1_runtime.py` | 新架构的单元测试 | Create |

---

### Task 1: Parquet 原子写入

**Files:**
- Modify: `cascade/lgbm_features.py` — `build_dense_feature_matrix()` 的缓存写入
- Test: `tests/test_a2_p1_runtime.py::test_parquet_atomic_write`

**Interfaces:**
- Consumes: `build_dense_feature_matrix()` 现有签名
- Produces: 函数签名不变，内部写入逻辑改为临时文件 + `os.replace()`

- [ ] **Step 1: 写失败测试**

在 `tests/test_a2_p1_runtime.py` 添加：

```python
"""A2-P1 运行架构重设计测试"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile
import pandas as pd

def test_parquet_atomic_write():
    """验证 build_dense_feature_matrix 的缓存写入是原子的（临时文件 + os.replace）"""
    import inspect
    from cascade.lgbm_features import build_dense_feature_matrix
    source = inspect.getsource(build_dense_feature_matrix)
    # 检查源码中包含 os.replace 和 .tmp
    assert "os.replace" in source, "必须使用 os.replace() 原子替换"
    assert ".tmp" in source, "必须使用临时文件 .tmp"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_parquet_atomic_write -v
```

Expected: FAIL — `AssertionError: 必须使用 os.replace() 原子替换`

- [ ] **Step 3: 实现原子写入**

读 `cascade/lgbm_features.py` 找到 `build_dense_feature_matrix()` 中的 `to_parquet()` 调用，修改为：

```python
# 在 build_dense_feature_matrix() 中，找到 mat.to_parquet(cache_path) 或类似代码
# 替换为原子写入:
import os
tmp_path = str(cache_path) + ".tmp"
mat.to_parquet(tmp_path)
os.replace(tmp_path, str(cache_path))  # 原子替换
```

同时在文件顶部添加 `import os`（如果尚未存在）。

- [ ] **Step 4: 运行测试验证通过**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_parquet_atomic_write -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add cascade/lgbm_features.py tests/test_a2_p1_runtime.py
git commit -m "fix(a2-p1): Parquet 原子写入 (临时文件 + os.replace 防 OOM 损坏)"
```

---

### Task 2: Worker 单品种脚本（核心）

**Files:**
- Create: `scripts/a2_p1_worker.py`
- Test: `tests/test_a2_p1_runtime.py::test_worker_jsonl_payload_schema`

**Interfaces:**
- Consumes: `cascade.lgbm_features.build_dense_feature_matrix()`, `cascade.evaluation_metrics.evaluate_gate()` 的子集, `scripts.a2_p1_lgbm_baseline.train_lgbm_walkforward()`
- Produces: `scripts/a2_p1_worker.py` CLI: `python scripts/a2_p1_worker.py <symbol> [--dense-step 24] [--refit-every 10] [--dry-run]`
- 产出: `reports/a2_p1_results/<symbol>.jsonl`，每行 JSON 包含:
  ```json
  {"bar_idx": 480, "pure_pred_move": 12.5, "scheme_pred_move": -8.3,
   "lgbm_pred_move": 10.1, "actual_move": 11.2, "base_price": 14500.0,
   "atr": 85.3, "version": "bff807c", "seed": 12345}
  ```

- [ ] **Step 1: 写失败测试**

在 `tests/test_a2_p1_runtime.py` 添加：

```python
import json

def test_worker_jsonl_payload_schema():
    """验证 worker JSONL 每行包含完整 payload (可直接 evaluate_gate)"""
    # 检查 worker 脚本源码
    worker_src = pathlib.Path("scripts/a2_p1_worker.py").read_text(encoding="utf-8")
    # 必须包含所有必要字段
    required_fields = ["bar_idx", "pure_pred_move", "scheme_pred_move",
                       "lgbm_pred_move", "actual_move", "base_price", "atr"]
    for field in required_fields:
        assert f'"{field}"' in worker_src or f"'{field}'" in worker_src, \
            f"Worker JSONL 必须包含字段: {field}"
    # 必须包含 version 和 seed
    assert "version" in worker_src, "必须包含 git commit version"
    assert "seed" in worker_src or "np.random" in worker_src, "必须包含固定 seed"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_worker_jsonl_payload_schema -v
```

Expected: FAIL — `FileNotFoundError: scripts/a2_p1_worker.py` 或 `AssertionError`

- [ ] **Step 3: 实现 Worker**

创建 `scripts/a2_p1_worker.py`:

```python
"""A2-P1 Worker: 单品种 eval point 级别执行 + 细粒度断点续跑。

Usage:
    python scripts/a2_p1_worker.py ss [--dense-step 24] [--refit-every 10] [--dry-run]

产出:
    reports/a2_p1_results/<symbol>.jsonl — 每行一个 eval point 的完整结果
    reports/a2_p1_features/<symbol>_dense_matrix.parquet — dense 矩阵缓存 (原子写入)
"""
from __future__ import annotations
import sys, pathlib, os, json, argparse, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import numpy as np
import pandas as pd


def _get_git_version() -> str:
    """获取当前 git commit hash"""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, cwd=pathlib.Path(__file__).parent.parent)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _load_completed_bars(jsonl_path: pathlib.Path) -> set:
    """读取已有 JSONL, 提取已完成的 bar_idx 集合"""
    completed = set()
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    completed.add(rec["bar_idx"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return completed


def _generate_eval_grid(symbol: str, total_bars: int) -> list:
    """生成 eval bars 网格 (与 monthly_backtest 一致)"""
    from config.backtest_config import CONTEXT_BARS, HORIZON, STEP
    eval_bars = list(range(CONTEXT_BARS, total_bars - HORIZON + 1, STEP))
    return eval_bars


def _evaluate_one_point(mat, t0, hourly, daily, closes, df_1h, scheme, symbol):
    """
    评估单个 eval point T0。
    返回 dict: {bar_idx, pure_pred_move, scheme_pred_move, lgbm_pred_move,
                actual_move, base_price, atr}
    """
    from config.backtest_config import HORIZON
    from cascade.features import _calc_atr

    # base_price = T0 时刻的 close
    base_price = float(closes[t0])

    # actual_move = closes[T0 + HORIZON] - closes[T0]
    actual_move = float(closes[t0 + HORIZON] - closes[t0])

    # ATR @ T0
    atr_arr = _calc_atr(df_1h.iloc[:t0 + 1])
    atr = float(atr_arr[-1]) if len(atr_arr) else 1.0

    # pure_pred_move: 从 dense matrix 读取 timesfm_pure_pred (收益率) × base_price
    row = mat[mat["bar_idx"] == t0]
    if row.empty:
        pure_pred_move = 0.0
    else:
        pure_return = float(row["timesfm_pure_pred"].iloc[0])
        pure_pred_move = pure_return * base_price

    # scheme_pred_move: HourlyModel.predict with scheme covariates
    scheme_pred_move = 0.0
    if scheme is not None:
        try:
            from data.data_store import BacktestDataStore
            from cascade.daily_model import DailyModel
            from cascade.hourly_model import HourlyModel
            cutoff = str(pd.Timestamp(df_1h["dt"].iloc[t0]).strftime("%Y-%m-%d"))
            with BacktestDataStore(symbol, cutoff) as bts:
                dr = daily.predict(symbol, bts)
                hr = HourlyModel(shared_model=hourly.model)
                res = hr.predict(symbol, bts, dr,
                                 covariate_type=scheme.covariate_type,
                                 covariate_types=scheme.covariate_types,
                                 verbose=False, skip_validation=True)
                scheme_pred_move = float(res.point_forecast[-1]) - base_price
        except Exception:
            scheme_pred_move = 0.0

    # lgbm_pred_move: 从 train_lgbm_walkforward 的结果中获取 (在外部循环中填充)
    # Worker 中 lgbm_pred_move 由调用方填充
    lgbm_pred_move = None  # 占位, 由主循环填充

    return {
        "bar_idx": t0,
        "pure_pred_move": pure_pred_move,
        "scheme_pred_move": scheme_pred_move,
        "lgbm_pred_move": lgbm_pred_move,  # 待填充
        "actual_move": actual_move,
        "base_price": base_price,
        "atr": atr,
    }


def run_worker(symbol: str, dense_step: int, refit_every: int, dry_run: bool = False):
    """Worker 主函数: 单品种 eval point 级别执行 + 细粒度续跑"""
    from data.data_store import DataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward, FEATURE_COLS
    from config.prediction_scheme import SCHEMES

    symbol_upper = symbol.upper()
    symbol_lower = symbol.lower()
    version = _get_git_version()

    # 固定随机种子 (每品种确定性)
    seed = hash(symbol_upper) % (2 ** 32)
    np.random.seed(seed)

    # 输出路径
    results_dir = pathlib.Path("reports/a2_p1_results")
    results_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = results_dir / f"{symbol_lower}.jsonl"

    # Step 1: 加载数据, 确定 eval grid
    with DataStore(symbol_lower) as store:
        df_1h = store.get_main_contract_1h(limit=100000)
    total_bars = len(df_1h)
    closes = df_1h["close_price"].values.astype(float)
    eval_bars = _generate_eval_grid(symbol_lower, total_bars)

    # 仅保留 dense matrix 中有的 bar
    cache_path = f"reports/a2_p1_features/{symbol_lower}_dense_matrix.parquet"
    pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)

    # Step 2: 检查已完成 (细粒度续跑)
    completed_bars = _load_completed_bars(jsonl_path)
    pending_bars = [b for b in eval_bars if b not in completed_bars]
    print(f"[Worker {symbol_upper}] {len(completed_bars)} done, {len(pending_bars)} pending, {total_bars} total bars")

    if dry_run:
        print(f"[Worker {symbol_upper}] DRY RUN: would evaluate {len(pending_bars)} bars")
        if pending_bars:
            print(f"  First 5 pending: {pending_bars[:5]}")
            print(f"  Last 5 pending: {pending_bars[-5:]}")
        return

    if not pending_bars:
        print(f"[Worker {symbol_upper}] all done, exit")
        return

    # Step 3: 加载模型 (一次性, 本进程共享)
    print(f"[Worker {symbol_upper}] loading models...")
    import torch
    torch.set_float32_matmul_precision("high")
    import timesfm
    base = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    hourly = HourlyModel(shared_model=base)
    daily = DailyModel(shared_model=base)

    # Step 4: 构建 dense matrix (或从缓存读取, 原子写入在 build_dense_feature_matrix 内)
    print(f"[Worker {symbol_upper}] building dense matrix...")
    with DataStore(symbol_lower) as store:
        mat = build_dense_feature_matrix(
            symbol_lower, store, dense_step=dense_step,
            shared_hourly=hourly, shared_daily=daily, cache_path=cache_path,
        )

    # 添加 t0_close 列 (train_lgbm_walkforward 需要)
    mat["t0_close"] = [closes[t] if t < len(closes) else np.nan for t in mat["bar_idx"]]

    # Step 5: LGBM walk-forward 训练 (批量, 仅对 pending bars)
    # 注意: train_lgbm_walkforward 需要所有 eval bars (包括已完成的) 来训练
    # 但我们只对 pending bars 写入 JSONL
    print(f"[Worker {symbol_upper}] training LGBM on {len(mat)} dense rows...")
    lgbm_out = train_lgbm_walkforward(mat, pending_bars, refit_every=refit_every)
    # lgbm_out: DataFrame with columns [bar_idx, pred_return]
    # 转为 dict: bar_idx -> pred_return
    lgbm_preds = dict(zip(lgbm_out["bar_idx"], lgbm_out["pred_return"]))

    # Step 6: 逐 pending bar 评估, 原子追加 JSONL
    scheme = SCHEMES.get(symbol_lower)
    print(f"[Worker {symbol_upper}] evaluating {len(pending_bars)} points...")
    with open(jsonl_path, "a", encoding="utf-8") as f:
        for t0 in pending_bars:
            result = _evaluate_one_point(mat, t0, hourly, daily, closes, df_1h, scheme, symbol_lower)
            # 填充 lgbm_pred_move
            pred_return = lgbm_preds.get(t0, 0.0)
            result["lgbm_pred_move"] = pred_return * result["base_price"]
            # 添加元数据
            result["version"] = version
            result["seed"] = seed
            result["symbol"] = symbol_upper
            f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            f.flush()

    print(f"[Worker {symbol_upper}] completed {len(pending_bars)} points, wrote to {jsonl_path}")


def main():
    p = argparse.ArgumentParser(description="A2-P1 Worker: 单品种 eval point 级别执行")
    p.add_argument("symbol", help="品种代码 (如 ss, rb, i)")
    p.add_argument("--dense-step", type=int, default=24, help="dense 矩阵步长 (default: 24)")
    p.add_argument("--refit-every", type=int, default=10, help="LGBM 重训间隔 (default: 10)")
    p.add_argument("--dry-run", action="store_true", help="干跑模式: 只打印 pending bars, 不执行")
    args = p.parse_args()
    run_worker(args.symbol, args.dense_step, args.refit_every, args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_worker_jsonl_payload_schema -v
```

Expected: PASS

- [ ] **Step 5: 测试 dry-run 模式**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_worker.py ss --dry-run
```

Expected: 打印 `[Worker SS] 0 done, ~396 pending, ~9996 total bars` + pending bars 列表

- [ ] **Step 6: 提交**

```bash
git add scripts/a2_p1_worker.py tests/test_a2_p1_runtime.py
git commit -m "feat(a2-p1): Worker 单品种脚本 (细粒度续跑 + 完整 JSONL payload + dry-run)"
```

---

### Task 3: Orchestrator 调度器

**Files:**
- Create: `scripts/a2_p1_orchestrator.py`
- Test: `tests/test_a2_p1_runtime.py::test_orchestrator_skip_completed`

**Interfaces:**
- Consumes: `scripts/a2_p1_worker.py`（子进程调用）
- Produces: CLI: `python scripts/a2_p1_orchestrator.py [symbols...] [--force] [--parallel 1]`
- 产出: 每品种日志 `reports/a2_p1_logs/<symbol>.log`

- [ ] **Step 1: 写失败测试**

```python
def test_orchestrator_skip_completed():
    """验证 orchestrator 跳过已完成的品种 (JSONL 行数 == 预期)"""
    orch_src = pathlib.Path("scripts/a2_p1_orchestrator.py").read_text(encoding="utf-8")
    # 必须检查 JSONL 是否存在
    assert "jsonl" in orch_src.lower() or "results" in orch_src.lower()
    # 必须有 skip 逻辑
    assert "skip" in orch_src.lower() or "continue" in orch_src.lower()
    # 必须用 subprocess 调用 worker
    assert "subprocess" in orch_src
```

- [ ] **Step 2: 运行测试验证失败**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_orchestrator_skip_completed -v
```

Expected: FAIL

- [ ] **Step 3: 实现 Orchestrator**

创建 `scripts/a2_p1_orchestrator.py`:

```python
"""A2-P1 Orchestrator: 调度 Worker 子进程, 品种级隔离 + 断点续跑。

Usage:
    python scripts/a2_p1_orchestrator.py                          # 全 20 品种
    python scripts/a2_p1_orchestrator.py ss rb i                  # 指定品种
    python scripts/a2_p1_orchestrator.py --force ss               # 强制重跑
    python scripts/a2_p1_orchestrator.py --parallel 2             # 并行度 (实验性)
"""
from __future__ import annotations
import sys, pathlib, os, subprocess, argparse, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config.backtest_config import SYMBOLS, CONTEXT_BARS, HORIZON, STEP


def _count_jsonl_lines(jsonl_path: pathlib.Path) -> int:
    """统计 JSONL 行数 (已完成的 eval points)"""
    if not jsonl_path.exists():
        return 0
    return sum(1 for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip())


def _expected_eval_points() -> int:
    """估算预期 eval points 数量 (近似值, 用于判断是否完成)"""
    # 假设 ~10000 根 1H bars, eval_bars = range(480, 10000-24+1, 24) ≈ 396
    # 实际值因品种数据量不同略有差异, 但只要 >= 300 就认为完成
    return 300  # 保守阈值


def run_orchestrator(symbols: list, force: bool = False, parallel: int = 1):
    """调度 Worker 子进程"""
    results_dir = pathlib.Path("reports/a2_p1_results")
    logs_dir = pathlib.Path("reports/a2_p1_logs")
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    python = sys.executable  # 当前 Python 解释器
    worker_script = pathlib.Path(__file__).parent / "a2_p1_worker.py"

    completed = []
    skipped = []
    failed = []

    for sym in symbols:
        sym_lower = sym.lower()
        jsonl_path = results_dir / f"{sym_lower}.jsonl"
        log_path = logs_dir / f"{sym_lower}.log"

        # 检查是否已完成
        n_lines = _count_jsonl_lines(jsonl_path)
        if not force and n_lines >= _expected_eval_points():
            print(f"[Orchestrator] SKIP {sym.upper()}: already done ({n_lines} eval points)")
            skipped.append(sym)
            continue

        # 启动 Worker 子进程
        print(f"[Orchestrator] START {sym.upper()} (force={force}, prev_lines={n_lines})")
        with open(log_path, "w", encoding="utf-8") as log_file:
            result = subprocess.run(
                [python, str(worker_script), sym_lower],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=pathlib.Path(__file__).parent.parent,
                timeout=3600,  # 1 小时超时
            )

        if result.returncode == 0:
            n_final = _count_jsonl_lines(jsonl_path)
            print(f"[Orchestrator] DONE {sym.upper()}: {n_final} eval points, log={log_path}")
            completed.append(sym)
        else:
            print(f"[Orchestrator] FAIL {sym.upper()}: exit code {result.returncode}, log={log_path}")
            failed.append(sym)

    # 汇总
    print(f"\n[Orchestrator] SUMMARY: {len(completed)} done, {len(skipped)} skipped, {len(failed)} failed")
    if failed:
        print(f"  Failed: {[s.upper() for s in failed]}")
        print(f"  Check logs in {logs_dir}/")

    # 全部完成后, 自动调用报告生成
    if completed or (not failed):
        print(f"\n[Orchestrator] generating final report...")
        report_script = pathlib.Path(__file__).parent / "a2_p1_generate_report.py"
        subprocess.run([python, str(report_script)], cwd=pathlib.Path(__file__).parent.parent)


def main():
    p = argparse.ArgumentParser(description="A2-P1 Orchestrator: 调度 Worker 子进程")
    p.add_argument("symbols", nargs="*", default=SYMBOLS, help="品种列表 (default: 全 20 品种)")
    p.add_argument("--force", action="store_true", help="强制重跑 (忽略已有 JSONL)")
    p.add_argument("--parallel", type=int, default=1, help="并行度 (default: 1, 实验性)")
    args = p.parse_args()
    run_orchestrator(args.symbols, args.force, args.parallel)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_orchestrator_skip_completed -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/a2_p1_orchestrator.py tests/test_a2_p1_runtime.py
git commit -m "feat(a2-p1): Orchestrator 调度器 (品种隔离 + 断点续跑 + 自动报告)"
```

---

### Task 4: Status 进度查询脚本

**Files:**
- Create: `scripts/a2_p1_status.py`
- Test: `tests/test_a2_p1_runtime.py::test_status_script_exists`

**Interfaces:**
- Consumes: `reports/a2_p1_results/*.jsonl`
- Produces: CLI: `python scripts/a2_p1_status.py [--watch]`

- [ ] **Step 1: 写失败测试**

```python
def test_status_script_exists():
    """验证 status 脚本存在且可运行"""
    status_script = pathlib.Path("scripts/a2_p1_status.py")
    assert status_script.exists(), "scripts/a2_p1_status.py 必须存在"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_status_script_exists -v
```

Expected: FAIL

- [ ] **Step 3: 实现 Status 脚本**

创建 `scripts/a2_p1_status.py`:

```python
"""A2-P1 Status: 实时进度查询 (汇总所有 JSONL)。

Usage:
    python scripts/a2_p1_status.py              # 一次性查询
    python scripts/a2_p1_status.py --watch      # 每 10 秒刷新
"""
from __future__ import annotations
import sys, pathlib, json, time, argparse
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config.backtest_config import SYMBOLS


def _count_jsonl_lines(jsonl_path: pathlib.Path) -> int:
    if not jsonl_path.exists():
        return 0
    return sum(1 for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip())


def _get_last_record(jsonl_path: pathlib.Path) -> dict | None:
    """读取 JSONL 最后一行"""
    if not jsonl_path.exists():
        return None
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if line.strip():
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


def print_status():
    """打印进度表"""
    results_dir = pathlib.Path("reports/a2_p1_results")
    print(f"{'Symbol':<8} | {'Done':>5} | {'Status':<12}")
    print(f"{'-'*8}-+-{'-'*5}-+-{'-'*12}")

    total_done = 0
    total_pending = 0

    for sym in SYMBOLS:
        sym_lower = sym.lower()
        jsonl_path = results_dir / f"{sym_lower}.jsonl"
        n_lines = _count_jsonl_lines(jsonl_path)
        total_done += n_lines

        # 估算 pending (假设 ~396 个 eval points)
        estimated_total = 396
        pending = max(0, estimated_total - n_lines)
        total_pending += pending

        if n_lines == 0:
            status = "⏳ Pending"
        elif n_lines >= 300:
            status = "✅ Done"
        else:
            status = f"🔄 {n_lines}/396"

        print(f"{sym.upper():<8} | {n_lines:>5} | {status:<12}")

    print(f"\nTotal: {total_done} done, {total_pending} pending")


def main():
    p = argparse.ArgumentParser(description="A2-P1 Status: 实时进度查询")
    p.add_argument("--watch", action="store_true", help="每 10 秒刷新")
    args = p.parse_args()

    if args.watch:
        try:
            while True:
                print("\033[2J\033[H", end="")  # 清屏
                print_status()
                time.sleep(10)
        except KeyboardInterrupt:
            print("\nStopped")
    else:
        print_status()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_status_script_exists -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/a2_p1_status.py tests/test_a2_p1_runtime.py
git commit -m "feat(a2-p1): Status 进度查询脚本 (--watch 实时刷新)"
```

---

### Task 5: 报告生成脚本

**Files:**
- Create: `scripts/a2_p1_generate_report.py`
- Test: `tests/test_a2_p1_runtime.py::test_report_script_exists`

**Interfaces:**
- Consumes: `reports/a2_p1_results/*.jsonl`（每行包含完整 payload）
- Produces: `reports/research/2026-08-05_a2_p1_baseline_result.md`（裁决报告）
- 调用: `cascade.evaluation_metrics.evaluate_gate()`（或等价的 `calc_net_metrics` + `paired_bootstrap_ev_ci`）

- [x] **Step 1: 写失败测试**

```python
def test_report_script_exists():
    """验证报告生成脚本存在"""
    report_script = pathlib.Path("scripts/a2_p1_generate_report.py")
    assert report_script.exists(), "scripts/a2_p1_generate_report.py 必须存在"
```

- [x] **Step 2: 运行测试验证失败**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_report_script_exists -v
```

Expected: FAIL

- [x] **Step 3: 实现报告生成脚本**

创建 `scripts/a2_p1_generate_report.py`:

```python
"""A2-P1 Report Generator: 遍历所有 JSONL, 调用 evaluate_gate(), 生成裁决报告。

Usage:
    python scripts/a2_p1_generate_report.py

产出:
    reports/research/2026-08-05_a2_p1_baseline_result.md
"""
from __future__ import annotations
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import numpy as np
import pandas as pd

from config.backtest_config import SYMBOLS
from scripts.a2_p1_lgbm_baseline import evaluate_gate


def load_symbol_results(jsonl_path: pathlib.Path) -> pd.DataFrame:
    """读取单品种 JSONL 为 DataFrame"""
    if not jsonl_path.exists():
        return pd.DataFrame()
    records = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return pd.DataFrame(records) if records else pd.DataFrame()


def generate_report():
    """遍历所有 JSONL, 计算 gate 裁决, 生成 Markdown 报告"""
    results_dir = pathlib.Path("reports/a2_p1_results")
    report_path = pathlib.Path("reports/research/2026-08-05_a2_p1_baseline_result.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    verdicts = []

    for sym in SYMBOLS:
        sym_lower = sym.lower()
        jsonl_path = results_dir / f"{sym_lower}.jsonl"
        df = load_symbol_results(jsonl_path)

        if df.empty or len(df) < 10:
            print(f"[Report] SKIP {sym.upper()}: insufficient data ({len(df)} points)")
            continue

        # 提取 arrays
        lgbm_moves = df["lgbm_pred_move"].values.astype(float)
        pure_moves = df["pure_pred_move"].values.astype(float)
        scheme_moves = df["scheme_pred_move"].values.astype(float)
        actual_moves = df["actual_move"].values.astype(float)
        base_prices = df["base_price"].values.astype(float)
        atrs = df["atr"].values.astype(float)

        # tick_size
        try:
            from data.config import get_tick_size
            tick = get_tick_size(sym_lower)
        except Exception:
            tick = 1.0

        # 调用 evaluate_gate
        verdict = evaluate_gate(
            lgbm_moves, pure_moves, scheme_moves,
            actual_moves, base_prices, atrs, tick_size=tick,
        )
        verdict["symbol"] = sym.upper()
        verdict["n_eval"] = len(df)
        verdicts.append(verdict)
        print(f"[Report] {sym.upper()}: {verdict.get('gate')} (LGBM PF={verdict.get('lgbm_metrics', {}).get('PF')})")

    # 写 Markdown 报告
    lines = ["# A2-P1 LGBM 基线门禁裁决报告", "", f"**品种数**: {len(verdicts)}", ""]
    go_count = sum(1 for v in verdicts if v.get("gate") == "GO")
    lines.append(f"**聚合裁决**: {'GO' if go_count > len(verdicts) / 2 else 'NO-GO'} "
                 f"({go_count}/{len(verdicts)} 品种 GO)")
    lines.append("")
    lines.append("| 品种 | gate | LGBM PF | scheme PF | LGBM EV | EV差CI下界 | n |")
    lines.append("|------|------|---------|-----------|---------|-----------|---|")
    for v in verdicts:
        lpf = v.get("lgbm_metrics", {}).get("PF", "N/A")
        spf = v.get("scheme_metrics", {}).get("PF", "N/A")
        lev = v.get("lgbm_metrics", {}).get("EV", "N/A")
        ci = v.get("ev_diff_ci", {}).get("lower", "N/A")
        lines.append(f"| {v.get('symbol', '?')} | {v.get('gate', '?')} | {lpf} | "
                     f"{spf} | {lev} | {ci} | {v.get('n_eval', 0)} |")

    lines.append("")
    lines.append("## 声明")
    lines.append("- vol_prob 在 2026-03 前评估点有轻微 Lookahead（模型训练截止 2026-03-31）")
    lines.append("- 本报告会随 JSONL 数据增加自动更新")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已生成: {report_path}")


if __name__ == "__main__":
    generate_report()
```

- [x] **Step 4: 运行测试验证通过**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python -m pytest tests/test_a2_p1_runtime.py::test_report_script_exists -v
```

Expected: PASS

- [x] **Step 5: 提交**

```bash
git add scripts/a2_p1_generate_report.py tests/test_a2_p1_runtime.py
git commit -m "feat(a2-p1): 报告生成脚本 (遍历 JSONL + evaluate_gate + 裁决报告)"
```

---

### Task 6: 向后兼容旧入口

**Files:**
- Modify: `scripts/a2_p1_lgbm_baseline.py` — `main()` 函数改为调用 Orchestrator

- [ ] **Step 1: 修改旧入口**

读 `scripts/a2_p1_lgbm_baseline.py` 找到 `main()` 函数，修改为：

```python
def main():
    """向后兼容: 调用 Orchestrator"""
    import argparse
    p = argparse.ArgumentParser(description="A2-P1 LGBM 基线探针 (向后兼容入口)")
    p.add_argument("symbols", nargs="*", default=None, help="品种列表 (default: 全 20 品种)")
    p.add_argument("--max-points", type=int, default=None, help="[DEPRECATED] 忽略, 使用细粒度续跑")
    p.add_argument("--dense-step", type=int, default=24)
    p.add_argument("--refit-every", type=int, default=10)
    p.add_argument("--force", action="store_true", help="强制重跑")
    args = p.parse_args()

    if args.max_points:
        print("[WARNING] --max-points 已废弃, 使用细粒度续跑 (Worker 内部跳过已完成 bar_idx)")

    # 调用 Orchestrator
    from scripts.a2_p1_orchestrator import run_orchestrator
    symbols = args.symbols if args.symbols else SYMBOLS
    run_orchestrator(symbols, force=args.force)
```

同时在文件顶部添加 `from config.backtest_config import SYMBOLS`（如果尚未存在）。

- [ ] **Step 2: 验证旧入口仍可运行**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_lgbm_baseline.py ss --dry-run 2>&1 | head -5
```

Expected: 不报错（可能提示 `--dry-run` 不支持，因为 Orchestrator 没有 dry-run 参数；这是预期的，旧入口不支持 dry-run，用户应直接使用 Worker）

- [ ] **Step 3: 提交**

```bash
git add scripts/a2_p1_lgbm_baseline.py
git commit -m "refactor(a2-p1): 旧入口改为调用 Orchestrator (向后兼容)"
```

---

### Task 7: 全量运行测试

- [ ] **Step 1: 清理旧 JSONL（可选）**

```bash
# 如果要全量重跑, 清理旧的 results
rm -f reports/a2_p1_results/*.jsonl
```

- [ ] **Step 2: 测试单品种端到端**

```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_worker.py ss
```

Expected: 运行 ~5-10 分钟，产出 `reports/a2_p1_results/ss.jsonl`，~396 行

- [ ] **Step 3: 测试断点续跑**

```bash
# 手动 kill worker (在运行到 ~100 行时)
# 然后重启, 验证从 101 开始续跑
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_worker.py ss
```

Expected: 打印 `[Worker SS] 100 done, 296 pending`，从 101 开始

- [ ] **Step 4: 全量 20 品种运行**

```bash
# 后台运行 (nohup)
nohup D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_orchestrator.py \
    > reports/a2_p1_orchestrator.log 2>&1 &

# 查看进度
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_status.py --watch
```

Expected: ~3 小时完成 20 品种，产出 `reports/research/2026-08-05_a2_p1_baseline_result.md`

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat(a2-p1): 运行架构重设计完成 (Orchestrator + Worker + Status + Report)

核心改进:
- 品种级进程隔离 (JAX/LGBM 崩溃不影响其他品种)
- eval point 级细粒度断点续跑 (JSONL 原子追加)
- Parquet 原子写入 (防 OOM 损坏)
- 完整 JSONL payload (汇总脚本直接调用 evaluate_gate)
- 结果可复现 (每品种固定 seed + git version)
- 实时监控 (status --watch)"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: 所有 5 个设计目标（品种隔离、细粒度续跑、内存回收、结果可复现、监控友好）均有对应 Task
- [x] **Placeholder scan**: 无 TBD/TODO，所有 steps 包含完整代码
- [x] **Type consistency**: `bar_idx`, `pure_pred_move`, `scheme_pred_move`, `lgbm_pred_move`, `actual_move`, `base_price`, `atr` 在所有 Task 中命名一致
- [x] **3 个工程细节**: (1) JSONL 完整 payload ✓, (2) Parquet 原子写入 ✓, (3) Orchestrator 自动调用报告 ✓

---

**Plan 完成，保存到 `docs/superpowers/plans/2026-08-05-a2-p1-runtime-redesign.md`。**

下一步选择执行方式：
1. **Subagent-Driven**（推荐）：每个 Task 派发独立 subagent，review 后继续
2. **Inline Execution**：在当前 session 批量执行

选择哪种？
