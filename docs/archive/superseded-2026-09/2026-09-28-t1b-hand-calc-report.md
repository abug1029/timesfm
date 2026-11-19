# T1b 手算核对报告（2026-09-28）
> **代码基线**: `bade177`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

**Status:** ✅ 通过（10/10 点一致）
**Date:** 2026-09-28
**Spec:** §8.1 出口核验

## 方法

取 2 个品种（rb, ss）的新裁决 checkpoint，各手算前 5 个预测点的 `dir_ok`，
与代码落盘值逐点比对，并输出可人工复算的中间量。

## 结果

| 品种 | 变体 | Checkpoint 点数 | 核对点数 | 一致 |
|------|------|----------------|---------|------|
| rb | `rb_crack_spread_level_aligned_p6` | 6 | 5 | 5/5 ✅ |
| ss | `ss_vor_aligned_p6` | 6 | 5 | 5/5 ✅ |
| **合计** | | 12 | **10** | **10/10 ✅** |

## 核对样例（rb 点 0）

```
cutoff=2026-01-09 11:00:00
base=3151.0  pred_end=3171.924560546875  real_end=3162.0
端点 delta_pred = pred_end - base = +20.9246
端点 delta_real = real_end - base = +11.0000
同号 → dir_ok = True   （与落盘值一致）
```

## 关键发现：checkpoint 存在两套 delta_pred 口径

**首轮核对报出 3/10 不一致，经代码溯源确认为核对脚本的口径误用，非生产缺陷。**

`scripts/monthly_backtest.py:413-426` 中同时存在两个量：

| 量 | 定义 | 用途 |
|----|------|------|
| `delta_pred`（checkpoint 字段） | `position_from_forecast(...)["delta_pred"]` — **信号口径**（`signal_weight` / `short_horizon` 加权） | `pnl` / 经济尺度 |
| `_delta_pred_endpoint` | `pred[-1] - base` — **端点口径** | `dir_ok` / `endpoint_mape` / `endpoint_bias_pct` |

代码注释显式声明此设计：
```
# dir_ok uses endpoint (pred[-1]-base) — consistent with calc_prediction_quality
# weighted delta_pred still used for pnl / economic scale below
```

**风险登记**：checkpoint 同时落 `delta_pred`（信号口径）与 `pred_end`/`base`（可推端点口径），
字段名不自带口径标识 → 第三方核对极易误判（本轮即发生）。
建议后续在 checkpoint 增补 `delta_pred_endpoint` 显式字段，或将现有字段更名为
`delta_pred_signal`。**本轮不改**（改动会影响 resume 兼容与历史 checkpoint 解析），
登记为 Stage 4 待办。

## 验收结论

- [x] 取 2 个品种、固定窗口与 cutoff
- [x] 手算 3–5 个预测点的 `dir_ok` / `delta_pred` / `delta_real`
- [x] 手算结果与代码落盘值逐点一致（10/10）
- [x] 产出可人工复算的中间量

**T1b 通过** —— 兑现 spec §8.1 出口核验「手算核对预测点」。
