# 三环停机事件报告：SIGTERM 不可靠的根因定位
> **代码基线**: `ccdfea6`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

- **报告日期**：2026-10-03
- **事件时间**：2026-10-03 14:11 发起停机，14:27 强制停止，历时约 16 分钟
- **对象**：supervisor PID 416（2026-10-02 20:27 启动，存活约 18h）+ 孤儿 run PID 178344
- **关联**：
  - 重启档案与操作口径 `docs/supervisor_restart_backlog.md`（同批修订）
  - 未决问题清单 `docs/superpowers/reports/2026-10-03-fm-a-open-issues.md` §5.2
  - 收口计划 `docs/superpowers/plans/2026-10-03-three-loop-open-closure.md` Task 7
  - 运行成果 `docs/superpowers/reports/2026-10-03-three-loop-v4-operations-report.md`

---

## 一、结论先行

**`SIGTERM` 在当前 supervisor 实现下不可靠**：本轮两次 `SIGTERM`（累计等待 180s + 120s）**均被忽略**，
期间持续收割并发起新快环，最终必须 `SIGKILL` 强制停止。

**根因是结构性的，不是"信号丢了一次"**：停机标志只在主循环顶被读，而主循环内存在多处**无超时阻塞调用**，
信号落在阻塞中间就读不到。**因此"发两次 SIGTERM"不是可靠口径**（本轮第二次同样无效，白等 120s）。

---

## 二、事件时间线

| 时刻 | 事件 |
|---|---|
| 14:11 | 停机前清单：PID 416（supervisor，18h）+ PID 178344（run，在跑） |
| ~14:12 | 第一次 `SIGTERM` → PID 416 |
| 14:12–14:15 | 等待 180s：**未退出** |
| 14:15 | 第二次 `SIGTERM` → PID 416 |
| **14:16:05** | **supervisor 仍发起新 run**（`events` 末条 `run_started`）——信号完全未被消费 |
| 14:16–14:17 | 再等 120s：**仍未退出** |
| ~14:17 | 单独 `SIGTERM` 孤儿 run 178344 → **~5s 干净退出** ✅ |
| — | 慢环无进程 |
| 14:27:13 | `SIGKILL` supervisor → **~5s 强制停止** |
| 14:27:13 | `events` 出现 `supervisor_stopped{reason: signal_received, exit_code: 0, uptime_s: 64789.8}` |
| 复查 | ✅ 三环全部进程已停，无残留 |

**注意**：`supervisor_stopped` 事件虽为 `exit_code 0` / `reason: signal_received`，
但系**SIGKILL 后由 atexit 兜底补发**（信号语义已丢）；`stop_report.json` **未刷新**
（仍是 2026-10-02 PID 418 的记录），可作为「非正常路径退出」的旁证。

---

## 三、根因定位

### 3.1 信号处理本身是对的

```python
# scripts/praxist_supervisor.py:361
def _signal_handler(signum, frame):
    """Signal handler: set flag only, no I/O. Main loop detects and emits event."""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
```

只置标志、不做 I/O —— 符合 spec 与最佳实践，**不是本次问题所在**。

### 3.2 标志的唯一读取点是循环顶

```python
# scripts/praxist_supervisor.py:2856
while True:
    _write_heartbeat()
    if _SHUTDOWN_REQUESTED:
        _emit_event("critical", "supervisor_stopped", {...})
        return 0
```

检查紧跟心跳，位于循环最前 —— 设计正确，但**读取时机完全由主循环的控制流决定**。

### 3.3 主循环内存在无超时阻塞调用

阻塞点（部分）：

| 位置 | 阻塞性质 | 最坏时长 |
|---|---|---|
| `_maybe_finish_slow` | 等慢环子进程退出（慢环单变体 600 点评估 ~10–20 min） | 十几分钟 |
| `_maybe_start_slow_loop` / `_queue_busy` / `_slow_loop_alive` | 子进程探测与等待 | 秒~分钟 |
| `rl.queue_enqueue` / `queue_claim` | 文件锁 + 追加写 | 秒级 |
| `_harvest_rows` | 遍历全部 run 目录的提案文件（当前 3,592 份）+ 逐条走门链 | 数十秒~分钟 |
| 循环末尾 `time.sleep(POLL_S=300)` | 一次性睡眠，标志在下一次切片才可见 | ≤300s |

信号若落在上述任一阻塞中间，**标志在阻塞解除前读不到**；再叠加 300s 轮询周期，
最坏要等一整轮 poll 才能退出。

### 3.4 与前次（10-02）现象的关系

10-02 记录为「第一次被忽略、第二次生效」，当时归因为「一次性 300s 睡眠 + 信号落在循环顶检查之后」。
本轮证明该归因**不完整**：第二次同样无效，说明问题不止于睡眠切片，而是**任何长阻塞都能吃掉信号**。

---

## 四、影响评估

| 维度 | 影响 |
|---|---|
| 数据完整性 | 低风险。裁决 / 队列 / family 登记均为 append-only 或带校验和；SIGKILL 只丢最后一个 in-flight 循环的状态落盘 |
| 停机可预期性 | **差**。操作者无法预判需要几次信号、等多久，必须准备强杀 |
| 事件可信度 | `supervisor_stopped` 可由 atexit 兜底补发，**单看该事件不能证明是干净停机**；须结合 `stop_report.json` 是否刷新、uptime 是否与启动时刻吻合 |
| 自动化运维 | 不适合需要确定性停机的编排（如「停机→立即重启加载新代码」） |

**本轮实际损失**：无。（停机前计数已记录：registry 238 / v4 50 / gate_pass 16 / cycles 205 / phase fast）

---

## 五、修复方向

### 5.1 短期（操作口径，已写入 backlog）

```bash
kill -TERM "$SUP"; sleep 60
kill -0 "$SUP" 2>/dev/null && kill -KILL "$SUP"      # 直接强杀，不再等第二轮
```

判据：强杀路径下 `stop_report.json` 不刷新，**不能只看 `supervisor_stopped` 事件**。

### 5.2 中期（收口计划 Task 7 能覆盖的部分）

- 睡眠改 1s 切片（`_sleep_interruptible`）→ 覆盖「信号落在 300s 睡眠中」
- 开新工作前（收割 / 复测入队 / 确认入队 / `decide_fast_loop` 之前）查标志 → 覆盖「信号落在循环顶检查之后」
- 干净退出统一走 `_shutdown_exit()`，并**必须配套 `_mark_stop_emitted()`**（否则 atexit 会重复上报）

### 5.3 Task 7 未覆盖、需补的部分

**Task 7 只改睡眠与开关检查，对「卡在 `_maybe_finish_slow` 等阻塞调用」无效**。需要至少一项：

1. 给阻塞调用加超时返回（如 `_maybe_finish_slow` 改为带 deadline 的等待）；
2. 或让停机标志不依赖主循环控制流——独立线程监听事件 / `signal.set_wakeup_fd` 自管道唤醒，
   使循环顶检查不被长阻塞推迟；
3. 或为关键阻塞段（等子进程）安装临时信号处理器直接抛出并退出。

---

## 六、待办与归属

| 项 | 归属 | 状态 |
|---|---|---|
| backlog 已知缺陷条目改写为结构性根因 + 操作口径 | 本报告同批完成 | ✅ |
| Task 7 补「阻塞调用超时 / 信号唤醒」 | 收口计划作者（已反馈） | 待实施 |
| 停机事件可信度：`supervisor_stopped` 增加「是否 atexit 兜底」标记 | 未指派 | 待定 |
| 强杀后的状态完整性核对（本轮未做，评估为低风险） | 未指派 | 待定 |

---
*报告生成：2026-10-03 14:30（数据取至停机完成时刻）*