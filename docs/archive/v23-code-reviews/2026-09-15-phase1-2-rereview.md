# Phase 1–2 复审报告（对照上次审核意见的修丁）

- **日期**: 2026-09-15
- **对象**: WSL `/home/abug/timesfm` 分支 `feat/prediction-quality-redesign-v23`
- **修丁范围**: `4dabd95..28875b5`（4 个 commit）
- **对照**:
  - 上次审核: `docs/superpowers/2026-09-15-phase1-2-code-review.md`
  - 执行日志附录: `CHANGELOG-Phase1-2.md`「独立代码审核修复」
  - 规格 §4.2.2 / §4.2.3 / §9.3 / §9.4
- **测试**: `.venv/bin/python -m pytest` 指定套件 **67 passed**
- **结论**: **C1、C2、I4 已修好；I2/I3 部分修好。I1 修丁时丢掉了 `V /= T`，DM 功效塌掉，Task 9 仍不能开。**

---

## 1. 上次意见处置

| ID | 上次判定 | 本次 | 证据 |
|----|----------|------|------|
| **C1** 方差崩了打 `p=0` | Critical | **已修** | `statistical_tests.py` 约 201 行：`V<=1e-12` 一律 `return 1.0`。复算 `diebold_mariano_p([1]*200,[0]*200)==1.0`。新测试 `test_diebold_mariano_p_constant_diff_is_one` |
| **C2** 未过门小 p 污染 BH 截断点 | Critical | **已修** | `safe_p`：`gate_pass=False → 1.0`。复算 fail p=0.001 不再把 `ok_med` p=0.04 抬过线。新测试 `test_bh_fdr_gate_fail_pollutes_truncation` |
| **I1** DM 非规格；默认 step=24 | Important | **部分 / 回退** | 差分、q、γ 用 `sum/T`、HLN、从 `backtest_config` 读 STEP=2，都做了。**Bartlett 之后少了规格的 `V /= T`**（见 §2） |
| **I2** 不吃 Timestamp/datetime | Important | **部分** | naive/aware Timestamp、datetime 已对齐上海时区。`"20240615"` 现为 `None`。小数 unix 字符串、`pd.NaT` 仍有洞 |
| **I3** pool 键假绿 | Important | **部分** | Level 1 已吃 `covariates`/`pool`/list，测试改用 `custom_x`。启发式词表仍对不上规格 §9.3 |
| **I4** 路径条数 IndexError | Important | **已修** | `shape[0] != n` 先抛 `ValueError` |
| **leftover** `fallback_n_eff` 默认 step=24 | Important | **未修** | 无参 `fallback_n_eff(588)==588`；传入真实 STEP=2 才是 73 |
| **leftover** changelog 伪 APPROVE | 过程 | **未修** | 文首仍「代码审核通过」；附录把 I1 写成已完全修复 |

修丁 commit：

| Commit | 声称 | 实际 |
|--------|------|------|
| `49f4dde` | C1+C2+I1 | C1/C2 真修了；I1 重写时**丢掉了旧代码里已有的 `V = V / T`** |
| `08671ca` | I3 | Level 1 池格式已修 |
| `256f67c` | I4 | 已修 |
| `28875b5` | I2 | Timestamp/datetime 已修 |

---

## 2. 仍必须修：DM 少了 `V /= T`

规格 §4.2.2：

```python
V = gamma[0]
for j in range(1, q + 1):
    V += 2 * (1 - j / (q + 1)) * gamma[j]
V /= T          # 均值的方差；当前实现没有这一行
if V <= 1e-12:
    return 1.0
dm = d_bar / np.sqrt(V)
```

现在 γ 已经 `/T`（半正定那一半做对了），但统计量用的是 `d_bar / sqrt(ω̂)`，不是 `d_bar / sqrt(ω̂/T)`。DM 偏小约 `√T`。`49f4dde` 之前的旧实现**有** `V = V / T`，重写 I1 时弄丢了。

独立复算（`horizon=24, step=2`）：

| 场景 | 当前实现 p | 规格公式 p |
|------|------------|------------|
| 全 1 vs 全 0（C1） | 1.0 | 1.0 |
| T=200，变体 100% vs 基线 50%（现有「显著改善」测试） | 极小（测试仍绿） | 更小 |
| T=588，大约 +5pp（规格功效段） | **0.46** | **0.011** |

规格写的就是「+5pp 时单侧 p 约 0.01–0.02，能过 FDR q=0.10」。当前实现这条路径过不了门，晋级会整批假阴性。现有测试用 50 个百分点的差距，把 `√T` 倍缩小之后仍显著，所以 67 个测试全绿也测不出来。

**修法**（最小）：

1. Bartlett 求和之后、`if V <= 1e-12` **之前**加 `V /= T`。
2. HLN 内层按规格加 `max(1e-6, ...)`。
3. 回归：T=588、重叠抽样、大约 +5pp，断言规格口径 `p < 0.05`（当前实现约 0.46，这条现在就该红）。
4. 不要再用「全对打全错」或「100% vs 50%」当功效测试。

---

## 3. 其余未关项（不挡 Task 7，挡默认 n_eff）

**`fallback_n_eff` 默认仍是 `step=24`。** DM 已经改成读 `backtest_config`（WSL `STEP=2`），n_eff 没有跟。无参调用会把 588 点当成 588 个有效样本，`n_eff>=50` 等于没设。Task 8 必须写 `fallback_n_eff(n, HORIZON, STEP)`；更好是默认 `None` 时和 DM 一样去读配置，并加断言 `fallback_n_eff(588)==73`。

**启发式词表仍不是规格 §9.3。** 空池下 `roc_x` / `ema_cross` / `holiday` / `spread_x` 仍是 `"unknown"`。池键假绿已修，这条没修。迁移时 `families_hit` 会被抽空。

**时间戳边角：** `"1718413200.0"` 现为 `None`（规格允许一个小数点）；`pd.NaT` 会抛异常而不是返回 `None`，脏 checkpoint 可能打断 Inner Join。

**changelog：** 附录把 I1 勾成做完，文首 APPROVE 还在。不要把这份日志交给 Task 9 当验收依据。

---

## 4. 这一轮做得对的地方

- C1/C2 按上次给的修法落地，并且补了会失败的负面用例。
- DM 差分方向、滞后阶、γ 的 `/T`、HLN 因子、单侧 `t.sf(+dm_adj)`、参数名、默认读 `STEP=2`，方向都对，只差均值方差那一除。
- Timestamp 时区路径与 `"20240615"` 防护是对的。
- I3 测试不再靠 `"atr"` 蒙混。
- I4 把慢环可能炸的 IndexError 收成 `ValueError`。
- 已跟踪工作区是干净的（那 48 个已进归档分支）。

---

## 5. 结论

**Ready to merge:** No  
**Task 7 (registry):** 可以开，不依赖 DM。  
**Task 8 (monthly_backtest):** 可以开，但 `n_eff` 必须显式传入 WSL 的 `HORIZON=24, STEP=2`。  
**Task 9 (evaluator / DM 配对):** **不要开**，先补 `V /= T` 和 +5pp 回归。

合入前最小集就四件事：`V /= T`、+5pp 回归、`fallback_n_eff` 默认跟配置、changelog 文首/附录的 APPROVE 拿掉并写明 I1 仍开着。
