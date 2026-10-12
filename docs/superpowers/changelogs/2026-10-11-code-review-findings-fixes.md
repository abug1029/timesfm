# Changelog: Code-Reviewer Findings 修复

**日期**：2026-10-11  
**commit**：`8d124ab`  
**关联审核**：code-reviewer (Opus) 审核今天所有改动（2026-10-11）

## 审核结果

- **结论**：APPROVE（附修复建议）
- **Findings**：1 MAJOR + 6 MINOR + 1 NIT
- **修复**：1 MAJOR + 5 MINOR + 1 NIT（第 6 个 MINOR 接受现状，acceptable as-is）

## 修复清单

### [MAJOR] generate_baseline_points.py import 顺序

**问题**：`from praxist_supervisor import _write_heartbeat` 在 `sys.path.insert` 之前，standalone CLI 运行时 import 失败（fallback 到 no-op），P0-A 补丁失效。

**修复**：移动 `sys.path.insert` 到 line 25（import 之前）。

**影响**：supervisor 调用路径正常（supervisor 的 sys.path 已覆盖），仅 standalone CLI 受影响。修复后两种路径都正常。

---

### [MINOR] praxist_supervisor.py 节流定时器失败时不重置

**问题**：`_LAST_HB_WRITE` 仅在成功写入时更新。若 `os.makedirs` 或 `open()` 持续抛 `OSError`，节流窗口过后每秒重试并打印 stderr warning（stderr spam at 1Hz）。

**修复**：加 `finally` 块，无论成功失败都更新 `_LAST_HB_WRITE`。

**影响**：防止持续失败时的日志噪音。功能不受影响（失败仍会打印 warning，但只一次）。

---

### [MINOR] diagnose_three_loop.sh $SUP_PIDS 未加空值守卫

**问题**：`for _spb_pid in $SUP_PIDS` 在 `SUP_PIDS` 为空时循环一次（空字符串），导致 `ps -p ''` 报错（被 `2>/dev/null` 抑制），`_spb_mins` 变为 0，`SUP_START_MINS` 错误设为 0 而非 999。

**修复**：加 `if [ -n "$SUP_PIDS" ]; then ... fi` 守卫。

**影响**：实际场景不会触发（S1 检查保证 supervisor up 时 `SUP_PIDS` 非空），但更健壮。

---

### [MINOR] diagnose_three_loop.sh WAS_SUPERVISOR_UP 命名语义混淆

**问题**：`WAS_SUPERVISOR_UP` 实际表示"是否需要冷启动验活"（0 = cold, 1 = hot），不是"之前 supervisor 是否在跑"。命名导致阅读困难。

**修复**：重命名为 `NEEDS_COLD_START`，并在第一次赋值处加注释说明语义。

**影响**：纯可读性改进，逻辑不变。

---

### [MINOR] daily_update.py + collect_1h.py datetime import 位置

**问题**：`from datetime import datetime` 在函数体内（inline import），不符合 Python 风格指南。

**修复**：移到文件顶部 import 区。

**影响**：无功能影响，仅代码风格。

**附注**：按需拉取逻辑在两个文件中重复（违反"单一采集路径"原则），但按 Ponytail 原则暂不提取辅助函数（P2 refactor candidate）。

---

### [MINOR] data/AGENTS.md 重复 `## Dependencies` 标题

**问题**：commit `df537e7` 插入"采集策略"章节时，保留了原有的 `## Dependencies`，导致两个连续同名标题。

**修复**：删除 line 93 的重复标题。

**影响**：纯文档格式修复。

---

### [MINOR] tests/test_no_full_wipe.py regex 脆弱性

**问题**：`r'def collect_1h_main_only\([^)]+\):.*?(?=\ndef |\Z)'` 在多行函数签名时会失败。

**状态**：**Acceptable as-is**（当前代码都是单行签名，regex 工作正常）。

**未来改进**：可改用 AST 解析（已 import `ast`），但当前优先级低。

---

### [NIT] collect_1h.py datetime import 位置

**问题**：同 MINOR #5。

**修复**：已一并修复（移到文件顶部）。

---

## 验证

- ✅ pytest 全通过（3 个 AST 闸门测试，0.23s）
- ✅ bash -n 通过（diagnose_three_loop.sh）
- ✅ Python AST parse 通过（所有修改的 .py 文件）

## 影响

- **可靠性**：防止 standalone CLI 静默失败（MAJOR）
- **可观测性**：减少持续失败时的日志噪音（MINOR #2）
- **健壮性**：空值守卫防止边界条件报错（MINOR #3）
- **可读性**：变量重命名 + 注释说明（MINOR #4）
- **代码风格**：import 位置规范化（MINOR #5 + NIT）
- **文档格式**：删除重复标题（MINOR #6）

## 后续

- ⏸ P2 refactor candidate：提取按需拉取逻辑为共享辅助函数（消除 daily_update.py + collect_1h.py 重复）
- ⏸ 恢复 supervisor + 看门狗 cron
- ⏸ 监控 1 周确认无回归

---

**全部 code-reviewer findings 处理完毕。今天的工作可以收尾。**
