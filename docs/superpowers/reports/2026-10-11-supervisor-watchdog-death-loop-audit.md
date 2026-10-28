# FM_a Supervisor/看门狗死循环审计报告

> **代码基线**: `d7c5bf2`

> **事件窗口**：2026-10-08 21:15 → 2026-10-10 13:15（共 **40 小时**）
> **影响**：supervisor 启动 ~18 次，全部卡在启动期基线重生，从未进入正常工作 cycle；`cycles_done` 停在 28（2 天未增）
> **调查人**：Claude Code
> **调查日期**：2026-10-10（初版）→ 2026-10-11（修订落档）

## TL;DR

**死循环**：`ensure_baselines()` 跑 jd 基线重生需 25-30 分钟 → 期间不写 heartbeat → 看门狗 S2 误判 stale（阈值 12 min）→ SIGTERM → 重启 → 又卡 ensure_baselines → 无限循环。40 小时内 supervisor 启动 ~18 次，每次刚跑完基线就被杀，**有效工作时间 = 0 秒**，浪费 **~120 CPU-hour**。

## 🔍 直接死因链

```
1. 10-08 21:15 supervisor (PID 271176) 干净退出 (signal_received, exit 0, uptime 10h)
    ↓
2. 看门狗 diagnose.sh 检测到 S1 (supervisor down)，触发 AUTO_HEAL
    ↓
3. 新 supervisor 启动，进入 ensure_baselines() 跑基线重生（jd 缺覆盖窗 → 需重生 589 点）
    ↓
4. 基线重生耗时 25-30 分钟，期间 heartbeat 停在旧值（主循环前无心跳写入）
    ↓
5. 看门狗 12 分钟后再次巡检，判定 S2 (heartbeat stale > 12min) → SIGTERM 杀掉
    ↓
6. 新 supervisor 刚启动基线重生又被杀 → 无限循环
```

### 证据

- **`supervisor_events.jsonl`**（10-08 21:36 → 10-10 01:58）：~18 个不同 PID，uptime 全在 1189-1829 秒（19-30 分钟）之间 —— 正是基线重生耗时
- **`supervisor_heartbeat` mtime** 停在 `2026-10-10 01:58:22`（PID 572 启动时写了一次，之后再未更新）
- **`supervisor.out`** 反复出现 `ensure_baselines: jd 基线末端 2026-09-23 15:00:00 未覆盖确认窗起点 2026-10-03 00:00:00（数据已到位 → 拉取日重锚） → 重生`，每次重生跑到 400-500/589 就被杀
- **`diagnose.log`** 反复出现 `HEALED [S2 heartbeat stale 25min/55min/631min]` —— 实际是看门狗在误杀刚启动的 supervisor

## 🎯 系统性缺陷（三层）

### 缺陷 1：`ensure_baselines` 在主循环外，不写心跳（设计缺陷）

**代码位置**：`scripts/praxist_supervisor.py:4338-4348`

```python
def _main_locked(args):
    # Pre-flight: ensure baseline metrics/points exist
    try:
        goal_for_baselines = load_goal(args.goal)
        ensure_baselines(_goal_target_symbols(goal_for_baselines), args.root)  # ← 卡 25-30 分钟，无心跳
    except Exception as e:
        print(f"[ERROR] ensure_baselines pre-flight failed: {e}", file=sys.stderr)
    while True:
        _write_heartbeat()  # ← 只有进入主循环才写心跳
        ...
```

**修法**：`ensure_baselines` 内部每处理完一个 symbol 就写一次 heartbeat，或把 ensure_baselines 移入主循环的首次迭代。

### 缺陷 2：看门狗 S2 判定没考虑"启动宽限期"（逻辑漏洞）

**代码位置**：`scripts/diagnose_three_loop.sh:210-214`

```bash
elif [ "$SUPERVISOR_UP" -eq 0 ]; then
  STATE="AUTO_HEAL"; ACTION="S1 supervisor down"
elif [ "$HB_AGE" -gt 12 ]; then  # ← 启动后立即生效，没宽限期
  STATE="AUTO_HEAL"; ACTION="S2 heartbeat stale ${HB_AGE}min"
```

**修法**：加 PID 启动时间检查 —— 若 supervisor 刚启动 <30 分钟，跳过 S2 判定（基线重生就是这期间）。

```bash
# 提议补丁
SUP_START_MINS=999
for pid in $SUP_PIDS; do
  ETIME=$(ps -p $pid -o etimes= 2>/dev/null | tr -d ' ')
  [ -n "$ETIME" ] && ETIME_MINS=$((ETIME / 60)) && [ $ETIME_MINS -lt $SUP_START_MINS ] && SUP_START_MINS=$ETIME_MINS
done
if [ "$SUP_START_MINS" -lt 30 ]; then
  : # 启动宽限期内，跳过 S2
elif [ "$HB_AGE" -gt 12 ]; then
  STATE="AUTO_HEAL"; ACTION="S2 heartbeat stale ${HB_AGE}min"
fi
```

### 缺陷 3：看门狗 HEALED 输出误导（可见性问题）

`diagnose.log` 显示 `HEALED [S1 supervisor down] pids=[]` —— 实际上根本没 heal 成功（新 supervisor 启动后立刻被下一轮 S2 kill）。HEALED 状态判断只检查 `start_supervisor.sh` 的退出码，没验证新进程真的跑起来 + 进入主循环。

## 📌 次要问题（独立事件）

### 问题 A：WSL 频繁重启（Windows 侧触发）

journalctl 显示（10-10）10:37 到 13:06 之间 **WSL 重启了 10+ 次**（boot -9 到 boot 0），每次只活 23 秒到 45 分钟。关机日志是正常 systemd poweroff（`systemd-poweroff.service: Deactivated successfully`），说明是 Windows 侧 `wsl --shutdown` 或 VM 回收触发。

**根因猜测**：可能与 Windows 睡眠/休眠、AQE 扫 WSL 文件触发 9P 锁、或 Hyper-V 内存压力有关。需查 Windows Event Log（System → Kernel-Power / Hyper-V-VMMS）定位。

### 问题 B：supervisor.lock 文件本身不是问题（之前误判）

`supervisor.lock` 0 字节 + mtime 10-07 22:52 看似 stale，但 **flock 是进程级锁**，持有者进程退出后自动释放，新进程 `open()` 复用 inode 立即可拿。之前观察到的 `lock_contention` 是真的有另一个 supervisor 进程在跑（PID 不同），不是文件 stale 阻塞。

## ✅ 修复建议（按优先级）

| # | 修复 | 复杂度 | 影响 |
|---|---|---|---|
| **P0** | `ensure_baselines` 内每 symbol 完成后写 heartbeat | 低 | 根治死循环 |
| **P0** | 看门狗 S2 加 30 分钟启动宽限期 | 低 | 双保险 |
| **P1** | HEALED 状态要验证新进程真的进入主循环（检查 heartbeat 更新时间 ≥ 启动时间） | 中 | 防误报 |
| **P1** | 看门狗触发 kill 前检查 PID 启动时长（同上宽限期） | 低 | 防乱杀 |
| **P2** | 排查 Windows 侧 WSL 频繁重启根因（Event Log + 内存压力） | 中 | 避免事件 A 再现 |
| **P2** | supervisor 主循环内 heartbeat 频率从"每轮迭代"改为"每 N 秒"（独立线程） | 中 | 彻底解决长操作阻塞心跳 |

## 📊 关键数字

| 项 | 值 |
|---|---|
| 事件窗口 | 40 小时（10-08 21:15 → 10-10 13:15） |
| supervisor 实例数 | ~18 个（每 30 分钟一个） |
| 每个实例 uptime | 1189-1829 秒（19-30 分钟） |
| 卡死位置 | `ensure_baselines()` → jd 基线重生（589 点 × 2.5s = 25min） |
| 看门狗误杀次数 | ≥15 次（每 30 分钟一轮） |
| 有效工作时间 | **0 秒**（从未进入主循环） |
| 浪费 token/计算 | 18 × 25min × CPU 270% ≈ **120 CPU-hour** |

## 时间线

| 时间 | 事件 |
|---|---|
| 10-08 21:15 | supervisor PID 271176 干净退出（uptime 10h） |
| 10-08 21:36 | 看门狗拉起 PID 303406 → 卡 ensure_baselines → 22:07 被杀 |
| 10-08 21:36-21:40 | 5 个 supervisor 实例连续 lock_contention（互相顶） |
| 10-08 22:07 | PID 303494 被杀 → WSL 进入"稳定"期（实际是没 supervisor 在跑） |
| 10-09 23:19 | 看门狗再次触发 → 又 6 个实例循环 |
| 10-10 01:58 | PID 572 被杀，heartbeat 停在 `2026-10-10T01:58:22` |
| 10-10 10:37-13:06 | WSL 重启 10+ 次（boot -9 → boot 0） |
| 10-10 12:22 | 用户手动介入，拉起 PID 447 |
| 10-10 12:22-13:08 | PID 447 同样卡 ensure_baselines，被看门狗 S2 误杀 3 次（diagnose.log: `HEALED [S2 heartbeat stale 631min/646min/661min] pids=[447]`） |
| 10-10 13:08 | 看门狗拉起 PID 507（jd 重生到 3/589） |
| 10-10 13:15 | 用户 kill PID 507 + 完成本报告初版 |
| 10-11 — | 修订版落档至当前路径 |

## 相关文件

| 文件 | 用途 |
|---|---|
| `scripts/praxist_supervisor.py:4338-4348` | 缺陷 1 位置（ensure_baselines 在主循环外） |
| `scripts/diagnose_three_loop.sh:210-214` | 缺陷 2 位置（S2 判定无宽限期） |
| `data/cache/supervisor_events.jsonl` | 事件流水（关键证据） |
| `data/cache/diagnose.log` | 看门狗动作日志 |
| `data/cache/supervisor_heartbeat` | 心跳文件（mtime 停在 01:58） |
| `data/cache/supervisor.out` | supervisor stdout（基线重生进度） |

## 教训

1. **长操作必须有心跳**：任何 >1 分钟的启动预检都应该写心跳，否则看门狗会误判。
2. **看门狗必须有启动宽限期**：不能仅凭心跳年龄判定 stale，要看 PID 启动时长。
3. **HEALED 状态要验活**：启动脚本成功 ≠ 进程真的健康，要检查后续心跳是否更新。
4. **WSL 重启会放大问题**：本来 40 小时停机是 supervisor 侧问题，但 WSL 频繁重启让诊断更混乱（cron 跟着重启，日志不连续）。

---

**下一步**：实施 P0 修复（ensure_baselines 心跳 + 看门狗宽限期），验证后重启 supervisor，观察 2-3 小时确认进入稳定 cycle。
