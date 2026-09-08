# TimesFM 系统效率审计报告

> 日期: 2026-09-08
> 审计范围: `/home/abug/timesfm/` 全部核心组件
> 审计工具: oh-my-claudecode:analyst (opus)

---

## 项目概述

TimesFM 期货量化预测系统，核心组件：

| 组件 | 文件 | 行数 | 职责 |
|------|------|------|------|
| 监督环 | `scripts/praxist_supervisor.py` | ~1100 | 三环调度 + 事件监控 |
| 日线模型 | `cascade/daily_model.py` | ~150 | TimesFM 日线预测 |
| 1H 级联模型 | `cascade/hourly_model.py` | ~300 | XReg 协变量预测 |
| 回测引擎 | `scripts/monthly_backtest.py` | ~900 | Walk-forward 回测 |
| 评估管道 | `task_FM/evaluations/fm_eval/` | ~150 | Praxist 评估入口 |
| 特征工程 | `cascade/features.py` | ~2000 | 协变量矩阵构建 |
| 数据存储 | `data/data_store.py` | ~800 | SQLite 数据层 |
| 数据验证 | `cascade/data_validator.py` | ~250 | 数据质量校验 |
| 波动率过滤 | `cascade/vol_risk_filter.py` | ~400 | 波动率熔断器 |

---

## 发现汇总

| 严重度 | 数量 | 预估工时 |
|--------|-----:|---------:|
| CRITICAL | 4 | 4-6h |
| HIGH | 8 | 10-14h |
| MEDIUM | 7 | 10-14h |
| LOW | 3 | 4-6h |
| **合计** | **22** | **28-39h** |

| 类别 | 数量 |
|------|-----:|
| robustness（健壮性） | 8 |
| performance（性能） | 5 |
| testing（测试） | 4 |
| observability（可观测性） | 3 |
| config（配置） | 2 |

---

## CRITICAL 发现

### F-001: DataStore 连接泄漏

- **文件**: `scripts/monthly_backtest.py:164-169`
- **类别**: robustness
- **工作量**: S

**描述**: `DataStore(symbol)` 在 `run_symbol_backtest` 中创建时未使用上下文管理器。如果 `get_main_contract_1h`（165行）或 `get_main_continuous`（168行）抛出异常，`store.close()`（169行）永远不会执行，泄漏 SQLite 连接。在 20 品种 walk-forward 回测下，会累积泄漏连接。

**影响**: SQLite 连接耗尽，长时间回测可能出现 "database is locked" 错误。

**修复方案**: 使用 `with DataStore(symbol) as store:` 上下文管理器（已在 data_store.py:94 测试通过）。

---

### F-002: XReg 异常被宽泛 except 吞掉

- **文件**: `cascade/hourly_model.py:244`
- **类别**: observability
- **工作量**: M

**描述**: `except Exception as e:` 捕获了 XReg 预测调用的所有异常，包括 OOM、NaN 等灾难性错误。回退路径替换了结果但原始异常丢失——系统静默产出降级预测，无法区分正常回退（协变量缺失）和灾难性故障（GPU OOM、模型权重 NaN）。

**影响**: 静默数据损坏或模型降级；无法诊断根因。

**修复方案**: 收窄异常类型（`ValueError`, `RuntimeError`），记录原始 traceback，在 `HourlyResult` 中添加结构化 `failure_reason` 字段。

---

### F-003: Checkpoint JSONL 无文件锁

- **文件**: `scripts/monthly_backtest.py:848, 358-359`
- **类别**: robustness
- **工作量**: S

**描述**: Checkpoint 文件以 append 模式打开（`open(cp, "a", ...)`），每次写入后 `flush()`。代码注释（827-828行）已承认此问题："未来可选: filelock 强制互斥"。多个并发 `--resume` 运行会交叉写入，损坏 JSONL，导致下次 resume 产出静默错误的结果。

**影响**: Checkpoint 数据损坏，回测指标静默错误。

**修复方案**: 添加文件锁（`fcntl.flock` 在 Linux，`msvcrt` 在 Windows），或使用 `filelock` 库。

---

### F-004: 每次 predict 都重新编译模型

- **文件**: `cascade/daily_model.py:69`, `cascade/hourly_model.py:117`
- **类别**: performance
- **工作量**: M

**描述**: 两个模型在每次 `predict()` 调用时都重新编译 TimesFM 配置（`self.model.compile(self._DAILY_CONFIG)` / `self.model.compile(self._XREG_CONFIG)`）。注释承认另一个模型可能已用不同设置重新编译。在 walk-forward 回测中数百个评估点 × 20 品种 = 1000+ 次无效重编译。

**影响**: 每次重编译开销大（torch.compile/torchscript），全品种回测显著变慢。

**修复方案**: 跟踪当前配置状态，仅在配置变更时重编译。或者为每个配置使用独立模型实例。

---

## HIGH 发现

### F-005: 测试文件硬编码 Windows 路径

- **文件**: `tests/test_a2_p1_integrity.py:68,77,86,93,103,111`
- **类别**: testing | **工作量**: S
- **描述**: 测试使用硬编码 `"D:/FlyBuddy/fm_a"` 路径。无法在其他机器或 Linux CI 上运行。
- **修复**: 使用 `Path(__file__).resolve().parent.parent` 或 pytest fixtures。

### F-006: cascade_predict.py 无 GPU 内存清理

- **文件**: `scripts/cascade_predict.py:863-867`
- **类别**: robustness | **工作量**: S
- **描述**: 主预测脚本加载模型后从不调用 `torch.cuda.empty_cache()`。`monthly_backtest.py` 有此保护（240-243行）但生产预测脚本没有。
- **修复**: 在主循环中每 N 个品种调用 `torch.cuda.empty_cache()`。

### F-007: pickle.load 加载不可信模型文件

- **文件**: `cascade/vol_risk_filter.py:384-385`
- **类别**: robustness | **工作量**: M
- **描述**: `pickle.load(f)` 反序列化 ML 模型。如果 `models/` 目录被不可信进程写入，可执行任意代码。
- **修复**: 文档化信任边界，迁移到 safetensors/ONNX，或添加文件完整性校验（hash）。

### F-008: 主力合约检测忽略周末/假日

- **文件**: `data/data_store.py:690-702`
- **类别**: robustness | **工作量**: M
- **描述**: `_get_main_contract_at_cutoff()` 使用 OI 排序选择主力合约。如果 cutoff 在周末/假日，"最新"数据可能是周五下午的，不反映周一的实际主力合约。
- **修复**: 添加交易日历感知，或文档化为已知限制。

### F-009: 全代码库无结构化日志

- **文件**: 所有文件
- **类别**: observability | **工作量**: L
- **描述**: 全部使用 `print()` 输出诊断信息。`data_store.py:15` 定义了 `logger` 但仅用于 2-3 处。无日志级别系统。
- **修复**: 迁移到 Python `logging` 模块，统一级别：INFO/WARNING/ERROR/DEBUG。

### F-010: sklearn 延迟导入

- **文件**: `cascade/features.py:210-211`
- **类别**: robustness | **工作量**: S
- **描述**: `sklearn.decomposition.PCA` 和 `sklearn.preprocessing.StandardScaler` 在函数内部导入。依赖在运行时才被发现。
- **修复**: 移到模块级 import，用 try/except 在导入时提供清晰错误信息。

### F-011: progress.log 被 write_text 覆盖

- **文件**: `scripts/monthly_backtest.py:857-858`
- **类别**: observability | **工作量**: S
- **描述**: `progress_log.write_text(...)` 覆盖文件。并发运行时第二个覆盖第一个的进度日志。
- **修复**: 使用 append 模式或文件名含 run ID。

### F-012: 数据验证器跨夜 session 检查不完整

- **文件**: `cascade/data_validator.py:173-214`
- **类别**: robustness | **工作量**: M
- **描述**: Bar 级新鲜度检查仅在 `days_stale == 0` 时触发。`days_stale == 1` 时不验证当前交易 session 的 bars 是否完整。
- **修复**: 扩展 bar 级检查到 `days_stale <= effective_max`，加入 session 逻辑。

---

## MEDIUM 发现

| ID | 问题 | 文件 | 类别 | 工作量 |
|----|------|------|------|:---:|
| F-013 | sys.path.insert 路径解析不一致 | `monthly_backtest.py:29` | config | S |
| F-014 | features.py 协变量长度不变量无测试 | `cascade/features.py` | testing | M |
| F-015 | rolling Hurst 使用 Python for 循环 (O(N*W)) | `features.py:332-334` | performance | M |
| F-016 | cascade_predict.py 模型加载失败浪费 DataStore 周期 | `cascade_predict.py:94-104` | performance | S |
| F-017 | vol_risk_filter ThrPolicy 优先级链无全面测试 | `vol_risk_filter.py:156-181` | testing | M |
| F-018 | calendar_cyclical horizon 生成忽略交易时间 | `features.py:2129-2134` | robustness | S |
| F-019 | data_store.py store_klines 用 iterrows() O(N) | `data_store.py:125-130` | performance | S |

---

## LOW 发现

| ID | 问题 | 文件 | 类别 | 工作量 |
|----|------|------|------|:---:|
| F-020 | 30+ 协变量函数无单元测试 | `features.py` | testing | M |
| F-021 | 回测引擎函数无类型提示 | `monthly_backtest.py` | config | M |
| F-022 | features.py ATR 重复计算 | `features.py` 多处 | performance | S |

---

## 修复计划

### Phase 1: 关键修复（1-2h）

| 优先级 | ID | 修复内容 |
|:---:|------|---------|
| 1 | F-001 | DataStore 改用 `with` 上下文管理器 |
| 2 | F-003 | Checkpoint JSONL 添加 `fcntl.flock` 文件锁 |
| 3 | F-006 | cascade_predict.py 添加定期 `torch.cuda.empty_cache()` |
| 4 | F-010 | features.py sklearn 移到模块级 import |
| 5 | F-011 | progress.log 改用 append 模式 |

### Phase 2: 核心改进（3-4h）

| 优先级 | ID | 修复内容 |
|:---:|------|---------|
| 6 | F-002 | hourly_model.py 收窄异常类型 + 添加 failure_reason |
| 7 | F-004 | 模型 compile 添加配置变更检测，避免重复编译 |
| 8 | F-005 | 测试文件路径改用 `Path(__file__)` 动态解析 |

### Phase 3: 可观测性 + 数据质量（6-8h）

| 优先级 | ID | 修复内容 |
|:---:|------|---------|
| 9 | F-009 | 全代码库迁移到 Python logging 模块 |
| 10 | F-012 | data_validator.py 扩展 session 感知检查 |
| 11 | F-018 | calendar_cyclical 使用交易日历生成 horizon |

### Phase 4: 测试 + 性能（持续）

| 优先级 | ID | 修复内容 |
|:---:|------|---------|
| 12 | F-014 | 协变量长度不变量 property-based 测试 |
| 13 | F-017 | ThrPolicy 参数化测试 |
| 14 | F-020 | 协变量函数单元测试补全 |
| 15 | F-015 | Hurst 滚动计算 Numba 加速 |
| 16 | F-022 | ATR 预计算注入 combo 模式 |
| 17 | F-019 | store_klines 改用 `df.values.tolist()` |

---

## 待确认问题

- [ ] 是否有多个进程并发运行 `monthly_backtest.py --resume`？（决定 F-003 紧迫度）
- [ ] 目标部署环境是否仅 Windows？（决定 F-005 紧迫度）
- [ ] 生产预测是否使用 GPU？（决定 F-006 紧迫度）
- [ ] `models/` 目录是否有访问控制？（决定 F-007 实际严重度）
