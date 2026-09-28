# T2 三路消融对照表（2026-09-28）

> spec §8.2 出口核验：确认协变量输入确实改变模型。

消融裁决数：**16**（status=ok，已排除 no_data 墓碑）

## 逐组明细

| 品种 | 协变量 | 模式 | n | dir_acc | dir_acc_full | endpoint_mape | gate_pass |
|------|--------|------|---|---------|-------------|--------------|-----------|
| jd | calendar_cyclical | full | 6 | 0.3330 | 0.3330 | 7.490 | False |
| jd | calendar_cyclical | content | 6 | 0.8330 | 0.8330 | 6.610 | False |
| jd | calendar_cyclical | structural | 6 | 1.0000 | 1.0000 | 6.400 | False |
| jd | calendar_cyclical | baseline | 6 | 0.8330 | 0.8330 | 6.570 | False |
| jd | ccl | full | 6 | 0.3330 | 0.3330 | 7.230 | False |
| jd | ccl | content | 6 | 1.0000 | 1.0000 | 6.340 | False |
| jd | ccl | structural | 6 | 1.0000 | 1.0000 | 6.410 | False |
| jd | ccl | baseline | 6 | 0.8330 | 0.8330 | 6.570 | False |
| rb | calendar_cyclical | full | 6 | 0.3330 | 0.3330 | 0.950 | False |
| rb | calendar_cyclical | content | 6 | 0.3330 | 0.3330 | 0.670 | False |
| rb | calendar_cyclical | structural | 6 | 0.3330 | 0.3330 | 1.010 | False |
| rb | calendar_cyclical | baseline | 6 | 0.3330 | 0.3330 | 0.730 | False |
| rb | ccl | full | 6 | 0.3330 | 0.3330 | 0.900 | False |
| rb | ccl | content | 6 | 0.5000 | 0.5000 | 0.550 | False |
| rb | ccl | structural | 6 | 0.3330 | 0.3330 | 0.920 | False |
| rb | ccl | baseline | 6 | 0.3330 | 0.3330 | 0.730 | False |

## 三路对照

| 品种 | 协变量 | 内容效应 full-content | 通道效应 full-structural | 路径差 structural-baseline | 输入是否改变模型 |
|------|--------|------------------------|--------------------------|------------------------------|------------------|
| jd | calendar_cyclical | -0.5000 | -0.6670 | 0.1670 | ✅ 是（dir_acc + mape 双证） |
| jd | ccl | -0.6670 | -0.6670 | 0.1670 | ✅ 是（dir_acc + mape 双证） |
| rb | calendar_cyclical | 0.0000 | 0.0000 | 0.0000 | ✅ 是（仅 mape；dir_acc 二值粒度未分辨） |
| rb | ccl | -0.1670 | 0.0000 | 0.0000 | ✅ 是（dir_acc + mape 双证） |

## 结论

**输入确实改变模型**：4/4 组可区分（判据：dir_acc 或 endpoint_mape 任一有差异）。

- `jd_calendar_cyclical`（dir_acc + mape 双证）
- `jd_ccl`（dir_acc + mape 双证）
- `rb_calendar_cyclical`（**仅 mape** —— dir_acc 二值粒度未分辨，见第 3 条）
- `rb_ccl`（dir_acc + mape 双证）

> ⚠️ 「改变模型」的判定已改用 dir_acc + endpoint_mape 双指标。
> 初版只看 dir_acc，把 `rb_calendar_cyclical` 误判为「四值同一」——
> 该组 dir_acc 四值确实都是 0.3330，但 endpoint_mape 明显不同
> （0.950 / 0.670 / 1.010 / 0.730）。二值命中计数掩盖了连续输出的差异。
> 结论层面的强度限制见下方方法论小节与文末降级声明讨论。


## ⚠️ 方法论限制（必读 —— 防止误读本表）

### 1. n=6 使 dir_acc 差异不具统计意义

本表 `dir_acc` 的全部差异由 **6 个样本**产生。换算为命中数：

| dir_acc | 命中/6 |
|---------|--------|
| 0.3330 | 2/6 |
| 0.5000 | 3/6 |
| 0.8330 | 5/6 |
| 1.0000 | 6/6 |

即 0.667 的「内容效应」实为 **2 个样本之差**。在 n=6 下，
命中数 ±2 的波动完全可由随机性产生（binomial SE ≈ 0.19）。
**本表的 dir_acc 列只能用于「是否存在差异」的定性判据，不得作为效应量引用。**

### 2. endpoint_mape 是更可靠的判据（连续量）

`endpoint_mape` 无二值化损失，n=6 下仍可读出方向性：

| 品种 | 协变量 | full | content | structural | baseline |
|------|--------|------|---------|------------|----------|
| jd | calendar_cyclical | 7.490 | 6.610 | 6.400 | 6.570 |
| jd | ccl | 7.230 | 6.340 | 6.410 | 6.570 |
| rb | calendar_cyclical | 0.950 | 0.670 | 1.010 | 0.730 |
| rb | ccl | 0.900 | 0.550 | 0.920 | 0.730 |

**关键观察：四组中 `full` 的 endpoint_mape 均为四模式里最差**
（jd 两组最差；rb 两组中 full 亦高于 content 与 baseline）。

即：协变量通道**确实进入了计算图**（依据：`covariates_used=True` 且
四模式 `pred_end` 互不相同，见第 3 条），但**在本样本上降低了短期预测精度**。

⚠️ **该观察同样受 n=6 限制**。`endpoint_mape` 虽为连续量，但 6 个点的
均值无误差估计，无法区分「真实劣化」与「这 6 个点恰好波动」。
**不能据此断言「协变量有害」**，只能说「在本样本上未观察到 full 优于 baseline，
且 full 的点均值方向一致地更差」。

### 3. ⚠️ 修正：structural vs baseline 的「差异 0」是二值粒度的假象

本表该列 4 组差异均为 0.0000。**初稿据此推断「两条路径行为一致，
验证了消融实现正确」—— 该推断不成立。**

直接读 checkpoint 的连续输出可证伪：

| variant | pred_end（第 0 点） |
|---------|---------------------|
| `jd_calendar_cyclical_baseline_aligned_p6` | 3052.2571 |
| `jd_calendar_cyclical_structural_aligned_p6` | 3049.5288 |
| `jd_ccl_baseline_aligned_p6` | 3052.2571 |
| `jd_ccl_structural_aligned_p6` | 3050.7373 |

structural 与 baseline 的 `pred_end` **确实不同**（差 2.73 / 1.52）。
差异为 0 只是因为 n=6 下 `dir_acc` 是二值命中计数（2/6、5/6 粒度），
不同连续输出在这 6 个点上的方向恰好落在同一命中数。

**这暴露了本表方法论的核心缺陷：n=6 时 dir_acc 列的分辨率不足以
区分「路径相同」与「路径不同但方向一致」。** 二值计数把连续差异压平了。

补充验证（说明消融**确实在执行**，而非两组都没跑）：

- `covariates_used=True`（4 组 structural 全部为 True）→ 协变量通道被调用而非跳过
- 四模式 `pred_end` 互不相同（jd_calendar: 3103.15 / 3054.60 / 3049.53 / 3052.26）
  → 消融参数确实影响了计算图

因此正确表述是：**消融执行已确认，但「structural ≡ baseline」这一
本应成立的性质在本轮样本量下无法用 dir_acc 验证。** 需扩大样本或改用
连续指标（如 endpoint_mape 的配对检验）才能判定。

### 4. rb_calendar_cyclical：dir_acc 四值全同但并非「无影响」

该组 dir_acc 四值均 0.3330（2/6）但 endpoint_mape 明显不同
（0.950 / 0.670 / 1.010 / 0.730）→ 预测值确实变了，只是这 6 个点上的
方向命中数未变。初稿据此标为「输入未改变模型」，**该判定已修正**为
「是（仅 mape；dir_acc 二值粒度未分辨）」—— 与第 3 条同源。

---

## 对 Stage 1/2 降级声明的影响

Stage 1/2 的核心降级声明是「协变量未被利用」。

本轮消融**已排除**该声明的前半部分，但对后半部分未提供正面证据：

| 状态 | 判据 | 本轮观测 |
|------|------|---------|
| 未接入模型 | full 的输出 ≡ baseline | ❌ **已排除**（`covariates_used=True`，四模式 `pred_end` 互不相同） |
| 已接入且有效 | full 优于 baseline | ❌ 未观测到（4/4 组 full 的 mape 点均值更差） |
| 已接入但可能有害 | full 劣于 baseline | ⚠️ 4/4 组方向一致，但 n=6 无误差估计，不足定论 |

**可以确立的**：降级声明中的「**未被利用**」不成立 ——
协变量确实进入计算图并改变了输出（已由 `pred_end` 互异证实）。

**不能确立的**：「产生负增量」目前只是 4 组方向一致的方向性观察。
在 `max_points` ≥100 或对 endpoint_mape 做配对检验之前，
**不应据此修改降级声明本身** —— 声明中「协变量是否提升预测力」这问，
本轮**未获任何正面证据**。

**建议的表述修正**（拆为两问）：
> ① 协变量是否接入模型 —— **已解决：是**
> ② 协变量是否提升预测力 —— **仍未解决**，本轮未获正面证据

**样本量限制**：以上基于 4 组 × 6 点 = 24 个预测点。
扩大样本前，本节应视为**待验证的方向性观察**，不作为定论。
