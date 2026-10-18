# Laya 中文泄漏修复 Implementation Plan 审核（三审）

- 审核对象：`/home/abug/timesfm/docs/superpowers/plans/2026-10-18-laya-chinese-leak-fix-implementation.md`（837 行，mtime 2026-10-18 13:36 Asia/Shanghai）
- 对照 SPEC（三审 **通过**）：`…/specs/2026-10-18-laya-chinese-leak-fix-spec.md`
- 对照再审：同目录 `…-implementation-audit.md`（有条件通过，3×P0 **仍未闭合**）
- 代码根：WSL `/home/abug/timesfm`（machine `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`）
- 日期：2026-10-18（Asia/Shanghai）
- 轮次：**三审**
- 结论：**通过**——再审列出的 3 处 P0 **全部闭合**（本机按计划伪代码实算 + grep 现网 API）。Phase 1 Task 1–5 可安全开 TDD；残留为 P1/P2，不挡开工。

---

## 0. 总评

| 维度 | 判定 | 摘要 |
|------|------|------|
| 再审 P0 闭合 | **全闭合** | P0-1 / P0-2 / P0-3 断言与 API 已与实算 / 现网一致 |
| vs SPEC Phase 覆盖 | 强 | Task 1–5 ≈ Phase 1；Task 6 ≈ Phase 2；Task 7 ≈ Phase 3 |
| SPEC 关键决策对齐 | **强** | `_PD_MIN_LEN=12`、双道字符类、空壳→`""`、不扩 PrescreenStatus、`language` best-effort、timeout 30→60 |
| 测试/门禁可执行性 | **强（Phase 1）** | Task 1–2 期望串/边界与实算一致；可开 TDD |
| 回滚 | 中偏强 | 每 Task 一 commit（Global 已写明） |

---

## 1. 再审 P0 闭合核验（实算 + 代码）

算法与计划 Step 3 / SPEC 伪代码一致：

```python
_ZH = re.compile(r"[\u4e00-\u9fff\u3000-\u303f]+")
_FULLWIDTH_PUNCT = re.compile(r"[！-／：-＠［-＿｛-･]+")
# strip: ZH→空格 → FW→空格 → collapse → .strip(" (;,)")
# shell: core = re.sub(r"[->,;|()+\s]", "", stripped); len(core) < 12
```

### P0-1 Task 1 期望串 vs `.strip(" (;,)")` —— **已闭合**

| 输入 | 计划断言（三审稿） | 本机实算 |
|------|-------------------|----------|
| `价差加速度转正 -> long` | `"-> long"` | `"-> long"` ✅ |
| `价差（利润） -> long` | `"-> long"` | `"-> long"` ✅ |
| `seasonal_supply_peak(7-9月出栏高峰) -> short` | `"seasonal_supply_peak(7-9 ) -> short"`（`)` 前空格） | 同左 ✅ |
| `RSI(6)>80 超买 -> short` | `"RSI(6)>80 -> short"` | 同左 ✅ |

Review Focus §2 亦改为 `"-> long"`（无前导空格）。全文无 `== " -> long"` 断言；`_build_variant_id` 出现次数 = **0**。

### P0-2 Task 2 阈值边界算术 —— **已闭合**

| 输入 | 计划期望 | 实算 core / len / shell(<12) |
|------|----------|------------------------------|
| `-> long, -> short` | True；注释 core=`longshort` **len=9** | `longshort` / 9 / True ✅ |
| `RSI(6)>80 -> short` | True；core=`RSI680short` len=11 | 同左 ✅ |
| `oi_up_with_price -> long` | False；core=`oi_up_with_pricelong` **len=20** | 同左 ✅ |
| `abcdefghijk` | True（len=11） | True ✅ |
| `abcdefghijkl` | False（len=12） | False ✅ |
| `abcdefghijklm` | False（len=13） | False ✅ |

再审稿的坏例 `abcdefghijk -> long`（实 core len=15→False）与伪造 `abcdefghiklong` **已删除**，改为纯字母边界串。

### P0-3 Task 6 伪 API —— **已闭合**

| 项 | 计划（三审稿） | 现网 `scripts/backfill_prescreen.py` |
|----|----------------|--------------------------------------|
| 函数 | `process_proposal(...)` 七参 | L298–300：`(proposal_path, stats, verdict_history, covariate_menu, queue_path, dead, existing)` ✅ |
| vid | `generate_variant_id(symbol, cov_override)` | L202：同签名；依赖 cov_family + experiment_fingerprint + `sup_evidence` ✅ |
| 虚构 | `_build_variant_id` | **计划中 0 次**；代码中亦不存在 ✅ |
| 去重点 | `extract_proposal_fields` 成功后、`prescreen_and_save` 前查 `existing` | 与再审改法一致；`Stats.inc("skipped")` 已有 |

测试伪代码传入完整七参 + mock `extract_proposal_fields` / `generate_variant_id`。

---

## 2. SPEC 决策对齐（无回归）

| SPEC 决策 | Plan | 状态 |
|-----------|------|------|
| `_PD_MIN_LEN = 12` | Global + Task 2 | ✅ |
| `_ZH` + `_FULLWIDTH_PUNCT` 二次清洗 | Task 1 伪代码与 SPEC 同字符类 | ✅ |
| 空壳 → `""` | Task 2–3 | ✅ |
| 不扩 `PrescreenStatus` | 全文无 `duplicate` 枚举扩展 | ✅ |
| `language: en` best-effort | Task 3–4 | ✅ |
| timeout 30→60 | Task 4 改签名默认；现网 `_prescreen_impl` 已 `timeout=60.0`（L375） | ✅ |
| harvest 去重标 Phase 2b / 不在本 plan | Task 6 仅 backfill | ✅ |
| 门禁扫 experiments proposals | Task 5 `check_pd_chinese.py` | ✅ |

---

## 3. 残留（非门禁）

### P1（Phase 2 / Task 6 实施时注意）

1. **mock 路径**：现网 `prescreen_and_save` 在 `process_proposal` **函数体内** `from cascade.typesafe_prescreen import …`。`patch("scripts.backfill_prescreen.prescreen_and_save")` 可能打空；实施时应 patch `cascade.typesafe_prescreen.prescreen_and_save`，或改成本地 import 后再测。
2. **`test_backfill_does_not_skip_new_variant`**：mock 返回 `success` 后现网还会再调 `generate_variant_id` 并走入队写 queue；计划写「入队不测」，但未 mock 入队副作用——应用更窄断言（只 assert `prescreen_and_save` 被调）并 mock/截断后续，或返回非 success 状态避免写盘。

### P2（刮词）

1. Task 3 注释仍写 `strip 后 " -> long, -> short"`（前导空格）；实算终态为 `"-> long, -> short"`。**断言 `pd == ""` 正确**，仅注释刮词。
2. Task 4：`_call_laya` 默认仍 30，调用点已 60——计划统一默认值合理；实施时 Read 现 payload/`questions` 再 Edit，勿整段替换掉现网结构。

---

## 4. 结论与开工建议

**通过。** 可按 Task 1→5 开 Phase 1 TDD，不必再改计划才能进 Task 1。

- Phase 1（Task 1–5）：立即开工
- Phase 2（Task 6）：开工前按上节 P1 修正 mock 路径/入队副作用即可，非本轮门禁

本审核**未修改** plan / spec；**未**释放本机锁（由总管释放）。
