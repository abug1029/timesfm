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
P0 ─┬─ T1: registry 复活三环（验证 Stage 1 A1 接线）
    └─ T2: 三路消融审计集实跑（验证 Stage 2 核心主张）
P1 ─┬─ T3: PR-B4 dir_acc 口径变更改档
    └─ T4: 审计集裁定记录（「固定审计集」语义）
P2 ─┬─ T5: PR-C1..C6 统计实现（spec §8.3）
    ├─ T6: PR-B1 接线（含 64-bit 截断 + 回退吞异常）
    └─ T7: 板块部分退化 WARN
阻塞 ── D5 裁定 → PR-A1（cutoff 语义）→ 重生成 nocov 基线 + 重跑 DM
```

---

## P0 — 生产层实证（本阶段唯一的新增前置）

### T1: registry 复活三环

**目标:** 产出第一批 **A1 完整的 confirmation 裁决**，验证 Stage 1 全链路在生产生效。

**验收判据（必须全部满足）:**

1. 新增裁决的 `protocol_fingerprint` / `cov_fingerprint` / `pair_set_hash` /
   `dir_acc_full` / `dir_acc_ex_roll` / `dm_status` / `run_mode` **均非空**
2. `a1_missing_fields()` 对新增裁决返回空列表
3. `pass_variants()` 返回值 **> 0**（当前为 0）—— 这是 Stage 1 硬门 2/3
   「生产层闭合」的唯一充分证据
4. `run_mode` 字段实际取值落在 `RUN_MODES` 内（非 None）

**前置检查（复活前必须确认）— 以下为 2026-09-28 实测状态:**

- [x] **baselines 非空** — 8 个品种的基线存在
  （`baseline_points_{cj,eg,jd,lh,m,rb,sr,ss}.jsonl`，均 61-62KB，2026-09-16/17 生成）
  + `baseline_points_rb_nocov.jsonl`（115KB，2026-09-27，Task 5 产物）
  > 注：2026-09-24 停滞根因之一的「baselines 空」是**历史状态**，当前已不成立。
- [x] **`baseline_metrics.json` 覆盖 8 品种**（cj/eg/jd/lh/m/rb/sr/ss）
- [ ] ⚠️ **`symbol_status.json` 全部为非 ACTIVE** — 这是复活的首要障碍:

  | 品种 | 状态 | 依据 |
  |------|------|------|
  | `eg` | **DEAD** | 22 ok verdicts, 0 pass, best dir_acc=0.490 |
  | `jd` | **HOLD** | 7 ok verdicts, 0 pass, best=0.468 |
  | `lh` | **HOLD** | 7 ok verdicts, 0 pass, best=0.488 |

  `harvest_proposals` 对 DEAD/HOLD 直接 `_reject`（L1415/L1417）。
  未在 `symbol_status.json` 中登记的品种默认 ACTIVE —— 即当前
  **8 个有基线的品种中，仅 m / ss / sr / cj / rb 5 个可提案**。
  **复活前须裁定:** 是否重置 eg/jd/lh 状态，或接受 5 品种起步。
- [x] **提案门禁不会重演饿死** — PR-B6 的 circuit-breaker 已在位，
  实测拦截率 0%（Stage 2 报告 §6）
- [ ] **`no_failure_delta` 拒绝率需观察** — 2026-09-24 的 ~100% 拒绝是停滞根因之一；
  复活后须实测其占比

**风险:** 复活后可能因其他未知门禁再次饿死。**缓解:** 复活后首轮观察
`harvest_proposals` 的 `reject_reasons` 分布，若任一 reason 占比 > 80% 立即暂停并归因。

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

## 阻塞项 — D5 裁定

**spec §8.5 硬约束:**

> 2. **D5 未裁定 → PR-A1 与 PR-D2 均不得实施**（阶段 1 其余项可并行）。

PR-A1（cutoff 语义 + checkpoint 键）落地后须:
1. 重新生成全部 nocov 基线
2. 重跑 DM 配对验证

**与 T1 的依赖（必须在计划评审中裁定）:**

若 PR-A1 在 T1 之后落地 → T1 产出的裁决建立在待变更的 cutoff 语义上 → 需重跑。
若 PR-A1 在 T1 之前落地 → T1 的 A1 裁决流一次到位。

**建议:** 在 T1 之前先推动 D5 裁定；若 D5 短期无法裁定，
则 T1 照常进行（其目的是验证 A1 接线，与 cutoff 语义正交），
但须在 T1 结论中显式声明"cutoff 语义待 D5 裁定，届时需重跑"。

---

## 出口判据

1. **T1 验收判据 1-4 全部满足**（`pass_variants()` > 0）→ 解除 Stage 1/2 的降级声明
2. **T2 产出消融对照结论** → 兑现 spec §8.5 约束 5
3. **T3/T4 改档与裁定记录入库**
4. **PR-C1..C6 全绿** + spec §8.3 的核验清单逐项通过
5. **D5 裁定状态明确**（已裁定 / 明确延期及影响）

**阶段 3 核验未通过 → 不得进入阶段 4**（spec §8.5 约束 4）。

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
