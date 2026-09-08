# A2-P1 实验完整性与可复现性加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 A2-P1/A2-P1.1 的结果目录、断点写入、完成判定、门禁报告和运行审计在重启、重复启动、异常预测和部分产物缺失时均 fail-closed，并能重建可信的 20 品种基线报告。

**Architecture:** 新增一个只负责运行路径、eval grid 和 JSONL 校验的共享模块，Orchestrator、Worker、Report Generator 共同使用同一套实验配置和完整性规则。Worker 对单品种结果文件实施单写入锁并在写入前后按 `bar_idx` 校验；Report Generator 在任何缺失、重复、版本不一致、预测异常或 eval grid 不完整时拒绝覆盖正式报告。历史 A2-P1 与 A2-P1.1 通过显式 `run_id` 和独立目录隔离，恢复历史结果只使用 manifest 记录的来源文件，不重新运行回测。

**Tech Stack:** Python 3.11、标准库 `dataclasses/json/pathlib/os/time/hashlib`、pandas、NumPy、LightGBM、SQLite、pytest/unittest；Windows CPU-only 运行环境；不新增第三方依赖。

## Global Constraints

- 不启动任何真实回测；本计划只修改运行器、结果校验和文档/测试。
- A2-P1 与 A2-P1.1 必须使用不同 `run_id`、结果目录、日志目录和报告路径；禁止通过修改源码硬编码路径切换实验。
- 同一结果 JSONL 只能有一个写入者；`flush()` 不视为并发安全；锁无法取得时 Worker 必须 fail-fast。
- 完成判定必须比较精确的唯一 `bar_idx` 集合与当前数据库计算出的 eval grid；禁止使用固定 `>=300` 行数阈值。
- 报告生成必须 fail-closed：任何预期品种缺文件、重复 bar、无效记录、版本/实验不一致或 eval grid 缺失时，不得覆盖正式报告。
- 历史结果恢复只允许读取现有 `reports/a2_p1_results/` 与 `reports/a2_p1_results_backup/`，不得把 A2-P1.1 结果混入 A2-P1。
- `TICK_SIZES` 必须来自 `config.backtest_config`；缺少品种 tick size 时报告失败，不允许静默回退 `1.0`。
- Scheme 预测异常必须显式记录并使该品种结果无效，不能写入 `scheme_pred_move=0.0` 伪装为合法预测。
- 随机种子必须使用稳定哈希，并显式传入 LightGBM 的 `random_state`。
- 现有 A2-P1.1 三项修复保持不变：inner CV `best_iteration_`、`sqrt(abs(Y))*100`、`hour_sin/hour_cos`。
- 任何文档、结果清单或 manifest 的状态描述必须以磁盘事实和校验脚本输出为准。

---

## 文件结构与职责

| 文件 | 职责 | 变更 |
|---|---|---|
| `scripts/a2_p1_runtime.py` | 共享 `run_id`、路径、eval grid、JSONL 读取/校验、manifest schema | 新建 |
| `scripts/a2_p1_orchestrator.py` | 接收显式运行配置、创建 manifest、单实例调度、捕获 timeout | 修改 |
| `scripts/a2_p1_worker.py` | 接收运行配置、单品种锁、幂等结果追加、显式错误记录 | 修改 |
| `scripts/a2_p1_generate_report.py` | 全量 fail-closed 校验、正确 tick size、只在通过后写报告 | 修改 |
| `scripts/a2_p1_lgbm_baseline.py` | 稳定随机性、保留当前 CV early stopping 逻辑 | 修改 |
| `cascade/lgbm_features.py` | 使用共享 eval grid，防 dense/eval 边界不一致 | 修改 |
| `tests/test_a2_p1_integrity.py` | 运行配置、grid、JSONL 去重/校验、锁和 fail-closed 行为 | 新建 |
| `tests/test_a2_p1_runtime.py` | 更新旧的“原子追加”断言，覆盖单写入者语义 | 修改 |
| `scripts/a2_p1_restore_manifest.py` | 历史 A2-P1 主目录/备份目录 dry-run 清单与安全恢复 | 新建 |
| `reports/a2_p1_manifest.json` | A2-P1 历史运行来源、目录、版本、校验摘要 | 生成/新增 |
| `docs/runbook.md` | 运行、恢复、完整性校验和故障处置说明 | 修改 |
| `docs/README.md` | 当前 A2 门禁结果口径与报告入口 | 修改 |
| `STATE.md` | 恢复后正式基线状态和未关闭技术债 | 修改 |

---

### Task 1: 建立共享运行配置与精确 eval grid

**Files:**
- Create: `scripts/a2_p1_runtime.py`
- Modify: `scripts/a2_p1_orchestrator.py:22-50`
- Modify: `scripts/a2_p1_worker.py:41-45,125-145`
- Modify: `cascade/lgbm_features.py:286-290`
- Test: `tests/test_a2_p1_integrity.py`

**Interfaces:**
- Produces `RunConfig`, `generate_eval_grid(total_bars: int) -> list[int]`, `expected_eval_grid(symbol: str) -> list[int]`, `load_jsonl_records(path: pathlib.Path) -> list[dict]`, `validate_jsonl_records(records, expected_bars, run_id, symbol, version=None) -> ValidationResult`。
- `RunConfig` 至少包含 `run_id: str`、`results_dir: pathlib.Path`、`logs_dir: pathlib.Path`、`report_path: pathlib.Path`、`features_dir: pathlib.Path`、`symbols: list[str]`。

- [ ] **Step 1: 写共享 grid 和配置测试**

```python
# tests/test_a2_p1_integrity.py
from pathlib import Path
from scripts.a2_p1_runtime import generate_eval_grid, RunConfig


def test_eval_grid_matches_worker_boundary():
    assert generate_eval_grid(1000) == list(range(480, 1000 - 24 + 1, 24))


def test_run_config_never_uses_a2_p1_1_for_a2_p1_by_default():
    root = Path("D:/FlyBuddy/fm_a")
    cfg = RunConfig.for_run("a2-p1", ["ss"], root)
    assert cfg.results_dir == root / "reports/a2_p1_results"
    assert cfg.logs_dir == root / "reports/a2_p1_logs"
    assert cfg.report_path == root / "reports/research/2026-08-05_a2_p1_baseline_result.md"


def test_run_config_isolated_for_a2_p1_1():
    root = Path("D:/FlyBuddy/fm_a")
    cfg = RunConfig.for_run("a2-p1.1", ["fg"], root)
    assert cfg.results_dir == root / "reports/a2_p1.1_results"
    assert cfg.logs_dir == root / "reports/a2_p1.1_logs"
    assert cfg.results_dir != RunConfig.for_run("a2-p1", ["fg"], root).results_dir
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py -q
```

Expected: `ModuleNotFoundError`，因为共享运行模块尚未建立。

- [ ] **Step 3: 实现 `RunConfig` 与共享 grid**

```python
# scripts/a2_p1_runtime.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import os
from config.backtest_config import CONTEXT_BARS, HORIZON, STEP, SYMBOLS


def generate_eval_grid(total_bars: int) -> list[int]:
    return list(range(CONTEXT_BARS, total_bars - HORIZON + 1, STEP))


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    results_dir: Path
    logs_dir: Path
    report_path: Path
    features_dir: Path
    symbols: list[str]

    @classmethod
    def for_run(cls, run_id: str, symbols: list[str], root: Path) -> "RunConfig":
        if run_id == "a2-p1":
            suffix = "a2_p1"
            report = root / "reports/research/2026-08-05_a2_p1_baseline_result.md"
        elif run_id == "a2-p1.1":
            suffix = "a2_p1.1"
            report = root / "reports/research/20260806_a2_p1.1_verdict.md"
        else:
            raise ValueError(f"unsupported run_id: {run_id}")
        return cls(
            run_id=run_id,
            results_dir=root / f"reports/{suffix}_results",
            logs_dir=root / f"reports/{suffix}_logs",
            report_path=report,
            features_dir=root / "reports/a2_p1_features",
            symbols=[s.lower() for s in symbols],
        )


def load_jsonl_records(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL {path}:{line_no}") from exc
    return records
```

The implementation must also expose `expected_eval_grid(symbol)` by reading `DataStore(symbol).get_main_contract_1h(limit=100000)` and applying `generate_eval_grid`; it must close the store in a `with` block.

- [ ] **Step 4: Replace Worker, Orchestrator and dense feature grid calculations with `generate_eval_grid`**

Remove the duplicate `range(...)` expressions. The Worker and `build_dense_feature_matrix` must receive the same list or call the same function, so the final bar boundary cannot diverge.

- [ ] **Step 5: Run focused tests**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q
```

Expected: all focused tests PASS.

- [ ] **Step 6: Commit after review approval**

```bash
git add scripts/a2_p1_runtime.py scripts/a2_p1_orchestrator.py scripts/a2_p1_worker.py cascade/lgbm_features.py tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py
git commit -m "refactor(a2-p1): centralize run paths and eval grid"
```

---

### Task 2: Add single-writer locking and idempotent JSONL writes

**Files:**
- Modify: `scripts/a2_p1_runtime.py`
- Modify: `scripts/a2_p1_worker.py:143-205`
- Test: `tests/test_a2_p1_integrity.py`

**Interfaces:**
- Produces `exclusive_result_lock(lock_path: Path)` context manager.
- Produces `append_unique_record(path: Path, record: dict, key: str = "bar_idx") -> None`.
- Lock failure raises `RuntimeError` and Worker exits non-zero before loading TimesFM.

- [ ] **Step 1: Write lock and idempotency tests**

```python
from scripts.a2_p1_runtime import append_unique_record, load_jsonl_records


def test_append_unique_record_does_not_duplicate_bar(tmp_path):
    path = tmp_path / "ss.jsonl"
    record = {"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS"}
    append_unique_record(path, record)
    append_unique_record(path, record)
    rows = load_jsonl_records(path)
    assert rows == [record]


def test_lock_is_exclusive(tmp_path):
    from scripts.a2_p1_runtime import exclusive_result_lock
    path = tmp_path / "ss.lock"
    first = exclusive_result_lock(path)
    first.__enter__()
    try:
        second = exclusive_result_lock(path)
        try:
            second.__enter__()
        except RuntimeError:
            pass
        else:
            raise AssertionError("second writer acquired the lock")
    finally:
        first.__exit__(None, None, None)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py::test_append_unique_record_does_not_duplicate_bar tests/test_a2_p1_integrity.py::test_lock_is_exclusive -q
```

Expected: import or assertion failure before implementation.

- [ ] **Step 3: Implement Windows-safe exclusive lock without dependencies**

Use `os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` to acquire the lock and write JSON metadata containing PID, run ID and start time. On normal exit close and unlink the lock. Do not silently reclaim a lock based only on age; stale locks must be reported with their metadata and require explicit operator cleanup.

- [ ] **Step 4: Implement idempotent append under the lock**

Within the lock, load existing records and build `existing_bar_idx`. If the record key already exists, compare immutable payload fields (`run_id`, `symbol`, `version`, predictions, actuals). Identical records are skipped; conflicting records raise `ValueError` rather than appending a second value for the same bar.

- [ ] **Step 5: Hold one result lock for the Worker write phase**

Acquire `reports/<run>_results/<symbol>.jsonl.lock` immediately before writing pending results and release it in `finally`. Re-read completed bars after acquiring the lock, recalculate pending bars, and write only still-missing bars. The lock must be acquired before model loading if the Worker is intended to protect the full read/build/write lifecycle; otherwise a second Worker could still build stale caches. Use the stricter full-lifecycle lock.

- [ ] **Step 6: Add a run-level Orchestrator lock**

Create `<logs_dir>/<run_id>.orchestrator.lock` before the symbol loop. If it already exists, exit with a clear error and do not start any Worker. This prevents two orchestrators from independently launching the same symbol Worker.

- [ ] **Step 7: Run tests and existing runtime tests**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q
```

Expected: PASS; tests must assert the code no longer claims that append+flush alone is atomic.

- [ ] **Step 8: Commit after review approval**

```bash
git add scripts/a2_p1_runtime.py scripts/a2_p1_worker.py scripts/a2_p1_orchestrator.py tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py
git commit -m "fix(a2-p1): make result checkpoints single-writer and idempotent"
```

---

### Task 3: Make the report generator fail-closed and restore correct transaction costs

**Files:**
- Modify: `scripts/a2_p1_generate_report.py:18-96`
- Modify: `scripts/a2_p1_runtime.py`
- Test: `tests/test_a2_p1_integrity.py`

**Interfaces:**
- Produces `validate_run_results(config: RunConfig) -> ValidationReport`.
- `generate_report(config: RunConfig)` raises `RuntimeError` and leaves the existing report untouched when validation fails.
- Uses `TICK_SIZES[symbol]`; a missing key raises a visible error.

- [ ] **Step 1: Write fail-closed report tests**

```python
from scripts.a2_p1_runtime import validate_jsonl_records


def test_validation_rejects_duplicate_bar_idx():
    rows = [
        {"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc"},
        {"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc"},
    ]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert not result.ok
    assert "duplicate" in result.errors[0]


def test_validation_rejects_missing_eval_bar():
    rows = [{"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc"}]
    result = validate_jsonl_records(rows, [480, 504], "a2-p1", "ss")
    assert not result.ok
    assert "missing" in result.errors[0]
```

- [ ] **Step 2: Implement record validation**

Validation must reject:

1. malformed JSONL;
2. duplicate `bar_idx`;
3. missing expected `bar_idx`;
4. unexpected `bar_idx`;
5. `run_id` mismatch;
6. symbol mismatch;
7. mixed non-empty `version` values;
8. missing required numeric fields;
9. `scheme_ok is False` or a non-empty `scheme_error`;
10. non-finite prediction, actual, base price or ATR values.

The validator returns a structured object with `ok`, `errors`, `row_count`, `unique_count`, `missing_bars`, `unexpected_bars`, and `versions`.

- [ ] **Step 3: Change report loading to use the selected `RunConfig`**

The report generator must accept:

```text
python scripts/a2_p1_generate_report.py --run-id a2-p1
python scripts/a2_p1_generate_report.py --run-id a2-p1.1
```

Do not infer the experiment from whichever directory happens to exist. The report path and result directory must come from `RunConfig`.

- [ ] **Step 4: Require all configured symbols before writing**

For every symbol in `config.symbols`, compute its expected eval grid from the current database and validate its JSONL. If any symbol fails, print a per-symbol error and raise `RuntimeError` before `report_path.write_text(...)`. Write to a temporary report path and use `os.replace` only after every symbol passes.

- [ ] **Step 5: Use authoritative tick sizes**

Replace the `data.config.get_tick_size` try/except with:

```python
from config.backtest_config import TICK_SIZES
try:
    tick = float(TICK_SIZES[sym_lower])
except KeyError as exc:
    raise RuntimeError(f"missing tick size for {sym_lower}") from exc
```

Include `tick_size` in each report row and in the manifest.

- [ ] **Step 6: Add report tests for no-overwrite behavior**

Create a temporary report containing `OLD REPORT`, invoke the generator with a missing symbol result, assert it raises `RuntimeError`, and assert the file still contains `OLD REPORT`. Add a test proving the correct `TICK_SIZES` value is passed to `evaluate_gate` by patching the function.

- [ ] **Step 7: Run tests**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit after review approval**

```bash
git add scripts/a2_p1_runtime.py scripts/a2_p1_generate_report.py tests/test_a2_p1_integrity.py
 git commit -m "fix(a2-p1): fail closed on incomplete result reports"
```

---

### Task 4: Make Worker failures visible and deterministic

**Files:**
- Modify: `scripts/a2_p1_worker.py:48-105,121-205`
- Modify: `scripts/a2_p1_lgbm_baseline.py:29-61,94-103`
- Test: `tests/test_a2_p1_integrity.py`

**Interfaces:**
- `_evaluate_one_point(...)` returns a record with `scheme_ok: bool` and `scheme_error: str | None`.
- Stable seed function `stable_symbol_seed(symbol: str) -> int` is shared and deterministic.

- [ ] **Step 1: Write deterministic seed and visible failure tests**

```python
from scripts.a2_p1_runtime import stable_symbol_seed


def test_stable_symbol_seed_is_repeatable():
    assert stable_symbol_seed("SS") == stable_symbol_seed("SS")
    assert stable_symbol_seed("SS") != stable_symbol_seed("UR")


def test_scheme_error_is_not_zero_prediction():
    # The test may use a patched HourlyModel that raises RuntimeError.
    # Assert the resulting record has scheme_ok=False, a non-empty scheme_error,
    # and no valid scheme prediction is submitted to gate evaluation.
    record = evaluate_with_patched_scheme_failure()
    assert record["scheme_ok"] is False
    assert record["scheme_error"]
    assert record["scheme_pred_move"] is None
```

- [ ] **Step 2: Run tests to verify failure**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py::test_stable_symbol_seed_is_repeatable tests/test_a2_p1_integrity.py::test_scheme_error_is_not_zero_prediction -q
```

Expected: failure because the current code uses Python `hash()` and converts Scheme exceptions to `0.0`.

- [ ] **Step 3: Implement stable hashing**

```python
import hashlib

def stable_symbol_seed(symbol: str) -> int:
    digest = hashlib.sha256(symbol.upper().encode("ascii")).digest()
    return int.from_bytes(digest[:4], "big")
```

Set both NumPy and LightGBM random state from this seed. Add `random_state=seed` to the parameter dictionary passed to `LGBMRegressor` without changing the approved feature set or early-stopping design.

- [ ] **Step 4: Make Scheme exceptions explicit**

Change `_evaluate_one_point` so successful records contain:

```python
"scheme_ok": True,
"scheme_error": None,
```

On exception, produce:

```python
"scheme_ok": False,
"scheme_error": f"{type(exc).__name__}: {exc}",
"scheme_pred_move": None,
```

Do not substitute `0.0`. The report validator must reject any symbol containing `scheme_ok=False`.

- [ ] **Step 5: Run tests and compile**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m py_compile scripts/a2_p1_worker.py scripts/a2_p1_lgbm_baseline.py
```

Expected: PASS and no compile errors.

- [ ] **Step 6: Commit after review approval**

```bash
git add scripts/a2_p1_runtime.py scripts/a2_p1_worker.py scripts/a2_p1_lgbm_baseline.py tests/test_a2_p1_integrity.py
 git commit -m "fix(a2-p1): make seeds stable and model failures visible"
```

---

### Task 5: Add run manifest, timeout states and log isolation

**Files:**
- Modify: `scripts/a2_p1_runtime.py`
- Modify: `scripts/a2_p1_orchestrator.py:29-91`
- Modify: `scripts/a2_p1_generate_report.py`
- Test: `tests/test_a2_p1_integrity.py`
- Generate: `reports/a2_p1_manifest.json` for the restored historical run

**Interfaces:**
- Produces a manifest containing `run_id`, `started_at`, `finished_at`, `symbols`, `results_dir`, `logs_dir`, `report_path`, Python executable, Git full hash, dirty flag, feature columns, config constants, tick sizes and per-symbol validation status.
- Orchestrator terminal states are `DONE`, `SKIP`, `FAILED`, `TIMEOUT`, `INVALID`.

- [ ] **Step 1: Write manifest and timeout tests**

```python

def test_manifest_contains_experiment_identity(tmp_path):
    manifest = build_manifest(
        run_id="a2-p1",
        symbols=["ss"],
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
    )
    assert manifest["run_id"] == "a2-p1"
    assert manifest["results_dir"].endswith("results")
    assert "git_sha" in manifest
    assert "feature_columns" in manifest


def test_timeout_is_terminal_failure():
    assert classify_subprocess_result(returncode=None, timed_out=True) == "TIMEOUT"
    assert classify_subprocess_result(returncode=1, timed_out=False) == "FAILED"
```

- [ ] **Step 2: Implement manifest creation**

Capture full `git rev-parse HEAD`, `git status --porcelain`, `FEATURE_COLUMNS`, `CONTEXT_BARS`, `HORIZON`, `STEP`, `SLIPPAGE_TICKS`, and `TICK_SIZES`. Store the manifest in the run-specific report directory or an explicit `manifest_path`, never in a shared ambiguous filename for multiple runs.

- [ ] **Step 3: Add `--run-id`, `--results-dir`, `--logs-dir`, `--report-path` and `--manifest-path` CLI options**

Defaults must preserve the two supported run IDs, but all paths must be passed into the Worker as explicit arguments. Worker must stop using hardcoded `reports/a2_p1.1_results`.

- [ ] **Step 4: Isolate logs by run ID**

Use `<logs_dir>/<symbol>.log` only inside a run-specific directory. Open logs in exclusive/create-new mode for a new run, or append only when explicitly resuming the same run. Record command line and PID at the top of each log.

- [ ] **Step 5: Catch `subprocess.TimeoutExpired`**

Wrap `subprocess.run` in `try/except subprocess.TimeoutExpired`. Record `TIMEOUT`, terminate the process tree using the existing Windows-safe process cleanup path, and continue to the next symbol only if the run policy permits. Never generate a final report when any symbol is `TIMEOUT`, `FAILED` or `INVALID`.

- [ ] **Step 6: Run focused tests**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit after review approval**

```bash
git add scripts/a2_p1_runtime.py scripts/a2_p1_orchestrator.py scripts/a2_p1_worker.py scripts/a2_p1_generate_report.py tests/test_a2_p1_integrity.py
 git commit -m "feat(a2-p1): record run manifests and terminal states"
```

---

### Task 6: Reconcile historical A2-P1 files without running models

**Files:**
- Create: `scripts/a2_p1_restore_manifest.py`
- Create: `reports/a2_p1_manifest.json`
- Test: `tests/test_a2_p1_integrity.py`
- Modify: `docs/runbook.md`
- Modify: `STATE.md`

**Interfaces:**
- `scan_historical_results(main_dir: Path, backup_dir: Path, expected_symbols: list[str]) -> dict` performs read-only reconciliation.
- `restore_missing_results(..., apply: bool = False)` defaults to dry-run and refuses to overwrite an existing file.
- No TimesFM, TqSdk or LightGBM import is allowed in the restore script.

- [ ] **Step 1: Write restore dry-run tests**

```python

def test_restore_dry_run_does_not_modify_files(tmp_path):
    main = tmp_path / "main"
    backup = tmp_path / "backup"
    main.mkdir(); backup.mkdir()
    (backup / "ao.jsonl").write_text('{"bar_idx":480}\n', encoding="utf-8")
    before = list(main.iterdir())
    result = restore_missing_results(main, backup, ["ao"], apply=False)
    assert result["copied"] == []
    assert list(main.iterdir()) == before


def test_restore_refuses_existing_destination(tmp_path):
    main = tmp_path / "main"; backup = tmp_path / "backup"
    main.mkdir(); backup.mkdir()
    (main / "ao.jsonl").write_text("old\n", encoding="utf-8")
    (backup / "ao.jsonl").write_text("new\n", encoding="utf-8")
    result = restore_missing_results(main, backup, ["ao"], apply=True)
    assert result["conflicts"] == ["ao"]
    assert (main / "ao.jsonl").read_text(encoding="utf-8") == "old\n"
```

- [ ] **Step 2: Implement read-only reconciliation**

The scan must report for all 20 symbols:

- source path (`main` or `backup`);
- row count;
- unique `bar_idx` count;
- duplicate count;
- first/last bar index;
- version set;
- expected grid status;
- SHA256.

For the observed historical files, explicitly record `BU/AO/TA/UR` from backup and `FU` as 792 rows/396 unique bars. Do not silently deduplicate or overwrite during reconciliation.

- [ ] **Step 3: Create the historical manifest**

Run the dry-run scan against the current disk. Save `reports/a2_p1_manifest.json` only after the manifest contains all 20 expected symbols and identifies the FU duplicate condition and the four backup-sourced files.

- [ ] **Step 4: Add a separate canonicalization command**

Implement `--canonicalize` only for a user-approved historical repair. It must:

1. copy missing files from backup only when the destination is absent;
2. refuse conflicts;
3. write a `.bak` before changing an existing file;
4. canonicalize FU by retaining the first record for each `bar_idx` into a new file, never editing the original in place;
5. emit source and destination SHA256 values;
6. stop before report generation if any symbol remains invalid.

- [ ] **Step 5: Document the no-model recovery path**

Add commands to `docs/runbook.md`:

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe scripts/a2_p1_restore_manifest.py --run-id a2-p1 --dry-run
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe scripts/a2_p1_restore_manifest.py --run-id a2-p1 --canonicalize
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe scripts/a2_p1_generate_report.py --run-id a2-p1
```

State clearly that the first two commands do not load TimesFM and that report generation is blocked until all 20 symbols validate.

- [ ] **Step 6: Commit after review approval**

```bash
git add scripts/a2_p1_restore_manifest.py reports/a2_p1_manifest.json tests/test_a2_p1_integrity.py docs/runbook.md STATE.md
git commit -m "ops(a2-p1): reconcile historical results with manifest"
```

---

### Task 7: Final documentation and regression gate

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/runbook.md`
- Modify: `STATE.md`
- Modify: `reports/research/20260806_a2_p1.1_verdict.md` only if validation boundaries change
- Test: `tests/test_a2_p1_integrity.py`, `tests/test_a2_p1_runtime.py`

- [ ] **Step 1: Update the documentation only after the restored report validates**

The final docs must distinguish:

1. original A2-P1 execution log: 20/20 subprocesses completed;
2. canonicalized A2-P1 result set: 20/20 unique and validated, including FU deduplication provenance;
3. A2-P1.1: five isolated result files, 0/5 GO after de-duplication;
4. no A2-P2 start without a new user authorization.

- [ ] **Step 2: Run the complete local verification suite**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m pytest tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py -q
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe -m py_compile scripts/a2_p1_runtime.py scripts/a2_p1_restore_manifest.py scripts/a2_p1_worker.py scripts/a2_p1_orchestrator.py scripts/a2_p1_generate_report.py scripts/a2_p1_lgbm_baseline.py cascade/lgbm_features.py
```

Expected: all tests pass and all listed files compile.

- [ ] **Step 3: Run non-model disk integrity checks**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe scripts/a2_p1_restore_manifest.py --run-id a2-p1 --dry-run
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python.exe scripts/a2_p1_generate_report.py --run-id a2-p1 --validate-only
```

Expected: the dry-run prints 20 symbols, identifies the four backup sources and FU duplicates; `--validate-only` returns non-zero until the historical canonicalization step has been explicitly performed.

- [ ] **Step 4: Final review checklist**

- [ ] No hardcoded `a2_p1_results` or `a2_p1.1_results` remains in Worker/Orchestrator control flow.
- [ ] No fixed `>=300` completion check remains.
- [ ] No `except Exception: tick=1.0` remains in report generation.
- [ ] No Scheme exception writes `scheme_pred_move=0.0`.
- [ ] No report is written before all symbols validate.
- [ ] No A2-P1.1 result is read by an A2-P1 report command.
- [ ] Existing A2-P1.1 three fixes and 13 runtime tests remain passing.

- [ ] **Step 5: Commit after review approval**

```bash
git add docs/README.md docs/runbook.md STATE.md reports/research/20260806_a2_p1.1_verdict.md tests/test_a2_p1_integrity.py tests/test_a2_p1_runtime.py
git commit -m "docs(a2-p1): document canonical results and integrity gates"
```

---

## Self-Review

### Spec coverage

- Missing four main-directory files: Task 6 reconciles main/backup sources and records provenance.
- FU 792/396 duplication: Task 3 rejects duplicates; Task 6 provides non-destructive canonicalization.
- Hardcoded A2-P1/A2-P1.1 paths: Task 1 and Task 5 centralize `RunConfig` and CLI paths.
- Concurrent append race: Task 2 adds run-level and result-level locks plus idempotent writes.
- Fixed `>=300` completion logic: Task 1 replaces it with exact grid comparison.
- Incomplete report overwrite: Task 3 adds fail-closed validation and atomic report replacement.
- Wrong tick-size fallback: Task 3 uses `TICK_SIZES` and fails visibly.
- Silent Scheme exceptions: Task 4 records explicit invalid records and blocks reporting.
- Unstable seeds: Task 4 adds SHA256-based seeds and LightGBM `random_state`.
- Log/timeout audit gaps: Task 5 adds run IDs, manifests and terminal timeout states.
- Cache contamination: Task 5 manifest records feature/config identity; implementation must reject incompatible cache metadata before reuse.
- No-model historical recovery: Task 6 separates restore/canonicalization from model execution.

### Plan completeness scan

All implementation tasks provide concrete files, interfaces, test cases and commands. No unfinished implementation markers or vague cross-task references remain in the task instructions.

### Type consistency

- `RunConfig.for_run()` is the single source of output paths.
- `generate_eval_grid()` is used by Worker and dense feature construction.
- `validate_jsonl_records()` returns the structured validation fields consumed by report generation and manifest creation.
- `stable_symbol_seed()` supplies both NumPy and LightGBM deterministic state.
- `restore_missing_results(..., apply=False)` is dry-run by default and never overwrites existing files.

### Scope boundary

This plan deliberately does not implement a new model, change feature selection, alter the GO gate, launch A2-P2, or run any real backtest. It fixes the evidence pipeline first so any future experiment can be trusted.
