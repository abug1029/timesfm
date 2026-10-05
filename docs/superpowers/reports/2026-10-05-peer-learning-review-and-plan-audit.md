# 审核报告：同伴学习缺口复核与加固计划

> **日期**: 2026-10-05
> **对象**:
> - `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md`（156 行）
> - `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md`（118 行）
> **活仓**: WSL `/home/abug/timesfm`，审核开始时 HEAD `ee01b56`
> **方法**: 按评审附录重算 `task_FM/config/aligned_verdicts.jsonl`；对照 09:10 运行的提示词与交接；核对 `scripts/praxist_supervisor.py` 的注入函数与行号；用 checkpoint 的 `eval_end_ts` 核对 10-04 窗口。注册表在写稿后仍在追加，下文凡写「10:40 快照」均指 `decided_at < 2026-10-05T10:40`。
>
> **结论**: 报告需修订后采信。计划需修订后执行。

## 总评

评审把原文「结果没有回传、22 可能是幻觉」判错，这一刀是对的。截至 2026-10-05 10:40，当前协议动量通过数是 22/50，库存 3/13，日历 6/10。10-04 16:55 两侧的评估窗口也确实从 `2026-09-23 15:00:00` 换到了 `2026-09-30 15:00:00`。

判反的是来源。这三个数不是同伴自己读注册表算出来的。`task_FM/prompt_base.jinja2` 第 89 行已经 `{% include 'known_verdicts.inc.md' %}`。这份文件由 `scripts/praxist_supervisor.py` 的 `materialize_known_verdicts`（第 1227 行）写入 `task_FM/known_verdicts.inc.md`（路径常量在第 76 行）。慢环收尾（第 3329 行）和主循环（第 3405 行）都会按当前协议指纹重写它。`_effective_clue_lines`（第 1409 行）已经数了分母，打印时只留「N gate_pass」。09:10 那次提案是在复述提示词里已经写好的近失和族计数。

按现稿执行计划，会在这条注入通道旁边再造一份 digest，并用一条几乎打不中的 `success_delta` 去关成功侧缺口。

## 一、十二条裁定

| # | 文档裁定 | 本审核 | 证据 |
|---|---|---|---|
| 1 | `research_memory.jsonl` 全空，成立 | 成立 | 现扫到 212 个该文件，全部 0 字节。正文写 211，是之后又多了一个空文件 |
| 2 | `shared_store.db` 非空，原报告事实错误 | 成立 | 10-05 六个 run 为 196608–282624 字节，约 196.6–282.6 KB，与「196–282KB」一致 |
| 3 | 「结果没有回传」不成立 | 成立 | 三条引用的裁决都在，而且近失与族计数已经由提示词送进同伴 |
| 4 | 「22 来源不明」不成立 | 部分成立 | 10:40 快照三个数精确命中。来源是提示词里的 Passing families，不是同伴自算。同一条命令现在得到动量 (53, 24) |
| 5 | 41/96 是混协议，当前协议是 22/50 | 成立 | 10:40 时全协议动量为通过 44、共 121 条；当前协议之前的通过数恰好 22，当前协议是 22/50。第 22 个动量通过在 2026-09-29T22:57:45，变体 `sr_vwap_deviation_aligned_p6`，指纹前缀 `91ab913e` |
| 6 | 「下一轮是盲猜」不成立 | 成立 | `m_vor`、`ss_ccl`、`sr_calendar_cyclical` 复述的是提示词第 214–227 行和 375–384 行已经列出的近失与 DEAD 行 |
| 7 | `cycles_done` 225 | 部分成立 | 现值为 226、`phase` 为 fast。225 只能是评审当时的值，正文没有写查询时刻 |
| 8 | 10-04 43.6%（39）、10-05 60%（15），半成立 | 成立 | 注册表侧 17/39 = 43.6%，10-05 到 10:40 是 9/15 = 60.0%。130 和 50 不能从这份 jsonl 复现。分母恰好是注册表的 10/3，通过数不是同比例（原文族表加总是 51/130），「比率吻合」说重了 |
| 9 | E1–E6 改不了过门计算 | 成立 | `e155474`、`f4e8e90` 动的是失败记账、板块过滤和复测入选，没有改评估窗口、分母或 `dir_acc`。当天跑在 `f4e8e90` 上的 10 条里只有 2 条过门。它们可以改变以后提案什么，不能把当晚窗口从 09-23 改成 09-30 |
| 10 | 16:55 数据恢复是真正断点 | 部分成立 | 27/10 与 12/7 的算术成立，`eval_end_ts` 也在这一刀两侧整体更换。Fisher 精确检验双侧 p = 0.30，不能把 37.0%→58.3% 写成已经证实的跃升。`9522900` 的提交时间是 2026-10-04 15:47:28，不是 10-05 早晨 |
| 11 | 账本只记提案 | 成立 | 09:10 这个 run 有 6 份 `experiment_ledger.jsonl`，`proposal_authored` 共 3 条，没有 `gate_pass` 字段。其余是会话收尾 |
| 12 | 「完全没实现」过强，半成立 | 部分成立 | 「未实现」过强。同句里的「没有系统保证」不成立：族计数、品种合计、近失和截断后的逐行裁决每次主管循环都会写进提示词 |

## 二、定量证据

### 2.1 「22/3/6」

附录 A 不加时间过滤，当前文件是：

```text
calendar (10, 6), inventory (13, 3), momentum (53, 24),
term_structure (22, 10), volatility (15, 3)
```

脚本里的二元组是（条数, 通过数）。

加上 `decided_at < 2026-10-05T10:40` 后与正文一致：全文件 324 行 = 298 条 `ok` + 26 条 `no_data`；指纹分层为无指纹 169、`bd851c9c` 27、`91ab913e` 18、`f02b2a43` 110；当前协议 `ok` 为动量 (50, 22)、期限结构 (22, 10)、库存 (13, 3)、波动率 (15, 3)、日历 (10, 6)。26 条 `no_data` 全部没有指纹，时间在 2026-10-03T21:36 至 22:37，品种是 jd 与 sr。

多出来的 3 条是 10:49、11:01、11:10 落账的动量裁决（1 条不过、2 条过）。`aligned_verdicts.jsonl` 在 11:10 已含这 3 条，评审文件 11:30 才保存。附录 A 在文档保存时就已经对不上自己的期望值。10:40 快照本身的算术没有错。之后的 `known_verdicts.inc.md` 已写成 `momentum: 24 gate_pass`，说明注入通道在跟着文件走。

09:10 运行的 `gen_0/gen0_peer0_prompt.md` 第 214 行起就是：

```text
- momentum: 22 gate_pass
- term_structure: 10 gate_pass
- calendar: 6 gate_pass
- inventory: 3 gate_pass
- volatility: 3 gate_pass
```

会话日志没有读 `aligned_verdicts.jsonl`。第一个 Read 打在不存在的 `task_FM/task/known_verdicts.inc.md`，随后直接写下三份提案。

### 2.2 三条硬证据

1. 近失原文成立。交接第 13 行写了 `m_volatility_e7092bbdd14d (dir_acc=0.498)`。注册表这行是 2026-10-03T21:36:28、`status=ok`、`gate_pass=False`、`dir_acc=0.498`、指纹前缀 `f02b2a43`、`cov_override=stddev`。提示词第 227 行和第 378 行已经列出这行。
2. 失败规避原文成立。交接点了 `b796d1e1483d` 和 `82991327cde2`。两行都在：`sr_term_structure_b796d1e1483d` 的协变量是 `crack_spread_zscore`、`dir_acc=0.501`；`sr_term_structure_82991327cde2` 的协变量是 `crack_spread_slope`、`dir_acc=0.494`。都是 `term_structure`、`status=ok`、`gate_pass=False`。提示词第 224、375、384 行已经给了这两行。评审把它们写成 `sr_crack_spread_zscore` / `sr_crack_spread_slope`，那是协变量名，不是 `variant_id`。
3. 拒收门成立，行号也对。`scripts/praxist_supervisor.py` 第 2147–2150 行：已有失败且 `failure_delta` 短于 20 字就 `_reject("no_failure_delta")`。第 1395 行和第 1920 行的注释也在。匹配键仍是品种或协变量，二者满足其一即可。`prompt_generation.jinja2` 第 41–43 行有 exploit 角色的近失精炼指令。

### 2.3 10-04 16:55 与 37.0%→58.3%

附录 B 现在重跑仍是 pre (27, 10)、post (12, 7)。10/27 = 37.037%，7/12 = 58.333%。10-04 全天是 17/39 = 43.6%。10-05 到 10:40 是 9/15 = 60.0%，这一天稍后是 11/18 = 61.1%。这些行全部已是 `f02b2a43`，没有把 `no_data` 算进分母。

16:55 不是某一条裁决的时间。前一条是 2026-10-04T16:02:29，后一条是 2026-10-04T17:40:07。这个空档对得上恢复和重启：

- `logs/pull_restore_20261004.log` 修改时间 2026-10-04 16:50。
- `docs/superpowers/changelogs/2026-10-03-confirmation-channel-and-failure-accounting-fixes.md` 第 84 行：恢复拉取 16:04:59–16:55，抽样品种 1H 末端从 2026-09-23 14:00 推到 2026-09-30 14:00。
- 监督事件：PID 5207 于 15:14:38 退出，16:06:21 以 PID 403 再启动。

按 `variant_id` 去对 `data/cache/aligned_checkpoints/*.jsonl` 的 `eval_end_ts`：16:55 前 27 条全部是 `2026-09-23 15:00:00`，之后 12 条全部是 `2026-09-30 15:00:00`。`n` 仍是 588。这是固定长度窗口的内容平移。评审写的日期成立；checkpoint 上的钟点是 15:00，changelog 里的原始 bar 末端是 14:00。

同一张 2×2 表（通过/未通过 = 10/17 对 7/5）的 Fisher 精确检验双侧 p = 0.299。晚上 12 条里，17 时 1/3、19 时 2/3、21 时 3/3、23 时 1/3，不是一条抬高后保持住的台阶。窗口内容变了，这是更硬的事实；比率差在这个样本量下不显著。

评审用原文族表的期限结构 +27 个百分点和动量 +28 个百分点当「各族同向」的证据。那两列是按日对比，而且评审自己说不可复现。注册表按 16:55 切开是动量 3/10 到 4/8、期限结构 4/9 到 3/4。

`9522900` 提交于 2026-10-04 15:47:28，说明是「三环范式审计 + 新协变量入队（pmi/crack_spread_acceleration）」。全库裁决里没有 `pmi`，也没有 `crack_spread_acceleration`。它们解释不了当晚的窗口变化，「10-05 晨入队所以来不及」这个时间句是错的。

按 `git_rev` 拆 10-04 的通过数：`b4c2e00` 为 7/15，`f4e8e90` 为 2/10，`9522900` 为 1/2，`fadea75` 为 7/12。37% 是前三段混在一起。`fadea75` 这一段的 `dm_common_count` 从 588 降到 572–578，`n` 仍是 588。

## 三、缺口 G1–G6 与 §7

G2、G4 的格式问题、G5 的交叉矩阵、G6 是真的。

- **G2**。`prompt_base.jinja2` 第 80 行写着：过了硬门、即使没过 FDR，也不要当作已经解决再提一遍。收割只对 `failure_delta` 拒收。当前协议里 `gate_pass=True` 且 `fdr_pass=True` 的行只有 1 条：`m_momentum_b06ddbcd88e3`，`cov_override=vwap_deviation`，`run_mode=exploration`，`decided_at=2026-10-02T20:38:25`。其余过门行是 hard-gate-but-losing。快照正文对「已经解决」还要求 `run_mode='confirmation'` 且 `p_value` 非空。
- **G4**。`_effective_clue_lines` 只打印 `momentum: 22 gate_pass`，函数里的分母 `fam_ok` 没有印出来。评审举的 lh 56%→0% 是原文 §5 的分析表，不是同伴通道。
- **G5**。品种合计和族合计已经在提示词里。缺的是品种×族交叉格。
- **G6**。`sr_calendar_cyclical` 在 2026-09-17T15:43:59，`gate_pass=True`，`fdr_pass=False`，`dir_acc=0.617`，`n=588`，没有协议指纹。当前协议快照先滤掉旧指纹，于是写「另有 0 个协议组」。09:10 的同伴又提了这一对。在 `045c7e2` 下重测可以合法，提示词没有把这条旧裁决标成「不是当前证据」。

G1 不成立。注册表视图已经系统送进每一代提示词。缺的是分母、交叉矩阵、生成时刻，以及被预过滤掉的旧协议注记。

G3 要收窄。include 的节标题和逐行都带 `f02b2a43` 的前 12 位。不带戳的是交接对「22 gate_pass」的转述。现在 include 已是 24，09:10 的交接仍写 22。

§7 否决，对照原文第 115–123 行的示例 `{"ts","symbol","family","pass","fail","rate"}`：

- 再写一份 `cross_run_learning.jsonl` 会变成第二事实源。这一点成立。示例没有 `protocol_fingerprint`。这一点成立。
- 「schema 没有样本量、没有日期戳」不成立。`ts` 是时间戳，`pass` 加 `fail` 就是样本量。不该照搬的是裸 `rate`。
- 「再做一套 supervisor 聚合器整体冗余」只对了一半。族通过数和品种通过数已经在提示词里。原文要的 family×symbol 矩阵，现有 clues 没有。
- 不要去改框架渲染的 `memory_prompt`。这一点成立。仓库里已经在用的注入点是第 89 行的 include，不是一份新的 digest。
- 「提示词纪律已经有一半」对应得比较松。`failure_delta` 管的是失败变体，不管族统计。原文第 4 点只是要求引用历史统计。

## 四、附录命令

四条都只读，都跑过。没有跑会改状态或加载模型权重的命令。

| 命令 | 结果 |
|---|---|
| A，v4 族统计 | 现在动量是 (53, 24)，不是期望的 (50, 22)。其余四族一致。加上 10:40 截止后，动量回到 (50, 22) |
| B，10-04 16:55 分割 | pre (27, 10)、post (12, 7)，与期望一致 |
| C，三个标识是否在册 | `grep -c` 为 3 |
| D，议程、`no_failure_delta`、`dominant family` | `run_2026-10-05_05-27-04` 的 `agendas/` 有 gen1、gen2 和两份 `pi_prompt`。`no_failure_delta` 在第 1395、1920、2150 行。`site-packages/praxist` 排除 examples 后没有 `dominant family` |

`main_risk` 原句「All gen0 hypotheses remain untested (dir_acc=None) with no gate_pass evidence — cohort is over-proposing without validation gates」在 05-27 的 gen1 议程里，不在 09:10 那份。

## 五、计划 T0–T5

**T0** 仍然该做，次序也对：先改文档，再改代码。原文把在跑的回传说成不存在，把 22 说成可能是幻觉，还用混协议的 41/96 去打这个 22。叫 P0 的意思是「不先改掉，后面的任务会照着假缺口做」，不是线上事故。按计划第 24–27 行的替换句去做，会把「同伴自主读取注册表、反馈没有系统保证」写进被勘误的原文。10:40 的三个数和 16:55 两侧的 `eval_end_ts` 可以留下，必须写上截止时刻，也不要把 p = 0.30 的比率差写成已证实的跃升。

**T1–T3** 要补的分母、低样本标记、生成时刻、历史协议注记，有一部分是真缺口。落地方式会把已经在跑的注入再做一遍。`registry_digest.md` 不经过第 89 行的 include。T3「提案前必读」验收只证明句子渲染了，不证明数字进了上下文。09:10 的同伴连错误路径都读失败了，仍用提示词里的数字写提案。

近失定义也不一致。计划第 42 行是 `dir_acc >= effective_min - 0.02`，或者 `dm_status` 未决。活代码第 1430 行是 `0.49 <= dir_acc < effective_min`，第 1444 行只留 12 条。现有 `dm_status` 没有「未决」这个取值。两套定义会给同伴两份名单。

验收里的 momentum (22, 50) 是（过门, 样本），附录打印的是（样本, 过门），而且活数据已经离开这组数。手动核对应写成「digest 等于当场重算」，10:40 的数字只作历史例子。

**T4** 关不上 G2。命中条件是当前协议里 `gate_pass` 且 `fdr_pass`。这样的行现在只有上面那一条探索运行。计划第 41 行的成功清单又是全部 `gate_pass=True`，和第 76 行「复用 T1 成功清单」互相矛盾。按窄条件做，门几乎不触发；按宽清单做，会把大量未封账的过门变体拒掉。不要改 `_has_prior_failure` 的「品种或协变量」匹配。

14 天逃逸阀用 `decided_at` 的墙钟年龄代表「评估窗口已经移动」。窗口身份在 checkpoint 的 `eval_end_ts`。那条唯一的 `fdr_pass` 行是 10-02 的，窗口在 10-04 已经换到 09-30，阀却要到大约 10-16 才打开。窗口若 14 天都没动，阀仍会放行。计划也没有说明它和 `_maybe_enqueue_retests` 的自动复测是什么关系。

**T5** 没有假设热加载。文末要求先在隔离工作树里回归、核对指纹再重启，这一点是对的。10-04 15:14:38 那次单次 TERM 确实即时退出、`exit_code` 0，和 changelog 第 86 行一致。同一份 `docs/supervisor_restart_backlog.md` 第 78–104 行仍写着 SIGTERM 会卡在阻塞调用里，SIGKILL 不会刷新 `stop_report.json`。观察项「main_risk 那句是否消退」不稳定：05-27 的 gen1 有这句，09:10 的 gen1 已经是另一句。这句来自「这一代不跑评估」，digest 交上去它也会继续出现。

## 六、明确不做与风险

明确不做的四条与已锁定行为相容：不建第二份 jsonl，不改 site-packages，不改过门语义，不动空的 `research_memory.jsonl`。计划没有要求改自适应门、两同伴编制、失败侧的「品种或协变量」、家族死亡的确认性 `gate_pass` 与 `min_ok` 4、目标 `all_symbols_pass_phase1`、空的 token 上限、2000/2000/2028-10-02，也没有要求写 `preregistry.jsonl` 或改 0.08 / 0.80。

不做清单丢掉的，是「把矩阵和分母送进现有 include」。风险表盖住了窗口归因、队列深度、digest 头上的 mtime、误入库，以及 10-08 开闸不要和确认通道混着归因。没盖住的是：第二份名单和 `known_verdicts.inc.md` 同时存在；近失公式和活代码不一致；14 天墙钟和 `eval_end_ts` 不是一回事；T0–T4 的任务正文没有重复文末的工作树约束。

## 七、问题清单

### Issue 1 -- Severity: bug

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:48`
- Description: 「唯一自洽解释是同伴自己读注册表」与 09:10 提示词不符。第 214–217 行已有动量 22、日历 6、库存 3。G1（第 91 行）据此说反馈没有系统保证，这个缺口不存在。
- Suggestion: G1 改成「include 已送达族计数、品种合计、近失和截断后的逐行裁决；缺的是分母、品种×族矩阵、生成时刻，以及被预过滤掉的旧协议注记」。
- Status: open

### Issue 2 -- Severity: bug

- File: `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:24`
- Description: T0 的替换句会把 Issue 1 写进被勘误的原文，T1–T3 会跟着这个假缺口做。
- Suggestion: 替换句改成「回传已由 `known_verdicts.inc.md` 注入；缺口是这份快照没有分母、没有交叉矩阵、没有生成时刻、不展示旧协议先验，成功侧仍只有散文」。
- Status: open

### Issue 3 -- Severity: bug

- File: `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:33`
- Description: T1–T3 新建 `registry_digest.md`，再叫同伴去读。同伴实际使用的是 `materialize_known_verdicts`（第 1227 行）和 `_effective_clue_lines`（第 1409 行），调用点在第 3329 行和第 3405 行。新文件不经过 `prompt_base.jinja2:89`。
- Suggestion: 删掉平行 digest。在 `_effective_clue_lines` 给族计数补上 `(pass, n)` 和 `low-n`，在 `materialize_known_verdicts` 增加品种×族矩阵和 `generated_at`，并在过滤前为每个 `(symbol, cov)` 附一行旧指纹注记。仍由现有 include 送进提示词。
- Status: open

### Issue 4 -- Severity: bug

- File: `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:42`
- Description: 计划的近失是 `effective_min - 0.02` 或 `dm_status` 未决。活代码第 1430 行是 `0.49 <= dir_acc < effective_min`，第 1444 行只留 12 条。现有 `dm_status` 没有「未决」。
- Suggestion: 近失谓词调用或照抄 `_effective_clue_lines`。
- Status: open

### Issue 5 -- Severity: bug

- File: `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:71`
- Description: T4 只在 `gate_pass` 且 `fdr_pass` 时要求 `success_delta`。这样的行现在只有探索运行 `m_momentum_b06ddbcd88e3`。第 80 行禁止再提的是全部 `gate_pass=True`。T1 第 41 行的成功清单又是全部过门行，和第 76 行「复用成功清单」互相矛盾。
- Suggestion: 先写明要执法的是哪一句。若执法第 80 行，命中应是当前协议 `gate_pass=True` 的同一 `(symbol, cov_override)`。不要把探索运行自动当成封账成功，也不要改失败侧的「或」匹配。
- Status: open

### Issue 6 -- Severity: bug

- File: `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:74`
- Description: 14 天阀用 `decided_at` 代表「评估窗口已经移动」。10-04 的窗口更换记录在 `eval_end_ts`。唯一一条 `fdr_pass` 行在窗口已经移动之后仍要再等大约十天。
- Suggestion: 放行条件改成该 `(symbol, cov)` 最新裁决的 `eval_end_ts` 已经不等于当前数据末端对应的锚，或者直接依赖现有复测计划。
- Status: open

### Issue 7 -- Severity: suggestion

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:77`
- Description: `9522900` 是 2026-10-04 15:47:28 的提交。全库没有使用 `pmi` 或 `crack_spread_acceleration` 的裁决。同段用原文按日的 +27、+28 个百分点证明「各族同向」。
- Suggestion: 改成「新协变量提交于 10-04 15:47，且没有任何裁决使用它们」。同向只引用注册表的 3/10→4/8 和 4/9→3/4，并写上样本量。
- Status: open

### Issue 8 -- Severity: suggestion

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:73`
- Description: 27/10 与 12/7 的算术和 `eval_end_ts` 更换都成立。Fisher 双侧 p = 0.299，不能把比率差写成已经证实的跃升。
- Suggestion: 正文改成「16:55 切开的是两个评估窗口；通过率差在这个样本量下不显著」。附录 B 保持不变。
- Status: open

### Issue 9 -- Severity: suggestion

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:118`
- Description: 附录 A 没有 10:40 截止。文件在 11:10 已含后来的 3 条动量裁决，评审 11:30 才保存。
- Suggestion: 命令加上 `decided_at` 上限，或在期望值旁写「截至 2026-10-05T10:40；此后文件仍在追加」。
- Status: open

### Issue 10 -- Severity: suggestion

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:103`
- Description: 「没有样本量、没有日期戳」与原文示例不符。示例有 `ts`、`pass` 和 `fail`。缺的是协议指纹。「聚合器整体冗余」也忽略了原文要的品种×族矩阵现在并不存在。
- Suggestion: 否决理由改成「不要第二事实源；若要矩阵，加进现有 snapshot，并强制带协议指纹；不要只注入 `rate`」。
- Status: open

### Issue 11 -- Severity: suggestion

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:93`
- Description: G3 说统计不带指纹戳。include 里的节和逐行都带指纹前 12 位。不带戳的是交接转述。G4 用原文 §5 的小样本表当证据，真格式问题是第 1438 行只打印通过数。
- Suggestion: G3 限定为交接和会话记忆会丢掉指纹和时间。G4 改引 `_effective_clue_lines` 的输出格式。
- Status: open

### Issue 12 -- Severity: suggestion

- File: `docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:82`
- Description: T5 的两周观察没有可证伪的界限。「main_risk 那句是否消退」在 05-27 和 09:10 的 gen1 议程里已经不是同一句。任务正文没有重复文末的工作树约束。
- Suggestion: 验收改成抽查重启后第一份 `known_verdicts.inc.md` 是否含 `(pass, n)`、`generated_at` 和旧协议注记。T2 和 T4 写明只在工作树里改 `praxist_supervisor.py`。
- Status: open

### Issue 13 -- Severity: nit

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:12`
- Description: `research_memory.jsonl` 现在是 212 个全空文件，正文写 211。`cycles_done` 现在是 226，正文写 225。结论不变。
- Suggestion: 两个数字旁边加上统计时刻。
- Status: open

### Issue 14 -- Severity: nit

- File: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md:63`
- Description: anti_mainline 列出的是五个被忽略的族，不含动量。`cascade/cov_family.py` 的 `ALLOWED_FAMILIES` 还有 `momentum`。`PIAgentConfig` 在 `task_spec.py` 第 1328 行，`enabled` 默认值在第 1337 行。07-18 那个 run 有 gen1 议程，没有 gen2。
- Suggestion: 六族名单改抄 `ALLOWED_FAMILIES`。`「每个 run 都有 gen1 和 gen2」`改成「多数 run 有；07-18 只有 gen1」。
- Status: open

## 八、结论

T1 不能按现在的文本开工。先改评审的 G1 和「同伴自算」这句，再改 T0 的勘误稿，否则勘误会把错结论写进原文。

可以留下的是：10:40 快照的 22/3/6 和指纹分层；16:55 两侧 `eval_end_ts` 从 `2026-09-23 15:00:00` 换到 `2026-09-30 15:00:00`；三条被引用的裁决和 `no_failure_delta` 的行号；原文把回传说成不存在是错的；不要做第二份 jsonl；不要改过门语义和协议指纹；重启前在工作树里核对指纹。

实现时应改 `materialize_known_verdicts` 和 `_effective_clue_lines`，而不是新开一个同伴可以不读的 digest。成功侧的门要先对准第 80 行的集合。逃逸条件要跟 `eval_end_ts` 走，不要用 14 天墙钟。
