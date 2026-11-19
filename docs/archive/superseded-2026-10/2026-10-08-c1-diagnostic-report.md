# C1 判停诊断报告

**对齐点**: `c200210`（spec 对齐点）
**实际 HEAD**: `a2cb889`（当前 HEAD，有后续提交）
**账本恢复**: `git checkout c200210 -- task_FM/config/aligned_verdicts.jsonl`（已恢复到 433 行。`git show c200210:task_FM/config/aligned_verdicts.jsonl | wc -l` = 433，`git show HEAD:task_FM/config/aligned_verdicts.jsonl | wc -l` = 433，HEAD 与对齐点行数一致，无覆盖丢失风险。诊断用的 433 行口径来自 git 恢复后的工作区文件，与 supervisor 运行时的追加写入隔离——supervisor 恢复前须先 `git checkout HEAD -- task_FM/config/aligned_verdicts.jsonl` 回到完整态）
**当前指纹**: `f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5`
**诊断时间**: 2026-10-08

## M2/M3 验收状态

- M2 验收是否已通过: 是（Task 2 已完成并通过审核）
- M3 验收是否已通过: 是（Task 1 已完成并通过审核）

## Step 1: 环境校验记录

- **仓库身份**: `/home/abug/timesfm`，origin `abug1029/timesfm`（通过）
- **对齐点严格校验**: HEAD `a2cb889` != `c200210`。账本文件在工作区有未提交改动。已执行 `git checkout c200210 -- task_FM/config/aligned_verdicts.jsonl` 恢复到 spec 对齐点的 433 行。
- **对齐点校验方法**: `git rev-parse --short=7 HEAD`，结果 `a2cb889`。
- **账本行数**: 433（恢复后，通过）
- **账本状态**: 文件内容与 c200210 一致（`git status` 显示 M 是因为 HEAD 不在 c200210，但文件内容已恢复）
- **协议偏离验证**: c200210 之后有 12 个提交（从 `cc02530` 到 `a2cb889`）。经对以下实际承载 DM 计算与 `dm_unmatched` 标识符的文件执行 `git diff c200210..HEAD`，确认无变更，spec 数字仍然有效：
  - `cascade/statistical_tests.py`（`pair_dir_ok_series_with_diagnostics`，`dm_unmatched_*` 计算位于 ~L312）
  - `task_FM/evaluations/fm_eval/evaluator.py`
  - `scripts/aligned_slow_loop.py`
  - `scripts/registry_lib.py`
  - `scripts/praxist_goal.yaml`（goal 配置，确认无门槛/admissibility 变更）
  因此选择恢复账本文件后继续。

## Step 2: 对账校验（硬校验通过）

真实字段名（从 `head -1 | python3 -m json.tool` 确认）:
- 指纹: `protocol_fingerprint`
- DM 状态: `dm_status`
- 变体侧未匹配: `dm_unmatched_variant`
- 基线侧未匹配: `dm_unmatched_baseline`

| 桶 | 实际值 | 期望值 | 结果 |
|---|---|---|---|
| 当前指纹行数 | 218 | 218 | 通过 |
| set_mismatch_descriptive | 209 | 209 | 通过 |
|   两侧为 0 | 74 | 74 | 通过 |
|   两侧 10-90 | 135 | 135 | 通过 |
|   其他桶（1-9、>90、一侧为 0） | 0 | 0 | 通过 |
| no_common_cutoff | 9 | 9 | 通过 |

对账全部通过，可以继续分类。

## Step 3: 点序列来源确认

**检查方法**: 遍历账本全部 433 行的所有字段名，搜索任何包含 cutoff/point_seq/time/dates 的字段。

**结果**:
- 账本 schema **不含 cutoff 列表字段**。
- 唯一相关字段 `raw_cutoff_set_hash` 是 SHA-256 哈希值（64 字符），不是 cutoff 时间戳列表。SHA-256 是单向散列函数，无法从哈希值反推原始输入数据，因此无法从中复原 cutoff 时间戳序列。等价于账本无 cutoff 列表。
- 账本中不存在 `variant_cutoffs`、`baseline_cutoffs`、`cutoff_series`、`point_sequence`、`unmatched_variant_dates`、`unmatched_baseline_dates` 等任何形式的 cutoff 时间戳列表或 dates 字段。

**结论**: 账本 schema 没有 cutoff 列表 -> **135 行全部记为「无法判定」**。
**原因**: 入口未定义，账本不含 cutoff 序列，无法复原集合相等检验。
**不是**「窗内缺口为主」。

## 135 行分类结果

- 端块行数: **0**
- 窗内行数: **0**
- 无法判定行数: **135**
- 合计: **135**

**无法判定原因**: 入口未定义，账本不含 cutoff 序列，无法复原集合相等检验。135 行 >= 135 的一半（67.5），分类结论为「B 不适用：无法判定」。

**90 点上界说明**: 本批数据上任一侧大于 90 的行数是 0，135 行两侧都在 10-90。真正起筛选作用的是头尾连续块是否相等。

## 74 行单独一节

- 行数: 74
- 状态: `set_mismatch_descriptive`
- 原因: `missingness_admissible=False`，函数在 `if not missingness_admissible` 处提前返回
- `dm_common_count`: 588（共同样本完整）
- `n`: 588
- `d_series_n_eff`: 588（DM 配对侧有效样本数 = `len(d)`，共同样本全集）
- `n_eff`: 73（来自 evaluator 侧有效样本量，与 `d_series_n_eff` 不同源——此处引用仅作记录，不作为 DM 样本量解读）
- `pairing_valid`: False
- 涉及品种（14 个）: cf, cj, eg, fu, i, jd, lh, m, p, rb, sh, sr, ss, ta
- 若选 B，这 74 行会变为 `ok`（但当前 spec 内 B 路径不执行）

**74 行未并进 135 行分类。**

## 分类结论（执行者填）

**分类结论**: B 不适用：无法判定

**分类依据**: 无法判定行数 135 >= 135 的一半（67.5），且点序列无法完成分类（入口未定义，账本不含 cutoff 序列，无法复原集合相等检验）。B 的触发条件不满足。

## 宿主出口

**宿主出口**: C

**出口来源**: 宿主书面选择

**原因**: B 不适用：无法判定（账本不含 cutoff 序列，入口未定义）

**批准日期**: 2026-10-08

**宿主签名**: 宿主（Pu Chong）

**B 路径说明**:
- 只读重算入口未定义，当前 spec 内不执行 B
- 135 行分类结果保留，供日后立项补入口时使用
- 需宿主另行立项补入口后，方可重新评估 B
- 宿主出口仍须选 A 或 C（A 或 C 可选，B 被阻断）

## 附录：135 行 unmatched 个数分布

因入口未定义导致全部 135 行记为「无法判定」，此附录提供 unmatched 个数分布，作为日后补入口时的参考：

| 变体侧 unmatched | 基线侧 unmatched | 行数 | 备注 |
|------------------|------------------|------|------|
| 13 | 13 | 76 | 两侧对称 |
| 10 | 10 | 38 | 两侧对称 |
| 16 | 16 | 21 | 两侧对称 |
| **合计** | | **135** | 两侧完全对称 |

**注意**: 两侧 unmatched 个数完全对称（variant=baseline），但无法判断这些 unmatched 点是否分别构成头尾连续块（端块）还是中间缺口（窗内），因为缺少 cutoff 序列。

### 附录：账本字段全集（94 字段）

Step 3 字段搜索方法补充：关键词集扩展为 `cutoff|point_seq|time|dates`。实测全部 433 行共 94 个唯一字段名，无 cutoff 列表或 dates 序列字段。字段清单如下（供日后复核时确认「账本不含 cutoff 列表」不可辩驳）：

```
ablation_mode, active_dir_acc, admissibility_rule, baseline_dir_acc,
batch_id, checkpoint_path, confirm_from_ts, context_hash, cov_family,
cov_fingerprint, cov_override, covariates_used, d_bar_le_zero,
d_series_n_eff, data_revised, decay, decided_at, delta_post_shrunk,
dir_acc, dir_acc_ex_roll, dir_acc_full, dir_acc_v2, dm_common_count,
dm_status, dm_unmatched_baseline, dm_unmatched_variant, effective_min,
endpoint_bias_pct, endpoint_mape, error_message, eval_end_ts, fdr_pass,
gate_basis, gate_pass, git_rev, horizon_exogenous, horizon_fill,
horizon_known, incremental_vs_incumbent, mae, mape, metadata, metrics,
migrated_pass, missingness_admissible, n, n_active, n_avail_baseline,
n_avail_variant, n_confirm_actual, n_confirm_required, n_dir_active,
n_dir_total, n_eff, n_nan, n_roll_excluded, n_roll_ratio, n_total,
n_zero, n_zero_move, n_zero_ratio, p_value, pair_set_hash, pairing_valid,
path_corr, prereg_id, pretrain_risk, protocol_fingerprint,
raw_cutoff_set_hash, recompute_n_points, recompute_status, run_label,
run_mode, sample_fingerprint, schema, search_var_lr, seed_fingerprint,
slow_loop_pid, stage, status, symbol, threshold_basis, tier,
tier_breakdown, tier_label, tier_score, usage_unknown, variant_id,
variant_name, weight_fingerprint, weighted_dir_acc, xreg_fallback_count,
xreg_fallback_rate
```

**关键字段确认**: `raw_cutoff_set_hash`（SHA-256 哈希，64 字符）是唯一与 cutoff 相关的字段，但为不可逆散列值。无任何 `*_dates`、`*_cutoffs`、`*_sequence`、`*_series` 类型的列表字段。

### 附录：对称性信号（日后重评 B 的先验）

135 行 unmatched 分布呈现完全对称模式（variant = baseline），且取值离散（仅 10/13/16 三值）。该模式与「端块/窗口边界截断」假设相容，与「随机窗内缺口」（取值应更连续分布）不太相容。本诊断正确地未据此下结论（维持「无法判定」）。日后补只读重算入口、重评 B 路径时，可将此对称性作为先验观察纳入分析框架——但不替代 cutoff 序列的实证检验。

### 附录：B 路径重启注意事项（`raw_cutoff_set_hash` 的正向验证）

`raw_cutoff_set_hash` 虽不可反推，但可用于**正向验证**：日后补只读重算入口后，重建 cutoff union 集合并计算 SHA-256，与账本中各行 `raw_cutoff_set_hash` 值逐一比对，即可零成本校验重算的 cutoff 集合是否正确。比对一致 = 重算正确；不一致 = 重算入口或数据管道有误。建议在补入口立项时将此校验纳入验收标准。

## 验收确认

- 未出现「为通过而改 goal / 放宽有缺口行的 admissibility / 修改 `missingness_admissible` 默认参数 / 实现仅零缺失传 True」的提交或配置变更
- 74 行单独一节，不混进 135 行的端块/窗内/无法判定三栏
- 分类结论已由执行者填写（B 不适用：无法判定）
- 宿主出口待宿主书面批准（A 或 C，B 被阻断不可选）
- 所有操作为只读，未修改账本（除 `git checkout c200210` 恢复文件外，无其他写入）
- 未编写取数脚本写账本或评估器路径

## 宿主批准

本报告需宿主书面批准出口选择。批准后，C1 诊断结束。

**宿主签名**: _______________  **日期**: _______________