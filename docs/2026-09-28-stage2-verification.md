# 阶段 2 出口核验报告 v4 (2026-09-28)

**Commit 范围:** `51088bd` (Stage 1 末次提交) .. `65beade` (HEAD)
**测试:** 320 用例 / 16 文件（日常回归口径 310 PASS + 1 xfailed，见 §5）

> **版本历史**
> - **v1** (`3d35c39`) — 被退回：① Stage 1 三项退回件无闭环证据；② PR-B1/B2/B3 评审只有"宣称通过"、
>   无逐条对照表；③ `symbol_has_pass` 语义张力未裁定。
> - **v2** (`0660508`) — 补齐三份材料：§2 Stage 1 闭环证据、§3 五个 PR 全量评审对照表、
>   §4.4 `symbol_has_pass` 裁定。另新增 §7（评审期间发现的 registry 遗留数据事实）。
> - **v3** (`842de03`) — 依审核裁定加入 §9.1 有条件通过声明（降级声明）、
>   §9.2 Stage 3 优先级重排（registry 复活升为 P0）、§9.3 五项待办、§9.4 D5 阻断 PR-A1。
> - **v4（本版）** (`65beade`) — 修正 §9.1 解除条件的**循环依赖**：
>   原绑定「confirmation 裁决」而 confirmation 依赖 PR-D1（阶段 4）→ 阶段 3 内永不解除。
>   改为绑定判据 A（接线层）+ 判据 B'（统计层），并显式声明判据 C 属阶段 4 属性。

## 0. Stage 2 意图（摘自计划）

Stage 1 闭合三项硬门（因果对齐、比较对象、可追溯性）。Stage 2 是 L2 诊断层，目标是把"协变量未利用"从推断变成可验证事实，并为后续确认层 (L3) 和预注册层 (L4) 奠基。

**交付清单（5 个 PR）:** PR-B1 指纹系统 · PR-B2 协变量诊断 · PR-B3 `xreg_fallback` 贯通 · PR-B5 三路消融 · PR-B6 提案质量门
**未实施:** PR-B4（dir_acc 口径变更影响面过大）—— **属计划偏移，见 §8**

## 1. 实施清单与提交

| PR | 实施 commit | 评审修复 commit | 新增文件 |
|----|------------|----------------|---------|
| B1 | `20245da` | `e6738cd` | `scripts/fingerprint_lib.py`, 2 测试 |
| B2 | `4e0b598` | `2a33484` | `cascade/covariate_diagnostics.py`, 1 测试 |
| B3 | `53ae61d` | `b89f71d` | — |
| B5 | `2852623`, `170947c` | `e171e45` | `cascade/ablation.py`, `config/ablation_audit_config.json`, 2 测试 |
| B6 | `2fed5b9` | `9d121be` | 3 测试 |
| — | — | `3d35c39` (v1 报告) | `docs/2026-09-28-stage2-verification.md` |

**每个 PR 均经 `oh-my-claudecode:code-reviewer` (opus) 独立评审**，B5/B6 经复评。

## 2. Stage 1 退回件闭环证据（审核阻断项 ①）

上一轮出口核验退回三件事。逐项闭环：

### ① Task 5 实跑（nocov 基线 + `baseline_dir_acc` 落链）

- **实施 commit:** `7328124` feat(eval): 同 cutoff 无协变量基线取代 ccl 基线 (E7)
- **实跑证据:** Stage 1 报告 §1 记载 `scripts/generate_baseline_points.py --symbol rb --cov none`
  → 589 评估点、写入 588 行、`dir_acc=0.435`
- **独立复核脚本:** `c216462` 纳入 `scripts/verify/check_slope_only.py`（审核要求证据可复现）
- **状态:** ✅ 闭环

### ② `test_a1_completeness.py`

- **文件存在:** `tests/test_a1_completeness.py`，**5 tests**（本次实测 5 passed）
- **配套:** `tests/test_nocov_baseline.py`，**5 tests**（本次实测 5 passed）
- **在回归总数中的位置:** 两文件合计 10 tests，已纳入 §5 回归口径
- **状态:** ✅ 闭环

### ③ Task 2 审核遗留证据

- **实施 commit:** `991ff4b` fix(features): ccl_pct bfill 因果化 (D4)
- **12 条失败归因:** Stage 1 报告 L108 记载「12 条，全部在 pre-Stage-1 基线 `b06e5d5` 复现
  （`git merge-base HEAD b06e5d5` == `b06e5d5`）」—— 即 12 条失败均为既有问题，非 Stage 1 引入
- **状态:** ✅ 闭环

### `51088bd` 完整 changelog（审核点名）

`51088bd` 是**纯文档单行提交**，不含代码：

```
51088bd  FlyBuddy  2026-09-27 21:07:08 +0800
docs: 记录第三轮验证结果与 resume 修复

 docs/2026-09-27-stage1-verification.md | 1 +
```

新增内容为 Stage 1 报告版本历史的一行：

> **第三轮验证通过** — 4 个 CRITICAL 修复经独立执行确认真实生效（非 no-op、无崩溃风险）。
> 唯一残留 gap（`covariates_used` 在 `--resume` 时丢失）已由 `500b315` 修复并同步 E2E 夹具。

**结论:** Stage 1 三项退回件均已闭环，`51088bd` 仅是收尾文档。Stage 2 未建在未验收地基上。

> ⚠️ **但 §7 披露了一个新事实**：这三项闭环是**代码与测试层面**的，生产 registry 中
> 尚无一条裁决带 A1 字段。详见 §7。

## 3. 专家评审对照（审核阻断项 ②）

### 3.1 PR-B1 指纹系统 — REQUEST CHANGES → 已修复

| # | 严重度 | 问题 | 处置 |
|---|--------|------|------|
| C1 | CRITICAL | `compute_variant_id` 零生产调用（死代码），PR 声明的"替代 variant_id 去重"未达成 | **按决策重定性为库实现**，接线留 Stage 3（理由见 §4.1） |
| C2 | CRITICAL | 与 Stage 1 同名函数冲突：`fingerprint_lib` 哈希配置 dict vs `evaluator` 哈希数值矩阵，误用则指纹永不匹配、去重静默失效 | 重命名为 `compute_cov_config_fingerprint` / `compute_protocol_config_fingerprint`，docstring 注明不可互换 |
| H1 | HIGH | `compute_weight_fingerprint` 只哈希前 4KB，对"仅末层权重变化、大小不变"的重训练给出相同指纹 → 假去重 | 改为流式哈希完整文件（1MB 分块）+ 回归测试 `test_tail_change_detected_same_size` |
| H2 | HIGH | SHA-256 截断至 16 hex (64 bit)，碰撞概率未评估 | 登记：无生产调用方，接线时评估（§8） |
| H3 | HIGH | `compute_variant_id` 回退路径静默吞异常 | 登记：随接线处理（§8） |
| M1-M3 | MEDIUM | 缺 golden 值测试 / 返回类型不一致 / nullable 变量命名误导 | 登记（§8） |
| L1-L2 | LOW | seed 范围未校验 / 缺 None 入参测试 | 登记（§8） |
| N1 | NIT | `import sys` 在 except 块内 | 登记（§8） |

### 3.2 PR-B2 协变量诊断 — REQUEST CHANGES → 已修复

| # | 严重度 | 问题 | 处置 |
|---|--------|------|------|
| C1 | CRITICAL | `cascade_predict.py` 的 `force_neutral` 覆盖路径重建 `HourlyResult` 时未转发诊断字段 → 诊断证据被静默抹除（`cov_effective` 归 0） | 转发 4 个诊断字段 |
| H1 | HIGH | 全 NaN 通道被计为"有效"（`np.all(arr==0)` 为 False、`std` 为 NaN 且 `NaN < 1e-12` 为 False） | 增加全 NaN 跳过 + 改用 `np.nanstd` |
| H2 | HIGH | `test_nan_values` 断言的正是 H1 的错误行为，会掩盖未来修复 | 重写断言 + 新增 `test_all_nan_channel_not_effective` |
| M1-M3 | MEDIUM | 四类互斥丢失信息 / 空 context 的 RuntimeWarning / 函数内惰性 import | 登记（§8） |
| L1-L2 | LOW | 测试随机性未固定 seed / baseline 路径未显式传 `last_covariate_input` | 登记（§8） |

### 3.3 PR-B3 `xreg_fallback` 贯通 — APPROVE WITH CHANGES → 已修复

| # | 严重度 | 问题 | 处置 |
|---|--------|------|------|
| H1 | HIGH | 旧 checkpoint 缺 `xreg_fallback` 键时 `p.get(..., False)` 默认 False → `summarize()` 报 count=0/rate=0.0，静默宣称"从未回退"而事实是"未知" | 改用 `None` 哨兵（与 `covariates_used` 既有处理一致）；`evaluator.build_summary` 同步去掉 0/0.0 兜底 |
| M1 | MEDIUM | 缺 `xreg_fallback_count/rate` 传播链专项测试 | 新增 `TestXregFallbackStats`（5 测试）：全回退/半数/全正常/缺键/混合缺键 |
| L1 | LOW | PR-B3 commit message 的 `not xreg_fallback` 公式已被 PR-B5 精化，文档漂移 | 不额外改动（`_covariates_used` docstring 已说明） |

**B3 与 Stage 1 Task 6 接线的关系（审核点名）:** 无冲突。Stage 1 的 `covariates_used` 走
`point → summarize → map_summary → build_summary`；PR-B3 在同一链路上**新增**两个统计字段，
不修改 `covariates_used` 的既有语义。PR-B5 随后把 `covariates_used` 的派生逻辑提取为
`_covariates_used()` 以排除 baseline 模式（见 §4.3）。

### 3.4 PR-B5 三路消融 — REQUEST CHANGES → 已修复

| # | 严重度 | 问题 | 处置 |
|---|--------|------|------|
| C1 | CRITICAL | resume 自我中毒：错误行不带 `ablation_mode`，读取侧归一为 `full` → 非 full 运行出过一个点级错误就**永远无法 resume** | 双侧修复：错误行写入补 `ablation_mode` + 读取侧只对非错误行计数模式 |
| H1 | HIGH | baseline 模式 `covariates_used=True`（`xreg_fallback` 为 False 但协变量未用）→ registry 元数据撒谎 | 提取 `_covariates_used()` 显式排除 baseline |
| H2 | HIGH | 审计集零覆盖 `energy_chem` 板块（ss→black_metals，其余全→agri） | 加入 `fu` + 新增板块覆盖断言 |
| M1 | MEDIUM | `rng.permutation` 多维语义含糊（1-D 逐通道独立打乱 vs 2-D 整行移动，不等价） | 显式 axis 0 写法 + docstring 注明 |
| L1-L2 | LOW | arg 错误 exit 0（调度误判成功）/ `--ablation-mode` 无值静默忽略 | 均改 `sys.exit(2)` |
| L4 | LOW | baseline 仍 fetch feedstock（白付 I/O） | 提前返回块上移 |
| N1-N2 | NIT | `last_covariate_input` 未初始化 / daily_slope 被打乱未说明 | 均已修 |
| L3 | LOW | resume 冲突检查在模型加载 (~800MB) 之后 | 登记（§8） |
| N3 | NIT | seed 硬编码 42 | 登记（§8） |

### 3.5 PR-B6 提案质量门 — REQUEST CHANGES → APPROVE（复评通过）

| # | 严重度 | 问题 | 处置 |
|---|--------|------|------|
| C1 | CRITICAL | **板块过滤器导致生产 100% 饿死**：实测 434/434 组合被拦（三板块各 ≥3 品种失败），与 2026-09-24 事故同构 | 改 circuit-breaker：仅当 `sector_map` 定义的**板块全集**失败才拦。实测拦截率 100% → 0% |
| H1 | HIGH | `_verdict_sort_key` ties 时取最旧裁决（`>` 比较，缺失 `decided_at` 时全为 `""`） | 改 `>=`，ties 取 jsonl 顺序最后（最新） |
| H2 | HIGH | `cov_recent_fail` -20 项在 `covariate_filter` 同条件下会先拦，可达窗口窄 | 已文档化 + `test_stale_pass_does_not_exempt_covariate_filter` 锁定窗口语义 |
| M1 | MEDIUM | 双重计数键名漂移（`quality_rejected` vs `quality_below_threshold`） | 对齐为 `quality_below_threshold` |
| L1 | LOW | 缺板块空裁决/单品种裁决测试 | 新增 2 个测试 |

**复评结论:** APPROVE。全部 CRITICAL/HIGH/MEDIUM/LOW 验证修复，生产实测拦截率 100% → 0%，
156 tests passed。

## 4. 关键设计决策

### 4.1 PR-B1 `variant_id` 不接线的裁定（审核阻断项 ③ 关联）

计划 PR-B1 步骤 2 要求把指纹嵌入 `variant_id`。**取证后决定不接线**：

| 证据 | 数值 |
|------|------|
| 生产裁决总数 | 143 |
| 其中 `variant_id` 为 `{symbol}_{cov}` 旧格式 | **143 / 143** |
| 其中带 A1 字段（`protocol_fingerprint` 等） | **0 / 143** |
| `pass_variants()` 返回条数 | **0** |

改 `variant_id` 格式会使 `dead_variants()` / `pass_variants()` / 新颖性判定全部落空 ——
已失败组合被当作新颖重新提案。且 Stage 1 已在 verdict 上落地 per-verdict 指纹字段，
承载同一"内容可比性"能力，无需在 `variant_id` 上重复编码。

**处置:** PR-B1 明确定位为**库实现**，接线留待 Stage 3（须先解决 64-bit 截断与回退吞异常）。

### 4.2 PR-B6 评分口径（v2 schema 限制）

计划中 `_proposal_quality_gate` 的 PF/IC 项与 `sector_filter` 的 `ev` 项**无法实现**：
143 条裁决全为 `fm.aligned_verdict.v2`，不含 `pf`/`ev`/`ic`（该三字段仅存在于已退役 v1 schema）。

**决策:** 评分与过滤一律基于 v2 可观测字段（`gate_pass` / `decided_at` / `cov_override` / `symbol`）。
评分项：`+5` 品种有过成功协变量 · `+3` 新颖性 · `+3` 机制完整 · `+10*plausibility` ·
`-20` 协变量跨品种 3 连败 · `-15` 品种 5 连败。

### 4.3 PR-B5/B6 交互: baseline 模式与 `covariates_used`

PR-B5 的 baseline 模式**主动**不传协变量（`xreg_fallback=False`，非回退）。若 `covariates_used`
仅由 `xreg_fallback` 派生，纯 TimesFM 基线会被错记为"用了协变量"。提取 `_covariates_used()`
显式排除 baseline。PR-B6 的 `sector` / `quality_score` 亦在同轮落地。

### 4.4 `symbol_has_pass` 语义张力裁定（审核阻断项 ③）

**审核意见:** 质量门用 `gate_pass` 真值，而 `pass_variants` 用更严的 v2 定义（含 `run_mode` 守卫）。
质量门可能放行一条 `run_mode=exploration` 但 `gate_pass=True` 的裁决作为"该品种有过成功协变量"的证据，
与 §1.4「探索运行不得出现在任何'已确认'表述中」冲突。

**裁定: 采纳审核意见，改为复用 `pass_variants` 的严格定义。**

```python
sym_pass = any(
    v.get("status", "ok") == "ok"
    and v.get("run_mode") in rl.RUN_MODES
    and v.get("run_mode") != "exploration"
    and v.get("gate_pass")
    and v.get("fdr_pass")
    and v.get("p_value") is not None
    and str(v.get("symbol") or "").lower().strip() == symbol
    for v in snap.values()
)
```

**后果（必须记录）:** 当前 registry 中 **0/143 条裁决带 `run_mode`**，因此
`symbol_has_pass` 的 `+5` 加分对**所有品种恒为 0**。语义上这是**正确的**
（确实不存在"已确认成功"），但门的行为因此改变：`+5` 项在当前数据上不可达，
提案分数整体下移 5 分。若未来要恢复该加分，须先产生 A1 完整的 confirmation 裁决（§7）。

## 5. 测试覆盖矩阵

| 模块 | 测试文件 | 测试数 |
|------|---------|-------|
| 指纹系统 | `test_fingerprint_lib.py` (33), `test_fingerprint_dedup.py` (12) | 45 |
| 协变量诊断 | `test_covariate_diagnostics.py` | 13 |
| 三路消融 | `test_ablation.py` (18), `test_ablation_integration.py` (28) | 46 |
| 提案质量门 | `test_proposal_quality_gate.py` (17), `test_sector_filter.py` (9), `test_covariate_filter.py` (7), `test_harvest_proposals.py` (32) | 65 |
| Stage 1 链路 | `test_phase1_integration.py` (14), `test_a1_completeness.py` (5), `test_nocov_baseline.py` (5) | 24 |
| 评估器 | `test_fm_evaluator_gated.py` | 36 |
| 监督环/注册表 | `test_supervisor.py` (61), `test_verdict_registry.py` (12), `test_praxist_fm_evaluator.py` (18) | 91 |
| **合计** | 16 文件 | **320** |

**回归执行口径:** 日常回归跑其中 14 个文件（不含 Stage 1 的两个专项文件）→ **310 PASS, 1 xfailed**；
含 Stage 1 两文件的全量为 **320**。上表数字由 `pytest --collect-only` 逐文件实测得出。

**关键回归保护:**
- `test_cold_start_not_blocked_by_quality_gates` — 空 snapshot 不得被新门挡住（防饿死重演）
- `test_partial_failure_does_not_block` — 板块部分失败不拦
- `test_predict_default_mode_is_full` — 默认 `ablation_mode=full` 行为不变
- `TestErrorRowsDoNotPoisonResume` — resume 不得被错误行毒化
- `TestCovariatesUsedFlag` — baseline 不得被记为使用协变量
- `TestXregFallbackStats` — 缺键报 None 而非 0

## 6. 生产数据实测

对生产 registry（143 条裁决，14 品种）运行完整门逻辑（PR-B6 复评独立复现）：

| 指标 | PR-B6 修复前 | 修复后 |
|------|------------|--------|
| sector 拦截率 | 434/434 (**100%**) | 0/434 (**0%**) |
| covariate 拦截率 | （未达） | 78/434 (18.0%) |
| quality 拦截率 | （未达） | 82/434 (18.9%) |
| **通过率** | **0%** | **274/434 (63.1%)** |

## 7. 重要发现: registry 为 pre-A1 遗留数据（本轮新增）

评审期间取证发现，**超出 Stage 2 范围但影响结论解释力**：

| 事实 | 数值 |
|------|------|
| 裁决总数 | 143 |
| 缺失全部 18 个 A1 字段的裁决 | **143 / 143** |
| `pass_variants()` 返回 | **0** |
| `gate_pass=True` 的裁决 | 42（但均因 A1 不完整不可晋升） |
| `run_mode` 存在条数 | **0** |

**根因（已排除接线断点）:**

| 事件 | 时间 |
|------|------|
| 最后一条裁决写入 | 2026-09-24 **06:25:39** |
| registry 文件 mtime | 2026-09-24 **06:25:40** |
| 三环 SIGTERM 封存 | 2026-09-24 **14:22** |
| Stage 1 A1 接线 commit (`35faef0` / `a038f76`) | 2026-09-27（封存后 **3 天**）|

registry 在 A1 接线落地前 3 天即冻结 —— **不可能有任何裁决带 A1 字段**。
这不是接线断点，而是"接线从未在生产跑过"。

**接线本身静态完整:** `build_summary` 显式写入全部 18 个 `A1_REQUIRED_FIELDS`，无遗漏；
`test_a1_completeness.py` (5) 与 `test_phase1_integration.py::TestA1GuardIsWired` 覆盖该守卫。

**影响:**
1. 当前不存在任何"经统计晋升"的裁决（与 2026-09-24 审计记录的「0 条经统计晋升」一致）
2. §4.4 的 `symbol_has_pass` 恒为 0 是**语义正确**的结果
3. PR-B6 的 63.1% 通过率是**质量门评分**通过率，非 `pass_variants` 晋升率 —— 两者口径不同
4. 要产生 A1 完整裁决，须重启三环（Stage 3 / 复活后）

## 8. 已知后续

| 项 | 来源 | 说明 |
|---|------|------|
| **PR-B4 dir_acc 口径变更** | 计划偏移 | 影响面过大。**须在 Stage 3 计划中正式改档** |
| **审计集变更** | PR-B5 评审 H2 | 审计集加入 `fu` 触及 §4.2 W2.3「固定审计集」的"固定"语义。**须在 Stage 3 spec 补裁定记录** |
| PR-B1 接线 | PR-B1 评审 C1 | `variant_id` 接线 + 64-bit 截断评估 + 回退吞异常处理 |
| PR-B1 其他 | PR-B1 评审 | golden 值测试 / 返回类型一致性 / nullable 命名 / seed 范围 / `sys` import 位置 |
| PR-B2 其他 | PR-B2 评审 | 四类互斥丢失信息 / 空 context RuntimeWarning / 惰性 import / 测试 seed |
| PR-B5 L3/N3 | PR-B5 评审 | resume 检查位置（模型加载后）/ `predict()` seed 参数 |
| registry 复活 | §7 | 需重启三环产生 A1 完整裁决，方能验证 Stage 1 接线与恢复 `symbol_has_pass` |
| 板块部分退化预警 | PR-B6 评审 | `n_failed >= sector_size * 0.5` 时 WARN |

## 9. 结论

**Stage 2 全部 5 个 PR 已完成并经专家评审 + 修复。出口核验：有条件通过。**

| PR | 首轮评审 | 修复后 |
|----|---------|-------|
| B1 | REQUEST CHANGES (2 CRITICAL) | 命名冲突 + 权重哈希已修；接线按决策重定性 |
| B2 | REQUEST CHANGES (1 CRITICAL) | 诊断转发 + NaN 已修 |
| B3 | APPROVE WITH CHANGES (1 HIGH) | 缺键 None 哨兵 + 5 测试已补 |
| B5 | REQUEST CHANGES (1 CRITICAL) | resume 自我中毒 + 元数据撒谎 + 审计集已修 |
| B6 | REQUEST CHANGES (1 CRITICAL) | 100% 饿死已修，**复评 APPROVE** |

测试 320 用例 / 16 文件全绿（回归 310 PASS / 1 xfailed）；
生产实测门通过率 63.1%（修复前 0%），无饿死风险。

### 9.1 通过条件（降级声明，必须随批准一并生效）

> **Stage 1 硬门 2/3 的闭合目前仅为「代码 + 测试层闭合」，非「生产层闭合」。**
>
> 依据 §7：registry 冻结于 2026-09-24 06:25，Stage 1 A1 接线落于 2026-09-27（封存后 3 天），
> **接线从未在生产运行过**。143/143 裁决缺全部 A1 字段，`pass_variants` 返回 0。
>
> 因此「过门具备证据含义」这一阶段使命，当前只兑现了**施工图**，未兑现**实证**。
>
> ⚠️ **不得以「320 tests」或「63.1%」掩盖此事实**：
> - 320 tests 证明的是**代码正确性**，非生产有效性
> - 63.1% 是**质量门评分**通过率，**不是** `pass_variants` 晋升率（§7 影响第 3 条）

#### 解除条件（v4 修订 — 修正循环依赖）

> **v2 原写法**: 「registry 复活并产出第一批 A1 完整的 **confirmation** 裁决之前，本条件不解除」
>
> **该条件循环依赖，不可达成**: `pass_variants()` 显式排除 `run_mode == "exploration"`
> （`registry_lib.py:456`），而 `build_summary` 默认 `run_mode="exploration"`
> （`evaluator.py:318`），生产路径均不传 `run_mode` → 生产裁决**全部是 exploration**
> （Stage 1 报告 §5 自述「这是设计意图」）。要产出 confirmation 裁决须有已锁定
> `prereg_id`（spec §1.4），而 prereg 是 **PR-D1（阶段 4）** 的交付物。
> 即：解除条件依赖阶段 4 机制 → 在阶段 3 内永不解除。

**修订后的解除条件（两层，均可于阶段 3 达成）:**

| 层 | 条件 | 达成任务 |
|----|------|---------|
| **接线层** | 判据 A: 新增裁决 A1 字段非空 + `a1_missing_fields()` 为空 + `run_mode` 合法 + `dm_status`/`pair_set_hash` 有值 | Stage 3 计划 T1a |
| **统计层** | 判据 B': 至少 1 条裁决 `pairing_valid=True` 且 `p_value` 非 None | Stage 3 计划 T1a（依赖 PR-A1） |

**「过门具备证据含义」（判据 C: `pass_variants() > 0`）属阶段 4 属性**，
由 spec §1.4 的 confirmation/prereg 设计决定，**不作为 Stage 1/2 降级声明的解除条件**。

详见 Stage 3 计划 `docs/superpowers/plans/2026-09-28-covariate-credibility-stage3.md` §T1a。

### 9.2 Stage 3 优先级重排（依审核裁定）

registry 复活**从「已知后续」升格为 Stage 3 第一优先级**，先于 PR-B4 改档与 PR-B1 接线。

**理由:** 接线在死数据上验证没有意义。新的 A1 裁决流才是验证 Stage 1 全链路的最小实证；
在它产生之前，PR-B1 接线与 PR-B4 口径变更都缺少可验证的判据。

### 9.3 Stage 3 计划必须收录的五项待办

| # | 待办 | 来源 | 优先级 |
|---|------|------|-------|
| 1 | **registry 复活三环**（产出首批 A1 完整 confirmation 裁决） | §7 / §8 | **P0 — 第一优先** |
| 2 | PR-B4 dir_acc 口径变更改档 | 计划偏移 | P1 |
| 3 | 审计集加入 `fu` 的裁定记录（触及 §4.2 W2.3「固定审计集」语义） | PR-B5 评审 H2 | P1 |
| 4 | PR-B1 接线（含 64-bit 截断评估 + 回退吞异常处理） | PR-B1 评审 C1/H2/H3 | P2 |
| 5 | 板块部分退化 WARN（`n_failed >= sector_size * 0.5`） | PR-B6 评审 | P2 |

**另需在 Stage 3 计划中明确 D5 裁定状态对 PR-A1 解冻的影响**（见 §9.4）。

### 9.4 遗留阻断：D5 阻断 PR-A1（Stage 1 硬门 1 未闭合）

Stage 1 硬门 1（因果与对齐）的 **cutoff 语义部分受 D5 裁定阻断，未闭合**。
PR-A1（cutoff 语义 + checkpoint 键）落地后须：
1. 重新生成全部 nocov 基线
2. 重跑 DM 配对验证

**该项与 §7 的 registry 复活存在依赖**：PR-A1 落地会改变 cutoff 语义 →
已有基线失效 → 须与三环复活一并规划，否则复活后产出的裁决仍建立在待变更的 cutoff 语义上。

**下一审核节点:** Stage 3 计划的批准评审（重点：§9.3 五项是否全数收录、优先级排序、
D5 对 PR-A1 解冻的影响）。

