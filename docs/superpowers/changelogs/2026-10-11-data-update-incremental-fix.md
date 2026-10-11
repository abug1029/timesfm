# Changelog: 数据更新系统增量模式修复

**日期**：2026-10-11  
**commits**：`d5d7309`（P0/P1 + AST 闸门）+ `df537e7`（固化设计原则）  
**关联报告**：Explore agent 调研（2026-10-11，数据更新架构 + 历史演变）  
**关联计划**：`docs/superpowers/plans/2026-10-11-data-update-incremental-fix-plan-audit.md`

## 问题

`data_management.py --1h --daily` 超时预算 **75 分钟**，实际跑 20+ 分钟。根因：
- `pull_history_1h.py` 在每日流程里做全量 DELETE + INSERT 10000 bars/symbol
- `daily_update.py` 的 `collect_1h_main_only()` 未同步 2026-07-15 Lesson #11 修复
- `data_management.py` 的 `collect_1h()` 先调增量版再调全量版，增量修复完全无效

## 根因（历史演变）

- **2026-07-15 Lesson #11**：记录 "DELETE 全表 + INSERT 是定时炸弹"，`collect_1h.py` 修复为 INSERT OR REPLACE + MIN_1H_ROWS
- **但 `daily_update.py` 未同步修复**，仍保留全量 DELETE + INSERT
- **2026-09-03 初始提交**：`data_management.py` 同时调增量版和全量版，使增量修复完全无效
- **历史教训未固化**：仅停留在 memory 文件，未落实到代码注释、测试、文档

## 修复（TDD 方法）

### 步骤 0：先写 AST 闸门测试（`tests/test_no_full_wipe.py`）
- **test_no_bare_delete_from_kline**：扫描 `scripts/*.py` 检测裸 DELETE
- **test_collect_1h_main_only_is_incremental**：specific to daily_update.py
- **test_data_management_no_pull_history**：确保 collect_1h() 不调用 pull_history_1h.py
- 实测失败（红灯），找到 4 处违规（daily_update / pull_history_1h / data_audit × 2）

### P0-A：`daily_update.py` 增量模式对齐
- **原代码**：`DELETE FROM kline_1h WHERE contract_code = ?`（裸 DELETE）
- **修复**：对齐 `collect_1h.py` 增量模式
  - INSERT OR REPLACE（`store_klines_1h` 内部已支持）
  - MIN_1H_ROWS = 500 保护（防 TqSdk 网络异常）
  - 防御性 DELETE 仅清 dt > new_max（未来 bar）

### P0-B：`data_management.py` 移除 `pull_history_1h.py` 调用
- **原代码**：`collect_1h()` 先调 `collect_1h.py` 再调 `pull_history_1h.py`
- **修复**：移除 `pull_history_1h.py` 调用，仅保留 `collect_1h.py`
- 注释说明手动重建方式：`python scripts/pull_history_1h.py`

### P1：`pull_history_1h.py` 加 DESIGN RISK + ALLOWED + MIN_ROWS
- 文件头加 DESIGN RISK 警告（仅初始化/灾难恢复用）
- DELETE 语句加 `# ALLOWED: 初始化专用` 注释
- 写入后检查 MIN_ROWS = 500，不足则打印 ERROR（不回滚）

### 固化 1：代码注释（3 处 DESIGN RISK）
- `daily_update.py`：已修复为增量模式，禁止退回
- `data_management.py`：已移除 `pull_history_1h.py` 调用
- `pull_history_1h.py`：仅初始化用，禁止被日常流程调度

### 固化 2：AST 闸门测试（3 个）
- 见步骤 0。所有测试 pytest 通过（0.33s）。

### 固化 3：CLAUDE.md 新增"数据采集设计原则"章节
- 5 条不可退化原则（增量更新 / 全量仅限初始化 / MIN_1H_ROWS / 单一采集路径 / 测试防护）
- 位置：数据管理策略章节末尾

### 固化 4：`data/AGENTS.md` 新增"采集策略"小节
- 权威实现清单（collect_1h / daily_update / data_management）
- 特殊路径说明（pull_history_1h / backfill_gaps）
- 历史教训（Lesson #11 + 2026-10-11 修复）

## 迭代历史

- **TDD 红灯**：3 个测试按预期失败，失败信息可操作
- **code-reviewer v1**：REQUEST_CHANGES
  - [HIGH] test 3 正则 bug（`[^)]+` 不处理返回类型注解）
  - [MEDIUM] 失败信息用占位符
  - [LOW] data_audit.py 应加 ALLOWED
- **v2 修复**：采纳 reviewer 建议
- **code-reviewer v2**：APPROVE
  - 3 个 finding 全部 FIXED
  - 新发现：`backfill_gaps()` 仍调用 pull_history_1h.py（合法例外，已加 ALLOWED 注释）

## 验证

- ✅ pytest 全通过（3 个 AST 闸门测试，0.33s）
- ✅ 性能预期：耗时从 75 分钟预算降到 6-10 分钟（待集成测试确认）
- ✅ AST 闸门可检测未来退化

## 影响

- **性能**：移除 `pull_history_1h.py` 日常调用，节省 29 分钟 timeout 预算
- **可靠性**：消除"定时炸弹"（全量 DELETE 在网络异常时摧毁历史数据）
- **可维护性**：设计原则文档化（CLAUDE.md + data/AGENTS.md），测试防护自动化

## 后续

- ⏸ 集成测试：`data_management.py --1h --daily` 验证实际耗时
- ⏸ 恢复 supervisor 运行 + 看门狗 cron
- ⏸ 监控 1 周确认无回归
