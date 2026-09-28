# T3 Changelog: PR-B4 dir_acc 口径统一（依 spec W6.5）

**Status:** 改档完成，待实施
**Date:** 2026-09-28（v2 — 依审计 D1 修正方向）
**Spec:** §4.7 W6.5（**宿主已裁定：重算**）
**裁定记录:** 2026-09-28 宿主裁定「遵循 spec 文档」（D1 路径 a）

---

## ⚠️ v1 勘误（审计 D1）

v1 文档**方向写反**，本版按 spec W6.5 重写。差异如下：

| 项 | v1（错误） | v2（依 spec） |
|----|-----------|--------------|
| 主口径 `dir_acc` | 保留 full-sample（零变动算 miss） | **零变动从分母剔除** |
| active-only 口径 | 降级为诊断字段 | 改名 `active_dir_acc`，仅 gated 路径使用 |
| 历史裁决 | 不迁移 | **重算**（宿主已裁定） |
| 引用 | 「spec §6.5 推荐」（**该章节不存在**） | §4.7 W6.5（实际出处） |
| 交付物 | 仅改名 | 三值口径 + 分母全套 + 幂等重算脚本 |

**v1 为何错误**：spec W6.5① 首句即「`dir_acc` 只保留**一个**定义。零变动点从分母**剔除**」。
v1 把 full-sample 保留为主口径，与规范正相反。

---

## 问题描述

### X9: zero-move 强制判负

`abs(delta_real) < eps → dir_ok=False`（零变动既非命中亦非失误，却被判负）。

实测占比：sr 0.3% / rb **2.0%** / m 0.7% / cj 0.5% / eg 0.2% / jd 0.7% / lh 1.0% / ss 0.3%

### X10: `dir_acc` 同名两义

| 口径 | 定义 | 当前使用位置 |
|------|------|-------------|
| **full-sample** | 所有样本，零变动算 miss | gate 判定、verdict 记录 |
| **active-only** | 仅非零变动样本 | `calc_net_metrics`、docstring 宣传 |

同一名词两个含义 → gate 消费的口径与文档宣传不一致，跨模块比较口径混乱。

---

## 裁定内容（spec W6.5）

### ① 主口径定义

**`dir_acc` 只保留一个定义：零变动点（`|Δreal| < eps`）从分母剔除。**

理由：零变动既非命中亦非失误，判负会机械压低 `dir_acc`（rb 实测 2.0%）。

### 必须同时落盘并报告（缺任一项即 verdict 不完整）

| 字段 | 含义 |
|------|------|
| `n_total` | 名义点数（剔除前） |
| `n_active` | 实际进入 `dir_acc` 分母的点数 |
| `n_zero_move` | 零变动剔除数 |
| `n_roll_excluded` | 跨换月剔除数（若启用 roll 守卫） |
| `n_zero_ratio` / `n_roll_ratio` | 上述两者占 `n_total` 的比例 |
| `dir_acc` | **主口径**（预注册约定，见下） |
| `dir_acc_full` | 不剔除任何点的原始口径 |
| `dir_acc_ex_roll` | 仅剔除跨换月、不剔零变动 |

### 主口径选定规则

- **探索运行**：使用**固定默认值**（剔零变动、**不**剔跨换月）并**记录在 verdict 中**，**不要求**预注册 —— 不阻断 L1 交付
- **确认运行**：必须在 `preregistry` **运行前**声明主口径，否则**不得确认**
- 跨换月一律作为**敏感性**单列报告
- **禁止**只剔跨换月就当作主口径 —— 不同品种/阶段的换月频率不同，会造成样本构成差异，使跨品种比较失真

### ② 其他口径收口

- active-only 口径**改名** `active_dir_acc`，**仅 gated 路径使用**，消除同名两义
- tier 的 `neff_score` 改用实测 `n_eff`；若实测后仍近乎常数（现只取 7 或 10），**从 tier 中移除该项**，不留不 discriminate 的分量制造虚假粒度
- tier 的 `prescreen_score` 改用 `jev_blind`（W6.2），切断 Z4 环路

### ③ 换月不能靠「默认不剔除」解决

必须先判定换月对 label 的影响属于**哪一类**：

| 情形 | 判据 | 处置 |
|------|------|------|
| **label 不可解释** | 跨换月 cutoff 的 `Δreal` 主要由**拼接跳变**贡献，而非真实价格变动 | **数据有效性问题**：修复（复权）或**排除**该 cutoff，**不得**留在主口径 |
| **仅敏感性** | 已复权/已修正，跨换月不改变 `Δreal` 的经济含义 | 可留在主口径，但**必须证明它不主导结果** |

**「证明不主导」的可操作定义**：报告 `dir_acc` 与 `dir_acc_ex_roll` 两值，给出两者差值及其**配对 CI**；仅当差值在多数品种上不显著、且量级远小于目标效应时，才可称「不主导」。**禁止**仅凭「默认不剔除」结案。

**量化前置**：必须先测出跨换月 cutoff 的**占比**（`n_roll_ratio`）与其对 `dir_acc` 的影响；占比不可忽略时，一律按「数据有效性问题」处理（即修复或排除），不得降级为敏感性。

---

## 历史 verdict 重算（宿主裁定：重算）

重算是**离线后处理，不需要重跑模型**：checkpoint（`data/cache/aligned_checkpoints/<variant_id>.jsonl`）逐点存有 `delta_real` 与 `dir_ok`，基线文件（`baseline_points_*.jsonl`）同样。因此 143 条 verdict 的新口径 `dir_acc` 可在**秒级**重算完成。

### 硬性要求

- 重算脚本必须**幂等**
- **只写新字段**（`dir_acc_v2` / `n_zero_move`），**不覆盖**原 `dir_acc` —— 保留原值以便对照口径差异

### 重算覆盖字段

```
dir_acc, dir_acc_full, dir_acc_ex_roll,
n_active, n_zero_move, n_roll_excluded, n_zero_ratio, n_roll_ratio,
effective_min, gate_pass,
detection_threshold_vs_random, detection_threshold_vs_baseline,
dir_acc_ci_lo/hi, delta_ci_lo/hi,
d_series_n_eff   # 有基线时可算，否则 null
```

---

## 实施步骤

### 1. `cascade/evaluation_metrics.py` — 三值计算

```python
def compute_dir_acc_variants(points):
    """计算 dir_acc 三值口径 + 分母全套。
    
    Returns:
        dict: {
            "dir_acc": 主口径（剔零变动、不剔跨换月）,
            "dir_acc_full": 不剔除任何点,
            "dir_acc_ex_roll": 仅剔跨换月,
            "n_total": ..., "n_active": ..., "n_zero_move": ...,
            "n_roll_excluded": ..., "n_zero_ratio": ..., "n_roll_ratio": ...
        }
    """
```

`calc_net_metrics` 的 active-only 返回值**改名** `active_dir_acc`（仅 gated 路径使用）。

### 2. `task_FM/evaluations/fm_eval/evaluator.py` — gate 改用主口径

- gate 消费的 `dir_acc` 改为**主口径**（剔零变动）
- 落盘三值 + 分母全套
- **注意**：`gate_pass` 会因口径变化而改变 → 需在新裁决流上验证影响面

### 3. `scripts/registry_lib.py` — schema 扩展

`VERDICT_FIELDS` 新增：
```
n_total, n_active, n_zero_move, n_roll_excluded,
n_zero_ratio, n_roll_ratio,
dir_acc_full, dir_acc_ex_roll, active_dir_acc
```

### 4. `scripts/recompute_dir_acc.py` — 幂等重算脚本（新增）

```bash
.venv/bin/python scripts/recompute_dir_acc.py \
  --registry task_FM/config/aligned_verdicts.jsonl \
  --checkpoints data/cache/aligned_checkpoints/ \
  --baselines task_FM/config/ \
  --dry-run    # 先 dry-run 核对差异，再实写
```

- 幂等：重复执行结果一致
- 只写 `dir_acc_v2` 等新字段，**不动**原 `dir_acc`
- 输出口径对照表（原口径 vs 新口径，逐品种）

### 5. 测试

- `tests/test_dir_acc_variants.py`：三值口径计算正确性（构造零变动样本）
- `tests/test_recompute_dir_acc.py`：幂等性 + 不覆盖原值
- 回归：`tests/test_praxist_fm_evaluator.py`、`tests/test_supervisor.py`

---

## 验收标准

1. `dir_acc` 主口径 = **剔零变动**（与 spec W6.5① 一致）
2. verdict 同时落盘三值 + 分母全套（缺任一项即 verdict 不完整）
3. `active_dir_acc` 改名完成，仅 gated 路径使用
4. 重算脚本幂等，且**不覆盖**原 `dir_acc`
5. 143 条历史 verdict 完成重算，产出 `dir_acc_v2`
6. rb 重算后 `dir_acc` 上升约 **+2pp**（零变动剔除效应）
7. 报告同时呈现主口径与敏感性口径，列出各类剔除数与比例
8. 跨换月影响已按 ③ 判定类别并留证据

---

## 预计工作量

| 项 | 工作量 |
|----|--------|
| 三值计算 + gate 改造 | 0.5 天 |
| schema 扩展 | 0.25 天 |
| 重算脚本 | 0.5 天 |
| 测试 | 0.5 天 |
| **总计** | **1.75 天** |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `gate_pass` 因口径变化而改变（过门率上升） | 先 dry-run 对照，量化影响面后再决定是否需重新评估门限 |
| 历史 verdict 重算后仍标 `legacy_untrusted` | spec 明确：重算**只解决口径，不解决窗口漂移**（X7/E9）；历史 verdict 仍仅用于探索记录 |
| 跨品种比较失真 | 主口径统一后仍须按 `protocol_fingerprint` 过滤；`n_zero_ratio` 差异须一并报告 |

---

## 与 spec 的一致性检查

| spec W6.5 要求 | 本档对应 | 状态 |
|---------------|---------|------|
| ① 主口径 = 剔零变动 | 「① 主口径定义」 | ✅ |
| ① 三值 + 分母全套落盘 | 「必须同时落盘并报告」表 | ✅ |
| ① 探索/确认主口径选定规则 | 「主口径选定规则」 | ✅ |
| ① 禁止只剔跨换月当主口径 | 同节末条 | ✅ |
| ② `active_dir_acc` 改名 | 「② 其他口径收口」 | ✅ |
| ② tier 收口（neff_score / prescreen_score） | 同节 | ✅ |
| ③ 换月分类判定 + 配对 CI | 「③ 换月不能靠默认不剔除解决」 | ✅ |
| 历史重算（幂等 + 不覆盖） | 「历史 verdict 重算」 | ✅ |

---

## 审核结论

**T3 v2 改档完成**，方向已依 spec W6.5 修正（宿主裁定：遵循 spec）。
实施推迟到 T1a 完成后，以便在新裁决流上验证口径变更对 `gate_pass` 的影响面。
