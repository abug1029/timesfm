<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-20 -->

# docs

## Purpose

人类可读运维与研究文档；回测实验注册表与固化判据的**文档真相源**。

## Key Files

| File | Description |
|------|-------------|
| **`praxist.md`** | **架构概览（先读）**：Praxist 本体 vs 三环；现行合同 |
| **`runbook_praxist_three_loop.md`** | **运维手册**：启停、429、队列/checkpoint、方案 A 收割、故障速查 |
| **`system_design.md`** | 系统设计全景：架构/数据流/协变量/评估/Praxist 三环 + TypeSafe 预筛 |
| **`README.md`** | 文档索引（分「在用 / 已归档」两段） |
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

## For AI Agents

### Working In This Directory

- 重跑 heavy WF 前先读 `./archive/history/backtest_registry.md`（已归档） 与 `STATE.md`。
- 固化门槛判据 v2 已归档（`./archive/history/validation_criteria.md`）；当前 Praxist 裁决以 v23 spec（`./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）为准；实现参考 `scripts/phase4d_parse_results.py` 的 `verdict()`。
- 更新文档时区分：**磁盘事实**（STATE/reports）vs 规划（plans）。
- Praxist：新人读 `praxist.md`；运维读 `runbook_praxist_three_loop.md`。`./archive/history/praxist_integration_plan.md` / `./archive/history/praxist_directive_design.md` 是历史方案（已归档），顶部有取代说明。
- Praxist 机器状态不在 STATE.md 独占：`data/cache/supervisor_state.json` + `task_FM/config/aligned_verdicts.jsonl`。

### Praxist 裁决口径 v23（Validation Criteria v2 已退役）

> 固化判据 v2 的 Rule1–Rule5（MaxDD 一票否决 / EV 翻正绿通等）已随 v23 退役出裁决链；旧文见 `./archive/history/validation_criteria.md`（已归档）。现行裁决口径唯一权威 = v23 spec `./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`：

- 硬门：n≥350、n_eff≥50（Bartlett）、dir_acc ≥ `effective_min`（`max(0.50, min(0.52, baseline_dir_acc))`）。新 verdict 落库这两字段；缺字段的历史行按「未知门槛」读，不要假设恒为 0.52。
- 统计裁决：DM 检验（Newey-West HAC + HLN）+ BH-FDR（per-symbol 多重校正；K<4 时降级固定 Bonferroni α=0.025）
- 裁决三态：`v2_pass` / `hard-gate-but-losing` / 变体级 `DEAD`（`materialize_known_verdicts`）。品种级探索状态另见 `task_FM/config/symbol_status.json`（`SYMBOL_DEAD` / `HOLD`），不要和变体级 DEAD 混名。
- PF/EV/MaxDD/IC：仅经济报表字段，不参与裁决

### Note on EV unit

monthly stdout 打印 **`EV_ratio=`**（无量纲）。文档中的 EV 案例多为该尺度，勿与 `evaluation_metrics["EV"]` 价格点混淆。历史日志可能仍出现 `EV=` 别名（`phase4d_parse_results` 二者同语义）。**EV 为经济报表字段，不参与 Praxist 裁决（v23）。**

## Dependencies

### Internal

- 产物目录：`reports/monthly_backtest/`、`reports/research/`、`reports/phase1/`

<!-- MANUAL: -->
