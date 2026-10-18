# Laya 预筛中文泄漏修复 Changelog

**日期**：2026-10-18
**状态**：✅ 完成（全部 7 Task 审核通过）
**Spec**：`docs/superpowers/specs/2026-10-18-laya-chinese-leak-fix-spec.md`（v3，Approved/Frozen）
**Plan**：`docs/superpowers/plans/2026-10-18-laya-chinese-leak-fix-implementation.md`
**审核**：3 轮 spec 审核 + 3 轮 plan 审核 + 每个 task 独立 code-reviewer

---

## 问题

Laya 预筛 `_build_state()` 将 `predicted_direction` 原样传入 state，25%（1796/7194）提案含中文字符（括号注释），导致：
- Laya 推理时间不稳定（接近 60s 超时边界）
- 可能路由到 multilingual 模型（~3x 性能开销）
- 预筛质量不一致

## 根因

Jev→Laya 迁移后三轮"打地鼠"式修复（`a134dac` → `5f1d17a` → `2c36e6c`）：
1. instructions/criteria 英文化
2. state 白名单过滤（去 mechanism/symbol_fit 等长中文）
3. sector/contract_details 英文化

但 `predicted_direction` 被错误归类为"安全字段"（prompt 示例是纯英文），未做中文过滤。

## 修复方案：两条腿走路

### Phase 1：下游止血（4 commits）

**Commit 1** — `0aa0fce`：核心函数
- 新增 `_strip_chinese()`：双道剥离（CJK 汉字+标点 → 空格 → 全角标点 → 空格 → 合并空白 → strip）
- 新增 `_is_shell_pd()`：空壳检测（阈值=12，对齐实测 ~496 空壳 27.6%）
- 正则常量：`_ZH`（CJK）、`_FULLWIDTH_PUNCT`（全角标点）、`_PD_MIN_LEN=12`
- 6 个单元测试

**Commit 2** — `813d374`：集成
- `_build_state()` 过滤 `predicted_direction` + 空壳回退为空串
- state 添加 `language: "en"`（best-effort）
- 处理显式 null：`proposal.get("predicted_direction") or ""`
- 6 个集成测试（含短公式空壳 `RSI(6)>80 超买 -> short`）

**Commit 3** — `ccc0e9d`：HTTP 层
- `_call_laya()` payload 顶层添加 `language: "en"`
- 超时签名统一：30s → 60s
- 2 个测试

**Commit 4** — `1ff4c7f` + `e82086a`：门禁脚本
- `scripts/check_pd_chinese.py`：扫描所有 proposals，验证 0 东亚宽字符
- 结果：8459 scanned, 44 skipped, 0 violations ✅

### Phase 2：去重（1 commit）

**Commit 5** — `ca636e7`：
- `process_proposal()` 在 `extract_proposal_fields` 后、`prescreen_and_save` 前检查 `existing`
- 命中则 `stats.inc("skipped")` + `return "skipped"`，不调用 Laya
- 不扩 `PrescreenStatus` 枚举（Frozen lifecycle §71/§422）
- 2 个测试（mock 路径正确：`cascade.typesafe_prescreen.prescreen_and_save`）

### Phase 3：源头约束（1 commit）

**Commit 6** — `71c7146`：
- `task_FM/prompt_base.jinja2` L65：`predicted_direction: English only. No Chinese annotations`
- 含格式示例：`"condition -> action"`
- Jinja 语法验证通过

---

## 关键设计决策

| 决策 | 理由 |
|------|------|
| 双道剥离（CJK + 全角标点）| v2 收窄正则去掉全角区后 369 条全角标点残留；v3 二次清洗解决 |
| 空壳阈值=12 | 实测：阈值=8 仅 247 空壳（漏判典型 `"-> long, -> short"` len=9）；阈值=12 对齐 ~496 |
| 不扩 `PrescreenStatus` | 与 Frozen lifecycle spec §71/§422 冲突；用 skip + 不写 prescreen.json 替代 |
| `language: en` best-effort | 未证实 Laya 服务端识别；不与成功率验收强绑 |
| `or ""` 处理 null | 比 `get(..., "")` 更防御（处理 JSON 显式 null） |

## 测试覆盖

| 测试文件 | 数量 | 覆盖 |
|----------|------|------|
| `tests/test_strip_chinese.py` | 6 | 基础/混合/全角/ASCII/空/纯中文 |
| `tests/test_build_state_no_cjk.py` | 8 | CJK 剥离/空壳/短公式/language/字段保留/null |
| `tests/test_backfill_dedup.py` | 2 | 跳过已有/不跳过新 |
| **总计** | **16** | 全通过 ✅ |

## 验收结果

| 指标 | 目标 | 实际 |
|------|------|------|
| 东亚宽字符残留 | 0 | 0 ✅ |
| 提案扫描数 | 动态 | 8459 (44 skipped) ✅ |
| 测试通过率 | 100% | 16/16 ✅ |
| Code review | 全 PASS | 7/7 ✅ |

## 不做的事

- ❌ 翻译 API（YAGNI）
- ❌ 通用中文字段检测器（过度抽象）
- ❌ `kill_condition`/`promote_condition` 英文化（不进 Laya）
- ❌ 扩 `PrescreenStatus` 加 `duplicate`（Frozen lifecycle 冲突）

## 后续

- 等下一代 peer 重跑后，prompt English only 约束生效，新生成 proposal 不再有中文 `predicted_direction`
- 已有 1796 条中文 PD 提案由下游 `_strip_chinese()` 处理
- GitHub origin push 失败（token 过期），需手动更新；备份机已同步

---

**Co-Authored-By**：Claude Code <noreply@anthropic.com>
