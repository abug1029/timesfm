# 阶段 3 实施计划 v4 (2026-09-28)

**前置:** Stage 1 有条件通过（代码+测试层）· Stage 2 出口核验 **v4 批准，有条件通过生效**
**Spec:** `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md` v14
**Stage 1 计划:** `docs/superpowers/plans/2026-09-27-covariate-credibility-stage1.md`

> **版本历史**
> - **v1** (`bb0981f`/`1217ccc`) — 被退回：① T1 头条判据 `pass_variants() > 0` 结构性不可达；
>   ② 「baselines 非空」误导（7/8 是已作废 ccl 基线）；③ spec §8.1 手算核验遗漏；
>   ④ §8.3 核验清单未落到任务；⑤ D5 无责任方/时限/默认分支。
> - **v2** (`65beade`) — 逐项修复上述五点，并消除 Stage 2 报告 §9.1 的循环依赖。
> - **v3** (`1d4ab7d`) — 复评收尾：④ 补齐 §8.3 黄金用例枚举三子项与
>   「无第二套参数定义 ≠ 已验证」项；修正执行图悬空的 T1c 标签；
>   补 `cutoff_convention` 字段的实现归属（PR-A1）。
> - **v4（本版）** — 依 Stage 2 v4 批准审核追加的两条核验项：
>   ① **硬性排序**: D5 裁定（或宿主显式宣布「本轮不裁、按现语义跑」）
>      **必须先于 T1a 实跑步骤**，否则复活做两遍；
>   ② **判据 B' 的降级写法**: D5 未裁时记为**条件性达成**（测了但结论带前提），
>      不得静默豁免（没测）。

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

### 三处「只有施工图、未实证」的项（v2 已全部收录）

| # | 未实证项 | spec 出处 | 本计划任务 |
|---|---------|----------|-----------|
| 1 | Stage 1 A1 接线从未生产运行 | Stage 1 §7 | T1 |
| 2 | 三路消融审计集从未实跑 | **§8.2 出口核验** | T2 |
| 3 | **手算核对预测点从未执行** | **§8.1 出口核验** | **T1b（v2 新增）** |

---

## 执行顺序

```
【第一道关 — 决策（硬性前置，v4）】
D5 裁定  或  宿主显式宣布「本轮不裁、按现语义跑」
        │
        │  ※ 未做此决策不得进入 T1a 实跑 —— 否则 PR-A1 落地后
        │    基线失效 + DM 重跑 → 复活做两遍
        ▼
【P0a — 生产层实证】
T1a : 7 个 nocov 基线重生（~70 min）
      → registry 复活
      → 判据 A（A1 字段确被生产路径写入）
T1b : 手算核对预测点（spec §8.1）        ← 需 T1a 的裁决流
T2  : 三路消融审计集实跑（spec §8.2）    ← 需基线；fu 需先冒烟

【关键路径（仅 D5 已裁情形）】
D5 裁定 ─→ PR-A1（cutoff 语义 + checkpoint 键 + 协议指纹 bump）
        ─→ 重生成全部 nocov 基线
        ─→ 重跑 DM 配对验证
        ─→ T1a 判据 B'（确定性达成）
    ※ D5 未裁（路径 b）→ 判据 B' 改为条件性达成，见「阻塞项」

【P1 — 计划偏移收录，可与上述并行】
T3: PR-B4 dir_acc 口径变更改档
T4: 审计集裁定记录（「固定审计集」语义）

【P2 — spec §8.3 主体】
T5: PR-C1..C6 统计实现 + §8.3 核验交付物
T6: PR-B1 接线 + Stage 2 登记的小项
T7: 板块部分退化 WARN
```

> **v4 关键改动:** 原图把 T1a 标为「不依赖 D5 裁定」—— **与硬性排序要求冲突**。
> 实测 T1a 的基线重生同样会被 PR-A1 的 cutoff 语义变更作废
> （Stage 2 v4 批准审核指出「PR-A1 落地会使 nocov 基线失效」），
> 故 T1a 整体置于 D5 决策之后。

---

## P0a — 生产层实证

### T1a: registry 复活 + nocov 基线重生

**目标:** 产出第一批 **A1 完整**的裁决，验证 Stage 1 A1 接线在生产生效。

#### 判据可达性（v2 核心修正）

**原计划判据 `pass_variants() > 0` 结构性不可达**，证据:

| 证据 | 内容 |
|------|------|
| `registry_lib.py:456` | `pass_variants()` 显式 `continue` 掉 `run_mode == "exploration"` |
| `evaluator.py:318` | `build_summary(..., run_mode="exploration")` —— **默认值即 exploration** |
| 生产路径 grep | `aligned_slow_loop.py` / `run.py` **均不传** `run_mode` → 全部落 exploration |
| `aligned_slow_loop.py:84,95` | `_no_data_verdict` 写 `run_mode=None` |
| Stage 1 报告 §5 | 自述「生产 verdict 全部是 exploration —— 这是设计意图」 |
| spec §1.4 | confirmation **必须有已锁定 `prereg_id`**，而 prereg 是 **PR-D1（阶段 4）** 交付物 |

**推论:** 在 PR-D1 落地前，生产裁决**全部是 exploration** → `pass_variants()` 结构性恒 0。
这与 PR-A1/cutoff 无关，是**运行模式设计**导致的，阶段 3 范围内无法解除。

#### 验收判据 A — 接线层（本阶段可达成）

限定为「**经评估产出的、非 no-data 墓碑的** exploration 裁决」（排除 `_no_data_verdict`
的合法 null）:

1. 新增裁决的 `protocol_fingerprint` / `dir_acc_full` / `dir_acc_ex_roll` /
   `n_roll_excluded` / `n_roll_ratio` / `run_mode` / `covariates_used` **均非空**
2. `a1_missing_fields()` 对新增裁决返回**空列表**
3. `run_mode == "exploration"`（当前设计预期值，非 None）
4. `dm_status` / `pair_set_hash` **有值**（可为 `no_common_cutoff`，但不得为缺键）
5. `cov_fingerprint` 可为 null（在 `A1_NULLABLE` 内，exploration 传不齐矩阵时是设计豁免）

> **判据 A 通过 = 「A1 字段确实被生产路径写入」** → 解除 Stage 1/2 的
> 「接线从未跑过」质疑。

#### 验收判据 B' — 统计层（**依赖 PR-A1**）

6. 至少 1 条裁决的 `pairing_valid=True` 且 `p_value` 非 None
7. `dm_status` 落入可配对状态（非 `no_baseline` / `no_common_cutoff`）

> **判据 B' 通过 = 「DM 配对在生产真实产出 p 值」。**
> 依赖 PR-A1（cutoff 语义就绪），见「阻塞项」。
>
> **v4 补充:** 该判据的可达性是**决策问题而非工程问题**。
> D5 已裁 → **确定性达成**；D5 未裁（按路径 b）→ **条件性达成**
> （仍须实测并记录，但结论标注「基于 `bar_open` 语义」）。
> **不得**跳过实测，也**不得**无限定地记为「已达成」。
> 详见「阻塞项 — D5 裁定」的降级写法。

#### 验收判据 C — 晋升层（**本阶段不可达，显式推迟**）

8. `pass_variants() > 0` —— **推迟至 PR-D1（阶段 4）之后**。
   本计划**不**以此为阶段 3 出口判据。

#### 前置检查（2026-09-28 实测）

- [ ] ⚠️ **nocov 基线仅 rb 存在（1/8）** — v2 修正

  | 基线文件 | 状态 | 说明 |
  |---------|------|------|
  | `baseline_points_rb_nocov.jsonl` | ✅ 588 行，含 `protocol_fingerprint` | 生产可用 |
  | `baseline_points_{cj,eg,jd,lh,m,sr,ss}.jsonl` | ❌ **已作废** | 2026-09-16/17 的 **ccl 基线**，首行无 `protocol_fingerprint`；Stage 1 报告 §4.7 声明 cov_fill v1→v2 使其作废 |

  生产读取路径: `aligned_slow_loop.py:153` / `run.py:109` → `load_baseline_points(symbol, cov=None)`
  → `cascade/baseline_paths.py:12` → `baseline_points_{sym}_nocov.jsonl`。
  **ccl 基线文件存在 ≠ 生产可用。**

  **处置:** `ensure_baselines`（`praxist_supervisor.py:2188`）已正确使用
  `gbp.baseline_filename(sym, None)`（nocov 路径；docstring 过期但代码正确）。
  对 7 个品种其 `n_lines = 0 < 100` → **会自动串行重生**，每品种约 10 min 模型实跑
  （7 品种 ≈ 70 min）。**列为 T1a 显式步骤与观察项。**

  验收命令:
  ```
  ls task_FM/config/baseline_points_*_nocov.jsonl | wc -l   # 期望 8
  head -1 task_FM/config/baseline_points_m_nocov.jsonl      # 须含 protocol_fingerprint
  ```

- [x] **提案门禁不会重演饿死** — PR-B6 circuit-breaker 在位，实测拦截率 0%
- [ ] ⚠️ **`symbol_status.json` 全部非 ACTIVE**:

  | 品种 | 状态 | 依据 |
  |------|------|------|
  | `eg` | **DEAD** | 22 ok verdicts, 0 pass, best dir_acc=0.490 |
  | `jd` | **HOLD** | 7 ok verdicts, 0 pass, best=0.468 |
  | `lh` | **HOLD** | 7 ok verdicts, 0 pass, best=0.488 |

  `harvest_proposals` 对 DEAD/HOLD 直接 `_reject`（L1415/L1417）；未登记品种默认 ACTIVE
  → 8 个品种中 **仅 m / ss / sr / cj / rb 可提案**。
  **复活前须裁定:** 重置 eg/jd/lh，或接受 5 品种起步。
- [ ] **`no_failure_delta` 拒绝率需观察** — 2026-09-24 的 ~100% 拒绝是停滞根因之一
- [ ] ⚠️ **无基线品种会落 `no_baseline`** — `cf/i/jm/ma/p/sh` 在 `ALLOWED_SYMBOLS` 内、
  有裁决但无任何基线 → 提案后 `dm_status=no_baseline`、`p_value=None`。
  这是「8 品种中仅 5 个可提案」之外的**第二层可行性收窄**，须在结论中声明。

**风险:** 复活后可能因其他未知门禁再次饿死。**缓解:** 首轮观察 `reject_reasons` 分布，
任一 reason 占比 > 80% 立即暂停归因。

**预计:** 2.5 天（含 70 min 基线重生 + 观察窗口）

### T1b: 手算核对预测点（spec §8.1 出口核验）— v2 新增

**目标:** 兑现 spec §8.1 出口核验「取 2–3 个品种、固定窗口与 cutoff，手算核对一小批
预测点，证明对齐与基线配对正确」。

Stage 1 报告 §4 第 2 条自述「**未做**逐点手算……留待阶段 2 或按需补做」，
Stage 2 未做，v1 计划亦未收录 —— 与 T2 同构的未实证项。

**交付:**
- 取 `rb`（有 nocov 基线）+ 1 个其他品种，固定窗口与 cutoff
- 手算 3–5 个预测点的 `dir_ok` / `delta_pred` / `delta_real`
- 手算变体与基线的 cutoff 交集，与裁决的 `dm_common_count` 对账
- 产出对账记录（可人工复算）

**依赖:** T1a（需真实裁决流与基线）。

**预计:** 0.5 天

### T2: 三路消融审计集实跑

**目标:** 兑现 spec **§8.2 出口核验**（「用少量代表性协变量做完整消融，确认输入确实改变模型」）
—— §8.5 约束 5 是其后置条款。

**交付:**
- 对 `config/ablation_audit_config.json` 的 7 品种 × 5 协变量，
  以 `--ablation-mode {full,content,structural,baseline}` 各跑一遍
- 对照表: `full` vs `content`（内容效应）· `full` vs `structural`（通道效应）
  · `structural` vs `baseline`（代码路径差异）
- 结论: 协变量输入是否真的改变预测

**前置检查（v2 新增）:**
- [ ] ⚠️ **`fu` 的可行性未验证** — 审计集含 `fu`（补 energy_chem 覆盖），
  但 `fu` **无基线、无裁决、未见 checkpoint 证据**。
  启动前须先跑一个 `fu` 的 `full` 模式**冒烟**，确认模型 checkpoint 可用。

**预计:** 1.5 天（+ 冒烟 0.5 天）

---

## P1 — 计划偏移的正式收录

### T3: PR-B4 dir_acc 口径变更改档

Stage 2 计划中 PR-B4（dir_acc 口径变更）因影响面过大延期。
**本阶段须在计划文档中正式改档**，说明: 变更后口径定义 · 对已有裁决的影响面
（143 条 + T1a 新增）· 是否需要迁移。

### T4: 审计集裁定记录

PR-B5 评审 H2: 审计集加入 `fu` 触及 spec §4.2 W2.3「固定审计集」的「固定」语义。
**须补裁定记录:** 审计集是否允许扩充？扩充是否影响跨阶段可比性？

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

### T5 的 §8.3 核验交付物（v2 新增 — 不得只引用 spec）

spec §8.3 的核验项须逐条认领到具体交付物，避免重演 Stage 1 v2
「67 测试全绿却有 4 个 CRITICAL 空转」的假闭合:

| spec §8.3 核验项 | 交付物 | 认领 PR |
|-----------------|-------|--------|
| 已知自相关序列手算长程方差，与代码结果比较 | 黄金用例文件（完整序列 + 参数 + **精确预期值**） | PR-C1 |
| 负自相关 / 边界滞后 / 重叠预测场景 | 各 ≥1 专项用例 | PR-C1 / PR-C3 |
| **三套公式分别验证**（`n_eff` 实测 ESS / DM 标准误 / 功效规划） | 三套独立用例；**禁止**一套通过即视为三套通过 | PR-C1 / PR-C3 |
| **不把「没有第二套参数定义」当成「统计量定义已验证」** | 显式用例：断言每套公式均有独立定义与独立预期值 | PR-C1 / PR-C3 |
| 断言实现中**不存在**「长程方差 × VIF」混用路径 | 源码断言测试（§4.3 W3.5 二选一） | PR-C1 |
| 黄金用例写明带宽约定 / 均值中心化 / 样本方差分母 / 有限样本修正 | 用例 docstring 强制字段 | PR-C1 |
| **黄金用例枚举（spec §5.3 测试 67）**: 负自相关 / **常数序列** / **有效样本不足** / **带宽边界** 各一 | 四个边界用例（「边界滞后」≠「带宽边界」，须分别覆盖） | PR-C1 / PR-C3 |
| 重叠预测: 实测 HAC vs 名义 VIF 的区分 | 断言名义 VIF 不得用于检验校正 | PR-C1 |
| 手算对账记录 | 独立记录文件 | PR-C3 |

### T6: PR-B1 接线 + Stage 2 登记的小项

**接线前置:** 须在 T1a 产出的裁决流上验证，不得在死数据上接线。

**PR-B1 评审登记项（v2 补全 — v1 仅覆盖前两项）:**
- 64-bit 截断（SHA-256 截断至 16 hex）评估
- 回退路径静默吞异常 → 区分「预期失败」与「编程错误」
- golden 值测试
- 返回类型一致性（`(str, dict)` vs `(str, None)`）
- `validate_verdict_v2` 的 nullable 变量命名
- `compute_seed_fingerprint` seed 范围校验
- `sys` import 位置

**PR-B2 评审登记项:**
- 四类诊断互斥丢失信息 / 空 context 的 RuntimeWarning / 函数内惰性 import / 测试 seed

**PR-B5 评审登记项:**
- L3: resume 冲突检查在模型加载（~800MB）之后
- N3: `predict()` 未暴露 seed 参数

### T7: 板块部分退化 WARN

PR-B6 评审建议: `n_failed >= sector_size * 0.5` 时打 WARN，
用于预警「板块部分退化」（当前 circuit-breaker 是二元 block/pass，无预警能力）。

---

## 阻塞项 — D5 裁定（**本计划的关键路径**）

**spec §8.5 硬约束 2:** 「D5 未裁定 → PR-A1 与 PR-D2 均不得实施」。

PR-A1（cutoff 语义 + checkpoint 键）落地后须:
1. 重新生成全部 nocov 基线
2. 重跑 DM 配对验证

### 与 T1 的依赖关系（v2 修正表述）

v1 的「A1 接线验证与 cutoff 语义正交」**表述过强**，正确表述:

| 层面 | 与 cutoff 语义的关系 |
|------|-------------------|
| **字段管线**（判据 A 的 1/2/4 项） | **正交** — 字段是否落盘与 cutoff 无关 |
| **统计输出**（`pair_set_hash` / `dm_status` / `dm_common_count` / `d_series_n_eff` / `baseline_dir_acc` / `p_value` / 判据 B'） | **完全下游** — D5 若裁定改 `bar_close`，全部 cutoff 时间戳 +1h → 配对交集 / 方向标签 / DM 序列全变 → **T1 的统计输出全部作废** |

**因此:** T1 验证的是**接线与字段完备性**；其**统计输出在 D5 裁定后须全部重跑**，
**不作为持久证据**。

### PR-A1 的协议指纹衔接（v2 新增）

实测 `compute_protocol_fingerprint`（`evaluator.py:279-292`）当前**不含** cutoff 约定分量，
而 spec §4.1（L397）要求「cutoff 约定（bar_open/bar_close）| D5 裁定结果」**进入协议指纹**。

**PR-A1 落地时必须**将 cutoff 约定并入 `compute_protocol_fingerprint`
或 bump `PROTOCOL_FINGERPRINT_VERSION` —— 否则 A1 前后裁决指纹逐字节相同却不可比，
**可比性守卫（`comparable()`）失效**。

### D5 裁定责任方与时限（v2 新增）

| 项 | 内容 |
|----|------|
| **责任方** | **宿主本人**（D5 是研究方向决策，非工程决策） |
| **裁定窗口** | **T1a 实跑步骤之前**（硬性排序，见下） |
| **默认分支** | 若未裁定，宿主须**显式宣布**「本轮不裁、按现语义跑」；此时按 spec §4.1 W1.6 的 **(b) 维持 `bar_open` 现状**，裁决落 `cutoff_convention` 字段，T1a 结论中**显式声明**统计输出待重跑 |
| **逾期处理** | 判据 B' 改为**条件性达成**（见下），**不得**静默豁免 |

#### ⚠️ 硬性排序要求（v4 新增 — 防「复活做两遍」）

**D5 裁定（或宿主显式宣布「本轮不裁、按现语义跑」）必须先于 T1a 的实跑步骤。**

理由: 若 T1a 先跑、PR-A1 后落地，则:
1. 三环复活并产出一批裁决
2. PR-A1 改变 cutoff 语义 → nocov 基线全部失效 → 重生成
3. DM 配对重跑 → 第 1 步产出的裁决统计输出全部作废
4. **T1a 实跑做两遍**（每次含 7 品种基线重生 ~70 min + 观察窗口）

**可接受的两条路径（均须在实跑前落定）:**

| 路径 | 前置动作 | 后果 |
|------|---------|------|
| (a) D5 已裁定 | 直接进 T1a 实跑 | 统计输出一次到位 |
| (b) 宿主显式宣布「本轮不裁、按现语义跑」 | 记录该声明 + 落 `cutoff_convention="bar_open"` | 判据 B' 为**条件性达成**；PR-A1 落地后须重跑 |

**不接受:** 未做任何裁定/声明就开跑 —— 这会让 T1a 的结论处于
「不知是否需重跑」的悬空状态。

#### 判据 B' 的降级写法（v4 新增）

判据 B' 的可达性是**决策问题而非工程问题** —— 依赖 PR-A1，而 PR-A1 受 D5 阻断。
因此:

- **D5 已裁定** → 判据 B' 为**确定性达成**（实施 PR-A1 → 重生成基线 → 重跑 DM）
- **D5 未裁（路径 b）** → 判据 B' 为**条件性达成**:
  - 仍须实测「至少 1 条裁决 `pairing_valid=True` 且 `p_value` 非 None」**并记录实测结果**
  - 但结论须标注: 「基于 `bar_open` 语义；D5 若改 `bar_close` 则本判据须重测」
  - **不得**因 D5 未裁而跳过该项实测，也**不得**将其记为「已达成」而不加限定

> 二者区别: 条件性达成 = **测了，但结论带前提**；静默豁免 = **没测**。前者可审计，后者不可。

> ⚠️ **`cutoff_convention` 字段当前不存在**（全仓 grep 0 命中）。
> 若默认分支触发，**实现归属为 PR-A1**（cutoff 语义域）；在此之前不得引用该字段。
> 该字段须同时并入 `compute_protocol_fingerprint`（见下节「协议指纹衔接」）。

---

## 出口判据

0. **D5 决策已落定**（裁定 / 或宿主显式宣布「本轮不裁、按现语义跑」）
   —— **硬性前置**，未落定不得进入 T1a 实跑
1. **T1a 判据 A 全部满足** → 解除 Stage 1/2 的「接线从未跑过」质疑
2. **T1a 判据 B' 达成** → 解除 Stage 1/2 的**统计层**降级声明:
   - D5 已裁 → **确定性达成**
   - D5 未裁（路径 b）→ **条件性达成**（须实测并记录，结论标注
     「基于 `bar_open` 语义；D5 若改 `bar_close` 则须重测」）
   - **不得**跳过实测，也**不得**无限定地记为「已达成」
3. **T1b 手算对账记录入库** → 兑现 spec §8.1 出口核验
4. **T2 产出消融对照结论** → 兑现 spec §8.2 出口核验
5. **T3/T4 改档与裁定记录入库**
6. **PR-C1..C6 全绿** + §8.3 核验交付物（见 T5 表）逐项产出
7. **D5 裁定状态明确**（已裁定 / 显式宣布不裁 + 声明）

**判据 C（`pass_variants() > 0`）不作为阶段 3 出口判据** —— 结构性依赖 PR-D1（阶段 4）。

**阶段 3 核验未通过 → 不得进入阶段 4**（spec §8.5 约束 4）。

---

## 依赖与硬约束（引用 spec §8.5）

1. 阶段 4 前置 = 阶段 1–3 全部 PR + D5 裁定 + 目标效应裁定
2. D5 未裁定 → PR-A1 / PR-D2 不得实施
3. 目标效应未裁定 → PR-D2 不得实施
4. 阶段 3 核验未通过 → 不得进入阶段 4
5. 阶段 2 核验未通过（消融显示输入不变）→ 阶段 4 不得宣称任何协变量有效
6. 阶段 2 是诊断项，不阻塞阶段 1 交付
7. 每个 PR 必须带绿测试，**禁止把「下一步再写测试」写进 diff**（v2 补全后半句）

---

## 孤儿项处置（v2 新增 — 不留静默孤儿）

| 项 | 来源 | 处置 |
|----|------|------|
| `_primary_fp` 排名守卫 | Stage 1 报告 §8（HIGH，明确推迟阶段 2，「待宿主追认」） | **收录进 T5**（门槛一致性，与 PR-C4 同域） |
| PR-B1 其余小项 | Stage 2 报告 §8 | 收录进 **T6**（见 T6 清单） |
| PR-B2 四项 | Stage 2 报告 §8 | 收录进 **T6** |
| PR-B5 L3/N3 | Stage 2 报告 §8 | 收录进 **T6** |
| `get_klines_1h` 缺 `adjustment_policy` 标注 | Stage 1 报告 §8（LOW） | 收录进 **T5**（PR-C4 文档域） |
| `baseline_metrics.json` 键冲突 | Stage 1 报告 §8（MEDIUM） | 收录进 **T1a**（基线重生时一并核） |

---

## 与 Stage 2 报告的对应

| 本计划项 | Stage 2 报告出处 |
|---------|-----------------|
| T1a registry 复活 + 基线重生 | §9.2（升格为 P0）· §7 |
| T1b 手算核对 | **本计划新增**（Stage 1 §8.1 未实证项） |
| T2 三路消融实跑 | **本计划新增**（Stage 2 未实证项，对应 spec §8.2） |
| T3 PR-B4 改档 | §9.3 第 2 项 |
| T4 审计集裁定 | §9.3 第 3 项 |
| T5 PR-C1..C6 | spec §8.3 |
| T6 PR-B1 接线 | §9.3 第 4 项 + §8 登记项 |
| T7 板块退化 WARN | §9.3 第 5 项 |
| D5 / PR-A1 | §9.4 |

**需同步修订 Stage 2 报告 §9.1:** 其解除条件当前绑定「confirmation 裁决」，
而 confirmation 依赖 PR-D1（阶段 4）→ **循环依赖**。
须改为绑定「判据 A + 判据 B'」（阶段 3 可达成）。
