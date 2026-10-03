# supervisor 重启待办

> 登记日期: 2026-09-17。**不重启运行中的 supervisor**；第 1、3 项已实施/完成（见处置记录），仅剩第 2 项登记待议。

## 1. 菜单 track 行固定前缀「【旧口径线索·非证据】」

- 位置: `scripts/praxist_supervisor.py:745` 附近，`materialize_covariate_menu` 渲染 track 行处：
  `tr = " [track: %s]" % v["track_record"] ...`
- 做法: 给菜单 track 行加固定前缀「【旧口径线索·非证据】」（防御性，防止 pool 未来再写入裸数字时被当作证据）。
- 背景: pool 源头已在 2026-09-17 去数字（covariate_pool 内 10 条 v22 旧口径 track_record 标注，见 git log）。

## 2. IDLE_HOLD 守卫等价物

- 背景: 原 `scripts/start_praxist.sh`（已归档至 `docs/archive/batch/`）启动前检查 `docs/superpowers/reports/praxist_20260907_ctrl/IDLE_HOLD` 文件，存在即拒绝启动（exit 78），作为启动守卫。
- 现状: 脚本归档后该守卫失去入口，当前无引用。
- 做法: 如需该功能，应在 supervisor 侧补等价实现（启动周期检查 IDLE_HOLD 标记文件，存在则拒绝启快环）。当前仅为登记，无实施计划。

## 3. ~~加载 2026-09-29 的 4 个 commit~~ —— **已完成 2026-09-29，PID 670**

- 背景: supervisor PID 22703 于 2026-09-28 18:54 启动，其内存里是当天的代码；
  磁盘上 4 个 commit 未加载 → 监督环派生慢环子进程会跑新代码，而 verdict 仍按旧 schema
  记账，即「新代码语义 + 旧 schema 记账」的混版本窗口。
- 处置: 旧进程 22703 干净退出（`supervisor_stopped{reason: signal_received, exit_code: 0}`，
  uptime 88725s）→ 新进程 **PID 670** 启动。
- **新代码已加载的端到端证据**（不只是「进程起来了」）:

  ```
  磁盘现算:  protocol_v3  fingerprint = 91ab913e448aead6f4c81f55
  启动日志:  [WARN] ensure_baselines: cj 基线协议指纹不符
                    (bd851c9ca0730dc5… != 91ab913e448aead6…) → 重生（跨协议不可比）
  ```

  `91ab913e448aead6` 是新代码算出的 v3 指纹，cj 旧基线带的是 v2 的 `bd851c9c`。
  指纹 bump → 跨协议不可比被识别 → 强制重生。H1/Q2 的机制在生产里跑通。
  ~~只有 cj 需重生，其余 7 个基线本就兼容。~~（**勘误 2026-09-29**：与日志不符——9 个 nocov 基线全部带 v2 指纹、全部按上述指纹 bump 机制重生，非仅 cj；本行为重启当时采样过早所致。）
- K6 / M4 的验收断言在**周期末尾**物化后核对（`materialize_known_verdicts` 在周期末执行）:

  | 断言 | 期望 | 修复前 |
  |---|---|---|
  | `grep -c "v1 legacy: pass by ev>0" task_FM/known_verdicts.inc.md` | 1（K6 图例去重） | 2 |
  | `grep -c "gate_pass=True" task_FM/known_verdicts.inc.md` | 43（M4 截断只切尾部） | 23 |

  M4 修复前，活仓 42 条 `gate_pass` 里只有 20 条进了 peer 提示词 —— 被静默吞掉的
  22 条正是「已解出、不要再提」的集合，直接违反该文件自己的表头契约。

- **验收结果（2026-09-29 晚，PID 670 首个周期末物化后核对，三项全过）**：
  - K6 过：`grep -c "v1 legacy: pass by ev>0" task_FM/known_verdicts.inc.md` = 1（图例单条）
  - M4 过（语义断言「gate_pass 行全部在场、截断只切尾部」）：`grep -c "^- .*gate_pass=True"` = 43 == 注册表 `gate_pass` = 43（rows=173；慢环后续追加的均为非过门行）
  - M4 过：`verdicts_truncated=` 标记存在（`verdicts_truncated=91`，被截断全为 DEAD 尾行）
  - 计数口径注意：文件头部两条图例行（v2 pass / hard-gate-but-losing 说明）本身含 `gate_pass=True` 字样，
    裸 `grep -c "gate_pass=True"` = 45 = 43 条 verdict 行 + 2 条图例行；上表「期望 43」若按裸 grep 口径会差这 2 条，
    语义以「verdict 行数 == 注册表 gate_pass 数」为准。

### 停止监督环的正确做法（本文档此前写错，已更正）

**`scripts/stop_supervisor.sh` 不存在**，日志也不在 `logs/supervisor.log`。实测流程:

```bash
kill -TERM <supervisor_pid>          # 只置标志，主循环最迟下个 tick（≤300s）退出
# 等 data/cache/supervisor.out 出现:
#   supervisor_stopped{reason: signal_received, exit_code: 0}
setsid nohup python scripts/praxist_supervisor.py --goal scripts/praxist_goal.yaml   >> data/cache/supervisor.out 2>&1 < /dev/null &
```

日志真路径 = **`data/cache/supervisor.out`**。`logs/` 下只有手工归档的快照。

**孤儿 run 必须单独停**（2026-09-29 实测，本文 §故障 8 口径）：run 由
`subprocess.Popen(..., start_new_session=True)` 派发，`pgrep -P <supervisor_pid>` **查不到**，
必须 `pgrep -f "praxist.run run --task-path"` 单查、单 kill。停机顺序：先 supervisor（等干净退出），
再 run（实测 ~5s 退出）。

**启动器是唯一权威入口**：用 `scripts/start_supervisor.sh`，不要裸 `setsid`（会丢
`$HOME/.local/bin` PATH 前置，peer `claude` 会解析到 Windows shim → exit 126）。
launcher 内部已做 `setsid nohup` 孤儿化；验证会话独立性看 `ps -o pid,ppid,sid,tty`——
`SID` 应与调用方不同、`PPID` 应为 `/init`、`TTY` 为 `?`。

**⚠ 已知缺陷：SIGTERM 停机不可靠（2026-10-02 首现，2026-10-03 修订为结构性根因）**

症状：发送 `SIGTERM` 后 supervisor 长时间不退出，且期间继续收割、继续发起快环。

- 2026-10-02 实测：第一次 SIGTERM 后 180s 内继续收割 + 发起新 run，第二次才生效（约 35s）。
- 2026-10-03 实测（更严重）：**两次 SIGTERM 均被忽略**，累计等待 180s + 120s 后仍在运行
  （14:16:05 还发起新 run），最终需 `SIGKILL` 强制停止；停机事件由 atexit 兜底补发，
  `stop_report.json` 未刷新（仍为 10-02 PID 418）。

**根因（结构性，非「信号丢了一次」）**：`_signal_handler`（`praxist_supervisor.py:361`）按设计只置
`_SHUTDOWN_REQUESTED = True`（无 I/O，做法正确）；但该标志**只在主循环顶被读**
（`:2858`，紧跟 `_write_heartbeat()`）。主循环内存在多处**无超时阻塞调用**
（如 `_maybe_finish_slow` 等慢环子进程退出、`rl.queue_*` / `_harvest_rows` 的文件锁与全量扫描），
信号一旦落在这些调用中间，标志在阻塞解除前读不到。叠加 `POLL_S = 300`（`:117`），
最坏情况要再等一整轮 poll。

**因此「发两次 SIGTERM」不是可靠口径**——2026-10-03 第二次同样无效，白等 120s。

**修复前操作口径**：

```bash
kill -TERM "$SUP"; sleep 60
kill -0 "$SUP" 2>/dev/null && kill -KILL "$SUP"      # 直接强杀，不再等第二轮 SIGTERM
```

注意：SIGKILL 路径下 `stop_report.json` **不会刷新**，判据只能看
`data/cache/supervisor_events.jsonl` 的 `supervisor_stopped`（可能由 atexit 兜底补发）。

**修法方向**：`docs/superpowers/plans/2026-10-03-three-loop-open-closure.md` Task 7
（睡眠改 1s 切片 + 开新工作前查标志）能缓解，但**覆盖不到「卡在 `_maybe_finish_slow`
之类阻塞调用」的情形**——需补：阻塞调用加超时返回，或停机标志改走独立线程 / 自管道唤醒，
使循环顶检查不被长阻塞推迟。

## 处置记录

- 2026-09-17: 显式重启时实施第 1 项 —— praxist_supervisor.py:749 track 行已加固定前缀「【旧口径线索·非证据】」（test_supervisor/test_covariate_pool 47 passed）。第 2 项维持登记：本次以启动前人工检查 IDLE_HOLD（不存在，放行）履行守卫职责。
- 2026-09-17: supervisor 已重启（PID 546，setsid 脱离进程树，日志 data/cache/supervisor_loop.out）。
- 2026-09-29: 第 3 项完成（旧进程 22703 退出 → PID 670 加载新代码，v3 指纹端到端验证）；本节原有的
  `scripts/stop_supervisor.sh` / `logs/supervisor.log` 两个路径经核实**均不存在**，已按实测改写。
- 2026-10-01: **v4 收口重启**（计划任务 2.9）。readiness check 6/6 通过 → PID 418（11:09）。
  v4 指纹 `f02b2a43…` 上线；`ensure_baselines` 重生波 9/9 全带 v4 落章（fu 为入集后首个基线）。
  中途 WSL VM 回收击杀 PID 393（eg 重生 201/589 处，无 traceback）→ 重跑 launcher幂等续跑，
  **重生波可恢复性获生产实证**（波恢复后 cj 持久化跳过）。
- 2026-10-02: **阶段 3 接线后重启**（PID 418 → **PID 416**，20:27）。停机：第一次 SIGTERM 被忽略
  （见上方已知缺陷），第二次生效，19:05:40 干净退出 `exit_code 0` / uptime 114,956.8s。
  启动：清理 4 个残留锁文件 → 轮转 `supervisor.out`（1,498 行 → `supervisor_pre_restart_20261002_202719.out`）
  → `scripts/start_supervisor.sh`。**重启后首轮收割即入队 3 行**（修复前连续 9 轮 0 入队），
  证实对方 `045c7e2` 的「收割/复测只看当前协议」修掉了收割枯竭；入队率回到 100%，
  裁决产出 0.72→1.62 条/h。运行成果见
  `docs/superpowers/reports/2026-10-03-three-loop-v4-operations-report.md`。
- 2026-10-01: **v4 收口重启**（计划任务 2.9）。readiness check 6/6 通过 → PID 418（11:09）。
  v4 指纹 `f02b2a43…` 上线；`ensure_baselines` 重生波 9/9 全带 v4 落章（fu 为入集后首个基线）。
  中途 WSL VM 回收击杀 PID 393（eg 重生 201/589 处，无 traceback）→ 重跑 launcher幂等续跑，
  **重生波可恢复性获生产实证**（波恢复后 cj 持久化跳过）。
- 2026-10-03: **计划性停机**（配合文档治理）。SIGTERM 两次均被忽略（180s+120s 内持续产出）→ `SIGKILL` 强制停止；停机事件由 atexit 兜底补发（`exit_code 0` / uptime 64,790s），`stop_report.json` 未刷新（仍为 10-02 PID 418）。孤儿 run 178344 单独 SIGTERM ~5s 干净退出。停机前计数：registry 238（v4 50 · gate_pass 16 · tier S7/A7/B25/C11）· cycles 205 · phase fast。上方操作口径即据本次实测修订。

