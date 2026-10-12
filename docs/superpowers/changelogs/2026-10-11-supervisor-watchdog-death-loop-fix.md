# Changelog: Supervisor/看门狗死循环修复

**日期**：2026-10-11  
**commit**：`d7c5bf2`  
**关联报告**：`docs/superpowers/reports/2026-10-11-supervisor-watchdog-death-loop-audit.md`  
**关联计划**：`docs/superpowers/plans/2026-10-11-supervisor-death-loop-fix-plan-audit.md`

## 问题

`ensure_baselines()` 启动期基线重生阻塞 25-30 分钟不写 heartbeat → 看门狗 S2 误判 stale（阈值 12min）→ SIGTERM → 无限循环。40 小时停机，~18 个 supervisor 实例被拉起又杀掉，有效工作时间 = 0 秒。

## 根因

1. **设计缺陷**：`_write_heartbeat()` 仅在主循环内调用，`ensure_baselines` 在主循环外且运行时间长
2. **看门狗逻辑漏洞**：S2 判定无启动宽限期，刚启动的 supervisor 立即被判 stale
3. **HEALED 状态不验活**：start_supervisor.sh 成功即报 HEALED，不验证心跳是否推进

## 修复

### 补丁 0：`_write_heartbeat` 节流（`praxist_supervisor.py`）
- 加 `_LAST_HB_WRITE` 模块级变量 + `time.monotonic()` 节流 ≤1 次/秒
- 防止紧循环（如 `ensure_baselines` 每 symbol 调用）触发 I/O 风暴

### P0-A：`ensure_baselines` 循环加心跳（`praxist_supervisor.py`）
- 用 `try/finally` 包裹 `for sym in sorted(symbols):` 循环体
- `finally` 块调用 `_write_heartbeat()`（节流后每秒最多 1 次）
- 覆盖所有 `continue` 路径

### P0-A 补充：`generate()` 内每 50 点写心跳（`generate_baseline_points.py`）
- **发现问题**：P0-A 只包外层循环，单 symbol 重生 25min 期间 finally 不执行
- **修复**：在 `generate()` 的进度打印处（每 50 点）调用 `_hb()`
- try/except 包裹 import，独立运行时降级为空函数

### P0-B：看门狗 S2 加 30 分钟启动宽限期（`diagnose_three_loop.sh`）
- 在判定块前插入 `SUP_START_MINS` 计算（`_spb_` 前缀变量隔离 + unset）
- S2 条件改为 `SUP_START_MINS >= 30 AND HB_AGE > 12`
- S2 动作消息带 uptime 信息方便诊断

### P1-A v2：skip-kill + skip start（`diagnose_three_loop.sh`）
- 宽限期内（`SUP_START_MINS < 30`）跳过 kill + 跳过 start_supervisor.sh
- 设置 `STATE="HEALTHY"` 直接退出 AUTO_HEAL 块
- 避免新进程撞 Python flock 秒退导致日志噪音

### P1-B v2：区分冷启动/热重启验活（`diagnose_three_loop.sh`）
- `WAS_SUPERVISOR_UP` 变量保存原始状态
- 冷启动路径（S1 或刚 kill）：用 `pgrep` 弱验活（进程活着即 HEALED）
- 热重启路径：保留 `stat mtime` 强验活
- 下一轮巡检 S2/S4 兜底卡死进程

## 迭代历史

- **v1**：P1-A/P1-B 初版 → code-reviewer **REQUEST_CHANGES**
  - [HIGH] S1 冷启动 5s 验活必失败（supervisor 加载 TimesFM >10s）
  - [MEDIUM] skip-kill + start_supervisor.sh 撞 Python flock
- **v2**：采纳 reviewer 建议 → code-reviewer **APPROVE**

## 验证

- ✅ pytest 全通过
- ✅ 集成测试：supervisor 启动 32 分钟，heartbeat 持续更新（< 60s）
- ✅ 成功进入主循环（phase=slow，current_batch 跑评估）
- ✅ 看门狗未误杀（宽限期保护生效）

## 影响

- **性能**：无负面影响（节流后心跳 I/O 可忽略）
- **可靠性**：彻底终结死循环，supervisor 可稳定运行
- **可观测性**：S2 消息带 uptime 信息，便于诊断
