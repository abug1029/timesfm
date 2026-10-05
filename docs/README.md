# FM_a 文档索引

面向人类操作者与下游接手者。AI 会话约定见根目录 `AGENTS.md` / `CLAUDE.md`；**当前门禁与待办以 `STATE.md` 为准**。

> **不知道从哪读起？→ [handbook.md](./handbook.md)（手册入口 + 按需阅读路径）**

## 分层结构

| 层 | 定位 | 规则 |
|----|------|------|
| **L0 手册层** | handbook · glossary · tech_stack · data_dictionary | 查"是什么/多少" |
| **L1 规范层** | system_design · runtime_contract · **evaluation** · runbook* · run_artifacts | 改代码前先查，改完同步 |
| **L2 证据层** | `superpowers/{specs,reports,changelogs,plans}` · `archive/` | 不合并、不重写，只链接 |

> ⚠️ **单一权威**：阈值只在 [evaluation.md](./evaluation.md) 定义，其他文档一律链接不得复述。
> 过时文档见 [archive/README.md](./archive/README.md)。

## L0 手册层

| 文档 | 内容 | 状态 |
|------|------|:----:|
| [handbook.md](./handbook.md) | **入口**：5 分钟上手 + 按需阅读路径 + agent 硬约束 | 在用 |
| [glossary.md](./glossary.md) | 术语表（每条带代码锚点） | 在用 |
| [tech_stack.md](./tech_stack.md) | 技术栈 · 依赖版本 · 环境 · 目录职责 | 在用 |
| [data_dictionary.md](./data_dictionary.md) | 品种 / 协变量族 / 数据表 / 字段 / 防穿越 | 在用 |

## L1 规范层

| 文档 | 内容 | 状态 |
|------|------|:----:|
| **先读这三份** | | |
| [system_design.md](./system_design.md) | 系统设计全景（数据流 + 模块依赖 + 评估口径） | 在用 |
| [runtime_contract.md](./runtime_contract.md) | **三环运行合同**：goal DSL / 门判据 / 指纹 / family / 预注册 | 在用 |
| [evaluation.md](./evaluation.md) | **评估口径唯一权威**：阈值 / n_eff / DM / FDR / fail-closed | 在用 |
| [praxist.md](./praxist.md) | 架构概览：Praxist 本体 vs 本仓三环、方案 A 合同 | 在用 |
| [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md) | **运维手册**：启停、429 failover、队列/checkpoint、方案 A 收割、故障速查 | 在用 |
| [run_artifacts.md](./run_artifacts.md) | **运行产物生命周期**：run 目录分级、真相源隔离、清理流程与保留策略 | 在用 |
| [../task_FM/AGENTS.md](../task_FM/AGENTS.md) | 任务包：手写合同 vs 运行产物、18 道提案门、evaluator 接口 | 在用 |

> ⚠️ **同名不同物**：[runtime_contract.md](./runtime_contract.md) 是三环运行合同；
> [`superpowers/specs/praxist_control_plane.md`](./superpowers/specs/praxist_control_plane.md)
> 是**资源控制 spec**（内存/cgroup · 429 · Session 解卡 · ghost `active_work`）。

### 规范层其余在用文档

| 文档 | 内容 | 状态 |
|------|------|:----:|
| **Stage 3 交付（2026-09-29 结案）** | | |
| [family_boundary_rules.md](./family_boundary_rules.md) | 研究 family 边界规则（90 天封账 / 20 成员上限 / T_max / p=1 适用范围） | 在用 |
| [fingerprint_component_mapping.md](./fingerprint_component_mapping.md) | spec 七组件 → 承载方映射（跨实现校验索引） | 在用 |
| [supervisor_restart_backlog.md](./supervisor_restart_backlog.md) | 重启待办（3 项：1 已实施 / 2 登记 / **3 已完成**） | 在用 |
| [superpowers/reports/2026-09-29-stage3-verification-record.md](./superpowers/reports/2026-09-29-stage3-verification-record.md) | §8.3 出口条件核验记录 | 在用 |
| [superpowers/specs/2026-09-24-covariate-research-credibility-design.md](./superpowers/specs/2026-09-24-covariate-research-credibility-design.md) | 上游 spec **v15** | 在用 |
| **2026-10-03 三环范式审计（未提交）** | | |
| [superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md](./superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md) | **Peer 记忆回路闭合**：死亡族名单 + 协议指纹回流给 peer（D2/D3 本轮）；拒收摘要（D1）与 `decision=abandon`（D4）待做。只改可见性，不改门判据 | 实施中 |
| [superpowers/reports/2026-10-03-three-loop-autoresearch-paradigm-audit.md](./superpowers/reports/2026-10-03-three-loop-autoresearch-paradigm-audit.md) | 四维定位代码级核实。**顶部有勘误节**：P0 三项经 spec 裁定后在飞计划禁止，已作废——读它之前先读勘误 | 在用（含勘误） |
| **2026-10-05 Peer 学习机制分析** | | |
| [superpowers/reports/2026-10-05-peer-learning-gap-analysis.md](./superpowers/reports/2026-10-05-peer-learning-gap-analysis.md) | **Peer 学习断裂**：225 cycle 结果未回传，peer 每次提案 = 盲猜。Cross-run feedback channel 未实现 | 在用 |
| **Praxist 三环合同** | | |
| [spec_hypothesis_driven_fast_loop_20260908.md](./spec_hypothesis_driven_fast_loop_20260908.md) | 方案 A 设计：peer 机制化假设作者（提示词纪律以 2026-09-19 为准） | 在用 |
| [2026-09-19-three-loop-followup-spec.md](./2026-09-19-three-loop-followup-spec.md) | 跟进合同：门控可观测、两人议程、DEAD/HOLD、去重 | 在用 |
| [three_loop_restart_protocol.md](./three_loop_restart_protocol.md) | 重启清理协议：避免 peer 被历史状态残留误导 | 在用 |
| [2026-09-30-dead-code-purge-spec.md](./2026-09-30-dead-code-purge-spec.md) | 死代码清理 Spec（v2 修订，已批准执行） | 在用 |
| [loop-constraints.md](../loop-constraints.md) | 循环强制约束（唯一可写区 / 预注册纪律） | 在用 |
| **日常运维** | | |
| [runbook.md](./runbook.md) | 环境、采集、幽灵 K 线、单测、A2-P1 完整性工具、故障排查 | 在用 |
| [long-task-sop.md](./long-task-sop.md) | 长任务 SOP（回测/慢环操作规范） | 在用 |
| [host_environment_assessment.md](./host_environment_assessment.md) | 宿主评估（顶部有 2026-09-09 WSL 迁移事实表） | 在用 |
| [2026-09-17-claude-dual-system-path-map.md](./2026-09-17-claude-dual-system-path-map.md) | Claude Code 双系统 PATH 关系图与排查手册（Windows 主机 + WSL 宿主） | 在用 |
| [praxist_llm_env.md](./praxist_llm_env.md) | LLM 环境变量（Ark 主 / DashScope 备） | 在用 |
| **产品与卡面** | | |
| [copilot.md](./copilot.md) | 主观领航员用法与报告说明 | 在用 |
| [paper_trading.md](./paper_trading.md) | 纸面闭环：Copilot → ledger → 回填 → 健康表 | 在用 |
| [product_positioning.md](./product_positioning.md) | **产品定位**：可交易方向=加权1H；辅助非自动 | 在用 |
| [module_freeze.md](./module_freeze.md) | 子策略冻结（Vol OFF / A2 关 / Regime 研究-only） | 在用 |
| [param_hygiene.md](./param_hygiene.md) | 参数卫生裁决记录 | 在用 |
| [research/slow_loop_evaluation_points_research.md](./research/slow_loop_evaluation_points_research.md) | 慢环评估点研究 | 在用 |
| **历史（已归档，勿作当前口径）** | | |
| [archive/history/vol-risk.md](./archive/history/vol-risk.md) | Vol 风控 / R1 / L1 经济结论与红线 | 已归档 |
| [archive/history/validation_criteria.md](./archive/history/validation_criteria.md) | 固化判据 v2（已随 v23 退役出裁决链） | 已归档 |
| [archive/history/backtest_registry.md](./archive/history/backtest_registry.md) | 历史协变量实验目录 | 已归档 |
| [archive/superseded-2026-09/](./archive/superseded-2026-09/) | **2026-09-29 归档**：27 份一次性调查/阶段核验/已执行计划 | 已归档 |
| [archive/superpowers-plans/](./archive/superpowers-plans/) | 已执行的历史施工单 | 已归档 |
| [archive/](./archive/README.md) | 归档总入口（含各子目录说明） | 已归档 |

> **协变量规格仍是在用文档**：[2026-09-18-oi-gated-momentum-spec.md](./2026-09-18-oi-gated-momentum-spec.md)
> ——它被 peer 提示词直接内嵌，改动会影响生产提案面。

Goal / 运行口径：`scripts/praxist_goal.yaml`（2026-09-23 起目标=24 品种全部通过三阶段验证，成功条件见 [praxist.md](./praxist.md)）。

### 2026-08-08 新口径 rebaseline（必读）

> **历史口径（v2 PF/星级，2026-08 回测）**：本节数字非 v23 证据，裁决以 v23 裁决链（DirAcc/MAPE + DM + BH-FDR）为准。

| 文件（**均已不在仓内**，历史指针） | 内容 |
|------|------|
| `reports/research/20260808_g005e_results.md` | **20 品种全表** PF/星级（bar-exact + signal_weight）；结果文件已清理，裁决口径以 v23 spec 为准 |
| `reports/research/20260808_tradable_alpha_final_score.md` | 可交易 alpha 健康度 6.7/10 |
| `reports/research/20260808_conflict_debt_register.md` | 冲突债 CF-01…25 裁决 |

## 30 秒上手

```bash
cd /home/abug/timesfm
source .venv/bin/activate

# 盘中主观（推荐）
python scripts/copilot.py ss fu

# 生产级联预测（默认无 vol 压平）
python scripts/cascade_predict.py ss

# 数据卫生
python scripts/data_management.py --daily --1h
python -m data.future_bar_guard --dry-run

# Praxist 三环（监督环；密钥只进 .env.praxist）
# 架构见 docs/praxist.md；细节见 docs/runbook_praxist_three_loop.md
scripts/start_supervisor.sh
```

## A2 轨道（2026-08-07 结案，Track B 已关闭）

**结论**：A2-P1.1 定向修复 **0/5 GO**；A2-P2 残差叠加 **0/5 GO**（stacked PF 全部 < 1.0，
且低于 scheme PF）→ **Track B 关闭**。LGBM 路径（`cascade/lgbm_features.py`）**已于 2026-09-30 git mv 归档**
（`cascade/archive/2026-09-30-a2-retired/`，CF-13 + 裁定 e）；venv 未装 pyarrow/fastparquet。

> 上述两个数字为 **v2 历史口径**（2026-08 PF/星级回测），**非 v23 证据**。现行裁决口径唯一权威 =
> v23 spec + `task_FM/config/aligned_verdicts.jsonl`。
>
> 原「磁盘事实来源」（`reports/a2_p1_manifest.json`、`reports/research/20260807_a2_p2_verdict.md`）
> **已不在仓内**，故本节不再重述逐品种明细表。

### 对账工具（**2026-09-30 已归档**，仅历史参考）

⚠️ **原路径已失效**。工具实际位置：
`scripts/archive/2026-09-30-a2-retired/a2_p1_restore_manifest.py`

<details>
<summary>展开历史命令（需自行加 archive 前缀才可运行）</summary>

```bash
A2=scripts/archive/2026-09-30-a2-retired/a2_p1_restore_manifest.py
python "$A2" --dry-run       # 扫描主/备份目录，打印 20 品种状态
python "$A2" --canonicalize  # 对重复写入的 JSONL 去重
python "$A2" --restore       # 从备份恢复缺失文件
```

</details>

详见 [runbook.md](./runbook.md) "A2-P1 完整性工具" 章节（同已归档标注）。

## 当前生产姿态

- **Neutral / Absolute Risk Overlay：默认 OFF**（全宇宙经济门禁未过）
- **Copilot：预警-only**，不改变预测数值。卡面「可交易方向」= `position_from_forecast`（加权 1H）；日线只作 `regime_direction`
- **级联/回测/Copilot 可交易方向** = `position_from_forecast`（加权 1H）；见 [product_positioning.md](./product_positioning.md)
- **无真实 3 星**；`--three-star` = 信用≥2 星列表
- **Phase 11（2026-08-21 结案）**：12 品种协变量替换固化（SS/SP/FU/I/RB/TA/EG/CJ/LH/JD + 3 基线保持 M/P/SR），34 GREEN
- **Phase 12（2026-08-21）**：BU 组合协变量 `calendar_cyclical+hourly_slope` 固化。该 PF=1.01 边际 GREEN 结论属 v2 历史口径（2026-08 月度回测），非 v23 证据；v23 下以 aligned verdicts 为准
- 经济表与信用档（v2 历史口径）：见上表 g005e（结果文件已不在仓内；Phase 11/12 后协变量已刷新）；v23 裁决以 aligned verdicts 为准（口径见 [praxist.md](./praxist.md) 与 v23 spec）；运维细节见 [vol-risk.md](./archive/history/vol-risk.md)（已归档）与 `STATE.md`
- **Praxist 三环**：方案 A 运行中。**活计数（`cycles_done` / PID / phase）一律读 `data/cache/supervisor_state.json`，本文档不记录快照** —— 2026-09-29 曾在此钉住 `cycles_done=36` / PID 31638，一周内即失效。架构 [praxist.md](./praxist.md)，运维 [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md)，现场快照见 `STATE.md`

## 维护协议

- **唯一权威源**：WSL `/home/abug/timesfm/`（git repo `abug1029/timesfm`）
- **Windows 副本**：无 —— 2026-09-29 核实 `D:\FlyBuddy\FM_a\` 与 `D:\FlyBuddy\timesfm\` 在 Windows 侧均已不存在，旧指引作废；一切读写走 WSL 仓
- **新增文档流程**：在 WSL 侧创建 → 更新 `docs/README.md` 索引 → `docs/AGENTS.md` 路由 → git commit/push
- **system_design.md 更新触发**：架构变更 / 新模块上线 / 评估口径切换 / 品种状态变更 / 星级调整
- **会话结束前**：运行 `/neat-freak` 检查文档与代码一致性
- **不归集**：`D:\FlyBuddy\shared\timesfm\`（独立模型库项目）、`D:\FlyBuddy\docs\`（工作区级文档）
