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

> **⚠️ 复核 HIGH-1 修正 —— spec 的字面字段名与现有代码冲突**
>
> 复核实测：spec W6.5① 列出的 `n_total` / `n_active` 与 `active_dir_acc`
> **在代码中已存在，但语义完全不同**：
>
> | 现有字段 | 现有语义（Signal-based） | 位置 |
> |---------|------------------------|------|
> | `n_total` / `n_active` | `Signal != 0` 且 `dir_ok` 可评估的点数 | `evaluator.py:191-211` `active_mask_metrics` |
> | `active_dir_acc` | `n_ok / n_active`（gated 路径） | `evaluator.py:209` |
> | `n_zero` | `Signal == 0`（门未激活） | 同上 |
>
> 且 **143 行 registry 中已有 5 行带 `n_active`/`n_total`**；
> gated 硬门**消费 `n_active`** 做样本量判定（`evaluator.py:331-333`
> 调 `gate({"n": _n_active, ...}, min_n=350)`）。
>
> **若照 spec 字面复用这些名字，会重造本 PR 要消灭的 X10「同名两义」——
> 且发生在 gated 路径上。**
>
> **处置**：spec v15 已修订，**字段改名以避开冲突**（宿主 2026-09-28 裁定）：
>
> | spec 旧名（冲突） | spec 新名（v15） | 现有代码含义 |
> |------------------|----------------|-------------|
> | `n_total`        | **`n_dir_total`** | Signal-based：`Signal != 0` 且 `dir_ok` 可评估的点数 |
> | `n_active`       | **`n_dir_active`** | Signal-based：同上（`n_active` 在现有代码中指「激活」点数） |
> | `n_zero_move`    | `n_zero_move`（保留） | 新字段，无冲突 |
> | `n_roll_excluded` | `n_roll_excluded`（保留） | 新字段，无冲突 |
> | `n_zero_ratio` / `n_roll_ratio` | 保留 | 引用 `n_dir_total`（新名） |
>
> `_dir_` 前缀标明是**方向口径**分母，与现有 Signal-based 计数器区分。
> 此裁定与 T3 修订同步落入 spec v15（§4.7 W6.5）；原嵌套对象方案弃用。

| spec 名称（v15 后） | 落盘路径 | 含义 |
|--------------------|---------|------|
| `n_dir_total` | 顶层新字段 | 名义点数（剔除前） |
| `n_dir_active` | 顶层新字段 | 实际进入 `dir_acc` 分母的点数（零变动剔除后） |
| `n_zero_move` | 顶层新字段 | 零变动剔除数 |
| `n_roll_excluded` | 顶层新字段 | 跨换月剔除数（若启用 roll 守卫） |
| `n_zero_ratio` / `n_roll_ratio` | 顶层新字段 | 上述两者占 `n_dir_total` 的比例 |
| `dir_acc` | 顶层（**已存在**） | **主口径**（预注册约定，见下） |
| `dir_acc_full` | 顶层（**已存在**） | 不剔除任何点的原始口径 |
| `dir_acc_ex_roll` | 顶层（**已存在**） | 仅剔除跨换月、不剔零变动 |

> **`n_zero_move` 命名提示**：现有 `n_zero` 意为「`Signal == 0`，门未激活」，
> 与本项「`|Δreal| < eps`」无关。两者并存时须在 schema 注释中显式区分
> （或考虑 `n_flat_real`，见复核 LOW-4）。

### 已落地 vs 新增（复核 MEDIUM-4 修正）

> 原稿把三值机制整体列为新交付物 —— **不实**。复核实测：
> `cascade/evaluation_metrics.py:399-480`（`calc_prediction_quality`）
> **已返回** `dir_acc` / `dir_acc_full` / `dir_acc_ex_roll` /
> `n_roll_excluded` / `n_roll_ratio`，且 `dir_acc_full = dir_acc`（:459）。
>
> **实际缺口只有三项**：
> 1. 主口径方向（现 `dir_acc` 仍为 full-sample）
> 2. 四个分母字段（`n_total`/`n_active`/`n_zero_move`/`n_zero_ratio`）
> 3. gate 接线



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

**跨品种汇总的声明要求（复核 MEDIUM-6 补录）**：

spec §5.3 测试 #22（其权威引用指向 §4.7 W6.5③）要求：**跨品种汇总必须声明是「描述性审计结论」还是「正式推断」** —— 后者需跨品种不确定性处理，属「结论仅限品种内」的**显式例外**。

> ⚠️ **spec 内部归属不一致（须提请宿主）**：该句在 §4.7 W6.5③ 的**正文中不存在**（正文只有换月分类表 + 配对 CI 定义），却出现在 §5.3 测试 #22 并引用 W6.5③。本档按「要求真实存在」处理，同时登记该归属矛盾待 spec 修订。

**落地要求**：跨品种换月影响汇总表须带 `claim_type` 字段，取值为 `descriptive`（描述性审计）或 `inferential`（正式推断）；取 `inferential` 时必须附跨品种不确定性处理说明，否则报告校验失败。

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

### 1. `cascade/evaluation_metrics.py` — 扩展 `calc_prediction_quality`

> **⚠️ 复核 MEDIUM-4 修正 —— 不得新建第二个函数**
>
> 原稿提议新建 `compute_dir_acc_variants()`。但复核实测：
> `calc_prediction_quality`（`:399-480`）**已返回**三值中的全部字段。
> 新建第二个函数从同一批 points 计算同一口径 = **第二个事实来源** ——
> 与 X10 同类缺陷。**必须扩展既有函数，不得另起。**

**改动**：

```python
# cascade/evaluation_metrics.py — calc_prediction_quality 内
# (1) 主口径方向：dir_acc 改为「剔零变动」
zero_move = np.abs(delta_real_arr) < EPS
keep_active = ~zero_move
dir_acc = float(np.mean(dir_ok[keep_active])) if keep_active.any() else float("nan")

# (2) dir_acc_full 保持「不剔除任何点」（现为 dir_acc 的别名 → 改为独立计算）
dir_acc_full = float(np.mean(dir_ok))

# (3) dir_acc_ex_roll 保持「仅剔跨换月」（现有逻辑不变）

# (4) 新增方向口径分母计数（v15 字段名：n_dir_total/n_dir_active，避免与 Signal-based n_active/n_total 冲突）
n_dir_total = int(n)
n_dir_active = int(keep_active.sum())
n_zero_move = int(zero_move.sum())
# n_roll_excluded, n_roll_ratio 已在上方计算（现有逻辑不变）
n_zero_ratio = float(n_zero_move / n_dir_total) if n_dir_total else 0.0
```

**关于 `active_dir_acc` 改名（复核 HIGH-1 修正）**：

原稿称「`calc_net_metrics` 的 active-only 返回值改名 `active_dir_acc`」—— **两处不实**：

1. `calc_net_metrics`（`evaluation_metrics.py:29`）**没有**名为 active-only 的返回值；
   它的 active-only 输出是键 **`DirAcc`**（`:164`），口径为
   `active_mask = (dirs != 0) & (rets != 0)`（`:144`）——**第三种定义**
2. `active_dir_acc` 这个名字**已被占用**（`evaluator.py:209`，Signal-based）

**处置**：`calc_net_metrics` 的 `DirAcc` **保持原名不动**（其消费者
`scripts/a2_p1_lgbm_baseline.py:186-190` 与 `tests/test_evaluation_metrics_contract.py`
依赖它）；`evaluator.py:209` 的 `active_dir_acc` 也保持。spec W6.5② 的「改名」
意图是**消除同名两义**，而现状是**三个不同口径各占其名**，已无同名冲突 ——
**故本项无需改动，但须在报告中显式登记三个口径的名称与定义边界**。



### 2. `task_FM/evaluations/fm_eval/evaluator.py` — gate 改用主口径

- gate 消费的 `dir_acc` 改为**主口径**（剔零变动）
- 落盘三值 + 分母全套
- **注意**：`gate_pass` 会因口径变化而改变 → 需在新裁决流上验证影响面

### 3. `scripts/registry_lib.py` — schema 扩展

> **⚠️ 复核 HIGH-2 修正 —— 原稿指向错误的 schema 常量**
>
> 复核实测：**143 行 registry 全部为 `schema == "fm.aligned_verdict.v2"`**，
> 而 `registry_lib.py:180-183` 将 v2 裁决路由到 `validate_verdict_v2`，
> 该校验依据 **`VERDICT_FIELDS_V2`**（:21 起），**不是** `VERDICT_FIELDS`（:8，v1 遗留 15 字段集）。
>
> **两个后果**：
> 1. 原稿列的 `dir_acc_full` / `dir_acc_ex_roll` / `n_roll_excluded` / `n_roll_ratio`
>    **已在 `VERDICT_FIELDS_V2` 中**（:21, :35）→ 四个"新增"是 no-op，证明基线盘点过期
> 2. `active_dir_acc` **仅在 gated 变体写入**（`evaluator.py:462`，`gm is not None` 时）。
>    若只加入 `VERDICT_FIELDS_V2` 而不加入 **`VERDICT_FIELDS_V2_NULLABLE`**，
>    则 `validate_verdict_v2` 的 `nullable_ok = missing - VERDICT_FIELDS_V2_NULLABLE`
>    非空 → **每一个非 gated 裁决写入都会抛 ValueError**

**正确目标**：`VERDICT_FIELDS_V2` + `VERDICT_FIELDS_V2_NULLABLE`（均在 `scripts/registry_lib.py`）

新增字段及 nullable 归属：

| 字段 | 加入 `VERDICT_FIELDS_V2` | 加入 `..._NULLABLE` | 理由 |
|------|:---:|:---:|------|
| `n_dir_total` | ✅ | ✅ | 非 gated 运行可能不产出全部分母 |
| `n_dir_active` | ✅ | ✅ | 同上 |
| `n_zero_move` | ✅ | ✅ | 同上 |
| `n_zero_ratio` | ✅ | ✅ | 同上
| `dir_acc_v2` | ✅ | ✅ | 仅重算脚本写入 |
| `gate_basis` | ✅ | ✅ | 已存在于 verdict（`evaluator.py:462`），补登记 |
| `active_dir_acc` | ✅ | ✅ | **必须 nullable** —— 仅 gated 变体有 |
| `dir_acc_full` / `dir_acc_ex_roll` | 已在 | 已在 | no-op |
| `n_roll_excluded` / `n_roll_ratio` | 已在 | 已在 | no-op |

> **复核 LOW-3 提示**：`validate_verdict_v2` 只检查**缺字段**，未知多余字段可通过。
> 但登记进 schema 才能保持 schema 为唯一事实来源。



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

**新增：**

- `tests/test_dir_acc_caliber_v15.py （建议改名为 test_dir_acc_denominators.py）`：三值口径 + 分母全套正确性（构造含零变动的样本）
  - 黄金用例：real deltas `[0, +5, 0]` → `dir_acc == 1.0`、`n_zero_move == 2`、
    `n_active == 1`、`dir_acc_full == 1/3`（spec W6.5① 的直接断言）
- `tests/test_recompute_dir_acc.py`：幂等性 + **不覆盖**原 `dir_acc`

**必须更新（复核 MEDIUM-5 补录 —— 原稿遗漏）：**

| 文件 | 为何必须改 |
|------|-----------|
| `tests/test_evaluation_metrics.py:55` | `test_calc_prediction_quality_dir_ok_zero_delta` **显式断言旧主口径**：输入 real deltas `[0, +5, 0]` 时期望 `dir_acc == 1/3`。新口径下应为 `1.0` → **该测试必然失败**，须改写为新口径的**首要正向测试** |
| `tests/test_fm_evaluator_gated.py:120-180` | 断言 `n_active`/`n_total` 语义与 gate 结果；若 gated 路径口径变动则含义翻转 |
| `tests/test_evaluation_metrics_contract.py` | 消费 `calc_net_metrics` 的 `DirAcc` |

**回归：**

- `tests/test_praxist_fm_evaluator.py`、`tests/test_supervisor.py`

**执行顺序**：先改上述 3 个「必须更新」测试 → 再改实现 → 全绿后提交。
（禁止先改实现再补测试 —— 那会让失败被误读为回归。）

### 5b. gated vs 非 gated 路径的口径归属（复核 MEDIUM-6 澄清）

> 原稿只说「gate 消费的 `dir_acc` 改为主口径」，未区分路径。实测现状：

| 路径 | 现消费 | 本 PR 后 |
|------|--------|---------|
| **非 gated** gate | full-sample `dir_acc`（`evaluator.py:330`） | **主口径**（剔零变动）—— 本 PR 的目标 |
| **gated** gate | `active_dir_acc`（`evaluator.py:346`） | **不变** |

**gated 路径不变的理由**：`active_dir_acc` 是 Signal-based 口径（`Signal != 0`），
与「零变动剔除」是**不同的筛选轴**；两者混用会让 `n_active` 的语义再次漂移。

**须同步更新**：`tests/test_fm_evaluator_gated.py` 的
`test_gate_uses_n_active_not_n_total` 与 `test_gate_active_can_pass_when_full_fails`
在本 PR 后**语义不变**（gated 路径未动），但须在测试 docstring 中显式声明
「此路径不受 dir_acc 主口径变更影响」，防止未来误改。



---

## 验收标准

1. `dir_acc` 主口径 = **剔零变动**（与 spec W6.5① 一致）
2. verdict 同时落盘三值 + 分母全套（缺任一项即 verdict 不完整）
3. `active_dir_acc` 改名完成，仅 gated 路径使用
4. 重算脚本幂等，且**不覆盖**原 `dir_acc`
5. 143 条历史 verdict 完成重算，产出 `dir_acc_v2`
6. rb 重算后 `dir_acc` 上升约 **+1pp**（复核 MEDIUM-3 修正 —— 原稿写 +2pp，
   **算术不可达**。实测 rb 冻结 registry 均值 `dir_acc = 0.4661`（n=19），
   零变动占比 2.0% → `0.4661 / 0.98 = 0.4756`，即 **+0.95pp**。
   原 +2pp 需占比 ≈ 4.1%。**spec 测试 #30 同此错误，须一并提请宿主更正**）

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
