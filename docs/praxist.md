# Praxist 在 FM_a 里做什么

面向第一次接触本仓 Praxist 的人：五分钟搞清**它是什么、怎么转、读哪份文档**。运维命令、故障表、启停细节见 [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md)。

| 你想… | 去哪 |
|---|---|
| 理解架构与合同 | 本文 |
| 启停 / 429 / 队列 / 复测 | [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md) |
| 快环现行合同（方案 A） | [spec_hypothesis_driven_fast_loop_20260908.md](./spec_hypothesis_driven_fast_loop_20260908.md) |
| LLM 环境变量 | [praxist_llm_env.md](./praxist_llm_env.md) |
| 宿主容量与内存硬顶 | [host_environment_assessment.md](./host_environment_assessment.md) |
| 机器状态 / 裁决 | `data/cache/supervisor_state.json`、`task_FM/config/aligned_verdicts.jsonl` |
| 目标与预算 | `scripts/praxist_goal.yaml` |

**不要改** `.praxist-venv` 里的 Praxist 源码（升级会丢）。本仓只通过任务包、提示词和外层监督环适配。

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

CLI：`praxist start|resume|stop|status|monitor|doctor|resolve`。本仓入口是 `.praxist-venv/bin/praxist`。

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

合同：`schema=fm.hypothesis_proposal.v1`，`mechanism` ≥40 字（禁模板）、`symbol_fit`、预注册 kill/promote。只许提议协变量池里 **active** 的项（`task_FM/config/covariate_pool.json`，目前 30 个、9 个族）。新指标写 `new_cov_<name>.json`，进 backlog，不入评估队列。

### 监督环

每 300 秒 tick：

1. 用 `scripts/praxist_goal.yaml` 的 DSL 判定成功 / 预算
2. 配额窗够才 `praxist start` / `resume`；429 则 stop，解封后 **resume 同一 run**（禁止开新 run）
3. run 结束后 `harvest_proposals`：校验 → 去重 → 分层选座 → 入慢环队列
4. 有货立刻拉慢环
5. 物化 `known_verdicts.inc.md` 与 `covariate_menu.inc.md`，喂给下一代

选座（`survivors_per_cycle=3`）：目标 1 星且 n≥350 → 1 星欠样本（cj/lh）→ 其余；同层再按协变量族正交填。

近失误自动复测：裁决只差样本（n<350 但 ic≥0.05、ev>0、PF 比现任好 5%）时，本地库长到 ≥350 就补队，checkpoint 只算新点。首个候选 `cj_oi`（n=324）。

### 慢环

消费队列，跑 `monthly_backtest.py` 全量 walk-forward。硬门预注册在 `config/praxist_task.yaml`：

- n ≥ 350
- IC ≥ 0.05（ic = 2×|dir_acc−0.5|）
- 扣滑点 EV > 0
- 主指标 `ev_after_slippage`，PF 为次

日线预测按 `(symbol, cutoff, 窗口, 模型指纹)` 缓存（日线模型不吃协变量）。队列 claim / inprogress / recover，kill 后零损失。**只有慢环能写** `task_FM/config/aligned_verdicts.jsonl`。伪造 verdict = 破坏预注册纪律。

---

## 4. 当前目标与现场（2026-09-09）

成功条件（`scripts/praxist_goal.yaml`）：

- 1 星集合 `{m, ss, sr, cj, jd, lh, eg, rb}` 里至少 4 个过门
- 过门策略相对现任 PF 比 > 1.05
- 至少 1 个协变量族
- 预算：20 cycles / 30 CPU 小时 / 80M token 增量 / 截止 2026-09-20

磁盘快照（监督环已于 2026-09-09 10:54 有序 SIGTERM，为重启电脑）：

- `phase=slow`，`cycles_done=6`，队列空
- 20 条 unique 裁决；**经济意义上过门的实质只有 `ss_vor`**（n=396，PF=1.123，ev=+11.06，ic=0.06）
- `i_oi` 被标了 `gate_pass=True` 但 ev=−2.46：硬门只判 n+ic，materializer 未区分「过硬门」与「过硬门但亏钱」，对 peer 有误导（待修）

重启：

```bash
cd /home/abug/timesfm
set -a && source .env.praxist && set +a
setsid nohup .praxist-venv/bin/python scripts/praxist_supervisor.py \
  --goal scripts/praxist_goal.yaml \
  >> data/cache/supervisor.out 2>&1 < /dev/null &
```

`task_FM/task.yaml` **不要**放明文 API key；密钥只进 `.env.praxist`。

---

## 5. 效率改造已经落地的 / 还没动的

已落地：

1. 取消诊断档评估（快环 0 次模型加载）
2. 日线预测缓存（慢环候选之间复用）
3. 1 星优先选座
4. n 不足近失误自动复测
5. 429 后 resume 同一 run；Ark 主 / DashScope 备

预测链本身的性能债（重复 `compile`、连接泄漏、Hurst 循环等）记在 [audit_system_efficiency_20260908.md](./audit_system_efficiency_20260908.md)，与编排是两条线。

明确非目标：不改 Praxist 核心、不做 GPU/多机并行、监督环无出站通知（会话级监控随 Agent 会话消失）。

---

## 6. 历史文档怎么读

| 文档 | 地位 |
|---|---|
| [praxist_integration_plan.md](./praxist_integration_plan.md) | 2026-09-01 方案稿，P0–P3 已落地；路径 `/root/timesFM_fu` 过时 |
| [praxist_directive_design.md](./praxist_directive_design.md) | 指令闭环仍有效；peer 跑 diagnostic 评估已被方案 A 取代 |
| [praxist_peer_evaluation_fix.md](./praxist_peer_evaluation_fix.md) | 方案 A 的动机（诊断 PF 不可信） |
| `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | 三环原始 spec；与现行冲突时以 runbook「Spec 绑定解释」为准 |

Windows 工作区里的 `D:\FlyBuddy\timesfm` 可能是过期副本。读/改本仓一律走 WSL：`wsl -d Ubuntu-22.04 -- bash -c "..."`。
