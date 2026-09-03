# A2-P1 Dense Matrix 缓存断点恢复 Spec

**日期**: 2026-08-05
**状态**: 待审核
**替代**: 原一次性全量计算 dense matrix（崩溃后重算全部 78min/品种）

---

## 1. 问题陈述

当前 `build_dense_feature_matrix()` 一次性全量计算 12 维特征，最后才原子写 parquet 缓存。如果 Worker 在中途崩溃（OOM、Segfault、电脑重启），缓存未生成，重启后重算全部特征。

**核心瓶颈**: `compute_timesfm_features_batch()` 逐 bar 调用 TimesFM 前向传播，396 bars × ~10.8s/bar ≈ **71min/品种**（冷启动）。这期间任何崩溃都导致 71min 白费。

**A2-P1 全量运行时长**: 20 品种 × 78min ≈ 26 小时。长时间运行中**大概率会遇到**暂停/重启/OOM，必须有抗崩溃能力。

**当前断点能力**: JSONL 结果已是 eval point 级别断点，但 **dense matrix 生成过程无断点**。

## 2. 设计目标

| 目标 | 实现方式 |
|------|----------|
| **dense matrix 生成可断点续算** | TimesFM 特征逐 bar 原子追加，崩溃后只重算未完成的 |
| **market 特征可复用** | 9 维市场特征独立缓存，二次运行直接读 |
| **结果可复现** | 断点续算与全量计算数值一致 |
| **长时间运行抗崩溃** | 任意时刻崩溃，已写盘的 bars 保留 |

**保持不变**:
- 12 维特征池、walk-forward step=24、配对 bootstrap Gate
- JSONL eval point 级断点续跑（已有）
- 品种级进程隔离（Orchestrator + Worker）

## 3. 架构设计

### 3.1 三级缓存

```
reports/a2_p1_features/
├── <symbol>_market.parquet       # 阶段1: 9 维市场特征 (一次性原子写, ~7min)
├── <symbol>_tsfm.jsonl           # 阶段2: 3 维 TimesFM 特征 (逐 bar 原子追加, ~71min) ← 核心
└── <symbol>_dense_matrix.parquet # 阶段3: 完整 12 维矩阵 (最终产物, 秒级)
```

| 阶段 | 缓存 | 崩溃恢复 | 重算成本 |
|------|------|---------|---------|
| 阶段1 (7min) | `market.parquet` | 有则读，无则重算 | 7min（可接受） |
| **阶段2 (71min)** | **`tsfm.jsonl` 逐 bar 追加** | **读已有，只重算未完成** | **剩余时间（非全量）** |
| 阶段3 (秒级) | `dense_matrix.parquet` | 直接读 | 0 |

### 3.2 逐 bar 原子追加（核心机制）

`compute_timesfm_features_batch()` 对每个 eval bar 计算完成后，**立即**追加一行到 `tsfm.jsonl`：

```json
{"bar_idx": 480, "timesfm_pure_pred": 0.0123, "timesfm_confidence": 0.0456, "horizon_slope": 0.0008}
```

**关键保证**:
- 每行 `flush()` 立即写盘 → 崩溃最多损失"最后一个 bar 写入后到崩溃前"的间隙（毫秒级）
- 重启时读 `tsfm.jsonl`，提取已完成 `bar_idx` 集合，只计算未完成的
- 已完成 + 新计算的合并 → 完整 3 维特征

### 3.3 缓存读取优先级

`build_dense_feature_matrix()` 按以下顺序尝试：

```
1. dense_matrix.parquet 存在 → 直接读取（完整矩阵）
2. market.parquet 存在 → 读 9 维；否则重算
3. tsfm.jsonl 存在 → 读已完成 bars，续算未完成
4. 全部组合 → 原子写 dense_matrix.parquet
```

## 4. 接口变更

### 4.1 `compute_timesfm_features_batch()` 新增参数

```python
def compute_timesfm_features_batch(
    symbol, store, df_1h, bar_indices,
    shared_hourly, shared_daily, batch_size=128,
    resume_path: str | None = None,   # 新增
) -> pd.DataFrame:
```

- `resume_path`: TimesFM 特征断点文件路径（`<symbol>_tsfm.jsonl`）
- 存在则读已完成 bars，只计算未完成的；每完成一个 bar 原子追加

### 4.2 `build_dense_feature_matrix()` 新增参数

```python
def build_dense_feature_matrix(
    symbol, store, dense_step=24, shared_hourly=None, shared_daily=None,
    vol_filter=None, cache_path=None,
    market_cache_path: str | None = None,   # 新增
    tsfm_resume_path: str | None = None,    # 新增
) -> pd.DataFrame:
```

- `market_cache_path`: 9 维市场特征缓存（`<symbol>_market.parquet`）
- `tsfm_resume_path`: TimesFM 特征断点（`<symbol>_tsfm.jsonl`）

### 4.3 Worker 传入缓存路径

```python
cache_path = f"reports/a2_p1_features/{symbol_lower}_dense_matrix.parquet"
market_cache_path = f"reports/a2_p1_features/{symbol_lower}_market.parquet"
tsfm_resume_path = f"reports/a2_p1_features/{symbol_lower}_tsfm.jsonl"

mat = build_dense_feature_matrix(
    symbol_lower, store, dense_step=dense_step,
    shared_hourly=hourly, shared_daily=daily, cache_path=cache_path,
    market_cache_path=market_cache_path, tsfm_resume_path=tsfm_resume_path,
)
```

## 5. 应对暂停/重启

| 场景 | 行为 | 恢复 |
|------|------|------|
| **电脑暂停**（睡眠） | 进程冻结，内存保留 | 唤醒后继续，无需处理 |
| **电脑重启** | 进程死掉，**已写盘缓存保留** | 重启 Orchestrator，从断点续跑 |
| **Worker 崩溃**（OOM） | 已写盘 bars 保留 | Orchestrator 自动续跑该品种 |
| **Orchestrator 崩溃** | 子进程被回收，缓存保留 | 重启 Orchestrator，跳过已完成品种 |

## 6. 附带修复

### 6.1 输出缓冲（诊断必需）

当前 Worker 所有 `print()` 无 `flush=True`，Python 在文件重定向时使用块缓冲（~8KB），导致日志为空、无法实时监控进度。

**修复**: Orchestrator 启动 Worker 时加 `-u` 参数（`PYTHONUNBUFFERED=1`），或 Worker 所有 `print()` 加 `flush=True`。选择 **Orchestrator 加 `-u`**（改动最小，一处生效全部品种）。

### 6.2 超时调整

专家调查确认: 单品种冷启动需要 ~78min，Orchestrator 当前 `timeout=3600`（60min）不够。

**修复**: `timeout=3600` → `5400`（90min），给冷启动留余量。断点续跑后（tsfm.jsonl 已存在），实际时间远低于 90min。

## 7. 验收标准

| 测试 | 预期 |
|------|------|
| 手动 kill Worker（运行到 ~50 个 tsfm bars 时） | 重启后只计算剩余 bars（`[Worker RB] 50 done, 346 pending`） |
| 二次运行（缓存已存在） | 直接读取 market.parquet + tsfm.jsonl，不重算 TimesFM |
| 断点续算数值一致性 | 同 bar 的 TimesFM 预测与全量计算一致 |
| `--dry-run` | 不加载模型，不写任何缓存 |
| Orchestrator 超时 | 单品种冷启动（<90min）通过 |

## 8. 文件变更清单

| 文件 | 操作 | 变更 |
|------|------|------|
| `cascade/lgbm_features.py` | Modify | `compute_timesfm_features_batch` 加 `resume_path`；`build_dense_feature_matrix` 拆 market/tsfm 缓存 |
| `scripts/a2_p1_worker.py` | Modify | 传入 `market_cache_path`/`tsfm_resume_path` |
| `scripts/a2_p1_orchestrator.py` | Modify | 启动 Worker 加 `-u`；`timeout` 3600→5400 |
| `tests/test_a2_p1_runtime.py` | Modify | 新增缓存断点测试 |

## 9. 不做的事（Scope）

- **不实现 TimesFM batching**（治本提速，属于 A2-P2）
- **不做并行**（CPU 是瓶颈，并行不加速）
- **不改变 12 维特征池**、step=24、Gate 逻辑
- **不改变品种级进程隔离架构**

---

**下一步**: 用户审核本 Spec → 批准后写实施计划。
