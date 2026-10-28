# TimesFM 2.5→3.0 迁移计划

> **代码基线**: `ba0a785`

**日期**：2026-10-13  
**状态**：PROPOSED  
**优先级**：P1（技术债清理）  
**预计工作量**：M（1.5-2 小时）

## 背景

代码层面已完成 TimesFM 3.0 迁移（`import timesfm3`, `TimesFM3Forecaster.from_pretrained()`），但残留三类 2.5 引用：
1. 环境变量和启动脚本中的硬编码路径
2. `_weight_shards()` 的 fallback 路径
3. 12 处 print/report 文案

## 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| **模型权重** | ✅ 3.0 已下载 | `/home/abug/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch` |
| **代码 API** | ✅ 已迁移 | `cascade/daily_model.py` 等使用 `timesfm3.TimesFM3Forecaster` |
| **环境变量** | ⚠️ 指向 2.5 | `.env.praxist` 中 `FM_TIMESFM_MODEL_PATH` |
| **启动脚本** | ⚠️ 指向 2.5 | `data/cache/start_supervisor.sh` |
| **fallback 路径** | ⚠️ 硬编码 2.5 | `scripts/monthly_backtest.py:143` |
| **文案** | ⚠️ 12 处写 "2.5" | 各脚本的 print 语句 |

## 迁移方案

### Phase 1：功能性路径（P1，15 分钟）

**目标**：确保 supervisor 和基线生成使用 3.0 模型

#### 1.1 更新 `.env.praxist`

```bash
# 修改前：
FM_TIMESFM_MODEL_PATH=/home/abug/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots/1d952420fba87f3c6dee4f240de0f1a0fbc790e3
TIMESFM_WEIGHTS_DIR=/home/abug/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots/1d952420fba87f3c6dee4f240de0f1a0fbc790e3

# 修改后：
FM_TIMESFM_MODEL_PATH=/home/abug/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch/snapshots/43046b85ec22d584a13f8098c2ed39c889e129c2
TIMESFM_WEIGHTS_DIR=/home/abug/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch/snapshots/43046b85ec22d584a13f8098c2ed39c889e129c2
```

#### 1.2 更新 `data/cache/start_supervisor.sh`

```bash
# 修改前：
export FM_TIMESFM_MODEL_PATH="/home/abug/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots/1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
export TIMESFM_WEIGHTS_DIR="/home/abug/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots/1d952420fba87f3c6dee4f240de0f1a0fbc790e3"

# 修改后：
export FM_TIMESFM_MODEL_PATH="/home/abug/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch/snapshots/43046b85ec22d584a13f8098c2ed39c889e129c2"
export TIMESFM_WEIGHTS_DIR="/home/abug/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch/snapshots/43046b85ec22d584a13f8098c2ed39c889e129c2"
```

#### 1.3 更新 `scripts/monthly_backtest.py`

```python
# 修改前（line 143-144）：
"~/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots")

# 修改后：
"~/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch/snapshots")
```

### Phase 2：文案更新（P2，20 分钟）

**目标**：所有 print/report 文案统一为 "TimesFM 3.0"

**文件清单**（12 处）：

| 文件 | 行号 | 原文 | 修改 |
|------|------|------|------|
| `scripts/predict.py` | 92 | `TimesFM 2.5 (200M)` | `TimesFM 3.0` |
| `scripts/ablation_context.py` | 23 | `加载 TimesFM 2.5 模型...` | `加载 TimesFM 3.0 模型...` |
| `scripts/copilot.py` | 885 | `加载 TimesFM 2.5 ...` | `加载 TimesFM 3.0 ...` |
| `scripts/batch_backtest.py` | 196 | `TimesFM 2.5 级联` | `TimesFM 3.0 级联` |
| `scripts/cascade_predict.py` | 347 | `TimesFM 2.5 级联` | `TimesFM 3.0 级联` |
| `scripts/cascade_predict.py` | 892 | `加载 TimesFM 2.5 模型` | `加载 TimesFM 3.0 模型` |
| `scripts/monthly_backtest.py` | 866 | `TimesFM 2.5 级联` | `TimesFM 3.0 级联` |
| `scripts/monthly_backtest.py` | 1127 | `加载 TimesFM 2.5 模型` | `加载 TimesFM 3.0 模型` |
| `scripts/three_star_predict.py` | 205 | `加载 TimesFM 2.5 模型` | `加载 TimesFM 3.0 模型` |
| `scripts/three_star_predict.py` | 291 | `TimesFM 2.5 级联` | `TimesFM 3.0 级联` |
| `scripts/variety_analysis.py` | 478 | `TimesFM 2.5 已加载` | `TimesFM 3.0 已加载` |
| `scripts/toxic_variety_runner.py` | 186 | `加载 TimesFM 2.5` | `加载 TimesFM 3.0` |

### Phase 3：基线重生（P1，30-60 分钟等待）

**目标**：用 3.0 模型重新生成 9 个品种的基线

**步骤**：
1. 停止 supervisor（避免模型加载冲突）
2. 运行基线生成：
   ```bash
   for sym in jd sr m ss ao rb cf i fu; do
       python scripts/generate_baseline_points.py --symbol $sym --cov none --root .
   done
   ```
3. 验证新基线指纹（必然与 v4 `f02b2a43` 不同）
4. 重启 supervisor

**预期**：
- 旧基线自动归档（`baseline_points_{sym}_nocov.archive_*.jsonl`）
- 新基线生成（9 品种 × 588 点 ≈ 30-60 分钟）
- 新指纹落盘（`baseline_metrics.json` 更新）

### Phase 4：验证（20 分钟）

**步骤**：
1. 单品种跑 `predict.py` 确认模型加载正常
2. 检查 supervisor 日志无 ERROR
3. 确认 cycles_done 增长
4. 验证新基线指纹

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 3.0 内存更大（925MB→1.32GB） | 低 | 中 | 共享模型实例已实现（`shared_model` 参数） |
| 基线重生期间无可用基线 | 中 | 高 | 保留旧基线不动，新生成新指纹目录 |
| Supervisor 切换模型 | 低 | 低 | Supervisor 不重启不会 reload，重启自动用新路径 |

## 不需要改

| 位置 | 原因 |
|------|------|
| `third_party/timesfm-3.0-official/` | 第三方库自带 2.5 兼容层 |
| `reports/` / `data/archive/` | 历史产物 |
| `.env.praxist.bak_*` | 历史备份 |
| `data/config.py` | `TIMESFM_HUB_ID` / `TIMESFM_LOCAL_DIRNAME` 已是 3.0 |

## 时间线

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| Phase 1 | 功能性路径（env + fallback） | 15 分钟 |
| Phase 2 | 文案更新（12 处） | 20 分钟 |
| Phase 3 | 基线重生（9 品种） | 30-60 分钟 |
| Phase 4 | 验证 | 20 分钟 |
| **总计** | | **1.5-2 小时** |

## 关键文件路径

| 文件 | 作用 |
|------|------|
| `/home/abug/timesfm/.env.praxist` | 环境变量 |
| `/home/abug/timesfm/data/cache/start_supervisor.sh` | 启动脚本 |
| `/home/abug/timesfm/scripts/monthly_backtest.py` | fallback 路径 |
| `/home/abug/timesfm/scripts/generate_baseline_points.py` | 基线生成 |
| `/home/abug/.cache/huggingface/hub/models--google--timesfm-3.0-pytorch` | 3.0 模型 |

## 成功标准

- ✅ 所有环境变量指向 3.0 snapshot
- ✅ 所有文案统一为 "TimesFM 3.0"
- ✅ 9 品种基线重生完成
- ✅ Supervisor 运行正常（无 ERROR）
- ✅ 新基线指纹落盘

## 后续优化（可选）

- **选项 D**：删除 2.5 模型目录（节省磁盘空间）
- **选项 E**：更新 `CLAUDE.md` / `docs/praxist.md` 中的 TimesFM 版本说明

---

**下一步**：按 Phase 1 → 2 → 3 → 4 顺序实施。
