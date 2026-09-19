# Task 3: superpowers specs / plans 过期与冲突

> 审核日期: 2026-09-11
> 活仓: `/home/abug/timesfm`（`git status`: `master...origin/master`，HEAD `2855ebf`）
> 范围: Task 3 only。只读生产代码；本文件是允许写入的报告。
> 现行合同（本审核强制对照，不可被更早 spec 推翻）:
> peers 只写假设；慢环是唯一验证器；硬门 `n≥350` 且 `ic=2×|dir_acc−0.5|≥0.05` 且扣滑点 EV>0。

## 0. 结论（先给执行者）

**现在还敢当合同的 spec 只有三份半：**

1. `docs/spec_hypothesis_driven_fast_loop_20260908.md` — **现行快环合同**（方案 A，已实施）。
2. `docs/superpowers/specs/2026-09-10-system-hardening-design.md` — **已落地接口合同**（SPEC-004…013 的函数名/不变量仍约束代码）。**启动姿态过期**，禁止再当「待开工计划」执行。
3. `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md` — **已落地效率合同**（`ensure_compiled` 指纹跳过）。状态栏「待审阅」过期。
4. `docs/superpowers/specs/praxist_control_plane.md` — **半份**：mem_guard / 429 / 启停审批仍有运维效力；peer 评估、15GiB 宿主、diagnostic 选人 **已废或与 runbook 冲突**。

`docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` **不能当现行合同**。三环骨架（监督/快/慢、verdict 唯一写者、429 resume 同一 run）仍在代码里，但 peer「diagnostic 筛选 / 诊断幸存者」已被方案 A 废止。更糟的是：`docs/praxist.md` 和 runbook 宣称「冲突时以计划里的 Spec 绑定解释为准」，而那份绑定解释自己还在规定 diagnostic 收割。

其余 2026-07/08 协变量与 Alpha2 spec：历史方案，状态栏未关闭，**不约束当前生产路径**。

---

## 1. 全量 spec 分类表

git 最后提交取 `git log -1 --format=%h %ci`。标签含义：

- **仍约束代码**：执行者改相关子系统时必须遵守
- **已落地/状态过期**：代码已 merge，文档仍写待审/待启动
- **已被取代**：被方案 A / 后文明确覆盖
- **历史方案**：当时的协变量/Alpha2 设计，不是现行三环/硬门合同
- **与 runbook 冲突**：和 `docs/runbook_praxist_three_loop.md` 或方案 A 直接打架

| 文件 | 文档日期 | 状态字段 | git 最后提交 | 是否 merge 到 master | 标签 |
|---|---|---|---|---|---|
| `2026-09-10-system-hardening-design.md` | 2026-09-10 v1.2-final | 终审封版；**依赖 critical-fixes 完成后可启动** | `5925156` 2026-09-11 08:33 | 是（实现 merge `243693d` 2026-09-11 08:31；能力表 `2855ebf`） | **仍约束代码（接口/不变量）**；启动姿态过期 |
| `2026-09-09-compile-skip-phase1-design.md` | 2026-09-09 | **待审阅**；验收框全空 | `c2d2336` 2026-09-09 15:28 | 是（`a8b0b6b`…`b354b5e` 均是 HEAD 祖先） | **已落地/状态过期**；接口解释仍可用 |
| `praxist_control_plane.md` | 2026-09-06，修订到 2026-09-09 | **已批准稳妥启动**（eval 硬顶=1，cohort=2） | `9609d28` 2026-09-09 17:52 | 是 | **半份仍约束**；peer eval / 15GiB **与 runbook 冲突** |
| `2026-09-02-praxist-three-loop-design.md` | 2026-09-02 | **待审阅** | `10dbeb3` 2026-09-03（初始提交，此后未改） | 骨架已落地；peer diagnostic **未再作为合同** | **已被方案 A 取代**；覆盖链有毒（见 C1） |
| `ACCEPT_flock_20260906.md` | 2026-09-06 | 无状态栏；验收记录 | `14131bf` 2026-09-06 | mem_guard 仍在 | 历史验收；规模数字被 runbook 后续改乱，代码仍接近此条 |
| `2026-07-28-covariate-optimization-design.md` | 2026-07-28 | **Approved (Phase 1 in progress)** | `10dbeb3` | 历史 | 历史方案；状态栏未关闭 |
| `2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md` | 2026-07-28 | **Draft (待用户审批)** | `10dbeb3` | 历史 | 历史方案 |
| `2026-07-29-followup-4-directions-optimization-design.md` | 2026-07-29 | 已与用户逐节确认,等待 spec 自审 | `10dbeb3` | 历史（checkpoint JSONL 已是生产形态） | 历史方案；与同名 `.txt` **内容不一致** |
| `2026-07-29-phase4-calendar-cyclical-design.md` | 2026-07-29 | 待用户审核 | `10dbeb3` | 历史 | 历史方案 |
| `2026-07-31-phase8-crack-spread-design.md` | 2026-07-31 | 待用户审核 | `10dbeb3` | 历史 | 历史方案 |
| `2026-08-04-alpha2-phase1-baseline-gate-design.md` | 2026-08-04 | **Draft (待用户 review)** | `10dbeb3` | 历史（LGBM 探针线） | 历史方案 |
| `2026-08-04-phase9-toxic-variety-design.md` | 2026-08-04 | 无状态栏 | `10dbeb3` | 历史 | 历史方案 |
| `2026-08-05-a2-p1-dense-cache-resume-design.md` | 2026-08-05 | 待审核 | `10dbeb3` | 历史 | 历史方案 |
| `2026-08-05-a2-p1-market-vectorize-design.md` | 2026-08-05 | 待审核 | `10dbeb3` | 历史 | 历史方案 |
| `2026-08-05-a2-p1-runtime-redesign.md` | 2026-08-05 | 待审核 | `10dbeb3` | 历史 | 历史方案 |
| `2026-08-22-phase15-new-covariates-design.md` | 2026-08-22 | 待审核 (v2) | `10dbeb3` | 历史 | 历史方案 |

仓外但本任务必读、应算现行合同的文档：

| 文件 | 地位 |
|---|---|
| `docs/spec_hypothesis_driven_fast_loop_20260908.md` | **现行快环合同**（状态：已实施；git `3374dd6` 2026-09-09） |
| `loop-constraints.md` §预注册评估契约 | **最高优先级硬门+方案 A**（git `3374dd6`） |
| `docs/praxist.md` | 现行架构概览；§6 把 09-02 spec 降为历史 |
| `docs/runbook_praxist_three_loop.md` | 现行运维；Harvest 节是方案 A；「Spec 绑定解释」指针有毒 |
| `docs/superpowers/plans/2026-09-02-praxist-three-loop.md` | 实施计划；**Spec 绑定解释仍写 diagnostic 收割** |
| `docs/superpowers/plans/2026-09-10-system-hardening.md` | 实现计划；**71 个 `- [ ]`，0 个 `- [x]`**，与 `243693d` 已 merge 矛盾 |
| `docs/superpowers/plans/2026-09-09-compile-skip-phase1.md` | 实现计划；**35 个 `- [ ]`，0 个 `- [x]`**，与 `a8b0b6b` 等已在 master 矛盾 |
| `CLAUDE.md` L257–274 | hardening 已合并能力表；比 spec 头部更新 |

### md/txt 双份（按计划只记一笔）

`docs/superpowers/specs/`：16 个 `.md`，9 个 `.txt`。

- 字节级相同：07-28 covariate、07-28 phase5-6、07-29 phase4、08-04 phase9、08-05 market-vectorize、08-05 runtime。
- **内容漂移（执行者若读 txt 会拿到旧设计）**：
  - `2026-07-29-followup-4-directions-optimization-design.txt`（10899）vs `.md`（11662）：txt 仍写整文件 JSON checkpoint；md 已改 JSONL 逐点追加。
  - `2026-08-04-alpha2-phase1-baseline-gate-design.txt`（14755）vs `.md`（18183）：txt 目标是价格点位移；md 已改百分比收益率 + dense training。
- **截断文件名**：`2026-08-04-alpha2-phase1-baseline-gate-desig.txt`（缺 n，17732 字节，与 md 也不相等）——三份 alpha2 设计并存。
- 无 txt 副本：phase8、a2-p1-dense-cache、phase15、三环、compile-skip、hardening、control_plane、ACCEPT_flock。

忽略 `.txt` 当合同。不要用它们「补」md。

---

## 2. 三环 spec vs 方案 A

### 2.1 现行合同原文

`loop-constraints.md` L47–49：

> **最终裁决口径不变**：全量 walk-forward（n≥350）、IC≥0.05（ic=2×|dir_acc−0.5|）、扣滑点 EV>0、PF/incumbent>1.05
> **方案 A（2026-09-08 起）：peers 不再跑任何评估/加载 TimesFM**，只写机制化提案 `results/**/proposals/*.json`（schema `fm.hypothesis_proposal.v1`，mechanism ≥40 字）；慢环 `aligned_slow_loop.py` 是唯一验证器，诊断小样本 PF 不作数

`docs/praxist.md` L65–67：

> Peer **是假设作者，不是评估器**。禁止跑 `evaluations/fm_eval/run.py`，禁止加载 TimesFM。

`docs/spec_hypothesis_driven_fast_loop_20260908.md` L4、L37：

> 状态: **已实施（2026-09-08 上线，当日首个过门策略 ss_vor 即出自本方案）**
> Peer **不再跑评估**，转为产出机制优先的结构化假设；慢环成为唯一验证器。

代码抽查：`scripts/praxist_supervisor.py:1289` `_harvest_rows` 调 `harvest_proposals`；`harvest_survivors`（L419）仅留函数体，与方案 A spec §8 回滚设计一致。

### 2.2 09-02 spec 里仍会被当成现行合同的句子

文件：`docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md`，状态栏 L3–4「日期: 2026-09-02 / 状态: 待审阅」，**没有「已被方案 A 取代」横幅**。

| 行 | 原文 | 与现行合同 |
|---|---|---|
| L38 | `PI 面板 + 4 角色 peers + diagnostic 筛选` | 冲突。方案 A：peer 零次模型加载，不筛选 |
| L39 | `产出: 诊断幸存者 -> pending 队列` | 冲突。现行入队源是 `proposals/*.json`，不是诊断幸存者 |
| L51 | `run_summary + frontier 幸存者` | 冲突。收割读 hypothesis 文件 |
| L23 | `硬门口径 \| 维持 n>=350 (与 G005-E 可比)` | **残缺**。现行硬门还有 IC≥0.05 与扣滑点 EV>0 |
| L110–111 | `指示 peers 开工前读注册表; gate_pass=true 不再重试, false 即死亡` | 部分仍有效（known_verdicts）；但未区分「过 n+ic 硬门但 EV<0」的 `i_oi` 瑕疵 |
| L125 | `run 结束且非 429 pause -> 收割幸存者入队` | 半过期：429 期间代码**仍然 harvest**（见 I4）；「幸存者」语义已废 |
| L213 | `不修改 cascade/ (禁改红线)` | 历史非目标。compile-skip 与 hardening 已改 `cascade/`（经批准豁免） |
| L11–15 | 评估点 ~60s、2 核 CPU、n≥350 需 6–8h | 动机仍成立；宿主已不是 2 核/旧盒 |

骨架仍对、不应连坐废除的句子：慢环唯一写 `aligned_verdicts.jsonl`（L109–110）、监督环 0 token、429 后 resume 同一 run（L147）、goal.yaml DSL、daily 缓存键含模型指纹。这些已被 runbook / praxist.md 吸收。

### 2.3 覆盖链把执行者送回 diagnostic（本任务最严重问题）

`docs/praxist.md` L154：

> `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | 三环原始 spec；与现行冲突时以 runbook「Spec 绑定解释」为准

`docs/runbook_praxist_three_loop.md` L192：

> `docs/superpowers/plans/2026-09-02-praxist-three-loop.md` — 实施计划（Spec 绑定解释优先于过时 spec 句）

runbook **自己没有**写绑定解释正文，只指到计划。计划 L30–37：

> ## Spec 绑定解释 (与 spec 原文冲突时以本箱为准)
> 4. harvest: 身份 (symbol, cov_override); max_points 来自 goal.cadence.aligned_max_points 默认 400, 不用诊断 n; **幸存者 = diagnostic + status=ok + ev>0**。源仍是 canonical `results/**/evaluation_summary.json`

计划 L7 架构句同样未改：

> 快环 (praxist run, LLM 探索+诊断筛选) 产幸存者

**判定：** 文档自称的「覆盖过时 spec 的权威解释」仍在命令执行者按 diagnostic 收割。这与方案 A、`harvest_proposals`、runbook L121–123 直接矛盾。默认 400 也与现行 `aligned_max_points=600` 不符。

runbook L121–123 自己已经是方案 A（`harvest_proposals`，旧 `harvest_survivors` 仅回滚）。所以 runbook **正文**对、**指针**错。

---

## 3. Hardening spec vs 已落地

### 3.1 git / CLAUDE.md

```
243693d 2026-09-11 08:31:24 +0800
  Merge branch feat/system-hardening-v1.2 — System Hardening v1.2 (10 SPECs, 14 commits)
cd29bb6 Merge branch feat/critical-fixes-v1.4
2855ebf docs(CLAUDE.md): add System Hardening v1.2 capability table
5925156 docs: add system-hardening spec v1.2-final + implementation plan
```

`CLAUDE.md` L257–259：

> ## System Hardening v1.2 (2026-09-11)
> 10 项统计严谨性与工程质量提升，**已合并至 master**。Spec: `docs/superpowers/specs/2026-09-10-system-hardening-design.md`。

spec 头部 L6–7 仍写：

> **预计工期**: 7 天（3 Phase）
> **依赖**: critical-fixes spec (SPEC-001~003) **完成后可启动**

计划 `docs/superpowers/plans/2026-09-10-system-hardening.md`：71 个未勾选步骤，0 个已勾选；无「已完成」横幅。Task 3 要求的「对照 CLAUDE.md / git：SPEC-004…013 哪些已在 master」——**全部 10 项已在 master**。文档若仍当「待启动」执行 = 重复施工。

### 3.2 抽 2 个 SPEC 点名到代码（其余留给 Task 6/7）

| SPEC | spec 接口 | 代码事实 |
|---|---|---|
| SPEC-004 | `effective_sample_size(...)` → n_eff=71（H=24,S=2,rho=0.9）；不改硬门 | `task_FM/evaluations/fm_eval/evaluator.py:206` 定义；`scripts/aligned_slow_loop.py:12,105` `v["n_eff"] = effective_sample_size(...)`；`tests/test_system_hardening.py:15` `assert effective_sample_size(589, 24, 2) == 71` |
| SPEC-012 | `_compute_direction_v2(daily_result, scheme)` R² 决策闭环 | `cascade/daily_model.py:189` 定义，L180 报告路径调用；`scripts/copilot.py:384,434` 盘中路径调用；`tests/test_system_hardening.py:171+` 覆盖 R²<0.35→中性 |

顺手可见（不当本任务深审）：`calc_margin_maxdd_robust` 在 `cascade/evaluation_metrics.py:314`；`apply_backward_adjustment_robust` 在 `data/data_store.py:113,421`；`detect_trading_hours` 在 `cascade/data_validator.py:562`；`_clip_prediction_drift` 在 `cascade/features.py:22`；`craft_advisory_v2` 在 `scripts/copilot.py:322`；`signal_weight` 在 `config/prediction_scheme.py:524`。与 CLAUDE.md 能力表一致。

### 3.3 与现行硬门

hardening spec Non-Goals L40：`不改变硬门阈值 — n≥350 / IC≥0.05 / EV>0 保持不变`。与现行合同一致。SPEC-004 不变量 L760：`n_eff 只用于报告，不改 gate_pass`。这是 **仍约束代码** 的部分，不要因为「待启动」过期就整份作废。

---

## 4. compile-skip spec vs 已落地

spec L3–4：`日期: 2026-09-09` / `状态: 待审阅`。L190–199 验收框全部 `- [ ]`。

计划 35 个 `- [ ]`，0 个 `- [x]`。

git（均为 `HEAD` 祖先）：

```
c2d2336 2026-09-09 15:28  docs: TimesFM compile 跳过与效率审计第一批 spec
696f458 2026-09-09 15:38  docs: compile 跳过与效率审计第一批实施计划
a8b0b6b 2026-09-09 15:50  feat(cascade): add ensure_compiled skip-if-same-config helper
b32ec93 2026-09-09 16:07  feat(cascade): skip TimesFM compile when ForecastConfig fingerprint matches
b354b5e 2026-09-09 17:04  test: warmup predict so skip path is same-config, not recompile
```

代码：`cascade/daily_model.py:53 def ensure_compiled`；`hourly_model.py:17,82,87,118` 调用；`tests/test_compile_skip.py` 存在。

命名漂移：spec L56 架构图写 `_ensure_compiled`，计划 L7/代码是 `ensure_compiled`（无下划线）。再实现会找错符号。

spec 前序 L8 正确引用「慢环是唯一验证器」——与方案 A 不冲突。本 spec 是预测链效率，不是 peer 评估合同。

---

## 5. praxist_control_plane.md

状态 L3–5：宿主 **8×CPU / 15GiB**；2026-09-06 **已批准稳妥启动**（eval 硬顶=1，cohort=2）；未获批准禁止 `praxist start`。

### 5.1 与方案 A / 现行宿主冲突

| 行 | 原文 | 事实 |
|---|---|---|
| L3 | 宿主 15GiB | `docs/host_environment_assessment.md` L3–10 横幅：当前 WSL **7.7 GiB / 无 swap**。控制面未改宿主行 |
| L19–27 | 「内存红线（TimesFM **eval**）」「强制真实 `fm_eval`」「主动停 **peer eval**」 | 方案 A 后 peer 禁止加载 TimesFM；TimesFM 只在慢环。控制面仍按「peer 跑 fm_eval」作战 |
| L33 | 禁止 peer 自写 `/tmp` 评测脚本 | 作为防御仍合理（防回归），但口吻假定 peer 仍会评测 |
| L63 | 缺 canonical peer 时可从磁盘 `evaluation_summary` 回填 | 方案 A 后 peer 不应再产 diagnostic `evaluation_summary` 当证据 |
| L190 | harvest 选人「先占不同品种，**再按 EV 补齐**」 | 方案 A 选座：tier（1 星 n≥350 → 欠样本 → 其余）+ 族正交 + 机制完备度，**不是诊断 EV** |
| L196 | 归档到 `/workspace/shared/praxist_assets/` | 旧盒路径；runbook L177 已记 Permission denied |

### 5.2 仍可能有效的部分

- eval flock 硬顶=1、MemAvailable 2.5GiB 拒启：与 `scripts/mem_guard.py:43–44` `DEFAULT_MAX_SLOTS = 1` / `MIN_AVAIL_BYTES = 2.5GiB` **一致**（比 runbook「flock≤2 / <2GiB」更接近代码）。
- 429 → failover resume 同一 run、cohort_size=2、survivors=3 / aligned_max_points=600、goal 20 cycles / deadline 2026-09-20：与 praxist.md / runbook 扩目标快照大体一致。
- L191「wait_quota / paused_429 / failover **不阻塞** 已入队 aligned」：与代码 `praxist_supervisor.py:1299–1300` 一致。

控制面不能整份丢弃，也不能整份当现行 peer 合同。

---

## 6. 方案 A spec 本身

`docs/spec_hypothesis_driven_fast_loop_20260908.md` 是本任务里**唯一状态写成已实施、且与代码收割路径一致**的设计规格。

仍有文档债（不改变「它是现行合同」的判定）：

| 行 | 问题 | 严重度 |
|---|---|---|
| L20–30 | §1.1 用现在时写「快环 peer **当前**用 n=3~6 的诊断评估」 | Minor：这是改造前动机；头部 L4 已说已实施。执行者若从 §1 读起可能以为 diagnostic 仍在 |
| L32–34 | 「当前 11 个 aligned 裁决全部 gate=False」 | Minor：头部与 praxist.md 已记录 `ss_vor` 过门。快照过期 |
| L11 / L147 | 「合格未入队提案结转 pending-proposals 索引」明确未实现 | 已自报偏差，可接受 |
| L183 | 「宿主用 run.py diagnostic 档冒烟」 | 这是**宿主**给新协变量冒烟，不是 peer 评估；与方案 A 不冲突，但「diagnostic」一词易混 |
| L196–199 | 一次性 PID（`kill -TERM 486`） | 历史操作，勿当现行 runbook |

硬门写法 L33：`n≥350 且 ic≥0.05（ic=2×|dir_acc−0.5|）`——**缺 EV>0**。现行合同把 EV 放在最终裁决口径里；praxist.md L91–96 三条件并列；runbook L137 承认代码 `gate_pass` 目前只判 n+ic（`i_oi` 瑕疵）。方案 A spec 对 EV 是否进入 `gate_pass` 布尔值写得不够硬，但没有叫 peer 去评 EV。

---

## 7. runbook Spec 绑定解释

**有指针，没有正文。** 绑定解释在 `docs/superpowers/plans/2026-09-02-praxist-three-loop.md` L30–44，写于方案 A 之前。

runbook 内部自相矛盾：

| 位置 | 说法 |
|---|---|
| L21 | 方案 A，peer 只写机制化提案、零 TimesFM |
| L82 | `paused_429` 期间不 harvest |
| L121–123 | harvest_proposals；旧 harvest_survivors 仅回滚 |
| L154 | 执行期验收对照 spec §11 + 计划「Spec 绑定解释」 |
| L192 | Spec 绑定解释优先于过时 spec 句 |

L82 vs 代码/控制面：`scripts/praxist_supervisor.py:1299` 明文 `paused_429 / wait_quota / failover do NOT block harvest`。runbook L82 **落后于代码**；控制面 L191 与代码一致。

L24 flock≤**2** / MemAvailable < **2GiB** vs `mem_guard.py` 槽=1 / 2.5GiB vs 控制面硬顶=1 / 2.5GiB。runbook 运维数字也不如控制面接近代码。这不是「控制面整份过期」那么简单。

---

## 8. Findings

### Critical（按该文档执行会改错生产合同：peer 评估 / 收割源 / 硬门）

**C1. 自称覆盖 09-02 spec 的「Spec 绑定解释」仍规定 diagnostic 收割，覆盖链把方案 A 绕回去。**

- 证据：`docs/praxist.md:154`「冲突时以 runbook『Spec 绑定解释』为准」；`docs/runbook_praxist_three_loop.md:192`「Spec 绑定解释优先于过时 spec 句」；`docs/superpowers/plans/2026-09-02-praxist-three-loop.md:37`「幸存者 = diagnostic + status=ok + ev>0。源仍是 canonical `results/**/evaluation_summary.json`」；同文件 L7「诊断筛选」。
- 对照现行合同：`loop-constraints.md:49` peers 不再跑任何评估；`docs/praxist.md:65–67` 假设作者；代码 `_harvest_rows` → `harvest_proposals`（`scripts/praxist_supervisor.py:1289`）。
- 为何严重：执行者按文档权威链「修 harvest / 补齐三环」会把 `harvest_survivors` 接回主路径，peer 重新加载 TimesFM，违反方案 A，并在 7.7GiB 宿主上打满内存。
- 建议（不落地）：在 `docs/praxist.md` §6、runbook 相关文件、09-02 计划头部加一句「方案 A 之后 Spec 绑定解释第 4 条作废，收割以 `harvest_proposals` 为准」；09-02 spec 状态改为「部分取代 / peer diagnostic 已废」。不要重写整份 spec。

### Important

**I1. Hardening spec 仍写「critical-fixes 完成后可启动」+ 计划 71 框未勾，但 `243693d` 已把 SPEC-004…013 merge 进 master。**

- 证据：spec L7「依赖: critical-fixes spec (SPEC-001~003) 完成后可启动」；计划 0 个 `[x]` / 71 个 `[ ]`；git `243693d`；`CLAUDE.md:257–259`「已合并至 master」。
- 对照：这不是代码没做，是文档启动姿态撒谎。按 spec 再开 7 天工期会重改已冻结的 `cascade/` / `prediction_scheme.py`。
- 建议：spec 头部改「已落地 master `243693d`（2026-09-11）」；计划顶部加完成态，或标明「历史施工单，勿再执行」。接口合同（n_eff 不进 gate、SCHEMES 不因退役而改）保留。

**I2. compile-skip spec 状态「待审阅」、验收框全空，但 `ensure_compiled` 已在 master。**

- 证据：spec L4「状态: 待审阅」；L190–199 全空框；git `a8b0b6b`…`b354b5e` 是 HEAD 祖先；`cascade/daily_model.py:53`。
- 建议：状态改为「已实施（2026-09-09）」；架构图 `_ensure_compiled` 改成代码里的 `ensure_compiled`。

**I3. 控制面仍按 15GiB + peer `fm_eval` 作战，与方案 A 和当前 7.7GiB WSL 冲突。**

- 证据：控制面 L3「15GiB」；L24–26「强制真实 fm_eval」「主动停 peer eval」；L190「再按 EV 补齐」；宿主评估 L10「7.7 GiB total」。
- 对照：`docs/praxist.md:67` 禁止加载 TimesFM。慢环仍需要 mem_guard，但不能再把硬顶叙事写成「peer eval」。
- 建议：宿主行改为 7.7GiB；「peer eval」改为「任何 TimesFM 进程（现仅慢环）」；harvest 选人指向方案 A tier+QD。

**I4. runbook 写 `paused_429` 期间不 harvest，代码和控制面都说要 harvest。**

- 证据：runbook L82「`paused_429` 期间不 harvest、不 start」；控制面 L191「harvest 不再因 paused_429 跳过」；`scripts/praxist_supervisor.py:1299–1300`「paused_429 / wait_quota / failover do NOT block harvest」。
- 对照：方案 A 下提案是本地文件，harvest 不烧 TimesFM，429 时抽干慢环是正确合同。runbook L82 会让运维在 429 时人为跳过收割。
- 建议：改 runbook L82，与 L121 和代码对齐。

**I5. 09-02 spec 硬门只写 n≥350，缺 IC 公式与 EV；状态仍「待审阅」，无取代横幅。**

- 证据：spec L4「待审阅」；L23 硬门只维持 n≥350。
- 对照：`loop-constraints.md:48` 三条件 + IC 公式。按 09-02 改 `gate_pass` 会丢掉 IC/EV。
- 建议：文件头加「已被 `docs/spec_hypothesis_driven_fast_loop_20260908.md` + `docs/praxist.md` 取代；硬门以 loop-constraints 为准」。

**I6. 2026-07/08 spec 状态栏普遍停在 Draft / 待审核 / Phase 1 in progress，看起来像活合同。**

- 证据：见 §1 表。例如 covariate-optimization L3「Phase 1 in progress」（2026-07-28，git 后再无更新）。
- 建议：批量加「历史 / 不约束三环与硬门」一行。不要在本审核改正文。

### Minor

**M1.** spec 架构图 `_ensure_compiled` vs 代码 `ensure_compiled`（compile-skip spec L56 / `cascade/daily_model.py:53`）。

**M2.** 方案 A spec §1 现在时描述 diagnostic 仍在（L20），与头部「已实施」并置。

**M3.** md/txt 双份且 followup-4、alpha2 内容漂移；另有截断名 `...-desig.txt`。

**M4.** `ACCEPT_flock_20260906.md` 记硬顶 1 / 2.5GiB，与当前 `mem_guard.py` 仍一致，但 runbook 写成 flock≤2 / 2GiB——验收条本身还对，索引它的运维文档不对。

**M5.** 控制面 L196 `/workspace/shared/praxist_assets/` 旧路径（runbook 已记噪音）。

**M6.** hardening / compile-skip **计划**勾选框全空，比 spec 更容易骗 agentic worker「从 Step 1 再跑一遍」。

---

## 9. What's Missing（文档缺口，不是代码 bug）

- 没有任何一份 `docs/superpowers/specs/*.md` 在状态栏写明「方案 A 之后 09-02 peer diagnostic 作废」。取代声明只在 `docs/praxist.md` §6，且指向一条**本身过期**的绑定解释。
- 09-02 spec、方案 A spec、hardening spec、loop-constraints 对「EV 是否进入 `gate_pass` 布尔」没有统一句子。现行磁盘事实（runbook L137，`i_oi`）是硬门布尔只判 n+ic，经济门槛在 goal DSL。这应在合同层写死，否则执行者会「修」`gate_pass` 把 EV 塞进去或拿掉。本缺口深审归 Task 7/8，这里只标文档未锁。
- compile-skip / hardening 没有「已 merge 的 commit 哈希」回写到 spec 头，只有 CLAUDE.md 能力表做了 hardening。
- 控制面未声明「peer 不再持有 TimesFM 之后，mem_guard 保护的是慢环单实例」。
- 历史 spec 没有归档目录或 `superseded-by` 字段。

---

## 10. 哪份 spec 现在还敢当合同（执行清单）

| 敢当合同？ | 文件 | 敢的范围 | 不敢的范围 |
|---|---|---|---|
| **敢** | `docs/spec_hypothesis_driven_fast_loop_20260908.md` | peer 假设作者、proposals schema、harvest_proposals、池/backlog、mechanism≥40 | §1 改造前快照；未实现的 pending-proposals 结转 |
| **敢（接口）** | `docs/superpowers/specs/2026-09-10-system-hardening-design.md` | SPEC-004…013 函数名、n_eff 不进 gate、不改硬门阈值、后复权不除法还原 | 「待启动 / 7 天工期 / 依赖 critical-fixes」 |
| **敢（接口）** | `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md` | 同配置跳过 compile、fail-open、不改硬门 | 状态「待审阅」；符号 `_ensure_compiled` |
| **半敢** | `docs/superpowers/specs/praxist_control_plane.md` | 未经批准不启 Praxist；flock=1 / 2.5GiB（与代码一致）；429 failover；慢环加压 3/600 | 15GiB；peer fm_eval 作战；按诊断 EV 选人；`/workspace` 归档 |
| **不敢** | `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | 仅可作三环骨架考古 | diagnostic 筛选、诊断幸存者、硬门只 n≥350、禁改 cascade |
| **不敢** | `docs/superpowers/plans/2026-09-02-praxist-three-loop.md` 的 Spec 绑定解释第 4 条 | 无 | harvest 源、默认 max_points=400 |
| **不敢当施工单** | `docs/superpowers/plans/2026-09-10-system-hardening.md`、`.../2026-09-09-compile-skip-phase1.md` | 无（已做完） | 全空勾选框 |
| **不敢** | 2026-07/08 全部协变量与 Alpha2 spec（含 txt 副本） | 无（历史） | 任何「待审核」字面 |
| **不是 spec，但是合同** | `loop-constraints.md`、`docs/praxist.md`、runbook Harvest 节（L121–137，**不含** L82 与 L192 指针） | 方案 A + 硬门口径 + 唯一写者 | L82、L192 |

---

## 11. 预承诺 vs 实际

预判：① 09-02 仍写 peer diagnostic；② hardening 仍标待启动但 `243693d` 已 merge；③ md/txt 双份；④ 控制面过期；⑤ compile-skip 状态不清。

实际：①②③④⑤ 全部坐实。额外挖到：文档权威链（praxist.md → runbook → 计划 Spec 绑定解释）**比 09-02 spec 原文更危险**，因为绑定解释被标记为「以本箱为准」却仍是 diagnostic；runbook L82 与代码 harvest-during-429 相反；followup-4 / alpha2 的 txt 与 md 已经分叉。

---

## 12. 统计

| 级别 | 条数 |
|---|---|
| Critical | 1（C1） |
| Important | 6（I1–I6） |
| Minor | 6（M1–M6） |

未改生产代码，未启动 Praxist，未 push。
