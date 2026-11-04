# jd / sr 基线后条件统一 —— 运维说明

> 日期：2026-11-03
> 关联计划：`docs/superpowers/plans/2026-11-03-baseline-point-contract-plan.md`
> 关联规格：`docs/superpowers/specs/2026-11-03-baseline-point-contract-spec.md`

本文档描述 `jd` 与 `sr` 两个品种在基线后条件统一之后的运维操作步骤。
两个品种现在走同一套收口路径：`baseline_eval_cutoffs(symbol)` 决定网格，`accept_baseline_file` 做唯一后条件检查，`finalize_baseline_write` 是唯一换名或回滚的函数。

---

## 第一步：先合并第二截（PR2）

本次运维的前提是 PR2（Task 6-10）的代码已经合入 master。
**在此之前不要手删 `task_FM/config/baseline_points_jd_nocov.jsonl`。**
现行守卫（`finalize_baseline_write` 内部的 `accept_baseline_file` 检查）会把不达标的归档拷回活文件。
如果在代码到位之前删掉活文件，守卫会从磁盘上找到最近一份归档并拷回去 —— 而那份归档不是今天的网格。

## 第二步：确认磁盘上没有现成的正确 jd 文件

磁盘上没有一份已经等于今天网格的 `jd` 活文件。

- `archive_20260929T1500.jsonl` 是 588 行，窗口是 `2025-10-16` 至 `2026-09-29`。**不要把它拷到活文件上。**
- 1 行归档和 3 行归档都不是恢复目标。把它们拷回去等于把旧网格的子集当成新网格，下一次启动仍会被收口拒绝。

## 第三步：由运维选择时机让监督进程跑启动前检查

代码到位之后，由运维选择时机让监督进程跑启动前检查。
会加载模型的是 `jd` 这一趟，属于运维决定，**不是本计划的命令，也不是为了修正 `dir_ok`**。

启动失败路径按以下合同执行（这一段是规格 Key Decision 9 的唯一结尾，原样写入，不改写）：

> `incremental_generate` 返回后：已有可发布临时文件就调用 `finalize_baseline_write`。
> 第一次收口为真就换名、返回网格末笔、不再运行 `generate`。
> 没有可发布临时文件（包括任一评估点带 `error`，或换名前失败），或临时文件未通过，这是第一次接受失败，不是提前结束；没有临时文件且活文件尚未通过时，把第一次收口当成假。
> 只有第一次收口为假，才恰好运行一次 `generate(..., finalize=False)` 并第二次调用 `finalize_baseline_write`。
> 只有第二次收口为假才 `_remember_stall`。第一次为真不记停滞。
> 读网格或写入抛出的异常不是这个 `None`：留在品种循环的 `except` 里记日志；读网格失败不记停滞、不启动全量；写入中途抛出则记停滞，并且不再启动另一次全量。

补充约束：

- 3 行文件只在第二次收口仍为假时留在原地。
- **不要把一份少于网格的文件当成这次运维的成功。**
- **不要运行 `scripts/restart_three_loop_clean.sh` 作为合并动作。**

## 第四步：成功判据

本次运维的成功判据是：

1. 活文件的 cutoff 序列等于 `baseline_eval_cutoffs("jd")` 返回的网格。
2. 指纹仍是现行 v4（`_current_protocol_fingerprint()`）。
3. 没有「已从归档恢复旧档」把行数打回 3。

**不要求与九月归档的 cutoff 集合相同。** 今天的网格就是今天的网格，归档窗口不同是正常的。

## 第五步：sr 的处理

`sr` 不必手改，也不要为它新增预注册或移动 `confirm_from_ts`。

当前磁盘上 `sr` 的 637 行是两次恢复之后又拼上 49 个更早 cutoff 的文件，不是未动过的网格。
下一次按新后条件落盘时，`accept_baseline_file` 会用 `baseline_eval_cutoffs("sr")` 检查，那 49 行如果不在当前网格上就会被丢掉，这是预期行为。

网格上的 588 行若指纹仍是现行 v4 且字段齐全，增量可以复用，**不必为了这 49 行加载模型**。

---

## 禁止事项

- 不要「重跑 21 个品种」。本次只涉及 `jd` 的运维动作；`sr` 在下次自然落盘时自动对齐。
- 不要「为了修正 `dir_ok` 而重生模型」。`dir_ok` 的属主是 `endpoint_dir_ok`，不为它抬协议指纹。
- 不要运行 `scripts/restart_three_loop_clean.sh` 作为合并动作。
- 不要在代码合并之前手删活文件。
