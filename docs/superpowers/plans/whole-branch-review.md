# Whole-Branch Review — 4 方向优化 (3205cae → dfdc7a0)

**Reviewer:** whole-branch code reviewer subagent
**Date:** 2026-07-29
**Commits:** 5 task commits + 1 plan commit
**Diff:** 7 files, +322/-13 lines

---

## Overall Verdict

**APPROVED**

0 Critical / 0 Important / 1 Minor (deferred from Task 4)。全部 4 方向实现符合 spec,零回归铁律验证通过,6/6 单测全 PASS,跨 task 无冲突。

---

## Cross-Task Coherence: ✅ 无问题

四个 task 改动 7 个文件,两两无交集:

| Task | 文件 | 与其他 Task 交叉 |
|------|------|:---:|
| 1 (归档) | `config/prediction_scheme.py`, `STATE.md` | 无 |
| 2 (backtest CLI) | `scripts/monthly_backtest.py` | 无 |
| 3 (OI 过滤) | `data/data_store.py` | 无 |
| 4 (scan 显著性) | `scripts/covariate_scan.py` | 无 |
| 测试 | `tests/test_basis_oi_filter.py`, `tests/test_scan_significance.py` | 无 |

**唯一的跨 task 读取路径**：Task 4 的 `scan_single_variety` 在 line 197-204 import `config.prediction_scheme.get_scheme` 读取固化方案 → Task 1 在 `prediction_scheme.py` 仅追加了注释,**未改 `covariate_type` 值或 SCHEMES 字典结构**,读取路径安全。

**命名/风格一致性**: 4 个 task 均遵守仓库既有风格 — 手写 CLI 解析(无 argparse 新增)、局部 import (`import json as _json` / `from pathlib import Path`)、`# ──` 注释分隔符、`unittest.TestCase` 测试类。无命名冲突。

**错误处理一致性**: Task 2 的 resume JSONL 解析用 `try/except (_json.JSONDecodeError, KeyError)`;Task 4 的 baseline 查找用 `try/except Exception` 兜底;Task 3 的 P95 查询对空数据返回 `None` 走 fallback `0.0`。三处降级行为均合理,不会 crash。

---

## Spec Coverage: ✅ 完整

| Spec 方向 | Plan Task | Diff 文件 | 覆盖 |
|-----------|-----------|-----------|:---:|
| §1 方向 1 — 单进程长跑治理 (`--cache-interval` / `--max-points` / `--resume` JSONL) | Task 2 | `scripts/monthly_backtest.py` (+91/-4) | ✅ |
| §2 方向 2 — basis OI 过滤 (P95×5%, 置 NaN 不删行) | Task 3 | `data/data_store.py` (+26), `tests/test_basis_oi_filter.py` (+104) | ✅ |
| §3 方向 3 — scan 展示去误导 + 3% 显著性门槛 | Task 4 | `scripts/covariate_scan.py` (+50/-8), `tests/test_scan_significance.py` (+38) | ✅ |
| §4 方向 4 — TA 归档注释 + STATE 路线图 | Task 1 | `config/prediction_scheme.py` (+5), `STATE.md` (+21/-1) | ✅ |
| §5 Out of scope (Daemon / Phase 4/7/8/9 实现) | 无 | 无 | ✅ 未触碰 |

**Spec 7 验收标准逐条:**
1. ✅ `--max-points 10 cf` 跑通 (冒烟 `cf --max-points 2` exit 0);`--resume` 跳过已完成 (Task 2 re-review 验证);无参数行为一致 (Task 2 R1 fix 确认);JSONL 格式 4 字段 schema 正确
2. ✅ `test_basis_oi_filter.py` 2/2 PASS;TA 冒烟 NaN=71.7% 符合预期
3. ✅ `test_scan_significance.py` 4/4 PASS;scan 输出含 `[显著改善]` / `[无显著改善(<3%)]` 标签;DirAcc 列 4 处改名
4. ✅ prediction_scheme.py 含 5 行归档注释;STATE.md 路线图已更新

---

## Zero-Regression 验证: ✅ 通过

| 验证项 | 结果 |
|--------|------|
| 单测 6/6 PASS (`test_basis_oi_filter` 2 + `test_scan_significance` 4) | ✅ |
| `prediction_scheme` import + `TA covariate_type=='bb_squeeze'` | ✅ `TA scheme OK: bb_squeeze` |
| `monthly_backtest.py cf --max-points 2` 无参数时不创建 checkpoint | ✅ 运行前后 checkpoint 文件数不变 (1→1,无新增);stdout 无 `[checkpoint]` 消息 (`grep -c "checkpoint"` exit 1) |
| `covariate_scan.py ta --points 1` 输出含 DirAcc(展示) + 裁决锚点 + [显著改善] | ✅ |
| `results.sort(key=lambda x: x[1])` 未被修改 | ✅ diff hunk 中 sort 行是 context line (前导空格,非 +/-) |
| `config/prediction_scheme.py` 仅追加注释,无非注释行改动 | ✅ `git diff` 过滤 `^[+-]` + 排除 `^#` 后无非注释变更 |
| 下游脚本 `covariate_advisor.py` / `diracc_optimizer.py` 不受影响 | ✅ 两者均解析旧格式 (per-covariate `|` 表 / `T+1=` 行),与当前 scan 输出格式本就不匹配,本次改名未引入新 break |

---

## 高风险路径保护: ✅ 通过

`config/prediction_scheme.py` 是 `loop-constraints.md` 标注的高风险路径。

**Task 1 改动审计:**
- diff 仅含 5 行 `+` 行,全部以 `#` 开头 (注释)
- `covariate_type="bb_squeeze"` 值未改
- `SCHEMES` 字典无新增/删除品种,`VarietyScheme` 字段值无变动
- TA scheme 块其它 13 个字段 (`symbol/name/scheme_type/stars/dir_acc/mape/decay/coverage/use_full_signal/short_horizon_only/confidence_multiplier/xreg_covariates`) 均未在 diff 中出现

**结论:** 高风险路径保护未被违反。

---

## Findings

### Critical: 无

### Important: 无

### Minor

**M1. 汇总报告表头与数据列宽 1 字符不对齐 (Task 4)**
- **位置:** `scripts/covariate_scan.py` line 302 vs 313
- 表头: `{"DirAcc(展示)":>14s}` (14 字符宽)
- 数据: `{best[2]:>13.0%}` (13 字符宽)
- **影响:** 纯视觉对齐瑕疵,不影响功能/逻辑/下游解析
- **来源:** task-4-review.md Minor-1
- **裁决:** 留 TODO,不阻塞合并。修复方案: 统一为 `>14` 或 `>13`

---

## Deferred Findings 汇总 (从 4 个 task reviews)

| 来源 | Finding | 严重性 | 裁决 |
|------|---------|--------|------|
| task-1-review | 无 findings | — | — |
| task-2-review | Important-1: 无 `--resume` 时自动创建 checkpoint | Important | ✅ **已修复** (commit `02daa46`),task-2-rereview APPROVED |
| task-3-review | 无 findings | — | — |
| task-4-review | M1: 表头 14s vs 数据 13s 列宽瑕疵 | Minor | **留 TODO**,不阻塞 |

**现在修 vs 留 TODO:**
- **现在修:** 无 (唯一的 Important 已修复)
- **留 TODO:** M1 列宽瑕疵 — 纯视觉,不影响功能或下游脚本,可在下次碰触 covariate_scan.py 时顺手修

---

## Test Coverage 评估: 充分

| 方向 | 测试 | 覆盖核心逻辑 | 评估 |
|------|------|:---:|:---:|
| 方向 1 (backtest CLI) | 无单测 (spec 设计: CLI 冒烟替代) | — | ✅ 合理 (回测依赖 TqSdk 数据,单测不可行) |
| 方向 2 (OI 过滤) | `test_basis_oi_filter.py` 2 方法 | ✅ 低 OI→NaN + 全高 OI→无 NaN | ✅ 充分 |
| 方向 3 (显著性) | `test_scan_significance.py` 4 方法 | ✅ 超阈值/退化/微改善/零基线 | ✅ 充分 |
| 方向 4 (归档) | 无测试 (纯文档变更) | — | ✅ 合理 |

**未覆盖路径 (可接受,不阻塞):**
- Task 2 CLI 参数组合 (`--cache-interval` + `--max-points` + `--resume` 三者组合): 冒烟覆盖了两两组合,三参数组合逻辑是简单的正交传递,无需额外测试
- Task 3 `get_basis_1h` 被 `features.py:basis_momentum` 消费后的 NaN→0 回退: 已有 task-3-review TA 冒烟验证 NaN=71.7% 行为合理;NaN→0 回退路径是既有代码,非本次新增

---

## 冒烟验证实际输出

### 单测 (6/6 PASS)

```
test_low_oi_history_becomes_nan ... ok
test_no_filter_when_all_oi_high ... ok
test_micro_improvement_below_threshold ... ok
test_rel_drop_above_threshold_is_significant ... ok
test_rel_drop_below_threshold_is_insignificant ... ok
test_zero_baseline_edge ... ok

Ran 6 tests in 0.079s
OK
```

### prediction_scheme import

```
TA scheme OK: bb_squeeze
```

### monthly_backtest 零回归

```
# 运行前: 1 个 checkpoint 文件 (来自 task-2 早期测试)
# 运行 cf --max-points 2 后: 仍 1 个,无新增
# grep -c "checkpoint" → 0 (无 [checkpoint] stdout)
```

### covariate_scan 输出

```
[3/3] 汇总报告
  裁决锚点: 24h MAE 相对下降率 vs 当前固化方案 (DirAcc 仅展示,不参与裁决) | 阈值 3%

  品种 |   最优协变量 |  24h MAE | DirAcc(展示) |  次优 | 次优 MAE
  TA |          ccl |    1.66% |        100% |  hourly_slope |    1.66%

推荐配置更新:
  "ta": covariate_type="ccl",  # 24h MAE=1.66% DirAcc(展示)=100% [显著改善]
```

---

## 总结

| 维度 | 结论 |
|------|------|
| Overall verdict | **APPROVED** |
| Findings | 0 Critical / 0 Important / 1 Minor (deferred) |
| Cross-task coherence | ✅ 无问题 |
| Spec coverage | ✅ 完整 (4/4 方向,7 验收标准全过) |
| Zero-regression | ✅ 通过 (5/5 Bash 验证) |
| 高风险路径保护 | ✅ 通过 (prediction_scheme.py 仅注释) |
| Test coverage | ✅ 充分 (6/6 单测 PASS) |
| 需 fix loop | **否** |

**一句话摘要:** 4 方向优化分支全部 5 个 commit 实现正确、零回归验证通过、跨 task 无冲突、高风险路径未被违反,APPROVED。唯一 deferred 是 Task 4 的 1 字符列宽视觉瑕疵 (Minor,留 TODO)。
