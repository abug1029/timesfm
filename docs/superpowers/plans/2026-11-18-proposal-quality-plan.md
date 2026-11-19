# 提案质量提示词 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉快环提示词里与目标品种、活跃协变量族、现有对齐门禁互相矛盾的句子，并用一个只读三个文本的测试钉住。

**Architecture:** 不改收割、目标、门禁和任务配置。只改三份会被渲染进同一次快环提示的文本：`task_FM/prompt_base.jinja2` 四处，`task_FM/roles/peer_generalist/skill.md` 两处，`task_FM/prompt_generation.jinja2` 一处。`gen0_peer1_prompt.md` 加载的是同一份 `skill.md`，没有第二份角色文件。测试按规格里的禁止串和必须出现串做静态断言。

**Tech Stack:** 活仓 `/home/abug/timesfm`，解释器 `/home/abug/timesfm/.venv/bin/python`（Python 3.11），pytest。不引入新依赖。

**Spec:** `/home/abug/timesfm/docs/superpowers/specs/2026-11-18-proposal-quality-design.md`

## Global Constraints

规格已经锁定。每个任务都带上下面这些限制。

- 代码基线是活仓 `master` 的 `50c848b09545230b4f0cc2d87556ca294829841f`。实施前若 `HEAD` 已前进，先看这四个路径有没有被别的提交改过：`task_FM/prompt_base.jinja2`、`task_FM/roles/peer_generalist/skill.md`、`task_FM/prompt_generation.jinja2`、`tests/test_prompt_symbol_authority_20261118.py`。改过就停下来。
- 不重启监督环，不杀已有的 `praxist_supervisor.py`，不跑 `scripts/restart_three_loop_clean.sh`。提示词在下一次由宿主明确要求启动的快环里生效。
- 不 `git add`，不 `git commit`，不推送。活仓里已有的运行数据保持未暂存。规格验收第 4 条禁止提交。这覆盖本技能模板里的提交步骤。
- 不改 `scripts/sup_harvest.py`、`scripts/praxist_goal.yaml`、`task_FM/config/covariate_pool.json`、`task_FM/task.yaml`、`task_FM/roles/` 下除 `peer_generalist/skill.md` 以外的文件、评估门禁、`known_verdicts.inc.md`、`covariate_menu.inc.md`。写规格时 `search_policy` 是 `shadow`，不要打开目标文件去改这个键。
- 不把 24 个品种名写进提示词。品种权威是绝对路径 `/home/abug/timesfm/scripts/praxist_goal.yaml` 里的 `target_symbols`，加上收割拒绝码 `symbol_not_allowed`。
- 不改 `cohort {{ cohort_size | default(4) }}`。`cohort_size` 是同行个数。已核对的渲染传入的是 2。
- 这一轮新写的句子用英文。`prompt_base.jinja2` 第 34 行已有的 `aligned dir_acc 低于该品种 adaptive effective_min 即放弃` 留着，不要译成英文，也不要抄进 `skill.md`。
- `skill.md` 里 `symbol_fit` 的 `positioning/calendar/structure` 留着。`prompt_base.jinja2` 第 2 条 `symbol_fit` 里的 positioning 一词留着。禁止的是带引号的 `"covariate_family": "positioning"`。
- `prompt_generation.jinja2` 里的 `adaptive gate (0.50-0.52)` 留着。`prompt_base.jinja2` 第 7 行的 `n=350-600` 留着。禁止串是 `n>=350`，两者不是同一个字符串。
- 渲染结果里另一处 `n>=350` 来自 include，不在 `prompt_base.jinja2` 源文件里。本计划不改 include。
- 测试只读三个源文件。不断言运行中的监督环，不读 `aligned_verdicts.jsonl`。不跑全量 pytest。
- 监督环若在运行，不要改活仓源文件。按 `superpowers:using-git-worktrees` 从活仓开工作树再改。工作树不含未跟踪的规格和本计划，阅读规格用活仓绝对路径。监督环没在运行时，直接改活仓下面写出的路径。命令里的 `cd /home/abug/timesfm` 和 `git -C /home/abug/timesfm` 指改文件的那棵树；开了工作树就把这两处换成工作树根。pytest 解释器始终是 `/home/abug/timesfm/.venv/bin/python`。
- 规格「明确不做」和「以后再看」没有对应任务。不要加注册表、`proposal_id` 硬去重、品种黑名单、配额、熔断、本地预筛，也不要去查那 608 份重复提案的收割去向。

## 范围

这是一个子系统：快环实际看得到的三段提示文本，外加一个静态测试。不拆成多份计划。`task.yaml` 的 `research_direction` 里还有短名单和 `DirAcc>=0.52`，规格已核对它没有进入 `gen0_peer0_prompt.md` 和 `gen0_peer1_prompt.md`，本计划不改它。

## 文件职责

| 文件 | 职责 |
|---|---|
| `task_FM/prompt_base.jinja2` | 快环基底。改品种规则、`p_oi` 的族、Diversity 段、Domain guidance 的门禁句。 |
| `task_FM/roles/peer_generalist/skill.md` | 两个同行都会拼上的角色技能。改 Proposal scope 和 kill 示例。 |
| `task_FM/prompt_generation.jinja2` | 代次模板。只改 anti_mainline 那句族名单。 |
| `tests/test_prompt_symbol_authority_20261118.py` | 只读上面三个文件，按规格的表断言禁止串和必须出现的串。 |

规格条目对照：提示 1–4 是 Task 1，提示 5 是 Task 2，提示 6 是 Task 3。验收 1–4 在 Task 3 收口。

---

### Task 1: prompt_base 的四处矛盾句

**Files:**
- Create: `tests/test_prompt_symbol_authority_20261118.py`
- Modify: `task_FM/prompt_base.jinja2`（第 30、68、88–92、143–144 行）
- Test: `tests/test_prompt_symbol_authority_20261118.py`

**Interfaces:**
- Consumes: 无。三个源文件都已在仓库里。
- Produces: 模块级名字 `ROOT`、`BASE`、`SKILL`、`GEN`、`SHORT`，以及 `_read(path) -> str`。后面的任务往同一文件追加测试函数，沿用这些名字。`test_prompt_base_symbol_family_and_gate` 在本任务结束时通过。

- [ ] **Step 1: 确认监督环，再写会失败的测试**

在改文件之前执行：

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'pgrep -af "[p]raxist_supervisor.py" || echo NO_SUPERVISOR'
```

有进程：不要杀，按 Global Constraints 改到工作树，下面的路径相对于那棵工作树。没有进程：路径相对于 `/home/abug/timesfm`。

新建 `tests/test_prompt_symbol_authority_20261118.py`：

```python
"""快环提示词的品种与族权威（spec 2026-11-18-proposal-quality-design.md）。

本文件最终要覆盖 prompt_base.jinja2 的四条规则，以及 skill.md 和
prompt_generation.jinja2。这一任务先钉住 prompt_base.jinja2。
只读文本。不断言运行中的监督环，也不读裁决文件。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "task_FM", "prompt_base.jinja2")
SKILL = os.path.join(ROOT, "task_FM", "roles", "peer_generalist", "skill.md")
GEN = os.path.join(ROOT, "task_FM", "prompt_generation.jinja2")
SHORT = "{m, ss, sr, cj, jd, lh, eg, rb}"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_prompt_base_symbol_family_and_gate():
    text = _read(BASE)
    for banned in (
        SHORT,
        "2-star",
        '"covariate_family": "positioning"',
        "macro_sentiment",
        "n>=350",
        "n_eff>=50",
        "DirAcc>=0.52",
    ):
        assert banned not in text, banned
    for required in (
        "/home/abug/timesfm/scripts/praxist_goal.yaml",
        "target_symbols",
        '"covariate_family": "inventory"',
        "When you write two or more proposals",
        "Do not invent a family the menu does not list",
        "the slow loop's existing aligned gate",
    ):
        assert required in text, required
    assert "cohort_size | default(4)" in text
    assert "n=350-600" in text
    assert "covariate_menu.inc.md" in text
    assert "known_verdicts.inc.md" in text
    assert "p_oi.json" in text
    assert "failure_delta" in text
    assert "ACTIVE 品种优先" in text
    assert "缺 `success_delta` 的复跑会被拒收 (`no_success_delta`)。" in text
    assert "低于该品种 adaptive effective_min" in text
    assert "positioning/calendar/structure" in text
```

- [ ] **Step 2: 跑测试，确认它先失败**

Run:

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /home/abug/timesfm && /home/abug/timesfm/.venv/bin/python -m pytest tests/test_prompt_symbol_authority_20261118.py::test_prompt_base_symbol_family_and_gate -v'
```

工作树里把 `cd /home/abug/timesfm` 换成工作树根。解释器仍用活仓的 `.venv/bin/python`。

Expected: FAIL。失败断言是短名单 `{m, ss, sr, cj, jd, lh, eg, rb}` 仍在 `prompt_base.jinja2` 里。若失败原因是文件找不到或 `ACTIVE 品种优先` 已不在，停下来，不要改提示词。

- [ ] **Step 3: 只改 prompt_base 的四处**

第 30 行，把：

```text
  "covariate_family": "positioning",
```

换成：

```text
  "covariate_family": "inventory",
```

第 68 行，把：

```text
5. **Symbols**: {m, ss, sr, cj, jd, lh, eg, rb} plus the 2-star set in the evaluator.
```

换成：

```text
5. **Symbols**: only target_symbols in /home/abug/timesfm/scripts/praxist_goal.yaml. Do not use a shorter list. A symbol outside that file is rejected at harvest as symbol_not_allowed.
```

第 88–92 行，保留标题，把标题下的段落换成规格里的三句。整段变成：

```text
## Diversity gate (QD)
When you write two or more proposals in this generation, at least one must use an ACTIVE covariate family from the menu below that differs from the family of your other proposal. A single proposal is valid when its covariate is an ACTIVE row in that menu. Do not invent a family the menu does not list.
```

第 143–144 行的 Baselines 子弹换成下面这一条。Mechanism 子弹和 “Never edit evaluator” 子弹不动。第 7 行的 `n=350-600` 不动。第 34 行的中文 kill 示例不动。

旧句末尾的 `and BH-FDR survival` 随这句一起换掉。规格给的新句里没有它。

```text
- Baselines: the fixed schemes in config/prediction_scheme.py are the incumbents. A proposal passes only when the slow loop's existing aligned gate passes. This prompt does not add a direction-accuracy cutoff.
```

- [ ] **Step 4: 再跑同一条测试，确认通过**

Run: 与 Step 2 相同的 pytest 命令。

Expected: PASS（1 passed）。

- [ ] **Step 5: 看 diff，不要提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'git -C /home/abug/timesfm diff --stat -- task_FM/prompt_base.jinja2 tests/test_prompt_symbol_authority_20261118.py'
```

Expected: 只有这两个路径。不要 `git add`。不要改 `skill.md` 和 `prompt_generation.jinja2`，那是后面两个任务。

---

### Task 2: 角色技能里的短名单和英文放弃条件

**Files:**
- Modify: `tests/test_prompt_symbol_authority_20261118.py`
- Modify: `task_FM/roles/peer_generalist/skill.md`（第 26 行、第 56 行）
- Test: `tests/test_prompt_symbol_authority_20261118.py::test_skill_scope_uses_goal_file_and_english_kill`

**Interfaces:**
- Consumes: Task 1 的 `ROOT`、`SKILL`、`SHORT`、`_read`。
- Produces: `test_skill_scope_uses_goal_file_and_english_kill`。通过时 `skill.md` 含 `below that symbol's adaptive effective_min`，不含 `dir_acc<0.52`，也不含 `低于该品种`。

- [ ] **Step 1: 追加会失败的技能测试**

在 Task 1 的测试函数后面追加，不要改已有的 `_read` 和 `test_prompt_base_symbol_family_and_gate`：

```python
def test_skill_scope_uses_goal_file_and_english_kill():
    text = _read(SKILL)
    for banned in (
        SHORT,
        "2-star",
        "dir_acc<0.52",
        "低于该品种",
    ):
        assert banned not in text, banned
    for required in (
        "/home/abug/timesfm/scripts/praxist_goal.yaml",
        "target_symbols",
        "below that symbol's adaptive effective_min",
    ):
        assert required in text, required
    assert "positioning/calendar/structure" in text
    assert '"covariate_family": "volatility"' in text
```

`volatility` 是这个文件里 `m_vor` 示例的族，本来就对，本任务不要改它。断言是为了防止改 kill 时把示例 JSON 改乱。

- [ ] **Step 2: 跑技能测试，确认它先失败**

Run:

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /home/abug/timesfm && /home/abug/timesfm/.venv/bin/python -m pytest tests/test_prompt_symbol_authority_20261118.py::test_skill_scope_uses_goal_file_and_english_kill -v'
```

工作树同样换成工作树根。

Expected: FAIL。`dir_acc<0.52` 仍在第 26 行，或短名单仍在第 56 行。

- [ ] **Step 3: 只改 skill.md 的两行**

第 26 行整句换成：

```text
  "kill_condition": "aligned dir_acc below that symbol's adaptive effective_min, or endpoint_mape does not improve (falsifiable)",
```

保留行尾逗号。不要写成 `低于该品种`。不要改第 23–25 行已有的中文，也不要改第 27 行的 `promote_condition`。

第 56 行换成：

```text
- symbol: only target_symbols in /home/abug/timesfm/scripts/praxist_goal.yaml. Do not use a shorter list.
```

- [ ] **Step 4: 跑本文件已有的两条测试**

Run:

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /home/abug/timesfm && /home/abug/timesfm/.venv/bin/python -m pytest tests/test_prompt_symbol_authority_20261118.py -v'
```

Expected: PASS（2 passed）。Task 1 那条不能被这次修改弄失败。

- [ ] **Step 5: 看 diff，不要提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'git -C /home/abug/timesfm diff --stat -- task_FM/prompt_base.jinja2 task_FM/roles/peer_generalist/skill.md tests/test_prompt_symbol_authority_20261118.py'
```

Expected: 这三个路径。不要 `git add`。

---

### Task 3: 代次模板的族名单，并跑规格里的回归

**Files:**
- Modify: `tests/test_prompt_symbol_authority_20261118.py`（模块 docstring，再追加一个测试）
- Modify: `task_FM/prompt_generation.jinja2`（第 52–55 行）
- Test: `tests/test_prompt_symbol_authority_20261118.py`，外加规格验收第 3 条列出的四条既有测试

**Interfaces:**
- Consumes: Task 1 的 `GEN`、`_read`。Task 1 和 Task 2 的测试保持通过。
- Produces: 模块 docstring 写明覆盖四条 `prompt_base.jinja2` 规则，以及 `skill.md` 和 `prompt_generation.jinja2`。`test_generation_anti_mainline_does_not_name_macro_sentiment` 通过。`macro_sentiment` 不再出现在 `prompt_generation.jinja2`。

- [ ] **Step 1: 把模块 docstring 换成规格要求的最终文本，并追加会失败的测试**

用下面整段替换文件开头的 docstring：

```python
"""快环提示词的品种与族权威（spec 2026-11-18-proposal-quality-design.md）。

覆盖 prompt_base.jinja2 的四条规则：品种只指向目标文件、示例族为 inventory、
两份以上提案才要求跨族、不再另写方向准确率门槛。
同时覆盖会进入同一次渲染的 skill.md 与 prompt_generation.jinja2。
只读这三个文本。不断言运行中的监督环，也不读裁决文件。
"""
```

在文件末尾追加：

```python
def test_generation_anti_mainline_does_not_name_macro_sentiment():
    text = _read(GEN)
    assert "macro_sentiment" not in text
    assert "Do not invent a family the menu does not list" in text
    assert "adaptive gate (0.50-0.52)" in text
    assert "ACTIVE covariate from the pool menu" in text
```

最后一条是这个文件检查清单第 2 条的原文，本任务不要改它。

- [ ] **Step 2: 跑新测试，确认它先失败**

Run:

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /home/abug/timesfm && /home/abug/timesfm/.venv/bin/python -m pytest tests/test_prompt_symbol_authority_20261118.py::test_generation_anti_mainline_does_not_name_macro_sentiment -v'
```

Expected: FAIL。`macro_sentiment` 仍在 anti_mainline 句里。

- [ ] **Step 3: 只改 anti_mainline 那句**

把第 52–55 行：

```text
- anti_mainline: your proposals are FORBIDDEN from using the dominant families
  (see anti_mainline contract above if present, else the families already on the
  frontier). Cover the neglected families (6-family controlled vocabulary, cascade/cov_family.py):
  inventory, volatility, calendar, term_structure, macro_sentiment.
```

换成：

```text
- anti_mainline: your proposals are FORBIDDEN from using the dominant families
  (see anti_mainline contract above if present, else the families already on the
  frontier). Cover a neglected family that has at least one ACTIVE row in the menu. Do not invent a family the menu does not list.
```

`exploit` 段里的 `adaptive gate (0.50-0.52)` 不动。`bridge` 段里的 “CCL positioning” 不动。

- [ ] **Step 4: 跑规格验收列出的全部测试**

Run:

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /home/abug/timesfm && /home/abug/timesfm/.venv/bin/python -m pytest tests/test_prompt_symbol_authority_20261118.py tests/test_praxist_evidence_ladder.py::test_prompt_base_selection_discipline tests/test_praxist_evidence_ladder.py::test_templates_render_directive_context tests/test_praxist_evidence_ladder.py::test_templates_render_without_agenda tests/test_search_peer_surface_20261007.py::test_prompt_teaches_search_fields_and_keeps_success_delta -v'
```

工作树把 `cd` 换成工作树根，解释器仍用 `/home/abug/timesfm/.venv/bin/python`。不要跑全量 pytest。

Expected: PASS。新文件 3 passed，再加上四条既有测试，一共 7 passed。

这四条既有测试读的是 `prompt_base.jinja2`。它们断言 `p_oi.json`、`failure_delta`、`ACTIVE 品种优先`、`success_delta` 的拒收句，以及模板能渲染。它们不断言本计划删掉的短名单、`2-star`、`macro_sentiment` 或 `DirAcc>=0.52`。若其中一条失败，先看是不是 Step 3 改出了 `prompt_base.jinja2` 的范围；本任务只允许改 `prompt_generation.jinja2` 和测试文件。

- [ ] **Step 5: 核对 diff 只有四个路径，不要提交**

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'git -C /home/abug/timesfm diff --stat -- task_FM/prompt_base.jinja2 task_FM/roles/peer_generalist/skill.md task_FM/prompt_generation.jinja2 tests/test_prompt_symbol_authority_20261118.py && git -C /home/abug/timesfm status --short -- task_FM/prompt_base.jinja2 task_FM/roles/peer_generalist/skill.md task_FM/prompt_generation.jinja2 tests/test_prompt_symbol_authority_20261118.py'
```

Expected: 上述四个路径有改动。运行数据、`task.yaml`、`scripts/praxist_goal.yaml`、`scripts/sup_harvest.py`、`covariate_pool.json` 不在这次 diff 里。不要 `git add`，不要 `git commit`，不要重启监督环。

未跟踪的规格 `docs/superpowers/specs/2026-11-18-proposal-quality-design.md` 和本计划可以留在工作区，它们不是这四个路径。
