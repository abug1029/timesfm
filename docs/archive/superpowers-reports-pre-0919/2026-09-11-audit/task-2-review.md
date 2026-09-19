# Task 2 Review — `docs/system_design.md` 审核报告

- **被审**: `docs/superpowers/reports/2026-09-11-audit/task-2-system-design.md`
- **计划**: `docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 2
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-2-brief.md`
- **审核日**: 2026-09-11
- **范围**: 只审 Task 2 报告是否按规格取证；不改生产代码

## Verdicts

| 项 | 结论 |
|----|------|
| **Spec** | ✅ |
| **Task quality** | **Approved** |

## Must-fix gaps

无。

---

## Spec 核对（计划 Step 1–3 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| 对点名符号 grep：存在 / 签名是否一致 | 有「符号核对表」 | 独立 grep 对齐：`_compute_direction` 全仓不存在；活函数 `_compute_direction_v2`（`cascade/daily_model.py:189`）；`position_from_forecast` 文档未出现；`gate_pass` 无此函数名，活实现 `evaluator.gate`（`task_FM/evaluations/fm_eval/evaluator.py:199-202`）；其余 `DailyResult` / `HourlyResult` / `signal_weight` / `confidence_band` / `ThrPolicy` / `apply_neutral_override_v2` / `craft_advisory` 均点到文件:行 |
| 核对关键数值并给代码位置 | 有「关键数值核对」表 | 数值本身对：context 480/250、horizon 24/22、`STEP=2`、`EVAL_WINDOW_BARS=1200`、`SLIPPAGE_TICKS=2`、`trend_threshold_pct=0.1`、2 星 8 个、Vol 默认 OFF、SS `calendar_cyclical` vs `ss_vor` 双口径。见下方非阻塞行号偏差 |
| 方向 vs CF-01 A | C1 | `docs/product_positioning.md:15-22` 可交易方向 = `sign(weighted_1H − base)`；`docs/system_design.md:313-332` 写成日线 `_compute_direction`；`scripts/cascade_predict.py:208-230` / `scripts/monthly_backtest.py:50,329` 走 `position_from_forecast`；`scripts/copilot.py` **不** import 该函数，主方向仍 `_compute_direction_v2`（`:433-446`）。测试锁：`tests/test_signal_contract.py:67-77` |
| IC 公式 vs Pearson | C2 | 文档 `docs/system_design.md:485` 写 `corr(预测, 实际)`；合同 `loop-constraints.md:48` `ic=2×\|dir_acc−0.5\|`；代码 `evaluator.py:202` 同式。磁盘：`aligned_verdicts.jsonl:4` `m_vor` ic=0.048；`:16` `ss_vor` ic=0.06；`:19` `i_oi` ic=0.066 且 `gate_pass=true`、ev=−2.46。方向性 IC，不是 Pearson |
| 不宣称「代码仍穿越」，除非已追踪 | I7 + 文首 | 明确写「本文不判定代码是否仍穿越」「不宣称代码仍穿越」。只记录文档未点名 `get_safe_daily`，Stage 1 读 `get_main_continuous`（`daily_model.py:104`），`get_safe_daily` 仅报告路径（`cascade_predict.py:106-107`）。穿越归 Task 5 |

Task 1 矩阵：报告写落盘时目录仍空，按计划「探索期嫌疑」独立取证。现已有 `task-1-doc-authority.md`，方向 / IC / `gate_pass` / SS 双口径与 Task 2 同向，不构成返工。

Critical 口径：简报「仅用于按该文档执行会改错生产信号、硬门或数据截断」。C1（方向）、C2（IC/硬门）符合。未建议改 `SCHEMES` / `daily_model.py` / `evaluator.gate`。

## Quality 核对

| 检查 | 结果 |
|------|------|
| 每条 Critical / Important 有 file:line | 通过。C1–C2、I1–I11 均带文档原文行 + 代码/磁盘行。抽查 C1/C2/I1/I2/I4/I7/I10 行号与源码一致 |
| 是否把过期文档写成活代码 bug | 否。建议是改 `system_design.md`，不要改 `position_from_forecast`；I4 明确不要按 §7.3 去改 `evaluator.gate`；copilot 分叉交给 Task 9 |
| 严重度是否抬高 | 否。文档过期默认 Important/Minor。I4（gate 含 EV）因权威分裂压成 Important 而非 Critical，偏低但不阻塞 |
| 越权改生产代码 | 否。只产出报告 |

## 非阻塞偏差（不必返工）

- 关键数值表把 `CONTEXT_BARS`/`CONTEXT_DAYS`/`HORIZON`/`STEP`/`EVAL_WINDOW_BARS` 写成 `config/backtest_config.py:65-70`。实际是 `:51-56`（`:65-70` 是 `THRESHOLDS`）。数值对，`SLIPPAGE_TICKS:118` 对。
- `docs/product_positioning.md:11-16` 略提前；CF-01 A 表在 `:15-22`。
- `scripts/copilot.py:139-177` 是雷达-only，但「永不压平」注释在 `:413`，不在该段。

以上不改变 C1/C2 事实，不要求重写报告。
