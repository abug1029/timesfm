# Laya 预筛中文泄漏修复 Spec

> **状态**：Approved/Frozen · v3（post-audit-3 2026-10-18）
> **优先级**：P1（性能 + 稳定性）
> **影响面**：cascade/typesafe_prescreen.py, task_FM/prompt_base.jinja2, scripts/backfill_prescreen.py
> **前置依赖**：lifecycle spec `2026-10-18-proposal-lifecycle-management-spec.md`（Frozen，不扩 PrescreenStatus 枚举）
> **审核记录**：`2026-10-18-laya-chinese-leak-fix-spec-audit.md`（初审 + 再审）

---

## 1. 问题定义

### 1.1 现象

Laya 预筛（`_call_laya`）在 25% 的提案上收到含中文的 state payload，导致：
- 推理时间不稳定（部分请求接近 60s 超时边界）
- Laya 路由到 multilingual 模型而非 english 模型（性能开销 ~3x）
- 无法保证预筛质量一致性

### 1.2 数据

| 指标 | 值 |
|------|-----|
| 总提案数 | 7194 |
| `predicted_direction` 含中文 | 1796（24.97%） |
| 其他字段（proposal_id/symbol/cov_override/covariate_family）含中文 | 0 |
| Laya 当前超时 | 60s |
| 历史超时记录 | 5 次（10-17 迁移初期），现已降至 0 |
| strip 后空壳率 | ~496/1796（27.6%），阈值=12，双道 strip 后近空壳需回退处理 |

> **v3 修订**：空壳率从 ~487（27.1%，阈值=8）修正为 ~496（27.6%，阈值=12，双道 strip 后实测）。再审实测发现阈值=8 时仅 247 条空壳（13.8%），典型空壳 `"-> long, -> short"` 的 core="longshort" 长度 9，阈值 8 系统性漏判。调至 12 对齐实测；加上 `_FULLWIDTH_PUNCT` 二次清洗后空壳略升至 ~496。

### 1.3 影响范围

- **Laya 服务端**：中文 token 导致推理时间膨胀
- **backfill_prescreen.py**：5 worker 并发，中文提案拖慢整批
- **sup_harvest.py**：daemon thread fire-and-forget，超时不影响主流程但浪费算力

> **v2 修订**：原 §1.3 声称"人类可读性：preregistry.jsonl 含中文"——**下游 `_strip_chinese` 不改 JSONL 原文**，可读性仅 Phase 3 新提案改善。主脏数据源为 `task_FM/experiments/run_*/results/**/proposals/*.json`（7194 条），非 preregistry.jsonl（仅 2 行）。已修正。

---

## 2. 根因分析

### 2.1 历史修复时间线

Jev→Laya 迁移（10-14）后发现中文导致超时，进行了三轮"打地鼠"式修复：

| Commit | 时间 | 改动 | 方法 |
|--------|------|------|------|
| `a134dac` | 10-17 11:47 | instructions/criteria 英文化 | 翻译 prompt 模板 |
| `5f1d17a` | 10-17 17:07 | state 白名单过滤 | 从 `"proposal": proposal` 改为 5 字段白名单 |
| `2c36e6c` | 10-17 17:20 | sector/contract_details 英文化 | 用英文映射替换 SECTOR_NAMES |

**共同动机**：解决 Laya 超时（>60s），不是语言净化。方法论是"超了再砍"，没有系统性扫描。

### 2.2 遗漏原因

**predicted_direction 被错误地归类为"安全字段"**：

1. prompt 示例是纯英文：`"oi_up_with_price -> long"`
2. 字段名像代码公式，不像自然语言
3. 开发者未对 7194 条真实 proposal 做中文 grep 验证
4. predicted_direction 字符串短（50-150 字），混合中文后不会像长文本那样爆超时，无反馈信号驱动修复

### 2.3 当前代码逻辑（`_build_state()` L255-282）

```python
proposal_summary = {
    "proposal_id": proposal.get("proposal_id", ""),           # ✅ 纯 ASCII
    "symbol": proposal.get("symbol", symbol),                 # ✅ 纯 ASCII
    "cov_override": proposal.get("cov_override", ""),         # ✅ 纯 ASCII
    "covariate_family": proposal.get("covariate_family", ""), # ✅ 纯 ASCII
    "predicted_direction": proposal.get("predicted_direction", ""), # ❌ 25% 含中文
}
```

**被过滤掉的字段（有中文）**：
- `mechanism`：peer 写的 ≥40 字中文机制描述
- `symbol_fit`：中文品种适配说明
- `kill_condition`：中文放弃条件
- `promote_condition`：中文过门条件
- `covariate_menu`：整块砍掉（含中文菜单）
- `recent_verdicts_summary`：整块砍掉（含中文历史）

### 2.4 中文 predicted_direction 来源

peer LLM agent（Claude/qwen 中文模型）生成 proposal 时，在 predicted_direction 中夹带中文括号注释：

```
"seasonal_supply_peak(7-9月出栏高峰) -> short; seasonal_supply_trough(2-4月) -> long"
"RSI(6)>80 超买 -> short_mean_reversion; RSI(6)<20 超卖 -> long_mean_reversion"
"价差加速度转正（利润加速扩张） -> long, 加速度转负（利润加速收缩） -> short"
```

数据中继链：`prompt_base.jinja2` → peer JSON → `search_promote.py` → `preregistry.jsonl` → `_build_state()` → Laya

### 2.5 Jev vs Laya 对比

| 维度 | Jev 时代 | Laya 时代（当前） |
|------|---------|----------------|
| instructions | 中文 | 英文 ✅ |
| state.proposal | 整体传入（全中文） | 白名单 5 字段 ✅ |
| state.sector | 中文 | 英文 ✅ |
| state.predicted_direction | 中文 | **中文 ❌** |
| 超时 | 5s（SDK 默认） | 60s（仍可能超时） |

Jev 时代无语言处理需求（Jev 模型吃中文没问题）。迁移到 Laya 后发现中文导致超时，三轮打补丁修复，但 predicted_direction 被遗漏。

---

## 3. 修复方案：两条腿走路

### 3.1 短期止血（下游过滤）

**目标**：确保发送到 Laya 的 state 无东亚宽字符（Han + CJK 标点 + 全角标点）

**验收字符类定义**：
- ✅ 允许：ASCII（U+0000–U+007F）、拉丁扩展（U+0080–U+024F，含重音字母）、通用标点/符号（半角）
- ❌ 禁止：CJK 统一表意文字（U+4E00–U+9FFF）、CJK 标点（U+3000–U+303F）、全角标点（U+FF00–U+FFEF 中的标点区）

**文件**：`cascade/typesafe_prescreen.py`

**变更 1**：添加 `_strip_chinese()` 函数（含空壳检测 + 全角标点二次清洗）

```python
import re
# v3: 主正则剥 CJK 汉字 + CJK 标点；二次清洗剥全角标点（保留全角数字/字母）
_ZH = re.compile(r'[一-鿿　-〿]+')
_FULLWIDTH_PUNCT = re.compile(r'[！-／：-＠［-＿｛-･]+')
_PD_MIN_LEN = 12  # v3: 从 8 调至 12，对齐实测 ~496 空壳（27.6%，双道 strip 后）

def _strip_chinese(s: str) -> str:
    """剥中文字符 + 全角标点，保留英文/数字/半角符号/空格。
    ponytail: 二次清洗避免全角标点残留（v2 收窄正则的遗漏）。
    """
    # 第一次：剥 CJK 汉字 + CJK 标点
    result = _ZH.sub(' ', s)
    # 第二次：剥全角标点（！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～）
    result = _FULLWIDTH_PUNCT.sub(' ', result)
    return re.sub(r'\s+', ' ', result).strip(' (;,)')

def _is_shell_pd(stripped: str) -> bool:
    """判定 strip 后是否为近空壳（如整句中文 → '-> long, -> short'）。
    v3: 阈值 12，对齐实测 ~496 空壳样本（双道 strip 后）。
    """
    # 去掉箭头和分隔符后，剩余字母数字长度不足阈值
    core = re.sub(r'[->,;|()+\s]', '', stripped)
    return len(core) < _PD_MIN_LEN
```

> **v3 修订**：
> 1. `_PD_MIN_LEN` 从 8 调至 12。再审实测：阈值=8 时仅 247 条空壳（13.8%），阈值=12 时 ~496 条（27.6%，含全角二次清洗），对齐初审估算 ~487。典型空壳 `"-> long, -> short"` 的 core="longshort" 长度 9，阈值 8 漏判。
> 2. 新增 `_FULLWIDTH_PUNCT` 二次清洗。v2 收窄正则去掉全角区后，全角标点如 `（）` 残留（实测 369 条），既非纯英文又影响空壳判定。v3 做二次清洗剥全角标点，保留全角数字/字母（避免误伤）。

**变更 2**：修改 `_build_state()` 过滤 predicted_direction（含空壳回退）

```python
raw_pd = proposal.get("predicted_direction", "")
stripped_pd = _strip_chinese(raw_pd)
if _is_shell_pd(stripped_pd):
    # 空壳回退：置为空串，Laya 收到空 predicted_direction
    final_pd = ""
else:
    final_pd = stripped_pd

proposal_summary = {
    "proposal_id": proposal.get("proposal_id", ""),
    "symbol": proposal.get("symbol", symbol),
    "cov_override": proposal.get("cov_override", ""),
    "covariate_family": proposal.get("covariate_family", ""),
    "predicted_direction": final_pd,
}

return {
    "language": "en",    # best-effort: 未证实 Laya 服务端识别此字段
    "symbol": symbol,
    "proposal_summary": proposal_summary,
    "sector": symbol_profile.get("sector", "commodity"),
    "contract_details": symbol_profile.get("contract_details", "futures contract"),
}
```

> **v3 修订**：注释从「省略该字段」改为「置为空串」，与代码实际行为一致（字段仍存在，值为空）。

**变更 3**：`_call_laya()` payload 顶层添加 language（best-effort）

```python
payload = {
    "model": "laya-rl-agent",
    "language": "en",    # best-effort: 未证实服务端识别，不阻塞成功率验收
    "state": state,
    "questions": { ... },
}
```

> **v2 修订**：`language: en` 标为 best-effort。`docs/praxist_llm_env.md` 仅记录 instructions 英文化，无 language 路由字段文档。验收不应与成功率强绑。

### 3.2 长期治本（源头约束）

**目标**：peer LLM 不再生成中文 predicted_direction

**文件**：`task_FM/prompt_base.jinja2`

**变更**：在 predicted_direction 字段约束中添加 English only

当前（约 L65）：
```
- predicted_direction / kill_condition / promote_condition must be falsifiable before seeing results
```

修改后：
```
- predicted_direction: English only. No Chinese annotations. Format: "condition -> action"
  Example: "oi_up_with_price -> long; oi_down_with_price_breakdown -> short"
- kill_condition / promote_condition must be falsifiable before seeing results
```

**为什么两条路都要做**：
- prompt 修复需要等下一代 peer 重跑才见效
- 已有的 1796 条中文 predicted_direction 提案还在 experiments proposals 里，需要下游过滤

### 3.3 附加修复：去重（不扩 PrescreenStatus 枚举）

> **v2 修订**：v1 扩 `PrescreenStatus` 加 `"duplicate"` 与 Frozen lifecycle spec §71/§422 冲突（lifecycle 锁死 status ∈ {success, degraded, error}）。改为不扩枚举。

**目标**：避免 REGISTRY/QUEUE 中已有的 variant 重复调用 Laya

**文件**：`scripts/backfill_prescreen.py`（+ 可选 `scripts/sup_harvest.py`）

**策略**：在调用 Laya 前 pre-check variant_id 是否已存在；若存在，**跳过 Laya 调用且不写 `.prescreen.json`**（或写 `"status": "degraded"` + `note="skipped: variant in REGISTRY/QUEUE/INPROGRESS"`）。

**backfill 变更**：

```python
# process_proposal() 中，在 _prescreen_impl 调用前
if variant_id in existing_variant_ids:
    # 方案 A（推荐）：跳过，不写 prescreen.json
    stats.inc("skipped")
    return "skipped"

    # 方案 B（可选）：写 degraded + note
    # result = {
    #     "status": "degraded",
    #     "note": "skipped: variant in REGISTRY/QUEUE/INPROGRESS",
    #     ...
    # }
    # write_prescreen_result(str(prescreen_path), result)
```

**harvest 覆盖**（可选，Phase 2b）：

`sup_harvest.py` 的 `_prescreen_async` 当前仅幂等检查 `status == "success"` 的已有文件，不查 REGISTRY/QUEUE。若目标是「全面避免重复调用 Laya」，需同策略。本期先做 backfill，harvest 留 Phase 2b 或标记为 out-of-scope。

### 3.4 附加修复：统一超时值

`_call_laya()` 签名默认值从 30s 改为 60s，与实际调用一致。

---

## 4. 验证标准

### 4.1 短期止血验证（Phase 1）

| 测试项 | 方法 | 通过标准 |
|--------|------|---------|
| 中文过滤正确性 | 单元测试 `tests/test_strip_chinese.py` | 所有中文样本被清洗为无东亚宽字符（含半角符号） |
| 全角标点清洗 | 单元测试含全角标点样本 | `"价差（利润） -> long"` → `" -> long"`（全角括号被剥） |
| 空壳检测 | 单元测试 `test_is_shell_pd()` | ~496 条已知空壳样本正确识别（阈值=12，双道 strip 后） |
| 空壳回退 | 集成测试：空壳 PD → `_build_state()` | `predicted_direction` 置为空串，不伪装为有效英文 |
| `_build_state` 集成 | 对 7194 条 proposal 跑 `_build_state()` | 0 条 state 含东亚宽字符（Han + CJK 标点 + 全角标点） |
| language 字段存在 | 检查 payload | `"language": "en"` 存在于 state 和 payload 顶层（best-effort，不与成功率强绑） |
| Laya 调用成功率 | 跑 backfill 批次 | 成功率 ≥ 99%，超时率 < 1% |
| 性能不劣化 | 对比修复前后的 p50/p95 延迟 | p95 延迟不增加，记录对比批次 run id |
| 7194 全量扫描 | 一次性门禁脚本 `scripts/check_pd_chinese.py` | 输出 0 条含东亚宽字符 state，脚本落点写入 Phase 1 commit |

> **v3 修订**：
> 1. 新增「全角标点清洗」测试项，验证二次清洗逻辑
> 2. 「0 条 state 含 CJK 字符」改为「0 条 state 含东亚宽字符（Han + CJK 标点 + 全角标点）」，明确验收字符类
> 3. 空壳数从 487 修正为 ~496（阈值=12，双道 strip 后实测）

### 4.2 长期治本验证（Phase 3）

| 测试项 | 方法 | 通过标准 |
|--------|------|---------|
| peer prompt 生成英文 | 跑 10 个 peer 种子 | 100% predicted_direction 无中文 |

### 4.3 去重验证（Phase 2）

| 测试项 | 方法 | 通过标准 |
|--------|------|---------|
| backfill 去重 | 对已知 REGISTRY 中的 variant 跑 backfill | 不重复调用 Laya，stats.inc("skipped") 计数正确 |
| PrescreenStatus 未扩 | 代码审查 | `PrescreenStatus` 仍为 `Literal["success", "degraded", "error"]` |
| harvest 覆盖（Phase 2b） | 同上策略应用于 `_prescreen_async` | 若纳入范围，同标准 |

---

## 5. 实施计划

### Phase 1：短期止血（1 天）

1. `cascade/typesafe_prescreen.py`：
   - 添加 `_strip_chinese()` + `_is_shell_pd()` + `_FULLWIDTH_PUNCT` 二次清洗
   - 修改 `_build_state()` 过滤 predicted_direction + 空壳回退（置为空串）
   - 添加 `language: "en"`（best-effort）
   - 统一超时值 30→60
2. 编写单元测试 `tests/test_strip_chinese.py`（含空壳样例 + 全角标点样例）
3. 编写集成测试 `tests/test_build_state_no_cjk.py`（验收东亚宽字符类）
4. 编写一次性门禁脚本 `scripts/check_pd_chinese.py`
5. 跑完整测试 `pytest cascade/ tests/`
6. Commit + push

### Phase 2：去重（0.5 天）

1. `scripts/backfill_prescreen.py`：添加 REGISTRY/QUEUE pre-check，跳过已存在 variant
2. 可选：`scripts/sup_harvest.py` 同策略（Phase 2b）
3. 编写测试
4. Commit + push
5. **不改 `PrescreenStatus` 枚举**，与 lifecycle Frozen spec 保持一致

### Phase 3：长期治本（1 天）

1. `task_FM/prompt_base.jinja2`：添加 English only 约束
2. 跑 10 个 peer 种子验证
3. Commit + push

---

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `_strip_chinese()` 过度清洗 | 低 | 低 | 主正则仅剥 CJK 汉字 + CJK 标点；二次清洗仅剥全角标点，保留全角数字/字母；单测覆盖 |
| **strip 后空壳伪装为有效英文** | **中** | **中** | `_is_shell_pd()` 门禁（阈值=12）+ 空壳回退为空串；验收含空壳检测 |
| **全角标点残留** | **低** | **低** | v3 新增 `_FULLWIDTH_PUNCT` 二次清洗；单测含全角标点样本 |
| prompt 约束导致 peer 生成质量下降 | 低 | 中 | 只约束 predicted_direction 格式 |
| language 字段不被 Laya 服务端识别 | 中 | 低 | best-effort，不与成功率验收强绑 |
| 去重跳过导致遗漏新提案 | 低 | 低 | 仅跳过 REGISTRY/QUEUE 已有 variant，新提案不受影响 |

> **v3 修订**：新增「全角标点残留」风险项（低/低），v3 已通过二次清洗缓解。

---

## 7. 不做的事

- ❌ 用翻译 API 翻译中文 predicted_direction：增加依赖，引入翻译错误，YAGNI
- ❌ 重写 `validate_laya_prescreen.py` 的 5 个硬编码 proposal：验证脚本，非生产代码
- ❌ 建立通用"中文字段检测器"扫整个 proposal：过度抽象，只有 predicted_direction 漏网
- ❌ 为 `kill_condition`/`promote_condition` 加 English only 约束：这两个字段不发送到 Laya
- ❌ 扩 `PrescreenStatus` 加 `"duplicate"`：与 Frozen lifecycle spec 冲突

---

## 8. 回滚方案

Phase 1 为单 commit，回滚即 `git revert`。具体：

| 变更 | 回滚方式 |
|------|---------|
| `_strip_chinese()` + `_build_state()` 修改 | revert commit，恢复原样传入 predicted_direction |
| `language: "en"` | revert commit 自动移除 |
| timeout 30→60 | revert commit 恢复 30 |

Phase 3 prompt 修改独立 commit，回滚互不影响。

---

## 9. 参考资料

- Commit `a134dac`：Laya 预筛英文支持（instructions 英文化）
- Commit `5f1d17a`：_build_state 移除中文 proposal
- Commit `2c36e6c`：state 全英文化
- `docs/praxist_llm_env.md` L109-113：Laya 英文输入修复记录
- `docs/superpowers/changelogs/2026-10-14-jev-to-laya-migration.md`：Jev→Laya 迁移
- `docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md`：Frozen lifecycle spec（§71/§422 PrescreenStatus 锁死三值）
- `docs/superpowers/specs/2026-10-18-laya-chinese-leak-fix-spec-audit.md`：审核报告（初审 + 再审）
