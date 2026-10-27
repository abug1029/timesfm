# PRAXIST 三环运维手册

> 宿主硬件与容量结论见 [`host_environment_assessment.md`](./host_environment_assessment.md)。**当前宿主 = WSL2 Ubuntu-22.04，项目根 `<FM_ROOT>`**；勿沿用旧 Grok 盒 `/workspace/repos/...`、`/home/box/...`、Windows `D:/FlyBuddy` 或 1.9GB/15GB RAM 假设。

> **路径口径**：本文用 `<FM_ROOT>` 表示仓库根（本机为 WSL 活仓；换机器/换用户后由脚本按自身位置推导，不要写死绝对路径）。

新人先读架构概览 [`praxist.md`](./praxist.md)。本文是运维手册：启停、429、队列、收割、复测、故障速查。

监督环（0 token）按 `scripts/praxist_goal.yaml` 编排快环（praxist）与慢环（aligned）。三环以 append-only 文件为总线。

| 项 | 值 |
|----|-----|
| 项目根 | `<FM_ROOT>`（WSL2 Ubuntu-22.04；FM_a / PRAXIST 同仓） |
| Python | `.venv/bin/python`（Python 3.11） |
| praxist | 本仓 `.venv/bin/praxist`（`PRAXIST_BIN` 可覆盖；supervisor 自动解析） |
| Goal | `scripts/praxist_goal.yaml` |
| 监督状态 | `data/cache/supervisor_state.json` |
| 监督锁 | `data/cache/supervisor.lock` |
| 决策日志 | `.omc/supervisor_decisions.jsonl` |
| Known verdicts | `task_FM/known_verdicts.inc.md`（Symbol status / Effective clues / Do not re-propose；`prompt_base.jinja2` `{% include %}`） |
| 品种探索状态 | `task_FM/config/symbol_status.json`（2026-09-28 清空 `symbols={}`，当前无 DEAD/HOLD；人手改 JSON，代码不自动复活） |
| 面板 topology | `task_FM/.praxist/plugins/panel_topologies/fm_two_peer/`（`cohort_size=2` → exploit+falsifier） |
| Verdict 注册表 | `task_FM/config/aligned_verdicts.jsonl`（仅慢环可写；新行含 `baseline_dir_acc`/`effective_min`） |

**TimesFM 权重 / RAM：** PRAXIST 用本仓 `models/timesfm-3.0-pytorch/`（`TIMESFM_MODEL_PATH` / `.env.praxist`）。**当前 WSL2 仅 7.7 GiB / 无 GPU / 无 swap**：方案 A（2026-09-08，peer 只写机制化提案、零 TimesFM 加载）后 peer 常驻 ~330MB，TimesFM 仅慢环单实例加载，N=2 舒适；旧盒（15GiB）"并行 peer eval 共载"结论在本机不适用。详见 `docs/host_environment_assessment.md` 顶部迁移表。


**内存硬顶（2026-09-04 总管 retune）：** 不以紧 `RLIMIT_AS` 为主（TimesFM safetensors mmap 冲突）。主路径：① 全局 flock ≤**2** + `MemAvailable < 2GiB` 拒启；② RSS shed（单进程 RSS>~3.5GiB 或 avail<2GiB → TERM，日志 `data/cache/capacity_actions.log`）；③ cgroup 时优先 `memory.max`/`memory.high`。强制挂钩：`scripts/praxist_mem_guard_hook.py` patch `protected_pids.launch_command`（`.pth` 安装见 `scripts/install_praxist_mem_guard_hook.py`），peer Bash/batch_runner/fm_eval 不靠 prompt。§4b 证据：N=4 ≈**8.53 GiB** 不可持续；N=2 舒适。e2e round complete（fast+harvest+slow）。详见 `docs/host_environment_assessment.md` Hard caps。

**cycle 定义：** 一次已结束的 praxist run + harvest +（若有幸存者）慢环抽干队列。`harvest_empty` 也计 1 cycle。`phase=slow` 时禁止 `start` 下一轮快环。`phase` 见 `data/cache/supervisor_state.json`，取值 `{fast, slow, wait_quota}`。**不是** 300s poll tick。

---

## 启动 / 停止

```bash
cd <FM_ROOT>

# 启动监督环（规范方式 = scripts/start_supervisor.sh，canonical launcher，2026-09-21 起）
# launcher 做三件事：
#   ① 幂等前置 PATH：保证 claude 解析到 WSL 原生 ~/.local/bin，而非 /mnt/c Windows npm shim
#      （否则 peer spawn `claude` → claude.exe → Exec format error → exit 126 → peer runtime_failure）
#   ② source .env.praxist 注入 LLM 环境
#   ③ setsid nohup 孤儿化 + sanity 检查 + 打印 PID
scripts/start_supervisor.sh

# 干跑：一轮打印 action JSON 后立即退出
# 不 sleep、不起 praxist/慢环、不写队列、不加 cycle、不 materialize known_verdicts
.venv/bin/python scripts/praxist_supervisor.py --dry-run

# 单步：允许真启进程 / harvest / 启慢环，仍不 sleep，一轮后退出
.venv/bin/python scripts/praxist_supervisor.py --once

# 优雅停止监督环：SIGTERM 只置标志，主循环最迟下一个 tick（≤300s sleep）退出
# 退出码 0，事件 reason=signal_received；慢环 start_new_session 是孤儿，继续跑完当前候选
kill -TERM <supervisor_pid>
# flock 在进程死后释放；慢环 inprogress 由下次慢环启动时 queue_recover 回收
```

停机报告：`goal_reached` / `budget_exhausted` 写入 `docs/superpowers/reports/supervisor_<kind>_<ts>.md`（不写 `STATE.md`，STATE.md 是 FM_a 月度回测状态的事实源）。

> **重启电脑/注销 WSL 前的有序停机**：先 `kill -TERM` 监督环（阻止排空后起新快环），让慢环孤儿把在跑候选自然跑完（checkpoint 逐点落盘，kill 也可续跑），确认零 praxist 进程后再关机。重启后用上面的规范启动命令即可：队列/state/checkpoint 全部可恢复，首 tick 自动 cycle+1 起新 run。

> **重启后验收（K6/M4，2026-09-28 起）**：待首个 cycle 物化后检查 `task_FM/known_verdicts.inc.md`：① `grep -c "v1 legacy: pass by ev>0"` = 1（图例单条，K6）；② 品种表 `gate_pass=True` 计数行正常出现；③ `verdicts_truncated=` 标记存在（M4）。三项齐 = 新代码物化生效；任一缺失 = 疑似旧进程仍在写（查 `ps aux | grep praxist_supervisor` 与 `data/cache/supervisor.out` mtime）。

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
4. **同提供商、同 model id**：禁止 429 后对同一中断 run `praxist start` 新 run；须 resume 同一 `last_run_dir` / `last_run_id`。
5. **model id 不同**（例：Ark `claude-opus-4-7` → DashScope `qwen3.7-plus`）：Praxist resume 拒改模型身份，**允许** 新 `run_dir`。已配置 failover 时走 `run_failover_llm`，不是只 `wait_quota`。

`paused_429` 期间：**仍** `harvest_proposals`（提案是本地文件，不烧 token）；不 start 同一提供商、同 model id 的新 run。仅在 stop/resume/failover 的 praxist 调用成功时才改该标志。

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

kill 慢环后重启即可续跑。`variant_id = {symbol}_{cov_override}`；`max_points` 来自 goal `cadence.aligned_max_points`（**当前 600**）。

### 队列清理（2026-10-27 新增）

当队列中混入无效提案（族名/未注册协变量/无数据品种）时，可用清理脚本安全移除：

```bash
# 1. 停止慢环（避免并发写冲突）
pkill -f aligned_slow_loop

# 2. 运行清理脚本（自动备份 + 文件锁 + 原子替换）
.venv/bin/python scripts/cleanup_invalid_queue.py

# 3. 验证结果
wc -l data/cache/aligned_pending.jsonl
ls -lh data/cache/aligned_pending.jsonl.bak.*

# 4. 重启慢环（如需要）
.venv/bin/python scripts/aligned_slow_loop.py --batch-id <batch_id>
```

**清理逻辑**：
- 族名（momentum, volatility 等）→ 移除
- 未注册协变量（不在 `covariate_pool.json` 的 active 列表）→ 移除
- 品种 `c`（玉米，无数据）→ 移除

**安全措施**：文件锁（`fcntl.flock`）、备份原文件、原子替换（先写 `.tmp` 再 `rename`）。

**相关脚本**：
- `scripts/enqueue_reprocess.py`：入队时验证协变量（P0-A）
- `scripts/cleanup_invalid_queue.py`：清理队列中的无效条目（P3）
- `cascade/features.py::UnsupportedCovariateError`：fail-fast 异常（P0-B）

监督环在 harvest 入队后立刻 `Popen aligned_slow_loop.py`（**不看 clock window**）。完成条件：pending 与 inprogress 皆空，且 `aligned_slow_loop.lock` 可抢。慢环崩溃时 `phase` 保持 `slow`，下一 tick 再拉起；`queue_recover` 仍由慢环自己做。429 等待期间若 `phase=slow`，慢环继续；抽干后若仍封禁则 `phase=wait_quota`。

---

## Harvest 与 Known verdicts（方案 A：机制化假设作者，2026-09-08 起）

- Peer **不跑评估**，只写机制优先的结构化提案：`task_FM/experiments/run_*/results/gen_*/<peer>/proposals/<symbol>_<cov>.json`（schema `fm.hypothesis_proposal.v1`，`mechanism` ≥40 字）。监督环在**活 run 已结束**时由 `harvest_proposals` 收割：`paused_429` / `wait_quota` / failover **不挡** harvest（提案是本地文件）。每 cycle 重扫全部 `run_*/results/**/proposals/*.json`，dead/passing/in-flight 去重。旧 `harvest_survivors`（读 `evaluation_summary.json`）仅留作回滚，不是现行源。
- **拒绝计数（fail visibly）**：`missing_symbol_or_cov` / `symbol_not_allowed` / `cov_archived` / `cov_not_in_active_pool` / `no_current_baseline`（该品种没有当前协议的 `baseline_points_{symbol}_nocov.jsonl`）/ `mechanism_too_short` / `no_failure_delta`（同 symbol 或同 cov 已失败且 delta 不足 20 字）/ `symbol_dead` / `symbol_hold` / `dedup`（dead / 已过门 / in-flight / 本批重复）/ `backlog_dup`。
- **新协变量想法** `new_cov_<name>.json`（`cov_override=null`）→ 追加 `task_FM/config/covariate_backlog.jsonl`（按 name 去重），**不入队**；宿主在 `features.py` 实现并入池后才可测。
- **选座（top_k = `survivors_per_cycle`，当前 3）**：先按 tier 排序再两遍 QD——
  1. tier 0：`cadence.priority_symbols` 中当前有效点 n≥350 者（2026-09-23 起 goal.yaml 未设该键 → tier 0 现为空）；
  2. tier 1：优先集中样本暂不足者（同样依赖 `priority_symbols`，当前亦为空）；
  3. tier 2：其余品种。
  同 tier 内按协变量履历分；第一遍每个 family 一席，第二遍按分补满。
- 0 份合格提案 → `harvest_empty`（仍计 1 cycle）。有入队则 `phase=slow`，cycle 等到慢环抽干再 +1。
- 每 tick（无论 phase）还跑 `_maybe_enqueue_retests`：对「硬门仅差 n」的近失误裁决（实现是 `scripts/sup_loops.py` 的 `_retest_candidates`；触发判据见 [runtime_contract.md](./runtime_contract.md)「复测触发判据（2026-10-08 裁定 C+a）」），当本地库有效点长到 ≥350 且比上次裁决多 ≥`retest_min_new_points` 点时，**旁路 dead 去重**补队（`source:"sample_retest"`），checkpoint resume 只算新点。dry-run 中以 `sample_retest_plan` 行展示。
- 菜单 `covariate_menu.inc.md` 每轮由协变量池 + **品种样本天花板表**（每品种当前可对齐有效点，`BELOW GATE`/`gate-reachable`，`_valid_n_for_symbol` 复刻月度回测有效点计数，fail-open）物化生成。
- 非 dry-run 每轮会 `scripts/sup_evidence.py` 的 `materialize_known_verdicts` → 覆盖写 `task_FM/known_verdicts.inc.md`（品种表不截断；Effective clues 从 snapshot 现场算过门族/近门/弱族；禁止再提案最多 80 条；`verdicts_truncated=<N>` 行标记被截断的裁决计数——2026-09-28 M4）。
- `prompt_base.jinja2`：先读证据再写提案；`{% include 'known_verdicts.inc.md' ignore missing %}` 与 `covariate_menu.inc.md`。**不要**再写「优先波动率族」。
- **红线：** 只有 `aligned_slow_loop.py` 可写 `aligned_verdicts.jsonl`。
- **TypeSafe Jev 预筛（2026-09-22，可选增强）：** harvest 每个合格提案 `_prescreen_async`（fire-and-forget daemon 线程）调 TypeSafe 三问，原子写 `<proposal>.prescreen.json`。`_proposal_priority_score` 读它做 ± 调度降权/奖励；**永远不阻断慢环回测**。缺 `TYPESAFE_API_KEY`、超时、降级时静默跳过（`skip_suggested=None`）。降权因异步滞后一轮收割生效。慢环读同一文件注入 `verdict.metadata.prescreen`。验证：`python scripts/validate_typesafe_prescreen.py`；质量门禁：`python scripts/track_prescreen_quality.py`。
- materializer 三态已区分 `v2_pass` / `hard-gate-but-losing` / 变体级 `DEAD`。过硬门但未过 FDR **不是** already solved。`dir_acc` 略低于 0.52 仍 `gate_pass=True` 是品种自适应门槛，不是 bug。

### 当前 goal（以 `scripts/praxist_goal.yaml` 为准）

成功条件（以 `scripts/praxist_goal.yaml` 为准）：只有 `all_symbols_pass_phase1`。一个品种达到「可预测」当且仅当至少有一条 family 封账的确认：`run_label` 为 confirmed 且 `fdr_pass` 为 True。原三阶段门槛和无界预算已经退役，本文件不再记录那些公式。目标品种 24 个：m/ss/sr/cj/jd/lh/eg/rb/i/p/y/cf/bu/fu/ta/ma/fg/ur/px/oi/sh/sp/ao/jm（2026-10-08 删 `sc`、增 `jm`，与候选准入门 `ALLOWED_SYMBOLS` 归一；该准入门由本 yaml 的 `target_symbols` 派生，改品种只改这里）。预算：`max_cycles`=2000，`cpu_hours`=2000，`token_budget_m`=null（不参与停机），`deadline`=2028-10-02。cadence：survivors=3、aligned_max_points=600、quota 窗 5h、run 预算 1.5h。`dir_acc` 主口径为剔零变动（spec W6.5①，PR-B4）；经济数值仅作报表参考，不参与裁决。已锁定的预注册样本量不在监督环里改写。jd 的确认样本仍是 1199，sr 的确认样本仍是 986，都写在 `task_FM/config/preregistry.jsonl`。Q7 备忘录要求重启后按 live 密度修订日历，并且每季按实测 Var_LR 复核 Δ_min；那是宿主动作，监督环不为此改预注册文件，也不改 Δ*=0.08。

---

## 验收演练清单

### 文档/单测可本地完成

1. **`--dry-run`**：输出含 `goal_reached` 或 `budget_exhausted`（若已达）、`harvest_plan`、`sample_retest_plan`（若有近失误可复测），以及 `wait_quota` / `run_started` / `run_paused_429` / `run_resumed` 之一；立即退出，无 sleep、无新进程、无 cycle 增量。
2. **假 429**：在某 `task_FM/experiments/run_*/logs/*.log` 注入含未来 `reset at ...` 的行 → `quota_gate` False；有活 run 时 `scripts/sup_loops.py` 的 `decide_fast_loop` 给出 `run_paused_429`（argv: `stop <run_id>`）。
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

## 无人值守运维（2026-10-08 实施计划批次 A/A2）

> **背景**：待解决问题 spec（`docs/superpowers/specs/2026-10-08-open-issues-closure-spec.md`）批次 A/A2 实施了四类运维守护机制，提升三环系统的无人值守安全性。

### 维护窗口旗标（maintenance.flag）

**用途**：临时暂停自愈，进行人工维护（如升级代码、修改配置）。

```bash
# 启用维护窗口（7 天自动过期）
touch data/cache/maintenance.flag

# 检查维护窗口状态
ls -lh data/cache/maintenance.flag

# 提前结束维护窗口
rm data/cache/maintenance.flag
```

**行为**：
- 旗标存在且未过期（< 7 天）：`diagnose_three_loop.sh` 检测到后跳过自愈，仅报告状态
- 旗标过期（≥ 7 天）：自动删除旗标，恢复自愈
- 诊断输出：`MAINTENANCE [维护窗口中，暂停自愈]`

**注意**：维护窗口不会停止正在运行的 supervisor/slow loop，只阻止自动重启。

### 熔断机制（heal_fail.count）

**用途**：防止自愈死循环（如配置错误导致反复重启失败）。

**触发条件**：连续 3 次自愈失败（`heal_fail.count >= 3`）。

**行为**：
- 触发熔断：停止自愈，发送告警（日志 + 桌面通知），创建 `d5_disabled.flag` 禁用孤儿回收
- 诊断输出：`CIRCUIT_BROKEN [熔断中，需人工清除 heal_fail.count]`

**恢复步骤**：
```bash
# 1. 排查问题（查看 data/cache/supervisor.out 日志）
# 2. 同时清除两个文件
rm data/cache/heal_fail.count data/cache/d5_disabled.flag
# 3. 手动重启 supervisor
bash scripts/start_supervisor.sh
```

**自动清零**：每次自愈成功后，`heal_fail.count` 自动清零。

### 孤儿 run 回收（active_runs.json + flock）

**用途**：防止 supervisor 被硬杀后，慢环进程成为孤儿继续消耗资源。

**机制**：
1. supervisor 启动慢环时，两段式写入 `data/cache/active_runs.json`：
   - Popen 前：写意图记录（含 batch_id）
   - Popen 后：补 pid + cmdline
2. `diagnose_three_loop.sh` 检测到 supervisor 不在运行时：
   - 读取 `active_runs.json`
   - 检查 `aligned_slow_loop.lock`（flock）
   - 若锁被持有但 pid 不存在/不匹配：kill 孤儿进程
   - 校验 worktree 路径（防误杀其他会话）

**诊断输出**：
- `发现孤儿 run：pid=XXX batch=XXX cwd=XXX`
- `孤儿 run 已清理`
- `无孤儿 run（锁可获取）`

**禁用孤儿回收**：
```bash
# 临时禁用（熔断时自动创建）
touch data/cache/d5_disabled.flag

# 恢复
rm data/cache/d5_disabled.flag
```

### 诊断脚本（diagnose_three_loop.sh）

**用途**：统一的三环健康检查与自愈入口。

```bash
# 手动运行诊断
bash scripts/diagnose_three_loop.sh
```

**输出状态**：
- `HEALTHY`：三环正常
- `HEALED`：检测到问题并已自愈
- `MAINTENANCE`：维护窗口中，暂停自愈
- `CIRCUIT_BROKEN`：熔断触发，需人工干预
- `NEEDS_HUMAN`：检测到问题但无法自动修复

**自动调度**：需配置 Windows Task Scheduler（每 15 分钟运行一次），见 `docs/superpowers/runbooks/task_scheduler_setup.md`（待补）。

### 四类停用路径（回滚预案）

| 停用对象 | 操作 | 恢复 |
|---------|------|------|
| 调度任务 | Task Scheduler 禁用 | 启用任务 |
| 维护窗口 | `touch maintenance.flag` | `rm maintenance.flag` 或等待 7 天过期 |
| 孤儿回收 | `touch d5_disabled.flag` | `rm d5_disabled.flag` |
| 熔断 | `heal_fail.count` 达到 3 | `rm heal_fail.count d5_disabled.flag` |

**原则**：每项停用都可通过删一个文件 / 禁一个任务实现，无需回滚代码提交。

### 演练验证（2026-10-08 完成）

5 次演练全部通过：
1. ✅ 自愈恢复：supervisor 被杀后 11 分钟内恢复
2. ✅ 维护窗口：旗标存在时阻止自愈，移除后恢复
3. ✅ 熔断触发：3 次失败后触发，清除后恢复
4. ✅ 孤儿回收：清理 stale active_runs.json
5. ✅ D5 禁用：旗标存在时不回收，移除后回收

**发现并修复**：孤儿清理逻辑在锁可获取时未清理 stale active_runs.json，已修复（commit `b232e14`）。

---

## 数据资产备份与清理（2026-10-07）

**备份**（2026-10-07 晚裁定：与活仓同一个仓库，远端 GitHub 即备份）：

- 推送 `origin`。不跑 `backup_data_assets.sh`，不设 cron，不设 rclone，不设备份机目录，不设名为 backup 的第二 remote。
- 入库：`task_FM/config/aligned_verdicts.jsonl`、`baseline_points_*.jsonl`、`baseline_metrics.json`、`.omc/supervisor_decisions.jsonl`。
- 不入库：`.env` / `.env.*`、`data/cache/`（含 `aligned_checkpoints/` 与 `daily_pred/`）、`logs/`。
- 活仓上这些入库路径若还是未跟踪文件，在活仓 `git add` 后推 `origin`。不要把别的机器上的快照拷回来覆盖活文件。
- 恢复：从 GitHub 克隆或 `git checkout` 对应路径。`data/cache/` 不在仓里，随活仓磁盘走。

**清理**（配套禁令，详见 AGENTS.md）：

- **裸 `git clean -xdf` 禁止**；清理一律走 `<FM_ROOT>/bin/safe_clean.sh`：默认 dry-run（白名单自检，命中保护路径 FATAL），确认后 `--apply`
- 保护白名单：`task_FM/config/`、`.omc/`、`data/cache/`、`logs/`、`.env*`

---

## 故障速查

| 现象 | 排查 |
|------|------|
| `another supervisor holds the lock` | 已有实例；查 `supervisor.lock` / 进程 |
| `another slow loop instance holds the lock` | 同上，慢环锁 |
| harvest 空但 run 已结束 | 看 `results/**/proposals/*.json` 与 `reject_reasons`：机制 <40、`no_failure_delta`、DEAD/HOLD 品种、cov 不在池、symbol 非法都会拒 |
| PI 议程总是 `.rejected` 缺 exploit/falsifier | `cohort_size=2` 必须用 `panel_topology:fm_two_peer`。仍指向 `legacy_multi_pi_two_round` 时 2 个合同盖不住 4 角色。改完重启监督环 |
| `dir_acc<0.52` 但 `gate_pass=True` | 查 verdict 的 `effective_min`/`baseline_dir_acc`。低基线品种可放到 0.50。不要改 `gate()` 公式 |
| 429 后开了新 run | 同提供商同 model id 应 resume `last_run_dir`；model id 不同（failover）允许新 run_dir。查 `paused_429` / `llm_provider` |
| token 预算误停 | `tok_unknown` 时跳过 token 预算；确认 generation_results 是否有 `runtime_usage` |
| peers 看不到 verdict | 查 `known_verdicts.inc.md` 是否被 materialize；模板 include 是否在 `prompt_base.jinja2` |
| `no_data` 永久死 | 不应进 `dead_variants`；可重试入队 |
| `assets_archive_error: Permission denied: '/workspace'` | 旧 Grok 盒硬编码路径残留在 `praxist_assets_archive.py`，已 catch 非阻塞；每 cycle ~2 次，待改为仓库相对路径 |
| 事件流出现 uptime 极短的 `supervisor_stopped/unexpected_exit` | 2026-09-09 前是 import 副作用假事件（当库 import 触发 atexit）；已修为仅 `main()` 武装 handler。pytest 污染走 `_patch_paths` 隔离（EVENTS_PATH 等落 tmp） |
| `sample_retest_enqueued` 事件后队列没跑 | 确认当时 `phase=slow`；复测行走同一慢环，与普通候选无差别 |
| prescreen 事件 `[WARN]...失败` / 提案无 `.prescreen.json` | **非故障**：缺 `TYPESAFE_API_KEY` 或 API 超时/降级时预筛静默跳过（软建议模式）。若需启用，在 `.env.praxist` 设 `TYPESAFE_API_KEY`（模型 `jev-latest`）。幂等守卫保证已有 `status=success` 结果不重复付费 |
| `[degraded] KB PF all null` 启动警告 | 已知退化，不影响核心功能。L1 ECONOMIC_VERDICT.json 缺失（2026-07-25 产物未版本化后被清理），KB 处于 `schemes_snapshot_no_L1` 模式。PF ratio gate 事实休眠（v23 不产出 PF）。详见 `docs/superpowers/specs/2026-09-20-kb-pf-degraded-fix-spec.md` |

## 相关文件

- `docs/praxist.md` — 架构概览（本体 vs 三环、现行合同、现场快照）
- `docs/2026-09-19-three-loop-followup-spec.md` — 2026-09-19 跟进合同
- `docs/archive/superseded-2026-09/2026-09-19-peer-proposal-quality-verification.md` — 提案质量单测验证（已归档）
- `scripts/praxist_supervisor.py` — 监督环入口（shim）。符号家见 [praxist.md](./praxist.md)
- `scripts/aligned_slow_loop.py` — 慢环
- `scripts/mem_guard.py` — 全局 flock≤2 + MemAvailable 门 + RSS shed（RLIMIT_AS 默认 OFF）
- `scripts/praxist_mem_guard_hook.py` / `install_praxist_mem_guard_hook.py` — protected_pids 强制挂钩
- `scripts/registry_lib.py` — 队列 / verdict / snapshot
- `scripts/goal_dsl.py` — success_condition 求值（AST 白名单）
- `scripts/praxist_assets_archive.py` — 快/慢环资产归档（含已知 `/workspace` 硬编码噪音）
- `docs/spec_hypothesis_driven_fast_loop_20260908.md` — 方案 A 设计（peer 机制化假设作者）
- `docs/archive/superpowers-plans/2026-09-02-praxist-three-loop.md` — 实施计划（Spec 绑定解释优先于过时 spec 句）
- `docs/archive/superpowers-specs/2026-09-02-praxist-three-loop-design.md` — §11 验收标准
