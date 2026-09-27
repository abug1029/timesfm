# Task 1 Changelog: run_mode/run_label 双模式 + schema 波及面同步

**Commit:** d9a8a2b (amended with review fixes)
**Date:** 2026-09-27
**Status:** ✅ 完成 + 专家审核通过

## 实施内容

### 新增
- `tests/test_run_mode_field.py`: 12 个测试覆盖 run_mode schema、verdict 构造、pass_variants 守卫、tombstone 兼容性
- `RUN_MODES` 常量：`frozenset({"exploration", "confirmation"})`
- `RUN_LABEL_EXPLORATION` 常量：`"exploratory_unconfirmed"`

### 修改
- **scripts/registry_lib.py**:
  - `VERDICT_FIELDS_V2` 增 `run_mode`, `run_label`
  - `VERDICT_FIELDS_V2_NULLABLE` 增 `run_mode`, `run_label`（tombstone 等非评估产物容忍缺失）
  - `pass_variants()` v2 分支增三重守卫：① `run_mode not in RUN_MODES → continue`；② `run_mode == "exploration" → continue`；③ 必须 `gate_pass AND fdr_pass AND p_value is not None`
  - `make_error_tombstone` / `make_timeout_tombstone` 增 `run_mode: None`, `run_label: None`（外层 dict + metrics dict）

- **scripts/aligned_slow_loop.py**:
  - `_no_data_verdict` 增 `run_mode: None`, `run_label: None`（外层 dict + metrics dict）

- **task_FM/evaluations/fm_eval/evaluator.py**:
  - `build_summary` 签名增 `run_mode="exploration"` 关键字参数
  - `out` dict 增 `run_mode`, `run_label`（exploration 模式自动加 label）
  - 导入 `RUN_LABEL_EXPLORATION`（带 fallback）

- **scripts/migrate_verdicts_v1_to_v2.py**:
  - 迁移产物增 `run_mode: None`, `run_label: None`（迁移非评估产物）

- **tests/test_verdict_registry.py**:
  - `_v2_complete` fixture 增 `run_mode: "confirmation"`, `run_label: None`
  - `test_pass_variants_v2_needs_fdr` 按新语义改写：增加 `run_mode="confirmation"` + `p_value=0.01`；增加 exploration 模式测试用例

- **tests/test_prediction_quality_e2e.py**:
  - `_v2_row` 增 `run_mode="confirmation"`, `run_label: None`
  - `_summary_to_registry_row` 增 `run_mode="confirmation"`, `run_label: None`（测试夹具默认确认模式）
  - `test_e2e_migrate_output_into_registry` 断言改为迁移产物不晋升（`[]` 而非 `["m_rsi_state"]`）

## 语义变更

### 成功判定（pass_variants）
- **旧**：`gate_pass AND (fdr_pass OR migrated_pass)`
- **新**：`run_mode == "confirmation" AND gate_pass AND fdr_pass AND p_value is not None`

### migrated_pass 退役
- `migrated_pass` 不再是晋升通道
- 历史迁移产物（`run_mode=None`, `p_value=None`）恒不晋升

### 探索模式隔离
- `run_mode="exploration"` 的 verdict 永不进入成功判定
- `run_label` 仅供人读，不作为机器判据

## 波及面处理
- ✅ 三个 v2 构造器（error/timeout tombstone + no_data_verdict）补 `run_mode: None`
- ✅ `run_mode` 入 `VERDICT_FIELDS_V2_NULLABLE`，构造器无需全部字段仍通过校验
- ✅ 既有测试夹具（`_v2_complete` / `_v2_row` / `_summary_to_registry_row`）同步
- ✅ 迁移测试断言更新（迁移产物不晋升）

## 测试结果
- `test_run_mode_field.py`: 12/12 PASS
- `test_verdict_registry.py`: 12/12 PASS
- `test_prediction_quality_e2e.py`: 9/9 PASS
- `test_fm_evaluator_gated.py`: 31/31 PASS
- `test_praxist_fm_evaluator.py`: 19/19 PASS
- **总计: 83/83 PASS**

## 设计裁定
1. **run_mode 同时入 V2 与 NULLABLE**：tombstone 等非评估产物不抛 ValueError，但 `pass_variants` 的 `not in RUN_MODES` 守卫挡住 None，永不晋升
2. **迁移产物 run_mode=None**：迁移非评估产物，不应进入成功判定
3. **测试夹具默认 confirmation**：E2E 测试验证确认运行路径，探索路径由 `test_run_mode_field.py` 专项覆盖

## 待专家审核
- [x] 代码正确性
- [x] 波及面完整性
- [x] 测试覆盖充分性
- [x] 语义一致性

## 专家审核结果（oh-my-claudecode:code-reviewer, opus）

**总计 4 个发现**：HIGH 1, MEDIUM 2, LOW 1

### 修复项
- **[HIGH]** `test_supervisor.py::test_build_snapshot_scalars_v2` 缺 `run_mode` → 已加 `"run_mode": "confirmation", "run_label": None`
- **[MEDIUM]** `pass_variants()` docstring 过时 → 已更新为 `gate_pass AND fdr_pass AND p_value is not None (migrated_pass retired per W1.1)`

### 无需修复
- **[MEDIUM]** `evaluator.py` 中 `sys.path.insert(0, FM_ROOT)` 可能导致 import shadowing — 有 fallback 兜底，暂不修
- **[LOW]** `test_goal_dsl.py` 硬编码 `n_unique_pass_variants: 2` — 合成快照用于 DSL 测试，不受影响

**最终测试：test_supervisor.py 61/61 PASS，task1 核心测试 29/29 PASS**
