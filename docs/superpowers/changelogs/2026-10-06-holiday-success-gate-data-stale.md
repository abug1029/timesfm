# 国庆数据冻结：success_delta 门 data_stale 旁路 Changelog

**Date:** 2026-10-06
**Status:** 审核修订已落入工作区，仍未提交。未部署，未重启 supervisor。
**Review:** `docs/superpowers/reviews/2026-10-06-holiday-success-gate-code-review.md`（APPROVE，无阻塞）。
**Spec:** `docs/superpowers/reports/2026-10-06-holiday-success-gate-deadlock-diagnosis.md`（§6 选项 A）
**Plan:** `docs/superpowers/plans/2026-10-06-holiday-success-gate-unlock.md`
**Tree:** `/root/timesfm`，基线 `52132c3`。诊断里的活进程在 `/home/abug/timesfm`，不在这棵树上。

---

## 一、背景

2026-10-05 17:50 至 10-06 08:53，监督环把 24 个 `(symbol, cov)` 反复拒在 `no_success_delta`。三路诊断收敛为同一条链：

- v4 2.1 把 `eval_end_ts` 钉在 `2026-09-30 15:00:00`。
- T2 门在 `prior_ts == anchor` 时要求 `success_delta` 至少 20 字。
- 国庆休市，`kline_1h` 停在 `2026-09-30 14:00`，`window_moved` 不会触发。

T2 门本身按设计工作。缺的是「数据末端长期冻结」这条边界。本变更只补这条边界，并让 peer 看见当前仍会被拒的组合。

## 二、变更

| 位置 | 内容 |
|------|------|
| `scripts/praxist_supervisor.py` | `STALE_DATA_DAYS = 3`。`_success_delta_gate` 在 `window_moved` 之后增加 `data_stale` 放行。 |
| 同上 | `materialize_known_verdicts` 在 `## Do not re-propose` 之前写入 `## Locked this window`，最多 `LOCKED_WINDOW_MAX_ROWS = 40` 行。 |
| 同上 | 慢环物化与主循环物化两处调用传入 `root=FM_ROOT`，锁定名单与收获侧共用 checkpoint 兜底。 |
| `task_FM/prompt_base.jinja2` 规则 9 | 指向 `Locked this window`。名单为空时不要为了过门去补 `success_delta`。 |
| `tests/test_success_gate_stale_20261006.py` | 新文件，8 个用例。 |
| `tests/test_success_delta_gate_20261005.py` | `tmproot` 把 kline 钉在 `2099-01-01`，假日机器上的活库不会把旧拒收断言翻成放行。 |
| `tests/test_known_verdicts_injection_20261005.py` | 锁定名单 4 个用例：在列、冻结为空、checkpoint 兜底、40 行截断。 |

`scripts/monthly_backtest.py` 与 `scripts/aligned_slow_loop.py` 无 diff。checkpoint 的 `eval_end_ts` 不改、不删。

## 三、门语义

年龄按上海日历日计算：`(Asia/Shanghai 今日 − kline_1h MAX(dt) 的日期).days`。`> 3` 才放行，`== 3` 仍拒收。周五收盘到下周一的日历差是 3，正常周末不打开旁路。

判定顺序：

1. 无成功先验 → `no_prior_success`
2. 锚不可得 → `anchor_unavailable`
3. `prior_ts != anchor` → `window_moved`（此分支不读 sqlite）
4. 该 symbol 的 kline 年龄 `> 3` → `(None, "data_stale")`
5. 其余仍走原来的 20 字门槛

读不到库、空表、SQL 错误、日期解析失败：不放行，落到 `no_success_delta`。kline 只读 `file:{path}?mode=ro` 的 `SELECT MAX(dt) FROM kline_1h`，缺文件直接返回，不建库。同一 harvest cache 里每个 symbol 的 `data_stale` WARNING 只打一条：

```text
success_gate: {symbol} 数据末端 {max_dt} 距上海日历 {today} 已 {age} 天 > 3 → data_stale 放行
```

旁路只跳过 `success_delta`。mechanism 长度、dedup、family dead、PR-B6 质量门不动。

10/8 新 bar 的日期进入 3 天内后，`data_stale` 自行关闭。此时若 snapshot 的最大锚仍是 `2026-09-30 15:00:00`，同窗复跑恢复要求 `success_delta`。没有旧 checkpoint 的新 variant 仍按 v4 2.1 把锚打在当前数据末端；这条新裁决进入 snapshot 后，旧成功走原有 `window_moved`。

## 四、锁定名单

名单与门使用同一次 `_success_delta_gate(success_delta="")`。只有返回 `no_success_delta` 的 `(symbol, cov)` 入列。`data_stale`、`window_moved`、`anchor_unavailable` 都不入列，冻结期段落是 `- (none)`。

行格式：

```text
- {symbol} cov={cov} prior={variant_id} class={class} eval_end_ts={prior_ts}
```

`class` 与 T2b 拒收日志同一函数 `_prior_success_class`：`fdr_pass` 且 `p_value is not None` 且 `run_mode == "confirmation"` 为 `v2-pass`，否则 `hard-gate-but-losing`。

物化探门时 cache 带 `_probe`，不打拒收 WARNING，也不打 `data_stale` WARNING。收获路径不带这个标志，拒收日志保持原样。段落不含 `datetime.now()`，`test_idempotent_rewrite_except_generated_at` 仍只放过 `generated_at`。

单元测试不传 `root` 时不去读仓库里的真实 checkpoint。生产两处物化传入 `root=FM_ROOT`，行内没有 `eval_end_ts` 的成功裁决仍能从 `data/cache/aligned_checkpoints/<vid>.jsonl` 末行锚进名单。

## 五、相对诊断报告的差异

| 报告原文 | 本变更 |
|----------|--------|
| 降级为 `window_moved` | 独立状态 `data_stale`，放行行为相同，计数与真实窗口平移分开 |
| 陈旧判断放在 `prior_ts != anchor` 之前 | 放在该判断之后。窗口已平移时不读 sqlite |
| P0-2：数据变长后清除 checkpoint 旧锚 | 不实施。绝对锚挡住同一 checkpoint 混入多段窗口（发现 B） |
| 可与 `data_validator.is_stale` 对照 | 不复用。该标志扣除法定假日，国庆当天有效滞后可以为负，打不开这道门 |

## 六、验证

```text
python3 -m pytest tests/test_success_gate_stale_20261006.py \
  tests/test_success_delta_gate_20261005.py \
  tests/test_known_verdicts_injection_20261005.py -q
```

30 passed（其中新用例 13：冻结旁路 9，锁定名单 4）。

`tests/test_eval_end_ts_backfill_20261005.py` 未跑：这台 WSL 的系统 Python 没有 `numpy`，收集阶段在 `monthly_backtest.py` 失败。该文件不在本次 diff 内。

## 七、审核时建议看的点

1. `== 3` 不放行、`> 3` 放行是否接受。周一休市、周二早盘尚无新 bar 时，周五到周二日历差为 4，旁路会开一个上午。
2. 新 bar 已入库、snapshot 锚未更新的空档恢复强制 `success_delta`，是否接受。
3. 物化探门的 `_probe` 不打日志。收获路径的 `no_success_delta` WARNING 应仍在。
4. 锁定名单是提示，不是第二道硬门。硬拒收只有 `_success_delta_gate`。
5. 部署不在本变更内。审核通过并提交后，才能把这棵树同步到 `/home/abug/timesfm`，再按 `docs/three_loop_restart_protocol.md` 重启。

## 八、明确不做

- 不改评估窗锚，不重写 checkpoint。
- 不提交，不 push。
- 不在这台 WSL 启动或重启 supervisor。


## 九、审核修订（2026-10-06）

对照 `docs/superpowers/reviews/2026-10-06-holiday-success-gate-code-review.md`。

| 条目 | 处理 |
|------|------|
| M1 年龄边界 | 代码不改，维持 `age > 3`。审核没有指定改成 `>=`，只要求宿主确认。周五到周一日历差为 3，旁路保持关闭。 |
| M2 测试覆盖 | 审核已改为 INFO。不改测试清单，另加 L1 的回退用例。 |
| L1 `_today_shanghai` | `ZoneInfo` 失败时回退 `datetime.now(timezone.utc).date()`。这是防御，不是预期路径。用例 `test_today_shanghai_falls_back_to_utc_when_zoneinfo_fails`。 |
| L2 cache 原地修改 | `_locked_success_rows` 在写入 `_probe` 处加一行注释：`_symbol_data_stale` 会填 `_kline_max` / `_stale_logged`。 |

审核列出的另外三项开放问题（新 bar 与旧锚的空档、`_probe` 不打日志、锁定名单只是提示）维持原设计，没有改行为。
