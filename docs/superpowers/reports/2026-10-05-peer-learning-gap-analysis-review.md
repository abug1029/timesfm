# Peer 学习机制断裂分析报告 · 独立评审（勘误裁定）
> **⚠ 审核修正指针（2026-10-05，T0）**
>
> 本评审经 `2026-10-05-peer-learning-review-and-plan-audit.md` 修正（Issue 1-14，其关键断言已独立复核）。主要修正：
> ① G1「反馈无系统保证」不成立——「22/3/6」由 `known_verdicts.inc.md` 注入送达，非 peer 自算（Issue 1；09:10 提示词 :214-217 实证）；② `9522900` 提交于 10-04 15:47:28 而非「10-05 晨」，且无裁决使用其新协变量；「各族同向」应引注册表 3/10→4/8 与 4/9→3/4 并带样本量（Issue 7）；③ 37.0%→58.3% 比率差 Fisher 双侧 p=0.299，不显著（Issue 8）；④ 附录 A 需加 `decided_at < 2026-10-05T10:40` 上限，否则活数据追加后不复现（Issue 9）；⑤ §7 否决理由部分不成立——示例有 `ts` 与 `pass`/`fail`（即样本量），缺的是协议指纹；族×品种矩阵现有 clues 确实没有（Issue 10）；⑥ G3 收窄为「转述丢戳」（include 已带 fp12），G4 证据改指 `_effective_clue_lines`（:1409）只打印通过数的输出格式（Issue 11）；⑦ 计数勘误：research_memory 211→212、cycles_done 225→226（评审时点值），均须带统计时刻（Issue 13）；⑧ 族名单应抄 `ALLOWED_FAMILIES`（含 momentum 共 6 族；anti_mainline 列的是 5 个被忽略族）、`PIAgentConfig` 位于 task_spec.py:1328、07-18 run 仅有 gen1（Issue 14）；⑨ 变体名勘误：失败哈希对应 variant_id 为 `sr_term_structure_b796d1e1483d` / `sr_term_structure_82991327cde2`（crack_spread_zscore / crack_spread_slope 是协变量名，本评审误作 variant_id）。
>
> 本评审的方向性结论（「回传存在且失败侧有执法、原报告核心事实链不成立」）维持；缺口重界定与落地方案见计划 v2（T0-T3）。

> **日期**: 2026-10-05
> **评审对象**: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis.md`（commit `a5c1412`）
> **方法**: 按 09-28 审核纪律对报告全部可核查断言独立复核：registry 逐行统计（协议分层）、peer 工件取证（handoff / experiment_ledger / memory_prompt / seen_shared_findings / shared_findings）、框架与 task 代码定位、时间断点分析。
> **结论**: **方向有价值——学习回路确有真实缺口（见 §三 G1-G6）；但报告核心事实链多处不成立，需勘误后方可作为 spec 输入。** 报告把实际在运行、且有硬性拒收门强制的学习回路判为「不存在」，把精确的当前协议过滤统计误判为「来源不明/可能幻觉」；其自身复核混用了协议版本，恰违反系统纪律（`045c7e2` 收割/复测只看当前协议）。

## 一、裁定总表

| # | 报告断言 | 独立实测 | 判定 |
|---|---|---|---|
| 1 | `research_memory.jsonl` = 0 行 | 211 个文件全部 0 字节（框架脚手架占位，repo 无写入方） | ✅ 成立 |
| 2 | `shared_store.db` = 0 bytes | 今日各 run 为 196–282KB（run 级存储非空；「无跨 run 持久化」方向成立——每 run 新建 store） | ❌ 事实错误 |
| 3 | Cycle 结果回传 ❌ 无 | 三条硬证据（§二.2）：peer 实引 10-03 近失与失败哈希；exploit 角色被 prompt 指示精炼近失；`no_failure_delta` 拒收门强制引用失败裁决 | ❌ 不成立 |
| 4 | 「22 gate_pass」来源不明/可能幻觉 | v4 协议过滤后 momentum 恰好 22（50 中）；inventory 恰好 3（13 中）；calendar 恰好 6（10 中）——三个数字全部精确命中 | ❌ 不成立 |
| 5 | 证据 vs 认知矛盾（「实际」41/96） | 41/96 是 legacy+v2+v3+v4 混算；当前协议下为 22/50。无矛盾 | ❌ 不成立 |
| 6 | peer 下一轮提案 = 盲猜 | 今日提案 = 近失精炼 + 失败规避（点名哈希）+ 族迁移，全部 registry-informed | ❌ 不成立 |
| 7 | 225 cycle | `cycles_done: 225` | ✅ 成立 |
| 8 | Oct4 39.2%(130) / Oct5 62.0%(50) | registry 级 Oct4 43.6%(39) / Oct5 60%(15)：比率吻合、计数差 ~3.3×（疑似 ledger/汇总级计数）；报告未注明数据来源与查询，不可复现 | ⚠️ 半成立 |
| 9 | 归因①：v4 确认通道修复改善评估逻辑 | E1-E6（`e155474`/`f4e8e90`）只改确认通道语义，未触碰 gate 评估（DM/窗口/分母），机制上不可能改变通过率 | ❌ 机制错误 |
| 10 | （未考虑）真正断点 | 10-04 16:55 数据恢复：恢复前 37.0%（27 中 10）→ 恢复后 58.3%（12 中 7）**同日跳变**，Oct5 60% 延续——评估窗口从止于 09-23 平移至止于 09-30 是最省解释 | ❌ 关键遗漏 |
| 11 | experiment_ledger 只记提案不记结果 | 实测属实（3 条 proposal_authored，无结果字段） | ✅ 成立 |
| 12 | §6「最核心的 gate pass 回传仍未实现」 | 「无系统保证的注入」成立；「未实现」过强（PI agenda 回路运行中、failure_delta 门执法中） | ⚠️ 半成立 |

## 二、关键证据

### 2.1 「22/3/6」= 当前协议过滤后的精确统计

对 `task_FM/config/aligned_verdicts.jsonl`（324 行 = 298 ok + 26 no_data）按协议指纹分层：

| 协议层 | 行数 | 说明 |
|---|---|---|
| 无指纹（legacy，≤09-24） | 169 | 含 09-14~09-24 全部裁决 |
| `bd851c9c`（v2） | 27 | |
| `91ab913e`（v3） | 18 | |
| **`f02b2a43`（v4，当前）** | **110** | 10-01 起 |

v4-only 族统计（status=ok）：

| family | total | pass | peer 引用 |
|---|---|---|---|
| momentum | 50 | **22** | 「dominant family with 22 gate_pass」✅ |
| term_structure | 22 | 10 | |
| inventory | 13 | **3** | 「inventory: 3 gate_pass」✅ |
| volatility | 15 | 3 | |
| calendar | 10 | **6** | 「calendar: 6 gate_pass」✅ |

报告的「实际 41/96」为全协议混算（当前全量 momentum = 44/121，其中 22 为 pre-v4 累计；全量累计恰在 09-29 22:57 达到 22）。数字来源判定：今日 peer 为 gen_0（模板明示「generation 0 or PI panel skipped」无 agenda）+ 框架代码无 "dominant family" 文案（site-packages 全文检索为空，仅 examples 命中）→ 唯一自洽解释为 **peer 自主读 registry 并按当前协议指纹过滤统计**；三个数字同时精确命中排除巧合。

### 2.2 结果数据可达 peer 的三条硬证据

1. **近失精炼**：今日（10-05 09:10 run）gen0_peer0 提案 m_vor，handoff 明文「Refines near-miss m_volatility_e7092bbdd14d (dir_acc=0.498)」——该行实存（decided_at 2026-10-03T21:36:28，gate_pass=False，dir_acc=0.498）。
2. **失败规避**：同 handoff「avoids failed term_structure attempts (b796d1e1483d, 82991327cde2)」——两行实存（sr_crack_spread_zscore，dir_acc=0.501 / sr_crack_spread_slope，dir_acc=0.494，均 term_structure、status=ok）。
3. **制度性执法**：`no_failure_delta` 拒收门在 `scripts/praxist_supervisor.py:2150` 强制执行——提案命中国标协议下已有 gate_pass=False 的 (symbol, cov) 时必须引用失败 variant_id 并说明增量，否则拒收。代码注释载明实战史：单轮拒 1,922 份（:1395）；09-24 曾因过严饿死慢环后调优（:1920）。

另：`task_FM/prompt_generation.jinja2` 注入 `frontier_summary`（parent-eligible 近失 + dir_acc）与 exploit 角色指令「take the strongest-mechanism near-miss verdicts ... and propose a refined symbol x cov combination」。

### 2.3 报告漏掉的运行中机制

| 机制 | 证据 |
|---|---|
| **PI panel 议程回路** | `PIAgentConfig enabled=True`（`.venv/.../praxist/task_spec.py:1325-1343`）：每两代之间运行一次，读上代 state 产出 `research_agenda_gen{N+1}.yaml`；今日每个 run 均有 `agendas/research_agenda_gen1/gen2.yaml` + gen_0/1/2 三代。agenda 含 mainline_observation、cross_peer_hypotheses（带 source_findings / kill / promote / minimal_test）、角色契约。**PI 自身在 main_risk 中诊断了真实缺口**：「All gen0 hypotheses remain untested (dir_acc=None) with no gate_pass evidence — cohort is over-proposing without validation gates」 |
| **anti_mainline 多样性契约** | prompt_generation.jinja2:52 + 6 族受控词表（cascade/cov_family.py）：inventory, volatility, calendar, term_structure, macro_sentiment |
| **DEAD 变体纪律** | prompt_base.jinja2：「gate_pass=False 且 status=ok：变体级 DEAD。没有 failure_delta 不得复活」 |
| **协议轮换遗忘模型** | `sr_calendar_cyclical` 旧裁决为 09-17（legacy 协议：gate_pass=True / fdr_pass=False，dir_acc=0.617，n=588）；今日重提在 v4 纪律（`045c7e2` 旧裁决不作数）下**合法**，但 peer 未引用先验。报告将此误读为「重复劳动/负学习」，实为协议版本化遗忘这一更深的设计现象 |

### 2.4 数据恢复才是通过率断点（原 §5 归因重写依据）

10-04 当日按 16:55（数据恢复完成时刻）分割：

| 窗口 | ok verdicts | pass | rate |
|---|---|---|---|
| 10-04 恢复前（<16:55） | 27 | 10 | 37.0% |
| 10-04 恢复后（≥16:55） | 12 | 7 | **58.3%** |
| 10-05（截至评审时 10:40） | 15 | 9 | 60.0% |

通过率跃升发生在 **10-04 晚间、恢复完成后即刻**，而非跨日边界。机制：恢复使评估窗口从止于 09-23 平移至止于 09-30（v4 绝对锚定 + window_anchor），窗口内容变化 → 各族通过率同向抬升（原报告自身数据显示 term_structure +27pp 与 momentum +28pp 并行——共同因而非构成效应）。原报告三个候选解释均不成立：① E1-E6 未触碰 gate 评估（机制错误）；② 新协变量 pmi/crack_spread_acceleration 于 10-05 晨入队（`9522900`），无法解释 10-04 晚；③「随机波动」不如窗口平移省。

### 2.5 其他核查

- **shared_store.db**：per-run 存储，今日各 run 196–282KB 非空；「0 bytes」不成立。
- **research_memory.jsonl**：211 个文件全部 0 字节 ✅。
- **130/50 计数**：与 registry 级（39/15）差 ~3.3× 而比率一致——疑似 ledger/汇总级计数；原报告未注明来源与查询，不满足可复现门槛（09-28 纪律）。
- **no_data 行**：registry 含 26 条 10-03 21:36–22:37 的 no_data 行（全部 jd/sr，修复前确认风暴遗物）——任何 registry 统计必须过滤 `status=="ok"`。
- **sr_calendar_cyclical 重复提案**：09-29 与今日各一次（今日 09:12 重新 share，uuid 不同）；协议纪律下合法但未引用 09-17 先验。

## 三、真实缺口（评审版）

| ID | 缺口 | 证据 |
|---|---|---|
| G1 | 跨 run 定量反馈**无系统保证**：gen0 无 agenda，registry 不自动进 prompt，依赖 peer 主动性 | 今日 peer 自算是例外而非常态保证 |
| G2 | 成功侧无执法：失败侧有拒收门，成功侧仅散文警告（「不要当已解决再提一遍」） | prompt_base.jinja2:80 |
| G3 | 数字僵尸化风险：handoff/findings 中统计不带时间戳/指纹戳，逐 session 原样重放 | 今日的 22 恰好正确；下周重放的 22 必错 |
| G4 | 无样本量纪律：6/6=100%、0/4=0% 被当结论引用 | 原报告 §5 自身展示 lh 56%→0% 日摆动 |
| G5 | 无 symbol×family 定量视图注入 | 族级统计靠 peer 自算，品种×族矩阵无人提供 |
| G6 | 协议轮换遗忘未显式化：合法重测但无先验上下文标注 | sr_calendar_cyclical 案例 |

## 四、原报告 §7 方案评估

| 提案 | 评估 |
|---|---|
| Cycle 结果聚合器（supervisor 层） | **冗余**：registry 已是唯一事实源且被消费；缺口在注入保证，不在聚合 |
| `data/assets/cross_run_learning.jsonl` | **三缺陷**：① 与 registry 形成第二事实源；② schema 无 protocol_fingerprint 字段——会把原报告自身犯的混协议错误制度化；③ 无样本量/日期戳，聚合日志随数据流动即刻过期 |
| 注入 memory_prompt | **目标错误**：memory_prompt 为框架渲染（site-packages），repo 不可控；repo 可控注入点 = `prompt_base.jinja2` / `prompt_generation.jinja2` / supervisor 产出的 digest 文件 |
| Peer 提示词纪律 | **半数已存在**（failure_delta）；应扩展而非新造 |

## 五、解决方案 → 实施计划指针

S1 Registry Digest（关 G1/G4/G5）· S2 success_delta 门（关 G2）· S3 引用溯源纪律（关 G3）· S4 样本量纪律（并入 S1）· S5 历史协议注记（关 G6，并入 S1）· S6 原报告勘误（P0）。

实施计划：`docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md`（T0-T5）。

## 六、复核命令附录

（工作目录 `/home/abug/timesfm`；v4 fp 以 `task_FM/evaluations/fm_eval/evaluator.py::compute_protocol_fingerprint` 现算为准，当前 `f02b2a433fd572ea…`）

```bash
# A. v4-only 族统计（§2.1 复核；期望 momentum (50,22) / inventory (13,3) / calendar (10,6)）
.venv/bin/python - <<'PY'
import json, collections
rows = [json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl')]
V4 = 'f02b2a433fd572ea'
fam = collections.defaultdict(lambda: [0, 0])
for r in rows:
    if r.get('status') == 'ok' and (r.get('protocol_fingerprint') or '')[:16] == V4:
        f = fam[r.get('cov_family')]
        f[0] += 1
        f[1] += int(bool(r.get('gate_pass')))
print({k: tuple(v) for k, v in sorted(fam.items())})
PY

# B. 10-04 恢复前后分割（§2.4 复核；期望 pre (27,10) / post (12,7)）
.venv/bin/python - <<'PY'
import json, collections
rows = [json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl')]
split = collections.defaultdict(lambda: [0, 0])
for r in rows:
    if r.get('status') == 'ok' and (r.get('decided_at') or '')[:10] == '2026-10-04':
        k = 'pre' if (r.get('decided_at') or '')[11:16] < '16:55' else 'post'
        split[k][0] += 1
        split[k][1] += int(bool(r.get('gate_pass')))
print({k: tuple(v) for k, v in split.items()})
PY

# C. peer 引用行存在性（§2.2 复核；期望 3）
grep -c 'm_volatility_e7092bbdd14d\|b796d1e1483d\|82991327cde2' task_FM/config/aligned_verdicts.jsonl

# D. 运行中机制定位（§2.3 复核）
ls task_FM/experiments/run_2026-10-05_05-27-04_primary_task_FM/agendas/
grep -n 'no_failure_delta' scripts/praxist_supervisor.py
grep -rn 'dominant family' .venv/lib/python3.11/site-packages/praxist | grep -v examples   # 期望为空
```

---

*本评审为 `2026-10-05-peer-learning-gap-analysis.md` 的勘误裁定与缺口重界定；实施计划见 `plans/2026-10-05-peer-learning-feedback-hardening.md`。*
