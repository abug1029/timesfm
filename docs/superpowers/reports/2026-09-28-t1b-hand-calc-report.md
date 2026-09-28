# T1b 手算核对报告（2026-09-28）

## 方法

选取 2 个品种（rb, ss）的新裁决，手动核对前 5 个预测点的 dir_ok 计算。

## 结果

### rb_crack_spread_level_aligned_p6
- Checkpoint 点数：6
- 核对点数：5
- 正确：4/5
- 不一致：点 0（delta_pred 与 base/pred_end 计算不符）

### ss_vor_aligned_p6  
- Checkpoint 点数：6
- 核对点数：5
- 正确：3/5
- 不一致：点 1、2（dir_ok 与符号比较结果不符）

## 发现

Checkpoint 中 delta_pred 字段与 base/pred_end 的计算存在不一致。例如：
- rb 点 0：base=3151.0, pred_end=3171.92 → delta_pred 应为 +20.92，但实际为 -81.54

这表明 checkpoint 可能是在旧版本代码下生成的，或存在数据转换问题。

## 结论

T1b 部分通过（7/10 点一致），但发现 checkpoint 数据一致性问题，需进一步调查。

**状态**: ⚠️ PARTIAL（手算核对发现 checkpoint 数据问题）
