# 三环 Verdict 跟进 Spec

> 日期: 2026-09-19。上游: `docs/2026-09-19-verdict-analysis-report.md`。
> 状态: **待宿主批准后实施**。实施计划: `docs/2026-09-19-three-loop-followup-impl-plan.md`。
> 裁决口径仍以 `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md` 为唯一权威；本文不改写硬门公式。

## 1. 目的

把 2026-09-19 分析报告里的问题分成三类：**已核实不是 bug**、**必须修的控制面缺陷**、**明确不做**。修完后，快环不再把 token 花在已经证伪的品种/已经写过的提案上，PI 代际议程能在 `cohort_size=2` 下通过校验。

完成标准（全部满足才算本 spec 落地）：

1. 新写入的 aligned verdict 带有 `baseline_dir_acc` 与 `effective_min`，报告不再把自适应门槛误读成「dir_acc&lt;0.52 却过门」。
2. `generation_policy.cohort_size=2` 时，PI 合成的 `peer_contracts` 只需覆盖 `exploit` 与 `falsifier` 两个角色即可通过校验；不再因为缺 `bridge`/`anti_mainline` 整份议程被拒。
3. peer prompt 同时看到：品种级统计、符号状态（DEAD/HOLD/ACTIVE）、以及「已提案但尚未出 verdict」的 `variant_id`。
4. harvest 对 DEAD 品种直接拒绝；评分函数对失败率高的品种施加可复现惩罚。
5. 不修改 `.venv` 里的 Praxist 源码；不改 `gate()` 的自适应公式。

## 2. 问题清单与核实结论

| ID | 报告说法 | 核实 | 本 spec 处置 |
|---|---|---|---|
| P0-1 | `m_pca_momentum` (0.502) 与 `sr_crack_spread_level` (0.510) 低于 0.52 却 `gate_pass=True` | **符合 v23 设计，不是 bug** | 只补可观测字段，不改门槛 |
| P0-2 | PI synthesis 缺 `exploit`/`falsifier`，gen_2 无议程 | **结构不匹配：2 个 peer 无法覆盖 4 个必填角色** | 任务侧 topology `peer_role_rotation` 改为恰好 2 个角色 |
| P1-1 | eg/jd/lh/rb 连续失败仍被提案 | **属实**：prompt 只注入最多 20 条 verdict，且无品种级摘要；评分无品种失败惩罚 | 品种状态表 + prompt 摘要 + 评分惩罚 + harvest 拒绝 |
| P1-2 | `jd_ccl` / `sr_qstick` 跨代各提案 3 次 | **属实**：harvest 入口会按 `variant_id` 去重，但 peer 在写文件前看不到「已提案未入队」集合 | prompt 注入全量已提案 `variant_id` |
| P2 | launcher 退出 `Event loop is closed` | 进程退出清理噪音，不影响 verdict | **不做** |
| 死区族归档 | ccl/nvi/vor 等族建议标记 DEAD | 样本偏少（3–4 条），且 `oi`/`calendar_cyclical` 仍有效 | **本轮不做族级归档** |

### 2.1 P0-1 证据（为何不是 bug）

权威公式（v23 spec §5 与 `task_FM/evaluations/fm_eval/evaluator.py` 的 `gate()` 一致）：

```
effective_min = max(0.50, min(0.52, baseline_dir_acc))   # baseline 缺失时 = 0.52
gate_pass    = n>=350 and n_eff>=50 and dir_acc >= effective_min
```

磁盘基线 `task_FM/config/baseline_metrics.json`：

| 品种 | baseline_dir_acc | effective_min | 争议变体 dir_acc | 预期 gate |
|---|---|---|---|---|
| m | 0.486 | 0.50 | 0.502 (`m_pca_momentum`) | True |
| sr | 0.502 | 0.502 | 0.510 (`sr_crack_spread_level`) | True |

两条 verdict 均无 `baseline_dir_acc` / `effective_min` 字段，所以分析报告只能拿字面 0.52 去对，产生假异常。本 spec **禁止**把自适应门槛改回全局 0.52 硬切——那会否决 v23 已批准的品种自适应。

`gate_pass=True` 仍不是成功：成功继续要求 `fdr_pass` 或 `migrated_pass`。这两条的 `fdr_pass=False`，状态应继续显示为 `hard-gate-but-losing`。

### 2.2 P0-2 证据（真正的 P0）

Praxist `PIAgent.REQUIRED_PEER_ROLES = {exploit, falsifier, bridge, anti_mainline}`（4 个）。`task_FM/task.yaml` 的 `cohort_size: 2`。校验要求 `len(peer_contracts)==2` **且** 合同角色集合覆盖全部必填角色。2 个合同不可能覆盖 4 个角色，因此 **每次** gen_N→gen_{N+1} 合成都会失败。

当前 run `run_2026-09-19_08-35-03_primary_task_FM` 的被拒议程：

| 合成 | 实际角色 | 校验缺失 | 后果 |
|---|---|---|---|
| gen0→gen1 | bridge + falsifier | anti_mainline, exploit | `research_agenda_gen1.yaml.rejected`，gen_1 无议程 |
| gen1→gen2 | bridge + anti_mainline | exploit, falsifier | `research_agenda_gen2.yaml.rejected`，gen_2 无议程 |

Chair 其实写出了结构完整的议程（有 `cross_peer_hypotheses` 和 2 份合同），只是角色词不在「四个都要有」的集合里。`strict=False` 时 Praxist 回退到无议程，peer 按 `peer_generalist` 默认行为重复提案。

仓库里这件事已被钉成已知运营债：`tests/test_praxist_evidence_ladder.py` 的 `test_task_cohort_covers_four_pi_roles` 以 `xfail` 写着「cohort_size=2 配合 4 角色，控 token」。本 spec **关闭这笔债**：不把 cohort 扩到 4，改为 rotation 长度为 2。该 xfail 必须改成「rotation 长度 == cohort_size」的正向断言，禁止继续 xfail。

**禁止**改 `.venv` 里的校验器。官方扩展点是任务侧 panel topology 的 `peer_role_rotation`（Praxist issue #83/#84）：非空时用它替换硬编码的 4 角色集合。

## 3. 非目标

- 不修改 `gate()` 公式、不把 0.52 改成不可放宽的硬切。
- 不修改 `.venv` / Praxist 发行源码。
- 不把协变量族（ccl/nvi/vor/…）整族 `archived`。
- 不修 launcher asyncio 退出噪音。
- 不改慢环 walk-forward、DM/FDR、TimesFM 权重路径。
- 不把 `hard-gate-but-losing` 当成 1 星成功。

## 4. 设计

### 4.1 门控可观测性

**唯一公式家**：`evaluator.compute_effective_min(min_dir_acc, baseline_dir_acc)`。`gate()` 必须调用它，禁止在 `build_summary` 再写一遍。

`build_summary` 写入 verdict 顶层（同时写入 `metrics` 子字典）：

| 字段 | 类型 | 空值 | 含义 |
|---|---|---|---|
| `baseline_dir_acc` | float 或 null | 基线缺失时 null | 该品种基线 DirAcc |
| `effective_min` | float 或 null | 墓碑/error 时 null | 实际使用的 dir_acc 门槛 |

写入的 `baseline_dir_acc` 必须是 **当次 `gate()` 实际收到的值**（慢环从 `baseline_points_{symbol}.jsonl` 的 `dir_ok` 比例现场计算，见 `task_FM/evaluations/fm_eval/run.py`）。不要回头读 `baseline_metrics.json` 再写一遍——两份数字今天碰巧接近，但不是同一条路径。

`scripts/registry_lib.py` 的 `VERDICT_FIELDS_V2` 增加这两键；二者都进入 `VERDICT_FIELDS_V2_NULLABLE`（墓碑保持可写）。已存在的 81 条历史 verdict **不回填**；新写入必须带字段。分析脚本若缺字段，按「未知门槛」展示，不得再假设 0.52。

### 4.2 两名 peer 的议程角色

在 `task_FM/.praxist/plugins/panel_topologies/fm_two_peer/` 增加任务侧 topology 插件：

- 复制 bundled `legacy_multi_pi_two_round` 的 topology 主体（modes/roles/rounds 不变，继续用 `task_role:builder_pi` 等 bundled 角色）。
- **唯一增量**：

```yaml
peer_role_rotation:
  - exploit
  - falsifier
peer_role_descriptions:
  exploit: 在近门/过硬门未过 FDR 的变体上精炼 symbol×cov，写出更锋利的机制与 kill/promote。
  falsifier: 不追榜。针对主线机制写一条应失败的证伪提案（finding_type=challenge）。
```

- `topology_ref: panel_topology:fm_two_peer`

`task_FM/task.yaml` 的 `praxist_plugins.panel.topology` 改为 `panel_topology:fm_two_peer`。`generation_policy.cohort_size` 保持 2。

不变量（合同测试钉死）：

```
len(peer_role_rotation) == generation_policy.cohort_size == 2
set(peer_role_rotation) == {exploit, falsifier}
```

若未来把 `cohort_size` 改成 4，必须同步加长 rotation（例如补 `bridge`、`anti_mainline`），否则校验再次结构失败。本 spec 不把 cohort 扩到 4。

### 4.3 品种状态表

新文件 `task_FM/config/symbol_status.json` 是品种级探索状态的**唯一家**。peer prompt、harvest、评分都读它，禁止在三处各写一套阈值。

```json
{
  "schema": "fm.symbol_status.v1",
  "updated": "2026-09-19",
  "symbols": {
    "eg": {"status": "DEAD", "reason": "22 ok verdicts, 0 pass, best dir_acc=0.490"},
    "jd": {"status": "HOLD", "hold_generations": 5, "reason": "7 ok verdicts, 0 pass, best=0.468"},
    "lh": {"status": "HOLD", "hold_generations": 5, "reason": "7 ok verdicts, 0 pass, best=0.488"}
  }
}
```

未出现的品种视为 `ACTIVE`。`rb`/`sh`/`i` 本轮不写入（样本 &lt; 5）。

状态语义：

| status | harvest | peer prompt | 解除 |
|---|---|---|---|
| `DEAD` | 拒绝该 symbol 的一切新 `variant_id`（`reject_reasons.symbol_dead`） | 明确写「不要提案」 | 只允许宿主改 JSON；代码不自动复活 |
| `HOLD` | 拒绝（`symbol_hold`） | 写「暂停 N 代」 | 宿主改 JSON，或删除该键 |
| `ACTIVE`（缺省） | 现行规则 | 注入统计，不禁提案 | — |

`hold_generations` 本轮只作提示数字，**不**在 supervisor 里做代际计数器——避免与 Praxist gen_id / supervisor cycle 两个时钟纠缠。要恢复探索，宿主删键或改 status。

### 4.4 known_verdicts 注入（跨代去重的真正入口）

`materialize_known_verdicts(snapshot, dest_path)` 扩展为同时吃三份输入（可用关键字参数，缺省扫描现行路径）：

1. **品种表**：对 `GOAL_SYMBOLS_SET` 每个品种输出一行：`status, n_ok, n_pass, best_dir_acc, 建议`。DEAD/HOLD 来自 4.3；计数来自 snapshot。此表**不得截断**。
2. **禁止再提案的 variant_id 集合**（并集，按字母序，允许截断到 80 条并注明 `truncated`）：
   - snapshot 里已有的 vid
   - `aligned_pending.jsonl` + `aligned_pending.inprogress.jsonl` 的 vid
   - 当前与最近一次 run 的 `results/**/proposals/*.json` 里解析出的 `symbol_cov`
3. **亮点样本**：现行「最多 20 条、先 `gate_pass` 再 `dir_acc`」保留，作为机制参考，不再承担去重。

文案必须继续区分 `v2_pass` / `hard-gate-but-losing` / 变体级 `DEAD`（`gate_pass=False`）。变体级 DEAD 与品种级 DEAD 不要混名：prompt 里品种级写 `SYMBOL_DEAD`，变体级保持 `DEAD`。

### 4.5 评分惩罚

`_proposal_priority_score(prop, cov, symbol, snapshot)` 增加品种失败项，加在现行分数之后：

```
n_fail = 该 symbol 且 status=ok 且 gate_pass=False 的条数
penalty = 0                     if n_fail < 3
        = 4 * (n_fail - 2)      if 3 <= n_fail < 8
        = 24 + 8 * (n_fail - 7) if n_fail >= 8
score  = score - penalty
```

再叠加状态表：`DEAD` → `score -= 50`；`HOLD` → `score -= 20`。惩罚必须确定性、不读时间、不读 LLM。

这是第二道闸：即使 prompt 被忽略，harvest 排序也会把 eg 类提案压到 QD 座位之外。DEAD/HOLD 的硬拒绝仍以 4.3 harvest 为准。

现有探索偏置测试的期望分数会变，**同步改测试期望**，不要为了保旧数字而关掉惩罚。

### 4.6 错误处理

- `symbol_status.json` 缺失或 JSON 损坏：fail-open 为空表（全 ACTIVE），stderr 打 `[WARN] symbol_status load failed`。不得让 supervisor 崩。
- 提案 JSON 缺 `symbol`：现行 `missing_symbol_or_cov`，不变。
- topology 插件未加载：启动期合同测试失败（见计划 Task 2），禁止带错 topology 跑快环。

## 5. 测试要求

每个行为必须有失败先于实现的测试（仓库既有风格：`tests/test_praxist_fm_evaluator.py`、`tests/test_supervisor.py`、`tests/test_harvest_proposals.py`、`tests/test_praxist_task_contract.py`）。

最低用例：

1. `compute_effective_min(0.52, 0.486)==0.50`；`gate` 在 dir_acc=0.502、baseline=0.486 时 True；无 baseline 时 False。
2. `build_summary` 输出含 `baseline_dir_acc` 与 `effective_min`；墓碑二者为 null。
3. topology 插件 `peer_role_rotation` 长度等于 `task.yaml` 的 `cohort_size`，集合为 `{exploit, falsifier}`。
4. `materialize_known_verdicts` 含品种表、含「仅存在于 proposals 树、不在 snapshot」的 vid。
5. harvest：`eg_*` 在 DEAD 下 `symbol_dead`；`jd_*` 在 HOLD 下 `symbol_hold`；ACTIVE 品种行为不变。
6. `_proposal_priority_score`：eg 模拟 8 条失败后分数低于同 cov 的新品种提案。

## 6. Key Decisions

1. **P0-1 定性为可观测性缺口，不是门槛 bug。** 改公式会和已批准的 v23 自适应门冲突，也会把 m/sr 这类低基线品种的近门信号全部杀掉。
2. **P0-2 在任务侧用 `peer_role_rotation` 修，不改 Praxist。** 发行包要求 4 角色是给 5 人 cohort 的；本任务 cohort=2，官方扩展点就是 rotation。扩 cohort 到 4 会成倍烧 token，本轮不做。
3. **品种 DEAD/HOLD 用手写 JSON，不用代码自动晋升。** 自动规则会被「再试一次换机制」的合法探索误杀；宿主已经在报告里做了裁定草案。
4. **跨代去重的主入口是 prompt 注入，不是 harvest 再收紧。** 未入队的提案仍应允许下一轮 harvest 选中；要挡的是 LLM 再写一遍。
5. **族级归档不做。** 3–4 条 verdict 不够判死整个协变量族；`oi`/`calendar_cyclical` 仍在产。

## 7. 开放问题（宿主可改 JSON，不挡实施）

若批准本 spec，下列默认即生效；要改只动 `symbol_status.json`，不必改代码：

- eg → DEAD
- jd、lh → HOLD（文案写暂停 5 代；解除靠人手）
- rb/sh/i → 不标记

若宿主坚持把 `dir_acc>=0.52` 改成不可放宽硬切，那是对 v23 spec 的修订，**不在本次实施范围**，需要另开设计。

## 8. PR 切分

| 顺序 | 标题 | 文件 | 依赖 |
|---|---|---|---|
| PR1 | 门控字段可观测 | `evaluator.py`, `registry_lib.py`, `tests/test_praxist_fm_evaluator.py` | 无 |
| PR2 | 两 peer 议程角色 | `task_FM/.praxist/plugins/.../plugin.yaml`, `task_FM/task.yaml`, 合同测试 | 无（可与 PR1 并行） |
| PR3 | 品种状态 + prompt 去重 + 评分/harvest | `praxist_supervisor.py`, `symbol_status.json`, harvest/supervisor 测试 | PR2 非硬依赖；建议 PR1 之后合，便于报告对照字段 |

每个 PR 必须带绿测试，禁止把「下一步再写测试」写进 diff。
