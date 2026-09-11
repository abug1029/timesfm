# TimesFM compile 跳过与效率审计第一批 (Spec)

> **文档状态（2026-09-11）**：**已落地**（`ensure_compiled`，自 `a8b0b6b`）。状态栏「待审阅」过期。勿当待开工。空验收框不表示未实现。

日期: 2026-09-09
状态: 已落地（2026-09-11 标注；原「待审阅」过期）
前序文档:
- `docs/audit_system_efficiency_20260908.md`（22 条发现；本 spec 只落地其中 5 条）
- `docs/host_environment_assessment.md`（WSL2，7.7 GiB，无 GPU）
- `docs/praxist.md`（慢环是唯一验证器；日线预测已按 cutoff 缓存）

审计原文 ID：F-004（主）、F-001、F-010、F-011、F-005。
红线豁免（本批经人工批准）：允许改 `cascade/daily_model.py`、`cascade/hourly_model.py`、`cascade/features.py`，且只改与上述 ID 直接相关的行。

---

## 1. 背景与问题

慢环 walk-forward 每个评估点走「日线 → 1H」。日线和 1H 共用一份 TimesFM 权重（约 800MB），配置不同：

- 日线：`max_horizon=256`，无 `return_backcast`
- 1H：`max_horizon=128`，`return_backcast=True`

当前两边的 `predict()` **每次无条件** `self.model.compile(...)`。注释动机成立：对方可能刚把配置改掉。但日线缓存命中时根本不会进 `DailyModel.predict`，模型已停在上一轮 1H 配置上，`HourlyModel.predict` 仍会再 `compile` 一次。

TimesFM 2.5 PyTorch 的 `compile()` **不是** `torch.compile` / TorchScript。它校验 `ForecastConfig`、把 `forecast_config` 写到实例上、重建 `_compiled_decode` 闭包。审计把开销写成「torch.compile」是过时判断。本批优化的是：**配置没变时不要反复重建闭包**。热缓存慢环里，浪费集中在连续的 1H `predict`。

顺手四条不加快推理，但改动面小、和同一批回测路径相关：

- F-001：`run_symbol_backtest` 开头 `DataStore` 手动 `close()`，读库抛错会漏 SQLite 连接
- F-010：`sklearn` PCA / StandardScaler 在函数内 import，缺依赖拖到第一次算 PCA 才爆
- F-011：`progress.log` 用 `write_text` 覆盖，并发/重跑丢历史进度
- F-005：`tests/test_a2_p1_integrity.py` 硬编码 `D:/FlyBuddy/fm_a`，WSL 上失败

---

## 2. 设计决策总览

| 决策 | 选择 | 放弃的备选 |
|---|---|---|
| 避免重复 compile | 共用模型 + 配置指纹一致则跳过（方案 A） | 日线/1H 各持一份已编译模型（内存翻倍）；只在 `monthly_backtest` 循环里手动切配置（其它入口享受不到） |
| 指纹存放 | 共享 `model` 实例属性（如 `_fm_compiled_fp`） | 进程全局变量；DailyModel/HourlyModel 各自记（看不见对方刚编过什么） |
| 指纹内容 | `ForecastConfig` 里会改变解码闭包行为的字段元组 | 依赖 `ForecastConfig ==`（未必实现）；只比对象 `id()`（同字段不同实例会误编） |
| 指纹失败 | fail-open：当未编译，走一次 `compile` | fail-closed 抛错（给预测路径引入新失败模式） |
| F-004 验收 | 假模型核对调用次数 + 逐位数值；另加 `@pytest.mark.slow` 真模型抽查 | 只数 `compile` 次数；或只信现有回测兜底 |
| 本 spec 范围 | F-004 + F-001 + F-010 + F-011 + F-005 | 整份 22 条一次落地 |
| F-006 GPU empty_cache | 不适用（宿主无 GPU） | 按审计原文做 |
| F-003 checkpoint flock | 降优先级（慢环单实例锁 + 单写入者约定已成立） | 本批加锁 |

---

## 3. 架构

```
DailyModel.predict / HourlyModel.predict
        |
        v
_ensure_compiled(model, config)
        |
        +-- 指纹 == model._fm_compiled_fp  --> 跳过 compile
        |
        +-- 否则 --> model.compile(config)
                    model._fm_compiled_fp = fingerprint(config)
```

调用方（`monthly_backtest._daily_predict_cached`、`HourlyModel.predict`、`cascade_predict`）不改调用形状。日线缓存命中仍完全跳过 `DailyModel.predict`，不经过 `_ensure_compiled`。

热缓存慢环一个品种：

1. 点 1 缓存未命中：日线 compile（日线配置）→ 1H compile（1H 配置）
2. 点 2 缓存命中：不进日线 `predict` → 1H `predict` 指纹已是 1H → **跳过**
3. 之后同品种 1H 点：继续跳过，直到有日线缓存未命中把配置切走

`cascade_predict` 单次日线+1H 几乎省不到（必须切一次配置），行为与现在一致。

辅助函数放在 `cascade/daily_model.py`（日线先加载），`hourly_model.py` import 它。不新建包、不加配置文件。

### 3.1 指纹字段

至少包含会改变 `_compiled_decode` 闭包的字段：

`max_context`, `max_horizon`, `normalize_inputs`, `use_continuous_quantile_head`, `force_flip_invariance`, `infer_is_positive`, `fix_quantile_crossing`, `return_backcast`, `per_core_batch_size`

缺字段或 `forecast_config` 为 None：视为未编译。

### 3.2 数据流（与现状对比）

| 场景 | 现在 | 本批之后 |
|---|---|---|
| 日线 `predict` 接在 1H 之后 | 必 compile 日线配置 | 必 compile（指纹变了） |
| 1H `predict` 接在日线之后 | 必 compile 1H 配置 | 必 compile（指纹变了） |
| 连续两次 1H（日线缓存命中） | 仍 compile | 跳过 |
| 连续两次日线 | 仍 compile | 跳过 |
| `compile()` 抛错 | 上抛 | 上抛，不写指纹 |

---

## 4. 其余四条（无架构分叉）

### 4.1 F-001 DataStore 连接

`scripts/monthly_backtest.py` 的 `run_symbol_backtest`：开头用 `with DataStore(symbol) as store:` 读 `get_main_contract_1h` 与 `get_main_continuous`，块结束即 close。后面评估点继续用 `BacktestDataStore`，不把生产 `DataStore` 拖进循环。`DataStore` 已有 `__enter__` / `__exit__`，不改 `data_store.py`。

### 4.2 F-010 sklearn 模块级 import

`cascade/features.py` 顶部：

```python
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
```

去掉 `calc_pca_momentum`（约 L210）的函数内 import。缺包时 import `cascade.features` 立即失败。不包一层自定义文案（保持 traceback 原样）。

### 4.3 F-011 progress.log 追加

同一函数内所有 `progress_log.write_text(...)` 改为追加（`open(..., "a")` 或等价）。文件不存在则创建。追加失败只打印警告，不中断回测。不在文件名里加 run id（单写入者约定下追加已够）。

### 4.4 F-005 测试根路径

`tests/test_a2_p1_integrity.py` 中所有 `Path("D:/FlyBuddy/fm_a")` 改为 `Path(__file__).resolve().parent.parent`。不断言绝对路径字符串，只断言根下存在 `cascade/`。

---

## 5. 错误处理

| 情况 | 行为 |
|---|---|
| 模型上无 `_fm_compiled_fp` | 当作未编译，调用 `compile`，成功后写入指纹 |
| 指纹字段缺失 / 非预期类型 | 当作未编译 |
| `model.compile` 抛错 | 原样上抛；不更新指纹 |
| F-001 读库抛错 | `with` 退出必 close |
| F-010 无 sklearn | import 阶段失败 |
| F-011 写 progress.log 失败 | 警告，回测继续 |

---

## 6. 测试

新文件 `tests/test_compile_skip.py`。假模型不加载 TimesFM 权重。

1. **连续同配置**：两次 `DailyModel.predict`（假模型），`compile` 调用次数 = 1。两次 `HourlyModel.predict` 同理。
2. **切换配置**：日线再 1H，第二次必须调用 `compile`。共享同一 `model` 对象。
3. **数值**：假模型 `compile` 不改变返回值；跳过路径与「每次都 compile」的日线 `forecast`、1H `point_forecast` 用 `np.array_equal`。
4. **`@pytest.mark.slow`**：真实 `DailyModel`/`HourlyModel`（共享权重），少量 cutoff（与 `test_daily_pred_cache.py` 同量级，例如 3 个）。路径 A 走 `_ensure_compiled`；路径 B 每次强制 `compile`。日线 `forecast` 与 1H `point_forecast` 必须 `np.array_equal`。常规 `pytest -m 'not slow'` 不跑。
5. **F-001**：`get_main_contract_1h` 抛错时 `__exit__` 被调用（可用包装/spy）。
6. **F-005**：解析到的根包含 `cascade/`，源码字符串不含 `D:/FlyBuddy/fm_a`。
7. **F-010**：`cascade.features` 模块字典含 `PCA`、`StandardScaler`。
8. **F-011**：连续两次写 progress，文件含两行而非只剩最后一行。

---

## 7. 非目标

- 不改 `.praxist-venv` / TimesFM 底座源码
- 不改预注册硬门、不改 SCHEMES
- 不引入第二份 TimesFM 实例
- 不给 checkpoint JSONL 加 flock（F-003）
- 不调用 `torch.cuda.empty_cache`（F-006，无 GPU）
- 不把全库 `print` 迁到 `logging`（F-009）
- 不加速 Hurst / `iterrows`（F-015 / F-019，后续 spec）

---

## 8. 后续 spec 清单（审计其余条目）

本文件不实施下列 ID。独立 spec，按优先级大致如下。

| 建议 spec | 审计 ID | 说明 |
|---|---|---|
| （本文件） | F-004, F-001, F-010, F-011, F-005 | 第一批 |
| 不适用，不单开 | F-006 | 宿主无 GPU |
| xreg-fallback-observability | F-002 | 收窄 `except Exception`，`HourlyResult.failure_reason` |
| checkpoint-lock | F-003 | 仅当确认会多进程 `--resume` 再做；当前单写入者 |
| pickle-trust-boundary | F-007 | 文档化 `models/` 信任边界；不强制迁 safetensors |
| main-contract-calendar | F-008 | cutoff 主力合约是否感知交易日历 |
| structured-logging | F-009 | 全库 logging，工作量大，单独排期 |
| validator-session | F-012 | `days_stale==1` 的 bar 级 session 检查 |
| path-insert-hygiene | F-013 | `sys.path.insert` 口径 |
| covariate-length-tests | F-014 | 协变量长度不变量测试 |
| hurst-vectorize | F-015 | 滚动 Hurst 去掉 Python 热循环 |
| predict-load-order | F-016 | `cascade_predict` 先加载模型再开 DataStore |
| thrpolicy-tests | F-017 | ThrPolicy 优先级链参数化测试 |
| calendar-horizon | F-018 | `calendar_cyclical` horizon 用交易日历 |
| store-klines-values | F-019 | `store_klines` 去掉 `iterrows` |
| covariate-unit-tests | F-020 | 协变量函数单测补全 |
| backtest-typing | F-021 | `monthly_backtest` 类型提示 |
| atr-reuse | F-022 | combo 路径 ATR 预计算注入 |

---

## 9. 验收标准（本 spec 完成时）

- [ ] `_ensure_compiled` 在同配置连续 `predict` 时不调用 `model.compile`
- [ ] 日线↔1H 切换时必调用 `compile`
- [ ] 假模型与真模型慢测：跳过路径 vs 强制 compile，预测数组逐位一致
- [ ] `run_symbol_backtest` 读库异常不再漏连接
- [ ] `cascade.features` 模块级持有 sklearn 符号
- [ ] `progress.log` 追加而非覆盖
- [ ] `test_a2_p1_integrity.py` 不再含 `D:/FlyBuddy/fm_a`
- [ ] 常规回归（不含 slow）通过
