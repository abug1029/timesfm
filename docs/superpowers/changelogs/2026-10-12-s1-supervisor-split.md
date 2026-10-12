# Changelog: S1 监督环拆分

**日期**: 2026-10-12
**作者**: FlyBuddy
**代码基线**: `3e8756e`
**分支**: `/root/timesfm-s1` 的 `feat/s1-supervisor-split`
**基线提交**: `9850af2`（`docs(spec): S1 supervisor split v3.2`）

## 现在在哪

11 个实现提交在 `3e8756e`。合并提交 `e416104` 把 master `94a320f` 并进来，入口仍是 `scripts/praxist_supervisor.py`，符号定义在 `scripts/sup_*.py`。归属的唯一表在 `docs/praxist.md`。宿主 `/home/abug/timesfm` 没有换到这版代码，也没有重启。本文件和同一次改过的活文档在本提交入库。

## 提交

- `dedd982 test(s1): 从 SPEC 附录 A 解析符号归属表`
- `f46159f refactor(s1): 提升 is_valid_tier 为模块级函数`
- `3379c0e refactor(s1): 抽出 sup_paths，队列路径在调用时读取`
- `88bb0b8 refactor(s1): 抽出 sup_env`
- `d39b72a refactor(s1): 抽出 sup_state，token 基线与预注册随状态走`
- `c46fe38 refactor(s1): 抽出 sup_lifecycle，停机标志不被拷贝`
- `ab91b34 refactor(s1): 抽出 sup_provider，parse_429_reset 留在 provider`
- `8163630 refactor(s1): 抽出 sup_evidence，指纹函数体保持不变`
- `765b045 refactor(s1): 抽出 sup_harvest，预筛日志打在 harvest 模块上`
- `ec37571 refactor(s1): 抽出 sup_family，family_for 仍是闭包`
- `3e8756e refactor(s1): 抽出 sup_loops，入口改为 __getattr__ shim`

## 代码

shim 170 行。`_HOMES` 有 209 个名字，`__all__` 有 92 个名字。`main()` 包在 `__name__ == "__main__"` 里，当库 import 不进主循环。

超过 700 行、按计划不再拆的文件：`scripts/sup_evidence.py` 1402 行，`scripts/sup_loops.py` 1308 行，`scripts/sup_harvest.py` 805 行。

唯一行为变化：`is_valid_tier(v, log=None)` 提升为 `scripts/sup_evidence.py` 的模块级函数，非法 tier 不再 `NameError`。调用仍是 `is_valid_tier(v)`。`_current_protocol_fingerprint` 与 `_baseline_protocol_fingerprint` 的函数体相对 `9850af2` 未改，协议指纹不 bump。

spec `docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md` 附录有六处和定义不一致。以 `docs/praxist.md` 的模块表为准：确认数据缓存两个名字在 `sup_state`；`_CONFIRMATORY_DM`、`CROSS_MATRIX_MAX_ROWS`、`OLD_PRIORS_MAX_ROWS` 在 `sup_evidence`；`_ev_mod_for_goal` 在 `sup_evidence` 赋值后 `del`，import 结束后模块字典里没有它。

## 验证

本机仍在的 junit：`/tmp/s1-baseline.xml` 为 1565 项、71 失败、41 错误、3 skipped。`/tmp/s1-after.xml` 为 1582 项、71 失败、41 错误、3 skipped，通过 1467。失败与错误的集合没有新增。命令带 `--continue-on-collection-errors`。pytest 7.4.4，未装 torch / sklearn，收集错误是原有的。

干跑文件 `/tmp/s1-dry-before.txt` 与 `/tmp/s1-dry-after.txt` 的 `harvest_plan` JSON 相同，缺 praxist 二进制的 `RuntimeError` 相同。traceback 的入口帧仍在 `scripts/praxist_supervisor.py`，其余帧落到 `sup_loops.py`、`sup_provider.py`、`sup_env.py`。这不是决策变化。

每个实现 task 的 critic 结论是 APPROVE。Task 12（宿主迁移）没有执行：没有杀进程，没有改 crontab，没有写 `maintenance.flag`。

## 没有做的事

合并提交 `e416104` 的第二父提交是 master `94a320f`。冲突只有 `scripts/praxist_supervisor.py`，保留了 shim。death-loop 修复在合并结果里：`scripts/sup_lifecycle.py` 的 `_write_heartbeat` 最多每秒写一次，失败也推进节流时间；`scripts/sup_evidence.py` 的 `ensure_baselines` 每个品种在 `finally` 里调用它。`scripts/generate_baseline_points.py` 与 `scripts/diagnose_three_loop.sh` 用的是 master 上的版本。`/root/timesfm` 上当时未提交的工作区和索引没有并进来。

活文档里的历史 spec、旧 changelog、研究笔记没有改。

## 下一步

审阅本文件和活文档 diff。要提交时只在 `/root/timesfm-s1` 提交文档路径。上宿主之前先处理与 `69067b5` 的分叉。重启只走 `docs/three_loop_restart_protocol.md`。
