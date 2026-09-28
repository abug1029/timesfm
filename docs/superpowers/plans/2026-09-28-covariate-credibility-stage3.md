# 阶段 3 实施计划 (2026-09-28)

**前置:** Stage 1 有条件通过（代码+测试层）· Stage 2 有条件通过
**Spec:** `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md` v14
**Stage 1 计划:** `docs/superpowers/plans/2026-09-27-covariate-credibility-stage1.md`

---

## Context

### 为什么 Stage 3 的第一优先级不是 spec §8.3 的 PR-C1..C6

Stage 1 与 Stage 2 的出口核验均附**降级声明**：

> Stage 1 硬门 2/3 的闭合目前仅为「代码 + 测试层闭合」，非「生产层闭合」。

依据（Stage 2 报告 §7）:

| 事件 | 时间 |
|------|------|
| registry 最后写入 | 2026-09-24 **06:25** |
| 三环 SIGTERM 封存 | 2026-09-24 14:22 |
| Stage 1 A1 接线 commit | 2026-09-27（封存后 **3 天**）|

registry 在 A1 接线落地前 3 天即冻结 → **接线从未在生产运行过**。
143/143 裁决缺全部 18 个 A1 字段，`pass_variants()` 返回 **0**。

因此 spec §8.3 的统计实现（PR-C1..C6）在当前状态下**缺少可验证的判据**：
统计量要在真实的 A1 完整裁决流上才有意义。

### 另发现一处 Stage 2 自身的未实证项

spec §8.5 约束 5：

> 阶段 2 核验未通过（**消融显示输入不变**）→ 阶段 4 不得宣称任何协变量有效。

PR-B5 交付了三路消融的**机制与接线**，但审计集**从未实跑**。
即 Stage 2 的核心主张（区分内容效应与通道效应）目前也只是施工图。

**这两项共同构成本阶段的第一优先级。**

---

## 执行顺序

```
【可立即进行 — 与 cutoff 语义正交】
P0a ─┬─ T1-A: registry 复活 → 判据 A（A1 字段确被生产路径写入）
     └─ T2  : 三路消融审计集实跑（验证 Stage 2 核心主张）

【关键路径 — 依赖 D5 裁定】
D5 裁定 ─→ PR-A1（cutoff 语义 + checkpoint 键）
        ─→ 重生成全部 nocov 基线
        ─→ 重跑 DM 配对验证
        ─→ T1-B: 判据 B（pass_variants() > 0）← Stage 1 生产层闭合的唯一充分证据

【P1 — 计划偏移收录，可与上述并行】
T3: PR-B4 dir_acc 口径变更改档
T4: 审计集裁定记录（「固定审计集」语义）

【P2 — spec §8.3 主体】
T5: PR-C1..C6 统计实现
T6: PR-B1 接线（含 64-bit 截断 + 回退吞异常）
T7: 板块部分退化 WARN
```

> **注:** T1 拆为 A/B 两层是 2026-09-28 自查后的修正。原计划把
> `pass_variants() > 0` 当作复活即可达成的判据，实际它依赖 PR-A1 的 cutoff 语义
> （证据见 T1「关键修正」与「阻塞项」两节）。

---

## P0 — 生产层实证（本阶段唯一的新增前置）

### T1: registry 复活三环

**目标:** 产出第一批 **A1 完整的 confirmation 裁决**，验证 Stage 1 全链路在生产生效。

**⚠️ 关键修正（2026-09-28 自查发现）: 验收判据必须分两层，因为 A1 接线验证
**不**与 cutoff 语义正交。**

证据:
- `cascade/statistical_tests.py:373` — `pair_set_hash` 是**共同 cutoff 集合**的哈希:
  `pair_hash = sha256("|".join(str(k) for k in common))`。cutoff 语义变更 → 该哈希变更。
- `evaluator.py` 注释明示: 「PR-A1 前 dm_status 会频繁落
  insufficient_common/no_common_cutoff —— 这是 fail-loud 设计行为」
- `registry_lib.pass_variants()` 要求 `p_value is not None`；
  `p_value` 仅在 DM 配对产出足够共同点（`len(v_series) >= 100`）时才被赋值。

**推论: PR-A1 未落地 → DM 配对频繁失败 → `p_value` 恒 None → `pass_variants()` 恒 0，
即便 A1 接线完全正确。** 故「`pass_variants() > 0`」**不是**接线验证判据，
而是 cutoff 语义就绪后的证据层判据。

#### 验收判据 A — 接线层（PR-A1 落地前即可测，用于解除 Stage 1「代码层」质疑）

1. 新增裁决的 `protocol_fingerprint` / `cov_fingerprint` / `dir_acc_full` /
   `dir_acc_ex_roll` / `n_roll_excluded` / `n_roll_ratio` / `run_mode` /
   `covariates_used` **均非空**
2. `a1_missing_fields()` 对新增裁决返回**空列表**
3. `run_mode` 取值落在 `RUN_MODES` 内（非 None）
4. `dm_status` / `pair_set_hash` **有值**（可为 `no_common_cutoff`，但不得为缺键）

> 判据 A 通过 = 「A1 字段确实被生产路径写入」。这解除 §7 的「接线从未跑过」质疑，
> 但**不**兑现「过门具备证据含义」。

#### 验收判据 B — 证据层（**依赖 PR-A1 落地**）

5. `pass_variants()` 返回值 **> 0**
6. 至少 1 条裁决的 `dm_status` 为可配对状态且 `p_value` 非 None

> 判据 B 通过 = Stage 1 硬门 2/3 的「生产层闭合」。
> **在 PR-A1 落地前不应期待判据 B 达成。**

**复活前置实测状态（2026-09-28）:**

- [x] **baselines 非空** — 8 个品种基线存在
  （`baseline_points_{cj,eg,jd,lh,m,rb,sr,ss}.jsonl`，61-62KB，2026-09-16/17）
  + `baseline_points_rb_nocov.jsonl`（115KB，2026-09-27，Task 5 产物）
  > 「baselines 空」是 2026-09-24 的**历史状态**，当前不成立。
- [x] **`baseline_metrics.json` 覆盖 8 品种**
- [ ] ⚠️ **`symbol_status.json` 全部非 ACTIVE** — 复活首要障碍:

  | 品种 | 状态 | 依据 |
  |------|------|------|
  | `eg` | **DEAD** | 22 ok verdicts, 0 pass, best dir_acc=0.490 |
  | `jd` | **HOLD** | 7 ok verdicts, 0 pass, best=0.468 |
  | `lh` | **HOLD** | 7 ok verdicts, 0 pass, best=0.488 |

  `harvest_proposals` 对 DEAD/HOLD 直接 `_reject`（L1415/L1417）。
  未登记品种默认 ACTIVE → 8 个有基线品种中 **仅 m / ss / sr / cj / rb 可提案**。
  **复活前须裁定:** 重置 eg/jd/lh 状态，或接受 5 品种起步。
- [x] **提案门禁不会重演饿死** — PR-B6 circuit-breaker 在位，实测拦截率 0%
- [ ] **`no_failure_delta` 拒绝率需观察** — 2026-09-24 的 ~100% 拒绝是停滞根因之一

**风险:** 复活后可能因其他未知门禁再次饿死。**缓解:** 首轮观察
`reject_reasons` 分布，任一 reason 占比 > 80% 立即暂停归因。

**预计:** 2 天（含观察窗口）

### T2: 三路消融审计集实跑

**目标:** 兑现 spec §8.5 约束 5 的「消融显示输入不变」核验。

**交付:**
- 对 `config/ablation_audit_config.json` 定义的 7 品种 × 5 协变量，
  以 `--ablation-mode {full,content,structural,baseline}` 各跑一遍
- 产出对照表：`full` vs `content`（内容效应）· `full` vs `structural`（通道效应）
  · `structural` vs `baseline`（代码路径差异）
- 结论：协变量输入是否真的改变了预测（若 `content` ≈ `full`，则"内容"无效应）

**依赖:** 与 T1 并行可行（回测不依赖三环存活），但**结论需在 T1 的 A1 裁决流上复核**。

**预计:** 1.5 天

---

## P1 — 计划偏移的正式收录

### T3: PR-B4 dir_acc 口径变更改档

Stage 2 计划中 PR-B4（dir_acc 口径变更）因影响面过大延期。
**本阶段须在计划文档中正式改档**（而非仅在报告里留一行），并说明:
- 变更后的口径定义
- 对已有裁决的影响面（143 条 + T1 新增）
- 是否需要迁移

### T4: 审计集裁定记录

PR-B5 评审 H2 指出：审计集加入 `fu`（补 energy_chem 覆盖）触及
spec §4.2 W2.3「固定审计集」的「固定」语义。
**须补一条裁定记录:** 审计集是否允许扩充？扩充是否影响跨阶段可比性？

---

## P2 — Spec 定义的 Stage 3 主体（§8.3）

| PR | 标题 | 主要文件 |
|----|------|---------|
| PR-C1 | `detection_threshold_*` + 配对 HAC + `n_required` 功效公式 | `statistical_tests.py`, `evaluation_metrics.py` |
| PR-C2 | family 定义 + 封账 + 未完成检验 `p=1` + `T_max` 兜底 + 跨品种范围声明 | `praxist_supervisor.py`, `statistical_tests.py`, 报告模板 |
| PR-C3 | `n_eff` 实测（七类边界）+ 定位收窄为诊断与最低信息门槛 | `evaluation_metrics.py` |
| PR-C4 | 门槛一致性 + 历史修订防护 + 预训练登记 | `evaluator.py`, `registry_lib.py`, `docs/` |
| PR-C5 | 协变量族**诊断矩阵**（只诊断，不自动归档） | `covariate_family_verdict.json`, 诊断脚本 |
| PR-C6 | horizon 尾填充（W5）：`horizon_known` 分类 + 证据格式 + 前视不变量 | `covariate_pool.json`, `features.py`, `hourly_model.py` |

### T6: PR-B1 接线（评审登记项）

PR-B1 已重定性为库实现（Stage 2 决策）。本阶段接线前须先解决:
- **64-bit 截断**: SHA-256 截断至 16 hex（64 bit），须评估是否改为全长
- **回退吞异常**: `compute_variant_id` 的回退路径静默吞异常，须区分
  "预期失败"与"编程错误"
- **接线前置**: 须在 T1 产出的 A1 完整裁决流上验证，不得在死数据上接线

### T7: 板块部分退化 WARN

PR-B6 评审建议：`n_failed >= sector_size * 0.5` 时打 WARN，用于预警
"板块部分退化"（当前 circuit-breaker 是二元 block/pass，无预警能力）。

---

## 阻塞项 — D5 裁定（**本计划的关键路径**）

**spec §8.5 硬约束:**

> 2. **D5 未裁定 → PR-A1 与 PR-D2 均不得实施**（阶段 1 其余项可并行）。

PR-A1（cutoff 语义 + checkpoint 键）落地后须:
1. 重新生成全部 nocov 基线
2. 重跑 DM 配对验证

### 与 T1 的依赖关系（修正后结论）

**先前判断「A1 接线验证与 cutoff 语义正交」是错的**，证据见 T1 的「关键修正」:

| A1 字段 | 是否依赖 cutoff 语义 |
|---------|-------------------|
| `protocol_fingerprint` / `cov_fingerprint` / `dir_acc*` / `run_mode` / `covariates_used` | **否** — 与 cutoff 无关 |
| `pair_set_hash` / `raw_cutoff_set_hash` | **是** — 直接哈希共同 cutoff 集合 |
| `dm_common_count` / `d_series_n_eff` / `p_value` | **是** — 派生自配对结果 |

**因此:**
- T1 的**判据 A（接线层）**与 cutoff 语义正交 ✅ 可在 PR-A1 前进行
- T1 的**判据 B（证据层）**依赖 PR-A1 ❌ **不可**在 PR-A1 前达成

### 裁定建议

**D5 → PR-A1 应作为 T1 判据 B 的硬前置，与 T1 判据 A 并行推进：**

1. **立即可做（不依赖 D5）:** T1 判据 A + T2（消融实跑）
   —— 二者分别验证「A1 字段被写入」与「协变量输入是否有效应」，均与 cutoff 正交
2. **D5 裁定后:** 实施 PR-A1 → 重生成 nocov 基线 → 重跑 DM → T1 判据 B
3. **不得**在 PR-A1 前宣称「Stage 1 生产层闭合」

**须在批准评审中明确:**
- D5 的**裁定责任方**与**时限**（当前计划未指定）
- 若 D5 长期无法裁定，判据 B 将无限期挂起 —— 此时应显式声明
  「Stage 1 生产层闭合延期」，而非默默降格

---

## 出口判据

1. **T1 判据 A 全部满足** → 解除 Stage 1/2 的「接线从未跑过」质疑
2. **T1 判据 B 满足（`pass_variants() > 0`）** → 解除 Stage 1/2 的**生产层**降级声明
   （**依赖 PR-A1 落地**；若 D5 未裁定，本项显式挂起并声明）
3. **T2 产出消融对照结论** → 兑现 spec §8.5 约束 5「消融显示输入不变」
4. **T3/T4 改档与裁定记录入库**
5. **PR-C1..C6 全绿** + spec §8.3 的核验清单逐项通过（见下方「spec §8.3 核验清单落地」）
6. **D5 裁定状态明确**（已裁定 / 明确延期及影响 + 责任方 + 时限）

**阶段 3 核验未通过 → 不得进入阶段 4**（spec §8.5 约束 4）。

### spec §8.3 核验清单落地（不得仅引用 spec）

spec §8.3 列出的阶段 3 出口核验项，须逐条落入本计划的测试与判据:

| spec §8.3 核验项 | 落地形式 |
|-----------------|---------|
| 已知自相关序列手算长程方差，与代码结果比较 | 黄金用例（完整序列 + 参数 + **精确预期值**） |
| 验证负自相关 / 边界滞后 / 重叠预测场景 | 各 ≥1 个专项用例 |
| **分别**验证三套公式（`n_eff` 实测 ESS / DM 标准误 / 功效规划） | 三套独立用例；**禁止**一套通过即视为三套通过 |
| 断言实现中**不存在**「长程方差 × VIF」混用路径 | 静态断言测试（§4.3 W3.5 二选一） |
| 固定黄金用例写明带宽约定 / 均值中心化 / 样本方差分母 / 有限样本修正 | 用例 docstring 强制字段 |
| 重叠预测相关结构：实测 HAC vs 名义 VIF 的区分 | 断言名义 VIF 不得用于检验校正 |

> 本表为 Stage 3 计划对 spec 核验清单的**承接**，避免「引用了 spec 但没落到计划」。

---

## 依赖与硬约束（引用 spec §8.5，不重复罗列）

1. 阶段 4 前置 = 阶段 1–3 全部 PR + D5 裁定 + 目标效应裁定
2. D5 未裁定 → PR-A1 / PR-D2 不得实施
3. 目标效应未裁定 → PR-D2 不得实施
4. 阶段 3 核验未通过 → 不得进入阶段 4
5. 阶段 2 核验未通过（消融显示输入不变）→ 阶段 4 不得宣称任何协变量有效
6. 阶段 2 是诊断项，不阻塞阶段 1 交付
7. 每个 PR 必须带绿测试

---

## 与 Stage 2 报告的对应

| 本计划项 | Stage 2 报告出处 |
|---------|-----------------|
| T1 registry 复活 | §9.2（升格为 P0）· §7 |
| T2 三路消融实跑 | 本计划新增（Stage 2 未实证项） |
| T3 PR-B4 改档 | §9.3 第 2 项 |
| T4 审计集裁定 | §9.3 第 3 项 |
| T5 PR-C1..C6 | spec §8.3 |
| T6 PR-B1 接线 | §9.3 第 4 项 |
| T7 板块退化 WARN | §9.3 第 5 项 |
| D5 / PR-A1 | §9.4 |
