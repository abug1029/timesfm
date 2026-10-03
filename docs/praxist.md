# Praxist 在 FM_a 里做什么

面向第一次接触本仓 Praxist 的人：五分钟搞清**它是什么、怎么转、读哪份文档**。运维命令、故障表、启停细节见 [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md)。

| 你想… | 去哪 |
|---|---|
| 理解架构与合同 | 本文 |
| 启停 / 429 / 队列 / 复测 | [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md) |
| 快环现行合同（方案 A） | [spec_hypothesis_driven_fast_loop_20260908.md](./spec_hypothesis_driven_fast_loop_20260908.md)；选题纪律见 [2026-09-19-three-loop-followup-spec.md](./2026-09-19-three-loop-followup-spec.md) |
| LLM 环境变量 | [praxist_llm_env.md](./praxist_llm_env.md) |
| 宿主容量与内存硬顶 | [host_environment_assessment.md](./host_environment_assessment.md) |
| 机器状态 / 裁决 | `data/cache/supervisor_state.json`、`task_FM/config/aligned_verdicts.jsonl` |
| 目标与预算 | `scripts/praxist_goal.yaml` |

**不要改** `.venv` 里的 Praxist 源码（升级会丢）。本仓只通过任务包、提示词和外层监督环适配。

---

## 1. 两层，不要混

Praxist（[Sapient Intelligence](https://github.com/sapientinc/PRAXIST)，本仓安装 **0.5.0**）是一个**与领域无关的多 Agent 研究控制平面**。论文：[From Experimental Artifacts to Solution Lineages](https://arxiv.org/abs/2608.25955)。

它不管期货、不管协变量，只提供研究过程：并行 peers、代际编排、证据搬运、PI/Chair 规划。科学内容全部在任务包 `task_FM/`。

| Praxist 本体管 | 本仓任务包管 |
|---|---|
| Peer 会话、代际、资源调度、生命周期 | 目标、约束、基线、允许改什么 |
| Agent 运行时、证据保留、可复现状态、综合规划 | 评估器、指标、成熟度、提示词、角色 |

本仓再在外面加了一层**零 token 三环调度**，因为合格 walk-forward（n≥350）要数小时，塞不进任何一代窗口。Praxist run 因此只当快环，不当唯一执行器。

红线仍在 `loop-constraints.md`：peers 不能改 `config/prediction_scheme.py`、`cascade/`、`data/config.py`、`cascade/features.py`。固化 = 建议包 + 人改 SCHEMES。

---

## 2. Praxist 本体怎么转

工作单位：

- **Task project**：外部可跑的研究问题（这里是 `task_FM/`）
- **Peer**：一代里的一个研究 Agent
- **Generation**：一群 peer 干活，然后做一次规划边界
- **Finding**：结构化证据或可复用教训
- **Incubator / Frontier / Gems**：三档证据保留（孵化 → 前沿 → 固化记忆）
- **PI / Chair**：规划面板。PI 根据已提交证据提议下一代议程；多 PI 时 Chair 合成一份

一代闭环：任务契约 + 已提交议程 → 并行 peers → 结果物化成 findings → PI/Chair 综合 → 更新 frontier / incubator / Gems → 写下一代议程。

CLI：`praxist start|resume|stop|status|monitor|doctor|resolve`。本仓入口是 `.venv/bin/praxist`。

证据角色（规划只信当前可信状态）：`canonical_state` / `validation_signal` / `derived_view` / `audit_snapshot` / `partial_output`。排行榜和报告是派生视图，不能反过来改裁决。代际关闭后晚到的结果不能重写本代。

---

## 3. 本仓三环

```
监督环  scripts/praxist_supervisor.py     纯 Python，0 token
   ├─ 快环  praxist start --task-path task_FM   烧 token，约 1.5h/run
   └─ 慢环  scripts/aligned_slow_loop.py        纯 CPU，0 token，唯一验证器
```

总线全是只追加文件。一个 **cycle** = 一次已结束的 Praxist run + harvest（有入队则再把慢环抽干）。不是 5 分钟 poll。`phase` ∈ `{fast, slow, wait_quota}`；慢环没抽干时禁止开下一轮快环。

### 快环（2026-09-08 方案 A 起）

Peer **是假设作者，不是评估器**。禁止跑 `evaluations/fm_eval/run.py`，禁止加载 TimesFM。n=3~6 的诊断 PF 统计上不可信（实测 ss+ccl 诊断 PF=10.1，慢环真相 1.02），还浪费一次模型加载。

Peer 第一件事：至少写 2 份假设到

`task_FM/experiments/run_*/results/gen_<N>/<peer>/proposals/<symbol>_<cov>.json`

合同：`schema=fm.hypothesis_proposal.v1`，`mechanism` ≥40 字（禁模板）、`symbol_fit`、预注册 kill/promote。同品种或同协变量已有失败 verdict 时必填 `failure_delta` ≥20 字。只许提议协变量池里 **active** 的项（`task_FM/config/covariate_pool.json`，6 族受控词表 `cascade/cov_family.py`）。新指标写 `new_cov_<name>.json`，进 backlog，不入评估队列。品种探索状态见 `task_FM/config/symbol_status.json`。

### 监督环

每 300 秒 tick：

1. 用 `scripts/praxist_goal.yaml` 的 DSL 判定成功 / 预算
2. 配额窗够才 `praxist start` / `resume`；429 则 stop。同提供商、同 model id 解封后 **resume 同一 run**；failover 且 model id 不同时允许新 `run_dir`
3. run 结束后 `harvest_proposals`：校验（含 DEAD/HOLD、`failure_delta`）→ 去重 → 分层选座 → 入慢环队列
4. **TypeSafe Jev 预筛**（可选，软建议）：连 peer 提案同时 `_prescreen_async`（fire-and-forget）调 TypeSafe System One 三问（机制可信度/新颖度/预期效果），写 `<proposal>.prescreen.json`。`_proposal_priority_score` 读它做 ± 调度分（invalid→-100、redundant+弱→-30、低可信→-20、effect==0且可信∈[0.4,0.6)→-15；skip=False+高效果→+10、新颖+高可信→+5）。**永远不阻断慢环回测**；无 `TYPESAFE_API_KEY` 或降级时静默跳过。降权因异步滞后一轮生效。详见 `cascade/typesafe_prescreen.py` 与记忆 `fm-typesafe-prescreen`。
5. 有货立刻拉慢环
5. 物化 `known_verdicts.inc.md`（Symbol status / Effective clues / Do not re-propose）与 `covariate_menu.inc.md`，喂给下一代。提示词先读证据，不要优先波动率族。

快环面板：`task_FM/task.yaml` 的 `cohort_size=2` 配任务侧 `panel_topology:fm_two_peer`（`peer_role_rotation = [exploit, falsifier]`）。bundled 默认要 4 个角色，两人 cohort 盖不住，议程会被拒。**不要改 `.venv` 里的 Praxist。** 改 topology 后重启监督环。

选座（`survivors_per_cycle=3`）：优先集 = goal `cadence.priority_symbols`（2026-09-23 起 goal.yaml 未设该键，优先集当前为空）；无优先品种时候选按协变量族正交填满，细节见 runbook 选座节。

近失误自动复测（2026-09-09 引入）：裁决只差样本（n<350；2026-09-11 时点触发条件 ic≥0.05、ev>0、PF 比现任好 5%，实现见 `scripts/praxist_supervisor.py::_retest_candidates`，以运行时代码为准）时，本地库长到 ≥350 就补队，checkpoint 只算新点。首个候选 `cj_oi`（n=324）。

### 慢环

消费队列，跑 `monthly_backtest.py` 全量 walk-forward。硬门预注册在 `config/praxist_task.yaml`（v23 纯预测质量口径；裁决唯一权威 = `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）：

- n ≥ 350
- n_eff ≥ 50（Bartlett 有效样本量）
- dir_acc ≥ `effective_min`（`max(0.50, min(0.52, baseline_dir_acc))`，基线缺失时 0.52；新 verdict 落库这两字段）
- 统计显著性：DM 检验（Newey-West HAC + HLN）+ BH-FDR（per-symbol；K<4 时降级固定 Bonferroni α=0.025）
- PF/EV/MaxDD/IC 退役出裁决链，仅作经济报表字段

日线预测按 `(symbol, cutoff, 窗口, 模型指纹)` 缓存（日线模型不吃协变量）。队列 claim / inprogress / recover，kill 后零损失。**只有慢环能写** `task_FM/config/aligned_verdicts.jsonl`。伪造 verdict = 破坏预注册纪律。

Stage 3 契约（2026-09-28/29 结案）：评估带 horizon 填充标记（`cascade/horizon_fill.py`）与实验指纹（`cascade/experiment_fingerprint.py`）；多重比较按研究 family 结账（`cascade/research_family.py`）；基线协议指纹由监督环 `ensure_baselines` 比对，不符自动重生。详见 [system_design.md §11.4](./system_design.md)。

---

## 4. 当前目标与现场（以 JSON 为准）

过期时以磁盘为准，不要把本节快照当成监督环现态。权威源：

- 监督状态：`data/cache/supervisor_state.json`
- 裁决：`task_FM/config/aligned_verdicts.jsonl`（按 `variant_id` 最新行）
- 目标与预算：`scripts/praxist_goal.yaml`

成功条件（goal.yaml 现行，**2026-10-02 重写**）：**唯一成功条件 `all_symbols_pass_phase1`**
——24 个目标品种（`m/ss/sr/cj/jd/lh/eg/rb/i/p/y/cf/bu/fu/ta/ma/fg/ur/px/oi/sh/sp/ao/sc`）
**每品种至少 1 个经 family 封账的确认变体**（`run_label == confirmed` 且 `fdr_pass is True`）。

- **原三阶段门槛全部退役**：`n_gate_pass_variants >= 10`、`avg_dir_acc_gate_pass >= 0.51`
  （0.51 作为绝对水平低于 `detection_threshold_vs_random`，作为相对基线增量低于
  `detection_threshold_vs_baseline`，两条路径都不达标）、`n_tier_a_or_b >= 8`。
  Phase 3 的 `multi_seed` / `decay` **仍未实现，且不发明通过线**
  （`docs/superpowers/specs/2026-10-02-phase3-multiseed-decay-todo.md`）
- 过门 = `pass_variants()`（严格链）：`run_mode == "confirmation"`（探索行一律不算）且 `gate_pass`
  且 `fdr_pass` 且 `p_value` 非空 且 `pairing_valid` 且 `missingness_admissible`
  且 `dm_status ∈ {ok, set_mismatch_ok}`。`migrated_pass` 与 `v2_pass` 已随v4 收口退役
- 预算（**有界**）：`max_cycles` 2000 · `cpu_hours` 2000 · `token_budget_m` **null（不参与停机）**
  · `deadline` 2028-10-02
- **预注册样本量已锁定**（监督环不改写）：jd 1,199 · sr 986，见 `task_FM/config/preregistry.jsonl`

磁盘快照（**2026-10-03**；过期以 JSON 为准）：

- `phase=fast`，`cycles_done=203`，`paused_429=false`
- 裁决注册表 **232 行 = 188 条跨协议旧行（活跃视图外）+ 44 条 v4**；v4 明细：`gate_pass` 13/44 ·
  `tier` S6/A6/B21/C11 · `run_mode` 全部 `exploration` · **确认级 `pass_variants` 0 条**
- 监督环 **PID 416**（2026-10-02 20:27 经规范启动器重启，`setsid nohup` 脱离会话；前一进程 PID 418
  于 10-02 19:05 干净退出 `exit_code 0` / uptime 114,957s）
- 协议指纹 **v4 = `f02b2a43…`**；9 个 nocov 基线全部带 v4 指纹（2026-10-01/02 重生，fu 为入集后首个基线）
- 阶段 3 确认机制已接线（2026-10-02，11 笔）：确认窗口透传、checkpoint 命名空间隔离、family 分派与封账、
  goal 重写、首批 2 条预注册、收割/复测只看当前协议
- 未决问题见 `docs/superpowers/reports/2026-10-03-fm-a-open-issues.md`
- 历史经济示例（`ss_vor` / `i_oi` / `m_ccl` / `cj_oi` 的磁盘裁决表）见 [system_design.md §4.3](./system_design.md)；「过硬门但亏钱 **不是** already solved」的纪律不变

重启（规范方式 = `scripts/start_supervisor.sh`，2026-09-21 起；PATH / `.env.praxist` / setsid 孤儿化由 launcher 处理并打印 PID）：

```bash
cd /home/abug/timesfm
scripts/start_supervisor.sh
```

`task_FM/task.yaml` **不要**放明文 API key；密钥只进 `.env.praxist`。

---

## 5. 效率改造已经落地的 / 还没动的

已落地：

1. 取消诊断档评估（快环 0 次模型加载）
2. 日线预测缓存（慢环候选之间复用）
3. 1 星优先选座
4. n 不足近失误自动复测
5. 429：同提供商 resume 同一 run；model id 不同允许新 `run_dir`（Ark 主 / DashScope 备）
6. TimesFM `ensure_compiled` 指纹跳过；生产 `DataStore` 连接关闭（compile-skip spec）

预测链剩余性能债（Hurst 循环等）记在 [audit_system_efficiency_20260908.md](./audit_system_efficiency_20260908.md)，与编排是两条线。

明确非目标：不改 Praxist 核心、不做 GPU/多机并行、监督环无出站通知（会话级监控随 Agent 会话消失）。

---

## 6. 历史文档怎么读

冲突时以 **方案 A**（[spec_hypothesis_driven_fast_loop_20260908.md](./spec_hypothesis_driven_fast_loop_20260908.md)）、`loop-constraints.md`、监督环 `harvest_proposals`（`proposals/*.json`）为准。09-02 实施计划「Spec 绑定解释」第 4 条（diagnostic survivors / `evaluation_summary.json`）**作废**。

| 文档 | 地位 |
|---|---|
| [praxist_integration_plan.md（已归档）](./archive/history/praxist_integration_plan.md) | 2026-09-01 方案稿，P0–P3 已落地；路径 `/root/timesFM_fu` 过时 |
| [praxist_directive_design.md（已归档）](./archive/history/praxist_directive_design.md) | 指令闭环仍有效；peer 跑 diagnostic 评估已被方案 A 取代 |
| [praxist_peer_evaluation_fix.md（已归档）](./archive/history/praxist_peer_evaluation_fix.md) | **失效（方案 A）**。只解释诊断 PF 不可信；禁止按本文给 peer 加评估 |
| `docs/archive/superpowers-specs/2026-09-02-praxist-three-loop-design.md` | 部分取代。骨架仍有效（慢环写 verdict、daily 缓存、同提供商 429 resume）；peer diagnostic 已废 |
| `docs/archive/superpowers-plans/2026-09-02-praxist-three-loop.md` | 历史施工单，已落地，勿再执行。绑定解释第 4 条作废，现行 harvest 见 `harvest_proposals` |

Windows 工作区里的 `D:\FlyBuddy\timesfm` 可能是过期副本。读/改本仓一律走 WSL：`wsl -d Ubuntu-22.04 -- bash -c "..."`。
