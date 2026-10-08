<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-20 -->

# docs

## Purpose

人类可读运维与研究文档；回测实验注册表与固化判据的**文档真相源**。


## Mandatory Pre-Action Reads

动手前扫一眼这张表——读完再改，省得改完被 evaluator 打回来。

| 你要改…… | 先读 |
|---------|------|
| 任何评估/门槛/统计口径 | [evaluation.md](./evaluation.md)（唯一权威） |
| 快环/慢环/监督环流程 | [runtime_contract.md](./runtime_contract.md) |
| 协变量/品种/数据表 | [data_dictionary.md](./data_dictionary.md) |
| 依赖/环境/入口命令 | [tech_stack.md](./tech_stack.md) |
| 术语含义/状态标志 | [glossary.md](./glossary.md) |

## Key Files

| File | Description |
|------|-------------|
| **`handbook.md`** | **入口（先读这个）**：5 分钟上手 + 按需阅读路径 + agent 硬约束 |
| **`evaluation.md`** | ⚠️ **阈值唯一权威**：n / n_eff / effective_min / DM / FDR / fail-closed。其他文档不得复述 |
| **`runtime_contract.md`** | 三环运行合同：goal DSL / 门判据 / 指纹 / family / 预注册 |
| **`glossary.md`** | 术语表（每条带代码锚点） |
| **`tech_stack.md`** | 依赖版本 / 环境 / 目录职责 / 入口命令 |
| **`data_dictionary.md`** | 品种集合 / 协变量族 / 数据表 / 防穿越 |
| **`praxist.md`** | 架构概览：Praxist 本体 vs 三环；方案 A 合同 |
| **`runbook_praxist_three_loop.md`** | **运维手册**：启停、429、队列/checkpoint、方案 A 收割、数据资产备份（同仓推 origin）、故障速查 |
| **`system_design.md`** | 系统设计全景：架构/数据流/协变量/评估/Praxist 三环 + TypeSafe 预筛 |
| **`run_artifacts.md`** | 运行产物分级 / 真相源隔离 / 清理流程 |
| **`README.md`** | 文档索引（按 L0 手册 / L1 规范 / L2 证据分层） |
| `family_boundary_rules.md` | 研究 family 边界规则（封账 / 成员上限 / T_max / p=1 范围） |
| `fingerprint_component_mapping.md` | spec 七组件 → 承载方映射（跨实现校验索引） |
| `supervisor_restart_backlog.md` | 重启待办（3 项：1 已实施 / 2 登记 / 3 已完成 2026-09-29） |
| `spec_hypothesis_driven_fast_loop_20260908.md` | 方案 A：peer 只写假设（提示词纪律已被 2026-09-19 跟进覆盖） |
| `2026-09-19-three-loop-followup-spec.md` | 三环跟进合同：自适应门可观测、两人议程、DEAD/HOLD |
| `three_loop_restart_protocol.md` | 重启清理协议（防 peer 被历史状态残留误导） |
| `2026-09-18-oi-gated-momentum-spec.md` | oi_gated_momentum 规格 —— **被 peer 提示词内嵌，改动影响生产提案面** |
| `runbook.md` | 日常运维（环境 / 采集 / 幽灵 K 线 / A2-P1 完整性工具） |
| `long-task-sop.md` | 长任务 SOP（回测 / 慢环操作规范） |
| `host_environment_assessment.md` | 宿主评估（顶部有 2026-09-09 WSL 迁移事实表） |
| `praxist_llm_env.md` | LLM 环境变量（Ark 主 / DashScope 备） |
| `copilot.md` / `paper_trading.md` | Copilot 用法 / 纸面闭环 |
| `product_positioning.md` / `module_freeze.md` / `param_hygiene.md` | 产品红线 / 子策略冻结 / 参数卫生裁决 |
| `research/slow_loop_evaluation_points_research.md` | 慢环评估点研究 |
| `superpowers/specs/` | 设计规格（v23 / spec v15 / praxist_control_plane / TypeSafe 预筛） |
| `superpowers/changelogs/` | 每轮实施 changelog —— **审计证据链，勿删勿归档** |
| `superpowers/reports/` | 核验报告（Stage 3 出口条件核验记录在此） |
| `archive/` | 已归档（见 `archive/README.md`；`superseded-2026-09/` 为 2026-09-29 归档的 27 份一次性文档） |
| ../loop-constraints.md | 循环强制约束（唯一可写区 / 预注册纪律） |

**新口径经济真相**: g005e 结果文件已不在仓内（原 `../reports/research/20260808_g005e_results.md`；Phase 11/12 后协变量已刷新）

## 行号引用纪律（D1，2026-10-08）

行号必然腐烂——实测现行契约文档行号引用仅 13% 正确（30 处 25 错），技术债清单自身写完 24 小时行号即失效（审计见 `superpowers/reports/2026-10-08-d1-line-reference-audit.md`）。规则：

- **现行契约文档**（本目录顶层 `*.md`、根目录 `*.md`、`task_FM/` 提示词与 AGENTS、各目录 `AGENTS.md`）**禁止行号引用**：不得写 `xxx.py:NN`、裸 `` `:NN` ``、`xxx.md:NN`。只写符号（`_dead_families()`）、文件路径，或**章节锚点**。
- **日期型文档**（`superpowers/**`、`research/`、`2026-MM-DD-*.md`）行号**不改**——那是写作当日的证据，改即篡改；但标题下必须有 `> **代码基线**: \`<short-sha>\`` 一行，复核用 `git show <sha>:<path> | sed -n 'NNp'`。
- 闸门：`python3 scripts/check_line_refs.py`；常备测试 `tests/test_doc_line_refs.py`，违规即红。

## For AI Agents

### Working In This Directory

- 重跑 heavy WF 前先读 `./archive/history/backtest_registry.md`（已归档） 与 `STATE.md`。
- 固化门槛判据 v2 已归档（`./archive/history/validation_criteria.md`）；当前 Praxist 裁决以 v23 spec（`./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）为准；实现参考 `scripts/phase4d_parse_results.py` 的 `verdict()`。
- 更新文档时区分：**磁盘事实**（STATE/reports）vs 规划（plans）。
- Praxist：新人读 `praxist.md`；运维读 `runbook_praxist_three_loop.md`。`./archive/history/praxist_integration_plan.md` / `./archive/history/praxist_directive_design.md` 是历史方案（已归档），顶部有取代说明。
- Praxist 机器状态不在 STATE.md 独占：`data/cache/supervisor_state.json` + `task_FM/config/aligned_verdicts.jsonl`。

### Praxist 裁决口径 v23（Validation Criteria v2 已退役）

> ⚠️ **阈值唯一权威 = [`./evaluation.md`](./evaluation.md)**。本节只留指针，不复述数字。
> 固化判据 v2 的 Rule1–Rule5（MaxDD 一票否决 / EV 翻正绿通等）已随 v23 退役出裁决链；
> 旧文见 `./archive/history/validation_criteria.md`（已归档）。
> 设计论证 = v23 spec `./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`。

- **硬门 / 统计裁决 / 裁决三态 / 退役字段** → 全见 [`./evaluation.md`](./evaluation.md)
- 品种级探索状态（`SYMBOL_DEAD` / `HOLD`）另见 `task_FM/config/symbol_status.json`——
  **不要和变体级 `DEAD` 混名**（两套状态机，见 `evaluation.md` §6）

### Note on EV unit

monthly stdout 打印 **`EV_ratio=`**（无量纲）。文档中的 EV 案例多为该尺度，勿与 `evaluation_metrics["EV"]` 价格点混淆。历史日志可能仍出现 `EV=` 别名（`phase4d_parse_results` 二者同语义）。**EV 为经济报表字段，不参与 Praxist 裁决（v23）。**

## Dependencies

### Internal

- 产物目录：`reports/monthly_backtest/`、`reports/research/`、`reports/phase1/`

<!-- MANUAL: -->
