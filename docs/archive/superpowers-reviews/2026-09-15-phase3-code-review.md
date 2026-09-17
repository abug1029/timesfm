# Phase 3 代码审核（Task 7–8）

- **日期**: 2026-09-15
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **范围**: `cceb40a..f54145a`（`5c81b23` registry，`f54145a` monthly_backtest）
- **对照**: `CHANGELOG-Phase3.md`；计划 Task 7–8；规格 §7 / §8.2 / §8.5
- **测试**: `tests/test_verdict_registry.py` + `test_monthly_backtest_quality.py` + `test_monthly_resume.py` + `test_aligned_slow_loop.py -m "not slow"` → **31 passed, 1 deselected**
- **结论**: **changelog 里的 APPROVE 不算数。** Task 7 主体可用，Task 8 的 `dir_acc` 和 `point_dir_ok_list` 不是同一套判定，Task 9 拿去配对 DM 会和硬门对不上。先修这一条再开 evaluator。

---

## 0. 日志对不上的地方

| 日志说法 | 实际 |
|----------|------|
| 状态「完成，代码审核通过」 | 执行者自报。独立审核见本文件 |
| `monthly_backtest.py` +221 行 | **+48 行**（`git diff --stat`） |
| 审核人「独立代码审核」 | 没有独立报告；本轮才是 |
| Task 8「6/6 审核点全部通过」 | 见 §2，口径不一致没测到 |

---

## 1. 做得对的地方

**Task 7**

- 没有推倒重写 `queue_*`；旧句柄测试仍绿。
- `append_verdict` 双态：路径走锁 + 去重，句柄走原来的 `validate` + `write`。
- 路径写入：`.lock` 排他、`pid+time_ns` 临时名、`fsync`、`os.replace`。
- `update_batch_verdicts` 持锁后直接 `_iter_jsonl`，没有二次 `flock`；没有 `metrics` 时不会凭空造一个。
- 同 `batch_id+variant_id` 先写赢。墓碑 `status=error/timeout`，`gate_pass=False`，`p_value=1.0`，带 `metrics`。
- `pass_variants`：v2 要 `gate_pass and (fdr_pass or migrated_pass)`；v1 仍是 `ev>0`；`status != ok` 不算过。待结算 `fdr_pass=None` 不会误过。

**Task 8**

- 零变动：`abs(delta_real_raw) < 1e-8` → `dir_ok=False`（不再记 True）。
- 成功点的 `cutoff` 改成完整 `%Y-%m-%d %H:%M:%S`，另留 `cutoff_date`。
- `summarize` 的 `dir_acc` 改走 `calc_prediction_quality`，不再用 `net["DirAcc"]`。
- `n_eff = fallback_n_eff(n, HORIZON, STEP)` 显式传入，WSL 上是 24/2。
- PF/EV/MaxDD 仍从 `metrics_from_backtest_points` 出，`calc_net_metrics` 没删。
- `_CHECKPOINT_POINT_KEYS` 加了 `endpoint_mape` / `endpoint_bias_pct` / `path_corr`。

---

## 2. 问题

### Critical — Task 9 之前必须修

**`dir_acc` 和 `point_dir_ok_list` 不是同一套 `dir_ok`**

- 文件：`scripts/monthly_backtest.py` 逐点循环约 345 行；`summarize` 约 454–458、497–505 行
- 规格 §8.2 / 计划 Task 8：透传给 DM 的 `point_dir_ok_list` 必须和硬门用的 `dir_acc` 同一判定。
- 现状：
  - **硬门 `dir_acc`**：`calc_prediction_quality(pred_end, real_end, base)` → `sign(pred[-1]-base)` vs `sign(real[-1]-base)`，零变动 False。
  - **逐点 `dir_ok` / `point_dir_ok_list`**：`sign(加权 delta_pred)` vs `sign(delta_real_raw)`。`delta_pred` 来自 `position_from_forecast`（scheme 加权），**不是**终点价差。
- 有 scheme 加权时，终点方向对、加权方向错（或反过来）就会：Gate 过了、DM 序列是另一套命中，或反过来。
- 现有测试还把这种分裂写进了断言：`test_dir_acc_from_calc_prediction_quality_not_net` 里零变动点 **存盘 `dir_ok=True`**，`dir_acc` 算成 0.5，`dir_acc_points` 仍是 1.0。列表抄的是存盘值，不是质量秤。

**修法（选一个，不要并存）：**

1. 推荐：`run_symbol_backtest` 的 `dir_ok` 改成和 `calc_prediction_quality` 一样用终点价差；`point_dir_ok_list` 继续抄存盘字段。加权方向留给 `pnl` / 经济秤。
2. 或者 `summarize` 自己按终点重算 `point_dir_ok_list`，不要用存盘 `dir_ok`。

补测试：加权 `delta_pred` 与 `pred_end-base` 反号时，`dir_acc` 与列表里那一位必须同真假。

### Important

**逐点 `endpoint_mape` 没有 `max(base, 1.0)`**

- 文件：约 379 行 `_ep_mape = abs(pred[-1]-real[-1]) / base * 100`
- `calc_prediction_quality` 分母是 `max(base, 1.0)`。低价资产上逐点 20、汇总 10。计划写的是带地板。
- 修法：逐点也用 `max(base, 1.0)`。`endpoint_bias_pct` 同样。

**墓碑和 `VERDICT_FIELDS_V2` 对不齐规格 §7.1 / §8.4**

- 缺 `cov_family`、`weighted_dir_acc`。异常键叫 `error` 不是 `error_message`。`metrics` 只有 8 个键，没有 `dir_acc` / `n` / `n_eff` / 端点指标。
- `validate_verdict_v2` 因此对残缺墓碑返回 `[]`（已复算）。`test_error_tombstone_has_metrics` 只查了 `batch_id`；超时墓碑工厂从未被测试调用。
- Task 10/12 若直接调用这两个工厂，Supervisor 读 `metrics.dir_acc` 或统计 `cov_family` 会踩空。
- 修法：按 §8.4 / §8.6 填满根字段和 `metrics`；`VERDICT_FIELDS_V2` 补上 `cov_family`、`weighted_dir_acc`；路径版落盘前走 `validate_verdict`。

**路径版 `append_verdict` 不校验 schema，且是整文件重写**

- 句柄版仍走 `validate_verdict`；路径版直接写。规格 §8.5 是持锁 `open(..., "a")` + `fsync`。实现把合法行读出来写 tmp 再 `replace`，坏行会在下一次追加时从磁盘消失。
- 修法：追加保持 append+fsync（去重仍可读）；批次回写才用 tmp。失败删 tmp。重复写入打 warning。

**句柄追加和路径追加不共用锁**

- 慢环现在仍是 `open(..., "a"); append_verdict(f, v)`（Task 10 才切路径）。
- 若 Supervisor 已用路径版 `update_batch_verdicts`，和句柄追加会抢同一文件、各拿各的锁（句柄那边甚至没 `.lock`）。
- Task 10 必须把慢环改成路径 API，过渡期不要混用。

### Minor

- 写 tmp 失败时临时文件可能残留（changelog 已写 LOW）。`try/finally` 里 `os.remove` 即可。
- 异常点仍写 `"cutoff": dt`（只有日期）。这些行带 `error`，`summarize` 会跳过，但 resume 对账会脏。
- `dir12_ok` 在 `d12_real == 0` 时仍记 True，和 §3.5 不一致（若 T+12 也进质量秤再改）。
- `n_eff` 测试只断言 `1 <= n_eff <= n`，锁不住 `STEP=2 → n/8`。`n=10` 时 STEP=2 期望 1、STEP=24 期望 10，两种都过。
- 质量测试只喂现成 `points`，不进 `run_symbol_backtest`。零变动 `dir_ok` 和完整 `cutoff` 整段回退，8/8 仍绿。
- `VERDICT_FIELDS_V2` 没有 `weighted_dir_acc` / `cov_family`（规格 §7.1 有）。多出来的键不会被拒；缺了也不强制。Task 9 写入时要自己补，不要指望 registry 拦住。
- 先写赢失败时没有 `logger.warning`（计划有）。

---

## 3. 建议顺序

1. 统一 `dir_ok` / `dir_acc` / `point_dir_ok_list`（Critical）。
2. 墓碑和 `VERDICT_FIELDS_V2` 对齐 §7.1 / §8.4（Task 10 会直接调用）。
3. 逐点 MAPE/bias 分母地板；错误路径 `cutoff` 用完整时间戳。
4. 路径版追加改为真正 append，并做 schema 校验。
5. Task 10 切慢环到路径 API，不要和句柄混写。
6. changelog 文首 APPROVE 拿掉，行数改成 +48。

**Ready to merge Phase 3:** No  
**Task 9 evaluator:** **不要开**，先统一 Gate 和 DM 的 `dir_ok`  
**Task 10 慢环:** 先补墓碑字段，落地必须用路径版 `append_verdict`  
**Task 7 锁与双态接口:** 可以留在分支上继续用，但不要当「已审核通过」
