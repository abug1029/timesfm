# Peer 记忆回路闭合 Spec

- **spec 日期**：2026-10-03
- **对照代码**：WSL `/home/abug/timesfm` master `d026118`（收口计划已合入；本文件仍未提交）
- **上位 spec**：`docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15）
- **事实来源**：`docs/superpowers/reports/2026-10-03-three-loop-autoresearch-paradigm-audit.md` 的勘误横幅，加上 P1-1。该报告正文里的 P0 与 §5 一等已作废。
- **文档标记**：`[事实]` 可回代码核验 · `[规定]` 本文件的要求 · `[待决]` 需宿主裁定 · `[决定]` 已定

> **当前进度**：只实施 D2 与 D3，外加弱族那句会误导 peer 的话。D1 等「本轮」有了窗口定义再做。D4 排在 D1 之后，向后兼容测试不过就不合入。

---

## 1. 目的与完成标准

### 1.1 目的

快环 peer 读 `known_verdicts.inc.md`。收割拒收的理由只进监督环日志，peer 看不到，于是按同样的写法再提。

本文件只增加 peer 能看见的事实。18 道门的判据、阈值和拒绝动作保持原样。

### 1.2 完成标准

| # | 标准 | 状态 |
|---|---|---|
| S1 | 文件含按 `reject_reason` 分组的拒收计数 | 未做。先定义「本轮」再做 D1 |
| S2 | 文件含死亡族名单：族名、`n_ok`、`n_gate_pass`、`min_ok`、协议指纹。`n_ok` 只数可确认的 DM | 本轮做 D2 |
| S3 | 三个老节有节级协议指纹；每条带指纹的裁决行用该行自己的指纹前 12 位 | 本轮做 D3 |
| S4 | 提案可写 `decision=abandon`，不入队、不加分、要物化 | 未做。见 D4 |
| S5 | 18 道门的判据与阈值不变 | 全程约束 |

S2 完成的判据：同一快照上，名单里的族集合等于 `_dead_families` 的返回值；`n_ok` 等于该函数计入的行数，而不是全部 `status=ok` 的行数。

S3 完成的判据：`## Symbol status`、`## Effective clues`、`## Do not re-propose` 各有一行 `protocol ` 加主协议指纹前 12 位；主协议组的选法与 `materialize_known_verdicts` 里现有的 `_primary_fp` 相同。没有指纹的裁决行不加方括号。

---

## 2. 核实结论 `[事实]`

收口计划已在 `d026118` 合入。确认入队有调用点。`_dead_families` 只计 `dm_status` 为 `ok` 或 `set_mismatch_ok` 的行，过门字段仍是 `gate_pass`，`min_ok` 仍是 4。下面的行号不再写入本文件：函数会随提交移动，peer 文本里也不放行号。

| 环节 | 看哪个函数 | 现状 |
|---|---|---|
| 门在判 | `harvest_proposals` | 拒收只进统计和 `.omc/supervisor_decisions.jsonl` |
| 物化给 peer | `materialize_known_verdicts` | 原文件没有 `reject_reason`，也没有死亡族节 |
| 死亡判定 | `_dead_families` | 收割在用；弱族渲染 `_effective_clue_lines` 不用它 |
| peer 读取 | `task_FM/prompt_base.jinja2` | 只 include 两个 `.inc.md` |

`_effective_clue_lines` 的弱族行原先写着「除非有 failure_delta」。这句不成立。`failure_delta` 只供应给 `no_failure_delta` 那一道门。`family_dead` 在它之前无条件拒绝，没有复活入口。弱族计数也不看 `dm_status`，所以「4 条 ok、0 过门」可以不是死亡族。

`_has_prior_failure` 仍是同一品种或同一协变量即算，不是必须同一对。`GOAL_SYMBOLS_SET` 仍是 9 个品种。目标文件 `target_symbols` 的更长名单只用于开局基线预检。`survivors_per_cycle` 以目标 yaml 的 3 为准；代码缺键时的默认 2 只有键不存在才生效。

---

## 3. 非目标

| 不做的事 | 理由 |
|---|---|
| 不改 `missingness_admissible` 的默认 False | v15 §7.8 在开放问题 #8 裁定前保持 False |
| 不改自适应门阈值 | v15 开放问题 #7 与 Q7 备忘录 |
| 不改 `_dead_families` 的 `min_ok=4` 与 `gate_pass` | 只把现有判定结果写给 peer |
| 不改 `_has_prior_failure` 的 OR | 宿主已要求保持 |
| 不改 18 道门的判据或阈值 | 只改 peer 能否看见结果 |
| 不动确认入队与终结 | 已在 `d026118` |
| 不新建 `attempts/`、`notes/`、`skills/` | 提案 JSON 已经落在各轮 `proposals/` |
| 不改 `top_k` / `survivors_per_cycle` | 宿主已要求保持 |
| 不重写 `aligned_verdicts.jsonl` | 文件保持追加 |
| 不把代码行号写进 peer 可见文本 | 行号会过期，见决策 4 |
| 不把审计里的累计拒收次数抄进 `.inc.md` | 那些数跨了很多轮，不是一轮的结果 |

---

## 4. 设计

### 4.1 D1 — 拒收摘要 `[规定]` 未实施

做的时候在 `materialize_known_verdicts` 增加一节，放在死亡族节之后。按 `reject_reason` 计数降序，计数为 0 的原因不写。

★ 只给补一段文字就可能通过的门：`no_failure_delta`、`schema_mismatch`。`family_dead` 不打 ★。它是无条件拒绝，`failure_delta` 不能让该族通过。`dedup` 以及其他硬拒也不打 ★。

理由文本用稳定的原因码，不写 `supervisor.py:` 加行号。行号在两次提交之间就会失效，peer 无法发现自己读到的是旧位置。

计数必须来自 `.omc/supervisor_decisions.jsonl` 里**本轮**的记录，这样重启后还能渲染出同一份摘要。本文件不定义「本轮」的起止。在宿主写下窗口之前，不实现这一节，也不把累计次数渲染出去。审计报告里的 2053、655、565 是累计数，不能当模板。

### 4.2 D2 — 死亡族名单 `[规定]` 本轮实施

在 `## Effective clues` 之后、`## Do not re-propose` 之前写：

```markdown
## Dead families
protocol f02b2a433fd5
判据与 family_dead 相同：只计 dm_status 为 ok 或 set_mismatch_ok 的 ok 行；条数达到 min_ok 且 gate_pass 为 0 才列入。描述性 DM 不计数。列入的族会被无条件拒绝。

- term_structure: n_ok=4, n_gate_pass=0, min_ok=4
```

没有死亡族时写 `- (none)`。`protocol` 那一行用主协议指纹前 12 位；主协议组不存在时写 `protocol (none)`。

`n_ok` 与 `n_gate_pass` 必须和 `_dead_families` 使用同一套计数。渲染层不得再数一遍「全部 ok 行」。

弱族小节保留，供 peer 看见描述性裁决堆在哪里。弱族行只写条数，不写「除非有 failure_delta」，也不写该族可以复活。弱族标题下用一句话指向死亡族节：那边才是 `family_dead` 的名单。

### 4.3 D3 — 协议指纹 `[规定]` 本轮实施

`## Symbol status`、`## Effective clues`、`## Do not re-propose` 各加一行节级指纹，格式与 D2 的 `protocol ` 行相同，取值是 `_primary_fp` 的前 12 位。

每条裁决行使用**该行自己的** `protocol_fingerprint` 前 12 位：

```markdown
- [f02b2a433fd5] m_momentum_b06ddbcd88e3: hard-gate-but-losing, gate_pass=True, …
```

该行没有指纹时不加方括号，避免把旧行伪装成当前协议。不用主协议指纹去标记其他协议的行。那样做会把跨代证据印成同一代，而指纹前缀的目的正是让这种混代能被看出来。

### 4.4 D4 — `decision` / `abandon` `[规定]` 未实施

现有提案没有这两个字段。实施时缺省等于 `propose`，旧文件的 18 道门、计数、优先级和入队结果保持不变。这是合入条件。

| 字段 | 必填 | 约束 |
|---|---|---|
| `decision` | 否，缺省 `propose` | `propose` 或 `abandon` |
| `abandon_reason` | `decision` 为 `abandon` 时必填 | 至少 40 个字符，与 `mechanism` 同一门槛 |

`decision` 为 `abandon` 的提案在全部 18 道门之前分开，不入队，不进入任何拒收计数。它仍写到原来的 `proposals/` 路径，并在 `known_verdicts.inc.md` 里单列一节，写明这是 peer 放弃、不是已验证的失败。

abandon 不加排序分，也不做比例告警。告警要不要做，见开放问题 1。

---

## 5. 测试

本轮只跑聚焦测试，不跑全量 pytest。

| # | 断言 | 何时 |
|---|---|---|
| T5 | 死亡族节的族集合与 `_dead_families` 一致；`n_ok` 不含描述性 DM；节内不出现复活或 `failure_delta` | 本轮 |
| T6 | 三个老节有主协议前 12 位；裁决行用自己的指纹；无指纹的行没有方括号 | 本轮 |
| T1–T3 | 拒收摘要的分组、★ 和零计数省略。★ 不含 `family_dead` | D1，窗口定义之后 |
| T4 | 撤回。不再要求理由字符串含 `supervisor.py:` | 不做 |
| T7–T10 | abandon 不入队、要物化、旧提案逐项不变、排序不加分 | D4 |
| T11 | 聚焦跑 `tests/test_harvest_proposals.py`、`tests/test_supervisor.py`、`tests/test_confirmation_wiring.py` 里这次改动碰到的测试 | 每次改动 |

夹具里的裁决要显式写 `dm_status` 和 `protocol_fingerprint`。缺 `dm_status` 的行不会进入死亡计数。

---

## 6. 决定

**决策 1 — 记忆仍是每轮覆盖 `[决定]`**

不建跨轮索引。提案 JSON 已经在各轮目录里。peer 先看见这一轮渲染出来的事实。跨轮记忆见开放问题 2，现在不做。

**决策 2 — 只改可见性 `[决定]`**

不改 18 道门的输入。不把 `min_ok` 调高，不把 OR 改成同一对。

**决策 3 — abandon 是表达 `[决定]`**

peer 可以写下自己不做某个方向，但不能靠这个声明提高排序分。

**决策 4 — 理由用原因码，不用行号 `[决定]`**

原先要求 peer 文本带 `supervisor.py:` 行号。该要求撤回。`d026118` 相对审计时的行号已经移动了数百行。稳定的是 `family_dead`、`no_failure_delta` 这些原因码。

---

## 7. 开放问题

1. **abandon 会不会被用来逃避探索 `[待决]`**。默认不做比例告警，也不把 abandon 计进排序。不挡住 D2 / D3。挡住的是「要不要在 D4 之外再加熔断」。
2. **要不要跨轮记忆 `[待决]`**。D1 落地并且「本轮」窗口已定义之后，若 `no_failure_delta` 的占比仍不下降，再决定要不要保留上一轮的摘要。现在不建。
3. **口径遗留已关闭**。9 与 24 是两份名单：前者是目标品种集合，后者是开局基线预检。名额以 yaml 的 3 为准。OR 保持，不在本文件里改。

D1 的窗口定义仍是 `[待决]`：哪些 `supervisor_decisions.jsonl` 记录算「本轮」。在这句被宿主写成可检查的起止条件之前，D1 不开始。

---

## 8. 实施顺序

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1 | D3 指纹 + D2 死亡族 + 删掉弱族行里的 `failure_delta` 承诺 | 本轮 |
| 2 | D1 拒收摘要 | 等开放问题里的窗口定义 |
| 3 | D4 abandon | 在 D1 之后；旧提案行为变化则不合入 |

监督环在跑时，代码改动进工作树。不启动、不停止、不重启监督环。不 push。测试只用聚焦命令。

---

## 9. 与收口计划的关系

`docs/superpowers/plans/2026-10-03-three-loop-open-closure.md` 的九项已合入 master `d026118`。计划文件本身仍是未跟踪文件。本文件不重做那九项。

交叉点只有死亡族的读法。Task 4 已经落地：可确认的 DM、`gate_pass`、`min_ok=4`。D2 显示这套结果，不另写一套计数。
