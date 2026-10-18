# Laya 预筛中文泄漏修复 Changelog 审核

- 审核对象：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-18-laya-chinese-leak-fix-changelog.md`（112 行，mtime 2026-10-18 15:41 Asia/Shanghai）
- 对照 SPEC（三审 **通过**）：`…/specs/2026-10-18-laya-chinese-leak-fix-spec.md`（v3 Frozen）
- 对照 Plan（三审 **通过**）：`…/plans/2026-10-18-laya-chinese-leak-fix-implementation.md`
- 对照前审：同目录 / box `…-spec-audit.md`、`…-implementation-audit.md`
- 代码根：WSL `/home/abug/timesfm`（machine `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`）
- 日期：2026-10-18（Asia/Shanghai）
- 结论：**有条件通过**——Phase 1–3 实码与 named commits 均在、门禁/测试/关键常量可复现；开「changelog 定稿」前建议短改 2 处 P1（Task 2 单测缺口表述、「全部 7 Task」过满），P2 刮词不挡接收。

---

## 0. 总评

| 维度 | 判定 | 摘要 |
|------|------|------|
| Claims vs 代码证据 | **强** | `_PD_MIN_LEN=12`、双道 `_ZH`/`_FULLWIDTH_PUNCT`、空壳→`""`、`language:en`、PrescreenStatus 未扩、timeout=60、backfill skip、prompt L65 均在 HEAD |
| Named commits | **全真** | `0aa0fce`/`813d374`/`ccc0e9d`/`1ff4c7f`/`e82086a`/`ca636e7`/`71c7146`（+ docs `f2a9a7f`）均存在且触达声称文件 |
| 完整性 vs SPEC Phase | **强（功能）** | Phase1 止血 + Phase2 backfill 去重 + Phase3 prompt；harvest Phase 2b 按 SPEC 可选，本期未做 |
| 完整性 vs Plan Task | **中偏强** | Task 1/3/4/5/6/7 有对应交付；**Task 2 计划内 `_is_shell_pd` 单测未落文件**（函数在 Commit1，仅靠集成测间接覆盖） |
| 指标可复现 | **强** | 门禁 `8459 scanned, 44 skipped, 0 violations` 本机重跑一致；空壳 `496/1796=27.6%` 一致；`16 passed` |
| 风险/回滚/后续 | **中** | 「不做的事」对齐 SPEC §7；**缺 SPEC §8 回滚摘要**；harvest 2b 未写入后续/不做 |
| 过满/漏报 | **有 P1** | 「全部 7 Task 审核通过」相对 Plan Task2 单测缺口过满；Commit2「6 个集成测试」与表「8」略打架 |

---

## 1. Claims vs 代码证据（逐项）

| Changelog 声明 | 证据 | 判定 |
|----------------|------|------|
| `_strip_chinese` 双道剥离 | `cascade/typesafe_prescreen.py` L36–54：`_ZH` + `_FULLWIDTH_PUNCT` → 空白 → `re.sub` → `.strip(" (;,)")` | ✅ |
| `_is_shell_pd` 阈值=12 | L38 `_PD_MIN_LEN = 12`；L57–66 `re.sub(r"[->,;|()+\s]", …)` | ✅ |
| `_build_state` 滤 PD + 空壳→`""` + `or ""` | L300–314：`raw_pd = proposal.get(...) or ""`；`final_pd = "" if _is_shell_pd(...)` | ✅ |
| state / payload `language: "en"` | L314、L338 | ✅ |
| PrescreenStatus 未扩 | L32 `Literal["success","degraded","error"]`；无 `duplicate` | ✅ |
| `_call_laya` timeout 60s | 签名默认 `60.0`；调用处 `timeout=60.0` | ✅ |
| `check_pd_chinese.py` 0 违规 | 本机重跑：`Scanned 8459 proposals (44 skipped), 0 violations` | ✅ |
| backfill `existing` → `skipped` 不调 Laya | `scripts/backfill_prescreen.py` L316–318；测 mock `cascade.typesafe_prescreen.prescreen_and_save` | ✅ |
| prompt English only | `task_FM/prompt_base.jinja2` L65 | ✅ |
| 根因三 commit `a134dac`→`5f1d17a`→`2c36e6c` | 三 hash 均存在，subject 与 changelog 叙述一致 | ✅ |
| 25%（1796/7194） | 本机：CJK PD 仍 **1796**；分母库已增至 readable≈8461（≈21.2%）。**1796 仍准**；7194 为 SPEC 冻结时分母，changelog 作问题陈述可接受 | ✅（注明分母已漂移） |
| ~496 空壳 27.6% | 本机双道 strip + thr12：**496 / 1796 = 27.6%** | ✅ |
| 16/16 测试 | `.venv/bin/pytest` 三文件 **16 passed** | ✅ |
| origin push 失败 / ahead | `git status`：`master...origin/master [ahead 20]`，与「需手动更新」一致 | ✅ |

**路径注意**：实现落在仓库根 `cascade/typesafe_prescreen.py`（非 `experiments/cascade/`），与 commits/计划一致；changelog 未写错路径。

---

## 2. 完整性：SPEC Phase / Plan Task

| SPEC | Plan | Changelog | 实码 | 判定 |
|------|------|-----------|------|------|
| §3.1 Phase1 下游止血 | Task 1–5 | Commit 1–4 | 函数+集成+门禁 | ✅ |
| §3.3 Phase2 去重（backfill） | Task 6 | Commit 5 `ca636e7` | `process_proposal` pre-check | ✅ |
| §3.3 harvest Phase 2b（可选） | 未强制 | **未提** | `sup_harvest` 未改 | ⚠ P2 漏写 deferred |
| §3.2 Phase3 prompt | Task 7 | Commit 6 `71c7146` | L65 English only | ✅ |
| §3.4 超时统一 | Task 4 | 记在 Commit 3 | 60s | ✅ |
| §7 不做（翻译 API / 通用检测器 / kill·promote / 扩枚举） | — | 「不做的事」四条 | 对齐 | ✅ |
| §8 回滚 | — | **无专节** | revert 路径仍可用但未文档化 | ⚠ P1 |
| Plan Task 2 `_is_shell_pd` **单测**（typical/short/valid/boundary/empty → 计划期望 strip 文件合计 12） | Task 2 | Commit1 仅写「6 个单元测试」（实为 strip） | `test_strip_chinese.py` **无** `test_is_shell_*`；仅 `test_build_state_shell_*` / `short_formula` 间接覆盖 | ⚠ **P1** |

手动冒烟（非 pytest）：计划 Task2 断言（`longshort` / `RSI680short` / `abcdefghijk` 边界 / 有效 PD）在解释器下 **全部成立**——**实现正确，单测缺口是文档/覆盖问题，非算法回归**。

---

## 3. 指标核验

| 指标 | Changelog | 本机（2026-10-18） | 判定 |
|------|-----------|-------------------|------|
| 门禁扫描 | 8459 / 44 skip / 0 viol | **同文** | ✅ |
| 测试 | 16/16 | **16 passed** | ✅ |
| 空壳 thr12 | ~496 / 27.6% | **496 / 27.6%** | ✅ |
| CJK PD 条数 | 1796（问题节） | **1796** | ✅ |
| 分母 7194 | 问题节 25% | 现库 proposal≈8503、readable≈8461 → 21.2% | ⚠ 历史分母，建议脚注「SPEC 冻结时」 |
| Commit2「6 集成」vs 表「8」 | 冲突 | 文件现 8（含 Commit3 的 `_call_laya` 2 测） | ⚠ P2 刮词 |

---

## 4. 残留风险 / 后续准确性

| 项 | Changelog | 评审 |
|----|-----------|------|
| 新 peer 后源头 English only 生效 | 「后续」有 | ✅ 合理 |
| 存量 1796 靠下游 strip | 有 | ✅ |
| GitHub push / 备份机 | 有 | ✅ 与 ahead 20 一致 |
| harvest 仍可能对已注册 vid 调 Laya | **未写** | ⚠ SPEC 明确 Phase 2b；建议补进「后续」或「不做」 |
| `language:en` 无服务端保证 | 关键决策表有 | ✅ |
| 短公式空壳误杀（如 RSI…） | 未作风险 | 与 SPEC 风险表一致属已知取舍；可不改 |
| 回滚 | **缺** | 建议补一行：Phase1–3 各可独立 `git revert` named commits |

---

## 5. 问题清单

### P1（定稿前建议改 changelog 正文；非要求改代码）

1. **「全部 7 Task 审核通过」过满**  
   Plan Task 2 要求在 `tests/test_strip_chinese.py` 追加 `_is_shell_pd` 单测（typical / short_formula / valid / boundary / empty）。HEAD 仅有 strip 6 测 + build_state 侧 2 个集成空壳测，**计划内 Task2 单测未落**。建议改为：「7 Task 功能交付；Task2 空壳单测并入 Task3 集成覆盖（计划内独立单测未单列 commit）」——或补测后再写「全 Task 测试按计划」。

2. **缺 SPEC §8 回滚摘要**  
   至少列出 Phase1（`0aa0fce`…`e82086a`）、Phase2（`ca636e7`）、Phase3（`71c7146`）可独立 revert，且 strip 与 prompt 互不绑定。

### P2（刮词 / 可选）

1. Commit2 子弹「6 个集成测试」→ 与验收表「8」及 Commit3 追加 2 测不一致；改为「Commit2 落地 6，Commit3 追加 2，文件合计 8」。
2. 问题节 `1796/7194` 加脚注：冻结时分母；现库已增，CJK 条数仍 1796。
3. 「后续/不做」补一句：`sup_harvest._prescreen_async` 去重 = SPEC Phase 2b，本期 out-of-scope。

### 无 P0

未发现：虚构 commit、门禁数字造假、声称扩了 PrescreenStatus、声称 harvest 已改、关键常量与 Frozen SPEC 冲突。

---

## 6. 建议定稿补丁（仅 changelog，本审不改）

1. 状态行：将「全部 7 Task 审核通过」改为「Phase1–3 功能完成；测试 16/16；Task2 空壳以集成测覆盖（计划单测未单列）」。
2. 增「回滚」小节（3 行 named commits）。
3. 「后续」补 harvest Phase 2b。
4. （可选）修 Commit2「6」刮词 + 7194 脚注。

---

## 7. 结论

**有条件通过**——changelog 作为「已落地变更记录」整体可信：commits 真、常量/契约对齐 Frozen SPEC、门禁与 16 测本机可复现、未发明交付。阻断定稿的不是造假，而是 **Task2 单测缺口被「全部 7 Task」一笔抹平**，以及 **回滚/harvest-2b 文档空洞**。按 §6 短改后可升为 **通过**；**不要求为定稿重开 Phase1 编码**（除非团队坚持补齐 Task2 单测后再改措辞）。
