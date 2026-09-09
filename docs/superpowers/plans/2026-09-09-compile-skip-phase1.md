# TimesFM compile 跳过与效率审计第一批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 配置没变时跳过 TimesFM `compile()` 重建解码闭包，并落地 F-001 / F-010 / F-011 / F-005 四条小修。

**Architecture:** 日线与 1H 继续共用一份模型。`ensure_compiled(model, config)` 用 `ForecastConfig` 字段指纹存在 `model._fm_compiled_fp`；一致则跳过，不一致才 `compile`。调用方不改。四条小修不改架构。

**Tech Stack:** Python 3.11，本仓 `.praxist-venv`，pytest（`slow` 标记已在 `tests/conftest.py`），TimesFM 2.5 PyTorch `ForecastConfig`（frozen dataclass）。

**Spec:** `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md`

## Global Constraints

- 活仓：WSL `/home/abug/timesfm`。读改一律 `wsl -d Ubuntu-22.04 -- bash -c "..."`，不要用 Windows 挂载当真相源。
- Python：`.praxist-venv/bin/python`（CPython 3.11）。pytest：`.praxist-venv/bin/python -m pytest`。
- 红线豁免仅本批：`cascade/daily_model.py`、`cascade/hourly_model.py`、`cascade/features.py` 只改与 F-004 / F-010 直接相关的行。
- 禁止改：`.praxist-venv` / TimesFM 底座、`config/prediction_scheme.py`、硬门、`aligned_verdicts.jsonl` 写入方。
- TimesFM `compile()` 只重建解码闭包，不是 `torch.compile`。
- 指纹失败 fail-open：当未编译，走一次 `compile`；`compile` 抛错则不写指纹。
- 常规回归：`pytest -m 'not slow'`。真模型抽查带 `@pytest.mark.slow`。
- 每个 Task 结束必须 commit。提交信息用 HEREDOC。

## File map

| 文件 | 职责 |
|------|------|
| `cascade/daily_model.py` | `forecast_config_fp`、`ensure_compiled`、`FM_COMPILED_FP_ATTR`；`DailyModel` 的 `__init__`/`predict` 改走 `ensure_compiled` |
| `cascade/hourly_model.py` | import 上述符号；`HourlyModel` 的 `__init__`/`predict` 改走 `ensure_compiled` |
| `scripts/monthly_backtest.py` | F-001 `with DataStore`；F-011 `_append_progress` |
| `cascade/features.py` | F-010 模块级 sklearn import |
| `tests/test_compile_skip.py` | F-004 假模型 + slow 真模型 |
| `tests/test_monthly_datastore_close.py` | F-001 |
| `tests/test_progress_log_append.py` | F-011 |
| `tests/test_a2_p1_integrity.py` | F-005 去掉硬编码路径 |
| `tests/test_features_sklearn_import.py` | F-010 |

---

### Task 1: `ensure_compiled` 辅助函数

**Files:**
- Modify: `cascade/daily_model.py`（模块级，`DailyModel` 类之前）
- Test: `tests/test_compile_skip.py`

**Interfaces:**
- Consumes: `timesfm.ForecastConfig`（frozen dataclass，字段见 spec §3.1）
- Produces:
  - `FM_COMPILED_FP_ATTR = "_fm_compiled_fp"`
  - `FP_FIELDS = ("max_context", "max_horizon", "normalize_inputs", "use_continuous_quantile_head", "force_flip_invariance", "infer_is_positive", "fix_quantile_crossing", "return_backcast", "per_core_batch_size")`
  - `forecast_config_fp(config) -> tuple | None`
  - `ensure_compiled(model, config) -> None`：指纹与 `getattr(model, FM_COMPILED_FP_ATTR, None)` 相等则 return；否则 `model.compile(config)`，成功后 `setattr(model, FM_COMPILED_FP_ATTR, fp)`（fp 为 None 则不写）

- [ ] **Step 1: Write the failing tests**

Create `tests/test_compile_skip.py`:

```python
import timesfm
from cascade.daily_model import (
    FP_FIELDS,
    FM_COMPILED_FP_ATTR,
    DailyModel,
    forecast_config_fp,
    ensure_compiled,
)


class FakeModel:
    def __init__(self):
        self.n = 0
        self.last = None

    def compile(self, config, **kwargs):
        self.n += 1
        self.last = config

    def forecast(self, horizon, inputs):
        import numpy as np
        h = horizon
        point = [np.linspace(100.0, 101.0, h)]
        quant = [np.tile(point[0][:, None], (1, 10))]
        return point, quant


def test_fp_none_on_missing_fields():
    assert forecast_config_fp(object()) is None


def test_fp_stable_for_same_config():
    a = DailyModel._DAILY_CONFIG
    b = timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=256,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    )
    assert forecast_config_fp(a) == forecast_config_fp(b)
    assert len(forecast_config_fp(a)) == len(FP_FIELDS)


def test_ensure_compiled_skips_same_fp():
    m = FakeModel()
    cfg = DailyModel._DAILY_CONFIG
    ensure_compiled(m, cfg)
    ensure_compiled(m, cfg)
    assert m.n == 1
    assert getattr(m, FM_COMPILED_FP_ATTR) == forecast_config_fp(cfg)


def test_ensure_compiled_runs_when_config_changes():
    m = FakeModel()
    ensure_compiled(m, DailyModel._DAILY_CONFIG)
    other = timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=128,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
        return_backcast=True,
    )
    ensure_compiled(m, other)
    assert m.n == 2
    assert m.last is other


def test_ensure_compiled_does_not_write_fp_if_compile_raises():
    class Boom(FakeModel):
        def compile(self, config, **kwargs):
            self.n += 1
            raise RuntimeError("compile failed")

    m = Boom()
    try:
        ensure_compiled(m, DailyModel._DAILY_CONFIG)
        raise AssertionError("should raise")
    except RuntimeError:
        pass
    assert m.n == 1
    assert not hasattr(m, FM_COMPILED_FP_ATTR) or getattr(m, FM_COMPILED_FP_ATTR, None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/abug/timesfm
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py -v
```

Expected: FAIL with `ImportError` or `cannot import name 'ensure_compiled'`.

- [ ] **Step 3: Write minimal implementation**

In `cascade/daily_model.py`, after the `DailyResult` dataclass and **before** `class DailyModel`, add:

```python
FM_COMPILED_FP_ATTR = "_fm_compiled_fp"
FP_FIELDS = (
    "max_context",
    "max_horizon",
    "normalize_inputs",
    "use_continuous_quantile_head",
    "force_flip_invariance",
    "infer_is_positive",
    "fix_quantile_crossing",
    "return_backcast",
    "per_core_batch_size",
)


def forecast_config_fp(config):
    try:
        return tuple(getattr(config, name) for name in FP_FIELDS)
    except Exception:
        return None


def ensure_compiled(model, config):
    fp = forecast_config_fp(config)
    if fp is not None and getattr(model, FM_COMPILED_FP_ATTR, None) == fp:
        return
    model.compile(config)
    if fp is not None:
        setattr(model, FM_COMPILED_FP_ATTR, fp)
```

Do not change `DailyModel` yet.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py -v
```

Expected: PASS (the 5 tests above).

- [ ] **Step 5: Commit**

```bash
git add cascade/daily_model.py tests/test_compile_skip.py
git commit -m "$(cat <<'EOF'
feat(cascade): add ensure_compiled skip-if-same-config helper

Fingerprint ForecastConfig on the shared model; skip compile when
unchanged. Fail-open if fingerprint cannot be built.
EOF
)"
```

---

### Task 2: DailyModel / HourlyModel 改走 `ensure_compiled`

**Files:**
- Modify: `cascade/daily_model.py:51-52` 和 `:68-69`（`self.model.compile(self._DAILY_CONFIG)` 两处）
- Modify: `cascade/hourly_model.py:17`（import）、`:82`、`:87`、`:117`
- Test: `tests/test_compile_skip.py`（追加）

**Interfaces:**
- Consumes: `ensure_compiled(model, config)` from Task 1
- Produces: `DailyModel.__init__` / `predict` 与 `HourlyModel.__init__` / `predict` 均调用 `ensure_compiled(self.model, self._DAILY_CONFIG|_XREG_CONFIG)`，不再直接 `self.model.compile(...)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_compile_skip.py`:

```python
import numpy as np
import pandas as pd
from cascade.hourly_model import HourlyModel


class _Store:
    def get_main_continuous(self, limit=250):
        n = max(limit, 40)
        dates = pd.bdate_range("2020-01-02", periods=n)
        return pd.DataFrame({
            "dt": dates,
            "close_price": np.linspace(3000.0, 3100.0, n),
        })


def test_daily_predict_skips_second_compile():
    m = FakeModel()
    model = DailyModel(shared_model=m)
    assert m.n == 1
    store = _Store()
    r1 = model.predict("m", store, context_days=40, horizon_days=22)
    r2 = model.predict("m", store, context_days=40, horizon_days=22)
    assert m.n == 1
    assert np.array_equal(r1.forecast, r2.forecast)


def test_shared_model_daily_then_hourly_must_recompile():
    m = FakeModel()
    DailyModel(shared_model=m)
    n_after_daily = m.n
    HourlyModel(shared_model=m)
    assert m.n == n_after_daily + 1
    ensure_compiled(m, HourlyModel._XREG_CONFIG)
    assert m.n == n_after_daily + 1
    ensure_compiled(m, DailyModel._DAILY_CONFIG)
    assert m.n == n_after_daily + 2
```

These fail until `__init__`/`predict` use `ensure_compiled` (second `DailyModel.predict` currently always compiles → `m.n == 2`).

- [ ] **Step 2: Run tests to verify they fail**

```bash
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py::test_daily_predict_skips_second_compile tests/test_compile_skip.py::test_shared_model_daily_then_hourly_must_recompile -v
```

Expected: `test_daily_predict_skips_second_compile` FAIL (`m.n == 2` or similar).

- [ ] **Step 3: Write minimal implementation**

`cascade/daily_model.py` `__init__` 末尾和 `predict` 开头，把

```python
self.model.compile(self._DAILY_CONFIG)
```

改成

```python
ensure_compiled(self.model, self._DAILY_CONFIG)
```

两处都改（`__init__` 约 L52，`predict` 约 L69）。

`cascade/hourly_model.py` 把

```python
from .daily_model import DailyResult
```

改成

```python
from .daily_model import DailyResult, ensure_compiled
```

把 `__init__` 里两处 `self.model.compile(self._XREG_CONFIG)`（约 L82、L87）和 `predict` 开头约 L117 都改成：

```python
ensure_compiled(self.model, self._XREG_CONFIG)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py -v
```

Expected: PASS，无 slow。

- [ ] **Step 5: Commit**

```bash
git add cascade/daily_model.py cascade/hourly_model.py tests/test_compile_skip.py
git commit -m "$(cat <<'EOF'
feat(cascade): skip TimesFM compile when ForecastConfig fingerprint matches

DailyModel and HourlyModel share one instance; switching configs still
compiles. Consecutive same-config predict (warm daily cache) skips.
EOF
)"
```

---

### Task 3: F-001 `with DataStore`

**Files:**
- Modify: `scripts/monthly_backtest.py:201-206`
- Test: `tests/test_monthly_datastore_close.py`

**Interfaces:**
- Consumes: `data.data_store.DataStore`（已有 `__enter__`/`__exit__` → `close()`）
- Produces: `run_symbol_backtest` 开头用 `with DataStore(symbol) as store:` 读取 `get_main_contract_1h` 与 `get_main_continuous`；块结束后连接关闭。循环内仍用 `BacktestDataStore`。

- [ ] **Step 1: Write the failing test**

Create `tests/test_monthly_datastore_close.py`:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import monthly_backtest as mb


def test_run_symbol_backtest_closes_store_if_read_raises(monkeypatch):
    closed = []

    class Boom:
        def __init__(self, symbol):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            closed.append(True)
            return False
        def close(self):
            closed.append("close")
        def get_main_contract_1h(self, limit=None):
            raise RuntimeError("boom")
        def get_main_continuous(self, limit=None):
            raise AssertionError("should not be reached")

    monkeypatch.setattr(mb, "DataStore", Boom)
    try:
        mb.run_symbol_backtest("ss", None, None)
        raise AssertionError("should raise")
    except RuntimeError as e:
        assert "boom" in str(e)
    assert True in closed
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.praxist-venv/bin/python -m pytest tests/test_monthly_datastore_close.py -v
```

Expected: FAIL（当前手动 `close()` 在 `get_main_contract_1h` 之后，抛错时 `__exit__` 不存在，`closed` 为空）。

- [ ] **Step 3: Write minimal implementation**

Replace `scripts/monthly_backtest.py` 约 201-206:

```python
    store = DataStore(symbol)
    all_1h = store.get_main_contract_1h(limit=99999)

    # 检查日线数据可用性 (daily model 需要 CONTEXT_DAYS 天)
    daily_df = store.get_main_continuous(limit=99999)
    store.close()
```

with:

```python
    with DataStore(symbol) as store:
        all_1h = store.get_main_contract_1h(limit=99999)
        daily_df = store.get_main_continuous(limit=99999)
```

Do not change the later `BacktestDataStore` loop.

- [ ] **Step 4: Run test to verify it passes**

```bash
.praxist-venv/bin/python -m pytest tests/test_monthly_datastore_close.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/monthly_backtest.py tests/test_monthly_datastore_close.py
git commit -m "$(cat <<'EOF'
fix(backtest): close DataStore via context manager on read errors
EOF
)"
```

---

### Task 4: F-010 sklearn 模块级 import

**Files:**
- Modify: `cascade/features.py:11-14`（imports）和 `:210-211`（删函数内 import）
- Test: `tests/test_features_sklearn_import.py`

**Interfaces:**
- Consumes: `sklearn.decomposition.PCA`, `sklearn.preprocessing.StandardScaler`
- Produces: `cascade.features.PCA` 与 `cascade.features.StandardScaler` 在模块加载时可用；`calc_pca_momentum` 不再内部 import

- [ ] **Step 1: Write the failing test**

Create `tests/test_features_sklearn_import.py`:

```python
import inspect
import cascade.features as feat


def test_pca_symbols_are_module_level():
    assert getattr(feat, "PCA", None) is not None
    assert getattr(feat, "StandardScaler", None) is not None
    src = inspect.getsource(feat.calc_pca_momentum)
    assert "from sklearn" not in src
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.praxist-venv/bin/python -m pytest tests/test_features_sklearn_import.py -v
```

Expected: FAIL（`PCA` 不在模块上，或源码仍含 `from sklearn`）。

- [ ] **Step 3: Write minimal implementation**

In `cascade/features.py` 顶部 imports 增加：

```python
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
```

Delete the two lines inside `calc_pca_momentum`（约 L210-211）：

```python
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
```

Do not wrap in custom try/except.

- [ ] **Step 4: Run test to verify it passes**

```bash
.praxist-venv/bin/python -m pytest tests/test_features_sklearn_import.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cascade/features.py tests/test_features_sklearn_import.py
git commit -m "$(cat <<'EOF'
fix(features): import sklearn PCA/StandardScaler at module level
EOF
)"
```

---

### Task 5: F-011 progress.log 追加

**Files:**
- Modify: `scripts/monthly_backtest.py`（新增 `_append_progress`；约 L902-949 的 `write_text` 全部改走它）
- Test: `tests/test_progress_log_append.py`

**Interfaces:**
- Consumes: `pathlib.Path`
- Produces: `def _append_progress(path, line: str) -> None`：以 `"a"` 写入 `line`（调用方保证换行）；`OSError` 时 `print` 警告并 return，不抛。`main` 里所有 `progress_log.write_text(...)` 改为 `_append_progress(progress_log, ...)`。

- [ ] **Step 1: Write the failing test**

Create `tests/test_progress_log_append.py`:

```python
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import monthly_backtest as mb


def test_append_progress_keeps_prior_lines(tmp_path):
    p = tmp_path / "progress.log"
    mb._append_progress(p, "START\n")
    mb._append_progress(p, "SS START\n")
    text = p.read_text(encoding="utf-8")
    assert text.splitlines() == ["START", "SS START"]


def test_append_progress_swallows_oserror(tmp_path, monkeypatch):
    p = tmp_path / "progress.log"
    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(Path, "open", boom, raising=False)
    # 直接补丁 _append_progress 使用的 open：改 path 为不可写目录也可。
    # 用 monkeypatch 让 Path.open 抛错：
    orig = Path.open
    def _open(self, *a, **k):
        raise OSError("disk")
    monkeypatch.setattr(Path, "open", _open)
    mb._append_progress(p, "X\n")  # 不得抛
```

If `Path.open` patch is too broad, use this instead for the second test:

```python
def test_append_progress_swallows_oserror(tmp_path, monkeypatch):
    p = tmp_path / "no_such_dir" / "progress.log"
    mb._append_progress(p, "X\n")
```

Parent dir missing → `OSError`/`FileNotFoundError` swallowed.

- [ ] **Step 2: Run tests to verify they fail**

```bash
.praxist-venv/bin/python -m pytest tests/test_progress_log_append.py -v
```

Expected: FAIL `AttributeError: _append_progress`.

- [ ] **Step 3: Write minimal implementation**

Near other helpers in `scripts/monthly_backtest.py` (after imports / before `run_symbol_backtest`):

```python
def _append_progress(path, line: str) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        print(f"  [WARN] progress log write failed: {e}")
```

Replace every `progress_log.write_text(...)` in `main`（约 L903、907-908、920-921、927-928、939-942、946-947、949）with `_append_progress(progress_log, <same string>)`. Keep the original line contents including trailing `\n`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.praxist-venv/bin/python -m pytest tests/test_progress_log_append.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/monthly_backtest.py tests/test_progress_log_append.py
git commit -m "$(cat <<'EOF'
fix(backtest): append progress.log instead of overwriting
EOF
)"
```

---

### Task 6: F-005 测试根路径

**Files:**
- Modify: `tests/test_a2_p1_integrity.py:68,77,86,93,103,111`
- Test: 同文件（改完后这些测试本身即验收）；另在文件中加一条静态断言

**Interfaces:**
- Consumes: `Path(__file__).resolve().parent.parent`（仓库根，已有先例 L10）
- Produces: 上述 6 处 `root = Path("D:/FlyBuddy/fm_a")` 全部改为仓库根。源码不再出现 `D:/FlyBuddy/fm_a`。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_a2_p1_integrity.py`:

```python
def test_integrity_file_has_no_hardcoded_windows_root():
    src = Path(__file__).read_text(encoding="utf-8")
    assert "D:/FlyBuddy/fm_a" not in src
    root = Path(__file__).resolve().parent.parent
    assert (root / "cascade").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.praxist-venv/bin/python -m pytest tests/test_a2_p1_integrity.py::test_integrity_file_has_no_hardcoded_windows_root -v
```

Expected: FAIL（源码仍含该字符串）。

- [ ] **Step 3: Write minimal implementation**

At the 6 `RunConfig` tests, replace

```python
    root = Path("D:/FlyBuddy/fm_a")
```

with

```python
    root = Path(__file__).resolve().parent.parent
```

Do not change other `Path(__file__).parent.parent` uses.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.praxist-venv/bin/python -m pytest tests/test_a2_p1_integrity.py::test_run_config_never_uses_a2_p1_1_for_a2_p1_by_default tests/test_a2_p1_integrity.py::test_run_config_isolated_for_a2_p1_1 tests/test_a2_p1_integrity.py::test_run_config_symbols_lowercased tests/test_a2_p1_integrity.py::test_run_config_unsupported_run_id tests/test_a2_p1_integrity.py::test_run_config_features_dir_shared tests/test_a2_p1_integrity.py::test_run_config_frozen tests/test_a2_p1_integrity.py::test_integrity_file_has_no_hardcoded_windows_root -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_a2_p1_integrity.py
git commit -m "$(cat <<'EOF'
test: resolve a2-p1 integrity fixture root from __file__
EOF
)"
```

---

### Task 7: F-004 真模型慢测

**Files:**
- Modify: `tests/test_compile_skip.py`（追加 `@pytest.mark.slow`）
- Test: 同文件

**Interfaces:**
- Consumes: 真实 `DailyModel()` / `HourlyModel(shared_model=daily.model)`；`data.data_store.BacktestDataStore`；`ensure_compiled`
- Produces: 3 个 cutoff 上，路径 A（跳过逻辑，默认 `predict`）与路径 B（每次 `predict` 前强制 `model.compile(config)`）的日线 `forecast`、1H `point_forecast` 均 `np.array_equal`

- [ ] **Step 1: Write the failing test (it should pass if Task 2 is correct; still add it now as the spec-mandated slow gate)**

Append to `tests/test_compile_skip.py`:

```python
import pytest
from data.data_store import BacktestDataStore
from cascade.daily_model import DailyResult


@pytest.mark.slow
def test_skip_vs_force_compile_bitexact_real_model():
    daily = DailyModel()
    hourly = HourlyModel(shared_model=daily.model)
    cutoffs = [
        "2021-01-05 14:00:00",
        "2021-01-11 09:00:00",
        "2021-01-14 13:00:00",
    ]
    for cutoff in cutoffs:
        store = BacktestDataStore("m", cutoff)
        try:
            r_skip = daily.predict("m", store, context_days=250, horizon_days=22)
            daily.model.compile(DailyModel._DAILY_CONFIG)
            setattr(daily.model, FM_COMPILED_FP_ATTR, None)
            r_force = daily.predict("m", store, context_days=250, horizon_days=22)
            assert np.array_equal(r_skip.forecast, r_force.forecast), cutoff

            h_skip = hourly.predict(
                "m", store, r_skip, horizon=24, visualize=False,
                covariate_type="ccl", verbose=False,
            )
            hourly.model.compile(HourlyModel._XREG_CONFIG)
            setattr(hourly.model, FM_COMPILED_FP_ATTR, None)
            h_force = hourly.predict(
                "m", store, r_force, horizon=24, visualize=False,
                covariate_type="ccl", verbose=False,
            )
            assert np.array_equal(h_skip.point_forecast, h_force.point_forecast), cutoff
        finally:
            store.close()
```

If `BacktestDataStore` supports `with`, prefer `with BacktestDataStore("m", cutoff) as store:`.

- [ ] **Step 2: Run the fast suite (must not collect this test)**

```bash
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py tests/test_monthly_datastore_close.py tests/test_features_sklearn_import.py tests/test_progress_log_append.py -m 'not slow' -v
```

Expected: PASS，且 `test_skip_vs_force_compile_bitexact_real_model` deselected。

- [ ] **Step 3: Run the slow test once**

```bash
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py::test_skip_vs_force_compile_bitexact_real_model -v
```

Expected: PASS（需本机权重与 `db/futures_m.db`）。若无数据：标 skip 的条件是 `BacktestDataStore` 读空，用 `pytest.skip("no m 1h data")` 包住，不要假绿。实现时若 `get_main_continuous` 为空则 `pytest.skip`。

在测试开头加：

```python
        probe = BacktestDataStore("m", cutoffs[0])
        try:
            df = probe.get_main_continuous(limit=30)
            if df is None or getattr(df, "empty", True):
                pytest.skip("no m daily data")
        finally:
            probe.close()
```

- [ ] **Step 4: Run broader non-slow regression**

```bash
.praxist-venv/bin/python -m pytest tests/test_compile_skip.py tests/test_monthly_datastore_close.py tests/test_features_sklearn_import.py tests/test_progress_log_append.py tests/test_a2_p1_integrity.py tests/test_daily_pred_cache.py -m 'not slow' -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/test_compile_skip.py
git commit -m "$(cat <<'EOF'
test: bit-exact skip vs force compile on real TimesFM (slow)
EOF
)"
```

---

## Self-review vs spec

| Spec 要求 | Task |
|---|---|
| `_ensure_compiled` 同配置跳过 | Task 1–2（函数名 `ensure_compiled`） |
| 日线↔1H 切换必 compile | Task 2 `test_shared_model_daily_then_hourly_must_recompile` |
| 假模型逐位一致 | Task 2 `test_daily_predict_skips_second_compile` |
| 真模型 slow 逐位一致 | Task 7 |
| F-001 with DataStore | Task 3 |
| F-010 模块级 sklearn | Task 4 |
| F-011 追加 progress.log | Task 5 |
| F-005 无硬编码路径 | Task 6 |
| 指纹字段列表 | Task 1 `FP_FIELDS` |
| fail-open / compile 失败不写指纹 | Task 1 |
| 不改 Praxist 核心、不加第二份模型、不加 checkpoint 锁、不上 GPU empty_cache | 全任务未涉及 |
| 后续 spec 清单 | 仅在 design spec §8，本计划不实施 |

无 TBD。名称前后一致：`ensure_compiled`、`forecast_config_fp`、`FM_COMPILED_FP_ATTR`、`FP_FIELDS`。
