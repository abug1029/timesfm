# Task 4 Review — research 文档 vs 磁盘/代码

- **被审**: `docs/superpowers/reports/2026-09-11-audit/task-4-research-docs.md`
- **计划**: `docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 4
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-4-brief.md`
- **审核日**: 2026-09-11
- **范围**: 只审 Task 4 报告是否按规格取证；不改生产代码

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
| 抽出研究主张并逐条分类：仍成立 / 已修复但文档未改 / 从未成立；带 git hash | 主表 R1–R21 + 权威对照表 | 必抽句均在：STEP=24→396（R4/R5）、evaluator 硬顶 500（R2）、日内前视（R14/R15）、STEP=2 建议（R8）、日历先验未验证（R12）、RevIN 未验证（R13）。哈希独立 `rev-parse` 对齐：`43144ee` / `feedf44` / `ee1f176` / `ba361df` / `2fcb3ee` / `cd29bb6` / `2206d4e` |
| 每句给当前代码值/函数名、相关 commit、判定 | 主表判定 + Evidence For/Against | `get_safe_daily` 存在（`data/data_store.py:158-198`，`ba361df`）；调用者只有 `scripts/cascade_predict.py:106-107`（报告用 `daily_df`）和 `tests/test_daily_freshness.py`。`DailyModel.predict` 仍 `store.get_main_continuous`（`cascade/daily_model.py:104`）。`BacktestDataStore` 不再无条件 `end_date=cutoff_day`：`data/data_store.py:795-802` `hour>=15` 含当日，否则前一日历日（`ee1f176`） |
| 若前视已修：Critical 是过期号召，不是「代码仍穿越」 | 文首 + Findings + Rebuttal | **未**把 `monthly_backtest` 原始前视标成 live Critical。Important 是研究文档仍写「必须立即修复」。夜盘 `hour>=15` 含当日、实盘裸读交给 Task 5。控制器假设成立：`STEP=2` 已在 `config/backtest_config.py:55`；`cd29bb6` 已 merge critical-fixes |
| 每条 finding 有 file:line 或 commit | Findings 五条 + 不升 Critical 清单 | 抽查行号与活仓一致（见下方非阻塞偏差）。pytest 失败方向可复现 |
| 效率审计只核「已落地/未动」 | F-001…F-022 表 | 抽查 F-001 `with DataStore`（`monthly_backtest.py:209`，`721ee47`）、F-002 宽泛 except（`hourly_model.py:247-251`）、F-003 仍 `open(cp,"a")`（`:900`）、F-006 无 `empty_cache`、F-010 模块级 sklearn（`features.py:15-16`）均对 |
| 只写报告，不改生产 | git status | 生产路径无改动。本任务产出仅报告 |

Task 1 矩阵：报告 mtime（10:44）早于 `task-1-doc-authority.md`（10:51），与 Task 2 一样按计划「1–4 可并行」独立取证。矛盾 5（396 vs 600 vs STEP=2 后的 n）已覆盖。矛盾 4（SS `calendar_cyclical` vs `ss_vor`）不是研究原文断言；R19 只标了「日线定方向」与 CF-01 A 冲突，交给 Task 6。不构成返工。

Critical 口径：简报「若前视已修，Critical 是过期号召，不是代码仍穿越」。报告把过期号召标 Important（文档债），与全局规则「文档过期默认最高 Important」以及 Task 11 一致。未把 `monthly_backtest` 标 live Critical，符合控制器假设与本审核检查项 2。

## Quality 核对

| 检查 | 结果 |
|------|------|
| 主张分类是否用 git 时间线，而不是把 09-09 文档当活 bug | 通过。研究唯一提交 `43144ee`（2026-09-09）；STEP/窗口/回测截断在次日 `ee1f176`。R15 明确「回测无条件含当日已修」 |
| 是否误把 monthly_backtest 前视写成 live Critical | **否。** Findings 无 Critical。Rebuttal 第三条明确拒绝把夜盘 `hour>=15` 升 Critical |
| `get_safe_daily` / `2fcb3ee` 名实 | 通过。`git show 2fcb3ee` 仅改报告段 `daily_df`；commit 说明写「production path」过声称。R21「从未成立」正确 |
| 失败单测方向 | 复跑：`test_daily_includes_cutoff_calendar_day` → `AssertionError: '2026-03-10' not found in {'2026-03-09'}`；`test_daily_freshness.py` 6 过。报告引用的失败方向是实验证据，不是「代码没修」 |
| 越权改生产代码 | 否 |

## 独立复验（活仓 `/home/abug/timesfm`）

```
STEP / EVAL_WINDOW_BARS     config/backtest_config.py:55-56 = 2 / 1200
eval_indices                scripts/monthly_backtest.py:220-222
BacktestDataStore 截断      data/data_store.py:795-802
get_safe_daily 定义         data/data_store.py:158-198
cascade_predict 预测后报告  scripts/cascade_predict.py:101 然后 :107
copilot 裸读                scripts/copilot.py:396-400
evaluator aligned           task_FM/evaluations/fm_eval/evaluator.py:126 (350, 600)
supervisor 死默认 400       scripts/praxist_supervisor.py:1292
pytest                      1 failed + 6 passed，失败方向与报告一致
```

理论 n：`len(range(T-1200, T-23, 2)) = 589`。报告公式对。Task 1 磁盘最高 588（日线充足性过滤后），本报告已声明未读 JSONL，不冲突。

## 非阻塞偏差（不必返工）

- Evidence For 把 `STEP` / `EVAL_WINDOW_BARS` 写成 `config/backtest_config.py:57-58`。实际是 `:55-56`（`:57-58` 是 `MIN_EVAL_POINTS` / `MIN_1H_BARS`）。**数值对。**
- F-013 写成 `monthly_backtest.py:31` 仍 `sys.path.insert`。实际 insert 在 `:30`。
- R11 把 `forecast_with_covariates(inputs=[hourly_closes])` 标成 `hourly_model.py:237`。`inputs=` 在 `:236`，调用在 `:235`。
- 效率审计计数散文「未动 9 → 若含 F-003 则 10」绕口；表内 22 项已列全，加减能对上。
- F-005 `:1183` 是拆开的 `assert "D:/FlyBuddy/" + "fm_a" not in src`，不是「断言文本里还有旧路径」。硬编码路径确实已清。
- 未点名回链 Task 1 矛盾 4；研究原文没有 SS 协变量断言。并行时 Task 1 尚未落盘。

以上不改变 R14/R15/R21 与「不要标 live Critical」的事实，不要求重写报告。
