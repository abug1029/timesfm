# Task 3 Review — 方向 2: basis 历史 OI 过滤

## Spec Compliance: PASS

| 约束 | 实际 | 判定 |
|------|------|------|
| 过滤位置: `get_basis_1h` 内部 (数据层) | `data/data_store.py:488-513`,在 `df["basis"] = ...` 之后、`return df` 之前 | ✅ |
| 阈值: P95 × 5%, OI_FLOOR_RATIO=0.05 固定 | `OI_FLOOR_RATIO = 0.05`, `np.percentile(oi_arr, 95)` | ✅ |
| 置 NaN,不删行 | `df.loc[~valid, "basis"] = np.nan`, 无 drop/remove | ✅ |
| `valid` 列新增 (bool) | `df["valid"] = valid`, 冒烟确认 dtype=bool | ✅ |
| features.py 不改 | diff 仅触及 `data/data_store.py` + `tests/test_basis_oi_filter.py` | ✅ |
| 测试 unittest.TestCase, 2 方法 | 2 个方法, `unittest.TestCase` 继承 | ✅ |
| 用 `np.percentile(oi_arr, 95)` | 实现中精确使用 | ✅ |

## Task Quality: PASS

- **代码质量**: 实现简洁,注释清晰,P95 查询带 `IS NOT NULL` 防护,空数据返回 `None` 走 fallback `0.0`。
- **测试质量**: 两个测试覆盖关键路径 — (1) 低 OI 段被过滤 + 高 OI 段保留 + 时间轴完整; (2) 全高 OI 无过滤。Mock 正确处理了 `ORDER BY dt DESC` + `iloc[::-1]` 反转语义。
- **零回归**: `features.py` 未触碰,NaN→0 回退路径不变。

## Findings

无 Critical / Important / Minor findings。

## 单测实际输出

```
test_low_oi_history_becomes_nan ... ok
test_no_filter_when_all_oi_high ... ok

Ran 2 tests in 0.045s

OK
```

## TA 冒烟实际输出

```
rows=999, basis NaN=71.7%
columns: ['dt', 'near_close', 'far_close', 'near_oi', 'far_oi', 'basis', 'valid']
valid dtype: bool

前 5 行 (2016 年, 远月 OI 6-10 手 → 全部 False/NaN):
                 dt  near_oi  far_oi  basis  valid
0  2016-08-05 09:00   389013      10    NaN  False
1  2016-08-08 13:00   347538       7    NaN  False
2  2016-08-17 11:00   252356       8    NaN  False
3  2016-08-23 22:00   200850       7    NaN  False
4  2016-08-29 09:00   172216       6    NaN  False

后 5 行 (2026-07, 远月 OI 47w+ → 全部 True/有效):
                   dt  near_oi  far_oi     basis  valid
994  2026-07-28 14:00   859700  472470  0.010413   True
995  2026-07-28 21:00   854331  472963  0.011498   True
996  2026-07-28 22:00   848889  473670  0.010764   True
997  2026-07-29 09:00   864851  477438  0.012027   True
998  2026-07-29 10:00   865308  478206  0.012752   True
```

**NaN=71.7% 判定**: 这是 TA 远月合约历史特征(2016 年 OI 仅个位数),filter 正确工作。符合 spec 设计意图,非缺陷。

## Verdict

**APPROVED** — 0 findings。实现完全符合 spec,测试通过,冒烟结果合理。
