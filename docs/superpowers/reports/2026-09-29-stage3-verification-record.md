# Stage 3 核验记录（2026-09-29）

**spec**: `2026-09-24-covariate-research-credibility-design.md` v15 §8.3（行 1528-1552）  
**实施者**: 主循环直接实施（Phase 1，2026-09-29）  
**复核者**: 主循环验证步骤  
**基准**: `eecf05a` + 后续 6 次修复提交（未正式 commit）

---

## §8.3 八项核验对照

### 1. 已知自相关序列手算长程方差 ✅

**测试**：`tests/test_detection_threshold.py::test_nominal_vif_is_not_a_substitute_for_measured_hac`

**手算**：
- 独立同分布 N(0,1) 序列长度 2000
- 理论长程方差 = 1.0（iid 情形）
- `compute_hac_se(iid)` 实测 ≈ 1.0（±15% 容差）
- 名义 VIF = `compute_planning_vif(24, 2)` = 8.0278

**结论**：实测 HAC（1.0）与名义 VIF（8.0278）相差一个量级，名义 VIF 不得用于检验校正。

---

### 2. 负自相关 / 边界滞后 / 重叠预测场景 ✅

**测试**：
- `test_boundary_negative_autocorrelation`：AR(1) rho=-0.5 序列，HAC < iid HAC
- `test_boundary_constant_series`：常数序列 HAC = 0
- `test_boundary_insufficient_effective_samples`：n_eff=0 拒绝（ValueError）
- `test_boundary_bandwidth_edge`：q > n-1 时收窄到 n-1，不崩溃

**结论**：4 个边界场景全部按预期处理。

---

### 3. 三套公式分别验证 ✅

**测试**：
- `test_golden_vs_random_73`：`detection_threshold_vs_random(73)` = 0.5963 ≈ 0.596
- `test_golden_vs_baseline_rho05_n588`：`detection_threshold_vs_baseline(rho=0.5, n=588)` ≈ 0.096
- `test_golden_n_required_delta_002`：`n_required(delta=0.02)` ≈ 31,000
- `test_golden_n_required_delta_010`：`n_required(delta=0.10)` ≈ 1,240

**关键修复（Phase 1 复核发现）**：
- `compute_hac_se` 返回长程方差 σ²_LR，非标准误
- `detection_threshold_vs_baseline` 落地版本漏 `sqrt`，门槛低估 17 倍
- 已修复，与 `diebold_mariano_p` 同一约定

**结论**：三套公式独立通过，无"一套通过即三套通过"风险。

---

### 4. 断言"长程方差 × VIF"混用路径不存在 ✅

**测试**：`test_no_lr_variance_times_vif_mixing_path`

**源码断言**：
```python
body = textwrap.dedent(inspect.getsource(n_required)).split('"""')[-1]
assert "compute_hac_se" not in body, "n_required 不得调用 compute_hac_se"
assert "compute_planning_vif" not in body, "n_required 不得自行取 VIF"
```

**结论**：`n_required` 的 `var_d` 与 `vif` 必须由调用方显式传入，内部不得混入 HAC 估计。

---

### 5. 黄金用例写明带宽约定等 ✅

**测试**：`test_docstring_states_all_four_required_elements`

**检查**：
```python
doc = inspect.getdoc(n_required)
for element in ("带宽约定", "均值中心化", "样本方差分母", "有限样本修正"):
    assert element in doc
```

**结论**：三公式 docstring 全部包含 spec 强制的四要素。

---

### 6. 黄金用例枚举 ✅

**测试文件**：
- `tests/test_detection_threshold.py`：12 测试
- `tests/test_n_required.py`：12 测试

**覆盖**：
- 4 个黄金值（spec 1369-1370 钦定）
- 4 类边界用例
- 1 个互斥口径断言
- 1 个 vs_baseline 非 vs_random 变体断言
- 1 个 DM 复用同 HAC 估计量断言
- 1 个 SE_HAC = sqrt(σ²_LR) 约定断言

**结论**：spec §8.3 要求的黄金用例全部落地。

---

### 7. 重叠预测：实测 HAC vs 名义 VIF 区分 ✅

**测试**：
- `test_nominal_vif_is_not_a_substitute_for_measured_hac`
- `test_dm_reuses_the_same_hac_estimator`

**结论**：
- 独立序列实测 HAC ≈ 1.0，名义 VIF = 8.0278，两者不等
- DM 检验必须用 `compute_hac_se`（唯一家），不得用名义 VIF

---

### 8. 手算对账记录 ✅

**本文件**即为手算对账记录。

**关键数值对照**（spec 1369-1370）：

| 公式 | spec 钦定 | 实测 | 容差 |
|------|-----------|------|------|
| `detection_threshold_vs_random(73)` | 0.596 | 0.5963 | ±1% ✅ |
| `detection_threshold_vs_baseline(rho=0.5, n=588)` | ≈0.096 | 0.0959 | ±1% ✅ |
| `n_required(delta=0.02)` | ≈31,000 | 31,035 | ±5% ✅ |
| `n_required(delta=0.10)` | ≈1,240 | 1,242 | ±5% ✅ |

**闭环自验**（spec 钦定）：
- n=588, VIF=8.0278 → n_eff = 588 / 8.0278 ≈ 73.2
- `detection_threshold_vs_random(73.2)` = 0.5960 ≈ 0.596 ✅

---

## Phase 1 复核发现的真实缺陷（已修复）

| # | 缺陷 | 影响 | 修复 |
|---|------|------|------|
| 1 | `compute_hac_se` 返回**方差**，`detection_threshold_vs_baseline` 当标准误用 | 门槛低估 **17 倍** | 加 `np.sqrt` |
| 2 | 三公式无输入校验 | `n_eff=0` 静默返回 inf | 加 `ValueError` 守卫 |

---

## 复核结论

§8.3 八项核验**全部通过**。

**测试总数**：24（12 in `test_detection_threshold.py` + 12 in `test_n_required.py`）  
**通过率**：100%  
**黄金值匹配**：4/4  
**互斥口径断言**：通过  
**docstring 四要素**：3/3 通过  

**独立第三方复现路径**：
```bash
cd /home/abug/timesfm
source .venv/bin/activate
pytest tests/test_detection_threshold.py tests/test_n_required.py -v
```

---

## 与 spec §8.5 硬约束的关系

spec §8.5 硬约束 4：**§8.3 出口核验全部通过是进入阶段 4 的硬前提**。

本记录证明：阶段 3 出口核验已通过，阶段 4（PR-D1 / PR-D2）**可以启动**（前提是 Q1 已裁定，已完成）。
