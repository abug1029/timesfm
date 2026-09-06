# PRAXIST 三环运维手册

> 宿主硬件与容量结论见 [`host_environment_assessment.md`](./host_environment_assessment.md)。勿沿用旧 `/root/timesFM_fu`、Windows `D:/FlyBuddy` 或 1.9GB RAM 假设。

监督环（0 token）按 `scripts/praxist_goal.yaml` 编排快环（praxist）与慢环（aligned）。三环以 append-only 文件为总线。

| 项 | 值 |
|----|-----|
| 项目根 | `/workspace/repos/timesfm-abug1029`（FM_a / PRAXIST；预测岗 timesFM_fu 另路径） |
| Python | `.venv/bin/python` |
| praxist | `/home/box/.praxist-venv/bin/praxist`（下文 `praxist`；`PRAXIST_BIN` 可覆盖；回退 repo `.praxist-venv`） |
| Goal | `scripts/praxist_goal.yaml` |
| 监督状态 | `data/cache/supervisor_state.json` |
| 监督锁 | `data/cache/supervisor.lock` |
| 决策日志 | `.omc/supervisor_decisions.jsonl` |
| Known verdicts | `task_FM/known_verdicts.inc.md`（`prompt_base.jinja2` `{% include %}`） |
| Verdict 注册表 | `task_FM/config/aligned_verdicts.jsonl`（仅慢环可写） |

**TimesFM 权重 / RAM：** 预测岗用自己的权重；PRAXIST 用本仓 `models/timesfm-2.5-200m-pytorch/`（`TIMESFM_MODEL_PATH` / `.env.praxist`）。**15GB RAM / 无 GPU：磁盘可并存独立权重。旧「评估必须串行 / 禁止与预测岗同时常驻第二份」红线已于 2026-09-04（约 09:23 CST）解除（容量试跑阶段）——并行 peer eval / 多份 TimesFM 共载 OK，同时计量 RSS/OOM；多副本仍可能 OOM。** 详见 `models/README_TIMESFM.md` 与 `docs/host_environment_assessment.md` §3。


**内存硬顶（2026-09-04 总管 retune）：** 不以紧 `RLIMIT_AS` 为主（TimesFM safetensors mmap 冲突）。主路径：① 全局 flock ≤**2** + `MemAvailable < 2GiB` 拒启；② RSS shed（单进程 RSS>~3.5GiB 或 avail<2GiB → TERM，日志 `data/cache/capacity_actions.log`）；③ cgroup 时优先 `memory.max`/`memory.high`。强制挂钩：`scripts/praxist_mem_guard_hook.py` patch `protected_pids.launch_command`（`.pth` 安装见 `scripts/install_praxist_mem_guard_hook.py`），peer Bash/batch_runner/fm_eval 不靠 prompt。§4b 证据：N=4 ≈**8.53 GiB** 不可持续；N=2 舒适。e2e round complete（fast+harvest+slow）。详见 `docs/host_environment_assessment.md` Hard caps。

**cycle 定义：** 一次已结束的 praxist run + harvest +（若有幸存者）慢环抽干队列。`harvest_empty` 也计 1 cycle。`phase=slow` 时禁止 `start` 下一轮快环。`phase` 见 `data/cache/supervisor_state.json`，取值 `{fast, slow, wait_quota}`。**不是** 300s poll tick。

---

## 启动 / 停止

```bash
cd /workspace/repos/timesfm-abug1029

# 启动监督环（后台）
nohup .venv/bin/python scripts/praxist_supervisor.py \
  > data/cache/supervisor.out 2>&1 &

# 干跑：一轮打印 action JSON 后立即退出
# 不 sleep、不起 praxist/慢环、不写队列、不加 cycle、不 materialize known_verdicts
.venv/bin/python scripts/praxist_supervisor.py --dry-run

# 单步：允许真启进程 / harvest / 启慢环，仍不 sleep，一轮后退出
.venv/bin/python scripts/praxist_supervisor.py --once

# 停止监督环
kill <supervisor_pid>
# flock 在进程死后释放；慢环 inprogress 由下次慢环启动时 queue_recover 回收
```

停机报告：`goal_reached` / `budget_exhausted` 写入 `docs/superpowers/reports/supervisor_<kind>_<ts>.md`，并追加 `STATE.md`。

---

## 快环（praxist）

```bash
# 手动启动（监督环内部同样用 --daemonize --json）
ANTHROPIC_API_KEY=${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY} \
  praxist start --task-path task_FM --daemonize --json

# 状态 / 停止
praxist status --json
praxist stop <run_id>
```

### 429 配额

监督环读最近 run 日志中的 `reset at YYYY-MM-DD HH:MM:SS ±ZZZZ`：

1. **封禁期**（`now < reset`）且有活 run（`state in {running,starting}`）→ `praxist stop <run_id>`，记 `paused_429=true`（action: `run_paused_429`）。
2. **解封且当前配额窗剩余 ≥ run_budget_hours + quota_margin_min** →  
   `praxist resume <run_dir_or_run_id> --daemonize --json`（**positional** target，不是 `--run-dir`）。
3. 窗剩余不足 → `wait_quota`，sleep 到下一窗起点（`reset + N * quota_window_hours`）。
4. **禁止** 429 后对同一中断 run `praxist start` 新 run；须 resume 同一 `last_run_dir` / `last_run_id`。

`paused_429` 期间不 harvest、不 start。仅在 stop/resume 的 praxist 调用成功时才改该标志。

---

## 慢环（aligned）

| 路径 | 说明 |
|------|------|
| `data/cache/aligned_pending.jsonl` | 待评估队列 |
| `data/cache/aligned_pending.inprogress.jsonl` | claim 后进行中 |
| `data/cache/aligned_pending.done.jsonl` | ack 完成 |
| `data/cache/aligned_checkpoints/<variant_id>.jsonl` | 断点 |
| `data/cache/aligned_slow_loop.lock` | 单实例 flock |
| `data/cache/slow_loop.out` | 监督环拉起时的 stdout |

```bash
# 手动单候选（启动时先 queue_recover，再 claim → 评估 → ack）
.venv/bin/python scripts/aligned_slow_loop.py --once

# 清空队列前持续跑
.venv/bin/python scripts/aligned_slow_loop.py

# 监控
tail -f data/cache/slow_loop.out
```

### claim / inprogress / recover（0 损失）

1. **recover**：进程启动把 `inprogress` 前置回 `pending`。
2. **claim**：队首写入 `inprogress` 后再从 `pending` 移除。
3. **ack**：先 append `done`，再清 `inprogress`，并写 verdict（`status=ok` 终裁；`status=no_data` 可重试，不进 `dead_variants`）。
4. 评估异常：不 ack、不写死亡 verdict；下次启动 recover 重试；checkpoint 续跑。

kill 慢环后重启即可续跑。`variant_id = {symbol}_{cov_override}`；`max_points` 来自 goal `cadence.aligned_max_points`（默认 400）。

监督环在 harvest 入队后立刻 `Popen aligned_slow_loop.py`（**不看 clock window**）。完成条件：pending 与 inprogress 皆空，且 `aligned_slow_loop.lock` 可抢。慢环崩溃时 `phase` 保持 `slow`，下一 tick 再拉起；`queue_recover` 仍由慢环自己做。429 等待期间若 `phase=slow`，慢环继续；抽干后若仍封禁则 `phase=wait_quota`。

---

## Harvest 与 Known verdicts

- 监督环在活 run 结束且非 `paused_429` 时 harvest：扫描 `task_FM/experiments/run_*/results/**/evaluation_summary.json`。
- 幸存者：`status=ok` + `stage=diagnostic` + `ev>0`，且不在 dead / in_flight / 已过门集合；入队 top_k（`survivors_per_cycle`，默认 2）。
- 0 份 summary → 决策日志 `harvest_empty`（仍计 1 cycle，不进 slow）。有幸存者则 `phase=slow`，cycle 等到慢环抽干再 +1。
- 非 dry-run 每轮会 `materialize_known_verdicts` → 覆盖写 `task_FM/known_verdicts.inc.md`。
- `prompt_base.jinja2`：`{% include 'known_verdicts.inc.md' ignore missing %}`；渲染结果含 `variant_id` 与 `gate_pass=`。
- **红线：** 只有 `aligned_slow_loop.py` 可写 `aligned_verdicts.jsonl`。

---

## 验收演练清单

### 文档/单测可本地完成

1. **`--dry-run`**：输出含 `goal_reached` 或 `budget_exhausted`（若已达）、`harvest_plan`，以及 `wait_quota` / `run_started` / `run_paused_429` / `run_resumed` 之一；立即退出，无 sleep、无新进程、无 cycle 增量。
2. **假 429**：在某 `task_FM/experiments/run_*/logs/*.log` 注入含未来 `reset at ...` 的行 → `quota_gate` False；有活 run 时 `decide_fast_loop` 给出 `run_paused_429`（argv: `stop <run_id>`）。
3. **inprogress 恢复**：向 `aligned_pending.inprogress.jsonl` 写一行合法候选，跑 `aligned_slow_loop.py --once` → recover 后产出 verdict（或 checkpoint 续跑）。
4. **cycle 计数**：在 `--once` 循环下，`max_cycles` 不会因 300s tick 耗尽；`cycles_done` 仅在「已完成 run 被 harvest」后 +1。

### 执行期验收（operator-time，对照 spec §11 + 计划「Spec 绑定解释」）

> 下列步骤需真实 API/配额与长跑，**不在 Task 7 文档交付内自动执行**；由操作员择窗完成并勾选。

- [ ] **完整 cycle：** 小 goal（如 1 个过门 variant）→ supervisor 起 run → 结束后 harvest 入队 → 慢环写 verdict → 下次 start 前 `known_verdicts.inc.md` 被 include 进 peer 提示（含 `variant_id` 与 `gate_pass=`）。
- [ ] **缓存 A/B：** daily 预测缓存逐位一致（Task 1 慢测已覆盖；回归时按需重跑 `@pytest.mark.slow`）。
- [ ] **任意时刻 kill：** 分别 kill 慢环 / 快环 / 监督环后重启，无队列丢失、快环可 resume、监督环 state 续跑。
- [ ] **429 注入演练：** 模拟配额耗尽 → stop → 等到 reset 且窗足够 → `resume <run_dir_or_run_id> --daemonize --json`，不 start 新 run。
- [ ] **DSL 安全：** goal 注入攻击被拒绝（Task 4 单测已覆盖）。

---

## 故障速查

| 现象 | 排查 |
|------|------|
| `another supervisor holds the lock` | 已有实例；查 `supervisor.lock` / 进程 |
| `another slow loop instance holds the lock` | 同上，慢环锁 |
| harvest 空但 run 已结束 | 缺 `evaluation_summary.json` 或 ev≤0 / 非 diagnostic；看 `harvest_empty` |
| 429 后开了新 run | 违规；应 resume `last_run_dir`；查 `paused_429` |
| token 预算误停 | `tok_unknown` 时跳过 token 预算；确认 generation_results 是否有 `runtime_usage` |
| peers 看不到 verdict | 查 `known_verdicts.inc.md` 是否被 materialize；模板 include 是否在 `prompt_base.jinja2` |
| `no_data` 永久死 | 不应进 `dead_variants`；可重试入队 |

## 相关文件

- `scripts/praxist_supervisor.py` — 监督环
- `scripts/aligned_slow_loop.py` — 慢环
- `scripts/mem_guard.py` — 全局 flock≤2 + MemAvailable 门 + RSS shed（RLIMIT_AS 默认 OFF）
- `scripts/praxist_mem_guard_hook.py` / `install_praxist_mem_guard_hook.py` — protected_pids 强制挂钩
- `scripts/registry_lib.py` — 队列 / verdict / snapshot
- `scripts/goal_dsl.py` — success_condition 求值
- `docs/superpowers/plans/2026-09-02-praxist-three-loop.md` — 实施计划（Spec 绑定解释优先于过时 spec 句）
- `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` — §11 验收标准
`)