# 三环系统的 AutoResearch 范式定位与优化方向 —— 代码级核实报告
> **代码基线**: `9522900`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

- **报告日期**：2026-10-03
- **核实基线**：WSL `/home/abug/timesfm` @ `fece4bd`，协议指纹 v4 `f02b2a43…`
- **方法**：6 路并行只读代码审计，逐条回代码与磁盘数据重新取证，**不采信既有文档描述**
- **报告性质**：对一份初步分析的**证伪/修正报告**。初步分析的 4 个维度评分中有 3 个被推翻，1 个被下调，1 项核心论据（确认墙）被推翻。

---

> ## ⚠️ 勘误（2026-10-03，报告落盘后当日追加）
>
> 本报告成稿时**只读了代码与运行报告，未先读 spec 的开放问题节**，把「等宿主裁定的保守默认」误判为「结构缺陷」。**以下四条结论降级，§5 的一等优化方向随之作废。**
>
> | 本报告结论 | 勘误 | 权威出处 |
> |---|---|---|
> | **P0-1**「配对诊断层整层空转」为 P0 缺陷，建议给 `build_summary` 传 `missingness_admissible=True` | **降级为「有意的保守默认」**。这是**错误诊断**，建议违反 spec | v15 spec 第 461 行：「§7.8 裁定前 `missingness_admissible` **恒为 False**（一切确认运行落 `descriptive_only`）——**这是有意的保守默认，不是缺陷**」。§7（开放问题 #8）明载缺失与状态独立性的判定方法**尚未裁定** |
> | **P0-2**「gate 阈值是常数、0.50 即硬币率」为 P0 缺陷 | **降级为已立项的开放问题** | v15 spec §7 开放问题 #7 + `docs/superpowers/reports/2026-09-30-q7-target-effect-power-memo.md`（Q7 备忘录）已在处理 |
> | **P1-3**「`_dead_families` 口径 bug」需修正 | **降级为已被覆盖**。其核心诉求（只有可确认的 DM 失败才让族死亡）已由 `plans/2026-10-03-three-loop-open-closure.md` Task 4 覆盖 | 该计划 Task 4 |
> | **P0-3**「确认通道未接线」为 P0 工程缺口 | **降级为已被覆盖** | 该计划 Task 8（造确认队列行）+ Task 9（确认入队与终结接到主循环） |
>
> **连带失效**：§5「优化方向」的一等项（接通裁判：配对诊断层可达 / 改 gate 口径 / 接通确认通道）**三条中两条已被 spec 裁定或明令禁止，第三条已在在飞计划中立项**。§5 二等项（记忆回路）与 §2.3 记忆架构分析**仍然成立**，是核实后唯一存活的高价值发现。
>
> **仍然存疑、未被任何文档裁定**：`P1-2`「`_has_prior_failure` 是 OR 语义」（在飞计划明令「不要改成必须同一配对」，故本轮不动，但长期存疑）；`P2-1` 品种数 9 vs 24、`survivors_per_cycle` 默认值不一致。
>
> **勘误后的唯一行动项**：见 `docs/superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md`。

---

## 0. 执行摘要

---

## 0. 执行摘要

初步分析给出的定位是「线性拓扑 + 人工规则决策 + 文件池记忆，仅反馈信号达标」，并据此断言**不要升级搜索拓扑，应升级决策主体与记忆架构**。

六路核实后，**这个定位和由此推出的优化排序都不成立**：

| 初步结论 | 核实结果 |
|---|---|
| 反馈信号 4/4（最强一格），别投 | **推翻**。判据强度是四维里**最弱**一格；`pass_variants()` 对全部 **235 行返回 0** |
| 决策主体 0.5/4，「比 Karpathy 的 Agent 自主还低」 | **推翻**。选方向由 agent 自主产出 `research_agenda`，含 `anti_mainline` 禁令与逐 peer 契约。真实档位 **1.5/4** |
| 记忆架构 2.5/4（CORAL 式文件池） | **推翻**。不是文件池，是每轮覆盖的快照；**拒收理由从不回写 peer**。真实档位 **1/4** |
| 「1.2–2.0 年确认墙」是真实主约束 | **推翻**。确认通道**从未接入调度**，实测速率 = 0。是**空墙**，不是高墙 |
| 三环属「线性路径」类 | **部分修正**。控制流是 phase 状态机有分支；但**解空间**仍无任何树/池/回溯结构，分类不变 |
| 三个饿死事故「同一根因：记忆污染」 | **推翻**。三者根因互不相同（字段缺失 / 快照口径 / 阈值过低），修复时间线不重叠 |

**修正后的核心判断**：三环有很强的**生成**能力（agent 自主选题、提案产出、指纹化裁决、协议版本管理都做得比同类系统扎实），但**几乎没有「判断」和「学习」能力**：

- **判断断路**：`missingness_admissible` 在 `build_summary` 里从未被传参，恒为 `False`，导致 `statistical_tests.py:392` 直接 `return set_mismatch_descriptive`，`:395` 的 `pairing_valid=True` 分支是**任何生产路径都不可达的死代码**。DM 检验层整层空转，38 个 p 值只是描述性输出。
- **学习断路**：18 道门的拒收理由（`no_failure_delta` / `family_dead` / `dedup` …）只进 supervisor 日志，**从不物化进 peer 可见的 `.inc.md`**。peer 被拒 → 看不到原因 → 基于同样认知重提 → 再被拒。
- **确认断路**：确认通道代码完备（`preregistry.py:400+`、`classify_confirmation`），但调度入口、数据就绪、晋升触发器三者全缺。

**因此真正的优化方向不是四维框架里的任何一维，而是接通裁判。** 详见 §5。

---

## 1. 核实方法与可信度声明

6 路并行只读审计，全程仅 `grep`/`sed`/`cat` 与 `/tmp` 临时只读脚本，未触碰仓内文件、未启停 supervisor、未跑 pytest 或回测。

**本报告区分两类证据**：

- **一手**：代码行、磁盘数据、日志实测、git 历史
- **二手**：既有报告（`2026-10-03-three-loop-v4-operations-report.md`、`STATE.md`）中的数字

初步分析与既有报告的数字偏差见 §6 校准表。**多份数字对不上，其中一份（本次分析）沿用了未复核的二手数字。**

---

## 2. 四维定位（修正版）

以 AutoResearch 四维框架（搜索拓扑 / 反馈信号 / 记忆架构 / 决策主体）对照。

### 2.1 搜索拓扑 —— 1/4（维持）

分类不变，但**证据要更正**：初步分析称「固定顺序线性流水线」，这不准确。主循环 `praxist_supervisor.py:2428-2620`（`_main_locked`）是 **phase 状态机**（`fast`/`slow`/`wait_quota`/`paused_429`），有多处分支：`dry_run`/`goal_reached` 提前退出、`budget_hit` 嵌套分支可多次循环、`phase==slow` 时跳过快环。`_maybe_harvest` 甚至不是每 cycle 必跑。

**但框架里的「线性/树形」指解空间的行走方式，不是控制流。** 解空间侧无任何结构：

- 全仓搜 `tree`/`parent`/`children`/`crossover`/`population`/`bandit`/`UCB`/`elite`/`generation`/`backtrack`/`rollback` —— 无搜索拓扑结构
- `fm_two_peer` 是 Praxist 的**多 PI 评审拓扑**（builder/skeptic/portfolio + chair，`peer_role_rotation: exploit/falsifier`），与遗传/树搜索无关
- `_has_prior_failure`（`:1025-1036`）只有「拒绝」语义，无回溯；`dead_variants`（`registry_lib.py:126-128`）只用于入队去重，不撤销已写裁决
- **提案只增不减确证**：`queue_enqueue`/`queue_ack` 无移除 API，`_append_backlog` 只追加。实测 run 目录 **190**、proposal JSON **3,651** 份、done 队列 275 行

### 2.2 反馈信号 —— 判据强度 1/4（**推翻 4/4**）

这是本次核实最重要的修正。初步分析把**字段数量当成了判据强度**。

v4 裁决 47 行共有 **67 个顶层 key**（工程完备度确实 4/4：6 类指纹、A1 必填字段 47/47 无缺）。但真正参与判定的只有 3 个量：

| 字段 | 判据类型 | 证据 |
|---|---|---|
| `dir_acc` | 统计量（比例），**无 CI** | `evaluator.py:526` |
| `p_value` | DM 检验，**但配对被判无效** | `statistical_tests.py:158`；38/47 有值全部 `dm_status=set_mismatch_descriptive` |
| `fdr_pass` | 真 BH/Bonferroni，但 **46/47 = False** | `statistical_tests.py:292/300` |

其余 **59 个字段**是恒零占位（`migrated_pass`/`seed_fingerprint`/`context_hash`/`data_revised` 47/47 全 None）、纯常数函数（`n_eff` 47/47 恒等于 73，是 `n=588` 的 Bartlett 核确定性映射，携带信息量为零）、查表元数据（`horizon_known`）、启发式加权（`tier` 105 分制，无一维含 p 值或 CI）、或血缘登记（注释明示「仅登记，不做诊断性检验」）。

**三个恒 False 死字段**：

```
pairing_valid          47/47 = False
missingness_admissible 47/47 = False   ← 根因
dm_status              仅在 set_mismatch_descriptive / no_common_cutoff 间摆动，无一进 ok
```

`missingness_admissible` 在 `statistical_tests.py:339-340` 的默认参数里是 `None → False`，而 `build_summary` **从不传该参数**。于是 `:392` 的 `if not missingness_admissible: return set_mismatch_descriptive` 恒成立，`:395` 的 `pairing_valid=True` 分支不可达。**配对诊断层整层空转。**

**「门槛=硬币率」的代码事实成立**（详见 §3 P0-2），但它是 §7 开放问题 #7 的待裁定项，非未处理缺陷。

**自我否定的证据**：系统自己写着 `pass_variants()` 对全部 **235 行返回 0**；v4 确认级产出 **0/47**（全部 `exploration`）；活跃视图 `passing=0`。

### 2.3 记忆架构 —— 1/4（**推翻 2.5/4**）

初步分析称「CORAL 式文件池」并建议「别加 attempts/notes/skills 目录」，方向对但定性错。

实际是**每轮覆盖的快照**，不是持久池：`materialize_known_verdicts`（`:872`）与 `materialize_covariate_menu`（`:1772`）每次循环**重写**两个 `.inc.md`（`:2827/:2833/:2906/:2912`），无追加、无版本链、无跨轮索引。

初步分析说「没有 family 级聚合」，**这句是错的** —— 实际产物有三个聚合节：

```markdown
### Passing families
- momentum: 8 gate_pass
### Near-miss (0.49 <= dir_acc < effective_min)
- sr_term_structure_b796d1e1483d dir_acc=0.501 min=0.520
### Weak families (>=4 ok, 0 pass)
- term_structure: 5 ok, 0 pass
```

但「有计数、缺理由与结论」这个判断成立，且缺口比想象中严重：

| 缺口 | 证据 |
|---|---|
| **渲染行无协议指纹** | 行格式 `- {variant_id}: {state}, gate_pass=…`，无 `f02b2a43` 前缀；`_primary_fp` 选择逻辑在 `:884-896`，但**不写入文件**，peer 无法知道当前主协议组是谁 |
| **拒收理由完全不可见** | `no_failure_delta`/`family_dead`/`quality_below_threshold`/`sector_blocked`/`cov_cross_fail` 只存在于 supervisor 日志，从不物化 |
| **dead family 状态不告知 peer** | `_dead_families()` 在 `:1194` 算出、`:1695` 用于拦截，但 peer 只看到 `Weak families: 5 ok, 0 pass` 计数 |
| **peer 读不到历史机制** | `prompt_base.jinja2` 只 include 两个 `.inc.md`，不含历史 `mechanism`/`failure_delta` |

`build_knowledge_base.py` / `copilot.py` 是**离线静态库，与快环记忆完全隔离**（CLAUDE.md 中 `known_verdicts` 与 `covariate_menu` 之外的第三条路径不存在）。

**结论：记忆与决策之间没有回路。** 这是 §3 P1 的核心。

### 2.4 决策主体 —— 1.5/4（**推翻 0.5/4**）

初步分析称「几乎全部人工硬编码，比 Karpathy autoresearch 的 Agent 自主还低」。**后半句不成立。**

**选方向确实是 agent 自主的。** Praxist 内置 PI/Chair agent 产出 `agendas/research_agenda_gen1.yaml`，自主决定：

- `mainline_observation`（`:4-14`）—— 自主识别主流机制与风险权衡
- `cross_peer_hypotheses` —— 每条须融合 ≥2 个 peer 证据，带 `minimal_test`/`kill_condition`/`promote_condition`
- `peer_contracts`（`:183-216`）—— **逐 peer 指定** `role`(exploit/falsifier)、`target_hypothesis`、`bottleneck_target`、`forbidden_actions`、`success_signal`
- `anti_mainline`（`prompt_generation.jinja2:52-55`）——「你的提案禁止使用主流族」，由 LLM 判定禁什么

`prompt_generation.jinja2:40-56` 只给四个角色的**元定义**，具体攻什么禁什么是 agent 从上一代证据推出来的。这套东西人工规则写不出来。Karpathy autoresearch 里 agent 同样是自己决定改什么。

**但 agent 没有否决权**，这是 1.5 而非 4 的原因：

- `harvest_proposals`（`:1638-1716`）内联 **18 道 reject 门**，agent 一票都投不了
- `top_k=3`（`goal.yaml:24 survivors_per_cycle`）配额，agent 无发言权
- `_proposal_priority_score`（`:1306-1385`）的 10 个加权项 + Jev 的 −100，是**人工设计的排序函数**
- **提案 schema 12 个字段全是「我要提什么」，没有一个是「我拒绝 / 我建议停」**

supervisor 内部 `grep agent|llm|decide|select` 命中 33 处**全是基础设施**（provider 路由、确定性分层、启停决策）—— **零处 LLM 调用**，证实 supervisor 不是决策者。

---

## 3. 关键发现（按严重度）

### P0-1　配对诊断层整层空转，DM 检验结论无效

> **⚠️ 勘误**：本节诊断**过度**。`missingness_admissible` 恒 False 是 v15 spec 第 461 行与 §7.8 明文规定的**保守默认**（「在裁定前……宁可只作描述性，不可误判可确认」），**不是缺陷**。本节的代码事实（分支不可达）全部成立，但对它的定性错误，且下述「最小修复」违反 spec 与在飞计划禁令。

**证据**：`statistical_tests.py:339-340` `missingness_admissible=None → False`；`:392` 恒真返回；`:395` `pairing_valid=True` 不可达。47 行 `pairing_valid`/`missingness_admissible` 全 False；38 个 `p_value` 全部只是描述性输出；9 行 `p_value=None`（`no_common_cutoff`）。

**影响**：报告中「两条 DM 显著候选」按 W3.4 不可确认，这条判断成立。但**整个系统目前没有任何一个数字带有统计意义**。

**最小修复**：给 `build_summary` 传 `missingness_admissible=True`（需先确认该参数的统计前提是否已满足，不能盲传）。

### P0-2　gate 阈值是硬编码常数，且 0.50 即硬币率

> **⚠️ 勘误**：本节的**代码事实全部成立**（阈值确为字面量、0.50 确为硬币率、`goal.yaml` 确无 gate 定义）。但它**不是未处理的缺陷**，而是 v15 spec §7 开放问题 #7 与 Q7 备忘录已在处理的**待裁定项**。在飞计划明令「不要改自适应门」。

**证据**：`evaluator.py:454` `gate()` 三条常数 `min_n=350 ∧ min_n_eff=50 ∧ min_dir_acc=0.52`；`evaluator.py:697` `compute_effective_min` = `max(0.50, min(0.52, baseline_dir_acc))`。`praxist_goal.yaml` **无任何 gate 定义**（第 13 行明写「原 Phase 1 的方向准确率绝对门槛与 tier≥8 已退役」）。

全流程**无置信区间、无功效分析、无多重比较校正用于 gate**。实测 15 条 `gate_pass` 中 **7 条 `effective_min=0.5`** —— baseline 差时，任何 `dir_acc ≥ 0.50` 的行都能过门。

这一项与 `docs/research/` 下尚未批准的评估口径审计（`fm-eval-credibility-audit`）结论一致，**本次从代码层面证实**。

### P0-3　确认通道代码完备但从未接线

> **⚠️ 勘误**：本节的**发现成立且有价值**（未接线、实测速率为空墙、数据滞后 10 天均为真），但**已被在飞计划覆盖**：`plans/2026-10-03-three-loop-open-closure.md` Task 8（从已锁定的预注册造确认队列行）+ Task 9（把确认入队和终结接到主循环）。本 spec 不重复立项。

**证据**：

| 项 | 状态 |
|---|---|
| `dispatch_confirmation`（`praxist_supervisor.py:190`）| 定义存在，**全文无调用点** |
| `finalize_confirmation`（`:260`）| 同上 |
| `aligned_verdicts.jsonl` 中 `run_mode=confirmation` | **0 条** |
| `preregistry.jsonl` 两条 `terminal_state` | 皆 `null` |
| `aligned_pending.jsonl` 队列 | 2 条，全 `exploration`，`max_points=600` |
| 最新 1H bar | **2026-09-23 14:00** |
| `confirm_from_ts` | 2026-10-03 00:00:00 → **10 天空档** |

**样本量数学本身是对的**（`statistical_tests.py:372` `n_required`）：

```
jd: 1.24 × (1.645+0.842)² / 0.08² = 1198.3 → 1199 ✓
sr: 1.02 × 2.487² / 0.0064          =  985.7 →  986 ✓
```

速率投影也成立（jd 2.50 点/交易日 → 2.00 年；sr 3.47 → 1.18 年）。**但通道未启动，实测速率 = 0。**

「1.2–2.0 年确认墙」应重新表述为：**通道的调度入口、数据就绪条件、探索→确认晋升触发器三者均缺位。当前不是被墙挡住，是确认室没开门。**

### P1-1　拒收理由从不回写 peer —— 记忆与决策无回路

见 §2.3。链条：

```
supervisor 拒掉 peer 提案 → 理由只进 supervisor_events/decisions 日志
        → peer 的 prompt 里没有任何这些字段
        → peer 基于同样认知重提 → 再被拒
```

实测拒收分布（最新一轮，seen=3644 / rejected=3597）：

```
no_failure_delta          2053 (57%)
family_dead                655 (18%)
dedup                      565 (16%)
schema_mismatch            253 ( 7%)
quality_below_threshold     42 (1.2%)   ← 质量门几乎不咬人
cov_cross_fail               10
其余                        19
```

质量门不咬的原因：正向项上限 `5+3+3+10=21`（`symbol_has_pass`+5 / `novel_combo`+3 / `mechanism_complete`+3 / `10×plausibility`），而 −20（`COV_FAIL_WINDOW=3`）与 −15（`SYMBOL_FAIL_WINDOW=5`）单独都打不穿 `MIN_QUALITY_SCORE=0.0`，必须同时命中。

### P1-2　`_has_prior_failure` 是 OR 语义，污染半径大于预期

**证据**（`praxist_supervisor.py:1025-1036`）：

```python
if v.get("symbol").lower() == symbol.lower(): return True
if v.get("cov_override") == cov: return True
```

初步分析（沿用官方报告）称「按 (symbol, cov) 配对」。实际是**单键 OR** —— 同 cov **不同品种**也会被拒，「这个协变量在任何品种试过了」即算已知失败。记忆污染的爆炸半径显著大于既有描述。

### P1-3　`_dead_families` 口径 bug：hard-gate 不救活自己的族

**证据**：`:1209` 用 `v.get("gate_pass")`，而全系统其他地方的「过门」定义是 `gate_pass ∧ fdr_pass`（`registry_lib.py:672`、`:683-684` 注释、`audit.yaml:22`）。

后果：一条过硬门但 FDR 未过的变体**救不了自己的族**，而它在 `materialize_known_verdicts:882-884` 里被告知「not a success; do not re-propose as solved」。agent 被**同时告知「这个已解决别再提」和「这个族已死别再提」**，而族死的那 5 条证据里可能连一条真过门的都没有。

`min_ok=4` —— 4 条 ok 即判死，无显著性、无样本量、无 `n_eff`、无 `dir_acc` 门槛。当前实测 `{term_structure}`（5 ok / 0 pass）被判死。**逻辑至今未改。**

### P2-1　`_has_prior_failure` 之外的次要口径不一致

- `GOAL_SYMBOLS_SET`（`:1153`）只有 9 个品种，`goal.yaml:31` 写 24 个
- `survivors_per_cycle` 代码默认 2、yaml 写 3（`:2491`）—— 改 yaml 不报错，静默生效

### P2-2　quota_gate 完全 fail-open

`:615-616` 从日志正则抓 `reset at <ts>`，抓不到即 `return True, 0` 放行。作用对象仅限快环 run 启停，明确不作用于 harvest（`:2499-2501` 注释）与慢环。

---

## 4. 三个饿死事故的真相

初步分析与官方报告均把三者叙述为「同一根因：记忆污染」。**核实后不成立。**

| 事故 | 一手证据 | 真实根因 | 状态 |
|---|---|---|---|
| #1 `no_failure_delta` 饿死 | 封存日志（2026-09-24T12:55）seen=1,936，该门 **1,270（65.6%）**。门禁代码 `:1695-1698`（`len(delta) < 20`）。`git log -S failure_delta` → **`5f0f151` (2026-09-19)**，**早于**封存 5 天 | **提案字段缺失**，不是记忆污染。门禁引入时存量/新生成提案未同步补 `failure_delta` 字段。时间错配说法不成立 | **未修**，门仍在 |
| #2 收割门跨协议旧代快照 | 密封日志共 **97 次** `harvest_empty`（09-20 当天曾连续 **14 轮**），非「连续 9 轮」。根因确认：`_harvest_rows` 原用 `rl.load_snapshot(REGISTRY)` 无协议过滤 | **快照口径缺失** —— 这是唯一一处「记忆污染」成立的事故 | **已修**（`045c7e2`, 2026-10-02，**封存后 8 天**才合入） |
| #3 `_dead_families` 判死 | 封存期日志**无任何 `family_dead` 记录**（功能 `6035c8e` 2026-09-20 引入）；封存后当前 `.omc/supervisor_decisions.jsonl` 实测 **655** | **阈值设计过低**（`min_ok=4`）+ P1-3 口径 bug | **未修**，封存后才开始生效 |

**修复时间线互不重叠，代码位置互不相关。三者是三个独立缺陷，不是一个故事的三个片段。**

值得单独指出：#2 的修复在封存**之后 8 天**才合入。这意味着 2026-09-24 → 09-28 解除封存的 4 天里，收割门仍在读跨协议旧代快照。

---

## 5. 优化方向（修正版）

初步分析的排序是「决策主体 → 记忆 → evaluator 吞吐，不要升拓扑」。核实后重排：

### 一等：接通裁判（P0-1 + P0-2 + P0-3）

> **⚠️ 勘误：本节整体作废。** 三件事中 (1) 违反 v15 spec 保守默认与在飞计划禁令，(2) 已在 Q7 备忘录立项、(3) 已在在飞计划 Task 8/9 立项。「235 行 0 过门」在 §7.8 与 §7 两项开放问题裁定前**本就是预期结果**，不是需要抢修的故障。勘误后的一等项见 `specs/2026-10-03-peer-memory-loop-closure-spec.md`。

**这是唯一能解开「235 行 0 过门」的改动。** 三件事，按依赖排序：

1. **让配对诊断层可达** —— 给 `build_summary` 传 `missingness_admissible`，使 `pairing_valid=True` 分支不再是死代码。需先核对该参数的统计前提。
2. **把 gate 从常数换成可论证的口径** —— 现在 `0.50/0.52` 是 `evaluator.py` 字面量，`goal.yaml` 里连定义都没有。建议改为「相对 baseline 的显著提升 + 置信区间下界」，而不是绝对 DirAcc 常数。
3. **把确认通道接进调度** —— `dispatch_confirmation` 的调用点、探索→确认的晋升触发器、数据就绪前置条件，三者缺一。

**为什么是一等**：在这三件完成前，任何提案数量的提升都只是在给一个不能判定的裁判喂料。§2.2 的实测已经证明这一点 —— 3,651 份提案、47 条裁决、0 条过门。

### 二等：接通记忆回路（P1-1 + P1-3）

> **📌 勘误后升为唯一行动项。** 一等作废后，本项是核实报告中唯一既未被 v15 spec 覆盖、也未被在飞计划禁止的高价值发现。P1-3 部分（`_dead_families` 口径）已被在飞计划 Task 4 覆盖；**P1-1（拒收理由从不回写 peer）无人认领**。spec 见 `docs/superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md`。

两件事，都只改渲染层与 schema，不碰回测器：

1. **把拒收理由与 dead-family 状态物化进 `.inc.md`**。`_dead_families` 的结果已在 `:1194` 算出来了，只是没写给 peer。加一段「本族已被判死（理由：min_ok=4, 5 ok / 0 gate_pass）」即可。
2. **给 `fm.hypothesis_proposal.v1` 加 `abandon`（bool + 理由）**。

第 2 点有独立佐证：Praxist 的 `next_step_intent` 枚举里**已经存在 `archive_negative_result`**（"放弃/归档负结果"），议程层有这个动作，只是 proposal schema 层没有对应槽位。导致 falsifier 角色被迫每次产出**一个正例提案**才能表达反对意见 —— 这是被 schema 逼出来的替代行为。

### 三等：口径与阈值修正（P1-2 + P2）

`_has_prior_failure` 的 OR 语义、`_dead_families` 的 `gate_pass` vs `gate_pass∧fdr_pass`、9 vs 24 品种、`survivors_per_cycle` 默认值不一致。这些是 bug 不是设计，改动成本低但需要单独评估回归。

### 不做：升级搜索拓扑

**维持初步分析的这条判断，但它现在有了更硬的理由。**

不是「搜索拓扑不是核心竞争力」这种泛论，而是具体的：

- 解空间侧无任何树/池/回溯结构（§2.1 已证）
- 快环**没有否决权**、慢环**没有并发**，但这两点都不是当前瓶颈
- **真正的瓶颈是裁判不通**：47 条裁决 0 过门、235 行 0 晋升

换树搜索或遗传池，只会让更多坏方案更快地涌进同一个**不能判定结果**的回测器。把反馈通道从「判不了」修到「能判」，收益远大于把提案数从 3,651 提到 10,000。

### 存疑：慢环并行化

初步分析称这是「最便宜」的 4–8× 收益。**这个判断要收回。** `aligned_slow_loop.py:319-324` 有全局文件锁**显式保证单实例**——串行是架构设计而非疏漏，并行化需要动锁语义与 checkpoint 隔离，成本高于表面。

且在确认通道未接通前，并行化的对象只有探索回测，而探索回测当前不是瓶颈（瓶颈是它产出的结果无法被判定）。

---

## 6. 数字校准表

本次核实中，**初步分析沿用的二手数字有若干偏差**：

| 项 | 官方报告 / 初步分析 | 一手核实 | 性质 |
|---|---|---|---|
| v4 裁决数 | 44 | **47** | 报告是 2026-10-03 11:00 前快照，非错误 |
| tier 分布 | S6/A6/B21/C11 = 44 | 剔除最后 3 条后**恰为 44** | 核实通过 |
| `no_failure_delta` 拒收 | 2,384（~75%） | 封存期 **1,270 / seen 1,936 = 65.6%** | 数字对不上，口径不明 |
| 连续 `harvest_empty` | 9 轮 | 密封日志共 **97 次**，09-20 当天连续 **14 轮** | 定义不同 |
| `family_dead` 拒杀 | 602 条 | 封存期 **0 条**；封存后当前 **655** | 时点错位 |
| run 目录 | 189 | **190** | 近似 |
| 提案 JSON | 2582→3592 | **3,651** | 同量级 |
| Jev 预筛 | 「只影响调度分、不阻断」 | 负向**只进排序**（`:1216-1250` 改 `_score`）；正向 `+10×plausibility` 进质量门。实测 `quality_below_threshold` 仅 42/3597 | 「不阻断」在生产上成立，结构性描述需修正 |
| schema 双轨 | v1 legacy / v2 | **235/235 全为 v2**，0 行含 `ev`；v1 分支是死代码 | 推翻 |
| `_has_prior_failure` | 按 (symbol, cov) 配对 | **单键 OR** | 推翻（污染半径更大） |
| 三事故根因 | 同一根因 | 三个独立根因 | 推翻 |

---

## 7. 未核实项

1. `daily_update.py` 是否配置定时任务、TqSdk 权限是否在线（影响 P0-3 的数据就绪条件）
2. supervisor 中是否存在动态 import 引入的确认派发逻辑（静态 grep 无果，未排除）
3. peer proposal 中是否存在生成 `run_mode: confirmation` 的逻辑（`harvest_proposals` 未见）
4. checkpoint resume 在确认模式下的实测表现（无确认运行记录，无法验证）
5. `n_eff = fallback_n_eff` 的常数映射是否影响 `gate_pass`（`min_n_eff=50` 而实测恒 73，故当前不构成约束；但若 `n` 变小则该门会静默失效）

---

*本报告由 6 路并行只读代码审计生成。全部断言均锚定 `文件:行号` 或磁盘实测；未能一手复核的数字已明确标注为二手或无法核实。*