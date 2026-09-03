# Task 4 实施报告 — covariate_scan 展示改名 + 3% 显著性门槛

**状态**: ✅ 完成
**日期**: 2026-07-29

## 改动文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/covariate_scan.py` | 修改 | 加 `significance_label` 顶层函数；scan_single_variety 输出区加 baseline_mae/label；4 处 DirAcc→DirAcc(展示)；汇总区加裁决锚点说明；推荐配置加 [label] |
| `tests/test_scan_significance.py` | 新建 | 4 个 unittest 方法覆盖 significance_label 的 4 种输入组合 |

## 关键约束遵守

- ✅ `results.sort(key=lambda x: x[1])` **未改** (裁决锚点铁律)
- ✅ `significance_label` 独立可测 (不依赖 scan 跑模型)
- ✅ 阈值 3% 固定, 不暴露为参数
- ✅ DirAcc(展示) 在 4 处一致: 最优行 / TOP5 / 表头 / 推荐配置
- ✅ 裁决锚点说明行: scan_single_variety 输出 + 汇总报告 stdout 各一处

## 单测结果

```
Ran 4 tests in 0.453s
OK
```

4 个方法:
- `test_rel_drop_above_threshold_is_significant`: baseline 5%→best 4.5% (rel_drop=10%≥3%) → "显著改善"
- `test_rel_drop_below_threshold_is_insignificant`: baseline 2.444%→best 2.518% (退化) → "无显著改善(<3%)"
- `test_micro_improvement_below_threshold`: baseline 5%→best 4.97% (rel_drop=0.6%<3%) → "无显著改善(<3%)"
- `test_zero_baseline_edge`: baseline=0 → "无显著改善(<3%)" (防除零)

## 冒烟验证

```bash
PYTHONIOENCODING=utf-8 python scripts/covariate_scan.py ta --points 1
```

输出节选 (关键行):

```
--- TA ---
  评估点: 1 个
    #1: idx=9989, base=6022
  最优: ccl                   MAE=1.66%  DirAcc(展示)=100%  [显著改善]
    * 裁决锚点: 24h MAE 相对下降率 vs 当前固化方案 (DirAcc 仅展示,不参与裁决)
  TOP 5:
    #1 ccl                 : MAE=1.66%  DirAcc(展示)=100%
    ...

[3/3] 汇总报告
  裁决锚点: 24h MAE 相对下降率 vs 当前固化方案 (DirAcc 仅展示,不参与裁决) | 阈值 3%

  品种 |                最优协变量 |  24h MAE |     DirAcc(展示) |                   次优 |   次优 MAE
----------------------------------------------------------------------------------------------------
  TA |                  ccl |    1.66% |          100% |         hourly_slope |    1.66%

推荐配置更新 (按 24h MAE 最优):
  "ta": covariate_type="ccl",  # 24h MAE=1.66% DirAcc(展示)=100% [显著改善]
```

exit=0。

**解读**: TA 当前固化基线是 `bb_squeeze` (1pt 评估下 MAE≈2%+),ccl 以 1.66% 胜出,rel_drop>3%,标签为"显著改善"。这与"全量 7pt 评估下 bb_squeeze 为 TA 最优"的结论不矛盾 — 1pt 样本方差大,只验证输出格式/标签逻辑正确。

## Sort 回归检查

```python
results = [('basis_momentum', 2.518, 0.57, 7), ('bb_squeeze', 2.444, 0.56, 7), ('ccl', 3.10, 0.43, 7)]
results.sort(key=lambda x: x[1])
assert results[0][0] == 'bb_squeeze'  # sort 仍按 MAE 升序
```

PASS: `best=('bb_squeeze', 2.444, 0.56, 7)`, sort 未变。

## Concerns

**无重大 concern**。唯一需要 reviewer 留意的点:

**summary tuple 5 元 vs dict 形态差异处理**:
- `scan_single_variety` 返回 dict (`{'results', 'best', 'n_eval_points', 'baseline_mae', 'label'}`)
- 汇总循环里 `best = r['best']` 是 list (JSON roundtrip 后 tuple→list)
- 用 `r.get('label', '无固化基线')` 从 dict 顶层取 label,然后 `summary.append((symbol, best[0], best[1], best[2], lbl))` 扩为 5 元
- 推荐配置 `for symbol, cov, mae, da, lbl in summary` 解包

选择 `r.get('label')` 而非 `best['label']` (best 是 list 不能 key access) — 这与 plan Step 7 inline 注释提醒一致,实施已正确处理。

## Commit

`dfdc7a0` — `feat(scan): DirAcc 改名(展示)+ 3% 显著性门槛标签 (裁决仍按 MAE 不变)`

2 files changed, 80 insertions(+), 8 deletions(-)
