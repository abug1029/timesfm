# Task 1：文档权威链与矛盾矩阵

- 任务：`docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 1
- 仓：WSL `/home/abug/timesfm`（不把 `D:\FlyBuddy\timesfm` 当真相源）
- 审核日：2026-09-11
- 范围：只审文档权威、日期字段、合同矛盾；不改生产代码，不启动 Praxist
- 模式：先按计划做完 7 对必查矛盾，因 Important ≥3 条，后半段按「有隐藏问题」加严，额外核对了 `m_ccl`、预算字段、STATE 死链、`n=588`

**结论先说：** 权威链本身能用。磁盘和 `loop-constraints.md` 在 IC 公式、可交易方向、Vol 默认 OFF、方案 A（peer 不评估）上是对齐的。真正危险的是：2026-09-10 的 `docs/system_design.md` 看起来比 `product_positioning.md` 新，却把已经被更高权威否决的日线主方向、Pearson IC、含 EV 的 `gate_pass` 写成可复制示例；`STATE.md` 的人类快照停在 2026-09-09，磁盘已经不是那天的状态。这些是文档债，不是「代码现在按日线斜率在下单」。

---

## 1. 权威链（谁覆盖谁）

冲突时按下表，**后者不得推翻前者的磁盘事实**。本任务的裁决全部按此执行。

| 层 | 文件 | 角色 | 覆盖范围 |
|----|------|------|----------|
| 1 | `STATE.md` + 磁盘产物 | canonical_state | 系统状态、过门事实、生产姿态。Praxist 机器事实另见本文件自述：以 `data/cache/supervisor_state.json` 与 `task_FM/config/aligned_verdicts.jsonl` 为准 |
| 2 | `loop-constraints.md` | 现行合同 | 红线路径、方案 A、预注册最终裁决口径、IC 公式原文 |
| 2 | `config/praxist_task.yaml` | 现行合同（部分过期） | 预注册指标名、min_samples/min_ic、full_walkforward 的 gate 列表；**仍残留 diagnostic 段** |
| 2 | `config/backtest_config.py` | 现行合同 | `STEP=2`、`EVAL_WINDOW_BARS=1200`、滑点 |
| 2 | `config/prediction_scheme.py` `SCHEMES` | 现行合同 | 生产协变量；**过门 ≠ 已固化** |
| 3 | `docs/praxist.md` + `docs/runbook_praxist_three_loop.md` | 现行合同 | 三环架构、方案 A、运维 |
| 3 | `docs/product_positioning.md` | 现行合同 | CF-01 A 可交易方向、产品红线 |
| 3 | `docs/validation_criteria.md` | 现行合同（另一套门） | SCHEMES 固化 v2（MAPE/DirAcc/PF + MaxDD），**不是** Praxist `gate_pass` |
| 3 | `docs/module_freeze.md` | 现行合同 | Vol/A2/Regime 冻结 |
| 4 | `docs/system_design.md` | derived_view / 关键条款过期 | 2026-09-10 写成「完整设计」，若干核心合同与层 1–3 冲突 |
| 5 | `docs/superpowers/specs/` 现行 | 现行规格 | 以 2026-09-10 hardening 与已 merge 的 critical-fixes 为准（本任务不展开，交 Task 3） |
| 6 | `docs/research/`、更早 spec/plan、`docs/praxist_integration_plan.md` | 历史方案 | 可解释来源，不得当活合同 |

**裁决规则（本任务）：**

1. 磁盘 JSONL / `supervisor_state.json` / `SCHEMES` / `backtest_config.py` 的数字，压过任何「当前快照」散文。
2. `loop-constraints.md` 的 `ic=2×|dir_acc−0.5|` 压过 `system_design.md` 的 Pearson。
3. `docs/product_positioning.md` CF-01 A 压过 `system_design.md` §5.1/§8 的日线主方向。
4. `gate_pass` 布尔值以磁盘 + `evaluator.gate()` 为准；「最终裁决 / 经济过门」是另一层（`ev>0` + PF 比），不要和 `gate_pass` 混名。
5. 文档过期 ≠ 代码 bug。代码若已按更高权威实现，只记文档债。

---

## 2. 文档角色表

| 文件 | 角色 | 依据 |
|------|------|------|
| `STATE.md` | canonical_state（自声明）+ 一截过期 derived_view | L3–L5 自称为唯一事实所有者；L28 又把 Praxist 机器事实让给磁盘。§PRAXIST 快照（L26–38）是 2026-09-09 的 derived_view，已落后 |
| `task_FM/config/aligned_verdicts.jsonl` | canonical_state（Praxist 裁决） | 不在 git；26 行；`gate_pass`/`n`/`ic` 的真相源 |
| `data/cache/supervisor_state.json` | canonical_state（监督环） | 不在 git；当前 `phase=fast`，`cycles_done=1` |
| `loop-constraints.md` | 现行合同 | IC 公式、方案 A、verdict 唯一写者 |
| `config/praxist_task.yaml` | 现行合同 / 局部历史残留 | 指标与 min_n/min_ic 仍有效；`stage: diagnostic` 是方案 A 之前的梯子 |
| `config/backtest_config.py` | 现行合同 | git `ee1f176`（2026-09-10）`STEP=2` |
| `config/prediction_scheme.py` | 现行合同 | SS 生产协变量仍是 `calendar_cyclical` |
| `docs/praxist.md` | 现行合同 | 方案 A 人类概览；现场数字复制了 STATE 快照，同样过期 |
| `docs/runbook_praxist_three_loop.md` | 现行合同 | 运维；写明「Spec 绑定解释优先于过时 spec 句」 |
| `docs/product_positioning.md` | 现行合同 | CF-01 A，短而有效 |
| `docs/module_freeze.md` | 现行合同 | CF-12 A Vol 永不默认 ON |
| `docs/validation_criteria.md` | 现行合同（SCHEMES 固化） | v2 2026-07-30；与 Praxist 硬门不是同一扇门 |
| `docs/system_design.md` | derived_view，关键条款过期 | 版本 1.0（2026-09-10）；附录网格已改 STEP=2，但方向/IC/gate/SS 示例与层 1–3 冲突 |
| `docs/README.md` | derived_view（索引） | 索引有用；「当前生产姿态（2026-08-21）」标题过期 |
| `docs/AGENTS.md` | derived_view | 2026-09-09 更新过；EV 单位注仍有效 |
| `AGENTS.md` / `CLAUDE.md` | derived_view（给代理） | 方向/方案 A/Vol OFF 与层 3 一致；硬门句子仍写成含 EV；`AGENTS.md` 残留 `timesFM_fu` |
| `scripts/praxist_goal.yaml` | 现行合同（目标/预算） | git `ee1f176` 已改无限预算；文件头注释仍像 2026-09-06 的 15GiB 盒子 |
| `docs/praxist_integration_plan.md` | 历史方案 | 顶部 2026-09-09 取代说明有效；正文 `/root/timesFM_fu` 仍在 |
| `docs/praxist_directive_design.md` | 历史方案（指令闭环仍部分有效） | 顶部已声明 diagnostic 被方案 A 取代 |
| `docs/praxist_peer_evaluation_fix.md` | 历史方案 / 状态字段撒谎 | 方案 A 的动机文；状态仍写「待执行」 |
| `docs/spec_hypothesis_driven_fast_loop_20260908.md` | 现行快环合同 | 状态「已实施」 |
| `docs/research/slow_loop_evaluation_points_research.md` | 历史研究（交 Task 4） | 状态仍「待执行修复」；代码侧 STEP=2 已落地 |
| `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | 历史 spec（交 Task 3） | runbook L192：绑定解释优先于过时 spec 句 |

---

## 3. 日期与状态字段

对照：`git log -1 --format=%ci`（工作区）以及 `STATE.md` 头「最后更新: 2026-09-09」。计划规则：任何「当前」口径早于 2026-09-09、且没有后文取代声明的，标 Important。

| 文件 | 文内日期/状态 | git 最后提交 | 判定 |
|------|----------------|--------------|------|
| `STATE.md` | 最后更新 **2026-09-09**；Praxist 快照 2026-09-09 | 2026-09-10 06:23 `ee1f176`（只追加一条 budget_exhausted 链接，**没改快照表**） | Important：头日期和快照都落后于磁盘 |
| `loop-constraints.md` | 方案 A 修订 2026-09-08 | 2026-09-09 11:22 | 现行 |
| `docs/praxist.md` | §4 现场 2026-09-09 | 2026-09-09 14:27 | 合同现行，现场数字过期 |
| `docs/runbook_praxist_three_loop.md` | 方案 A 2026-09-08；宿主 7.7 GiB | 2026-09-09 14:27 | 现行 |
| `docs/product_positioning.md` | 裁决 2026-08-08 | 2026-09-03 初始提交 | 合同仍有效，不是「当前快照」 |
| `docs/module_freeze.md` | 裁决 2026-08-08 | 2026-09-03 初始提交 | 同上 |
| `docs/validation_criteria.md` | v2 2026-07-30 | 2026-09-03 初始提交 | SCHEMES 固化合同仍被 `docs/AGENTS.md` 引用 |
| `docs/system_design.md` | 版本 1.0 **2026-09-10** | 2026-09-10 14:58 `a1b298f` | 日期新，关键合同旧 |
| `docs/README.md` | **当前生产姿态（2026-08-21）**；同节有 2026-09-09 补丁句 | 2026-09-09 14:27 | Important：标题日期未改 |
| `docs/AGENTS.md` | Generated 2026-08-08 \| Updated 2026-09-09 | 2026-09-09 14:27 | 可用 |
| `AGENTS.md` | 生产红线（**2026-07-27**）；Praxist 节 2026-09-09 | 2026-09-09 14:27 | 红线内容仍对；日期字段旧 |
| `CLAUDE.md` | Praxist 现行合同 2026-09-09 | 2026-09-11 08:36 | 代理文档里最新 |
| `config/praxist_task.yaml` | P0a 2026-09-01 | 2026-09-03 初始提交 | 方案 A 后未改 |
| `config/backtest_config.py` | 无文内「当前」戳 | 2026-09-10 06:23 | 现行网格 |
| `scripts/praxist_goal.yaml` | 头注释 2026-09-06 / 15GiB；成功条件 2026-09-09 | 2026-09-10 06:23 预算改无限 | 预算以磁盘为准 |
| `docs/praxist_integration_plan.md` | 日期 2026-09-01；状态「已实施」；顶部 2026-09-09 取代说明 | 2026-09-09 14:27 | 历史，有横幅 |
| `docs/praxist_peer_evaluation_fix.md` | 日期 2026-09-08；**状态: 待执行** | （本任务未再挖 git） | 状态撒谎：方案 A 已上线 |
| `docs/research/slow_loop_evaluation_points_research.md` | 2026-09-09；**状态：待执行修复** | 交 Task 4 | 号召过期 |

`ee1f176` 提交说明写了「预算无限制」和 `STEP 24→2`，但 `STATE.md` 只加了 L645–647 一条事件链接，快照表 L34 仍是「预算 20 cycles / 30h CPU / 80M token / 2026-09-20」。

---

## 4. 矛盾矩阵（计划要求的 7 对）

每行：文档 A 原文、文档 B 原文、磁盘/代码事实、判定。权威层 1–2 赢。

### 4.1 可交易方向：日线斜率 vs 加权 1H

| 侧 | 原文 |
|----|------|
| A `docs/product_positioning.md` L15–20 | 「可交易方向（CF-01 A）」=`sign(weighted_1H − base)` via `signal_weight`；「日线状态」=`daily_slope` vs `trend_threshold_pct`，**仅副标签** |
| A `STATE.md` L120 | 「可交易方向=加权1H」 |
| A `AGENTS.md` L304 | 「可交易方向 = 加权 1H（`cascade/signal_contract`），日线斜率仅为 regime 副标签」 |
| B `docs/system_design.md` L313–329 | `_compute_direction(horizon_slope)`「基于日线斜率判断方向」；§8 报告主句是「【方向判断】看多 ↑ / 日线斜率: +0.15%/天」 |
| 代码 | `cascade/signal_contract.py` L5–10、L32–45：`唯一可交易方向 = sign(weighted_1H_pred − base)`；`daily_slope` 只填 `regime_direction`，「never overrides trade position」 |
| 代码 | `cascade/daily_model.py` L189–207：`_compute_direction_v2` 仍按日线斜率+ R² 门出**日线摘要**，不是仓位 |

**判定：矛盾成立。** 现行合同是 CF-01 A（加权 1H）。`system_design.md` §5.1/§8 把副标签画成主方向，且提供可复制伪代码。这是文档会改错生产信号的主风险，交给 Task 2/6/9 查盘中文案是否跟错。**不是**「代码现在按日线斜率开仓」——`signal_contract.py` 已经按 CF-01 A 写死。

### 4.2 IC：Pearson vs `2×|dir_acc−0.5|`

| 侧 | 原文 |
|----|------|
| A `loop-constraints.md` L48 | 「IC≥0.05（ic=2×\|dir_acc−0.5\|）」 |
| A `docs/praxist.md` L94 | 「IC ≥ 0.05（ic = 2×\|dir_acc−0.5\|）」 |
| B `docs/system_design.md` L485 | 「**IC** \| corr(预测, 实际) \| 信息系数 \| ≥ 0.05」 |
| 代码 | `task_FM/evaluations/fm_eval/evaluator.py` L199–203：`ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)`；`gate` 只用 n 与 ic |
| 代码 | `scripts/aligned_slow_loop.py` L101：`ic = round(2 * abs(dir_acc - 0.5), 10)` |
| 磁盘 | 26 条 `status=ok` 裁决，`ic` 与 `2*\|dir_acc-0.5\|` **0 条 mismatch**。例：`ss_vor` dir_acc=0.53 → ic=0.06；`i_oi` dir_acc=0.467 → ic=0.066 |

**判定：矛盾成立，合同与磁盘站在 dir_acc 映射一边。** `system_design.md` 的 Pearson 是错合同。不要把这写成「评估器在算相关」——评估器没有 Pearson。

### 4.3 `gate_pass` 是否含 EV

| 侧 | 原文 |
|----|------|
| A `loop-constraints.md` L48 | 「最终裁决口径」：n≥350、IC≥0.05、**扣滑点 EV>0**、PF/incumbent>1.05 |
| A `config/praxist_task.yaml` L19–20 | `full_walkforward` gate: `["n>=350", "ic>=0.05", "ev>0"]` |
| A `docs/praxist.md` L91–95 | 硬门预注册列出 EV>0 |
| A `docs/system_design.md` L537–544 | `gate_pass = (n>=350) and (ic>=0.05) and (ev>0)`，「协变量是否可用于生产」 |
| B `docs/praxist.md` L115 | 「硬门只判 n+ic」；`i_oi` gate_pass=True 但 ev=−2.46 |
| B `STATE.md` L37 | 同上，称为已知瑕疵 |
| 代码 | `evaluator.gate()` L199–203：**只判 n 与 ic**，没有 EV |
| 代码 | `scripts/registry_lib.py` L39–45：`pass_variants()` = `gate_pass and ev>0`（经济过门另函数） |
| 磁盘 | `gate_pass=True` 共 3 条：`ss_vor`（ev=+11.06）、`i_oi`（ev=−2.46）、**`m_ccl`（ev=−3.64，2026-09-11T10:27，git_rev `2855ebf8`）** |

**判定：矛盾成立，而且是「同名两扇门」。**

- 布尔字段 `gate_pass`（磁盘/代码）= n≥350 且 IC≥0.05，**不含 EV**。
- 经济过门 / 目标成功条件 = 再加 ev>0 与 PF 比（`pass_variants`、goal DSL）。
- yaml 与 `system_design` 把第二扇门的 EV 写进了第一扇门的名字里。
- `praxist.md` 自己两段互斥（L91–95 vs L115）。
- STATE 只点了 `i_oi`；磁盘在 2026-09-11 又写了 `m_ccl` 同样亏钱却 `gate_pass=True`。文档低估了瑕疵面。

不要把 yaml 里的 `ev>0` 当成「代码忘了写」就去改 `gate()`——那会改变 peer 看到的 `gate_pass=` 语义。真正的问题是命名和 materializer。交 Task 7/8。

### 4.4 SS 主协变量：calendar_cyclical vs vor vs SCHEMES

| 侧 | 原文 |
|----|------|
| SCHEMES `config/prediction_scheme.py` L120–133 | `"ss"`：`covariate_type="calendar_cyclical"`，`covariate_types=["calendar_cyclical"]`，stars=2（G005-E，n=396） |
| Praxist 磁盘 | `ss_vor` n=396 PF=1.123 ev=+11.06 ic=0.06 `gate_pass=true`（2026-09-09） |
| `STATE.md` L36 / `docs/praxist.md` L114 | 「经济意义上实质仅 `ss_vor`」——这是慢环过门，**没说已写入 SCHEMES** |
| `docs/system_design.md` L231–236、L584、L765 | 示例 SS 主协变量 = `calendar_cyclical`（与 SCHEMES 一致） |
| `docs/system_design.md` L267–271 | 「当前过门协变量（2026-09-10）」SS = **vor**，标「实质性过门」 |
| `AGENTS.md` L351 | 生产协变量表：SS 仍是 `calendar_cyclical` |

**判定：三套名字，两套事实。**

- 生产 SCHEMES = `calendar_cyclical`（层 2）。
- 慢环过门候选 = `ss_vor`（层 1 磁盘），**尚未固化**。
- `system_design.md` 同一天的文档里，§4.2/§8/§10.1 写生产表，§4.3 写研究过门，却都叫「当前」，执行者会把 vor 写进 `SCHEMES` 或把 calendar 当成已证伪。

### 4.5 硬门 n：396 vs 600 vs STEP=2 后的实际 n

| 侧 | 原文/数字 |
|----|-----------|
| 硬门阈值 | 各现行合同均为 **n≥350**（不是 396，也不是 600） |
| 旧网格实现值 | 大量历史回测与 `ss_vor`：**n=396**（`max_points=600` 也只跑出 396） |
| 目标上限 | `scripts/praxist_goal.yaml` `aligned_max_points: 600`；`backtest_config.py` L56–57：`STEP=2`，`EVAL_WINDOW_BARS=1200`，「600 点 × STEP=2」 |
| `docs/system_design.md` L782–783 | 附录已改成 STEP=2 / 1200（与代码一致） |
| `docs/validation_criteria.md` 案例 | 多处 n=396，那是 Phase 4d 样本，不是门限 |
| 磁盘 n 分布 | 26 行：396×21、**588×3**、324×1、142×1。588 出现在 2026-09-10 `m_oi`/`eg_nvi`/`eg_ha_body`（STEP=2 之后）。2026-09-11 的 `m_ccl` 仍是 n=396 且 `max_points=396` |

**判定：数字打架成立，门限不打架。** 350 是硬门；396 是旧网格常见实现值；600 是 goal/理论上限；STEP=2 落地后磁盘最高 588，不是 600。研究文档若仍写「必须立刻改成 600 / STEP=24 是活 bug」，交 Task 4 按「号召过期」处理，不要写成代码没改——`backtest_config.py` 已经是 STEP=2。

### 4.6 Praxist peer：评估器 vs 假设作者

| 侧 | 原文 |
|----|------|
| 现行 `loop-constraints.md` L49 | 「方案 A（2026-09-08 起）：peers 不再跑任何评估/加载 TimesFM」 |
| 现行 `docs/praxist.md` L65–67 | 「Peer 是假设作者，不是评估器」 |
| 现行 `docs/spec_hypothesis_driven_fast_loop_20260908.md` | 状态「已实施」；`ss_vor` 出自本方案 |
| 残留 `config/praxist_task.yaml` L16–17 | 仍有 `stage: diagnostic`，「短窗口, 只产 incubator 证据」 |
| 历史 `docs/praxist_integration_plan.md` | 正文仍设计 diagnostic 阶梯；**顶部横幅已宣布过时** |
| 历史 `docs/praxist_peer_evaluation_fix.md` L4 | 状态仍「待执行」 |
| 历史 2026-09-02 三环 spec | 交 Task 3；runbook L192 说绑定解释优先 |

**判定：现行合同是方案 A（假设作者）。** 同级 yaml 仍留 diagnostic 阶梯，是层 2 内部不一致。原始 spec 不当活合同。`peer_evaluation_fix.md` 的「待执行」会把已经做完的方案 A 又当待办。

### 4.7 Vol gating：默认 OFF vs 读起来像生产路径

| 侧 | 原文 |
|----|------|
| `STATE.md` L119 | 「生产 vol 压平默认 OFF」 |
| `docs/module_freeze.md` L8 | CF-12 A「永不默认 ON；Copilot 仅预警」 |
| `docs/product_positioning.md` L26–27 | Vol 默认 OFF；预测永不因 Overlay 静默压平 |
| `docs/system_design.md` L58、L402–404、L700 | 明确「默认 OFF」；启用方式是 `--vol-filter-neutral` / `FM_VOL_FILTER=1` |
| `docs/system_design.md` §6.2–6.4、§8.1 | 把熔断流程、ThrPolicy、报告里的「Vol 雷达」画进主路径；§8.3「不建议」条件含「Vol 熔断」 |

**判定：默认 OFF 合同成立，没有文档主张「生产默认开熔断」。** §6/§8 的写法会让新接手的人以为雷达/熔断是盘中必经。这是读感问题，不是合同反转。交 Task 9 只核对代码默认值，不要从这篇出发去「打开生产熔断」。

---

## 5. 过期文档清单

| 文件 | 过期点 | 严重度 |
|------|--------|--------|
| `STATE.md` L7、L26–38 | 「最后更新 2026-09-09」；监督环 `cycles_done=6`/`phase=slow`/预算 20·30h·80M；磁盘已是 `phase=fast`、`cycles_done=1`、goal 无限预算 | Important |
| `STATE.md` L621–627 | `See /root/timesFM_fu/docs/superpowers/reports/supervisor_budget_exhausted_20260903_*.md` — 路径不存在 | Important |
| `docs/praxist.md` §4 现场 | 复制 STATE 快照，同样落后 | Important |
| `docs/system_design.md` §5.1/§7.1/§7.3/§4.3/§8 | 日期新、合同旧（方向/IC/gate/SS 混写） | Important |
| `docs/README.md` L103 | 「当前生产姿态（2026-08-21）」 | Important（标题）；同节 L111 有 2026-09-09 补丁 |
| `config/praxist_task.yaml` | 2026-09-01 diagnostic 阶梯 | Important |
| `docs/praxist_peer_evaluation_fix.md` | 状态「待执行」 | Minor |
| `docs/research/slow_loop_evaluation_points_research.md` | 「待执行修复」vs STEP=2 已落地 | 交 Task 4 |
| `AGENTS.md` L21 | 「生产红线（2026-07-27）」日期旧，内容仍对 | Minor |
| `scripts/praxist_goal.yaml` 头注释 | 仍写 15GiB 宿主；runbook 已是 7.7 GiB | Minor |
| `product_positioning.md` / `module_freeze.md` / `validation_criteria.md` | git 停在初始提交，合同内容仍被引用 | 不因日期作废 |

---

## 6. 会误导执行者、但不在「先审文档」主链里的文件

这些文件不是层 1–3 的活合同，但搜索/打开标题就会把人带跑。

| 文件 | 误导点 | 应读 |
|------|--------|------|
| `docs/praxist_integration_plan.md` | 标题仍像方案；正文 `/root/timesFM_fu`、独立 venv、peer 跑 diagnostic。**有 2026-09-09 横幅**，横幅有效 | `docs/praxist.md` |
| `STATE.md` L621–627 | **权威层 1 文件里的死链** `/root/timesFM_fu/...`；20260903 那三份报告在本仓不存在 | 删死链或改 `/home/abug/timesfm/...`（只建议） |
| `docs/system_design.md` §9.2 | `source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate` + `cd D:/FlyBuddy/FM_a` — 正是本审核禁止当真相源的 Windows 树 | WSL `/home/abug/timesfm` + `.praxist-venv` |
| `AGENTS.md` L32 | 权重隔离表仍写「预测岗 `timesFM_fu`」 | 同文件 L42 已写本仓 WSL |
| `docs/praxist_peer_evaluation_fix.md` | 「待执行」会让人再去做已经落地的方案 A | `spec_hypothesis_driven_fast_loop_20260908.md` |
| `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | 原始三环 spec，peer diagnostic 筛选 | runbook L192 绑定解释；交 Task 3 |
| `evaluator.py` L6 | 模块头仍写「诊断级只产 incubator」 | 方案 A 后快环不再跑该评估器；交 Task 8 |

---

## 7. 给 Task 2–4 的必查矛盾

**Task 2 `system_design.md`（按这篇执行会改错信号/硬门的，才升 Critical）：**

1. §5.1 `_compute_direction` / §8 主方向 vs `signal_contract.position_from_forecast`；并核 `_compute_direction` 是否还存在（代码里是 `_compute_direction_v2`）。
2. §7.1 Pearson IC vs `evaluator.gate` / 磁盘。
3. §7.3 `gate_pass` 含 EV vs `evaluator.py` L199–203。
4. §4.2 vs §4.3 SS 协变量；生产 SCHEMES 不得被 vor 覆盖，除非另开固化 plan。
5. §1/标题「开平仓建议」vs CF-05/CF-01 产品红线。
6. §9.2 Windows 路径；§6 Vol 读感（合同已是 OFF，不要反着「打开」）。
7. 示例 `horizon_slope * 100` 与 `daily_model.py` L198 `thr_ratio = trend_threshold_pct / 100.0` 是否单位反了。

**Task 3 specs：**

1. 2026-09-02 三环 spec 的 diagnostic 筛选句，哪些还像活合同。
2. `praxist_task.yaml` diagnostic 段是否仍被校验器当硬约束。
3. hardening SPEC-004…013 与 `CLAUDE.md` 能力表 / git merge 是否同拍。
4. `peer_evaluation_fix.md`「待执行」是否应改成「已被方案 A 取代」。

**Task 4 research：**

1. `slow_loop_evaluation_points_research.md`「待执行修复 / STEP=24」vs `backtest_config.py` STEP=2（2026-09-10）。
2. 396 vs 600 vs 磁盘 588：理论 n、`aligned_max_points`、`max_points=396` 的 `m_ccl` 从哪来。
3. 若前视已修：Critical 是「研究文档仍号召立刻修」，不是「代码仍穿越」。穿越本身归 Task 5。

---

## 8. Findings

### Critical（会直接改错生产信号 / 硬门 / 截断）

无。本任务看到的活代码与磁盘：方向走加权 1H，IC 走 `2×|dir_acc−0.5|`，Vol 默认 OFF，peer 不评估。危险在文档，不在「现在盘中已经按日线斜率下单」。

### Important

**I-01 可交易方向：新设计文档把副标签写成主方向**

- 证据：`docs/system_design.md` L313–329、§8 L577；对 `docs/product_positioning.md` L15–20；`cascade/signal_contract.py` L5–10
- 文档合同：CF-01 A = `sign(weighted_1H − base)`
- 磁盘/代码：`position_from_forecast` 用加权 1H；日线只出 regime
- 为何重要：`system_design.md` 日期 2026-09-10，比 CF-01 A 文档新，带可复制函数。按它改 copilot/回测会换掉仓位符号
- 建议：在 `system_design.md` §5/§8 改成「主方向=加权 1H，日线是副标签」；或在文首加「方向/IC/gate 以 product_positioning + loop-constraints 为准，本文示例作废」。不要改 `signal_contract.py`

**I-02 IC：设计文档写成 Pearson，活合同与磁盘不是**

- 证据：`docs/system_design.md` L485；`loop-constraints.md` L48；`evaluator.py` L199–203；26/26 裁决匹配
- 文档合同：`ic=2×|dir_acc−0.5|`
- 磁盘/代码：慢环写入的 `ic` 就是该式
- 建议：改 §7.1 公式。禁止把评估器改成 `corr(pred, actual)`

**I-03 `gate_pass` 与「硬门含 EV」混名；磁盘亏钱过门比 STATE 写的多**

- 证据：`evaluator.py` L163、L199–203 只判 n+ic；`aligned_verdicts.jsonl`：`i_oi` ev=−2.46、`m_ccl` ev=−3.64 均为 `gate_pass=true`；`STATE.md` L37 只写了 `i_oi`；`docs/praxist.md` L91–95 与 L115 自相矛盾；`praxist_task.yaml` L20 把 `ev>0` 写进 gate 列表
- 文档合同：最终裁决要 EV>0；`gate_pass` 字段实际不含 EV
- 磁盘/代码：`pass_variants()` 才是 `gate_pass and ev>0`
- 建议：文档把两扇门改名分开（例如 `gate_pass` vs `econ_pass`）。更新 STATE：至少补 `m_ccl`。不要在没改 materializer 语义的情况下给 `gate()` 加 EV

**I-04 SS：生产 calendar_cyclical，研究过门 vor，设计文档两边都叫「当前」**

- 证据：`prediction_scheme.py` L132–133；磁盘 `ss_vor`；`system_design.md` L231–236 vs L267–271
- 文档合同：SCHEMES 是唯一生产协变量表（`module_freeze.md` CF-11 A）
- 磁盘/代码：vor 过了慢环硬门，**没写进 SCHEMES**
- 建议：§4.3 标题改为「慢环过门、未固化」。固化 vor 必须另开人工确认，禁止顺手改 `prediction_scheme.py`

**I-05 样本量叙事：396 / 600 / STEP=2 / 实际 588 四套数**

- 证据：`backtest_config.py` L56–57；goal `aligned_max_points: 600`；磁盘 n 分布 396×21、588×3；`ss_vor` 在 max_points=600 时仍 n=396
- 文档合同：硬门 n≥350
- 磁盘/代码：STEP=2 已落地；600 是上限不是已实现 n
- 建议：STATE/praxist 快照写明「ss_vor 的 396 是 2026-09-09 旧网格实现值」。研究文档交 Task 4。不要把 396 当现行采样合同

**I-06 同层合同：`praxist_task.yaml` 仍有 diagnostic 阶梯**

- 证据：`config/praxist_task.yaml` L16–17；`loop-constraints.md` L49
- 文档合同：方案 A 起 peer 不评估
- 磁盘/代码：yaml 仍被标为契约权威文件（`loop-constraints.md` L50）
- 建议：yaml 删除或标注 diagnostic 作废；校验器若仍认该 stage，交 Task 3/8

**I-07 STATE 人类快照落后于磁盘（phase / cycle / 预算 / 死链）**

- 证据：`STATE.md` L7、L34–35、L621–627；`data/cache/supervisor_state.json`：`phase=fast`，`cycles_done=1`，`last_run_id=run_2026-09-10_03-06-50_primary_task_FM`；`scripts/praxist_goal.yaml` budgets 999999 / deadline 2099-12-31（git `ee1f176`）
- 文档合同：STATE 自称 canonical_state，同时又说 Praxist 机器事实在 JSON
- 磁盘/代码：快照表不是机器事实；`/root/timesFM_fu/...20260903...` 文件不存在
- 建议：快照表改成「以 JSON 为准，下表仅交接」或按磁盘重刷；删掉 `/root/timesFM_fu` 死链。不要用这张表判断监督环是否在跑（本审核也不启动它）

**I-08 两套固化门没有分层声明**

- 证据：`docs/AGENTS.md`「固化门槛以 `validation_criteria.md` v2 为准」；Praxist 硬门是 n+IC（+经济层 EV/PF）
- 文档合同：v2 管 SCHEMES 人工固化；Praxist 管慢环是否过门
- 磁盘/代码：`ss_vor` 过 Praxist 硬门，SCHEMES 仍是 calendar_cyclical，正好说明两扇门独立
- 建议：在权威链/README 写一句「v2 ≠ gate_pass」。禁止用 v2 的 MAPE 规则去改慢环 `gate()`，也禁止用 `gate_pass=True` 直接改 SCHEMES

**I-09 `system_design.md` 给出 Windows 活仓路径**

- 证据：`docs/system_design.md` §9.2（约 L747–748）：`D:/FlyBuddy/shared/timesfm/.venv` 与 `D:/FlyBuddy/FM_a`
- 文档合同：活仓是 WSL `/home/abug/timesfm`
- 磁盘/代码：本审核只认 WSL
- 建议：换成 WSL 命令。按那段在 Windows 副本上改 SCHEMES/模型，就是计划里禁止的真相源错误

### Minor

- **M-01** Vol 章节读感像生产路径，但 §6.1/§9.1 已写默认 OFF。不必当合同冲突。
- **M-02** `AGENTS.md` L21「生产红线（2026-07-27）」日期旧，内容仍对。
- **M-03** `docs/praxist_peer_evaluation_fix.md` 状态「待执行」。
- **M-04** `evaluator.py` L6 模块头仍提 diagnostic 档。
- **M-05** `system_design.md` 标题「开平仓建议」与「领航员而非自动驾驶」并排，产品定位风险，交 Task 2。
- **M-06** `praxist_goal.yaml` 头注释仍写 15GiB；runbook 为 7.7 GiB。
- **M-07** `AGENTS.md` L32 `timesFM_fu` 权重表与 L42 WSL 现状并排。
- **M-08** `docs/README.md` 索引把 `praxist_integration_plan.md` 和现行 runbook 列在同一张「PRAXIST」表里（`docs/AGENTS.md` 已标历史，README 没有）。

---

## 9. 给后续任务的权威裁决（可直接引用）

1. **可交易方向** = `sign(weighted_1H − base)`。日线斜率是副标签。
2. **IC** = `2×|dir_acc−0.5|`。不是 Pearson。
3. **`gate_pass` 字段** = n≥350 且 IC≥0.05。EV 在经济过门 / 最终裁决层，不在这个布尔里。
4. **SS 生产协变量** = `calendar_cyclical`。`ss_vor` 是慢环过门，未固化。
5. **硬门 n 阈值** = 350。396/588/600 是实现值或上限，不是阈值。
6. **Peer** = 假设作者，不评估。yaml diagnostic 段是残留。
7. **Vol** = 生产默认 OFF。
8. **Praxist 是否在跑** 以 `supervisor_state.json` 为准，不以 STATE 快照表为准。本审核不启动进程。

---

## 10. 本任务未做

- 未跑 pytest，未启动 supervisor / 慢环。
- 未把 `system_design.md` 逐节对照函数签名（Task 2）。
- 未分类全部 superpowers spec（Task 3）。
- 未验证 `get_safe_daily` / 前视是否已修（Task 4/5）。
- `aligned_verdicts.jsonl` 与 `supervisor_state.json` 不在 git 里，数字以本次读盘为准。
