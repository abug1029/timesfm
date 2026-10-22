# Proposal Gate Rules — 提案门禁规则清单

> **A1 交付物**（Phase 2-3 Praxist 集成 Task 1-1）
> **日期**: 2026-10-21
> **状态**: 草案
> **依据**: Spec §3.2 P1-A、审计 P0、`scripts/proposal_validator.py`

**目的**: 把 `proposal_validator.py` 的规则整理成可声明合同，与 validator 测试一一对应，为后续迁入 `task_audit` / `audit_rules/` 或 task-local plugin 提供规则清单。

---

## 1. 规则总览

| # | 规则 ID | 规则名称 | 校验阶段 | 强制级别 | 现有实现 |
|---|---------|----------|----------|----------|----------|
| R1 | `json_wellformed` | JSON 格式有效性 | Step 0 预检 | **硬门** | ✅ 已实现 |
| R2 | `required_fields` | 必填字段齐全 | Step 0 预检 | **硬门** | ✅ 已实现 |
| R3 | `type_checks` | 关键字段类型正确 | Step 0 预检 | **硬门** | ✅ 已实现 |
| R4 | `chinese_gate` | 中英门禁（mechanism/symbol_fit） | Step 0 预检 | **硬门** | ✅ 已实现 |
| R5 | `laya_prohibited_words` | Laya 禁用词检测 | Step 0 预检 | **硬门（P0 红线）** | ❌ 待实现 |
| R6 | `stem_variant_id_consistency` | stem / variant_id 口径一致 | Step 0 预检 | **硬门** | ❌ 待实现 |

---

## 2. 规则详细定义

### R1 — JSON 格式有效性 (`json_wellformed`)

**描述**: 提案文件必须是合法 UTF-8 编码的 JSON，可被 `json.load()` 解析。

**预期行为**:
- 合法 JSON → 进入后续规则校验
- 非法 JSON → 返回 `unparseable_json:<detail>` 错误，**短路拒绝**
- 文件不可读 → 返回 `io_error:<detail>` 错误，**短路拒绝**

**错误码**:
- `unparseable_json:<json.JSONDecodeError detail>`
- `io_error:<OSError detail>`

**对应测试**:
- `test_proposal_validator.py::TestInvalidJson::test_invalid_json`
- `test_proposal_validator.py::TestInvalidJson::test_io_error`

**实现位置**: `scripts/proposal_validator.py:validate_proposal()`

---

### R2 — 必填字段齐全 (`required_fields`)

**描述**: 提案必须包含以下 5 个必填字段，且值不为 `None`。

**必填字段清单**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `symbol` | `str` | 品种代码（如 `m`, `rb`, `cu`） |
| `cov_override` | `str` | 协变量名称（如 `vol`, `oi`） |
| `mechanism` | `str` | 机制论证（英文，见 R4） |
| `symbol_fit` | `str` | 品种适配论证（英文，见 R4） |
| `predicted_direction` | `str` | 预测方向（如 `up`, `down`） |

**预期行为**:
- 缺少任一字段或值为 `None` → 返回 `missing_required:<field>` 错误
- 多个字段缺失 → 返回多个 `missing_required` 错误（累积报告）

**错误码**: `missing_required:<field_name>`

**对应测试**:
- `test_proposal_validator.py::TestMissingFields::test_missing_symbol`
- `test_proposal_validator.py::TestMissingFields::test_missing_cov_override`
- `test_proposal_validator.py::TestMissingFields::test_missing_mechanism`
- `test_proposal_validator.py::TestMissingFields::test_missing_predicted_direction`
- `test_proposal_validator.py::TestMissingFields::test_multiple_missing_fields`（5 个必填字段全缺 → 5 个错误）

**实现位置**: `scripts/proposal_validator.py:REQUIRED_FIELDS` + `validate_proposal_dict()`

---

### R3 — 关键字段类型正确 (`type_checks`)

**描述**: 所有必填字段（R2 中列出的 5 个）的值必须为 `str` 类型。

**预期行为**:
- 字段存在但类型非 `str` → 返回 `type_error:<field>:expected_str:got_<actual_type>` 错误
- 字段为 `None` → 由 R2 处理（`missing_required`），R3 不重复报错

**类型映射表**:

| 字段 | 期望类型 |
|------|----------|
| `symbol` | `str` |
| `cov_override` | `str` |
| `mechanism` | `str` |
| `symbol_fit` | `str` |
| `predicted_direction` | `str` |

**错误码**: `type_error:<field>:expected_str:got_<actual_type_name>`

**对应测试**:
- `test_proposal_validator.py::TestTypeErrors::test_symbol_as_int`
- `test_proposal_validator.py::TestTypeErrors::test_cov_override_as_list`
- `test_proposal_validator.py::TestTypeErrors::test_predicted_direction_as_int`
- `test_proposal_validator.py::TestTypeErrors::test_mechanism_as_dict`

**实现位置**: `scripts/proposal_validator.py:TYPE_CHECKS` + `validate_proposal_dict()`

---

### R4 — 中英门禁 (`chinese_gate`)

**描述**: `mechanism` 和 `symbol_fit` 字段禁止包含中文字符（东亚宽字符），以防止 Laya System-1 预筛阶段的中文泄漏。

**门禁字段**: `mechanism`, `symbol_fit`

**中文字符定义**（东亚宽字符正则，与 SPEC 验收字符类一致）:

覆盖范围:
- CJK 统一汉字（U+4E00 到 U+9FFF）
- CJK 符号和标点（U+3000 到 U+303F）
- 全角 ASCII 变体（U+FF01 到 U+FF60）

**预期行为**:
- `mechanism` 或 `symbol_fit` 包含任一东亚宽字符 → 返回 `chinese_field:<field>` 错误
- 纯英文 / ASCII / 半角标点 → 通过
- 中英文混合 → **拒绝**（只要包含中文即拒绝）

**错误码**: `chinese_field:<field_name>`

**对应测试**:
- `test_proposal_validator.py::TestChineseDetection::test_chinese_mechanism`
- `test_proposal_validator.py::TestChineseDetection::test_chinese_symbol_fit`
- `test_proposal_validator.py::TestChineseDetection::test_english_mechanism_passes`
- `test_proposal_validator.py::TestChineseDetection::test_mixed_chinese_and_english`
- `test_proposal_validator.py::TestContainsChinese::test_pure_english`
- `test_proposal_validator.py::TestContainsChinese::test_pure_chinese`
- `test_proposal_validator.py::TestContainsChinese::test_mixed`
- `test_proposal_validator.py::TestContainsChinese::test_empty_string`
- `test_proposal_validator.py::TestContainsChinese::test_punctuation_only`
- `test_proposal_validator.py::TestContainsChinese::test_chinese_punctuation`
- `test_proposal_validator.py::TestContainsChinese::test_fullwidth_chars`

**实现位置**: `scripts/proposal_validator.py:CHINESE_GATED_FIELDS` + `contains_chinese()` + `validate_proposal_dict()`

**关联实现**: `cascade/typesafe_prescreen.py:_strip_chinese()`（预筛阶段剥离中文）+ `_is_shell_pd()`（空壳检测，阈值=12）

---

### R5 — Laya 禁用词检测 (`laya_prohibited_words`) ⚠️ 待实现

**描述**: 提案全文（所有字符串字段）禁止包含 Laya 相关禁用词，以固化「Laya 只是判断、不可学习」红线。

**禁用词清单**:

| 禁用词 | 说明 | 违规级别 |
|--------|------|----------|
| `训练 Laya` | 暗示 Laya 可被训练/学习 | **P0 红线** |
| `进化 Laya` | 暗示 Laya 可自我进化 | **P0 红线** |
| `可学习` | 暗示 Laya 具备学习能力 | **P0 红线** |

**检测范围**: 提案 JSON 中所有字符串值（递归扫描），重点关注 `mechanism`、`symbol_fit`、`proposal_id` 等自由文本字段。

**预期行为**:
- 任何字符串值包含禁用词（大小写不敏感） → 返回 `laya_prohibited_word:<word>:in_field:<field>` 错误
- 多个禁用词 → 累积报告

**错误码**: `laya_prohibited_word:<matched_word>:in_field:<field_path>`

**对应测试**: ❌ **待实现**
- 需新增 `tests/test_laya_prohibited_words.py`（Spec §4.4 验收项）
- CI 每次提交自动扫描，违规即 fail

**实现位置**: 待迁入 `scripts/proposal_validator.py` + `tests/test_laya_prohibited_words.py`

**Spec 引用**: §3.2「Laya 红线固化」、§4.4 卫生门禁验收项

---

### R6 — stem / variant_id 口径一致 (`stem_variant_id_consistency`) ⚠️ 待实现

**描述**: `variant_id` 必须与提案内容的标准化 stem（`symbol + _ + cov_override`）一致，防止身份链断裂。

**预期行为**:
- `variant_id` 为空或与 `{symbol}_{cov_override}` 前缀不匹配 → 返回 `variant_id_mismatch:expected_<expected>:got_<actual>` 警告或错误
- 允许 `variant_id` 包含额外后缀（如时间戳），但 **前缀必须匹配** `{symbol}_{cov_override}`

**错误码**: `variant_id_mismatch:expected_<expected_stem>:got_<actual_variant_id>`

**对应测试**: ❌ **待实现**
- 需新增 `tests/test_variant_id_consistency.py`

**实现位置**: 待迁入 `scripts/proposal_validator.py` 或 `audit_rules/`

**Spec 引用**: §3.2「stem / variant_id 口径（对照已通过的 proposals-evaluation-optimization SPEC）」

---

## 3. 规则与测试对应矩阵

| 规则 ID | validator 测试类 | 测试数量 | 状态 |
|---------|------------------|----------|------|
| R1 `json_wellformed` | `TestInvalidJson` | 2 | ✅ 已实现 |
| R2 `required_fields` | `TestMissingFields` | 5 | ✅ 已实现 |
| R3 `type_checks` | `TestTypeErrors` | 4 | ✅ 已实现 |
| R4 `chinese_gate` | `TestChineseDetection` + `TestContainsChinese` | 11 | ✅ 已实现 |
| R5 `laya_prohibited_words` | `test_laya_prohibited_words.py` | 0 | ❌ 待实现 |
| R6 `stem_variant_id_consistency` | `test_variant_id_consistency.py` | 0 | ❌ 待实现 |
| **合计** | — | **22** | 16/22 已实现 |

**有效提案通过测试**:
- `TestValidProposal::test_valid_proposal` — 最小有效提案
- `TestValidProposal::test_valid_with_extra_fields` — 允许额外字段

**批量验证测试**:
- `TestBatchValidation::test_batch_all_valid` — 3 个有效提案
- `TestBatchValidation::test_batch_mixed` — 1 有效 + 1 非法 JSON + 1 缺字段

---

## 4. 校验流程（Fail-fast in Evaluator）

```text
提案 JSON 输入
    │
    ▼
[R1] JSON 格式有效性
    ├─ FAIL → 短路拒绝，输出 validation_signal，不跑评估
    └─ PASS ↓
    │
    ▼
[R2] 必填字段齐全
    ├─ FAIL → 短路拒绝
    └─ PASS ↓
    │
    ▼
[R3] 关键字段类型正确
    ├─ FAIL → 短路拒绝
    └─ PASS ↓
    │
    ▼
[R4] 中英门禁（mechanism/symbol_fit）
    ├─ FAIL → 短路拒绝
    └─ PASS ↓
    │
    ▼
[R5] Laya 禁用词检测
    ├─ FAIL → 短路拒绝（P0 红线）
    └─ PASS ↓
    │
    ▼
[R6] stem / variant_id 口径一致
    ├─ FAIL → 短路拒绝
    └─ PASS ↓
    │
    ▼
进入 task evaluator（昂贵模型评估）
```

**关键约束**:
- 所有 6 条规则必须在 evaluator 启动前完成（Step 0 前置关卡）
- 任一规则失败 → 不消耗算力，直接输出 `validation_signal` 留痕
- `variants/` 和 `results/` 中的非法文件不进入 `findings / frontier`

---

## 5. 迁移计划（task_audit / audit_rules/）

**目标**: 将上述 6 条规则从 `scripts/proposal_validator.py` 迁移到 Praxist task 合同的可声明格式。

**候选位置**（按优先级）:
1. `<task>/audit_rules/proposal_gates.yaml` — 声明式规则配置
2. `<task>/.praxist/plugins/proposal_validator_adapter/` — task-local plugin 适配器
3. `evaluations/proposal_precheck.py` — evaluator Step 0 接入点

---

## 6. 双闸文档（主/备）

**主闸**: evaluator Step 0 预检（Fail-fast，省算力）
- 位置: `<task>/audit_rules/` 或 `evaluations/proposal_precheck.py`
- 调用时机: task evaluator 启动前
- 失败输出: `validation_signal` 持久化，不产生 `results/` 输出

**备闸**: harvest 旁路闸（防旧路径漏网）
- 位置: `scripts/sup_harvest.py` 调用 `validate_proposal_dict()`
- 调用时机: 旧提案文件导入慢环队列前
- 失败输出: 拒绝入队，记录日志

**文档要求**: 双闸并存期间，必须在文档中声明主/备关系，避免双口径混淆。

---

## 7. 验收标准（Task 1-1 完成条件）

- [x] 规则清单文档已创建（本文档）
- [x] 6 条规则与 validator 测试一一对应
- [x] Laya 禁用词清单已定义（R5）
- [x] stem / variant_id 口径规则已定义（R6）
- [ ] R5 / R6 代码实现（Task 1-2 A2 范围）
- [ ] R5 / R6 单测实现（Task 1-2 A2 范围）
- [ ] CI 自动扫描接入（Task 1-2 A2 范围）

---

## 8. 参考链接

- **Spec**: `docs/superpowers/specs/2026-10-21-phase2-3-praxist-integration-spec.md` §3.2 P1-A
- **Plan**: `docs/superpowers/plans/2026-10-21-phase2-3-praxist-integration.md` Task 1-1
- **Validator**: `scripts/proposal_validator.py`
- **Tests**: `tests/test_proposal_validator.py`
- **关联修复**: `docs/superpowers/specs/2026-10-18-laya-chinese-leak-fix-spec.md`
- **评估优化**: `docs/superpowers/specs/2026-10-19-proposals-evaluation-optimization-spec.md`（stem / variant_id 口径）
