# 提案生命周期管理规范（Proposal Lifecycle Management Spec）

> **状态**: **Frozen**（二审修订完成，可开 Phase 1，2026-10-18）
> **日期**: 2026-10-18
> **对照代码**: WSL `/home/abug/timesfm` master（截至 2026-10-18）
> **上位 spec**: `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15）
> **相关 spec**: `docs/superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md`（Peer 记忆回路）
> **文档标记**: `[事实]` 可回代码核验 · `[规定]` 本文件的要求 · `[待决]` 需宿主裁定 · `[决定]` 已定

---

## 1. 概述

### 1.1 目标

建立 FM_a 提案（Proposal）从生成到裁决的**显式状态管理、版本控制、跨 Run 反馈、关系追踪**的完整规范，使：

1. Peer agent 每次提案能参考历史裁决结果（不再是盲猜）
2. 宿主能追踪同一提案跨多个 run 的演化
3. 提案的搜索树关系（parent/child/sibling）可追溯
4. 入队后的提案可撤回、可重跑、可降级

### 1.2 范围

本规范覆盖以下提案管理环节：

| 环节 | 当前状态 | 本规范覆盖 |
|------|---------|-----------|
| 提案生成 | peer agent 生成 proposals/*.json | 增强：版本控制 |
| Prescreen 预筛 | Laya prescreen .prescreen.json | 增强：状态字段 |
| 质量门 + 树守卫 | harvest_proposals 过滤 | 增强：拒收标注 |
| 入队 | aligned_pending.jsonl | 增强：显式 status |
| 慢环评估 | aligned_slow_loop.py checkpoints | 增强：evaluating 状态 |
| 裁决 | aligned_verdicts.jsonl | 增强：version 字段 |
| 物化证据 | known_verdicts.inc.md + known_rejections.inc.md | 增强：反馈格式 |
| 跨 Run 反馈 | 未实现 | **新增** |
| 版本控制 | 未实现 | **新增** |
| 关系追踪 | search_parent_id/tree_id 存在但未使用 | **新增** |
| 撤回机制 | 未实现 | **新增** |

### 1.3 术语

| 术语 | 定义 |
|------|------|
| Proposal | peer agent 生成的假设提案（fm.hypothesis_proposal.v1/v2 schema） |
| Variant | 经过身份链（symbol + family + experiment_fp）确定身份的提案变体 |
| Run | 一次 supervisor 运行周期（从启动到重启） |
| Cycle / Generation | peer agent 的一次迭代（gen0, gen1, gen2...） |
| Verdict | 慢环回测后的裁决结果（fm.aligned_verdict.v2 schema） |
| Prescreen | Laya 预筛结果（.prescreen.json） |
| Queue | aligned_pending.jsonl 入队记录 |
| Search Tree | 正期望协变量搜索的树结构（root / exploit/falsifier） |

---

## 2. 现状分析

### 2.1 已有机制（不改变）

以下机制已经正常工作，本规范不修改其核心逻辑：

**2.1.1 提案生成**
- 路径：task_FM/experiments/run_*/results/gen_*/genN_peerM/proposals/*.json
- Schema：fm.hypothesis_proposal.v1（当前）；本规范引入 v2 并兼容 v1
- 字段：proposal_id, symbol, cov_override, covariate_family, mechanism, symbol_fit, predicted_direction, kill_condition, promote_condition
- 代码：peer agent 通过 prompt 生成

**2.1.2 Prescreen 预筛**
- 路径：*.prescreen.json（同目录，同名替换后缀）
- 异步触发：sup_harvest.py:_prescreen_async()
- 字段：status ∈ {success, degraded, error}, variant_id, mechanism_plausibility, novelty, effect_size, skip_suggested
- 代码：`cascade/typesafe_prescreen.py` `PrescreenStatus` 类型

**2.1.3 质量门 + 树守卫拒绝码**

> [注] 历史俗称「18 道质量门」，实际拒绝码集合已超出 18 个。以下以代码为准，不按数量命名。

**质量门拒绝码**（`sup_harvest.py` `_reject("...")` 字面量）：

| 拒绝码 | 含义 |
|--------|------|
| unparseable_json | JSON 无法解析 |
| schema_mismatch | schema 字段不在接受集合 |
| missing_symbol_or_cov | 缺少 symbol 或 cov_override |
| cov_archived | 协变量已归档 |
| cov_not_in_active_pool | 协变量不在活跃池 |
| no_current_baseline | 无当前基线 |
| mechanism_too_short | mechanism 描述过短 |
| symbol_dead | 品种已退市 |
| symbol_hold | 品种停牌 |
| family_unresolved | 家族无法解析 |
| family_dead | 家族已废弃 |
| experiment_fp_unavailable | 实验指纹不可用 |
| no_failure_delta | 无失效差异 |
| dedup | variant_id 重复 |
| sector_blocked | 板块被屏蔽 |
| cov_cross_fail | 交叉验证失败 |
| quality_below_threshold | 质量分数低于阈值 |
| no_success_delta | 无成功差异（_success_delta_gate 动态触发） |
| decision_abandon | 决策放弃 |
| backlog_dup | 积压去重 |
| symbol_not_allowed | 品种不允许 |

**树守卫拒绝码**（enforce 模式下 `search_trees.py` 返回值）：

| 拒绝码 | 含义 |
|--------|------|
| search_role_missing | 缺少 search_role |
| search_tree_closed | 搜索树已关闭 |
| search_tree_busy | 搜索树忙碌 |
| search_root_while_tree_active | 收割开始时存在未停止的树 |
| search_budget_exhausted | 搜索预算耗尽 |
| search_parent_missing | 父节点不存在（exploit/falsifier 通用） |
| search_parent_not_near_miss | 父节点非 near-miss（exploit 专用） |
| search_falsifier_same_cov | falsifier 使用了与父相同的协变量（falsifier 专用） |
| search_role_conflict | 角色冲突 |

> [事实] 精确集合以 `sup_harvest.py` 中 `_reject()` 字面量 + `search_trees.py` 守卫返回值为准，本表为阅读参考。

**2.1.4 入队**
- 路径：data/cache/aligned_pending.jsonl
- 字段（QUEUE_FIELDS）：variant_id, symbol, cov_override, max_points, stage, checkpoint_path, enqueued_at, src_run
- 附加字段（peer 提案）：source, quality_score, sector
- 搜索树字段（enforce 模式）：search_role, search_parent_id, tree_id
- 代码：`queue_enqueue` 不裁剪到 QUEUE_FIELDS，整行 append

**2.1.5 慢环评估**
- 代码：aligned_slow_loop.py
- 输出：data/cache/aligned_checkpoints/{variant_id}.jsonl 写入 aligned_verdicts.jsonl
- Verdict Schema：fm.aligned_verdict.v2
- **复测语义**：`_maybe_enqueue_retests`（`sup_loops.py` @150）是**样本近失误复测旁路**，将 dead variant 重新入队做同 variant_id 复测。**这不是提案 lifecycle 状态转换**，不创建 `retried` 状态。

**2.1.6 物化证据**
- known_verdicts.inc.md：成功/失败裁决视图（sup_evidence.py:materialize_known_verdicts）
- known_rejections.inc.md：**拒收计数统计**（aggregate_rejection_stats.py 读 `.omc/supervisor_decisions.jsonl` 聚合）
  - > [决定] 生产已有计数级拒收反馈（D1 已实施）。本规范的 `rejected_proposals.jsonl` 是 per-proposal 因果增强，不是重复建设。
- Peer 读取：task_FM/prompt_base.jinja2 include 这些 .inc.md（行 114-115）

### 2.2 缺失环节（本规范要解决）

| # | 缺失 | 影响 | 优先级 |
|---|------|------|--------|
| M1 | 跨 Run 反馈通道：peer 不知道历史 cycle 的实际裁决结果 | peer 重复提已被否决的组合 | P0 |
| M2 | 提案无显式 status 字段：状态隐含在文件存在性和队列位置 | 无法追踪已撤回、已重跑等中间态 | P0 |
| M3 | 同一 proposal_id 跨 run 多次生成时无版本追踪 | 无法分辨修正版 vs 原版重提 | P1 |
| M4 | search_parent_id 和 tree_id 存在但 peer 从未使用 | 搜索树关系断裂；与 enforce 模式下的 prompt 要求不一致 | P1 |
| M5 | 入队后无法撤回 | 错误或过时的提案浪费慢环算力 | P2 |

---

## 3. 设计方案

### 3.1 提案身份标识

#### 3.1.1 Proposal ID

**现状**：proposal_id 由 peer agent 自定，通常为 {symbol}_{cov_override} 格式（如 m_crack_spread_slope）。

**[规定]** 维持现状格式，不强制改名。但增加以下约束：

- proposal_id 在同一个 run 的同一个 peer 的同一代（generation）内必须唯一
- proposal_id 允许跨 run 重复（同一假设的多次尝试）
- 禁止使用 UUID 或时间戳作为 proposal_id（peer 必须用有意义的名称）

#### 3.1.2 Variant ID

**现状**（W6.4 契约）：variant_id = {symbol}_{cov_family}_{experiment_fp[:12]}，由 experiment_fingerprint.build_variant_id() 生成。

**[规定]** 维持现状。variant_id 是实验身份，不是提案身份。同一个 proposal_id 在不同 run 可能产生不同 variant_id（因为协变量指纹可能因数据更新而变）。

#### 3.1.3 Version 字段（新增）

**[规定]** 在 proposal JSON 中增加可选 version 字段。version 从 1 开始，默认值为 1（不写 = 1）。peer agent 重提同一 proposal_id 时应递增 version。version_note 可选，描述本次变更。schema bump 到 fm.hypothesis_proposal.v2（向后兼容：v1 的 version 默认为 1）。

**版本递增规则**：

| 场景 | version 变化 |
|------|-------------|
| 首次提案 | 1 |
| 同一 proposal_id 被拒后重提（改了 mechanism/cov_override） | +1 |
| 同一 proposal_id 被拒后原样重提（无变化） | 不变（仍为当前 version） |
| 同一 proposal_id 通过后被 slow loop 重测 | 不变 |

**[规定] 实质变更检查**（P1-9）：version 递增时，peer 必须在 version_note 中描述变更内容。harvest 侧不做自动 diff 检查（无法可靠实现语义比较），但将 version_note 为空且 proposal_id 重复的提案记录为 warn 级别日志（不拒绝），供审计追溯。此规则为文档建议，不在质量门强制执行。

### 3.2 提案状态管理

#### 3.2.1 状态枚举

**[规定]** 定义以下显式状态：

| 状态 | 含义 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| draft | 提案已生成，尚未被收割 | peer 写入 proposals/ | harvest 扫描到 |
| prescreened | 已通过 prescreen | prescreen 完成并落盘 | harvest 开始处理 |
| rejected | 被质量门或树守卫拒绝 | harvest 拒绝（任何 reject_reason） | （终态） |
| queued | 已入队 | 通过所有质量门，写入 aligned_pending.jsonl | 慢环开始消费 |
| evaluating | 慢环正在评估 | 慢环从队列取出，开始回测 | 回测完成 |
| verdicted | 裁决已产出 | verdict 写入 aligned_verdicts.jsonl | （终态） |
| withdrawn | 主动撤回 | 宿主或系统调用撤回 | （终态） |
| degraded | 降级（保留但不入队） | prescreen degraded 或质量门降级路径 | 可能被 future harvest 重新评估 |

#### 3.2.2 状态转换规则

**允许的状态转换**：

```
draft → prescreened → queued → evaluating → verdicted    （正常通过）
                      → rejected                          （质量门拒绝，终态）
                      → degraded                          （prescreen 降级）
                      → withdrawn                         （主动撤回，终态）
draft → withdrawn                                        （生成后立即撤回）
queued → withdrawn                                       （入队后撤回，阻止新 claim）
evaluating → withdrawn                                   （评估中撤回，best-effort 中止）
evaluating → verdicted                                   （回测完成）
```

**禁止的状态转换**：
- rejected 到任何状态（拒绝是终态；要重新评估须新 version 的提案）
- verdicted 到任何状态（裁决是终态；`_maybe_enqueue_retests` 的样本复测是**队列层面**的 variant_id 再入队，不是 proposal lifecycle 状态转换）
- withdrawn 到任何状态（撤回是终态；要恢复须新 version）

#### 3.2.3 状态持久化方案：事件日志模型（Model A）

**[决定]** 选择 Model A —— `proposal_status.jsonl` 作为状态事实源，append-only 记录一切转换。

**理由**：与上位 spec M1「读时聚合」对齐。现有 queue/verdict/prescreen 文件是执行面数据，`proposal_status.jsonl` 是它们的**读时聚合视图的物化缓存**，不是独立的第二事实源。所有行可由 queue + verdict + prescreen + harvest 日志重现。

**与 open-issues M1 的关系**（P0-6）：
- `[决定]` 开放问题 spec §4.4 M1 裁定「读时聚合、反对第三状态源」。本规范的 `proposal_status.jsonl` 不是新的独立状态存储，而是对现有执行面文件（queue/inprogress/verdict/prescreen）的**聚合物化**，每次 harvest 可重建。
- `[决定]` `rejected_proposals.jsonl` 同理：它是 harvest `_reject()` 调用的结构化日志，与 `.omc/supervisor_decisions.jsonl` 同源但携带 per-proposal 细节。聚合时去重（同一 proposal_id + version + reject_reason 在同一 run_id 只记一次）。
- 两个 jsonl 文件均可删除后由现有数据重建（通过 harvest 重扫 + verdict 匹配）。
- **例外**：`withdrawn` 状态以 status 日志为唯一事实源——无现有执行面文件可派生 withdrawn，因此 `proposal_status.jsonl` 中的 withdrawn 行不可被丢弃。备份/retention 策略中应将 withdrawal 记录视为审计不可丢弃数据，而非纯缓存。

**状态派生与写入**：

| 状态 | 派生来源 | 写入方式 |
|------|---------|---------|
| draft / prescreened | proposals/*.json 存在 + prescreen 落盘 | harvest 扫描时追加 |
| rejected | harvest `_reject()` 调用 | harvest 拒绝时追加一行 |
| queued | aligned_pending.jsonl 写入 | harvest 入队时追加一行 |
| evaluating | aligned_pending.inprogress.jsonl | 慢环 claim 时追加一行 |
| verdicted | aligned_verdicts.jsonl | 慢环 verdict 落盘时追加一行 |
| withdrawn | 无现有派生源 | `withdraw_proposal()` 调用时追加一行 |
| degraded | *.prescreen.json status=degraded | prescreen 完成时追加一行 |

**新增文件**：
- `data/cache/proposal_status.jsonl`：事件日志，每行一条状态转换记录
- `data/cache/rejected_proposals.jsonl`：结构化拒收详情，供增强 known_verdicts.inc.md 的拒收详情节

### 3.3 跨 Run 反馈设计（P0-1 补写）

**目标**：让 peer agent 在每次生成提案时，能看到历史上同一 proposal_id 的完整命运（入队→评估→裁决/拒绝）。

#### 3.3.1 Join 路径

**[规定]** 提案身份 ↔ 实验身份 ↔ 裁决的关联路径：

```
proposal_id + version  ──harvest──→  variant_id  ──queue行──→  verdict
       │                                │                      │
       │                                │                      │
  proposal_status.jsonl          aligned_pending.jsonl    aligned_verdicts.jsonl
  (记录绑定关系)                  (携带 proposal_id +      (不改 schema，无
                                 version + variant_id)     proposal_id 字段)
```

**关键约束**：
1. `aligned_verdicts.jsonl` 不改 schema（不含 proposal_id）。这是 `[决定]`，见 §7.5。
2. 绑定关系由 **入队行** 承载：aligned_pending.jsonl 每行携带 `proposal_id`、`version`、`variant_id` 三键。
3. 慢环完成 verdict 后，`proposal_status.jsonl` 追加 `verdicted` 行，同时将 `variant_id` 与 verdict 的绑定写入 status 日志，使读时聚合能反查。
4. 跨 Run 的 `known_verdicts.inc.md` 物化时，通过 queue 行的 proposal_id+version 与 verdict 的 variant_id 做 join。

#### 3.3.2 物化模板

`known_verdicts.inc.md` 在现有成功/失败视图基础上，新增以下节：

**节 1：提案裁决因果链**（行预算 ≤ 25 行）

```markdown
## Proposal Verdicts（最近 N 个 Run）

| proposal_id | ver | variant_id | 裁决 | gate | fdr | quality | run_id |
|---|---|---|---|---|---|---|---|
| m_crack_spread_slope | 1 | m_term_str_f02b.. | FAIL | gate_pass=False | — | -12.5 | a1b2c3 |
| m_crack_spread_slope | 2 | m_term_str_f02b.. | PASS | gate_pass=True | fdr_pass | 15.3 | d4e5f6 |
```

排序：按 run_id 倒序，同一 proposal_id 按 version 升序（显示演化轨迹）。

**节 2：拒收详情**（行预算 ≤ 20 行）

```markdown
## Recent Rejections（per-proposal，最近 20 条）

| proposal_id | ver | reject_reason | quality | ts | run_id |
|---|---|---|---|---|---|
| i_yield_curve_inv | 1 | quality_below_threshold | -8.2 | 10-18T09:30 | a1b2c3 |
```

**与 known_rejections.inc.md 的分工**：
- `known_rejections.inc.md`：保留现有**计数分布**（各 reject_reason 的数量和占比），供 peer 了解宏观质量门倾向。
- `known_verdicts.inc.md` 新增节：提供**per-proposal 因果行**（具体提案为何被拒/通过），供 peer 参考具体历史。
- 两者互补，不重复。peer prompt 同时 include 两者。

#### 3.3.3 行预算控制

| 节 | 最大行数 | 截断规则 |
|----|---------|---------|
| 提案裁决因果链 | 25 | 最近 25 条 verdicted 记录 |
| 拒收详情 | 20 | 最近 20 条 rejected 记录 |
| 版本比较（单个提案） | 10 | 同一 proposal_id 的最近 10 个 version |

### 3.4 撤回/降级协议（P0-2 补写）

#### 3.4.1 API 签名

```python
def withdraw_proposal(proposal_id: str, version: int | None = None,
                      reason: str = "") -> bool:
    """撤回指定提案。幂等操作：已撤回返回 True，不存在返回 False。"""
```

- `version` 为 None 时撤回该 proposal_id 的所有 version。
- `reason` 记录到 `proposal_status.jsonl` 的 reason 字段。

#### 3.4.2 各状态保证

| 当前状态 | 撤回保证 |
|----------|---------|
| draft / prescreened | 立即标记 withdrawn；后续 harvest 跳过 |
| queued | 标记 withdrawn；从 aligned_pending.jsonl 标记跳过行（不删除，保持审计）；后续消费跳过 |
| evaluating | 标记 withdrawn；慢环在下一个 checkpoint 检查 withdrawn 状态并 cooperative 中止。**[决定]** 不保证立即杀进程：已 claim 的评估 best-effort 中止，不保证不产出 verdict |
| verdicted | 不接受撤回（终态） |
| rejected | 不接受撤回（终态；须新 version 重提） |
| withdrawn | 幂等：已撤回，返回 True |

#### 3.4.3 竞态处理

- `withdraw_proposal()` 与 `harvest_proposals()` 共享 fcntl 文件锁（与 queue/verdict 相同模式）。
- 慢环 cooperative cancel 点：每 N 个 checkpoint 读取 proposal_status.jsonl，检查对应 variant_id 是否已 withdrawn。
- Phase 4 验收标准（P1-11）：
  1. `withdraw_proposal()` 幂等（连续调用返回 True）。
  2. 已 withdrawn 的 queued 提案不被慢环 claim。
  3. evaluating 状态的 withdrawn 提案：best-effort 中止，不保证不产出 verdict（若 verdict 已产出则保留）。

#### 3.4.4 降级协议

- prescreen 返回 `status=degraded` 时，记录到 `proposal_status.jsonl` 的 `degraded` 状态。
- **[决定]** 降级策略采用 **soft 模式**（选项 b）：degraded 提案不入队（不写入 aligned_pending.jsonl），下次 harvest 可重新评估（degraded 非终态）。不硬拦入队行为——Phase 1 不改 harvest 路径。降级原因（超时/数据不足/模型降级）记录到 reason 字段。此策略与当前生产行为一致，status 日志记录 degraded 仅作可观测性增强。

### 3.5 提案关系追踪

#### 3.5.1 搜索树机制（按 off/shadow/enforce 分支，P1-8）

**[规定]** 按 `search_policy` 配置分支处理 tree 字段：

| search_policy | tree_id 派生 | peer 是否必填 | 缺失处理 |
|---------------|-------------|--------------|---------|
| off | 收割侧自动派生：`symbol::family::sha256(proposal_id)[:12]` | 否 | 自动填充，不拒绝 |
| shadow | 同 off，同时记录 peer 是否填了 | 否 | 自动填充，warn 日志 |
| enforce | peer 按 prompt 合同填写 | **是** | `search_role_missing` 拒绝 |

**P0-6 补充**：M4「peer 从未使用 tree 字段」在 off/shadow 模式下是预期行为（自动派生）；在 enforce 模式下由 `prompt_base.jinja2` 的 enforce 段要求 peer 填写，与现有树守卫一致。

#### 3.5.2 提案演化关系

**[规定]** 在 `proposal_status.jsonl` 中增加关系字段：`parent_proposal_id`、`parent_version`、`relation`。关系类型：

| 关系类型 | 含义 |
|----------|------|
| revision | 同一假设的修正版（改了 mechanism/cov_override） |
| variant | 不同参数版（同一 mechanism 不同 symbol） |
| inspired_by | 从另一提案获得灵感（跨 proposal_id） |
| root / exploit / falsifier | 搜索树角色 |

#### 3.5.3 跨 Run 延续

**[规定]** `proposal_id + version` 是跨 run 的唯一身份标识。收割侧在 dedup 检查时：

1. 先检查 **variant_id** 去重（不变）：同一 variant_id → `dedup` 拒绝。
2. 再检查 **proposal_id + version** 在 `proposal_status.jsonl` 中是否已有记录：同一 proposal_id + version 重提 → `version_dup` 拒绝。
3. 同一 proposal_id 的更高 version 视为新提案（允许入队）。

**检查顺序与 reject 文案**（P1-9 补充）：
- 先 variant_id（实验身份去重），再 proposal_id+version（提案版本去重）。
- peer 可见文案：`dedup` = "同一实验已入队/评估过"；`version_dup` = "同一提案版本已处理过"。

### 3.6 Schema 接受规则（P0-5 补写）

**[规定]** `sup_harvest.py:604-605` 的 schema 检查从硬编码 `v1` 改为接受集合：

```python
_ACCEPTED_SCHEMAS = {"fm.hypothesis_proposal.v1", "fm.hypothesis_proposal.v2"}
if p.get("schema") not in _ACCEPTED_SCHEMAS:
    _reject("schema_mismatch"); continue
```

- v1 schema 的 version 默认为 1（不写 version 字段时 harvest 侧视作 version=1）。
- v2 schema 必须携带 version 字段（整数 ≥ 1），否则视为 `schema_mismatch`。
- Phase 1 任务 P1.2 必须包含此修改（与状态写入同批部署）。

---

## 4. 数据契约

### 4.1 Proposal Schema v2（增强版）

在 v1 基础上增加字段：

| 字段 | 类型 | 必需 | 默认 | 说明 |
|------|------|------|------|------|
| version | integer | 否（v1）/ 是（v2） | 1（v1） | 提案版本号 |
| version_note | string | 否 | "" | 版本变更描述 |
| parent_proposal_id | string | 否 | null | 父提案 ID |
| relation | string | 否 | null | 与父提案的关系（revision/variant/inspired_by） |

v1 schema 继续被接受（version 默认 1）。harvest 接受 `{v1, v2}`。

### 4.2 Prescreen Result Schema（增强版）

不变。prescreen 结果继续输出 status ∈ {success, degraded, error} + variant_id + 评分字段。prescreen 阶段不感知 version。

### 4.3 队列记录 Schema（增强版）

在现有 QUEUE_FIELDS 基础上增加：

| 字段 | 类型 | 说明 |
|------|------|------|
| proposal_id | string | 关联到原始提案（新增） |
| version | integer | 提案版本（新增） |

这两个字段使 queue 行成为 proposal_id↔variant_id 的绑定载体。

### 4.4 Proposal Status Schema（新增）

`data/cache/proposal_status.jsonl` 每行：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| proposal_id | string | 是 | 提案 ID |
| version | integer | 是 | 版本号 |
| status | string | 是 | 状态枚举（见 §3.2.1） |
| variant_id | string | 否 | 入队后填充 |
| reject_reason | string | 否 | rejected 时 |
| quality_score | number | 否 | 收割质量分数 |
| ts | string | 是 | ISO 8601 时间戳 |
| run_id | string | 是 | supervisor run 标识 |
| parent_proposal_id | string | 否 | 父提案 ID |
| parent_version | integer | 否 | 父提案版本 |
| relation | string | 否 | 关系类型 |
| reason | string | 否 | withdrawn/degraded 原因 |

### 4.5 Rejected Proposals Schema（新增）

`data/cache/rejected_proposals.jsonl` 每行：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| proposal_id | string | 是 | 提案 ID |
| version | integer | 是 | 版本号 |
| variant_id | string | 否 | prescreen 后的 variant_id |
| reject_reason | string | 是 | 拒绝码 |
| quality_score | number | 否 | 质量分数 |
| breakdown | object | 否 | 质量门各子项分数 |
| ts | string | 是 | ISO 8601 |
| run_id | string | 是 | supervisor run 标识 |

**聚合去重规则**（P1-11 补充）：同一 `proposal_id + version + reject_reason + run_id` 只记一次。harvest 重扫时先检查是否已有该行。

### 4.6 状态转换协议

| 转换 | 触发者 | 守卫条件 |
|------|--------|---------|
| draft → prescreened | _prescreen_async | proposal 文件存在 |
| prescreened → queued | harvest_proposals | 通过所有质量门 + 树守卫 |
| prescreened → rejected | harvest_proposals | 任一质量门/树守卫拒绝 |
| prescreened → degraded | _prescreen_async | prescreen status=degraded |
| queued → evaluating | aligned_slow_loop | 从队列取出 |
| evaluating → verdicted | aligned_slow_loop | 回测完成，verdict 落盘 |
| **非终态** → withdrawn | withdraw_proposal() | 提案存在；verdicted/rejected/withdrawn 不接受 |
| ~~verdicted → retried~~ | ~~_maybe_enqueue_retests()~~ | **[删除]** 样本复测是队列层面的 variant_id 再入队，不是 proposal lifecycle 状态 |

**Withdrawn 与 Verdict 的关系**（二审修订）：
- 若 verdict 落盘时该 proposal_id+version 已有 withdrawn 记录，**不再追加 verdicted 状态行**。
- 或：追加 `verdicted_after_withdraw` 审计事件（不改 lifecycle 枚举），用于记录时序竞态。
- verdict 文件本身（aligned_verdicts.jsonl）仍可保留（append-only 不改），仅供审计追溯，不改变提案状态。

---

## 5. 实施路径

### Phase 1：状态显式管理 + 标注机制（P0，2-3 天）

目标：让提案状态可观测、拒收原因可追溯、schema 接受 v2。

任务：
- **P1.1** sup_paths.py 新增 PROPOSAL_STATUS_PATH、REJECTED_PROPOSALS_PATH 常量
- **P1.2** sup_harvest.py：① 修改 schema 检查为接受集合 `{v1, v2}`；② 收割时写入 proposal_status.jsonl 和 rejected_proposals.jsonl
- **P1.3** aligned_slow_loop.py：verdict 落盘时写入 verdicted 状态到 proposal_status.jsonl
- **P1.4** aggregate_rejection_stats.py：读取 rejected_proposals.jsonl 生成增强的 known_verdicts.inc.md 的**拒收详情节**（per-proposal 因果行）；known_rejections.inc.md 仅保留计数分布（不新增 per-proposal 节）
- **P1.5** sup_evidence.py：materialize_known_verdicts 增加版本比较节 + 提案裁决因果链节（§3.3.2 模板）
- **P1.6** task_FM/prompt_base.jinja2：include 增强后的信息节（注意：是 task_FM，不是 task_TM）
- **P1.7** 新测试 test_proposal_lifecycle.py：覆盖状态写入 + schema 接受 + 回归

验收：
- proposal_status.jsonl 正确写入各状态
- known_verdicts.inc.md 包含 per-proposal 拒收详情节 + 提案裁决因果链节
- known_rejections.inc.md 保持现有计数分布不变
- 现有质量门行为不变（回归测试全绿）
- v1 无 version 的旧提案仍可入队；v2 schema 的提案不触发 schema_mismatch

### Phase 2：跨 Run 反馈通道（P0，3-4 天）

目标：Peer 能参考历史裁决结果。

任务：
- **P2.1** sup_evidence.py：新增 `_proposal_evolution_lines()` 构建提案演化视图
- **P2.2** materialize_known_verdicts：增加拒收详情节，通过 queue 行 proposal_id+version 与 verdict 的 variant_id 做 join
- **P2.3** render_open_trees：增加裁决状态标注
- **P2.4** prompt_base.jinja2：新增 Proposal feedback 节（包含 §3.3.2 模板的因果链和拒收详情）
- **P2.5** 新测试 test_cross_run_feedback.py：给定 proposal→queue→verdict 夹具，验证 known_verdicts.inc.md 出现可机器检查的因果行

验收：
- 重启后第一份 known_verdicts.inc.md 包含提案-裁决因果链接（含 proposal_id、version、variant_id、gate/fdr）
- 存在多 version 的提案有版本比较
- 搜索树渲染包含裁决状态
- prompt 总行数不超过行预算（因果链 ≤ 25 + 拒收 ≤ 20 + 版本比较 ≤ 10）

### Phase 3：版本控制 + 关系追踪（P1，3-4 天）

目标：同一提案跨 run 可追踪版本和演化关系。

任务：
- **P3.1** peer prompt 引入 version 和 version_note 字段说明
- **P3.2** sup_harvest.py dedup 检查增加 proposal_id + version 维度（先 variant_id，再 proposal_id+version）
- **P3.3** 新增 version_dup reject_reason
- **P3.4** sup_evidence.py 版本链构建逻辑
- **P3.5** search_trees.py 增强 _Tree 类，支持 version 感知的 tree_id 派生
- **P3.6** 新测试 test_proposal_versioning.py

验收：
- 同一 proposal_id 的 v2 可以被入队
- 同一 proposal_id + version 的重提被拒绝为 version_dup
- 搜索树追踪包含 version 信息
- 按 search_policy（off/shadow/enforce）正确派生 tree_id

### Phase 4：撤回机制（P2，2 天）

目标：入队后可撤回提案。

任务：
- **P4.1** sup_harvest.py 新增 `withdraw_proposal()` 函数（§3.4.1 签名）
- **P4.2** aligned_slow_loop.py 慢环消费前检查 withdrawn 状态，cooperative cancel 点
- **P4.3** sup_paths.py 新增撤回相关路径常量（已在 P1.1 完成）
- **P4.4** 新测试 test_proposal_withdraw.py

验收：
- `withdraw_proposal()` 幂等（连续调用返回 True）
- 已撤回的 queued 提案不被慢环 claim
- evaluating 状态的 withdrawn 提案：best-effort 中止（不保证不产出 verdict）
- rejected/verdicted 状态不接受撤回

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| proposal_status.jsonl 写入冲突 | 状态丢失 | 使用 fcntl 文件锁（与 verdict 写入相同模式） |
| 反馈信息过多导致 prompt 膨胀 | peer 注意力分散 | 行预算：因果链 ≤ 25 行，拒收详情 ≤ 20 行，版本比较 ≤ 10 行 |
| version 递增被 peer 滥用 | 绕过 dedup | version_note 为空时记录 warn 日志；版本比较节不显示无实质变更的 version |
| 撤回后慢环仍在运行 | 浪费算力 | 慢环每 N 个 checkpoint 检查 withdrawn 状态；已 claim 的评估 best-effort 中止 |
| Schema v2 向后不兼容 | 旧提案被拒 | v1 继续被接受（version 默认 1），接受集合 `{v1, v2}` |
| proposal_status.jsonl / rejected_proposals.jsonl 体积膨胀 | 磁盘/IO 压力 | 保留策略：仅保留最近 10 个 run 的记录；旧记录归档到 `data/cache/archive/` |
| 回滚 | 回滚需同步 prompt | feature flag 或 empty include ignore missing |

### 6.1 Jsonl 体积与 Retention（P2-12）

| 文件 | 预估大小 | Retention 策略 |
|------|---------|---------------|
| proposal_status.jsonl | ~200 行/run（24 品种 × 多 peer × 多代） | 保留最近 10 个 run；超期行归档 |
| rejected_proposals.jsonl | ~500 行/run（含各拒绝码） | 保留最近 10 个 run；超期行归档 |

归档路径：`data/cache/archive/proposal_status/` 和 `data/cache/archive/rejected_proposals/`，按 run_id 分文件。

---

## 7. 附录

### 7.1 关键文件路径

| 文件 | 路径 | 用途 |
|------|------|------|
| 提案 | task_FM/experiments/run_*/results/gen_*/gen*_peer*/proposals/*.json | peer 生成的提案 |
| Prescreen | 同目录 *.prescreen.json | Laya 预筛结果 |
| 队列 | data/cache/aligned_pending.jsonl | 待评估队列 |
| 进行中 | data/cache/aligned_pending.inprogress.jsonl | 正在评估 |
| Checkpoints | data/cache/aligned_checkpoints/{variant_id}.jsonl | 慢环 checkpoint |
| 裁决 | task_FM/config/aligned_verdicts.jsonl | 最终裁决 |
| 已知裁决 | task_FM/known_verdicts.inc.md | peer 可读的裁决视图 |
| 拒收统计 | task_FM/known_rejections.inc.md | peer 可读的拒收统计（计数分布） |
| 协变量池 | task_FM/config/covariate_pool.json | 活跃协变量 |
| 搜索承诺 | task_FM/config/search_commitments.jsonl | 搜索树承诺 |
| **新增** 提案状态 | data/cache/proposal_status.jsonl | 显式状态事件日志 |
| **新增** 拒收详情 | data/cache/rejected_proposals.jsonl | 结构化拒收记录 |

### 7.2 Proposal JSON 示例

    {
      "schema": "fm.hypothesis_proposal.v2",
      "proposal_id": "m_crack_spread_slope",
      "version": 2,
      "version_note": "修正了 kill_condition 阈值（0.52 改为 0.50），增加了压榨利润相关性论证",
      "symbol": "m",
      "cov_override": "crack_spread_slope",
      "covariate_family": "term_structure",
      "mechanism": "豆粕作为压榨产业链下游，其价格与大豆-豆粕-油脂压榨利润高度相关。压榨利润斜率变化领先豆粕价格",
      "symbol_fit": "m 是压榨产业链核心品种，压榨利润斜率直接反映产业链利润分配与景气周期",
      "predicted_direction": "crack_spread_slope_up -> long; crack_spread_slope_down -> short",
      "kill_condition": "aligned dir_acc < 0.50 或压榨利润与豆粕价格相关性<0.3时放弃",
      "promote_condition": "aligned gate_pass 且 fdr_pass"
    }

### 7.3 Proposal Status JSONL 示例

    {"proposal_id": "m_crack_spread_slope", "version": 1, "status": "rejected", "reject_reason": "quality_below_threshold", "quality_score": -12.5, "ts": "2026-10-18T10:00:00", "run_id": "a1b2c3d4e5f6"}
    {"proposal_id": "m_crack_spread_slope", "version": 2, "status": "queued", "variant_id": "m_term_structure_f02b2a43cdef", "quality_score": 15.3, "ts": "2026-10-18T12:00:00", "run_id": "a1b2c3d4e5f6", "parent_proposal_id": "m_crack_spread_slope", "parent_version": 1, "relation": "revision"}
    {"proposal_id": "m_crack_spread_slope", "version": 2, "status": "evaluating", "variant_id": "m_term_structure_f02b2a43cdef", "ts": "2026-10-18T14:00:00", "run_id": "a1b2c3d4e5f6"}
    {"proposal_id": "m_crack_spread_slope", "version": 2, "status": "verdicted", "variant_id": "m_term_structure_f02b2a43cdef", "ts": "2026-10-18T16:00:00", "run_id": "a1b2c3d4e5f6"}

### 7.4 与现有 Spec 的关系

| 现有 Spec | 关系 |
|-----------|------|
| 2026-09-24-covariate-research-credibility-design.md（v15） | 上位 spec，本规范不修改其评估口径和过门定义 |
| 2026-10-03-peer-memory-loop-closure-spec.md | 本规范扩展其 D1-D4 方案。`known_rejections.inc.md` 计数级反馈已存在（D1 已实施），本规范增加 per-proposal 因果增强（rejected_proposals.jsonl）和 cross-run verdict join（proposal_status.jsonl）。**D1 状态头**：peer-memory spec 的 D1 方案定义了 status header 窗口（`## Symbol status` / `## Effective clues` / `## Do not re-propose` + 协议指纹），该窗口定义仍待宿主对齐「本轮」判据（peer-memory spec §4.1 Q10）。本规范的 per-proposal 拒收详情节与 D1 状态头互补：D1 提供 macro 计数 + 状态头摘要，本规范提供 per-proposal 因果行。两者窗口定义需在同一次 M3 迭代中对齐。 |
| 2026-10-05-positive-ev-factor-search-spec | 本规范引用其搜索树机制（§3.5.1）；`tree_id_for` 的 hash 输入为 proposal_id：`sha256(proposal_id)[:12]`，输出 `symbol::family::hash[:12]` |
| 2026-10-08-open-issues-closure-spec | 本规范解决其中 M1（跨 Run 反馈）和 M2（状态显式管理）。`proposal_status.jsonl` 与 `rejected_proposals.jsonl` 是现有执行面文件的聚合缓存，非独立第三状态源（§3.2.3 [决定]） |

### 7.5 明确不做

| 不做的事 | 理由 |
|----------|------|
| 不修改质量门/树守卫的阈值或逻辑 | 保持评估口径不变 |
| 不修改 protocol_fingerprint | 不触发基线重生 |
| 不新建独立的状态数据库 | 利用现有文件总线 + 聚合缓存，降低复杂度 |
| 不改变 variant_id 生成规则 | W6.4 契约已稳定运行 |
| 不强制 peer 填 search_parent_id/tree_id（off/shadow 模式） | 由收割侧自动派生，减少 peer 负担 |
| 不重写 aligned_verdicts.jsonl | 保持 append-only；proposal_id↔verdict 绑定由 status 日志承载 |
| 不修改 gate_pass / fdr_pass 判定逻辑 | 评估语义不变 |
| 不修改 `_maybe_enqueue_retests` 的样本复测行为 | 它是队列层面的 variant_id 再入队，不是 proposal lifecycle 状态 |

### 7.6 tree_id_for 实现说明（P2-13）

```python
# search_trees.py tree_id_for 的实现：
# tree_id = f"{symbol}::{family}::{sha256(proposal_id.encode()).hexdigest()[:12]}"
```

输入是 **proposal_id**（不是 variant_id）。输出格式 `symbol::family::sha256[:12]`。在 off/shadow 模式下由收割侧自动计算；enforce 模式下 peer 按 prompt 合同填写。
