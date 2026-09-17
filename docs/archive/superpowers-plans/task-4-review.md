# Task 4 审查报告 — covariate_scan 展示改名 + 3% 显著性门槛

**审查日期**: 2026-07-29
**BASE**: `1eaa2ea` → **HEAD**: `dfdc7a0`
**Diff**: +80 / -8, 2 文件 (`scripts/covariate_scan.py` + `tests/test_scan_significance.py`)

---

## Spec Compliance: ✅ PASS

逐项对照 plan §Task 4 的 10 个 Step:

| 约束 | 结果 | 证据 |
|------|------|------|
| `results.sort(key=lambda x: x[1])` 不改 (裁决锚点铁律) | ✅ | diff hunk 2: sort 行是 context line (前导空格,非 +/-),仅上方注释被扩展 |
| `significance_label` 顶层函数,独立可测 | ✅ | diff hunk 1: 定义在 line 66-79, 无类依赖 |
| 阈值 3% 固定,不暴露为参数 | ✅ | 函数默认参数 `threshold=0.03`,scan 调用处硬编码 `0.03`,无 CLI/env 暴露 |
| DirAcc(展示) 4 处一致 | ✅ | 最优行 L207 / TOP5 L212 / 表头 L299 / 推荐配置 L313 |
| 裁决锚点说明行 (2 处) | ✅ | scan_single_variety L208 + 汇总报告 L298 |
| 推荐配置每行末尾 `[label]` | ✅ | L313 `[{lbl}]` |
| summary tuple 扩 5 元 | ✅ | L309 `summary.append((symbol, best[0], best[1], best[2], lbl))` |
| `r.get('label', '无固化基线')` 从 dict 取 label | ✅ | L308 |
| 单测 4 方法 (超阈值/退化/微改善/零基线) | ✅ | 4 方法全覆盖,4/4 PASS |
| baseline_mae 查找从固化方案读取 | ✅ | L195-204 `from config.prediction_scheme import get_scheme` + try/except 兜底 |

---

## Task Quality: ✅ PASS

**代码质量**:
- `significance_label` 防除零处理 (`baseline_mae <= 0` 直接判"无显著改善") ✓
- 函数 docstring 明确说明"不改变 sort,仅加标签" ✓
- baseline 查找用 try/except 包裹,`Exception` 全捕兜底,无固化方案时降级为 "无固化基线" ✓
- 子进程入口 (run_isolated) 通过 JSON roundtrip,dict 新增字段向后兼容 ✓

**测试质量**:
- 4 个方法覆盖边界: ≥阈值 / 退化 (best>baseline) / 微改善 (0.6%) / 零基线
- 无 mock, 纯函数测试, 快速 (0.35s) ✓

---

## Findings

### Minor

**M1. 表头与数据列宽不一致 (DirAcc(展示) 列)**
- 表头: `{"DirAcc(展示)":>14s}` (14 字符宽)
- 数据行: `{best[2]:>13.0%}` (13 字符宽)
- 影响: 纯视觉对齐瑕疵,不影响功能/逻辑。表头比数据列宽 1 字符,在宽屏终端下可能不易察觉。
- 修复建议: 统一为 14 或 13,如 `{best[2]:>14.0%}`。
- 严重性: Minor — 不阻塞合并。

---

## 单测实际输出

```
test_micro_improvement_below_threshold ... ok
test_rel_drop_above_threshold_is_significant ... ok
test_rel_drop_below_threshold_is_insignificant ... ok
test_zero_baseline_edge ... ok

Ran 4 tests in 0.350s
OK
```

**4/4 PASS** ✓

## Sort 回归验证实际输出

```
sort 未变, best= ('bb_squeeze', 2.444, 0.56, 7)
label = 无显著改善(<3%)
```

- sort 仍按 MAE 升序,best = `bb_squeeze` (MAE=2.444) ✓
- baseline=best 自身时 rel_drop=0 → "无显著改善(<3%)" ✓
- **裁决锚点铁律未被破坏** ✓

---

## Final Verdict

**APPROVED** — 0 Critical / 0 Important / 1 Minor (列宽视觉瑕疵,不阻塞)。

所有 spec 约束遵守;sort 铁律未被触碰;`significance_label` 独立可测;4/4 单测 PASS;sort 回归验证 PASS;summary tuple 5 元扩展与 `r.get('label', '无固化基线')` 处理 dict/list 形态差异正确。
