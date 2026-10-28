# FM_a 系统状态

> 最后核对：2026-10-27。对照的提交是 `fb6a40a 2026-10-27 21:56:03 +0800 docs(runbook): add queue cleanup section for invalid proposals`。
> 本文件是现行合同的入口，不是运行快照。进程号、`cycles_done`、裁决行数、协议哈希都不写在这里。
> 2026-10-12 及更早的流水在 `docs/archive/history/STATE-ledger-through-2026-10-12.md`。

人类文档从 `docs/README.md` 进入。架构看 `docs/praxist.md`，运维看 `docs/runbook_praxist_three_loop.md`。阈值只认 `docs/evaluation.md`，这里不复述。

## 先查哪里

| 想知道 | 查 |
|--------|----|
| 监督环在不在跑、跑到哪一圈 | `pgrep -af praxist_supervisor.py`，再读 `data/cache/supervisor_state.json` |
| 这次进程有没有加载某次提交 | 进程启动时间对照 `git log`。磁盘新于进程启动时间的提交，要等按 `docs/three_loop_restart_protocol.md` 重启才进运行中的监督环 |
| 成功条件、品种表、搜索档位、预算 | `scripts/praxist_goal.yaml` |
| 裁决 | `task_FM/config/aligned_verdicts.jsonl` |
| 信用档 | `config.prediction_scheme.list_by_stars`。不要抄一份清单到文档里 |
| 协议版本 | `PROTOCOL_FINGERPRINT_VERSION`。哈希用 `compute_protocol_fingerprint()` 现算 |
| 基线是否该重生 | `scripts/sup_evidence.py` 的 `_BASELINE_STALENESS_MAX_H` 和 `ensure_baselines` |

## 现行合同

- 生产红线不变：Neutral 压平默认关。盘中入口是 `scripts/copilot.py`。可交易方向来自加权 1 小时预测，日线只作状态标签。见 `docs/product_positioning.md`。
- 三环成功条件只有 `all_symbols_pass_phase1`：每个目标品种至少有一个经 family 封账的确认变体。原来的三阶段门槛已退役。品种表以 goal 文件为准。2026-10-08 起从目标里去掉 `sc`，加入 `jm`。
- 预算仍是 `max_cycles` 2000、`cpu_hours` 2000、`token_budget_m` 空（不参与停机）、截止日期 2028-10-02。
- 搜索档位只看 goal 文件里的 `search_policy`（`off`、`shadow`、`enforce`）。这个键每轮轮询热重载。2026-10-27 核对时磁盘值是 `shadow`。不要按更早的笔记把它改回 `off`，除非宿主明确要求。
- 预注册样本量已锁定，监督环不改写。已锁定的记录在 `task_FM/config/preregistry.jsonl`。
- 品种探索状态在 `task_FM/config/symbol_status.json`。2026-10-27 核对时 `symbols` 仍是空对象，没有品种被标成停用或观望。
- 协变量预筛的模块文件名仍是 `cascade/typesafe_prescreen.py`。没有 `TYPESAFE_API_KEY` 时直接降级，不发请求。有密钥时请求发到 `LAYA_BASE_URL`（未设置则 `http://100.96.19.116:8000`）的 `/v1/systemone`。加减分只写在 `docs/praxist.md`。
- 基线漂移上界以 `_BASELINE_STALENESS_MAX_H` 为准。2026-10-25 07:18 的 `894828e` 曾把它改成 336 小时，同日 07:35 的 `62dc675` 改回。以代码常量为准。
- 慢环是 `aligned_verdicts.jsonl` 的唯一写入者。硬门口径在 `docs/evaluation.md`。

## 2026-10-14 至 2026-10-27 已经进磁盘的事

这些是相对归档流水新增的事实。现场数字仍去上一节的文件里查。

1. 预筛传输已从 TypeSafe SDK 换成 Laya 的 HTTP 接口，模块文件名没改。记录在 `docs/superpowers/changelogs/2026-10-14-jev-to-laya-migration.md`。2026-10-24 在这之上做的超时分层、队列退避和配套 spec，已由 `62dc675` 撤回，那些 spec 不在库里。
2. 监督环拆分已在 master。符号家在 `docs/praxist.md`。入口仍是 `scripts/praxist_supervisor.py`。
3. 跨 run 的拒收摘要和 `decision=abandon` 已接到收割。拒收摘要脚本是 `scripts/aggregate_rejection_stats.py`，放弃提案在 `scripts/sup_harvest.py`。2026-10-03 那份「还没做」的说法已经过时。
4. 2026-10-03 的未决问题清单有收口记录：`docs/superpowers/changelogs/2026-10-08-open-issues-closure-implementation.md`。不要把那份 10 月 3 日报告当成还开着的工单。
5. 慢环对未支持协变量会快速失败，入队前会核对协变量名。记录在 `docs/superpowers/changelogs/2026-10-27-slow-loop-no-data-fix-changelog.md`。无效队列的清理步骤在运维手册的「队列清理」一节，脚本是 `scripts/cleanup_invalid_queue.py`。
6. peer 提示里有一份明确的协变量可写与不可写名单，在 `task_FM/roles/peer_generalist/skill.md`（`2c4c92b`）。
7. 2026-10-25 至 2026-10-26 的提案质量报告已归档到 `docs/archive/reports-2026-10-proposal-quality/`。

## 不要从旧文档里恢复的事

- 不要把预筛改回 TypeSafe SDK 的 `client.system_one()`。
- 不要按已删除的 2026-10-24 优化稿恢复 336 小时重生阈值或超时分层。
- 不要把 `sc` 加回目标品种，也不要发明新的成功门槛。
- 不要为了「让文档里的旧进程号对上」去重启监督环。重启只在用户明确要求时按 `docs/three_loop_restart_protocol.md` 做。

下一步：从 `docs/README.md` 选要读的手册。改三环行为之前先读 `docs/praxist.md` 和 `docs/evaluation.md`。
