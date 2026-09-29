# supervisor 重启待办

> 登记日期: 2026-09-17。**不重启运行中的 supervisor**；以下两项在下次 supervisor 自然停止或显式重启时一并实施。

## 1. 菜单 track 行固定前缀「【旧口径线索·非证据】」

- 位置: `scripts/praxist_supervisor.py:745` 附近，`materialize_covariate_menu` 渲染 track 行处：
  `tr = " [track: %s]" % v["track_record"] ...`
- 做法: 给菜单 track 行加固定前缀「【旧口径线索·非证据】」（防御性，防止 pool 未来再写入裸数字时被当作证据）。
- 背景: pool 源头已在 2026-09-17 去数字（covariate_pool 内 10 条 v22 旧口径 track_record 标注，见 git log）。

## 2. IDLE_HOLD 守卫等价物

- 背景: 原 `scripts/start_praxist.sh`（已归档至 `docs/archive/batch/`）启动前检查 `docs/superpowers/reports/praxist_20260907_ctrl/IDLE_HOLD` 文件，存在即拒绝启动（exit 78），作为启动守卫。
- 现状: 脚本归档后该守卫失去入口，当前无引用。
- 做法: 如需该功能，应在 supervisor 侧补等价实现（启动周期检查 IDLE_HOLD 标记文件，存在则拒绝启快环）。当前仅为登记，无实施计划。

## 3. 加载 2026-09-29 的 4 个 commit（**当前最紧要**）

- 背景: supervisor PID 22703 于 2026-09-28 18:54 启动，其内存里是当天的代码。
  磁盘上已有 4 个未加载的 commit：`a068d92`（ponytail 清理 + 第六轮 K4/K6/K7/M4）、
  `381f31e`（spec-alignment Phase 1-10）、`4c347df`（changelog）、
  `b8a6d36`（第七轮：退役 smoke 测试）。
- 风险: 未加载期间，监督环派生出的慢环子进程会执行**未加载的新代码**，而 verdict
  仍按旧 schema 记账 —— 即"新代码语义 + 旧 schema 记账"的混版本窗口。
- 做法: 走 `scripts/stop_supervisor.sh` → 归档 `logs/supervisor.log` →
  `setsid nohup scripts/start_supervisor.sh`。
- **完整步骤与 6 条验收标准**：`D:\FlyBuddy\.omc\artifacts\sixth-audit-supervisor-restart-runbook.md`
- 验收重点（本次两个实质修复的直接验证）:
  - `grep -c "v1 legacy: pass by ev>0" task_FM/known_verdicts.inc.md` → 应为 **1**（图例去重，K6）
  - `grep -c "gate_pass=True" task_FM/known_verdicts.inc.md` → 应为 **43**
    （截断只切尾部，M4；**修复前只有 20/42**，「已解出」的 22 条被静默吞掉）
- 前置: `scripts/restart_readiness_check.py` 应 16/16 通过；确认无持有者已死的 `*.lock`

## 处置记录

- 2026-09-17: 显式重启时实施第 1 项 —— praxist_supervisor.py:749 track 行已加固定前缀「【旧口径线索·非证据】」（test_supervisor/test_covariate_pool 47 passed）。第 2 项维持登记：本次以启动前人工检查 IDLE_HOLD（不存在，放行）履行守卫职责。
- 2026-09-17: supervisor 已重启（PID 546，setsid 脱离进程树，日志 data/cache/supervisor_loop.out）。
