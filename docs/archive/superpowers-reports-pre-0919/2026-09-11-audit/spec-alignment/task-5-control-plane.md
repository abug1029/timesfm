# Task 5：控制面 + flock 条款对齐

- 任务：`docs/superpowers/plans/2026-09-11-spec-code-alignment.md` Task 5
- 仓：WSL `/home/abug/timesfm`（HEAD `9653264`，2026-09-11 11:19）
- 审核日：2026-09-11
- 范围：只读。对照 `docs/superpowers/specs/praxist_control_plane.md`、`docs/superpowers/specs/ACCEPT_flock_20260906.md` 与活代码。不改生产代码、SCHEMES、`.env*`、verdicts。
- 宿主实测（本审核当日）：`free -h` → Mem **7.7Gi** / Swap **2.0Gi** / 8 vCPU / 无 GPU。`/sys/fs/cgroup/memory.max` **不存在**。`/workspace` **不存在**。
- 更高权威（本任务强制对照）：`loop-constraints.md:49` 方案 A（peer 不再评估、不加载 TimesFM）；`docs/host_environment_assessment.md:3–10` 现行宿主 7.7GiB WSL。

**结论先说：** 两份 spec 都不能整份扔掉，也不能整份当现行 peer 合同。`2.5GiB` 拒启、`DEFAULT_MAX_SLOTS=1`、supervisor 429 failover、以及「新流程须总管批再启」的操作合同 **仍绑定**。头部「宿主 15GiB / 0 Swap」和「peer eval 硬顶」**已失效**——杀手是 2026-09-09 WSL 迁移 + 2026-09-08 方案 A。**不要改代码去贴 15GiB。** flock=1 / 2.5GiB 在 7.7GiB 盒子上比旧盒更该留着。

判定四种：`对齐` / `部分对齐` / `缺口`（有效设计代码没有或写反） / `失效`（不评代码对错）。

---

## 0. 两份 spec 总判

| Spec | 总判 | 理由 |
|------|------|------|
| `praxist_control_plane.md` | **部分有效** | mem_guard / 429 / 启停审批 / cohort=2 / 慢环加压数字仍约束。15GiB 宿主、peer 当评估器作战、goal 20 cycles/2026-09-20、`/workspace` 归档、按诊断 EV 选座 **失效**。 |
| `ACCEPT_flock_20260906.md` | **仍有效（验收合同）** | 三条规模数字与 hook 语义仍被代码实现；这是 2026-09-06 的现场验收记录，不是「peer 必须评测」合同。2026-09-10 的 `capacity_actions.log` 仍打出 `all 1 eval slots busy` 与 `need >=2.5GiB`。 |

上一轮 Task 3（文件级）已把控制面标成「半份仍约束」。本任务把条款拆开。

---

## 1. 计划点名的四条（必须先答）

计划原文：`2.5GiB / slots=1 / 429 / 启停审批：对齐或文档过期`；`15GiB、peer eval 硬顶：标失效或文档缺口，不要改代码去满足 15GiB`。

| 条款 | 判定 | 证据 |
|------|------|------|
| MemAvailable **2.5GiB** 拒启 | **对齐** | spec ACCEPT L4 + 控制面 L21；`scripts/mem_guard.py:44` `MIN_AVAIL_BYTES = int(2.5 * 1024**3)`；`EvalSlot.acquire` L175–181 不足则 `SystemExit` + `capacity_actions.log`。2026-09-10T06:26:22Z 日志：`MemAvailable=1045426176 < 2684354560 (refuse acquire; need >=2.5GiB)`。 |
| **DEFAULT_MAX_SLOTS=1** | **对齐** | ACCEPT L4；`mem_guard.py:43`；忙则 L200–205 `all {max_slots} eval slots busy … refuse`。2026-09-10T04:58:50Z / 06:20:42Z 日志三次 `all 1 eval slots busy`。hook `praxist_mem_guard_hook.py:8,88` `acquire_slot(apply_limit=False)`。`task_FM/task.yaml:81` `max_concurrent_evals: 1`（控制面 L39 说 yaml 非 runtime 强制，以 flock 为准——代码两侧都是 1，不冲突）。 |
| **429** | **对齐**（failover 路径）；日志文件名 **缺口** | `praxist_supervisor.py:978–1240`：`quota_gate` → `run_failover_llm` / `run_paused_429` / `wait_quota`；有 `FAILOVER_*` 不只 `wait_quota`；切回 primary 仅新 `run_started`。`tests/test_supervisor.py` 覆盖 paused_429 / failover。控制面 L47 要求写 `rate429.log`：**仓内无此文件、scripts 无写入**。决策走 `.omc/supervisor_decisions.jsonl`（存在）。 |
| **启停审批** | **部分对齐**（操作合同仍绑；不是程序锁） | 控制面 L5、L130：未获「按新流程启动」禁止自行 `praxist start` / supervisor 持续跑。代码 **没有** 审批令牌；`decide_fast_loop` L1220–1236 无活动 run 且已 harvest 就 `_plan_start`。修订记录 L166（2026-09-07）已批「快环启停自转」。因此：人审仍是现行操作合同；「禁止 supervisor 持续跑」那句被 09-07 续跑批准 **废掉**；不要把「代码没闸」写成缺口去加闸。 |
| 宿主 **15GiB** | **失效** | 控制面 L3、`praxist_goal.yaml:2` 注释。杀手：`docs/host_environment_assessment.md:3–10`（2026-09-09 WSL 7.7GiB）+ 本机 `free -h` Mem 7.7Gi。**禁止改代码去假装还有 15GiB。** |
| **peer eval 硬顶**（把 flock=1 理解成「peer 正在跑 TimesFM，所以并发=1」） | **失效** | 控制面 L19–27、L192「慢环与快环共用 flock；禁止双 TimesFM」。杀手：`loop-constraints.md:49` 方案 A——peer 不再评估、不加载 TimesFM。TimesFM 只应出现在慢环。flock=1 **作为慢环/旁路防御仍然对齐**（见下），作战对象不再是「peer eval」。 |

---

## 2. `praxist_control_plane.md` 条款表

### 2.1 头部 / 宿主 / 角色

| 条款 | spec 位置 | 代码/事实 | 判定 | 严重度 |
|------|-----------|-----------|------|--------|
| 宿主 8×CPU / **15GiB** / **0 Swap** / 无 GPU | L3 | 8 vCPU **对齐**；无 GPU **对齐**；MemTotal **7.7Gi**；SwapTotal **2.0Gi**（连 09-09 评估横幅「无 swap」也已过时） | **失效**（15GiB、0 Swap） | —（文档债；不改代码） |
| 已批准稳妥启动：eval 硬顶=1，cohort=2 | L4 | `mem_guard.py:43` 槽=1；`task_FM/task.yaml:108` `cohort_size: 2` | **对齐** | |
| 加压 eval=2 须另批 | L4 | 代码默认仍 1；无自动抬到 2 的路径 | **对齐** | |
| 未批禁止 `praxist start` / supervisor 持续跑 / 清 SHUTDOWN | L5 | supervisor 持续 poll 会自己 `start`（L1223+）；09-07 已批自转。清 SHUTDOWN：unstick 文档 L12 明文 Never clear | **部分对齐**：SHUTDOWN 禁令仍绑；「禁止持续跑」失效 | Low（操作理解） |

### 2.2 §1 内存 / cgroup 红线

| 条款 | spec 位置 | 代码 | 判定 | 严重度 |
|------|-----------|------|------|--------|
| MemAvailable **&lt; 2.5GiB** → **预警**（`mem_guard_watch.log`，15min 限频） | L21 | 代码在 2.5GiB 是 **拒启**（`mem_guard.py:175–181`）+ RSS shed（L496–527），不是只记 watch log。仓内 **无** `mem_guard_watch.log` 写入（hardcap 想写 `docs/superpowers/reports/praxist_20260906_ctrl/mem_guard_watch.log`，但 daemon 根路径是旧盒，见下）。ACCEPT 与 mem_guard 文档字符串把 2.5GiB 定义为 refuse，**比控制面表格更严，且与代码一致**。 | **部分对齐**：2.5GiB 阈值仍绑，语义是拒启不是预警。watch log **缺口** | Low（控制面表格内部也不如 ACCEPT 准） |
| MemAvailable **&lt; 2.2GiB** → 强制真实 fm_eval 并发 ≤1，TERM **最新** `.praxist-venv/bin/python evaluations/fm_eval/run.py` | L22 | `timesfm_hardcap_daemon.py:21` `HARD_MEM = 2.2 * 1024**3`；L100–101 `avail < HARD_MEM and len(loads) > 1` 才 demote。硬顶已经是 1，所以 2.2GiB 分支几乎只在有人把 cap 抬上去时有意义。TERM 顺序：最新 inline 优先，再最新 `run.py`（L69–72），与「禁杀 launcher」一致（`mem_guard.py:352–360` 不计 protected_pids launch）。 | **部分对齐**（逻辑在 daemon；daemon 在本机起不来，见缺口） | Medium |
| cgroup ratio **≥ 0.85** → 禁止新 eval | L23 | **代码无 0.85**。`CGROUP_REFUSE_RATIO = 0.90`（`mem_guard.py:45,167`）。本机无 `memory.max`，`cgroup_memory_ratio()` 恒 `None`，整条 cgroup 门在 WSL **惰性**。 | **缺口**（0.85 从未落地）；本机 cgroup 路径整体无效，不升 Critical | Medium（他机若有 cgroup 会少一档拒启） |
| cgroup **≥ 0.90** → TERM 全部真实 fm_eval，勿清 SHUTDOWN | L24–26 | daemon L22 `CGROUP_STOP = 0.90`，L96–97 `target_cap=0`。acquire 侧同阈值拒新。 | **对齐**（实现在）；本机 inert | |
| 计数真实 eval：`run.py` + inline `python -c` / HourlyModel / monthly_backtest / `/tmp/*eval*` / standalone_eval / `run_eval_v*`；禁止 bash/protected_pids launch 算进去；硬顶仍=1；&gt;1 时 TERM 最新 inline 优先；禁止 peer 自写 /tmp 评测 | L32–33 | `DEFAULT_CMD_PATTERNS` `mem_guard.py:69–91`；`is_timesfm_eval_cmdline` L333–397；hook `_GATE_PATTERNS` L37–55；daemon `classify()` L24–43。禁令仍是防回归，方案 A 后 peer 本就不该评测。 | **对齐**（防御面仍有效；「peer 会评测」口吻失效） | |
| yaml `max_concurrent_evals` 非 runtime 强制 | L39 | yaml 仍写 1（`task.yaml:81`）。ComputeBudget 是否丢，本任务不重审 Praxist 内部。活闸是 flock。 | **对齐** | |

### 2.3 §2 LLM / 429

| 条款 | spec 位置 | 代码 | 判定 | 严重度 |
|------|-----------|------|------|--------|
| 单次 429 → 记 `rate429.log`；确认 `paused_429` / `run_paused_429` / `run_failover_llm`；报总管 | L47 | 动作名 **对齐**（supervisor L1075, L1117, L1135）。`rate429.log` **仓内无写入**。告警是 `_emit_event` / `_log_decision`，不是 SendToAgent。 | **部分对齐** | Low（日志文件名） |
| 连续 429 ≥3 次/15min 或 paused_429 ≥20min → **提案**降档 cohort 4→2 或 2→1，或 `min_interval_minutes` +15（上限 45） | L48 | **无计数器、无自动改 yaml**。spec 本身写「须总管批后改配置」，不是自动闸。`task.yaml` 已是 cohort=2、`min_interval_minutes: 25`、`max_interval_minutes: 45`（L108, L115–116）。 | **部分对齐**：降档提案是人审流程；cohort/间隔已经停在批准值。没有 3/15min 计数器 **不算代码写反** | Low |
| 已配置 `FAILOVER_*` → `llm_provider=failover`，DashScope resume/start，不是只 `wait_quota` | L49 | supervisor L980–982, L1061–1124, L1193–1206。`docs/praxist_llm_env.md:42–52` 同合同。测试 `tests/test_supervisor.py` failover 用例。 | **对齐** | |
| 无 failover → `wait_quota`，禁止强行 start | L50 | L1133–1149 | **对齐** | |
| 切回 primary：仅下一次 **新** `run_started` 且 Ark window ok；禁止 mid-run thrash | L51 | L1220–1233；paused 时留在 failover（L1158–1160）。llm_env.md L52。 | **对齐** | |
| 本机默认 cohort_size=2 | L53, L105 | `task.yaml:108` | **对齐** | |

### 2.4 §3–4 session / ghost active_work / contributing

| 条款 | spec 位置 | 代码 | 判定 | 严重度 |
|------|-----------|------|------|--------|
| session 关后 5min 无 next-session → 自动解卡；Mem≥3GiB 写 ops nudge；可从磁盘 `evaluation_summary` 回填 1 条；同 run/gen ≤1/20min；二次 stuck 才报总管；禁止清 SHUTDOWN / 抬 eval / 杀整仓 | L63 | `praxist_session_unstick.py`：`IDLE_MIN_S=5*60` L43，`MEM_MIN_GIB=3.0` L44，`COOLDOWN_S=20*60` L42；Never 列表 L12–13。supervisor 每 poll 调 `detect_and_act`（L1547–1550）。 | **部分对齐** | |
| `count_claude` 用 `/home/box/.local/bin/claude` | 实现 L91 | 本机 claude 在 `/home/abug/.local/bin/claude`；`/home/box/...` **不存在**。pgrep 对不上 → `claude_n` 恒 0 → 「0 claude」条件在 WSL 会误触发。 | **缺口** | Medium |
| 回填 `evaluation_summary` 当 canonical 证据 | L63, unstick `write_backfill` | 方案 A 后 peer 不应再产 diagnostic summary。函数还在，作为「旧 run 残骸」防御可留，不能当现行合成证据源。 | **失效**（证据语义）+ 残留能力面 | — |
| `active_work` 不是幽灵 PID，禁止乱杀 | L71 | unstick 不杀 fleets；hardcap 只 TERM 匹配 eval cmdline。 | **对齐** | |
| contributing 只认 canonical `gen0_peer*` / `gen{N}_peer{M}`；`gen0_result_artifact` 不算 | L84–91 | unstick `canonical_peers()` L186+；backfill 注释 L279 明确 artifact 不计。 | **对齐** | |
| 解卡后须 ≥2 个不同 canonical peer 新 share | L97 | 检测用 cohort 比较，未见「解卡后必须 2 个新 share」的硬断言。 | **部分对齐** | Low |

### 2.5 §5 默认规模 / goal

| 条款 | spec 位置 | 磁盘 | 判定 |
|------|-----------|------|------|
| `generation_policy.cohort_size` **2** | L105 | `task.yaml:108` = 2 | **对齐** |
| fm_eval 硬顶 1 / 加压 2 须批 | L106 | flock 默认 1 | **对齐**（机制）；「peer 硬顶」叙事 **失效** |
| `min_contributing_peers` 2 | L107 | `task.yaml:114` = 2 | **对齐** |
| `max_interval_minutes` 45（提案） | L108 | `task.yaml:116` = 45（已落地，不再是提案） | **对齐** |
| `min_interval_minutes` 25 | L109 | `task.yaml:115` = 25 | **对齐** |
| goal `max_cycles=20` / `deadline=2026-09-20` / `token_budget_m=120` / `cpu_hours=30` | L115–118 | `scripts/praxist_goal.yaml:15–19` 已是 `999999` / `2099-12-31`（git `ee1f176` 无限制）。spec L124「以 yaml 与本节一致为准」——**yaml 赢，表格数字失效**。 | **失效**（表格） |
| `survivors_per_cycle=3` / `aligned_max_points=600` / `run_budget_hours=1.5` | L119–121 | yaml L21–23 同值 | **对齐** |
| wait_quota / paused_429 / failover **不阻塞** 已入队 aligned | L191 | supervisor L932, L1299, L1527, L1536–1540 | **对齐**（比 runbook L82「paused 不 harvest」更接近代码） |
| harvest 选人「先占不同品种，再按 EV 补齐」 | L190 | 活路径是 `harvest_proposals` + 机制化排序（supervisor L521, L566+ `priority_symbols`）。`harvest_survivors` L419–424 仍按诊断 EV 排，但是回滚函数。 | **失效**（方案 A） |
| 归档 `/workspace/shared/praxist_assets/` | L196 | `scripts/praxist_assets_archive.py:2,18` 默认仍 `/workspace/shared/praxist_assets`。本机 `/workspace` 不存在。runbook 已记 Permission denied。 | **失效**（路径）+ 残留能力面 | 

supervisor **每 poll 重载 goal**（L1389–1392）与控制面修订记录 L162 **对齐**。

### 2.6 §6 启前自检 / §7 告警

| 条款 | 判定 | 说明 |
|------|------|------|
| 清单是人审 checklist，不是代码 | **对齐**（操作） | 代码不会勾这些盒子。MemAvailable ≥6GiB 才启：supervisor 无此检查（只有 eval flock 的 2.5GiB）。这是启跑纪律，不是 runtime 闸。 |
| hook `_fm_mem_guard_patched is True`；双 venv `.pth` | **部分对齐** | 本仓 `.praxist-venv/lib/python3.11/site-packages/zz_fm_mem_guard.pth` **已装**（2026-09-07），loader 指向 `/home/abug/timesfm/scripts/praxist_mem_guard_hook.py`。安装器 `CANDIDATE_SITE` 仍写 python**3.13** + `/home/box/...`（`install_praxist_mem_guard_hook.py:19–21`）。重建 venv 后若不用当前解释器跑安装器，会漏 3.11。 | Medium（重装风险） |
| 日志目录 `docs/superpowers/reports/praxist_YYYYMMDD/` | 未核 supervisor 是否按此写 stdout | 不升缺口 |
| 立刻 SendToAgent 总管 | **缺口**（通道） | 代码写 jsonl / print，没有 SendToAgent。spec 是多 agent 操作面。 | Low |
| `.env.praxist` Ark host | 不读密钥文件（本任务禁止） | 不评 |

---

## 3. `ACCEPT_flock_20260906.md` 条款表

历史验收记录（ACCEPT4_20260906T084514Z），不是启动姿态。规模数字仍是活合同。

| 条款 | spec | 代码 | 判定 |
|------|------|------|------|
| `MIN_AVAIL_BYTES=2.5GiB` | L4 | `mem_guard.py:44` | **对齐** |
| `DEFAULT_MAX_SLOTS=1` | L4 | `mem_guard.py:43` | **对齐** |
| Hook wraps `python -m …protected_pids` via runpy `_cli` | L5 | `praxist_mem_guard_hook.py:12–14,136–180`：`runpy._run_code` 上 settrace，`_cli` 入口 `_wrap_globals_launch(..., "runpy:_cli_entry")` | **对齐** |
| Slot held until original `launch_command` returns | L6 | hook L94–111：`FM_EVAL_SLOT_HELD=1`，`finally` 里 `slot.release()` + `hook: release slot=… after launch returned` | **对齐** |
| 第一次 launch：`hook: launch_command wrapped (runpy:_cli_entry)` + `hook: launch slot=0` | L9 | 代码仍打这些字符串（L97–98, L156）。当前 `capacity_actions.log` 只保留 09-07 的 `runpy._run_code patched` / `protected_pids.launch_command patched` 和 09-10 的拒启行，ACCEPT4 原文案已滚动掉。 | **对齐**（实现）；日志未复现不等于缺口 |
| 并行第二次：`all 1 eval slots busy … refuse`（exit 1）；`hook: refuse launch_command` | L10 | `mem_guard.py:200–205` + hook L90–93。09-10 日志三次 busy refuse。`hook: refuse launch_command` 在 SystemExit 时才会写；现日志是 mem_guard 自己的 refuse 行，语义等同。 | **对齐** |
| 文件：`mem_guard.py` / `praxist_mem_guard_hook.py` / `timesfm_hardcap_daemon.py`（3s demote fallback） | L13–15 | 三个文件都在。daemon `INTERVAL` 默认 3s（L18）。 | daemon **部分对齐**（见下） |

`task_FM/evaluations/fm_eval/run.py:25–34`：无 `FM_EVAL_SLOT_HELD` 时自挂 flock（控制面修订 L161）。`scripts/aligned_slow_loop.py:131–132` `apply_mem_guard(apply_limit=False)`。慢环与旁路仍走同一把锁。

**没有** `tests/test_mem_guard.py` / 任何 `EvalSlot` pytest。ACCEPT 是现场记录，不是自动回归。这是测试缺口，不是规模数字写反。

---

## 4. 失效条款（不要改代码去满足）

### 4.1 宿主 15GiB / 0 Swap — 失效

- 杀手：`docs/host_environment_assessment.md:3–10`（2026-09-09 起现行宿主 WSL 7.7GiB）；`docs/runbook_praxist_three_loop.md:3,21`；本机 `free -h`。
- 控制面 L3、goal.yaml 头注释 L2 仍写「8×Xeon, 15GiB RAM, 0 Swap」。
- 本机还有 **2GiB Swap**（09-09 横幅「无 swap 兜底」也已过时）。这是文档债，不是「关掉 swap 才能对齐 spec」。
- **明确：不要把 flock 放宽到旧盒 N=2/N=4，不要把 `MIN_AVAIL_BYTES` 改成旧评估的 2GiB 去迁就 15GiB 叙事，也不要加代码去「用满 15GiB」。** 7.7GiB 上 2.5GiB 拒启 + 槽=1 更紧、也更对。

### 4.2 peer eval 硬顶（作战对象）— 失效

- 杀手：`loop-constraints.md:49`「peers 不再跑任何评估/加载 TimesFM」；`docs/praxist.md` 快环节；`docs/spec_hypothesis_driven_fast_loop_20260908.md`。
- 控制面 L19 标题「TimesFM eval」、L24「主动停 **peer eval**」、L192「慢环与快环共用 flock；禁止双 TimesFM」把 flock 说成 peer 并发闸。
- 方案 A 之后：peer 常驻约数百 MB、不加载权重；TimesFM 只在慢环单实例。flock=1 的**正确读法**是「本机 TimesFM/aligned 加载 ≤1」，外加防 peer 回归写 `/tmp` 评测。
- 因此：「把硬顶从 1 改成 2/4 因为 peer 不再加载」**也不是**本任务建议——7.7GiB 仍装不下两份 TimesFM。失效的是「peer 正在 eval」这句话，不是槽位数。

### 4.3 其它失效（不评代码对错）

| 条款 | 杀手 |
|------|------|
| goal 表 20 cycles / 120M token / deadline 2026-09-20 / 30 CPU-h | 磁盘 `praxist_goal.yaml` 无限制（后批）；spec 自称以 yaml 为准 |
| harvest「按 EV 补齐」 | 方案 A `harvest_proposals` + 机制排序 / `priority_symbols` |
| 从 diagnostic `evaluation_summary` 回填当合成证据 | 方案 A peer 不产该证据 |
| 归档 `/workspace/shared/praxist_assets/` | 宿主迁移；`/workspace` 不存在 |
| 安装器 / daemon / unstick 里的 `/home/box`、python3.13、`/workspace/repos/timesfm-abug1029` | 旧盒路径；属于残留能力面（见缺口） |
| 「禁止 supervisor 持续跑」绝对句（L5） | 2026-09-07 用户批续跑自转（控制面自己的修订记录 L166） |

runbook L24 / host_assessment L17, L120 仍写 flock≤**2** / MemAvailable&lt;**2GiB**。那是 **比控制面更旧** 的运维数字。活代码站在控制面/ACCEPT 一边（1 / 2.5GiB）。不要用 runbook 去改 `mem_guard.py`。

---

## 5. 仍对齐、继续绑定的条款（摘要）

1. **2.5GiB 拒启 + 槽=1** — `mem_guard.py` + hook + `run.py` 自挂 + aligned 入口 + 09-10 现场日志。
2. **429 failover** — supervisor `run_failover_llm` / `paused_429` / 仅新 run 回 primary；测试在 `tests/test_supervisor.py`。
3. **cohort=2、min_contributing_peers=2、min_interval=25、max_interval=45** — 已在 `task.yaml`，不再是「待审核提案」。
4. **survivors=3 / aligned=600 / 慢环不被 429 挡住** — yaml + supervisor。
5. **启停须总管批新流程** — 仍是给人和代理的操作合同；09-07 之后允许自转，不是每次 poll 再批一次。
6. **ACCEPT hook 语义** — runpy `_cli` wrap，槽拿到 `launch_command` 返回才放。
7. **contributing 只认 canonical peer_id** — 仍对。
8. **goal 每 poll 重载** — 仍对。

---

## 6. 缺口（有效设计 vs 代码）

这些不是 15GiB 失效条款。**不要**用它们当借口去改内存上限。

| ID | 条款 | spec | 代码 | 严重度 | 建议（另开 plan，本任务不改代码） |
|----|------|------|------|--------|----------------------------------|
| G1 | cgroup ≥0.85 拒新 eval | 控制面 L23 | 只有 0.90；本机无 cgroup memory 文件 | Medium | 改文档改成「仅 0.90，且 WSL 无 cgroup 则跳过」；或真要两档再实现。**不要**为 15GiB 调阈值。 |
| G2 | `rate429.log` / `mem_guard_watch.log` | L47, L150 | 无写入；决策在 `.omc/supervisor_decisions.jsonl` 与 `capacity_actions.log` | Low | 改 spec 日志名对齐现文件，或补写。 |
| G3 | hardcap daemon 作为 3s 降档后备 | ACCEPT L15；控制面 L22/L24 | `timesfm_hardcap_daemon.py:13` `REPO = Path('/workspace/repos/timesfm-abug1029')`；本机 `/workspace` 不存在，import `mem_guard` 必失败。主路径 flock+hook **不依赖** daemon。 | Medium | 若还要后备，把 REPO 改成本仓根。**不要**按 15GiB 重写 cap。 |
| G4 | session unstick 数 claude | 控制面 L63–64 | `pgrep -f /home/box/.local/bin/claude `（unstick L91）；本机二进制是 `/home/abug/.local/bin/claude` | Medium | 改成 `pgrep -f claude` 或本机路径。这是 WSL 迁移残留，不是 15GiB 问题。 |
| G5 | 安装器 site-packages 列表 | 控制面 L132 双 venv `.pth` | `CANDIDATE_SITE` 只有 python3.13 与 `/home/box/.praxist-venv`（install L19–21）；注释还写 `GLOBAL≤2`（L90），与槽=1 矛盾。当前 3.11 `.pth` 是已装好的，重装才踩坑。 | Medium | 把 3.11 本仓 site 写进候选；注释改成 GLOBAL≤1。 |
| G6 | ACCEPT 无 pytest | ACCEPT 全文 | `tests/` 无 `EvalSlot` / flock 用例 | Low | 若要防回归，另开测试任务。现场日志已证明 09-10 仍拒第二槽。 |
| G7 | SendToAgent 告警路由 | 控制面 L148 | 无此调用 | Low | 操作面，不是运行时硬闸。 |

**不是缺口：**

- 代码没有「总管审批」环境变量 — 设计就是人审，09-07 已批自转。
- peer 不再加载 TimesFM 但 flock 仍=1 — 慢环仍要 TimesFM，7.7GiB 上 1 是对的。
- 2.5GiB 在代码里是拒启而控制面表格写成预警 — 以 ACCEPT + `mem_guard.py` 为准，改表格。
- goal 无限制 vs spec 表 20 cycles — yaml 是更高磁盘权威，标失效不标缺口。

---

## 7. 建议怎么改文档（本任务不落地）

**改文档横幅（优先）：**

1. `praxist_control_plane.md` L3：宿主改成「WSL2 8 vCPU / **7.7GiB** / Swap 以 `free -h` 为准 / 无 GPU」。删 15GiB、0 Swap。
2. 同一文件 §1 标题与 L24：把「peer eval」改成「TimesFM / aligned 加载」。写明方案 A 后 peer 不加载；flock=1 是慢环硬顶 + 旁路防御。
3. L21：2.5GiB 改成「拒启」，与 ACCEPT/代码一致；预警另说。
4. L23：0.85 要么删，要么标明未实现。
5. §5 goal 表：删 20/120/2026-09-20，改指向 `scripts/praxist_goal.yaml` 磁盘值。
6. L5：「禁止 supervisor 持续跑」改成「未批新流程不得**首次**拉起；09-07 起已批自转」。
7. `praxist_goal.yaml` 头注释同样去掉 15GiB。

**不要做：**

- 不要改 `MIN_AVAIL_BYTES`、`DEFAULT_MAX_SLOTS` 去贴 15GiB 或 runbook 的 2GiB/槽=2。
- 不要为了「peer 不评估」把硬顶抬到 2。
- 不要把失效的 peer-eval 作战手册重新实现一遍。

**有效缺口另开 plan（可选，非本任务）：** G3 daemon 路径、G4 claude pgrep、G5 安装器 3.11。这三项是旧盒路径残留，修的是 WSL 可运行性，不是容量合同。

---

## 8. 与上一轮的关系

- Task 1 / Task 3 已指出控制面「半份仍约束」、15GiB 与 peer eval 冲突。本任务把条款落到文件:行，并核对 09-10 `capacity_actions.log` 与本机 7.7GiB。
- runbook L24 flock≤2 / 2GiB **不是**本任务要代码去迁就的合同；它比 ACCEPT 更旧。
- 方案 A「peer 不评估」已在 Task 4 范围；本任务只用来当 peer-eval 硬顶的杀手，不重审 harvest。

---

## 9. 条款计数（供 Task 8 总表）

| Spec | 对齐 | 部分对齐 | 缺口 | 失效 |
|------|------|----------|------|------|
| `praxist_control_plane.md` | 2.5GiB 拒启、槽=1、429 failover、cohort/间隔、survivors=3、aligned=600、慢环不被 429 挡、canonical peer、goal 每 poll 重载、eval cmdline 匹配 | 启停审批（人审/自转）、2.5 预警 vs 拒启、2.2GiB daemon、unstick、0.90 cgroup（本机 inert）、hook 安装器 | G1 0.85；G2 日志文件名；G3 daemon 根路径；G4 claude 路径；G5 安装器 3.13；G7 SendToAgent | 15GiB/0 Swap；peer eval 作战；goal 20/120/日期；EV 选座；`/workspace` 归档；「禁止持续跑」绝对句；diagnostic 回填当证据 |
| `ACCEPT_flock_20260906.md` | 2.5GiB、槽=1、runpy `_cli` wrap、槽持有到返回、busy refuse 文案 | daemon 3s 后备（文件在、路径死） | G6 无 pytest | 无（不要把 15GiB 算进这份） |

**Critical 缺口：0。** 没有「有效 spec 与活生产路径相反且会改错信号/硬门/收割」的条款。最大风险是人把 15GiB / peer eval / runbook 槽=2 重新执行进代码——那是文档毒，不是代码现在写反。
