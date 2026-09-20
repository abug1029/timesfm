# Phase 1–2 第三轮复审

- **日期**: 2026-09-15
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **修丁范围**: `28875b5..060e15f`（`0a64221`, `741c191`, `060e15f`）
- **对照**: 第二轮复审 `2026-09-15-phase1-2-rereview.md`；changelog 附录「复审修复 (2026-09-15 第二轮)」
- **测试**: 指定套件 **72 passed**
- **结论**: **公式层上次开着的 Critical 已修好，Task 7–9 可以开。** 功效测试用两条独立二项再钉死 seed 84 去贴 p≈0.011，应换成构造的配对 +5pp。这不挡开工，但不要把这条测试和 changelog 的 APPROVE 当成规格已经锁死。

---

## 1. 上次未关项处置

| 上次 ID | 本次 | 复算 |
|---------|------|------|
| **I1 回退 `V /= T`** | **已修** | `statistical_tests.py` Bartlett 求和后有 `V /= T`。实现 p 与规格公式逐点一致（差值 < 1e-12） |
| **`fallback_n_eff` 默认 step=24** | **已修** | 无参从 `backtest_config` 读。`fallback_n_eff(588)==73`（WSL `STEP=2`） |
| **启发式缺 §9.3 词** | **已修** | 空池：`roc_x`→momentum，`holiday`→calendar，`spread_x`→term_structure，`ema_cross`→momentum |
| **`"1718413200.0"` / `pd.NaT`** | **已修** | 分别为 `1718413200` 和 `None`，不抛异常 |
| **HLN `max(1e-6, ...)`** | **已修** | 已加上 |
| **changelog 伪 APPROVE** | **过程问题仍在** | 附录把本轮也写成「独立审核通过」。那是执行者自报，不能当本文件的结论 |

C1 方差崩了 `p=1.0`、C2 FDR 污染、I2 Timestamp、I3 池键、I4 路径长度：本轮未回退，复算仍成立。

---

## 2. 功效：公式对了，测试在抽签

规格说的是**同一时间点上**变体比基线高约 5 个百分点。实现现在对这种配对序列给出 p≈0.01，和规格功效段一致。

changelog 里的 `test_diebold_mariano_p_5pp_power` 却是 **两串独立二项**，再把种子钉在 84 上：

| 种子 | 独立二项的 `d_bar` | 实现 / 规格 p |
|------|-------------------|---------------|
| 42 | 3.2pp | 0.138 |
| **84** | **6.5pp**（不是 5pp） | **0.011003**（日志写的那个数） |
| 0 | 8.3pp | 0.0014 |
| 1 | 3.2pp | 0.114 |

种子 42 会让这条测试红。种子 84 的样本提升其实是 6.5pp，不是规格的 5pp。NumPy 换版本后 RNG 一变，CI 可能无故红。

**构造配对**（同一条基线，把约 5% 的 0 翻成 1）才是规格要的实验：

- 提升 4.93pp，T=588，step=2
- 实现 p = 0.0114，规格公式同一值

公式过关。测试应改成这种构造序列，不要再绑 seed 84。

---

## 3. 其余（不挡 Task 7–9）

- `"inf"` 会进 `float()` 然后 `int(...)` 抛 `OverflowError`（只 catch 了 `ValueError`），Inner Join 可能被脏字符串打崩。`pd.NaT` 已接住；这一条还没有。
- `horizon: int = None` 类型撒谎，应是 `Optional[int]`。
- `from scipy.stats import t` 仍在文件中段。
- 缺 `symbol` 时 BH 分组键仍是 `"unknown"`，规格是 `"default"`。
- `NAME_HINTS` 里 `roc_x` / `spread_x` 多余（`roc` / `spread` 加 lookaround 已经能打中）。规格 §9.3 里 `bollinger` / `warehouse` / `dollar` 等仍未收录，当前池子走 Level 1，生产不靠它们。
- changelog 把 `V/=T` 记在 `741c191`，实际改动在 `0a64221` 的 `statistical_tests.py` 里。文首和「最终状态」仍写 APPROVE / 61 tests；本轮指定套件是 72。不要把这份日志当验收单。

---

## 4. 结论

**Ready to merge into the redesign branch:** 公式可以留下。seed 84 那条功效测试建议改完再当「规格已锁」。不要合 changelog 里的 APPROVE 叙事。  
**Task 7 registry:** Yes  
**Task 8 monthly_backtest:** Yes；无参 `fallback_n_eff` 已跟 `STEP=2`，显式传入仍更稳妥。  
**Task 9 evaluator:** Yes。上次挡 Task 9 的是缺 `V /= T`（全员假阴性 p≈0.46），这轮已按规格补上。不要把「独立二项 +5pp → p≈0.011」写进 evaluator。

不要把 changelog 里「独立审核 + 复审均通过」当成已经盖章。本文件才是第三轮独立结论：公式过关，功效测试要换构造配对序列，Phase 3 可以开工。
