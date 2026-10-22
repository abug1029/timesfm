# Phase 2-3 集成障碍分析报告

**日期**: 2026-10-21  
**作者**: AI Assistant  
**基于**: Phase 2-3 执行审计报告 (`docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md`)  
**状态**: 分析完成

---

## 一、执行摘要

Phase 2-3 代码实现完成度 100%，但主路径集成完成度仅 ~56%。主要障碍为 **praxist 框架限制**（peer 生成/写盘逻辑在外部框架内，无法注入自定义逻辑）和 **执行疏漏**（监控自动化未实际部署）。

**当前状态**：
- ✅ 慢环侧改进已完成（质量预测、短窗预筛、bandit 反馈）
- ❌ 生成侧集成受阻（praxist 框架限制）
- ⚠️ 监控自动化未部署（执行疏漏，可快速修复）

---

## 二、未形成闭环的详细分析

### 2.1 生成策略 → peer 生成（未集成）

**期望闭环**：
```
慢环验证 → bandit 反馈 → 生成策略调整 → peer 生成 → 慢环验证
```

**实际状态**：
- ✅ `scripts/generation_strategy.py` 已实现完整功能
  - `GenerationStrategy`: 规则采样配额调整
  - `MultiArmedBandit`: UCB + Thompson Sampling
  - `ElitePreservation`: Top-K 精英库 + 变异
  - `load_bandit_feedback()`: 可消费慢环反馈
- ❌ **peer 调用方不存在**，无法实际影响生成

**障碍分析**：
- peer 生成逻辑在 praxist 框架内（`.venv/lib/python3.11/site-packages/praxist/`）
- praxist 是第三方/框架包，非本仓库代码
- 无 hook 点供我们注入自定义逻辑

**相关文件**：
- 实现：`scripts/generation_strategy.py` (609 lines)
- 测试：`tests/test_generation_strategy.py` (24 tests)
- 反馈文件：`data/cache/bandit_feedback.jsonl` (由 harvest 写入)
- praxist 包：`.venv/lib/python3.11/site-packages/praxist/`

### 2.2 多样性奖励 → 生成策略（未集成）

**期望闭环**：
```
多样性度量 → 多样性奖励 → 生成策略调整 → peer 生成 → 多样性提升
```

**实际状态**：
- ✅ `scripts/diversity_metrics.py` 可计算多样性指标
  - symbol 熵、family 熵、组合覆盖率、新颖度
  - 发现组合覆盖率仅 19.8%（80% 未探索）
- ❌ **无接入点影响生成策略**

**障碍分析**：
- 同 2.1，peer 生成在 praxist 框架内
- 多样性奖励无法注入生成逻辑

**相关文件**：
- 实现：`scripts/diversity_metrics.py` (308 lines)
- 测试：`tests/test_diversity_metrics.py` (11 tests)
- 文档：`docs/diversity-metrics-guide.md`

### 2.3 提案卫生 → peer 写盘前（未集成）

**期望闭环**：
```
提案生成 → 写盘前验证 → 不合格拒绝 → 合格写盘
```

**实际状态**：
- ✅ `scripts/proposal_validator.py` 已实现
  - JSON/类型/中英验证
- ✅ **harvest 侧已集成**（入队前调用 `validate_proposal_dict()`）
- ❌ **peer 写盘前未集成**

**障碍分析**：
- peer 写盘逻辑在 praxist 框架内
- 无法在写盘前注入验证逻辑

**相关文件**：
- 实现：`scripts/proposal_validator.py` (114 lines)
- 批量验证：`scripts/validate_all_proposals.py` (150 lines)
- 测试：`tests/test_proposal_validator.py` (26 tests)
- harvest 集成：`scripts/sup_harvest.py` (入队前调用)

### 2.4 监控自动化 → crontab/supervisor（未部署）

**期望闭环**：
```
定时采集指标 → 生成报告 → 触发告警 → 人工干预
```

**实际状态**：
- ✅ `scripts/monitor_metrics.py` 已实现
  - 每日指标收集
  - 红线告警
  - 报告生成
- ✅ `scripts/generate_weekly_report.py` 已实现
- ❌ **未实际配置 crontab**

**障碍分析**：
- **技术障碍**：无（脚本已实现，crontab 示例已文档化）
- **实际原因**：执行疏漏，未实际配置

**相关文件**：
- 每日监控：`scripts/monitor_metrics.py` (364 lines)
- 周报生成：`scripts/generate_weekly_report.py`
- 测试：`tests/test_monitor_metrics.py` (17 tests)
- 示例报告：`docs/superpowers/reports/monitoring_example.md`
- 指标历史：`data/cache/metrics_history/`

---

## 三、障碍分类与解决难度

| 障碍类型 | 影响范围 | 解决难度 | 预计工作量 |
|---------|---------|---------|-----------|
| **praxist 框架限制** | 生成策略、多样性、提案卫生（peer 侧） | 高 | 1-2 周（fork/PR）或 2-3 天（sitecustomize） |
| **执行疏漏** | 监控自动化（crontab） | 低 | 10 分钟（配置即可） |
| **测试数据缺失** | 短窗回测效果验证 | 中 | 1-2 周（运行收集数据） |

---

## 四、解决路径建议

### 4.1 短期（可立即执行，1-2 天）

#### 4.1.1 配置 crontab 自动化监控

**操作步骤**：
```bash
# 编辑 crontab
crontab -e

# 添加以下条目
0 2 * * * cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/monitor_metrics.py collect >> /home/abug/timesfm/logs/monitor_metrics.log 2>&1
0 3 * * 1 cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/generate_weekly_report.py --days 7 >> /home/abug/timesfm/logs/weekly_report.log 2>&1
```

**预期效果**：
- 每日 02:00 自动采集指标
- 每周一 03:00 自动生成周报
- 实现持续监控闭环

**相关文件**：
- `scripts/monitor_metrics.py`（docstring 中已有 crontab 示例）
- `scripts/generate_weekly_report.py`

#### 4.1.2 运行短窗回测收集效果数据

**操作步骤**：
1. 让慢环运行 1-2 周，积累短窗回测数据
2. 统计 `short_window_fail` 占比
3. 对比过滤前后的慢环验证效率

**预期效果**：
- 验证短窗回测是否真的减少 50%+ 无效验证
- 为后续优化提供数据支撑

**相关文件**：
- `scripts/short_window_backtest.py`
- `data/cache/short_window_results.jsonl`

### 4.2 中期（需架构决策，1-3 周）

#### 4.2.1 方案 A：Fork praxist 并添加 plugin/hook 机制

**优点**：
- 完全控制，可注入任意逻辑
- 长期维护成本可控

**缺点**：
- 需要持续同步 praxist 上游更新
- 维护成本高

**实施步骤**：
1. Fork praxist 到本仓库或独立仓库
2. 在 peer 生成/写盘逻辑中添加 plugin/hook 点
3. 实现 plugin 接口供 `generation_strategy`、`diversity_metrics`、`proposal_validator` 调用
4. 测试并部署

**相关文件**：
- praxist 源码：`.venv/lib/python3.11/site-packages/praxist/`
- 需要修改的 praxist 模块：待分析（需阅读 praxist peer 生成逻辑）

#### 4.2.2 方案 B：提交上游 PR 添加 plugin/hook 机制

**优点**：
- 无需维护 fork
- 受益于 praxist 社区

**缺点**：
- 需要 praxist 维护者配合
- 时间不可控

**实施步骤**：
1. 分析 praxist peer 生成逻辑
2. 设计 plugin/hook 接口
3. 提交 PR 到 praxist 上游
4. 等待合并并发布新版本
5. 升级 praxist 并实现 plugin

**相关文件**：
- praxist 上游仓库：待确认
- praxist 本地包：`.venv/lib/python3.11/site-packages/praxist/`

#### 4.2.3 方案 C：通过 sitecustomize.py 注入

**优点**：
- 无需修改 praxist
- 实施速度快（2-3 天）

**缺点**：
- 脆弱，依赖 praxist 内部实现细节
- praxist 升级可能破坏注入
- 已有先例但需评估稳定性

**实施步骤**：
1. 分析现有 `sitecustomize.py` 注入机制（`docs/archive/peer-proposals-pre-0918/run_*//.runtime_guards/*/python_site/sitecustomize.py`）
2. 实现 monkey-patch 注入 `generation_strategy`、`diversity_metrics`、`proposal_validator`
3. 测试并部署

**相关文件**：
- 现有注入示例：`docs/archive/peer-proposals-pre-0918/run_*/.runtime_guards/*/python_site/sitecustomize.py`
- praxist 运行时：`.venv/lib/python3.11/site-packages/praxist/`

### 4.3 长期（架构演进，1-3 月）

#### 4.3.1 将 peer 生成逻辑从 praxist 抽离到本仓库

**优点**：
- 完全控制，无需依赖外部框架
- 可深度优化生成策略

**缺点**：
- 工作量大（1-3 月）
- 需要重构架构

**实施步骤**：
1. 分析 praxist peer 生成逻辑
2. 设计新的 peer 生成架构
3. 实现 peer 生成模块（本仓库）
4. 迁移现有逻辑
5. 测试并部署

**相关文件**：
- praxist peer 逻辑：待分析
- 新模块：待设计

---

## 五、相关文件完整索引

### 5.1 Phase 2-3 实现文件

| 文件 | 行数 | 说明 | 状态 |
|------|------|------|------|
| `scripts/generation_strategy.py` | 609 | 生成策略外环（规则/UCB/Thompson/精英） | ✅ 已实现 |
| `scripts/short_window_backtest.py` | 483 | 短窗回测预筛 | ✅ 已实现 |
| `scripts/proposal_validator.py` | 114 | 提案卫生验证 | ✅ 已实现 |
| `scripts/validate_all_proposals.py` | 150 | 批量提案验证 | ✅ 已实现 |
| `scripts/quality_predictor.py` | 536 | 质量预测器（频率模型） | ✅ 已实现 |
| `scripts/diversity_metrics.py` | 308 | 多样性指标 | ✅ 已实现 |
| `scripts/monitor_metrics.py` | 364 | 每日监控 | ✅ 已实现 |
| `scripts/generate_weekly_report.py` | - | 周报生成 | ✅ 已实现 |

### 5.2 集成文件

| 文件 | 集成内容 | 状态 |
|------|---------|------|
| `scripts/sup_harvest.py` | 短窗预筛、质量预测、提案卫生、bandit 反馈 | ✅ 已集成 |
| `scripts/aligned_slow_loop.py` | 慢环验证 | ✅ 运行中 |
| `cascade/peer/*.py` | peer 生成/写盘 | ❌ 未集成（praxist 框架内） |

### 5.3 测试文件

| 文件 | 测试数 | 状态 |
|------|--------|------|
| `tests/test_generation_strategy.py` | 24 | ✅ 全通过 |
| `tests/test_short_window_backtest.py` | 7 | ✅ 全通过 |
| `tests/test_proposal_validator.py` | 26 | ✅ 全通过 |
| `tests/test_quality_predictor.py` | 24 | ✅ 全通过 |
| `tests/test_diversity_metrics.py` | 11 | ✅ 全通过 |
| `tests/test_monitor_metrics.py` | 17 | ✅ 全通过 |
| **总计** | **109** | ✅ 全通过 |

### 5.4 数据文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `models/quality_model.json` | 质量预测模型 | ✅ 已训练 |
| `data/cache/bandit_feedback.jsonl` | bandit 反馈 | ✅ harvest 写入 |
| `data/cache/short_window_results.jsonl` | 短窗回测结果 | ✅ 缓存 |
| `data/cache/metrics_history/` | 指标历史 | ⚠️ 需 crontab |
| `data/cache/variant_registry.jsonl` | variant 注册表 | ✅ 已实现 |

### 5.5 文档文件

| 文件 | 说明 |
|------|------|
| `docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog.md` | Phase 2-3 执行 changelog |
| `docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md` | Phase 2-3 审计报告 |
| `docs/superpowers/reports/monitoring_example.md` | 监控示例报告 |
| `docs/diversity-metrics-guide.md` | 多样性指标指南 |
| `docs/quality_predictor.md` | 质量预测器文档 |
| `.omc/ultragoal/plans/phase2-3-execution-plan.md` | Phase 2-3 执行计划 |

### 5.6 praxist 框架文件

| 文件/目录 | 说明 |
|----------|------|
| `.venv/lib/python3.11/site-packages/praxist/` | praxist 包根目录 |
| `.venv/lib/python3.11/site-packages/praxist/run.py` | praxist 运行逻辑 |
| `.venv/lib/python3.11/site-packages/praxist/cli/monitor.py` | peer 监控 |
| `.venv/lib/python3.11/site-packages/praxist/cli/status.py` | peer 状态 |
| `docs/archive/peer-proposals-pre-0918/run_*//.runtime_guards/*/python_site/sitecustomize.py` | sitecustomize 注入示例 |

---

## 六、结论与建议

### 6.1 核心障碍

**praxist 框架限制** 是 Phase 2-3 主路径集成未完成的主要原因。peer 生成/写盘逻辑在外部框架内，无法注入自定义逻辑，导致：
- 生成策略无法影响 peer 生成
- 多样性奖励无法影响 peer 生成
- 提案卫生无法在 peer 写盘前验证

### 6.2 建议优先级

1. **立即执行**（10 分钟）：配置 crontab 自动化监控
2. **短期执行**（1-2 周）：运行短窗回测收集效果数据
3. **中期决策**（1-3 周）：选择 praxist 集成方案（fork/PR/sitecustomize）
4. **长期规划**（1-3 月）：评估是否将 peer 生成逻辑抽离到本仓库

### 6.3 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| praxist 升级破坏 sitecustomize 注入 | 锁定 praxist 版本，定期测试兼容性 |
| fork praxist 维护成本高 | 尽量提交上游 PR，减少 fork 差异 |
| 短窗回测效果不达预期 | 调整阈值或关闭短窗预筛 |
| 监控自动化未部署导致指标缺失 | 立即配置 crontab，添加告警 |

---

**报告结束**

**下一步行动**：
1. 配置 crontab 自动化监控（立即）
2. 决策 praxist 集成方案（本周内）
3. 实施选定的集成方案（1-3 周）
4. 收集短窗回测效果数据（1-2 周）
