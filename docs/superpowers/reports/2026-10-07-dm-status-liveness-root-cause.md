# dm_status 生产活性根因调研报告（Q6 子项目）

> **日期**: 2026-10-07
> **性质**: 只读调研（零代码改动）；宿主裁定记录见 plans/2026-10-07-tech-debt-closure-plan.md §8 Q6
> **数据基线**: task_FM/config/aligned_verdicts.jsonl 396 行（快照于 2026-10-07 上午；调查期间监督环仍在追加，早间口径 393 行）
> **代码基线**: live /home/abug/timesfm（master@5e7237a，监督环 PID 146369 运行中）+ pevs worktree（feat/positive-ev-factor-search@ad05fea，P2.6 增量判据核对）
> **结论一句话**: dm_status 可确认分支（ok / set_mismatch_ok）在生产**结构不可达**，一手根因是 credibility spec §7.8 开放问题 #8（缺失-状态独立性判定方法）**至今未裁定**，missingness_admissible 按设计恒 False；生产的"mismatch"实测为基线快照 vs 滚动评估窗的**良性边缘漂移**（≤2.7%，47.6% 行为零不匹配），并非守卫所防的"状态相关缺失"。**这不是代码 bug——代码忠实实现了 spec 的保守默认；修复的本质是一次设计裁定，不是一次缺陷修复。**

## 0. 结论速览

| 层 | 结论 |
|---|---|
| 分布层 | 396 行历史中 dm_status∈{ok,set_mismatch_ok} 的行数 = **0**；v4 时代（10 月）173/182 行全落 set_mismatch_descriptive |
| 机制层 | 判据梯中 `if not missingness_admissible: return set_mismatch_descriptive` 先于 mismatch 检查；生产唯一入口 build_summary 不传该参数（默认 False）；全仓只有读取方，**无任何写入方/评估器** |
| 根因层 | spec §7.8 开放问题 #8 未裁定（分桶方案/独立性检验方法/注册时冻结三要素悬空）→ 按设计的保守默认执行；实测 unmatched 为窗口边缘确定性漂移（实证见 §4.2），与守卫目标（状态相关缺失）不同物 |
| 影响层 | dead families 门休眠（恒空转）；fdr_pass 永不可持久化（92 行 exploration gate_pass=True 全部不可落盘）；**预注册确认轨道结构性无法确认**（两族只能等 2028-10-02 预算截止 underpowered 封账）；pevs P2.6 增量判据 pass 分支同样不可达（aligned_slow_loop.py:263 硬编码 False） |
| 修复本质 | 宿主裁定 §7.8（或裁窄守卫语义）→ 实现 → 若 dm_status 语义变更须走协议指纹评估（v5） |

## 1. 症状与合并理由

**症状一（技术债 N1）**: `_family_confirmatory_counts` 只数可确认行 → live 实跑 fam_ok={} → `_dead_families` 恒空 → "## Dead families" prompt 段永久为空、family_dead 门永不触发。
**症状二（pevs P2.6 专家审核）**: 增量判据要求可确认 dm_status → 生产恒 fail → 途径 (b) 晋升部署后休眠。
**合并理由**: 两症状消费同一判据（dm_status ∈ {ok, set_mismatch_ok} ∧ missingness_admissible），一份证据两处消费。

## 2. 分布层证据（396 行全量量化）

### 2.1 dm_status 全量分布

| dm_status | 行数 | 说明 |
|---|---|---|
| set_mismatch_descriptive | 189 | 唯一的生产稳态 |
| <缺字段> | 169 | = 143 行 pre-machinery（2026-09 legacy，无协议指纹）+ 26 行 no_data 存根 |
| insufficient_common | 26 | 全部 2026-09、全部 v2 指纹 bd851c9c（PR-A1 前的 fail-loud 高发期，evaluator 注释自证） |
| no_common_cutoff | 11 | 9 月 2 行 + **10 月仍有 9 行**（跟进项，开放问题 #3） |
| protocol_mismatch | 1 | v3 时代单行 |
| **ok / set_mismatch_ok** | **0** | **396 行历史可确认行数恒为零（结构不可达的直接证据）** |

### 2.2 按协议指纹 × 时间

- v4 `f02b2a43` 182 行 = descriptive 173 + no_common 9（10-01 上线后）
- v3 `91ab913e` 18 行 = descriptive 16 + protocol_mismatch 1 + no_common 1
- v2 `bd851c9c` 27 行 = insufficient 26 + no_common 1
- 月度：2026-09 descriptive 仅 16 行 → 2026-10 descriptive 173 行（v4 上线后全量落描述性）

### 2.3 "mismatch"的实际大小（189 行 descriptive）

| (unmatched_v, unmatched_b) | 行数 |
|---|---|
| (0, 0) | **90（47.6%）** |
| (13, 13) | 54 |
| (10, 10) | 31 |
| (16, 16) | 14 |

- 两侧恒等对称（量子化取值），比值中位 1.7%、最大 2.7%；n_avail 两侧恒 588，common 572-588
- **47.6% 的行集合完全一致仍落 descriptive**——因为 admissible 检查先于 mismatch 检查（§3.1）
- 若 admissible=True：90 行 → ok，99 行 → set_mismatch_ok，**189 行全部转为可确认**（协议指纹一致前提下）

### 2.4 其他口径

- gate_pass=True 134 行（exploration 92 + legacy 42 + confirmation 0），**可持久化（fdr_pass_persistable）0 行**
- run_mode=confirmation 仅 4 行，全部 status=no_data 存根（§5.3）
- eval_end_ts 51 行，首行 2026-10-06T02:03（T2d 随重启生效的干净边界），值全为 2026-09-30 15:00（国庆假期数据末端）
- descriptive 按品种分散：jd 36 / rb 27 / lh 25 / m 22 / ss 20 / p 13 / ……（系统性而非品种特异）

## 3. 机制层证据（代码路径）

### 3.1 判据梯（cascade/statistical_tests.py:322-396 `pair_dir_ok_series_with_diagnostics`）

优先级（首个匹配者胜）：no_baseline → protocol_mismatch → no_common_cutoff → insufficient_common → **set_mismatch_descriptive** → set_mismatch_ok → ok

关键分支（:389-391）：

```
if not missingness_admissible:
    return _base(dm_status="set_mismatch_descriptive", **counts)
```

**该分支位于 set_mismatch 检查之前**——admissible=False 时无论集合是否完全一致都落 descriptive。

### 3.2 生产入口不传参数（task_FM/evaluations/fm_eval/evaluator.py:479-496）

build_summary 的 dm_diag 初始化 missingness_admissible=False（:482），调用 pair 函数时只传 variant_protocol/baseline_protocol（:492-496），**不传 missingness_admissible** → 默认 None → False。

### 3.3 全仓只有读取方，没有写入方

| 位置 | 角色 |
|---|---|
| supervisor :22 `_PERSISTABLE_DM={ok,set_mismatch_ok}` + fdr_pass_persistable | 读取（fdr 持久化门） |
| preregistry :455 `_test_invalid` / :467 `_passes_confirmation` | 读取（预注册确认判据） |
| evaluator :482 / pair 函数默认参数 | 恒 False 写入 |
| **missingness_admissible=True 的评估器** | **不存在** |

结论：**ok / set_mismatch_ok 从生产入口结构不可达**——不是"很难达到"，是没有任何代码路径能到达。

## 4. 根因层

### 4.1 一手根因：spec §7.8 开放问题 #8 未裁定

credibility spec（docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md）：

- :459 规则："仅当能**证明**缺失与状态独立 → True；否则 False"
- :461 "故在 §7.8 裁定前 missingness_admissible **恒为 False**……**这是有意的保守默认，不是缺陷**"
- :1471 开放问题 #8 三要素悬空：① 分桶方案（复用 Regime/VolRisk vs 独立时间分桶）② **独立性判定方法**（卡方/比例检验？阈值？最小桶样本？）③ 分桶与判定规则注册时冻结（不得事后挑选分桶）
- 09-29 spec 实施审计 :72 早已挂账："family 封账缺失判定方法（§7 Q8）❓ 未裁定｜missingness_admissible 恒 False（保守默认）"

→ 评估器从未实现的原因是**它的判定方法从未被裁定**。这是设计流程的刻意暂停点，不是实现遗漏。

### 4.2 生产"mismatch"的真实来源（实证：jd_ccl 案例）

对 jd_inventory_1d7d1878f894（jd_ccl，unmatched 10/10，common 578）做 cutoff 集合差分析：

- **only_variant 11 点全在尾部**：2026-09-17 ~ 2026-09-23（最新累积的数据）
- **only_baseline 10 点全在头部**：2025-09-26 ~ 2025-10-09（最旧的数据）
- 正确配对基线 = baseline_points_jd_nocov.jsonl（inter 578；cov 版基线 inter 339 = 非本变体的配对目标）

**判读**：变体在滚动前窗（末端=最新数据）上评估，基线 points 文件是**冻结快照**（ensure_baselines 再生波次间隙中静止）。新数据每天累积 → 变体窗每天向前滑 → 相对冻结基线每天在尾部多出若干点、头部少掉若干点。量子化的 (10/13/16) 对应各基线批次锚定日以来的漂移量。

**关键辨析**：守卫设计防的是"缺失与市场状态相关"（选择偏差——比如某状态段变体系统性无输出）。生产实际出现的是**窗口边缘的确定性漂移**——每一点缺失都有明确成因（窗滑动），与市场状态无关。**守卫瞄的敌人和战场上实际出现的敌人不是同一个。**

### 4.3 次要观察

- insufficient_common 26 行全在 9 月 v2 时代 → PR-A1 已修复（10 月零发生）
- 10 月 no_common_cutoff×9 待查（零共同 cutoff，疑似新变体早期窗口/基线未再生，开放问题 #3）
- 案例行共同窗右端停在 2026-09-17——DM 实际落后最新数据约 2 周（开放问题 #5）

## 5. 影响层

### 5.1 dead families 门休眠（N1）

_family_confirmatory_counts 依赖可确认行 → 恒 0 → _dead_families 恒空 → prompt 段空 + family_dead 门永不触发。真死家族持续吃探索预算。**浪费无法精确量化**（门从未生效过，无对照期可比较）。

### 5.2 fdr 持久化恒拒

promote_batch_for_persistence 对一切行拒绝落盘 fdr_pass=True → 92 行 exploration gate_pass=True 全部不可持久化确认。

### 5.3 预注册确认轨道结构性瘫痪（v4 旗舰特性）

- 34fedcb 预注册两族：jd daily_slope+vor（n_req=1,199）、sr daily_slope+vwap_deviation（n_req=986）
- _passes_confirmation 需要 missingness_admissible=True ∧ dm_status∈ok 集 → **结构上永不满足**
- 唯一终局 = 2028-10-02 预算截止 underpowered 封账
- 至今 4 行 confirmation 记录全部是 no_data 存根（__prereg_ 检查点、n=0、p=1.0、2026-10-03T22:31/22:37、git_rev e155474/b8a2118）——**真实确认评估从未发生**（派发活性是相邻问题，开放问题 #2）

### 5.4 pevs 途径 (b) 晋升休眠（P2.6）

pevs worktree scripts/aligned_slow_loop.py:263 **硬编码 missingness_admissible=False**（默认参数，无调用方覆盖）→ :285 检查不过 → incremental_vs_incumbent ∈ {fail, not_applicable} 恒成立，pass 分支不可达。**P2.6 忠实实现了 spec，但 spec 自己的 §7.8 依赖让 pass 分支出生即死。** P2.7 的 dm_status 口径实现裁决依赖本报告（计划已挂账）。

### 5.5 系统级含义

现状 = "探索可跑、确认全休眠"：系统能产生 gate_pass=True 的探索证据，但这些证据**永远不能毕业为确认知识**（不可持久化、不可数进家族死亡、不可确认预注册）。v4 的核心设计意图（确认轨道）在 §7.8 裁定前处于设计性暂停。

## 6. 修复选项清单（只列不决策）

| 选项 | 内容 | 工作量 | 优点 | 缺点/前置 |
|---|---|---|---|---|
| A. 按 spec 原设计走完 §7.8 裁定 | 宿主裁定三要素（分桶/独立性检验/冻结）→ 实现 missingness 评估器 | 裁定 0.5d + 实现 2-3d | 语义最严谨，spec 原意 | **L2 诊断字段（missing_pattern/missing_rate_by_bucket）生产未采集**，需先补采集管道；且对 10-16 点边缘漂移可能"桶样本不足证明不了独立" → 保守默认依旧 |
| B. 窄化守卫语义：边缘漂移豁免 | 区分"状态相关缺失"与"确定性边缘漂移"：unmatched 仅落在窗两端 ±k 点内（或 unmatched/avail ≤ 阈值）→ admissible=True；状态相关缺失仍 False | 1-2d | 直接对准生产实际形态（47.6% 零不匹配 + 其余边缘漂移）；现存 189 行 100% 可判定 | 改变 spec 语义 → dm_status 语义变更 = gate 评估语义变更 → **必须走 v5 协议指纹评估**；"边缘漂移无害"需单独论证 |
| C. 基线再锚定 | 基线窗随变体窗滚动重算，消除边缘漂移源头 | 1d（搭重启窗口） | unmatched→0，DM 追上最新数据（消除 2 周滞后）；卫生改进 | **单独 C 无效**——90 行零不匹配照样落 descriptive（admissible 检查在先）；必须与 A 或 B 组合 |
| D. 维持现状 + 下游降级 | 接受确认轨道休眠；dead families 改独立口径（如 descriptive ∧ gate_pass=False 持续 N 轮）；预注册两族提前 underpowered 止损 | 0.5-1d | 零 gate 语义变更 | 确认机制名存实亡，违背 v4 核心设计意图 |
| E. 双轨制 | 探索层用 B（宽松，供 dead families/学习），确认层用 A（严格，供预注册/晋升） | A+B 之和 | 两层各服务各的目的 | 两套口径的维护与沟通成本；同样触发指纹评估 |

**组合倾向（供参考，非决策）**：B（或 A）解锁生产 + C 作为卫生改进；但任何 dm_status 语义变更必须走 v5 协议指纹评估流程——与 M5 的指纹纪律同源。

## 7. 开放问题

1. **§7.8 裁定本身**（选项 A 前置）：分桶用什么？独立性检验方法与阈值？最小桶样本？注册时冻结机制？
2. **确认轨道派发活性**：10-03 预注册后 4 天仅 4 行 no_data 存根——真实确认评估何时触发？（confirm_from_ts=2026-10-03 后每日 tick 应产生确认行；需查 supervisor 确认派发逻辑）建议并入批次 2 或单独立项小调研
3. **10 月 no_common_cutoff×9** 成因（零共同 cutoff）
4. **指纹流程确认**：若走选项 B，dm_status 枚举语义变化是否必须 bump 协议指纹 v5？（本报告倾向：是——verdict 语义字段）
5. **边缘漂移与 DM 新鲜度**：共同窗右端停在 09-17（案例），DM 落后最新数据约 2 周；若近期表现对策略重要，选项 C 可消除

## 8. Q1 附带结论：n_eff 溯源（M5 结案）

- **生产路径**（唯一）：scripts/monthly_backtest.py:660 `n_eff = fallback_n_eff(n, HORIZON, STEP)`（HORIZON=24、STEP=2 出自 config/backtest_config，即 h=12；fallback_n_eff 文档串与注册表数学恒等双重印证）
- **公式**：factor = 1 + 2·Σ_{j=1}^{h-1}(1−j/h)² = 8.028（h=12）；n_eff = ⌊n/8.028⌋
- **恒 73 = 设计使然**：n=588 → 73.24 → 73（335 行，全部 n=588，逐行数学恒等验证）
- 71×9 行 = 2026-09-14 旧公式时代（effective_sample_size，ρ=0.9 → 71.39 → 71），此后切换为 fallback 公式——两个时代都是解析式修正
- 0/1×52 行 = no_data 存根（26）+ 极小 n 行（26）
- **measured_n_eff（真实测量估计量，cascade/evaluation_metrics.py:510）全仓零调用方（含 scripts/）= 死代码**；effective_sample_size（evaluator.py:757）在 slow loop 仅存死导入（:16 导入后零调用）
- **结论 (a)：设计使然，非 bug，M5 关闭，零改动**（按 Q1 裁定：不进入修复流程、不动指纹）
- 副产品：三个 ESS 实现并存（1 生产 + 2 死）→ 登记为 D 类清理候选（随批次 4，不新增条目）
- tier 注意：n_eff 恒定意味着 tier_breakdown 的 neff_score 不随变体分化（分化来自其他分量）——符合设计意图，无需行动

## 9. 证据与复现

关键代码位置：

- cascade/statistical_tests.py:322-396（判据梯 + admissible 分支）
- task_FM/evaluations/fm_eval/evaluator.py:479-496（build_summary 不传参）
- scripts/praxist_supervisor.py:22-31（_PERSISTABLE_DM / fdr_pass_persistable）、:1714（_CONFIRMATORY_DM）
- scripts/preregistry.py:453-475（_test_invalid / _passes_confirmation）
- pevs worktree scripts/aligned_slow_loop.py:263-285（P2.6 硬编码 False）
- scripts/monthly_backtest.py:50,659-660（n_eff 生产路径）
- docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md:459,461,682,1471（spec 依据）
- docs/superpowers/reports/2026-09-29-spec-implementation-audit.md:72（未裁定挂账）

复现要点（live 只读）：

- 全量分布：读 aligned_verdicts.jsonl 按 dm_status / run_mode / protocol_fingerprint / decided_at 计数（本文所有表）
- 边缘漂移：取任一 descriptive 行 → checkpoint_path 读变体 cutoff 集 → 对 baseline_points_{symbol}_nocov.jsonl 做集合差 → only_* 落点集中在首尾
- 结构不可达：grep missingness_admissible 全仓 → 只有读取方与恒 False 默认，无 True 写入方

---

**交付边界**: 本报告只列选项不决策（计划 §6.3 约定）。修复方案讨论 → 宿主裁定 → 届时回写计划或另立实施计划。
