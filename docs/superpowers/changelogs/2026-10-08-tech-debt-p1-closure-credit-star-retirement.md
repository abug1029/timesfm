# 技术债 P1 收口 + 信用档退役 + 品种宇宙对齐

> **日期**: 2026-10-08
> **分支**: master（工作目录 `/root/timesfm`，WSL Ubuntu-24.04）
> **输入**: `reports/2026-10-07-tech-debt-inventory.md`（P1 L2/L3/L4 + P3 D2）+ 信用档/宇宙专项调研
> **回归**: 基线 `71F/1427P/44E` → `69F/1434P/41E`，**新增失败 0，已消除 5**

## 做了什么

| # | 项 | 内容 |
|---|---|---|
| 1 | **L2** | `_has_prior_failure` 单键 OR → `(symbol, cov)` 配对 AND |
| 2 | **L3** | 目标品种集单源化到 `praxist_goal.yaml`；`ALLOWED_SYMBOLS` 从 yaml 派生 |
| 3 | **L4** | cadence 默认值单源化（`_CADENCE_DEFAULTS` + `_cad_int`） |
| 4 | **D2** | `n_one_star_symbols_hit` → `n_goal_symbols_hit`；`tier_classifier` 加口径注 |
| 5 | **债 2（C+a）** | 删除 v1 legacy 复测判据（`ic`/`ev`/`pf_ratio`）+ 去掉 `INCUMBENT_PF` 静默兜底 |
| 6 | **债 1** | `V23_RETEST_PENDING` 移出生产模块 → 文档台账 |
| 7 | **信用档退役** | `scheme.stars` / `list_by_stars()` / KB `credit_stars` 全部删除；信心分级改由 L1 PF/EV 派生 |
| 8 | **归档** | `two_star_critic.py` / `two_star_candidate_runner.py` → `scripts/archive/2026-10-08-credit-star-retired/` |
| 9 | **品种宇宙** | `target_symbols` 删 `sc` 增 `jm`；两套集合归一为同一 24 个 |

## 核实与勘误

逐条对照代码核实后，多处发现比清单描述的更深：

- **L3 的漂移不止一处** —— 目标品种集原有**三份**副本：yaml(24) / `GOAL_SYMBOLS_SET` 硬编码(9) / `build_snapshot` 内 `TARGET_SYMBOLS` 硬编码(24)。
- **旧 9 个集合从来不是信用星集合** —— 它自称「1★ 信用品种」，但实测 1★ 恰 14 个、≥2★ 7 个，与任何一档都对不上，是**第三套独立口径**。
- **L4 范围更大** —— `aligned_max_points` 在同一文件三处互相矛盾（签名 600 / 复测处 600 / 收割处 **400**），yaml 是 600。
- **D2 的 `star` 说法只对了一半** —— verdict 上的 `star` 字段确实自始不存在，但品种信用星是**活跃子系统**（`config/prediction_scheme.py::SCHEMES[].stars` → `credit_stars`，CF-10 A 锁定唯一源），文档里 `list_by_stars(2)` / `1★` 全是正确术语。**若照单全清会删掉活跃子系统。**

## 债 2：为什么是 C+a 而不是只加守卫

完整链路：

```
ECONOMIC_VERDICT.json（L1 经济判决）不存在
  → knowledge_base.json 全表 PF/EV 降级为 null（该降级状态被提交进了 git）
  → INCUMBENT_PF 恒空 {}
  → ratio = pf / INCUMBENT_PF.get(sym, 1.0)  ← 分母恒为 1.0
  → 「PF 相对 incumbent 超 105%」被静默改写成「PF 绝对值 > 1.05」
```

**这不是 no-op，而是静默的语义替换**：incumbent PF=3.0、现已退化到 PF=1.2 的裁决照样会被排进复测队列 → 过度复测。且因 KB 是静态提交产物，**永不自愈**。

两条删除理由各自独立成立：(1) 指标已退役 —— evaluator 契约明写「PF/EV/MaxDD 已退役」；(2) 分母已损坏 —— 上述改写。故删门而非只加守卫。

## 信用档退役：方案 A 与四条证据

四条证据任一独立成立：零决策参与（supervisor/aligned_slow_loop 从不读）/ 自我声明脱钩（docstring 写明冻结于 2026-08 v2 口径且「不得作为 v23 证据引用」）/ 服务目标不可达（2026-08-03 结论「3 星不可达，DirAcc 天花板 ~58%」）/ 被"唯一事实源"固化成陈旧值（CF-10 A 钉死后，L1 证据 0/21 全缺失时仍输出 1~3 星）。

新分级 `evidence_grade(historical_pf, historical_ev)`：

| 档位 | 判据 |
|------|------|
| `no_evidence` | L1 缺失或无 PF（显式暴露） |
| `solid` | PF ≥ 1.20 且 EV > 0 |
| `positive` | PF ≥ 1.05 且 EV > 0 |
| `negative` | 有 PF 但不达门槛 |

**当前实测 21 品种全部 `no_evidence`** —— 这是事实陈述而非缺陷。原来正是 `credit_stars` 在 PF 全 null 时仍给 1~3 星掩盖了这一点。

**保留**：`prediction_scheme.py` 的全部固化预测参数（`covariate_type` 33 处引用 / `dir_acc` 19 / `scheme_type` 18 / `short_horizon_only` 14 / `confidence_multiplier` 12 等）—— 生产参数不是评级。

**不归档 `three_star_predict.py`**：它提供 `ensure_data`，被 `cascade_predict` / `predict` / `data_validator` 生产路径依赖。只去星级化：`run_all_three_star` → `run_all_schemes`（改跑全部固化品种），文件名 `*_three_star.md` / `three_star_progress.log` 保持不变以兼容既有产物路径。

## 品种宇宙对齐

对齐前 `target_symbols`(24) 与 `ALLOWED_SYMBOLS`(21) 双向割裂：

- `oi`/`px`/`y` 是攻坚目标却被准入门挡死 —— **goal 要求它们达标，却无法为它们产出任何候选**
- `jm` 能过门但不被 goal 统计（孤儿品种）

裁定：yaml 为唯一来源，evaluator 从它派生（fail loud）；删 `sc`、增 `jm`；归一为同一 24 个。

**`sc` 未被连带删除** —— 它仍是 `fu`/`bu` 裂解价差的原料输入（`config/crack_spread_pairs.py`），那是数据依赖不是研究目标。

守卫 `tests/test_symbol_universe_20261008.py`（11 例）断言两套恒等，并禁止 `ALLOWED_SYMBOLS` 退回内联字面量。

## 顺带修复

`copilot.py` 顶层 `from scripts.cascade_predict import TICK_SIZE` 会拉进 `sklearn`，导致建议措辞/证据分级/Markdown 渲染这些**纯逻辑**在缺可选 ML 依赖时不可用也不可测。改为惰性取用 + 优雅降级，顺带让 3 个 `test_copilot_*` 从 collection error 变为可运行。

## CLI / 接口变更

| 变更前 | 变更后 |
|--------|--------|
| `copilot.py --three-star` | `--evidence {solid\|positive\|negative\|no_evidence}` |
| `three_star_predict.run_all_three_star()` | `run_all_schemes()` |
| KB 字段 `credit_stars` / `scheme_stars` | `evidence_grade` |
| snapshot 字段 `n_one_star_symbols_hit` | `n_goal_symbols_hit` |
| `sup.RETEST_PF_RATIO` / `RETEST_GATE_IC` / `INCUMBENT_PF` | 已删除（`RETEST_GATE_N` 保留） |

## 新增测试

- `tests/test_tech_debt_20261008.py`（12 例）—— L2 配对语义、L3 单源与 fail loud、L4 默认值一致
- `tests/test_symbol_universe_20261008.py`（11 例）—— 宇宙恒等、`sc` 移除、`jm` 补齐、`oi/px/y` 准入
- 既有测试改写：`test_retest_candidates_rejects_v1_legacy_rows` / `test_retest_gate_constants_retired`（债 2）、`test_legacy_kb_without_grade_is_treated_as_no_evidence`（信用档退役）

## 生效条件

- L2 / L3 / L4 / 债 2 均改 `scripts/praxist_supervisor.py` 与 evaluator → **需一次 supervisor 重启生效**
- **协议指纹不动**：L2/L3/L4 属准入/goal 语义，verdict 行 schema 未变；债 2 是删除判据而非改阈值
- **L2 是本批唯一实质放宽准入门的一条**，建议重启后观察一轮 `no_failure_delta` 拒收分布再确认

## 遗留

- **L1 `ECONOMIC_VERDICT.json` 仍不存在** → 21 品种信心分级全为 `no_evidence`。产出该文件后需重建 KB 才能转真档位
- `train_regime_model.py` 有一处过时注释提及「排除 stars=0 品种」，其功能本就与星级无关，未改
- 历史 spec 与归档代码内的 star 字样按审计痕迹保留