# Task 3 Report — 方向 2: basis 历史 OI 过滤

## 改动文件

| 文件 | 动作 | 说明 |
|------|------|------|
| `data/data_store.py` | 修改 | `get_basis_1h` 末尾(line 488-513)插入合约自身 P95×5% OI 过滤 |
| `tests/test_basis_oi_filter.py` | 新建 | 2 个 unittest 测试方法 |

## 单测运行结果

```
test_low_oi_history_becomes_nan (tests.test_basis_oi_filter.TestBasisOiFilter) ... ok
test_no_filter_when_all_oi_high (tests.test_basis_oi_filter.TestBasisOiFilter) ... ok

Ran 2 tests in 0.038s

OK
```

## TA 真实数据冒烟

```
rows=999, basis NaN=71.7%
valid col present: True

早期 5 bar (2016 年,远月 OI 仅个位数 → 全部过滤):
                 dt  near_oi  far_oi  basis  valid
0  2016-08-05 09:00   389013      10    NaN  False
1  2016-08-08 13:00   347538       7    NaN  False
2  2016-08-17 11:00   252356       8    NaN  False
3  2016-08-23 22:00   200850       7    NaN  False
4  2016-08-29 09:00   172216       6    NaN  False

晚期 5 bar (2026-07,远月 OI 47w+ → 全部保留):
                   dt  near_oi  far_oi     basis  valid
994  2026-07-28 14:00   859700  472470  0.010413   True
995  2026-07-28 21:00   854331  472963  0.011498   True
996  2026-07-28 22:00   848889  473670  0.010764   True
997  2026-07-29 09:00   864851  477438  0.012027   True
998  2026-07-29 10:00   865308  478206  0.012027   True
```

**解读:** TA 历史远月合约早期 OI 只有 6-10 手(典型挂单价),被正确过滤为 NaN;
2026 年即期数据远月 OI 47w+ 手,全段保留。NaN 比例 71.7% 反映了 TA 远月合约
历史覆盖长、早期流动性极差的事实 — 符合预期。

## Commit

`1eaa2ea` — feat(basis): get_basis_1h 加合约自身 P95×5% 历史 OI 过滤 (置 NaN 抗挂单价污染)

## Concerns

**无阻塞 concerns。** 两点说明:

1. **NaN 比例偏高(71.7%)**: 这是 TA 远月合约历史特征(早期几乎无流动性),并非 bug。
   下游 `features.py:basis_momentum` 的 NaN→0 回退路径会自然处理这些点,
   walk-forward 回测中对应的历史评估点将不使用 basis_momentum 信号,符合预期。
2. **测试 mock 的 DESC/ASC 顺序**: 初版测试未考虑 SQL `ORDER BY dt DESC` + `iloc[::-1]` 的反转语义,
   已修正 mock 数据顺序以匹配真实 SQL 返回。
