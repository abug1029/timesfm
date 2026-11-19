# Changelog: 提案质量后续五步

> **代码基线**: 工作区改动叠在 `df09a2b9d8013fd9179d64d508ecc2de63d5b813` 上，尚未提交。计划里写的 `50c848b09545230b4f0cc2d87556ca294829841f` 在续跑开始前已被仓库外的历史重写移出当前分支，两者的 `scripts/sup_harvest.py` 内容相同。本轮没有把分支重置回去。
> 日期：2026-11-19
> 规格：`docs/superpowers/specs/2026-11-18-proposal-followup-design.md`
> 施工单：`docs/superpowers/plans/2026-11-18-proposal-followup-plan.md`
> 缘起：`docs/superpowers/reports/2026-11-18-proposal-quality-2day-audit.md`。同目录 `优化建议.txt` 在 2026-11-19 批准按计划执行，并指出三处编码注意，已经写进施工单。
> 本文件不提交、不推送。监督环没有重启。

## TL;DR

上一轮只改了互相矛盾的提示词。这一轮补上规格里收窄的五件事：只读回放 15 个快环目录并冻结拒绝分布；因为库存和日历进了候选却进不了三席，收割给未死亡的族留最后一席；同一品种和协变量已有可确认失败时，`failure_delta` 必须点名那条裁决的 `variant_id`；提示词改成同一条配对说法，并要求同一次生成至少用两个品种；另加一个只读清点脚本，以后报告只引用它的输出。目标文件、门禁公式、`search_policy: "shadow"` 都没有动。

## 问题

2026-11-17 到 2026-11-18 的 15 个快环里，假设文件大量重复，乙二醇、螺纹钢、鸡蛋占了将近一半，库存和日历相关提案很多却很少进入执行。审计里的 `dir_ok=0%` 和几份报告之间的数字也不一致。

核对之后，这些现象不是另一套注册表、硬去重或数据损坏能解释的。`proposal_id` 相同不等于机制相同。`eg_oi` 是合法的品种加协变量。方向字段是 `dir_acc`，没有 `dir_ok`。`cj` 仍在目标品种里。

## 根因

提示词里的失败增量仍按「这个品种或这个协变量」来写，收割从 2026-10-08 起已经按品种和协变量的组合判断。长度够 20 字但没有点名失败 `variant_id` 的文本会被收下。选座在有四个及以上的族时，第一轮就占满三席，第四个族没有位置。报告数字来自各次手工计数，没有一份锁定口径的只读输出。

## 修复方案

1. `scripts/sup_harvest.py` 抽出 `classify_loaded_proposal`。回放脚本 `scripts/proposal_reject_replay.py` 自己走拒绝顺序，不调用 `harvest_proposals`，也不做预筛、不写待办。15 个目录共用一个 `seen_vids`，按目录修改时间从新到旧。族计数用提案里的 `cov_override` 查活跃池，不用提前返回时还没有的 `extra["family"]`。结论写在 `docs/superpowers/reports/2026-11-18-proposal-reject-replay.json`，`failure_delta_rule` 固定为 `length_only`。实盘回放退出码 0，`decision` 是 `reserve_last_seat`。从第三步收紧点名规则开始，这份文件没有再跑、也没有覆盖。
2. 因为结论是 `reserve_last_seat`，收割在 `top_k` 至少为 2 时先占满前 `top_k - 1` 个不同的族，再留一席给未选中、未死亡、且池族有效的候选。席位比较的是最近 48 小时完成队列里的次数、分数和 `variant_id`。窗口含两端。时钟带时区时退回原来的两轮选座，不用空字典顶替。缺文件时计数是空字典。运行时不读回放 JSON。三个选座函数的源码里没有写死 inventory 或 calendar。
3. `failure_delta_rejects` 放在 `scripts/sup_evidence.py`，分类函数只调用一次。没有可确认失败则不要求这段文字。有配对失败时，去掉首尾空白后不足 20 字、没有点名任何一条存着的 `variant_id`、或编号全是空白，都返回 `no_failure_delta`。内部空白仍算长度。大小写按原字符串比较。不读 `status`。
4. `task_FM/prompt_base.jinja2` 只改三处。示例和第 8 条改成组合条件：可确认失败是 `gate_pass` 为假且 `dm_status` 为 `ok` 或 `set_mismatch_ok`，原文要包含该组合至少一条失败裁决的 `variant_id`。原有的 Diversity 段不动，空一行后另起一段，要求同一次生成写出两份以上提案时至少用两个品种；已有可确认失败的组合，这一次最多再写一份，而且文字里要有那条 `variant_id`。这句没有变成收割拒绝码。`skill.md` 和 `prompt_generation.jinja2` 这一步没有改。
5. `scripts/proposal_quality_census.py` 只读计数。`census` 返回字典，账本数字和退出码在 `main`。`runs` 按脚本里的目录表原顺序。全文没有 `dir_ok`。它不导入回放脚本，收割和监督进程也不导入它。活仓清点退出码 0。

## 关键设计决策

- 不建第二套协变量注册表，不按 `proposal_id` 硬去重，不把 `cj` 或 `bu` 拉黑，不加名额、熔断或本地预筛兜底。
- 回放先于点名规则落盘。第三步改了分类函数之后若再跑回放，会把 `length_only` 覆盖掉，所以冻结文件的两个 sha256 一直核对到收口。
- 抽出分类函数之前，`tests/test_harvest_proposals.py` 已有两条失败。一条是工作区未提交的 `config/sector_map.py` 把农产品板块从 10 个品种改成 9 个，测试取前 9 个等于整组。另一条是已提交的死亡族计数要求当前协议指纹和样本量至少 350，夹具没有这两项。两条都不修，板块地图不还原。抽出和点名之后仍是这两条失败，其余原来通过的测试仍通过。
- 2026-11-19 的三处编码注意都落在实现里：族计数不读 `extra["family"]`；选座函数连文档字符串都不写 inventory、calendar；清点的 `runs` 不按目录新旧排序，账本数字不出现在 `def main` 之前。
- 提示词第 100 行仍是「gate_pass=False 且 status=ok：变体级 DEAD。没有 failure_delta 不得复活。」它不在允许改的三处里。第 8 条没有写成 `status=ok`。收割不按第 100 行放宽或收紧。

## 测试覆盖

解释器是 `/home/abug/timesfm/.venv/bin/python`。没有跑全仓 pytest。

- 回放单测 7 通过。抽出前后收割测试都是 37 通过、2 失败。
- 选座新测试加上 `test_production_goal_survivors_per_cycle_is_3` 和 `test_family_diversity_pass_one`，共 9 通过。
- 点名规则并入后，收割测试 41 通过、2 失败。空白编号那条先用不够 20 字的原文，审核退回；改成 25 字后，临时拿掉空白编号拒绝时测试失败，恢复函数后又通过。
- 提示词五个节点共 7 通过。红灯失败在 `prompt_base.jinja2` 还没有新的第 8 条。
- 清点夹具 3 通过。活仓清点退出码 0。

每步有独立审核。第三步第一次质量审核未过，补测试后复查通过。收口审核看整份衔接，结论是规格通过、质量通过。没有新的严重问题。

## 验收结果

- 回放结论是 `reserve_last_seat`，`failure_delta_rule` 是 `length_only`。冻结校验值到收口未变。
- `scripts/praxist_goal.yaml` 里 `search_policy` 仍是带引号的 `"shadow"`，`survivors_per_cycle` 仍是 3。
- 监督进程在各步改代码前和收口时都不在。没有重启。
- 索引区是空的。HEAD 仍是 `df09a2b9d8013fd9179d64d508ecc2de63d5b813`。没有 `git add`、`git commit` 或推送。

## 不做的事

- 不提交、不推送、不从 master 开工作树。
- 不改门禁公式、`task.yaml`、协变量池、`cohort_size | default(4)`。
- 不清理历史提案，不把 24 个品种名写进提示词。
- 不把 `dir_acc` 为 0 的裁决改掉。活仓清点若退出码不是 0，本轮会停，不会改期望数字。
- 完成队列若出现无法按 UTF-8 解码的行，选座计数会抛错而不是退回两轮选座。当前队列没有这种行，本轮不改。
- 不启动下一次快环。新提示词要等宿主自己开下一次快环才会被同伴读到。
