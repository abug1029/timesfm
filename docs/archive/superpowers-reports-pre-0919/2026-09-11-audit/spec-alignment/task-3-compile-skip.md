# Task 3: Compile-skip + 效率五条 条款对齐

> 审核日期: 2026-09-11
> 活仓: `/home/abug/timesfm`（HEAD `9653264`，`master` 比 `origin/master` 超前 1）
> Spec: `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md` §3–§9
> 范围: 只读。本文件是允许写入的报告。
> 判定口径: 看代码与测试，不看 spec 状态栏「待审阅」、不看计划里未勾的 `- [ ]`。

## 0. 总判定

**有效性: 仍有效。** 没有后续合同废止指纹跳过或这五条小修。hardening SPEC-004…013 改过 `daily_model.py` / `features.py`，但没有拿掉 `ensure_compiled`。`docs/praxist.md` §5 仍把「重复 compile、连接泄漏」写成未动的性能债，那是文档滞后，不是杀手。

**对齐判定: 对齐。**

落地链（均为当前 HEAD 祖先）：

| 提交 | 内容 |
|---|---|
| `a8b0b6b` | `ensure_compiled` + 指纹辅助函数 + 假模型测试 |
| `b32ec93` | Daily/Hourly `__init__`/`predict` 改走 `ensure_compiled` |
| `721ee47` | F-001 `with DataStore` |
| `e35a31d` | F-010 模块级 sklearn |
| `08ac006` | F-011 `progress.log` 追加 |
| `d04da28` | F-005 测试根路径 |
| `3dff2d0` / `b354b5e` | 真模型 slow 逐位一致 + warmup |

函数名是 `ensure_compiled`（无前导下划线）。spec 架构图写 `_ensure_compiled`，实施计划已点名「函数名 `ensure_compiled`」。以代码与计划为准，不记缺口。

本轮非 slow 回归：13 passed，1 deselected（`test_skip_vs_force_compile_bitexact_real_model`）。slow 测未跑，但源码与 `@pytest.mark.slow` 标记在。

---

## 1. 条款表（§3–§9）

| # | 条款 | spec | 代码 / 测试 | 判定 |
|---|---|---|---|---|
| 3 | 共用模型 + `_ensure_compiled` 分流 | spec:56-62 | `cascade/daily_model.py:53-59` `ensure_compiled` | 对齐（名无下划线） |
| 3 | 调用方形状不改；缓存命中不进日线 `predict` | spec:64 | `monthly_backtest.py:165-173` `_daily_predict_cached`；`cascade_predict.py` / `aligned_slow_loop.py` 仍 `DailyModel`+`HourlyModel(shared_model=…)` | 对齐 |
| 3 | 热缓存：连续 1H 跳过，直到日线未命中切走配置 | spec:66-70 | 日线 `predict` 写日线指纹，1H `predict` 写 1H 指纹；缓存命中则日线 `predict` 不跑 | 对齐 |
| 3.1 | 指纹九字段 | spec:80 | `FP_FIELDS` `daily_model.py:33-43` 九项一字不差 | 对齐 |
| 3.1 | 缺字段 / 配不上 → 视为未编译 | spec:82 | `forecast_config_fp` 捕获异常返回 `None`；`fp is None` 则必 `compile` 且不写指纹 | 对齐 |
| 3.2 | 同配置跳过；切换必编；`compile` 抛错不写指纹 | spec:87-92 | `ensure_compiled`：先比指纹，`compile` 成功后才 `setattr` | 对齐 |
| 3 | 辅助函数只放 `daily_model.py`，hourly import；不新建包 | spec:74 | `hourly_model.py:17` | 对齐 |
| 4.1 F-001 | `run_symbol_backtest` 开头 `with DataStore`；循环用 `BacktestDataStore`；不改 `data_store.py` | spec:100 | `monthly_backtest.py:209-211`；循环 `283` 起用 `BacktestDataStore`；`DataStore.__exit__` 已有 `close()` | 对齐 |
| 4.2 F-010 | 模块级 `PCA` / `StandardScaler`；去掉函数内 import | spec:104-111 | `features.py:15-16`；`calc_pca_momentum` 源码无 `from sklearn` | 对齐 |
| 4.3 F-011 | `progress.log` 追加；不存在则创建；失败警告不中断；不加 run id | spec:113-115 | `_append_progress` `monthly_backtest.py:176-181`，`open(..., "a")` + `OSError` 打 `[WARN]` | 对齐 |
| 4.4 F-005 | `Path(__file__).resolve().parent.parent`；不断言绝对路径；断言有 `cascade/` | spec:117-119 | `tests/test_a2_p1_integrity.py:68+` 与 `1181-1185` | 对齐 |
| 5 | 无指纹属性 / 字段缺失 / compile 失败 / 读库 / 无 sklearn / 写 log 失败 | spec:124-132 | 与上表同一实现 | 对齐 |
| 6.1 | 连续同配置：两次 Daily `predict`，`compile==1`；Hourly 同理 | spec:140 | `test_daily_predict_skips_second_compile`；Hourly 假模型未直接两次 `predict`（见 §3 观察） | 对齐（Hourly 由 helper + slow 覆盖） |
| 6.2 | 日线再 1H，共享同一 `model`，第二次必 compile | spec:141 | `test_shared_model_daily_then_hourly_must_recompile` | 对齐 |
| 6.3 | 假模型跳过 vs 每次 compile，数组 `array_equal` | spec:142 | 假模型 `forecast` 不依赖 compile；`test_daily_predict_skips_second_compile` 比两次 `forecast` | 对齐 |
| 6.4 | `@pytest.mark.slow` 真模型，3 个 cutoff，skip vs force | spec:143 | `test_skip_vs_force_compile_bitexact_real_model`；`b354b5e` 加 warmup | 对齐（本轮未跑 slow） |
| 6.5 F-001 | 读库抛错时 `__exit__` 被调 | spec:144 | `tests/test_monthly_datastore_close.py` | 对齐 |
| 6.6 F-005 | 根含 `cascade/`，源码无 `D:/FlyBuddy/fm_a` | spec:145 | `test_integrity_file_has_no_hardcoded_windows_root` | 对齐 |
| 6.7 F-010 | 模块字典含 `PCA`、`StandardScaler` | spec:146 | `tests/test_features_sklearn_import.py` | 对齐 |
| 6.8 F-011 | 连续两写，文件两行 | spec:147 | `tests/test_progress_log_append.py` | 对齐 |
| 7 | 非目标：不改底座、硬门、SCHEMES；不加第二份模型；不加 checkpoint flock；不上 F-006 GPU；不迁 logging；不加速 Hurst/iterrows | spec:152-159 | 本批提交只动点名文件 + 测试 | 对齐（未越界） |
| 8 | 其余审计 ID 不实施 | spec:163-186 | 仓内无对应独立落地（本任务不评那些缺口） | 失效于本 spec 范围（按设计不做） |
| 9 | 八条验收框 | spec:190-199 | 代码与测试满足；文档框仍是 `- [ ]` | 代码对齐；文档框过期 |

---

## 2. F-004 指纹跳过（细核）

### 2.1 字段

spec §3.1 要求至少：

`max_context, max_horizon, normalize_inputs, use_continuous_quantile_head, force_flip_invariance, infer_is_positive, fix_quantile_crossing, return_backcast, per_core_batch_size`

`cascade/daily_model.py:33-43` 完全一致。

TimesFM 2.5 `ForecastConfig` 另有 `window_size`（标注 TODO，未实现）。`timesfm_2p5_torch.py` 的 `compile()` 闭包用到的是：`max_horizon`、`normalize_inputs`、`infer_is_positive`、`force_flip_invariance`、`use_continuous_quantile_head`、`return_backcast`、`fix_quantile_crossing`，以及实例上的 `per_core_batch_size`。`window_size` 不进闭包。指纹相对「会改变解码闭包的字段」是完整的，不是少字段。

日线 `_DAILY_CONFIG` 不写 `return_backcast`（默认 `False`），1H `_XREG_CONFIG` 写 `True`；`max_horizon` 256 vs 128。切换必编。

### 2.2 跳过条件

```53:59:cascade/daily_model.py
def ensure_compiled(model, config):
    fp = forecast_config_fp(config)
    if fp is not None and getattr(model, FM_COMPILED_FP_ATTR, None) == fp:
        return
    model.compile(config)
    if fp is not None:
        setattr(model, FM_COMPILED_FP_ATTR, fp)
```

- 指纹存在且相等 → 跳过（spec 3.2 连续 1H / 连续日线）。
- 无 `_fm_compiled_fp`、字段取不到、`fp is None` → 当未编译（fail-open）。
- `model.compile` 抛错 → 不执行 `setattr`（`test_ensure_compiled_does_not_write_fp_if_compile_raises`）。
- 指纹存在共享 `model` 实例上，不是进程全局，也不是 Daily/Hourly 各自一份。符合 §2 决策表。

`DailyModel.__init__`/`predict`、`HourlyModel.__init__`/`predict` 四处原 `self.model.compile(...)` 均已换成 `ensure_compiled`。`cascade/` 生产路径不再直接 `model.compile`（测试里 force 路径除外）。

### 2.3 调用方与缓存

`scripts/monthly_backtest.py:165-173`：缓存命中直接 `return hit`，不进 `DailyModel.predict`，因此不走 `ensure_compiled`。与 spec:64 一致。热缓存慢环里浪费集中在连续 1H `predict`，正是跳过要吃的场景。

`scripts/aligned_slow_loop.py`、`scripts/cascade_predict.py`、`scripts/copilot.py` 仍是 `DailyModel()` + `HourlyModel(shared_model=daily.model)`，调用形状未改。

### 2.4 测试对照验收框

| spec §9 | 测试 | 本轮 |
|---|---|---|
| 同配置连续 `predict` 不 compile | `test_ensure_compiled_skips_same_fp`；`test_daily_predict_skips_second_compile`（`m.n == 1`） | 过 |
| 日线↔1H 必 compile | `test_shared_model_daily_then_hourly_must_recompile`；`test_ensure_compiled_runs_when_config_changes` | 过 |
| 假模型 / 真模型逐位 | 假：两次 `forecast` `array_equal`；真：slow 测 skip vs `compile`+清指纹 | 假过；真未跑 |
| 常规回归不含 slow | `pytest -m 'not slow'` 本子集 13 passed, 1 deselected | 过 |

---

## 3. 其余四条（无架构分叉）

### 3.1 F-001 DataStore close

```209:211:scripts/monthly_backtest.py
    with DataStore(symbol) as store:
        all_1h = store.get_main_contract_1h(limit=99999)
        daily_df = store.get_main_continuous(limit=99999)
```

`data/data_store.py:217-219`：`__exit__` 调 `close()`，返回 `False`（不吞异常）。测试 `test_run_symbol_backtest_closes_store_if_read_raises` 在 `get_main_contract_1h` 抛错时断言 `__exit__` 被调用。循环内改用 `BacktestDataStore`，生产 `DataStore` 不进评估点。符合 §4.1。

### 3.2 F-010 sklearn 模块级 import

`cascade/features.py:15-16` 顶部 `from sklearn.decomposition import PCA` / `from sklearn.preprocessing import StandardScaler`。`calc_pca_momentum`（约 L202）只用这两个名字，无函数内 import。无自定义文案包装。`test_pca_symbols_are_module_level` 同时查模块字典和函数源码。

### 3.3 F-011 progress.log 追加

所有原 `progress_log.write_text(...)` 收进 `_append_progress`。`open(path, "a")`：文件不存在则创建。`OSError` 打印警告后返回。文件名仍是 `BACKTEST_DIR / "progress.log"`，无 run id。测试：两行保留；缺父目录不抛。

### 3.4 F-005 测试根路径

活仓 `tests/test_a2_p1_integrity.py` 已无 `Path("D:/FlyBuddy/fm_a")`（仅断言字符串拼接 `"D:/FlyBuddy/" + "fm_a"` 不出现在源码里，避免测试自己误伤）。根用 `Path(__file__).resolve().parent.parent`，并断言 `(root / "cascade").is_dir()`。

---

## 4. 观察（不升格为缺口）

这些不是「有效设计代码没有或写反」。

1. **文档状态过期（LOW）**  
   spec 头「待审阅」、§9 八个 `- [ ]`、实施计划 35 个未勾。代码已在 `a8b0b6b`…`b354b5e` merge。用户已声明以代码为准。建议另开文档修补，不在本审计改 spec。

2. **过期注释（LOW）**  
   `daily_model.py:83,100`、`hourly_model.py:81,117` 仍写「每次 predict 前重新 compile」。实际已是 `ensure_compiled`。误导阅读，不影响行为。

3. **假模型没有两次 `HourlyModel.predict`（LOW）**  
   spec §6.1 写「两次 HourlyModel.predict 同理」。`HourlyModel.predict` 会走数据校验 / `forecast_with_covariates`，假模型撑不住完整 `predict`。代码 `hourly_model.py:118` 已调用 `ensure_compiled`；helper 级 skip + slow 真模型两次 1H `predict` 覆盖语义。实施计划 Task 2 也是这样映射的。

4. **`docs/praxist.md` §5（LOW，文档）**  
   仍把「重复 compile、连接泄漏」列为预测链性能债。与本 spec 已落地矛盾。不是代码缺口。

5. **范围外残留（不记本 spec 缺口）**  
   - `tests/test_a2_p2_integrity.py:14,25` 仍 `Path("D:/FlyBuddy/fm_a")`。spec 只点名 `test_a2_p1_integrity.py`。A2-P2 已被 STATE 关轨，属 Task 7。  
   - `scripts/predict.py:253` 仍直接 `model.compile(...)`。这是独立 CLI，不走 `DailyModel`/`HourlyModel`。spec 点名的调用方是 `_daily_predict_cached` / `HourlyModel.predict` / `cascade_predict`。  
   - 评估点循环里 `BacktestDataStore(...)` 没有 `with`/`close`（`monthly_backtest.py:283`）。F-001 原文只修开头生产 `DataStore` 漏连接，明确不改 `data_store.py`。若要收，另开 spec。

6. **slow 真模型本轮未执行**  
   标记与实现在。常规门禁按 spec 排除 slow。不能凭本轮未跑断言真模型数值回归失败。

---

## 5. 缺口清单

无。有效条款没有「仓内无此符号」或写反。

Critical 门槛：有效 spec 与活生产路径相反且会改错信号/硬门/收割。本批是 compile 次数与连接/import/日志/测试路径，不碰 SCHEMES、硬门、收割。无 Critical。

---

## 6. 测试证据

命令（WSL `/home/abug/timesfm`，`.praxist-venv`）：

```
.praxist-venv/bin/python -m pytest \
  tests/test_compile_skip.py \
  tests/test_monthly_datastore_close.py \
  tests/test_progress_log_append.py \
  tests/test_features_sklearn_import.py \
  tests/test_a2_p1_integrity.py::test_integrity_file_has_no_hardcoded_windows_root \
  tests/test_a2_p1_integrity.py::test_run_config_never_uses_a2_p1_1_for_a2_p1_by_default \
  -m "not slow" -q
```

结果：`13 passed, 1 deselected in 12.47s`。

收集到的 compile-skip 用例 8 个，其中 1 个 slow。

---

## 7. 给 Task 8 的一行

| spec | 有效性 | 对齐 | Critical/High 缺口 |
|---|---|---|---|
| `2026-09-09-compile-skip-phase1-design.md` | 仍有效（状态栏过期） | **对齐** | 0 |

建议（不在本任务改代码）：把 spec 状态改为已落地；勾 §9；顺手改掉「每次重新 compile」注释；`praxist.md` §5 把 F-004/F-001/F-010/F-011/F-005 移到已落地。
