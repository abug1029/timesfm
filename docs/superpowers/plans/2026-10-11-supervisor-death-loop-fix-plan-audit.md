# Supervisor/看门狗死循环修复实施计划（审计版）

> **代码基线**: `d7c5bf2`

> **关联报告**：`docs/superpowers/reports/2026-10-11-supervisor-watchdog-death-loop-audit.md`
> **计划日期**：2026-10-11
> **计划状态**：**已审阅 / 待执行**
> **预计工时**：~1.5 小时（含 45 分钟集成测试等待）
> **本版本**：v2 审计版（基于 v1 审阅反馈落档）

## 1. 范围与原则

**只动必要代码**。本次目标 = 终结死循环，不做架构重构。遵循 Ponytail 原则（最小修改、YAGNI、双保险但要短）。

| 类别 | 是否包含 | 理由 |
|---|---|---|
| ✅ P0-A：`ensure_baselines` 内写 heartbeat | **做** | 根治死循环 |
| ✅ P0-B：看门狗 S2 加 30 分钟启动宽限期 | **做** | 双保险 |
| ✅ P1-A：看门狗触发 kill 前检查 PID 启动时长 | **做** | 防乱杀，与 P0-B 协同 |
| ✅ P1-B：HEALED 状态要验活 | **做** | 防误报，低成本 |
| ❌ P2.1：Windows WSL 频繁重启排查 | **不做** | 独立事件，不在本次范围 |
| ❌ P2.2：heartbeat 独立线程重构 | **不做** | 过度设计，P0+P1 已足够 |

## 2. 修复清单（详细）

### P0-A：`ensure_baselines` 内每 symbol 完成后写 heartbeat

**文件**：`scripts/praxist_supervisor.py:3988-4073`（`ensure_baselines` 函数）

**当前代码结构**（关键片段）：

```python
def ensure_baselines(symbols, root):
    ...
    for sym in sorted(symbols):
        sym_lower = sym.lower()
        points_path = os.path.join(config_dir, gbp.baseline_filename(sym_lower, None))
        met = metrics.get(sym_lower, {})
        if not isinstance(met, dict) or not met.get("n"):
            _regen_baseline_with_archive(sym_lower, points_path, root)
            continue
        ...
        if n_lines < 100:
            _regen_baseline_with_archive(sym_lower, points_path, root)
            continue
        # 协议指纹校验
        ...
        _regen_baseline_with_archive(sym_lower, points_path, root)
```

**改动方案**：在 `for sym in sorted(symbols):` 循环的**每次迭代末尾**调用 `_write_heartbeat()`。

**实现技巧**：用 `try: ... finally: _write_heartbeat()` 包每次迭代（无论 continue 还是 fall-through 都写），确保所有分支都覆盖。

```python
def ensure_baselines(symbols, root):
    ...
    for sym in sorted(symbols):
        try:
            sym_lower = sym.lower()
            ...（原循环体）...
        finally:
            _write_heartbeat()   # ← 新增：每个 symbol 处理完后写心跳
```

**最小化原则**：
- ✅ 不改函数签名
- ✅ 不加参数
- ✅ 不在 `_regen_baseline_with_archive` 内部写（那是重生路径，只在需要重生时跑）
- ✅ 不在主循环外另开线程

**风险**：写心跳过于频繁（symbol 重生时几百次/秒）。
**应对**：`_write_heartbeat()` 内部加 monotonic 节流（≤1 次/秒），见补丁 0。

---

### 补丁 0（前置）：`_write_heartbeat()` 加节流

**文件**：`scripts/praxist_supervisor.py:681-689`

**当前代码**：

```python
def _write_heartbeat():
    """Write heartbeat timestamp. Called each main loop iteration."""
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump({"ts": _now_iso(), "run_id": _run_id(), "pid": os.getpid()}, f)
    except Exception as e:
        print(f"[WARN] Failed to write heartbeat: {e}", file=sys.stderr)
```

**改动**：加模块级 `_LAST_HB_WRITE = 0.0`，函数内 `if time.monotonic() - _LAST_HB_WRITE < 1.0: return`。

```python
_LAST_HB_WRITE = 0.0

def _write_heartbeat():
    """Write heartbeat timestamp. Called each main loop iteration.

    Throttled to at most once per second to avoid I/O spam when called
    from tight loops (e.g. ensure_baselines per-symbol regen).
    """
    global _LAST_HB_WRITE
    now = time.monotonic()
    if now - _LAST_HB_WRITE < 1.0:
        return
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump({"ts": _now_iso(), "run_id": _run_id(), "pid": os.getpid()}, f)
        _LAST_HB_WRITE = now
    except Exception as e:
        print(f"[WARN] Failed to write heartbeat: {e}", file=sys.stderr)
```

---

### P0-B：看门狗 S2 加 30 分钟启动宽限期

**文件**：`scripts/diagnose_three_loop.sh:213-216`

**当前代码**：

```bash
elif [ "$SUPERVISOR_UP" -eq 0 ]; then
  STATE="AUTO_HEAL"; ACTION="S1 supervisor down"
elif [ "$HB_AGE" -gt 12 ]; then
  STATE="AUTO_HEAL"; ACTION="S2 heartbeat stale ${HB_AGE}min"
```

**改动**：在 S2 判定前插入 PID 启动时长计算，把原 `elif` 改为带宽限期检查：

```bash
elif [ "$SUPERVISOR_UP" -eq 0 ]; then
  STATE="AUTO_HEAL"; ACTION="S1 supervisor down"
else
  # 计算 supervisor 最小启动时长（取所有 PID 中最年轻的）
  SUP_START_MINS=999
  for pid in $SUP_PIDS; do
    ETIME=$(ps -p $pid -o etimes= 2>/dev/null | tr -d ' ')
    if [ -n "$ETIME" ]; then
      ETIME_MINS=$((ETIME / 60))
      [ $ETIME_MINS -lt $SUP_START_MINS ] && SUP_START_MINS=$ETIME_MINS
    fi
  done

  if [ "$SUP_START_MINS" -lt 30 ]; then
    : # 启动宽限期内（<30min），跳过 S2 判定（基线重生就是这期间）
  elif [ "$HB_AGE" -gt 12 ]; then
    STATE="AUTO_HEAL"; ACTION="S2 heartbeat stale ${HB_AGE}min (uptime ${SUP_START_MINS}m)"
  fi
fi
```

**关键**：`SUP_START_MINS >= 30`（≥30 分钟才判定 stale），让基线重生（~25-30min）完整跑完。

---

### P1-A：看门狗触发 kill 前检查 PID 启动时长

**文件**：`scripts/diagnose_three_loop.sh:248-254`（自愈分支）

**当前代码**：

```bash
if [ "$SUPERVISOR_UP" -eq 1 ]; then
  kill -TERM $SUP_PIDS 2>/dev/null
  sleep 3
fi
if O=$(bash scripts/start_supervisor.sh 2>&1); then
  STATE="HEALED"
  record_heal_success
else
  STATE="NEEDS_HUMAN"
  ACTION="heal restart FAILED: $O"
  record_heal_failure
fi
```

**改动**：`kill -TERM $SUP_PIDS` 前复用 P0-B 的 `$SUP_START_MINS`，若 < 30 分钟则跳过 kill。

```bash
if [ "$SUPERVISOR_UP" -eq 1 ]; then
  if [ "$SUP_START_MINS" -lt 30 ]; then
    log "supervisor 启动仅 ${SUP_START_MINS}min，跳过 kill（宽限期）"
  else
    kill -TERM $SUP_PIDS 2>/dev/null
    sleep 3
  fi
fi
```

**注意**：`$SUP_START_MINS` 必须在 P0-B 的 `else` 分支里已赋值；若进入 S1 分支（supervisor 不在），`SUP_START_MINS` 仍是 999，逻辑仍对。

---

### P1-B：HEALED 状态要验活

**文件**：`scripts/diagnose_three_loop.sh:251-256`

**当前代码**：

```bash
if O=$(bash scripts/start_supervisor.sh 2>&1); then
  STATE="HEALED"
  record_heal_success
else
  STATE="NEEDS_HUMAN"
  ACTION="heal restart FAILED: $O"
  record_heal_failure
fi
```

**改动**：`start_supervisor.sh` 成功后，等 5 秒再检查 heartbeat mtime 是否更新。

```bash
if O=$(bash scripts/start_supervisor.sh 2>&1); then
  sleep 5
  NEW_HB_MTIME=$(stat -c %Y "$HB_FILE" 2>/dev/null || echo 0)
  if [ "$NEW_HB_MTIME" -gt "$HB_MTIME" ]; then
    STATE="HEALED"
    record_heal_success
  else
    STATE="NEEDS_HUMAN"
    ACTION="heal started but heartbeat not advancing"
    record_heal_failure
  fi
else
  STATE="NEEDS_HUMAN"
  ACTION="heal restart FAILED: $O"
  record_heal_failure
fi
```

**风险**：`sleep 5` 拖慢看门狗循环。
**应对**：只拖 5 秒，可接受（看门狗 15min 一轮）。

## 3. 实施顺序

| 步骤 | 动作 | 验证 |
|---|---|---|
| 1 | `git checkout -b fix/death-loop-20261011` | 分支干净 |
| 2 | 实施补丁 0（`_write_heartbeat` 节流） | pytest 通过 + 单测覆盖 |
| 3 | 实施 P0-A（ensure_baselines 心跳） | pytest 通过 + 单测覆盖 |
| 4 | 实施 P0-B（S2 宽限期） | shellcheck 通过 |
| 5 | 实施 P1-A（kill 前宽限期） | shellcheck 通过 |
| 6 | 实施 P1-B（HEALED 验活） | shellcheck 通过 |
| 7 | 集成测试：手动 kill supervisor → 看门狗拉起 → 等 30 分钟确认不再被误杀 | heartbeat 持续更新 + 进程 uptime ≥ 30min |
| 8 | 进入主循环后观察 2 小时，确认 `cycles_done` 增长 | verdicts 文件有新内容 |
| 9 | git commit + PR | 合 master |

## 4. 验证标准（DoD）

- ✅ pytest 全通过（含现有 `test_v4_window_anchor` 等）
- ✅ shellcheck `diagnose_three_loop.sh` 无 warning
- ✅ 手动触发：supervisor 启动后 30 分钟内不被看门狗杀（即使 heartbeat 短暂不更新）
- ✅ 30 分钟后若 heartbeat 仍过期，看门狗才触发 kill
- ✅ 重启 supervisor 后 2 小时内 `cycles_done` 至少 +1
- ✅ 新增单测：
  - `test_write_heartbeat_throttle`：验证 1 秒内多次调用只写一次
  - `test_ensure_baselines_writes_heartbeat`：验证 ensure_baselines 循环中调用 heartbeat

## 5. 风险与回滚

| 风险 | 应对 |
|---|---|
| P0-A 写心跳过于频繁（symbol 重生时几百次/秒） | 补丁 0：加 monotonic 节流（≤1 次/秒） |
| P0-B 宽限期太长导致真 stale 不恢复 | 阈值 30min 略大于基线重生时间 25min，留 5min 余量；可调 |
| P1-B 验活 sleep 5s 拖慢看门狗循环 | 只拖 5 秒，可接受 |
| 修复后 WSL 又频繁重启 | 独立事件（P2.1），不在本次范围 |
| 补丁引入回归 | git revert HEAD 即可，所有改动都是增量补丁 |

## 6. 工作量估算

| 任务 | 时间 |
|---|---|
| 补丁 0 + P0-A 编码 + 单测 | 15 min |
| P0-B 编码 + shellcheck | 10 min |
| P1-A + P1-B 编码 | 10 min |
| 集成测试 | 45 min（含等待） |
| PR 审查 + 合入 | 15 min |
| **总计** | **~1.5 小时** |

## 7. 验收后跟进

- [ ] 更新 `CLAUDE.md` / `AGENTS.md`：记录 P0 修复（`ensure_baselines` 现在写心跳）
- [ ] 更新运维记忆（`fm-ops.md`）：移除"SIGTERM 首次会被忽略"的旧建议（P1-A 后不再需要双 kill）
- [ ] 监控 1 周，确认无回归
- [ ] 评估 P2.2（heartbeat 独立线程）是否仍有必要（预计不需要）

## 8. 审阅修订说明（v1 → v2）

本次修订基于用户审阅反馈，主要调整：

| 项 | v1 | v2（审计版） | 理由 |
|---|---|---|---|
| 状态 | 待审阅 | 已审阅 / 待执行 | 用户已审阅完成 |
| 文档名 | `...-fix-plan.md` | `...-fix-plan-audit.md` | 标记为审计版本 |
| 版本标识 | 无 | v2 审计版 | 明确版本演进 |
| 内容修订 | — | 内容主体保持 v1 原样 | 用户已批准 v1 范围和技术方案 |

**用户决策记录**（v1 待确认项 → v2 决议）：

| 决策项 | 用户答复 |
|---|---|
| 范围（P0+P1，不做 P2） | ✅ 同意 |
| 30 分钟宽限期阈值 | ✅ 同意 |
| sleep 5s 验活策略 | ✅ 同意 |
| `_write_heartbeat` 1 秒节流 | ✅ 同意 |

**未变更**：所有技术细节、代码补丁、实施顺序、DoD 均保持 v1 原样。

## 9. 下一步

回复「开始执行」即可进入实施阶段（从补丁 0 开始，按 §3 顺序执行）。

---

**文档版本**：v2 审计版 · 2026-10-11
