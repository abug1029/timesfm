# dm_status 生产活性根因调研报告（Q6 子项目）

> **日期**: 2026-10-07
> **性质**: 只读调研（零代码改动）；宿主裁定记录见 plans/2026-10-07-tech-debt-closure-plan.md §8 Q6
> **裁定状态（2026-10-07）**: **已裁定——批准 B+C 为主菜，采集包同步落地，不 bump 全局协议指纹，第 1 步等待，A 缓发**。全文见附录 A；质询补证（195/195 逐行边缘连续审计 + 21 行基线覆写留痕）见附录 B/C；开放问题 #1/#4 已关闭、#2/#3 升格为通电前置检查（§7）。
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

**裁定（2026-10-07，宿主，全文见附录 A）**：**B 批准**（边缘连续块 + k_max=30 双条件豁免，窗内缺失仍 False，只翻转 missingness_admissible、不动数值）；**C 批准**（基线快照版本化为前置，confirm_from_ts 守卫断言，unmatched 预期 ≈ 拉取滞后 1-3 点、B 不因 C 省略）；**A 缓发**（待真实窗内状态相关缺失案例带实测数据再裁）；**D、E 不采用**；**不 bump 全局协议指纹**（admissibility_rule 按行标记替代，关闭开放问题 #4）；第 1 步（dead families 改口径）等待（观察条件见附录 A 第六节）。

## 7. 开放问题

1. **§7.8 裁定本身** — **已关闭（2026-10-07 裁定）**：B+C 落定（附录 A）；A 的三要素（分桶/独立性检验/注册时冻结）随 A 缓发，待真实窗内状态相关缺失案例出现再裁
2. **确认轨道派发活性** — **升格为通电前置检查**（实施顺序第 5 步）：10-03 预注册后仅 4 行 no_data 存根，需查确认派发何时触发；B+C 让 dm_status 可确认，但不保证预注册确认能运转
3. **10 月 no_common_cutoff×9** — **升格为通电前置检查**：可能是另一类漂移，不在 B 的"边缘连续块"覆盖范围内，B 不对其豁免
4. **指纹流程确认** — **已关闭（有意决定）**：**不 bump**。理由（附录 A 第七节）：① 指纹 11 分量决定数值可比性，B 只改 dm_status 的解释资格（可确认性而非可比性变化）；② bump 会使 182 行 v4 活跃裁决失效并触发 9/9 基线重生；③ admissibility_rule 按行标记能精确保证新旧口径不混算。**限定**：本裁定只改 missingness_admissible 判定规则；将来若 d_t / DM 估计量 / 带宽 / 配对集合的计算本身变化则必须 bump；A 落地时重新评估；**实施前断言：B 上线前后同一行 protocol_fingerprint 不变**——若发现某分量实际哈希了 dm 层内容，本条作废，回到 bump 评估
5. **边缘漂移与 DM 新鲜度** — 保留：共同窗右端滞后（案例 ~2 周）；C 落地后预期收敛到拉取滞后 1-3 点，验收以实测为准

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

**交付边界**: 本报告只列选项不决策（计划 §6.3 约定）。修复方案讨论 → 宿主裁定 → 届时回写计划或另立实施计划。**（2026-10-07 已裁定，见附录 A；裁定回写见计划 §6.4。）**

---

## 附录 A：宿主裁定要旨（2026-10-07，事项一）

> 整理说明：本附录为裁定要旨整理，保留全部裁定条件、数字与限定，据 2026-10-07 会话记录整理（非逐字照录；如需原文宿主可补录替换）。裁定性质 = **证据标准设计裁定，非缺陷修复**。附录证据读数：2026-10-07 15:09（live master@ca4a3b9，registry 404 行）。

| 节 | 裁定内容 |
|---|---|
| A.1 对象与性质 | 本报告 §6 修复选项 A-E 的定夺；证据标准设计裁定 |
| A.2 各选项 | **B 批准**：边缘连续块豁免——「变体侧最新连续块 / 基线侧最旧连续块」+ 有界性双条件，任一不满足落回 descriptive；窗内缺失仍 False；只翻转 missingness_admissible，不改 dir_acc/d_t/DM 统计量/p 值。**C 批准**：基线快照版本化为前置；守卫断言 = 重锚不得删除 ≥ confirm_from_ts 的基线 cutoff（保 v9 修订②）；unmatched 预期 ≈ 拉取滞后 1-3 点（非零），**B 不因 C 省略**。**A 缓发**：待真实窗内状态相关缺失案例带实测数据再裁。**D、E 不采用**。**第 1 步等待**（见 A.4）。**pevs P2.7 可恢复**：只决定何时通电、不决定线路怎么接；消费端接线待 B+C 合入 master |
| A.3 采集包与 admissibility_rule | 采集包随 B+C 同步落地（不随 A）：① 基线版本化；② 行级 unmatched 位置（**每侧 ≤30 日期**）与连续性判定；③ 拉取日志保留；④ 21 行覆写留痕入报告（附录 C）。`admissibility_rule` 为行级可选字段，**唯一写入路径 = 裁决行产出**；5 个读取点（fdr_pass_persistable、_test_invalid、_passes_confirmation、classify_confirmation、_family_confirmatory_counts）只计匹配预注册钉定规则的行；旧行缺字段不计入、不回溯解释（今日零回归：0 行 ok/set_mismatch_ok，4 行 no_data 存根在更早检查处已失败） |
| A.4 第 1 步等待 | 两次口径变更成本 > 收益（10-03 已裁非目标，避免回退）；gate_pass 是质量筛选器，未验证真死族不判死；**观察条件** = B+C 上线满一个完整慢环周期、可确认行仍为零 → 带实测数据重开第 1 步裁定；期间 min_ok=4 与 gate_pass 不改 |
| A.5 不 bump 指纹 | 理由：① 指纹 11 分量决定数值可比性，B 只改 dm_status 的解释资格（可确认性而非可比性）；② bump 将废 182 行 v4 活跃裁决并触发 9/9 基线重生；③ 按行 admissibility_rule 精确隔离新旧口径。**限定**：本裁定只改 missingness_admissible 判定规则；将来 d_t/DM 估计量、带宽、配对集合计算本身变化必须 bump；A 落地时重评；**实施前断言：同一行 protocol_fingerprint 上线前后不变**——若任一分量实际哈希 dm 层内容则本条作废、回 bump 评估。开放问题 #4 由此关闭（有意决定） |
| A.6 补盖预注册 | 现存 2 条预注册（jd daily_slope+vor、sr daily_slope+vwap_deviation）由本裁定显式补盖 admissibility_rule；标记文本：「admissibility_rule 系 2026-10-07 裁定补设，confirm_from_ts 与 n_confirm_required 不变」；**补盖前必须重核验各自可确认行数 = 0 并留痕（命令/时间/结果）**，非零则暂停另行裁定 |
| A.7 通电前置检查 | 开放问题 #2（派发活性——仅 4 条 no_data 存根）与 #3（十月 no_common_cutoff×9，可能是 B 未覆盖的另一漂移类型，B 不对其豁免）升格为通电前置检查（落地顺序第 5 步） |
| A.8 落地顺序（五步） | ① 基线快照版本化（锚定日入文件名或重生即归档；**前置：批次 0 数据备份先行**）→ ② C（拉取日重锚 + 守卫断言）→ ③ B + 采集包（admissibility_rule + 五读取点过滤）→ ④ 补盖两条预注册（先重核验为零）→ ⑤ 通电前置核查（#2/#3）确认通电 |
| A.9 证据局限（宿主明示） | 105/105 逐行审计与指纹 11 分量清单系单方转述（未独立复核）——由补盖前重核验 + 实施前指纹断言两项覆盖 |

---

## 附录 B：逐行位置审计（非零 unmatched 行边缘连续性）

> 质询 Q1 补证：原报告 §4.2 为机制推理 + 单案例（jd_ccl），本附录把证据升级为**逐行全量**。审计脚本全文内嵌（B.4/C.4），复现零依赖。

### B.1 方法

对每条 dm_unmatched 非零的 descriptive 行：读其 checkpoint 文件的 cutoff 集（变体侧），与「最大交集」基线文件（`task_FM/config/baseline_points_{symbol}*.jsonl` 中与该变体 cutoff 交集最大者——自动避开非本变体配对目标的 cov 版基线）的 cutoff 集做集合差；判定 **only_variant 是否恰为变体侧最新连续块（尾部）** 且 **only_baseline 是否恰为基线侧最旧连续块（头部）**——即 B 选项豁免的判定形态，**零内部散点**才算通过。同时比对当前重建值与行上记录值之差（delta）与 checkpoint 增量，验证重建有效性。

### B.2 结果（两次读数）

| 读数 | descriptive 总数 | 零不匹配行 | 非零受审行 | 边缘连续通过 | 未通过 |
|---|---|---|---|---|---|
| 2026-10-07 上午（质询答辩时） | 195 | 90 | 105 | **105（100%）** | 0 |
| 2026-10-07 15:09（复跑确认） | 196 | 90 | 106 | **106（100%）** | 0 |

- (kv, kb) 分布（复跑）：(14,13)×57、(11,10)×35、(17,16)×14——**每侧实测最大 17**（裁定采集包口径「每侧 ≤30 日期」内，余量 13）
- 决定日期分布（复跑）：10-06×38、10-05×34、10-07×22、10-04×12
- delta（当前重建 − 行上记录）106/106 恒 (+1, 0)；checkpoint 增量（当前容量 − 记录 n_avail_variant）106/106 恒 +1——评估后 checkpoint 追加 1 根 bar；**当前连续块扣除极尾 1 点 = 评估时点连续块**，重建成立
- dm_common_count 分布（上午读数）：572×14、575×56、578×35、588×90——最小 572 对门槛 dm_min_common=50 / effective_min_n=50 余量 ≥11 倍（质询 Q2 的构造性保证：门槛检查先于 admissible 分支，statistical_tests.py :380/:387/:389）

### B.3 判读

- **105/105 → 106/106 全过、零内部散点、零异常行**：生产全部非零 mismatch 都是「变体侧尾部新数据 + 基线侧头部老化」的确定性边缘漂移，无一处状态相关缺失形态。B 的双条件豁免对现存数据 **100% 可判定**——质询 Q1 所问「边缘漂移 100% 可判定从何而来」由此从三层推理升级为逐行实证。
- 复跑与上午读数仅差 live 追加的 1 行（同样通过）——审计结论对 registry 增长稳定。

### B.4 审计脚本（内嵌全文）

```python
# item1_audit2.py — 2026-10-07；live 只读；python3 直跑
import json, glob, collections, os, datetime

os.chdir('/home/abug/timesfm')
rows = [json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl') if l.strip()]
desc = [r for r in rows if r.get('dm_status') == 'set_mismatch_descriptive']

def cutoffs_of(objs, mode='full'):
    s = set()
    for p in objs:
        if isinstance(p, dict):
            c = p.get('cutoff') or p.get('ts') or p.get('cutoff_ts')
            if c is not None:
                s.add(str(c) if mode == 'full' else str(c)[:10])
    return s

zero = [r for r in desc if not (r.get('dm_unmatched_variant') or 0) and not (r.get('dm_unmatched_baseline') or 0)]
nz = [r for r in desc if (r.get('dm_unmatched_variant') or 0) > 0 or (r.get('dm_unmatched_baseline') or 0) > 0]
print('descriptive:', len(desc), 'zero-unmatched:', len(zero), 'to audit:', len(nz))
print('=== decided_at of non-zero rows ===')
print(collections.Counter(str(r.get('decided_at'))[:10] for r in nz))

def best_baseline(sym, vc):
    best = None
    best_inter = 0
    for b in glob.glob('task_FM/config/baseline_points_%s*.jsonl' % sym):
        try:
            bp = [json.loads(l) for l in open(b) if l.strip()]
        except Exception:
            continue
        bc = cutoffs_of(bp)
        inter = len(vc & bc)
        if inter > best_inter:
            best_inter = inter
            best = (b, bc)
    return best

res = collections.Counter()
kv_pass = collections.Counter()
delta_counter = collections.Counter()
anomalies = []
ck_delta = collections.Counter()

for r in nz:
    vid = r.get('variant_id')
    sym = r.get('symbol')
    ruv = r.get('dm_unmatched_variant') or 0
    rub = r.get('dm_unmatched_baseline') or 0
    cp = r.get('checkpoint_path')
    if not cp:
        res['no_checkpoint_path'] += 1
        continue
    try:
        ckpt = [json.loads(l) for l in open(cp) if l.strip()]
    except Exception:
        res['checkpoint_unreadable'] += 1
        continue
    vc = cutoffs_of(ckpt)
    if not vc:
        res['checkpoint_no_cutoffs'] += 1
        continue
    bb = best_baseline(sym, vc)
    if bb is None:
        res['no_baseline_match'] += 1
        continue
    b, bc = bb
    only_v = vc - bc
    only_b = bc - vc
    vsort = sorted(vc)
    bsort = sorted(bc)
    tail_ok = (only_v == set(vsort[len(vsort) - len(only_v):])) if only_v else True
    head_ok = (only_b == set(bsort[:len(only_b)])) if only_b else True
    contiguous = tail_ok and head_ok
    dv = len(only_v) - ruv
    db = len(only_b) - rub
    delta_counter[(dv, db)] += 1
    nav = r.get('n_avail_variant')
    if nav is not None:
        ck_delta[len(vc) - nav] += 1
    if contiguous:
        res['edge_contiguous_pass'] += 1
        kv_pass[(len(only_v), len(only_b))] += 1
    else:
        res['NOT_contiguous'] += 1
        if len(anomalies) < 8:
            anomalies.append((vid, ruv, rub, len(only_v), len(only_b), tail_ok, head_ok,
                              sorted(only_v)[:2], sorted(only_v)[-2:]))

print('=== contiguity audit (current state, all non-zero rows) ===')
for k in sorted(res):
    print(' ', k, res[k])
print('=== (kv, kb) among contiguous ===')
for k in kv_pass.most_common(20):
    print(' ', k, kv_pass[k])
print('=== delta (current - recorded) ===')
for k in delta_counter.most_common(10):
    print(' ', k, delta_counter[k])
print('=== checkpoint delta (current size - recorded n_avail_variant) ===')
for k in ck_delta.most_common(10):
    print(' ', k, ck_delta[k])
print('anomalies:', anomalies)

loss = collections.Counter()
for r in desc:
    sym = r.get('symbol')
    da = str(r.get('decided_at') or '').replace('T', ' ')
    cp = r.get('checkpoint_path')
    if not cp or not da:
        loss['no_ckpt_or_date'] += 1
        continue
    try:
        ckpt = [json.loads(l) for l in open(cp) if l.strip()]
    except Exception:
        loss['ckpt_unreadable'] += 1
        continue
    vc = cutoffs_of(ckpt)
    if not vc:
        loss['ckpt_no_cutoffs'] += 1
        continue
    bb = best_baseline(sym, vc)
    if bb is None:
        loss['no_baseline'] += 1
        continue
    mt_s = datetime.datetime.fromtimestamp(os.path.getmtime(bb[0])).strftime('%Y-%m-%d %H:%M:%S')
    if mt_s > da:
        loss['baseline_modified_after_eval'] += 1
    else:
        loss['baseline_older_than_eval'] += 1
print('=== baseline snapshot freshness vs decided_at (all descriptive) ===')
for k in sorted(loss):
    print(' ', k, loss[k])
```

---

## 附录 C：21 行基线覆写留痕与勘误

### C.1 勘误（必须留痕）

本报告质询答辩阶段（2026-10-07 上午，口头推演未入正文）曾把「21 行 baseline_mtime > decided_at」**错误推断**为「今日行、今晨拉取所致」——**该推断被逐行核实证伪，纯属数字巧合**（当日行恰为 21 条）。实际：21 行全部是更早日期的决定行，其基线文件在**评估之后**被两个已知再生波覆写（10-01 v4 ensure_baselines 再生波、10-03 baseline_points_ma_nocov 再生）。此为「证据未齐即下全称结论」的同型错误（本会话第四次），记录以自警。

### C.2 事实

- 21 行 recorded_unmatched **全部 (0,0)**：评估时点零漂移，覆写发生在评估之后——**不推翻附录 B 审计结论**（B 审计的 106 非零行基线完好，mtime < decided_at）。
- 全景（15:09 复跑）：descriptive 196 行中 baseline_modified_after_eval=21、baseline_older_than_eval=175；基线文件共 32 个、7 日内被修改 24 个。
- 这 21 行正是裁定采集包「基线快照版本化」要消灭的对象：版本化落地后重生波归档旧版而非覆写，此类「事后无法精确重放评估时点配对」的留痕缺口不再产生。

### C.3 逐行明细（21 行全量，按 decided_at 排序）

| # | variant_id | symbol | decided_at | 基线文件 | 基线 mtime（覆写波） |
|---|---|---|---|---|---|
| 1 | rb_crack_spread_level_aligned_p6 | rb | 09-29 21:56:24 | rb_nocov | 10-01 12:43:57（波一） |
| 2 | ss_vor_aligned_p6 | ss | 09-29 22:37:49 | ss_nocov | 10-01 13:17:32（波一） |
| 3 | sr_vwap_deviation_aligned_p6 | sr | 09-29 22:57:45 | sr_nocov | 10-01 13:00:43（波一） |
| 4 | ss_oi_aligned_p6 | ss | 09-29 23:11:59 | ss_nocov | 10-01 13:17:32（波一） |
| 5 | rb_ccl_content_aligned_p6 | rb | 09-29 23:23:22 | rb_nocov | 10-01 12:43:57（波一） |
| 6 | jd_calendar_cyclical_content_aligned_p6 | jd | 09-29 23:38:17 | jd_nocov | 10-01 11:55:52（波一） |
| 7 | jd_calendar_cyclical_structural_aligned_p6 | jd | 09-29 23:49:54 | jd_nocov | 10-01 11:55:52（波一） |
| 8 | jd_calendar_cyclical_baseline_aligned_p6 | jd | 09-30 00:01:27 | jd_nocov | 10-01 11:55:52（波一） |
| 9 | jd_ccl_content_aligned_p6 | jd | 09-30 00:09:31 | jd_nocov | 10-01 11:55:52（波一） |
| 10 | jd_ccl_structural_aligned_p6 | jd | 09-30 00:17:29 | jd_nocov | 10-01 11:55:52（波一） |
| 11 | jd_ccl_baseline_aligned_p6 | jd | 09-30 00:25:34 | jd_nocov | 10-01 11:55:52（波一） |
| 12 | jd_vwap_deviation | jd | 09-30 02:05:16 | jd_nocov | 10-01 11:55:52（波一） |
| 13 | jd_crack_spread_level | jd | 09-30 02:13:18 | jd_nocov | 10-01 11:55:52（波一） |
| 14 | m_vwap_deviation | m | 09-30 02:21:23 | ma_nocov | 10-03 19:27:52（波二） |
| 15 | rb_crack_spread_slope | rb | 09-30 04:01:44 | rb_nocov | 10-01 12:43:57（波一） |
| 16 | jd_vor | jd | 09-30 09:15:09 | jd_nocov | 10-01 11:55:52（波一） |
| 17 | m_term_structure_ea1835408223 | m | 10-01 21:41:11 | ma_nocov | 10-03 19:27:52（波二） |
| 18 | m_momentum_f271f3458d87 | m | 10-01 21:49:54 | ma_nocov | 10-03 19:27:52（波二） |
| 19 | m_volatility_f92907d83bda | m | 10-01 21:58:29 | ma_nocov | 10-03 19:27:52（波二） |
| 20 | m_momentum_b06ddbcd88e3 | m | 10-02 20:38:25 | ma_nocov | 10-03 19:27:52（波二） |
| 21 | m_inventory_972440b990f6 | m | 10-03 03:24:54 | ma_nocov | 10-03 19:27:52（波二） |

波一（10-01 v4 再生波）= 15 行（rb×3 / ss×2 / sr×1 / jd×9，决定于 09-29 21:56 ~ 09-30 09:15）；波二（10-03 再生）= 6 行（全 m 品种，决定于 09-30 02:21 ~ 10-03 03:24）。

### C.4 审计脚本（内嵌全文）与复现命令

```python
# item1_overwrite_detail.py — 2026-10-07；live 只读；python3 直跑
import json, glob, os, datetime

os.chdir('/home/abug/timesfm')
rows = [json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl') if l.strip()]
desc = [r for r in rows if r.get('dm_status') == 'set_mismatch_descriptive']

def cutoffs_of(objs):
    s = set()
    for p in objs:
        if isinstance(p, dict):
            c = p.get('cutoff') or p.get('ts') or p.get('cutoff_ts')
            if c is not None:
                s.add(str(c))
    return s

out = []
for r in desc:
    sym = r.get('symbol')
    da = str(r.get('decided_at') or '').replace('T', ' ')
    cp = r.get('checkpoint_path')
    if not cp or not da:
        continue
    try:
        ckpt = [json.loads(l) for l in open(cp) if l.strip()]
    except Exception:
        continue
    vc = cutoffs_of(ckpt)
    if not vc:
        continue
    best = None
    best_inter = 0
    for b in glob.glob('task_FM/config/baseline_points_%s*.jsonl' % sym):
        try:
            bp = [json.loads(l) for l in open(b) if l.strip()]
        except Exception:
            continue
        bc = cutoffs_of(bp)
        inter = len(vc & bc)
        if inter > best_inter:
            best_inter = inter
            best = b
    if best is None:
        continue
    mt_s = datetime.datetime.fromtimestamp(os.path.getmtime(best)).strftime('%Y-%m-%d %H:%M:%S')
    if mt_s > da:
        out.append({
            'variant_id': r.get('variant_id'),
            'symbol': sym,
            'decided_at': da,
            'recorded_unmatched_v_b': [r.get('dm_unmatched_variant'), r.get('dm_unmatched_baseline')],
            'baseline_file': os.path.basename(best),
            'baseline_mtime': mt_s,
        })

print('audit_ts:', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('total_descriptive:', len(desc))
print('baseline_modified_after_eval:', len(out))
for o in out:
    print(json.dumps(o, ensure_ascii=False))
```

复现：`cd /home/abug/timesfm && python3 item1_overwrite_detail.py`（首次留痕 2026-10-07 14:40:28，复跑确认 15:09:44，两次输出恒等 21 行）。
