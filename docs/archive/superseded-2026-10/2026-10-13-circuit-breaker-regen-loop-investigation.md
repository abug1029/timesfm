# Circuit Breaker 重复重生问题调查报告

**日期**：2026-10-13
**状态**：FIXED_IN_WORKTREE（未提交、未部署）
**优先级**：P0（阻塞基线重生进度）

## 审核结论

原报告把「8 次记录、0 次跳过」归到 `_latest_data_dt` 返回 None 或时间戳格式不一致。这两条都解释不了这条日志，按原方案 1 加 None 判断也停不住重启后的重生。

根因是断路器记在进程内存里，而 `ensure_baselines` 每个进程只跑一次。

`scripts/sup_loops.py` 的 `_main_locked` 在 `while True` 之前做 pre-flight，调用一次 `ensure_baselines`。轮询循环里没有第二次调用。`16c0ad4` 的 `_RECENTLY_REGENED_NO_ADVANCE` 是模块级字典，注释写「下次 poll 跳过」，但下一次 poll 不会再进入这个函数。字典只在同一次启动里有效。supervisor 再次启动时字典是空的，重锚条件仍成立（基线末端停住、数据末端没变），于是再重生一次，再打一行「重生后基线末端未推进」。所以日志里只有记录、没有「跳过重生」。jd、sr 来回出现，是每次启动按品种各重生一遍，不是同一次 poll 里的内循环。

原报告三条猜想对不上代码：

1. **返回 None。** `None == None` 为真，稳定的 None 会走上原跳过分支，不会无限重生。下一次读取失败时，原逻辑会清掉记录，但同一轮 `_baseline_reanchor_reason` 在没有数据末端时 fail-open，这一轮并不会重生。
2. **时间戳格式不一致。** 记录和比较走的是同一个 `_latest_data_dt`。若下一次真变成 ISO 字符串，重锚用 `%Y-%m-%d %H:%M:%S` 解析失败，同样 fail-open，这一轮不会重生。
3. **30 分钟缓存。** 缓存命中时返回的是同一个值。这个函数在同一次启动里根本不会再被 pre-flight 调用。

原方案 2（把记忆落到磁盘）才是对症的。方案 1 单独做不会改变「下次启动字典为空」。

## 修复

工作区里的 `scripts/sup_evidence.py` 已改，测试在 `tests/test_baseline_regen_loop.py`。

- 停滞记录写到 `{root}/data/cache/baseline_regen_breaker.json`（`data/cache/` 已在 gitignore）。下次启动先读盘。
- 只有两边都能解析、且当前数据末端严格更晚时，才清除记录并允许重锚重生。读失败、解析失败、末端相同或更旧，都保留记录。
- `T` 与空格、小数秒、尾部 `Z` 先归一再比较。
- 跳过只挡重锚重生。指纹不符、行数不足仍会重生，避免协议升级被停滞记录挡住。

验证：`tests/test_baseline_regen_loop.py` 4 项通过；`test_baseline_reanchor.py`、`test_baseline_archival.py`、`test_ensure_baselines_fingerprint.py` 与 `test_supervisor.py` 里的基线用例、`test_sup_modules.py` 共 48 项通过。全量 pytest 未跑：这台 WSL 的系统 Python 没有 torch，收集阶段会停在依赖 torch 的测试上。

未做：没有提交，没有推送，没有重启 supervisor。活进程在另一台主机上，不从这棵树重启。

## 原报告中已否定的方案

原建议是在比较前对 None 做防御性跳过，并把持久化留作后续。持久化是这次要修的行为；None 防御只是「读失败时不要拆掉已有记录」，不能代替跨启动的记录。

原现象仍然成立：jd、sr 反复归档，日志里有「重生后基线末端未推进」，没有「跳过重生」。需要重锚是因为基线末端落后数据末端超过 168 小时，而 TqSdk 10000 bar 上限让重生后的 cutoff 停在原地。断路器要挡的就是这件事，挡的位置必须是下一次进程启动。
