# 参数卫生裁决（G004）

| CF | 裁决 | 动作 |
|----|------|------|
| CF-03 scheme_type | **C** 文档：历史分类标签，不保证当前 DirAcc/decay | 见下 |
| CF-06 双开关 | **C** 单测防非法组合 + 文档 | `tests/test_signal_mode_mutex.py` |
| CF-07 short+decay | **A** short 时 decay 不参与权重 | signal_weight 已如此 |
| CF-08 confidence_multiplier | **C** 冻结现状 + 注释来源 | 不批量重置 |
| CF-15 clip_gap | **A** 报告/docstring 强制说明 | monthly 已注 |
| CF-24 checkpoint | **B** 单 writer 运维约定 | monthly 注释 |

## scheme_type 说明

`scheme_type`（trend/stable/short_range/oscillation）来自早期月度分类，**可能与当前 dir_acc/decay 不一致**。读盘以 stars + cov + PF 为准。
