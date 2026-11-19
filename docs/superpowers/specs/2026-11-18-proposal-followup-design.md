# 提案质量后续规格

代码基线：`/home/abug/timesfm` 的 `master`，`50c848b09545230b4f0cc2d87556ca294829841f`。工作区里上一份规格的提示词改动还没提交。本文件在那些改动之上追加，不把它们退回去。写这份规格时 `pgrep -af '[p]raxist_supervisor.py'` 没有进程。`scripts/praxist_goal.yaml` 的 `search_policy` 是带引号的 `shadow`。

本文件不授权实施，不提交，不推送，不重启监督环。要改代码，先另写计划并得到单独授权。

上一份规格是 `docs/superpowers/specs/2026-11-18-proposal-quality-design.md`。它只改了快环提示词里互相矛盾的句子。它末尾「以后再看」的两件事，由本文件按下面五步接手。成功条件仍是 `all_symbols_pass_phase1`。`survivors_per_cycle` 仍是 3。评估门禁公式、协议指纹、协变量池和 `task.yaml` 都不在本文件的改动里。

## 决定

五步都做，只有第 2 步看第 1 步的结果决定改不改选座。

1. 用现有拒绝码，只读回放审计窗口里的提案，按族汇总。回放不调用 `harvest_proposals`。
2. 只有回放结论是 `reserve_last_seat` 时，才把 3 个座位里的最后一席留给近期完成队列里最少的未死亡族。结论是 `no_selection_change` 时，选座代码保持现状。
3. 同一品种、同一协变量已有可确认失败时，`failure_delta` 至少 20 字，并且原文包含该失败裁决里的一条 `variant_id`。拒绝码仍是 `no_failure_delta`。
4. 提示词里「品种或协变量」改成与收割相同的配对条件，并加一条英文：一份生成里写两份以上提案时至少用两个品种。这条不新增收割拒绝码。
5. 加一个只读计数脚本。以后的报告引用它打印的数字。方向字段只写 `dir_acc`。

`docs/superpowers/reports/优化建议.txt` 的这一版不推翻这五步。它要求写计划前先定五个实现边界。本修订把它们写进对应步骤：15 个目录共用一套去重集合、回放结论落盘后不再重跑、48 小时用闭区间并把空席补满、计数函数与命令行分开、失败增量沿用现有的首尾去空白。

## 写规格时核对过的窗口

窗口是附录 A 的 15 个 run，从 `run_2026-11-17_01-55-15_primary_task_FM` 到 `run_2026-11-18_12-41-11_primary_task_FM`。提案文件在 `results/**/proposals/*.json`。同目录下的 `*.prescreen.json` 也符合 `*.json`，不计入提案。2026-11-18 写规格时，去掉预筛文件后是 894 个提案文件：879 个能解析且 `schema` 为 `fm.hypothesis_proposal.v1`，15 个不是合法 JSON。按活跃池的族：`term_structure` 102、`momentum` 225、`calendar` 150、`inventory` 269、`volatility` 132，另有 1 份假设的协变量是空的。预筛文件 196 个，`status` 都是 `degraded`，`note` 都是 `TypeSafe API 超时`。

完成队列 `data/cache/aligned_pending.done.jsonl` 里，`enqueued_at` 含 `2026-11-17` 或 `2026-11-18` 的有 63 行。其中 `src_run` 属于这 15 个目录名的有 13 行。两个数分开报，不合并。当前协议 `status=ok` 且 `protocol_fingerprint` 以 `f02b2a43` 开头的裁决里，`dir_acc` 等于 0 的行数是 0。当时这类 ok 行共 185 条；185 只是当时的样本大小，验收不锁这个总数。

逐 run 的提案文件数（不含 `*.prescreen.json`）：

| run | 提案文件 |
|---|---|
| `run_2026-11-17_01-55-15_primary_task_FM` | 48 |
| `run_2026-11-17_03-55-34_primary_task_FM` | 65 |
| `run_2026-11-17_05-56-23_primary_task_FM` | 67 |
| `run_2026-11-17_07-56-25_primary_task_FM` | 103 |
| `run_2026-11-17_10-57-34_primary_task_FM` | 56 |
| `run_2026-11-17_13-50-15_primary_task_FM` | 78 |
| `run_2026-11-17_16-05-58_primary_task_FM` | 40 |
| `run_2026-11-17_18-07-01_primary_task_FM` | 18 |
| `run_2026-11-18_00-28-23_primary_task_FM` | 51 |
| `run_2026-11-18_02-25-52_primary_task_FM` | 79 |
| `run_2026-11-18_04-23-37_primary_task_FM` | 56 |
| `run_2026-11-18_06-22-12_primary_task_FM` | 54 |
| `run_2026-11-18_08-38-47_primary_task_FM` | 58 |
| `run_2026-11-18_10-41-10_primary_task_FM` | 78 |
| `run_2026-11-18_12-41-11_primary_task_FM` | 43 |

`run_2026-11-17_18-07-01_primary_task_FM` 没有 `run_summary.json`。计数不依赖这份摘要。

## 第 1 步：只读回放

脚本是 `scripts/proposal_reject_replay.py`。它只被人手动运行，监督环不导入它。

回放回答的是：用现在的快照、现在的在途队列和现在的拒绝码，把这 15 个目录里的提案走一遍，库存类和日历类有没有进入候选，以及按现在的 3 席规则会不会落到选中名单。它不是逐次历史收割的复原。当时的队列没有另存，不要补造。

1. 先读目标文件。`search_policy` 不是字符串 `shadow` 就退出，退出码 2，不写结论文件。强制档会多拒一批，本文件不改这个键，也不在别的档位下做结论。
2. 快照、死亡变体、在途集合、协变量池，用 `scripts/sup_loops.py` 里 `_harvest_rows` 已经传给 `harvest_proposals` 的同一组来源：`sup_evidence._active_protocol_snapshot(sup_paths.REGISTRY)`、`rl.dead_variants`、在途并上快照键、`sup_evidence.load_covariate_pool()`。`priority_symbols` 用 cadence 里的同名键；现在没有这个键，传入空，不要往目标文件里加。
3. 只遍历上面 15 个目录，按目录修改时间从新到旧。不要遍历其他 `run_*`。目录内文件顺序与 `harvest_proposals` 的 `glob` 一致。跳过文件名以 `.prescreen.json` 结尾的文件。`seen_vids` 和 `_evaluated` 都在目录循环之前各创建一次，15 个目录共用，不按 run 重置。这与 `harvest_proposals` 里 `seen_vids = set()` 写在 `run_*` 循环之前相同。`seen_vids` 的成员是 `build_variant_id` 得到的 `variant_id`，不是 `proposal_id`。文件通过 variant 去重检查后就加入 `seen_vids`，即使它后面被质量门或成功增量门拒绝，也占住这个 `variant_id`；更旧目录里的同一 `variant_id` 记为 `dedup`。`_evaluated` 的键仍是 `(symbol, cov, canonical_mode)`。同一 `proposal_id` 但 `variant_id` 不同的文件，不因为 id 相同而被 `dedup`。
4. 把「从读入 JSON 到成功增量门」这一段现有判断收成一个函数，放在 `scripts/sup_harvest.py`。`harvest_proposals` 调用它。回放也调用它。`_append_backlog` 和 `_prescreen_async` 留在 `harvest_proposals` 里，不要放进这个函数。回放拿到 backlog 原因时只计数，不写 `covariate_backlog.jsonl`，不调用预筛，不调用 `harvest_proposals`，也不调用 `_harvest_rows`。
5. 这一步的函数保持今天的 `no_failure_delta`：`delta = str(p.get("failure_delta") or "").strip()`，然后判断 `len(delta) < 20`。`strip` 只去掉首尾空白，中间的空格和换行仍算进 20 字。不要改成删掉全部空白。点名 `variant_id` 是第 3 步的事，不要提前加进回放。
6. `shadow` 下搜索守卫只记「本会拒绝」，不改变候选。回放不构造 `SearchGuard`，也不写它的计数。生产路径上的守卫调用留在 `harvest_proposals`。
7. 候选用现在的排序和现在的两轮选座模拟，`top_k` 用目标文件里的 `survivors_per_cycle`（3）。模拟只在这 15 个目录产生的候选上做。

结论文件是 `docs/superpowers/reports/2026-11-18-proposal-reject-replay.json`。先写临时文件，检查通过后再换成这个路径。检查失败时退出码 2，磁盘上不留这份 JSON。结论文件已经存在时，脚本退出码 0，不读取实验目录，也不替换文件。第 3 步开始改分类函数之前，只有这份文件还不存在，或者实施者确认分类函数仍只做长度检查、并且亲手删掉错误文件之后，才可以再跑一次。从第 3 步改分类函数起，直到验收结束，不删除这份 JSON，也不再运行 `scripts/proposal_reject_replay.py`。验收读取已落盘文件，要求 `failure_delta_rule` 仍是 `length_only`。

检查项：

- 提案文件数是 894，可解析假设是 879。库存类 269、日历类 150 按 `cov_override` 在活跃池里的 `family` 计，不读提案 JSON 自己的 `covariate_family`。有一项对不上就停。不要改期望数字，也不要改选座。
- 任一文件的拒绝码是 `family_dead` 时，所用的族必须在同一次 `_dead_families(snapshot)` 的结果里。不在，说明脚本和收割不是同一套死亡判断，停。
- `decision` 只有两个值。库存类或日历类至少有一个候选，并且模拟选中的族里没有这两类，才写 `reserve_last_seat`。其余情况写 `no_selection_change`。
- 另报 `dominant_reject_inventory_calendar`：这两类被拒文件里次数最多的拒绝码。次数并列时，取 `harvest_proposals` 里先出现的那个 `_reject` 字符串。被拒文件数是 0 时，这个字段是 JSON `null`，不要写成空字符串或空数组。这个字段只供阅读。它不授权放宽任何门，也不授权新拒绝码。
- JSON 含 `failure_delta_rule`。这一步的值是 `length_only`。

第 1 步完成的标志：要么这份 JSON 已落盘，`decision` 是上述两个字符串之一，并且 `failure_delta_rule` 是 `length_only`；要么检查失败并退出码 2、磁盘上没有这份 JSON。现有 `tests/test_harvest_proposals.py` 在抽出函数之后仍然通过。有测试结果变化就收回抽出的函数，后面的步骤也不做。

回放的单元测试用临时目录，不读 `task_FM/experiments`。至少覆盖：过短的 `mechanism` 得到 `mechanism_too_short`；`*.prescreen.json` 不被当成提案；两个目录里同一 `variant_id` 各一份提案时，较新目录占住该 id，较旧目录记为 `dedup`；结论文件已存在时再跑脚本，文件字节不变。用语法树检查这个脚本没有调用 `harvest_proposals`、`_prescreen_async`、`_append_backlog`、`_harvest_rows`。

## 第 2 步：最后一席

只在第 1 步的 JSON 存在且 `decision` 为 `reserve_last_seat` 时改选座。文件不存在，或值是 `no_selection_change`，则 `harvest_proposals` 在排序之后的两轮循环保持原样，本步结束。

不要改 `survivors_per_cycle`。3 席且候选里有四个以上的族时，现在的第一轮会占满三个席位，第二轮不会再跑，第四个族即使已经是候选也没有席。最后一席只在这种情况下把一个席位让给近期几乎没进完成队列的族。空队列时各族计数都是 0，结果应与现在的第一轮相同。

选座函数接收已经排好序的候选、`top_k`、死亡族集合、以及族到近期次数的映射。`harvest_proposals` 负责读完成队列并调用它。

1. `top_k` 小于 2 时，走现在的两轮循环。
2. 否则先用现在的「每个族一个席」走法，最多填 `top_k - 1` 个席。族不够时可以少于这个数，不要为了凑数重复同一个族。
3. 保留席的人选，来自还没选中的候选，族还没占席，族不在 `_dead_families` 的结果里，并且这个族出现在活跃池的某一行上。协变量不在池里的候选不能占这席。只占一个席。
4. 在这些人里，取完成队列里该族近期行数最少的；行数相同则 `_score` 更高的优先；仍相同则 `variant_id` 字典序较小的优先。近期是闭区间 `cutoff <= enqueued_dt <= now`。`now` 是 `datetime.fromisoformat(sup_lifecycle._now_iso())`，`cutoff = now - timedelta(hours=48)`。恰好早 48 小时的行计入，晚于 `now` 的行不计入。`_now_iso` 的实现是 `datetime.now().isoformat()`，返回值没有时区偏移。解析后 `tzinfo` 不是 `None` 的完成队列行不计数。若 `now` 自己的 `tzinfo` 不是 `None`，本轮选座退回现在的两轮循环，不做时区换算。族按该行 `cov_override` 在活跃池里的 `family` 计。协变量不在池里的行不给任何族加一。
5. 然后用现在的第二轮按分数补，直到选中数达到 `top_k` 或候选用尽。保留席没有人选时也走这轮。只有一个族、`top_k` 为 3 时，第一轮只占 1 席，保留席因为该族已经占席而空过，第二轮把其余席补满，选中数是 3。不要只补 1 席就停。

48 小时是运行时规则。11 月 17 日和 18 日那两个日期只给第 5 步的计数用，不要写进选座。

函数不要出现 `inventory` 或 `calendar` 这两个族名。第 1 步用这两个名字决定是否采纳这段代码；采纳之后，任何未死亡且在池里的族都按同一规则竞争最后一席。

单元测试直接调用选座函数，不读活的完成队列：

- `top_k` 为 3。四个族的分数是 40、30、20、10，近期次数是 5、5、5、0。选中的是前两个高分族，加上次数为 0 的族。分数 20 的那个族让出席位。
- 同样的输入，但次数为 0 的族在死亡集合里。选中的是分数 40、30、20 的三个族。
- `top_k` 为 1。选中的是分数最高的一个，不留最后一席。
- 四个族的近期次数都是 0。选中的是分数最高的三个族。
- `top_k` 为 3，候选只有一个族、三份不同分数。选中数是 3。
- 完成时间恰好等于 `now - 48 小时` 的行计入该族；再早 1 微秒的行不计入；带时区的行不计入。

## 第 3 步：失败增量必须点名

`scripts/sup_evidence.py` 的 `_has_prior_failure` 已经只认同一品种、同一协变量。品种按小写比较，协变量按原文比较。可确认失败是 `_is_confirmable_failure`：`gate_pass` 为假，且 `dm_status` 属于 `_CONFIRMATORY_DM`（`ok` 与 `set_mismatch_ok`）。这个函数不读 `status`。提示词不要另写一条 `status=ok` 的条件。

在同一文件里加一个函数，供收割和第 1 步抽出的分类函数一起调用。有可确认的配对失败时，先取 `delta = str(p.get("failure_delta") or "").strip()`。`len(delta) < 20`，或者 `delta` 没有包含这些失败行里任意一条非空 `variant_id`，就拒绝。`strip` 只去掉首尾空白，与今天 `sup_harvest.py` 的长度检查相同。拒绝码仍是 `no_failure_delta`。没有这类失败时，这个函数不拒绝。

`variant_id` 用裁决行里存的字符串做区分大小写的子串判断。非空是指 `str(vid or "").strip()` 之后还有字符。不要改成 `{symbol}_{family}_{fingerprint}` 再去对。匹配行里至少有一条非空 `variant_id` 时，原文含其中任意一条即可，不必把历史 id 都写上。所有匹配行的 `variant_id` 都空着时，拒绝，不要当成无 id 可对因而放行。

不要新表，不要按 `proposal_id` 去重。同一对的下一次重提，只要点名了那条 `variant_id`，仍然可以进入候选。生成侧已经有 Do not re-propose 名单，本步不改那段名单。

`tests/test_harvest_proposals.py` 里现有的五个 `failure_delta` 测试保持通过。`test_failure_delta_enqueued_when_present` 的 `DELTA` 含有 `m_vor`，而夹具里的 `variant_id` 就是 `m_vor`，不要为了新规则改写这段 `DELTA`。另加三条：

- 同一对已有可确认失败，`failure_delta` 不少于 20 字，但原文没有那条 `variant_id`：拒绝码 `no_failure_delta`，选中数是 0。
- 两条可确认失败，原文只含第二条的 `variant_id`，其余门相同：选中数是 1。
- 匹配行没有 `variant_id`，原文足够长：拒绝码 `no_failure_delta`。

`test_failure_delta_not_required_for_same_symbol_other_cov` 继续证明：同一品种的另一个协变量失败，不要求这份提案带 `failure_delta`。

第 3 步开始改这个函数之后，不运行 `scripts/proposal_reject_replay.py`，也不删除 `docs/superpowers/reports/2026-11-18-proposal-reject-replay.json`。那份文件记录的是点名规则生效前的拒绝分布，`failure_delta_rule` 必须仍是 `length_only`。

## 第 4 步：提示词

只改 `task_FM/prompt_base.jinja2`。不改 `task_FM/roles/peer_generalist/skill.md`，也不改 `task_FM/prompt_generation.jinja2`。修订时读过技能文件，全文没有 `failure_delta`，也没有按品种或协变量要求增量的句子，所以不必改它。上一份规格已经写上的句子保持，包括绝对路径的 `target_symbols`、`p_oi` 的 `"covariate_family": "inventory"`、两份以上提案才跨族、以及慢环现有 aligned 门。第 34 行的中文放弃示例保持。`cohort_size | default(4)`、`n=350-600`、两处 include、`p_oi.json`、`ACTIVE 品种优先`、`positioning/calendar/structure` 都保持。

示例里的 `failure_delta` 整行换成：

```text
  "failure_delta": "仅当本 symbol 与本 cov 的组合已有可确认失败时必填：原文包含该失败裁决的 variant_id，并写清这次机制差在哪（≥20字）",
```

行末逗号保留，因为下一项仍是 `success_delta`。第 9 条整句保持，其中必须原样留下下面这一句：

```text
缺 `success_delta` 的复跑会被拒收 (`no_success_delta`)。
```

第 8 条整句换成：

```text
8. **failure_delta**：若该 symbol 与该 cov 的组合已有可确认失败（`gate_pass` 为假，且 `dm_status` 为 `ok` 或 `set_mismatch_ok`），必须填写 ≥20 字，并且原文包含该组合至少一条失败裁决的 `variant_id`。只提到品种或只提到协变量不算。没有点名会被拒收 (`no_failure_delta`)。
```

文件里不再出现 `本 symbol 或本 cov`。

Diversity 段现有这段保持为一个独立段落：

```text
When you write two or more proposals in this generation, at least one must use an ACTIVE covariate family from the menu below that differs from the family of your other proposal. A single proposal is valid when its covariate is an ACTIVE row in that menu. Do not invent a family the menu does not list.
```

紧接其后另起一段，整段是：

```text
When you write two or more proposals in this generation, use at least two symbols. For a symbol and covariate that already has a confirmable failure, write at most one more proposal in this generation, and only with a failure_delta that contains that failure's variant_id.
```

一份提案仍然有效。这句话不进收割。同一次收割里，相同的 `(symbol, cov, canonical_mode)` 已经会得到 `dedup_evaluated`。再加一条「只有一个品种」或「至多一份」的拒绝，会把某一位同行的文件整批丢掉，和「每个目标品种都要过第一阶段」冲突。`eg`、`rb`、`jd` 不冻结。打分里已有的品种失败惩罚保持。不要用审计报告里的百分比做配额或熔断。

扩展 `tests/test_prompt_symbol_authority_20261118.py`。模块说明改成同时覆盖配对条件和两个品种这句。测试仍只读这三个文本。`prompt_base.jinja2` 必须包含第 8 条全文、示例行全文，以及上面那段英文全文。`本 symbol 或本 cov` 不得出现。`skill.md` 不得出现 `failure_delta`、`symbol or cov`、`本 symbol 或`，也不得出现 `use at least two symbols`。`prompt_generation.jinja2` 不得出现 `use at least two symbols`。原有禁止词和必须出现的词保持：短名单 `{m, ss, sr, cj, jd, lh, eg, rb}`、`2-star`、`"covariate_family": "positioning"`、`macro_sentiment`、`n>=350`、`n_eff>=50`、`DirAcc>=0.52` 不在 `prompt_base.jinja2`；技能文件不出现 `dir_acc<0.52` 和 `低于该品种`，并保留英文 kill 与 `"covariate_family": "volatility"`；代次模板不出现 `macro_sentiment`，并保留 `adaptive gate (0.50-0.52)`。

## 第 5 步：只读计数

脚本是 `scripts/proposal_quality_census.py`。`census(root)` 只返回字典，不读期望数字，也不决定退出码。命令行的 `main` 调用它，打印 JSON，再与下面的期望比较；有一项不同就退出码 1。监督环不导入它。`scripts/sup_*.py` 和 `scripts/praxist_supervisor.py` 不出现这两个新脚本的模块名。15 个 run 目录有缺失时，该目录的提案文件数记 0，不抛 `FileNotFoundError`。

提案计数用第 1 步的同一套范围和「跳过 `*.prescreen.json`」规则。完成队列的 63 用字符串包含 `2026-11-17` 或 `2026-11-18`，不用第 2 步的 48 小时。`done_src_run_in_window` 只数 `src_run` 精确等于那 15 个目录名的行。方向只统计 `status=ok` 且 `protocol_fingerprint` 以 `f02b2a43` 开头的行。零行的判断是 `not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0`。布尔值 `False` 不算 0。缺字段不算零。

`prescreen_all_degraded_timeout` 仅当 `prescreen_files > 0`，且每个预筛文件都能解析、`status` 为 `degraded`、`note` 为 `TypeSafe API 超时` 时为真。文件数是 0，或有一份解析失败、状态不同、备注不同，都为假。

打印的 JSON 使用这些键：`direction_field`、`dir_acc_zero_rows_current_ok`、`hypothesis_v1`、`unparseable_proposal_json`、`proposal_json_excluding_prescreen`、`prescreen_files`、`prescreen_all_degraded_timeout`、`done_enqueued_at_on_2026_11_17_or_18`、`done_src_run_in_window`、`runs`。`direction_field` 的值是 `dir_acc`。`runs` 的每一项有 `id` 和 `proposal_json_excluding_prescreen`，并且 15 个目录名都在，缺失目录的计数是 0。序列化结果里不出现 `dir_ok`。脚本源文件的正文、注释、文档字符串、名字和报错里也不出现 `dir_ok`。不打印任何比率。

对照活仓时，期望是：提案文件 894，假设 879，无法解析 15，预筛 196 且 `prescreen_all_degraded_timeout` 为真，完成队列两个数是 63 和 13，零行数是 0，逐 run 数字与上面的表一致。这项比较只放在 `main`。不要改裁决文件，不要改价格或合约映射，不要停掉品种，也不要把期望数字改成新数。

单元测试调用 `census` 对临时目录，不读活的 `task_FM/experiments`，也不因此退出码 1。夹具里放一份假设、一份无法解析的文件、一份备注为 `TypeSafe API 超时` 且 `status` 为 `degraded` 的 `*.prescreen.json`，一条 `dir_acc` 为 0 的 ok 裁决，以及一条 `dir_acc` 为布尔 `False` 的 ok 裁决。断言预筛文件不进提案数，零行数是 1，预筛标志为真，输出里没有 `dir_ok`。另一次调用没有任何预筛文件，预筛标志为假。15 个目录名里没放进夹具的，计数是 0。再断言脚本源文件全文不含 `dir_ok`。活仓对照是 `main` 的验收命令，不是这条单元测试。

## 明确不做

| 要做的 | 界限 |
|---|---|
| 用活跃池和现有拒绝码解释库存类、日历类为什么没进完成队列 | 不另建协变量注册表，不把 `oi`、`ccl`、`nvi`、`calendar_cyclical` 标成不可执行 |
| 重提必须点名已失败的 `variant_id` | 不按 `proposal_id` 硬去重。`eg_oi` 仍是品种 `eg` 加活跃协变量 `oi` |
| 提示词要求一份生成里至少两个品种 | 不把 `cj` 或 `bu` 移出 `target_symbols`，不把 `eg`、`rb`、`jd` 写成死亡或停牌 |
| 报告写 `dir_acc`、是否过门、样本量和协议指纹 | 不把 `dir_ok=0%` 当成数据损坏，不改价格、合约映射或门禁公式。打分里 `(dir_acc - 0.52) * 200` 的加分保持，它不是硬门 |
| 计数脚本按本文件的窗口定义输出 | 不把审计报告里的百分比表做成配额、多臂老虎机或熔断 |
| 预筛超时维持现状 | 不加本地预筛替身，不探测预筛服务，不把超时写成已确认宕机 |
| 会话计数维持现状 | 不加 JSON Schema，不设会话成功率目标 |
| 历史提案和脏的运行数据留在原地 | 不清理实验目录，不改写已有裁决或完成队列 |

也不改 `scripts/praxist_goal.yaml`、`task_FM/config/covariate_pool.json`、`task_FM/task.yaml`、`search_policy`、`cohort_size` 的默认值 4。不加分年切片、跨品种迁移、留出集或模拟盘。

## 验收

实施前再跑一次 `pgrep -af '[p]raxist_supervisor.py'`。有进程就停，不在活树上改 Python。没有进程才可以改活仓。解释器用 `/home/abug/timesfm/.venv/bin/python`。不跑完整 pytest。

1. 第 1 步抽出函数后，先跑 `tests/test_harvest_proposals.py`。结果与抽出前一致，再跑实盘回放。
2. 实盘回放的结论文件要么不存在（检查失败，第 2 步不改选座），要么 `decision` 为 `reserve_last_seat` 或 `no_selection_change`，且 `failure_delta_rule` 为 `length_only`。只有 `reserve_last_seat` 才有选座测试。第 3 步之后不再运行回放脚本，验收仍读这一份文件。
3. 第 3 步之后再跑 `tests/test_harvest_proposals.py`，加上本文件点名的三条新测试。`tests/test_harvest_proposals.py::test_production_goal_survivors_per_cycle_is_3` 仍是 3。
4. 提示词测试：
   - `tests/test_prompt_symbol_authority_20261118.py`
   - `tests/test_praxist_evidence_ladder.py::test_prompt_base_selection_discipline`
   - `tests/test_praxist_evidence_ladder.py::test_templates_render_directive_context`
   - `tests/test_praxist_evidence_ladder.py::test_templates_render_without_agenda`
   - `tests/test_search_peer_surface_20261007.py::test_prompt_teaches_search_fields_and_keeps_success_delta`
5. 计数脚本的夹具测试通过后，对 `/home/abug/timesfm` 跑一次实盘计数。退出码 1 就停，不改数据。
6. 结束后 `search_policy` 仍是 `"shadow"`，`pgrep` 仍没有监督环进程。不提交，不推送，不重启。工作区里原有的运行数据保持原样。

## 下一步

五个实现边界已经写进本文件。宿主确认这份修订后，再写 `docs/superpowers/plans/2026-11-18-proposal-followup-plan.md`。写计划之前不改收割、不改提示词、不跑回放脚本。
