# Praxist 控制面（预见性控制）

> 宿主：8×CPU / 15GiB / 0 Swap / 无 GPU。Owner：FM研；总管做预见性控制，不靠事后报炸再修。  
> 状态：2026-09-06 **已批准稳妥启动**（用户+总管：eval 硬顶=1，cohort=2）。加压 eval=2 须另批。  
> 禁止：未获「按新流程启动」前自行 `praxist start` / supervisor 持续跑 / next-session 解卡 / 清 SHUTDOWN 续跑。

## 0. 角色与节奏

| 角色 | 职责 |
|------|------|
| 总管 | 批准启停、改 cohort/硬顶、处理熔断升级 |
| FM研 | 执行控制面、维护 mem_guard hook、按清单自检后启跑、即时告警 |
| 监控 routine | 定时只读扫 Mem/cgroup/429/session 停滞；越线立刻报总管（不擅自扩权） |

启跑前必须完成 §6 自检；启跑后任何红线触发 → **先控载/停 eval**，再报总管，禁止干等到 gen cap。

---

## 1. 内存 / cgroup 红线（TimesFM eval）

| 条件 | 动作 | 谁执行 |
|------|------|--------|
| MemAvailable **&lt; 2.5 GiB** | 预警：记 `mem_guard_watch.log`，报总管（可静默限频 15min/次） | 监控 |
| MemAvailable **&lt; 2.2 GiB** | **强制**真实 `fm_eval` 并发 ≤ **1**（TERM **最新** `.venv/bin/python evaluations/fm_eval/run.py`，禁杀 launcher/wrapper） | FM研/监控 |
| cgroup ratio **≥ 0.85** | **禁止新 eval**（拒启 / flock 不放行）；已有 eval 可跑完或按下行降档 | mem_guard + 监控 |
| cgroup ratio **≥ 0.90** | **主动停 peer eval**（TERM 全部真实 fm_eval），防 ORCHESTRATOR_SHUTDOWN@~0.94；报总管；**勿**自行清 SHUTDOWN 续跑除非总管授权 | FM研 |
| 出现 `ORCHESTRATOR_SHUTDOWN` | 立即报总管；默认停干净再议，禁止 peer sleep 空转耗壁钟 | FM研 |

实现锚点：

- `scripts/mem_guard.py`：flock≤配置槽、MemAvailable 拒启、RSS shed  
- `scripts/praxist_mem_guard_hook.py` + `zz_fm_mem_guard.pth`：强制 `protected_pids.launch_command`  
- 计数真实 eval：`fm_eval/run.py` **以及** inline `python -c` / `HourlyModel` / `DailyModel` / `monthly_backtest` / `do_evaluate`（禁止把 bash/`protected_pids launch` cmdline 算进去）；硬顶仍=1，>1 时 TERM **最新** inline 优先

默认硬顶（本机）：

- **稳妥**：`fm_eval` 硬顶 **1**（推荐默认）  
- **加压**：硬顶 **2**，须总管**显式批准**本轮  
- yaml `max_concurrent_evals` **非** runtime 强制（ComputeBudget 会丢），以 flock/hook/本控制面为准

---

## 2. LLM / 429 控制

| 信号 | 动作 |
|------|------|
| 单次 429 / rate limit | 记 `rate429.log`；确认 supervisor `paused_429` / `run_paused_429` / `run_failover_llm`；立刻报总管 |
| **连续 429**：同窗口 **≥3 次 / 15min** 或 **paused_429 持续 ≥20min** | **提案降档**（须总管批后改配置）：`cohort_size` 4→**2** 或 2→**1**；或 `min_interval_minutes` +15（上限 45） |
| Ark 配额窗不足且 **已配置** `FAILOVER_*` | supervisor：`llm_provider=failover`，DashScope `resume`/`start`（`--model qwen3.7-plus`）；**不是**只 `wait_quota` |
| Ark 配额窗不足且 **无** failover | 跟现有 `wait_quota`；禁止强行 start |
| 切回 primary | 仅下一次 **新** `run_started` 且 Ark window ok；禁止 mid-run thrash |

本机默认 **cohort_size=2**（见 §5），降低并发打 Ark 的尖峰。详见 `docs/praxist_llm_env.md` §429 Failover。

---

## 3. Session / next-session（禁止干等 60min）

教训（2026-09-06）：bg eval 失败后 SDK 关 session，peer 进 `_wait_for_next_session_event`；`active_work` 仍显示 4，壁钟空耗到 soft/hard cap。

| 条件 | 动作 |
|------|------|
| 任一 peer session 因 `terminal_background_only` / eval failed 关闭后，**5 min 内无** `next-session` | **自动解卡**（`scripts/praxist_session_unstick.py`，supervisor 每 poll 兼跑）：Mem≥3GiB 写 ops nudge；缺 canonical peer 时可从磁盘 `evaluation_summary` 回填 1 条（非新 eval）。同 run/gen ≤1/20min；**二次 stuck 才报总管**。禁止清 SHUTDOWN / 抬 eval / 杀整仓 |
| 唤醒后 **10 min** 仍 0 claude | 升级总管：停跑或批准更深干预（禁止私自整轮狂杀再启除非授权） |
| 禁止 | 干等 `max_interval_minutes=60` cap 才发现空转 |

---

## 4. 合成 / ghost `active_work`

**定义澄清**：`active_work`（`_active_generation_work_count`）= 未 done 的 peer **asyncio 任务** + 当代 protected jobs。session 关闭但 peer 协程在等 next-session 时，`active_work=4` **不是**脏 PID，**禁止**当幽灵 PID 乱杀。

| 检测 | 解除 |
|------|------|
| `active_work>0` 且 `active_evals=0` 且 claude=0 持续 ≥5min | 判定空转；走 §3 nudge 或总管停跑 |
| `peers`（contributing）&lt; `min_contributing_peers` 且 findings 多数 `peer_id=gen0_result_artifact` | 已知污染：自动物化结果不计 canonical；需 peer `share_finding` 带真实 `gen0_peer*`。监控告警，不靠 artifact 数过门 |
| protected_pids 非空但进程已死 | `list_active_jobs` 应剪枝；若卡住，报总管后清对应 manifest（慎） |

合成门：`min_findings` + `min_contributing_peers` + `min_interval_minutes`；硬顶 `max_interval_minutes`。控制面优先避免空转，而非依赖硬顶收尸。

---


## 4.1 教训硬规则：contributing 只认 canonical peer_id

**2026-09-06 实测：** `shared_store.db` 中大量 findings 的 `peer_id=gen0_result_artifact`（自动物化 evaluation_summary / result artifact），合成门显示 `peers=1/2`——只有真实 `gen0_peer*` 的 `share_finding` 才计入 `COUNT(DISTINCT canonical peer_id)`。

| 算不算 contributing | 来源 |
|---------------------|------|
| **算** | peer 经 MCP `share_finding`（或等价）写入、且 `peer_id` 可规范为 `gen0_peerN` / `gen{N}_peer{M}` |
| **不算** | auto-materialized result artifact、`gen0_result_artifact`、空/NULL、跨 gen 泄漏 stamp |

控制面要求：

1. 监控告警时同时报：`findings_total` **与** `canonical_contributing_peers`（勿用 artifact 数冒充进度）。
2. 禁止把「results/ 下 summary 很多」当成合成已可过门。
3. 解卡唤醒（仅总管批准的 ops nudge）之后，必须以 **≥2 个不同 canonical peer** 新 share 为恢复信号；否则仍算未恢复。
4. 旧 run 解卡/nudge/next-session：**在全停+重构指令下禁止**；本条仅作将来新流程的设计约束。


## 5. 默认规模（本机提案）

| 项 | 提案 | 备注 |
|----|------|------|
| `generation_policy.cohort_size` | **2** | 原 4 易内存尖峰 + Ark 并发；待审核后改 `task_FM/task.yaml` |
| `fm_eval` 硬顶 | **1**（默认稳） / **2**（加压须批） | flock 槽同步 |
| `min_contributing_peers` | **2**（若 cohort=2 则有效上界 2） | 保持 |
| `max_interval_minutes` | **45**（提案，原 60） | 缩短空转上界；待批 |
| `min_interval_minutes` | **25** | 略低于 30，便于受控推进 |

### Goal 长跑受控提案（`scripts/praxist_goal.yaml`）

| 字段 | 提案 |
|------|------|
| `max_cycles` | **8**（2026-09-07 用户批续跑；cycles_done 已 3） |
| `deadline` | **2026-09-13** |
| `token_budget_m` | **80**（2026-09-08 总管批；spend~46 相对 50 过紧；deadline 仍 2026-09-13） |
| `cpu_hours` | **8** |
| `survivors_per_cycle` | **3**（慢环加压，已批） |
| `aligned_max_points` | **600**（慢环加压，已批） |
| `run_budget_hours` | **1.5** |
| success_condition | 不变 |

已批准稳妥启动 + 慢环加压（survivors=3 / aligned=600）；以 `scripts/praxist_goal.yaml` 与本节一致为准。

---

## 6. Supervisor 启前自检清单

- [ ] 总管已批「按新流程启动」+ 本控制面版本  
- [ ] 无残留：`praxist_supervisor` / `praxist.run` / `claude` / `fm_eval` / `aligned_slow_loop`  
- [ ] `mem_guard` hook：`protected_pids._fm_mem_guard_patched is True`（双 venv `.pth`；重建 venv 后重跑 `scripts/install_praxist_mem_guard_hook.py`）  
- [ ] MemAvailable **≥ 6 GiB** 才启（最低 ≥4 GiB 须总管特批）  
- [ ] cgroup ratio **&lt; 0.70**  
- [ ] `.env.praxist` source 后：`ANTHROPIC_BASE_URL` host=`ark.cn-beijing.volces.com`，key set（不回显）  
- [ ] `supervisor_state`：phase=fast，paused_429=false，cycles 按本轮约定  
- [ ] 无 `ORCHESTRATOR_SHUTDOWN` 在将复用的 run_dir（新跑用新 run）  
- [ ] 日志目录：`docs/superpowers/reports/praxist_YYYYMMDD/`  
- [ ] 监控 routine 已按本控制面更新并 **resume**（仅监控，不擅自启跑）  
- [ ] `cohort_size` / eval 硬顶与 §5 批准值一致  

启跑命令（仅批准后）：持续 `scripts/praxist_supervisor.py`（非 `--once`），stdout 进上述日志目录。

---

## 7. 告警路由

- **立刻 SendToAgent 总管**：429、SHUTDOWN、cgroup≥0.90、Mem&lt;2.2 降档、session 5min 无 next-session、run_dir 突然消失  
- **用户**：仅重大状态（启停、熔断、需选择）  
- 日志：`rate429.log`、`mem_guard_watch.log`、`.omc/supervisor_decisions.jsonl`

---

## 8. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-09-06 | 初稿：自 9-6 长跑熔断/空转/contributing 污染教训 |
| 2026-09-06 | **稳妥启动批准**：cohort=2，fm_eval 硬顶=1，goal max_cycles=3/token=20M |
| 2026-09-08 | **inline bypass 降级**：matcher 计 HourlyModel/`python -c`/monthly_backtest；`run.py` 无 `FM_EVAL_SLOT_HELD` 时自挂 flock；cgroup≥0.90 拒启+hardcap TERM；硬顶仍≤1 禁抬 2 |
| 2026-09-08 | token_budget_m **50→80**（spend~46 相对 50 过紧）；deadline 仍 2026-09-13 |
| 2026-09-08 | token_budget_m **30→50**；budget_hit 若 run 仍活则 `budget_hit_wait_run`（先等结束再 harvest/slow/exit） |
| 2026-09-07 | **自动 session 解卡**：`praxist_session_unstick.py` + supervisor poll；nudge/回填；限频 20min；二次 escalate |
| 2026-09-07 | 用户批续跑：max_cycles **3→8**；快环启停自转（harvest→slow→下一快环），异常仍报总管 |
| 2026-09-06 | token_budget_m **20→30**（failover 烧 ~22M 后；deadline 仍 2026-09-13）；budget_hit 先 harvest/slow 再 exit |
| 2026-09-06 | **慢环加压**：survivors=3 / aligned=600；quota 不挡 slow；`/workspace/shared/praxist_assets` 归档 |
| 2026-09-06 | **inline bypass**：peer `python -c`/do_evaluate 计入 eval 槽；matcher 扩 DailyModel/do_evaluate；硬顶仍=1 |

## LLM 429 Failover（2026-09-06）
- 主用：Volcengine Ark（`PRIMARY_*` / `ANTHROPIC_*`）
- 备用：DashScope Anthropic 兼容（`FAILOVER_*` / `ANTHROPIC_FAILOVER_*`，model=`qwen3.7-plus`）
- 触发：active run + quota_gate 失败且 `llm_provider=primary` + failover 已配置 → `run_failover_llm`（stop→overlay env→resume）；paused/wait_quota 亦优先 failover，不只 `wait_quota`
- state：`llm_provider`（兼写 `llm_route`）
- 切回 primary：仅下一次 **新** `run_started` 且 Ark window ok（禁止 mid-run thrash）
- 模型接线：`--model` argv + `PRAXIST_MODEL`（非 task.yaml）
- BASE_URL 透传：`scripts/praxist_llm_env_hook.py`（task.yaml 勿写死 BASE_URL）
- 回 Ark：下一轮新 `run_started` 默认 primary；或手动 state `llm_provider=primary`
- failover 仍失败：`paused_429` 等 Ark reset

## 慢环加压（2026-09-06 批准）

目标：每个快环结束后，慢环抽更多、更深的 aligned survivors，且 **不因 LLM 429 / wait_quota / failover 卡住本地 CPU 抽干**。

| 项 | 值 | 说明 |
|----|----|------|
| `survivors_per_cycle` | **3** | harvest 每周期最多入队 3 个 |
| `aligned_max_points` | **600** | aligned 回测深度（原 350） |
| harvest 选人 | symbol×cov 多样性 | 先占不同品种，再按 EV 补齐；禁止 3 个同品种挤满 |
| wait_quota / paused_429 / failover | **不阻塞** 已入队 aligned | `ensure_phase`：queue/slow 存活 → 强制 `phase=slow`；harvest 不再因 paused_429 跳过 |
| TimesFM eval 硬顶 | **仍=1** | 慢环与快环共用 flock；禁止双 TimesFM |

### 资产归档

快环 harvest / 慢环 drain 完成后，自动 append 到 `/workspace/shared/praxist_assets/`（`manifest.jsonl` + `timeline.md`）。恢复见该目录 `RECOVERY.md`。权重不进资产。

