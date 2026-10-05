# 正期望协变量搜索 Spec

- **spec 日期**：2026-10-05（同日两次修订）
- **对照代码**：WSL `/home/abug/timesfm`，初稿与修订均对照 HEAD `9dccbbc`
- **上位**：`docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15）；Q7 备忘录 `docs/superpowers/reports/2026-09-30-q7-target-effect-power-memo.md`（宿主裁定 a′：Δ\*=0.08，单侧 α=0.05，功效 80%）
- **文档标记**：`[事实]` 可回代码核验 · `[规定]` 本文件的要求 · `[待决]` 需宿主裁定后才能打开 · `[决定]` 已定
- **状态**：待宿主批准。批准前不改收割、不改确认、不重启监督环。
- **修订记录**：
  - **修订 1（同日，审核修订）**：P1 裁定为途径 (a)：晋升在 `preregistry.jsonl` 追加行（S5、§4、§6.6 相应改写）；新增 `shadow` 档与 §6.9 同伴教学；§6.5 补家族死亡停止；§6.2 原因表补 `search_root_while_tree_active`、`search_parent_not_near_miss`、`search_role_conflict`；§6.3 数例钉 `T=588` 并落 `delta_post_shrunk`；§6.4 补现任序列不可得=fail；§6.6 条件 6 补 `eval_end_ts` fail-closed；§3 补 `success_delta` 与 `no_success_delta`；S4 交叉引用修正。
  - **修订 2（同日，宿主落地指示）**：§3 快照行修正——族线索现状已是「通过数/总数」（`- 族: pass/total gate_pass`），非「只打印通过次数」，审核漏检一并勘正；§6.8 补族线索「仅当前协议」注记与不另做摘要文件；§4 补新指标不自动入池、公式搜索拒绝证据（arXiv 记账后预算 100 条全拒、前视泄漏非缩水可挡）、序贯 p 值/历史先验/横截面双重选择三条不接；§8 挂接实施计划。

> 正期望在本文件里只有一个意思：扣掉已经做过的尝试、和同一品种现任协变量的重复、以及挑选造成的上偏之后，再付一次慢环或一次确认的成本，期望增量仍然为正。它不是「这条协变量以后能赚钱」。

---

## 1. 目的与完成标准

### 1.1 目的

现在的发掘是两个同伴在 31 个活跃协变量上写机制。收割负责把不合格提案挡在慢环外面，慢环负责对无协变量基准做方向准确率和 DM。下一次试什么，没有父节点，也没有「再试一次是否还值」的停止规则。

本文件给这条搜索加一套事前承诺：每个品种、每个族最多一棵小树；子节点必须指向已经裁决的父节点；晋升确认用缩水后的增量，并且增量必须是现任协变量没有解释掉的那一截。公式搜索（遗传规划、表达式树、强化学习挖因子）不在本文件范围内。

### 1.2 完成标准

| # | 标准 | 判据 |
|---|---|---|
| S1 | 开关默认关闭 | `scripts/praxist_goal.yaml` 无 `search_policy` 或其值为 `off` 时，收割行为与今日相同；`shadow` 只增加「本会拒绝」的计数与决策日志，不改入队结果，不写 `search_commitments.jsonl` |
| S2 | 打开后，子节点必须有已裁决的父节点 | 带 `search_role=exploit` 或 `falsifier` 但父节点不在本树已裁决集合里的提案，收割拒绝，不入队 |
| S3 | 一棵树的慢环次数不超过预算 | 同一 `tree_id` 已有 4 条当前协议 `status=ok` 裁决后再来的提案被拒绝 |
| S4 | 缩水公式可复算 | 第 6.3 节两个数例的 `δ_post` 与「是否小于锁定样本量」由测试锁定（断言按 `T=588` 钉死） |
| S5 | 晋升不改 `gate_pass`；预注册只追加 | 增量检验和缩水只决定能不能把已有预注册的品种送进确认。既有 2 行（jd、sr）语义不变；每次晋升恰好追加 1 行（事前锁 n、`confirm_from_ts`、协变量与参数指纹）；`preregistry.jsonl` 行数 = 2 + 晋升次数 |
| S6 | 现任存在时，只打败基准不算增量 | 同一品种、当前协议、`gate_pass=True` 的裁决里有现任时，对现任的配对 DM 未过则不得晋升 |
| S7 | 锁定行为不变 | 第 4 节的每一行在打开开关之后仍然成立 |

---

## 2. 依据

这些论文说明为什么「样本里最好的那一次」不能直接当期望值。本文件只取它们的决策规则，不把论文里的横截面回归搬进期货方向预测。

| 文献 | 用哪一条 |
|---|---|
| Harvey、Liu、Zhu，2016，《Review of Financial Studies》29(1): 5–68 | 试过的次数要进门槛。单独一次 t>2 不是新因子的标准 |
| Feng、Giglio、Xiu，2020，《Journal of Finance》75(3): 1327–1370 | 新因子要在已有因子之外仍有增量。他们用双重选择处理「控制组本身也是挑出来的」 |
| Bailey、López de Prado，2014，《Journal of Portfolio Management》40(5): 94–107 | 被挑中的成绩先缩水，再和「零本事时 N 次里的最好成绩」比 |
| White，2000，Reality Check；Hansen，2005，SPA | 问的是这一批里的最好者有没有超过基准，不是单独看冠军 |
| Yu 等，2023，KDD，AlphaGen | 反例。表达式树把尝试次数扩到上万，样本内信息系数不是扣过尝试次数的期望值 |

已有的 Benjamini–Hochberg 封账继续用于确认族，不在探索树上再做一次。Q7 的 Δ\*=0.08 继续是确认检验的功效目标，不是探索硬门，也不是先验均值。

---

## 3. 核实结论 `[事实]`

写本文件时，活仓里没有协变量搜索树。

| 环节 | 现状 |
|---|---|
| 提案 | `schema=fm.hypothesis_proposal.v1`。字段是 `symbol`、`cov_override`、`covariate_family`、`mechanism`、`symbol_fit`、`predicted_direction`、`kill_condition`、`promote_condition`、`failure_delta`、`success_delta`、`proposal_id`。没有父节点 |
| 菜单 | `task_FM/config/covariate_pool.json` 有 31 个 `active`：动量 20、期限结构 4、库存 3、波动率 3、日历 1。`macro_sentiment` 在族名单里，池中没有成员 |
| 新指标 | `new_cov_<name>.json` 只进 `covariate_backlog.jsonl`，不入评估队列 |
| 面板 | `task_FM/task.yaml` 的 `panel_topology:fm_two_peer`，`peer_role_rotation` 为 `exploit`、`falsifier`。`graph_maintainers` 为空。`evaluation` 下没有 `frontier_lanes` |
| 收割 | `harvest_proposals` 拒绝不在池中、机制过短、缺少 `failure_delta`、品种死亡或冻结、重复、以及成功门 `no_success_delta`（已有 `gate_pass=True` 的 (symbol, cov) 组合复跑缺 `success_delta`）。选座 `survivors_per_cycle` 以目标文件为准，当前为 3。优先品种为空，同档内先按族各给一席 |
| 快照 | `materialize_known_verdicts` 写 `known_verdicts.inc.md`，由 `prompt_base.jinja2` include。族线索已是「通过数/总数」（`- 族: pass/total gate_pass`，如 `- momentum: 30/63 gate_pass`）：分母为当前协议快照内该族全部裁决（含描述性），分子为 `gate_pass=True`；`n_ok < 10` 的族带 `low-n` 标记。快照本身已滤旧协议 |
| 近失 | `_effective_clue_lines` 的近失是 `0.49 <= dir_acc < effective_min`，最多 12 条 |
| 检验 | 配对 DM 与功效规划的唯一实现是 `cascade/statistical_tests.py` 的 `compute_hac_se` 和 `n_required`。途径 B 用 `compute_hac_se` 的长程方差当 `var_d`，`vif=1`，因为长程方差已经含自相关。禁止再乘一个 VIF |
| 裁决 | `aligned_verdicts.jsonl` 只由慢环追加。当前协议行有 `dir_acc`、`baseline_dir_acc`、`p_value`、`dm_status`、`eval_end_ts`。没有 `delta_ci`。`eval_end_ts` 在首跑（无历史 checkpoint）时为 `null`，锚在 checkpoint 行里 |
| 确认 | 过门的严格定义仍是 `pass_variants()`：确认运行、`gate_pass`、`fdr_pass`、`p_value` 非空、`pairing_valid`、`missingness_admissible`、`dm_status` 为 `ok` 或 `set_mismatch_ok`。预注册样本量只锁定了 jd 1,199 和 sr 986。确认派发按行键控：`due_confirmations` 取行内 `cov_fingerprint.keys` 减基础协变量（`daily_slope`）恰好一个的协变量派发，行内键数不满足则整行跳过 |
| 自适应门 | `effective_min = max(0.50, min(0.52, baseline_dir_acc))`。探索期过滤器，不是成功 |

---

## 4. 非目标

| 不做的事 | 理由 |
|---|---|
| 不改 `gate()` 和自适应门 | v15 与 Q7。探索硬门仍只筛质量 |
| 不改 `cohort_size=2` 和 `survivors_per_cycle` | 席位数量不变。变的是哪些提案有资格占席 |
| 不改 `_has_prior_failure` 的「品种或协变量」 | 失败侧匹配保持 |
| 不改家族死亡的 `gate_pass` 与 `min_ok=4` | 死亡是另一条停止规则，§6.5 条件 4 只消费它的结论 |
| 不为探索追加预注册 | 没有锁定样本量的品种可以探索，不能晋升。`preregistry.jsonl` 的追加只发生在晋升时点（6.6 全部门槛通过），且 `n_confirm_required` 继承品种已锁定值——探索不能发明预算，只能重定向已锁定预算的用途 |
| 不改 Δ\*=0.08、单侧 0.05、功效 80%、协议指纹 | Q7 与 v4 协议 |
| 不改成功条件 `all_symbols_pass_phase1` | 本文件不发明新的通过线 |
| 不建第二份统计表 | 方向准确率和 DM 仍只住在裁决文件里 |
| 新指标不自动入池 | `new_cov_<name>.json` 继续只进 `covariate_backlog.jsonl`；人实现并标 `active` 之后才允许被提议。对象始终是现有池子里的 31 个活跃协变量 |
| 不做遗传规划、蒙特卡洛公式树、AlphaGen 一类表达式搜索 | 尝试次数会把期望增量打成负数：arXiv 上把尝试次数记账之后，预算放到 100 条的公式搜索全部被拒绝；前视泄漏也不是缩水能挡住的 |
| 不接始终有效的序贯 p 值 | 确认窗口是 `eval_end_ts` 之后另开的锁定样本，固定样本的 `n_required` 对得上这一段；序贯检验是另一套功效框架，不在本文件引入 |
| 不用历史实验估计先验 | `τ=0.04` 写死。历史实验是挑选出来的，从它们估出的先验会把上偏请回来 |
| 不接横截面上的双重选择 | FGX 的双重选择为横截面因子回归设计；单品种时间序列上的增量由 §6.4 的现有配对 DM 承担，不另建一套回归 |
| 不打开框架的 `graph_maintainers` 或 `frontier_lanes` | 不改 `.venv` 里的 Praxist |
| 不在监督环运行时改活仓代码 | 实施放在工作树，合入后核对指纹再重启 |

---

## 5. 定义 `[规定]`

增量：

```text
δ = dir_acc - baseline_dir_acc
```

标准误用该变体自己的配对差序列 `d_t`，与 DM 同一家：

```text
se = sqrt(compute_hac_se(d_t) / T)
```

`T` 是这条差序列的长度。`compute_hac_se` 返回的是长程方差，不是标准误。`T < 2` 或长程方差不是有限正数时，本文件的晋升与停止都失败关闭，不换一套标准误。

现任：同一品种、当前协议指纹、`status=ok`、`gate_pass=True` 的裁决里，`δ` 最大的一条。取 `gate_pass` 而不取 `pass_variants()` 的严格过门，是因为探索样本上不重做 BH：一个 `fdr_pass=False` 的现任仍有资格当增量基准——增量基准从宽，挡晋升从严。没有这样的裁决时，现任的 `δ` 记为 0，现任比较视为不需要。

树：一个 `tree_id`。同一品种、同一 `covariate_family` 同时只允许一棵未停止的树。

预算 `B = 4`。计入预算的是这棵树上已经写下的当前协议 `status=ok` 裁决，不是提案张数。`no_data` 不占预算。

先验标准差 `τ = 0.04`。这是打开开关之前写死的数，不用本族裁决去估计。打开之后不得改。

---

## 6. 设计

### 6.1 开关 `[待决]`

`scripts/praxist_goal.yaml` 增加：

```yaml
search_policy: off   # off | shadow | enforce
```

- `off` 是批准前和批准后的默认值。收割行为与今日相同。
- `shadow`：树检查照常求值，「本会拒绝的原因」只进拒绝计数与决策日志，提案照常走后续管道；不写 `search_commitments.jsonl`，不建树。用于 `enforce` 打开前观测同伴是否学会新字段（重点看 `search_role_missing` 占比）。
- `enforce`：第 6.2 节起的拒绝生效。

宿主把该键改成 `shadow` 或 `enforce` 之后对应档位才生效。本文件不授权代理自行改这一键。

### 6.2 提案如何进入一棵树 `[规定]`

`enforce` 打开后，提案在原有字段之外必须带：

| 字段 | 取值 |
|---|---|
| `search_role` | `root`、`exploit`、`falsifier` 之一 |
| `search_parent_id` | `root` 必须为空。另外两个角色必须是本树一条已裁决节点的 `variant_id` |
| `tree_id` | 根提案由收割写成 `symbol` 加族加根提案 `proposal_id`。子提案必须带同一个 `tree_id` |

三个新字段是 `fm.hypothesis_proposal.v1` 的可选字段，schema 版本不升。`off` 与 `shadow` 下缺字段不构成拒绝。

树资格检查在收割管道最前，先于去重、成功门（`no_success_delta`）、池与机制长度检查；同一提案命中多个原因时按检查顺序记第一个。

`enforce` 下，若存在未停止的树，收割先选定「本轮扩展树」：未停止的树里 `event=accept` 最早的一棵，同时刻按 `tree_id` 字典序。本轮两份提案必须属于本轮扩展树。不存在未停止的树时才接受 `root`。

收割新增的拒绝原因只追加计数，不改原有原因的判据：

| 原因 | 条件 |
|---|---|
| `search_role_missing` | 三个新字段缺一，或 `search_role` 不是上面三个值 |
| `search_tree_closed` | `tree_id` 已有停止记录（含子提案指向已停止的树） |
| `search_budget_exhausted` | 本树 `status=ok` 裁决数已经达到 4 |
| `search_tree_busy` | 同一品种、同一族已有另一棵未停止的树；或子提案的 `tree_id` 属于另一棵未停止、但不是本轮扩展树的树；或 `tree_id` 不属于任何已知树 |
| `search_parent_missing` | 子角色的父节点不是本树已有的当前协议 `status=ok` 裁决 |
| `search_parent_not_near_miss` | `exploit` 的父节点不满足近失条件 `0.49 <= dir_acc < effective_min` |
| `search_falsifier_same_cov` | `falsifier` 的 `cov_override` 与父节点相同 |
| `search_root_while_tree_active` | 存在未停止的树时来了 `root` 提案 |
| `search_role_conflict` | 本轮扩展树的同角色合法提案已有份，后到的同角色提案按收割处理顺序拒绝 |

`exploit` 只允许从父节点的近失往下做：父节点满足 `0.49 <= dir_acc < effective_min`，子节点的 `cov_override` 仍在活跃池里，可以与父节点不同。`falsifier` 必须同一品种、同一族、不同的活跃协变量，机制文本写明它要否定的父节点句子。池子里没有第二个协变量时，这一席留空，收割不用别的族补位。

根提案仍走今天的池子、机制长度和 `failure_delta` 规则。根不是近失的延续，近失条件不约束根。同一轮收割内，先处理的 `root` 先建树，后到的同品种同族 `root` 按 `search_tree_busy` 拒绝。

两个同伴席位不变。打开开关之后，若本轮有未停止的树，两份新提案必须是本轮扩展树的 `exploit` 与 `falsifier`，不能再平行开一个无关的根。没有未停止的树时，才允许各写一个 `root`。选座名额仍是 3，不够 3 份合法提案时不回填非法提案。

### 6.3 缩水 `[规定]`

只在裁决已经是当前协议 `status=ok`、并且 `se` 可算时计算：

```text
δ_post = δ × τ² / (τ² + se²)
```

`τ = 0.04`，所以 `τ² = 0.0016`。`δ_post` 与 `δ` 同号，绝对值更小。不估计 `τ`。

`δ_post` 在裁决落账时写入裁决行新字段 `delta_post_shrunk`（与 `incremental_vs_incumbent` 同批落账）。`se` 不可算时该字段为 `null`，不参与 6.6 条件 1 的树内比较与 6.5 条件 3 的上界比较。

数例（测试锁定 `δ_post` 与样本量比较，`T` 钉死 588；`var_d` 按 §5 的关系 `var_d = se²·T` 取）：

| | δ | se | T | var_d | δ_post | 后续功效判断 |
|---|---|---|---|---|---|---|
| 不晋升 | 0.06 | 0.03 | 588 | 0.5292 | 0.0384 | `n_required` = 2,220，大于 jd 的 1,199 |
| 可进入晋升判断 | 0.12 | 0.02 | 588 | 0.2352 | 0.096 | `n_required` = 158，小于 1,199 |

`T` 取 588（当前探索窗样本量）。两例结论在 `T ∈ [588, 2000]` 内不变：例 1 翻转需要 `T < 318`，例 2 翻转需要 `T > 4,466`（`n_required` 生产函数实算）。

`n_required` 的调用是：

```text
n_required(var_d=compute_hac_se(d_t), vif=1, z_alpha=1.645, z_beta=0.842, delta=δ_post)
```

`δ_post <= 0` 时不调用 `n_required`，直接不晋升。`var_d` 用长程方差本身，`vif` 保持 1。

### 6.4 对现任的增量 `[规定]`

现任存在时，慢环在写完对基准的 DM 之后，用同一套 `diebold_mariano` 与配对规则，再算新变体对现任的配对差。差的定义是新变体的方向命中减去现任的方向命中，只在共同 cutoff 上。

增量通过，当且仅当下面同时成立：共同样本满足 v15 的 `pairing_valid` 与 `missingness_admissible`，`dm_status` 为 `ok` 或 `set_mismatch_ok`，配对差均值大于 0，单侧 `p_value < 0.05`。缺现任时，这一条视为通过。

现任裁决存在、但其配对序列不可得（现任 checkpoint 缺失，或损坏被文件级弃读）时，`incremental_vs_incumbent` 记 `fail`——保守方向是不晋升。「缺现任视为通过」只覆盖没有现任裁决的情形，不覆盖现任序列不可得。

这个结果写入裁决的新字段 `incremental_vs_incumbent`，取值为 `pass`、`fail` 或 `not_applicable`。它不参与 `gate()`，不改 `gate_pass`，不改 `fdr_pass`。

### 6.5 停止 `[规定]`

每条相关裁决落账后，监督环给这棵树追加一条停止判断。停止条件命中任一即停止：

1. 本树 `status=ok` 裁决数达到 4。
2. 本树任一节点已经满足第 6.6 节的晋升条件。晋升之后不再扩展。
3. 本树已裁决节点里 `δ` 最大者的上界，低于现任下界。上界是 `δ + 1.645 × se`，下界是 `δ - 1.645 × se`。没有现任时，现任下界是 0。`se` 不可算的节点不参与这条比较。
4. 该树所在族死亡（家族死亡判据照旧：`gate_pass` 与 `min_ok=4`）。监督环为该族所有未停止的树补写停止记录，停止原因记 `family_dead`。

停止写入 `task_FM/config/search_commitments.jsonl` 的一条 `event=stop`，停止原因取 `budget`、`promoted`、`dominated`、`family_dead` 之一。停止后的提案按 `search_tree_closed` 拒绝。

### 6.6 晋升 `[规定]`

晋升不是新的成功定义。它只决定要不要把这个节点交给现有的确认入队。全部满足才晋升：

1. 节点属于一棵尚未因预算或上界规则停止的树，且是该树 `delta_post_shrunk` 最大的 `status=ok` 节点（`null` 不参与比较）。
2. `δ_post > 0`，并且第 6.3 节的 `n_required` 小于或等于该品种已锁定的确认样本量。
3. 该品种在 `preregistry.jsonl` 里已有锁定样本量（今日仅 jd 1,199 与 sr 986）。没有则不晋升——晋升不发明预算，只能重定向已锁定预算的用途。
4. `incremental_vs_incumbent` 为 `pass` 或 `not_applicable`。
5. 探索期的 `gate_pass` 仍为真。硬门继续用现在的自适应阈值。
6. 确认窗口的起点不早于选出该节点的那条裁决的 `eval_end_ts`。已有的 `confirm_from_ts` 若更晚，以更晚者为准。`eval_end_ts` 缺失（首跑无历史 checkpoint 的已知边界）时不晋升，fail-closed；T2d 落地（裁决行 `eval_end_ts` 走 checkpoint 兜底）之后本条自然不触发。

今天只有 jd 与 sr 有锁定样本量，因此打开开关之后也只有这两个品种能够晋升。其余品种的树可以探索、必须停止，但不能进入确认。

晋升记录写 `event=promote`，同时为该节点 `(symbol, cov_override)` 在 `preregistry.jsonl` 追加恰好一行：

- `n_confirm_required` 继承该品种已锁定值（jd 1,199 / sr 986），不重新计算；
- `confirm_from_ts` 按条件 6 的较晚者；
- `delta_star=0.08`、`power=0.8`、`alpha=0.05` 照 Q7 a′；`kill_condition`/`promote_condition` 照既有行（`d_mean` 对 0 与 0.08）；
- `var_lr` 取该节点 `d_t` 的 `compute_hac_se`；
- `cov_fingerprint`（`keys = ["daily_slope", cov_override]`，与既有行键型一致，满足确认派发「减基础协变量恰好一个」的硬约束）、`model_fingerprint`、`predict_params`、`horizon` 在追加时点锁定；
- `mechanism` 与 `predicted_direction` 抄自该节点的提案。

追加行同样只追加不改。确认派发走既有 `due_confirmations` 的按行键控，`BH-FDR`、`pass_variants()` 和家族封账保持原样。探索样本上的 `p_value` 不得被写成确认结论。

### 6.7 记录 `[规定]`

`task_FM/config/search_commitments.jsonl` 只追加，不改历史行。它记录的是承诺和决定：`tree_id`、`proposal_id`、`variant_id`、`search_role`、`search_parent_id`、`event`（`accept`、`stop`、`promote`）、`B`、`τ`、停止原因、晋升时的 `δ_post` 与 `n_required`。

方向准确率、DM 和 `gate_pass` 不在这里重写一份。审计时用 `variant_id` 回裁决文件。这个文件不是统计事实源。

### 6.8 同伴看见什么 `[规定]`

`materialize_known_verdicts` 增加一节「未停止的树」：`tree_id`、品种、族、已用次数、预算 4、父节点 `variant_id`、该父节点是否近失、是否为本轮扩展树。存在本轮扩展树时，这一节末尾追加一句：本轮两份提案应为本轮扩展树的 `exploit` 与 `falsifier`。不写标准误公式，不写代码行号。没有未停止的树时，这一节写「无」，避免同伴沿用上一轮的父节点。

族线索保持「通过数/总数」的现行写法（`- 族: pass/total gate_pass`），节首或行尾注明：仅当前协议，旧协议已滤除；分母含描述性裁决。不另做一份摘要文件，不另开展示通道。这一条与树节、§6.9 的 prompt 教学同批落地。

### 6.9 同伴如何学会新字段 `[规定]`

`prompt_base.jinja2` 的提案 schema 段落加入三个可选字段的说明与示例：`search_role` 取 `root`、`exploit`、`falsifier` 之一；`root` 的 `search_parent_id` 留空；子角色的 `search_parent_id` 填 `known_verdicts` 树节给出的父节点 `variant_id`；`tree_id` 照抄该树节。既有字段（含 `success_delta`）的说明保持不变。schema 版本仍为 `fm.hypothesis_proposal.v1`。

`off` 与 `shadow` 下同伴不写新字段不受罚；`enforce` 下缺字段按 `search_role_missing` 拒绝。因此 §6.9 的 prompt 教学必须先于或同时于 `enforce` 打开合入，§8 的 `shadow` 轮就是给这一条验收的缓冲。

---

## 7. 测试

实施时至少锁定下面这些行为。数例用第 6.3 节的输入（`T=588` 钉死），断言走 `n_required` 与 `compute_hac_se` 的生产函数，不在测试里另写方差。

| # | 断言 |
|---|---|
| T1 | `search_policy` 缺省或 `off` 时，一份没有新字段的旧提案仍按今天的规则入队或拒绝；`shadow` 时树检查照常求值，入队结果与 `off` 相同，拒绝计数与决策日志多出「本会拒绝」记录，`search_commitments.jsonl` 无写入 |
| T2 | `enforce` 下，子角色没有已裁决父节点 → `search_parent_missing`，队列长度不变 |
| T3 | 同一树已有 4 条 `status=ok` → 下一份提案 `search_budget_exhausted` |
| T4 | 同一品种同一族的第二棵根 → `search_tree_busy` |
| T5 | `δ=0.06, se=0.03`，按 `T=588` 取 `var_d=se²·T=0.5292`，得 `δ_post=0.0384`，`n_required` 大于 1,199，不晋升 |
| T6 | `δ=0.12, se=0.02`，按 `T=588` 取 `var_d=0.2352`，得 `δ_post=0.096`，`n_required` 小于 1,199；其余晋升条件不满足时仍不晋升 |
| T7 | 现任存在且增量 DM 失败时，`gate_pass` 保持慢环原值，晋升不发生 |
| T8 | 晋升恰好追加一行 `preregistry.jsonl`；既有 2 行内容不变；追加行 `cov_fingerprint.keys` 减 `daily_slope` 恰好 1 个 |
| T9 | 最好节点的上界低于现任下界时写入 `event=stop`，其后的子提案被 `search_tree_closed` 拒绝 |
| T10 | `vif` 与长程方差不会同时进入同一次 `n_required`。途径 B 的调用 `vif=1` |
| T11 | 存在未停止的树时 `root` 提案 → `search_root_while_tree_active`，队列长度不变 |
| T12 | `exploit` 的父节点非近失 → `search_parent_not_near_miss` |
| T13 | 家族死亡 → 该族活跃树补写 `event=stop`（原因 `family_dead`），其后的子提案按 `search_tree_closed` 拒绝 |
| T14 | 现任裁决在而其 checkpoint 损坏（文件级弃读）→ `incremental_vs_incumbent=fail`，晋升不发生 |
| T15 | 晋升追加的 prereg 行被 `due_confirmations` 正常派发（端到端：可构造 `confirmation_queue_row`，cov 与 n 取自追加行） |
| T16 | 选出节点的 `eval_end_ts` 缺失 → 晋升 fail-closed（6.6 条件 6） |
| T17 | 多树并存时本轮扩展树为 `event=accept` 最早者（平手按 `tree_id` 字典序）；指向其他未停止树的子提案按 `search_tree_busy` 拒绝 |
| T18 | 本轮扩展树同角色的第二份合法提案 → `search_role_conflict` |

---

## 8. 待决

只有一件需要宿主另行说「打开」：把 `search_policy` 从 `off` 改成 `enforce`。建议路径是先 `shadow` 至少一轮（§6.1），观测 `search_role_missing` 占比确认同伴已学会新字段，再改 `enforce`。

实施顺序：T2d（裁决行 `eval_end_ts` 的 checkpoint 兜底）先于本文件实施落地；在此之前 6.6 条件 6 按 fail-closed 执行。落地任务拆解、部署步骤与验收判据见 `docs/superpowers/plans/2026-10-05-positive-ev-factor-search-plan.md`。

`B=4` 和 `τ=0.04` 是本文件的规定，不是打开之后可以按结果再调的参数。要改这两个数，先改本文件并重新批准，且不得发生在第一行 `search_commitments.jsonl` 写入之后。

---

## 9. 权威

冲突时的顺序：v15，然后 Q7 备忘录的 a′，然后本文件。本文件与 v15 对 `gate()`、预注册、协议指纹或 `pass_variants()` 的读法不一致时，以 v15 和 Q7 为准，本文件的对应句子作废而不是「各用一半」。
