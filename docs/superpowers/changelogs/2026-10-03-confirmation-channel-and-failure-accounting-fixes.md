# 失败判定与确认通道修复 Changelog

**Date:** 2026-10-03（10-04 专家审核续审、E1-E6 全修与部署收口）
**Commits:** `e155474` / `b8a2118` / `b4c2e00` / `f4e8e90`（4 个）
**关联:** 收口计划 `plans/2026-10-03-three-loop-open-closure.md`（9 任务）；未决问题清单 `reports/2026-10-03-fm-a-open-issues.md`

---

## 一、背景

2026-10-03 三环收口计划启动。本 changelog 覆盖当晚两批修复及其 10-04 审核收口：

- **e155474**：未决问题清单 #1–#5（失败判定口径、板块断路器、停机信号、记账节流、审计字段）。
- **b8a2118 + b4c2e00**：#6「端到端盯首条确认裁决」验证中挖出的确认通道空评估死循环，及其后续副作用。
- **f4e8e90（10-04）**：对上述三笔的外部专家审核（P0/P1/P2 分级发现）经独立复核后全修。

### 原始 bug（b8a2118 所修）

confirm_from_ts=2026-10-03 00:00:00 已锁定，但 1H 数据尚未越过该边界。确认行一被派发就必然空评估 → 每次落一座 no_data 墓碑；墓碑不带 prereg_id，「已跑过」去重永远看不见它 → 每轮（~5.7 分钟）重复入队。实测：confirmation_enqueued 20 次、jd/sr 各 10 座墓碑（~~各 11 座~~，**勘误 10-04**：复核 registry 计数为 10/10）、registry 239 → 263 行。

## 二、修复内容

### 2.1 e155474 —— 失败判定只认可确认的 DM（清单 #1–#5）

1. 新增 `_is_confirmable_failure(v)`：失败 = 未过门且 dm_status ∈ {ok, set_mismatch_ok}。描述性 DM（set_mismatch_descriptive）与 no_common_cutoff 不是检验结论，不算失败。
2. `_has_prior_failure` 只认可确认失败（#4）。修复前任何 ok+unpassed 行都触发 no_failure_delta，实测单轮拒 1,922 份提案、可用候选 7 轮内 123 → 47。
3. `_sector_filter_check` 板块失败数同口径（#5）。修复前 agri 被记 7/10 失败（实为 6 描述性 + 1 无共同 cutoff）；确认产出前全库皆描述性行，板块迟早全失败触发断路器——与 2026-09-24 饿死同构、高一层。
4. `harvest_proposals` 遇 `_SHUTDOWN_REQUESTED` 立即中止且不返回半份候选（#3）。长扫描（当时 3,655 份提案）不再吃掉停机信号。
5. `confirmation_not_enqueued` 6h 节流（#2）：确认通道要跑 1.2–2.0 年，无条件每轮记账会写 30–40 万条/年（实测 17 分钟 8 条）。
6. family member 记录补 run_mode 字段（#1，可审计；正确性本由 make_member 对 run_mode != "confirmation" 抛错保证）。

### 2.2 b8a2118 —— 确认通道空评估死循环（D1/D2/D3）

- **D1 数据闸门** `_confirm_data_ready()`：fail-closed——1H 主连 max dt 须 > confirm_from_ts；查不到数据/异常也算未就绪；按 symbol 缓存 30 分钟避免每轮打库。在 `_maybe_enqueue_confirmations` 派发前过滤。confirm_from_ts 是预注册锁定字段（W3.7），改边界需新 prereg_id，故走闸门而非改边界。
- **D2 墓碑保身份**：`_no_data_verdict` 保留队列行的 run_mode/prereg_id/confirm_from_ts。墓碑仍非评估产物（status=no_data、n=0、p=1、fdr_pass=False），不进成功计数（pass_variants 要求 status=="ok"）。
- **D3 清理 family 污染**：生产 family_registry.jsonl 6 个 member 中 4 个是测试 vid（abababababab / 0eab46f69739 / 0dc4dfe4079c），虚增 family BH-FDR 的 K。清理为 2 个真实 member；原文件备份 `family_registry.jsonl.bak-20261003-fixture-pollution`；加守护测试。
- 附带：tests/test_confirmation_wiring.py 两个「派发→peek」链路测试补数据闸门桩（闸门是新增前置条件；闸门本身由 test_confirm_bugs 覆盖）。

### 2.3 b4c2e00 —— D2 副作用：墓碑不得永久占用去重名额

D2 让墓碑带上 prereg_id 后，`already` 去重会把「只有空评估墓碑」的预注册也视为已跑过——数据越过 confirm_from_ts 后永远不再派发，通道永久锁死；而闸门放行后的首派若仍空评估（闸门盲区，如窗口内尚无可标记样本）恰好落进这个状态。

修正：`already` 只计真实评估（status != "no_data"）。无 status 字段的真实裁决仍永久阻断——test_snapshot_prereg_id_blocks_second_enqueue 的语义边界保持。闸门负责数据未到位时不派发；~~闸门通过 ⇒ 评估窗口必有数据 ⇒ 真实裁决落账 ⇒ 去重永久生效~~（**该推论链 10-04 被专家审核证伪**：D1 只保证 ≥1 根 bar 越过 confirm_from_ts，确认评估需 n_confirm_required 个带 24h 前向标签的样本（jd 1199 / sr 986，HORIZON=24）；数据恢复后的首裁决必然是 status=ok 的未满样 peek 而非终态裁决，计入 already 会把预注册永久锁死——比墓碑占坑更隐蔽。修正见 §2.4 E1）。闸门盲区会以每循环一座墓碑的速度显性重试——有界、自愈、可见的故障信号，不做静默抑制。

### 2.4 f4e8e90 —— 专家审核 E1-E6 收口（2026-10-04）

专家审核（P0/P1/P2）逐条独立复核后全修，6 文件 +388/−14：

- **E1 终态语义（P0）**：`already` 去重只认满样终态裁决——status=="ok" 且 n_confirm_actual >= n_confirm_required（新增 `_confirmation_is_final`）。字段缺失视为非终态；no_data/error/timeout 墓碑都不占坑。修复 §2.3 被证伪的推论。
- **E2 重派节流（进程内）**：新增 `_CONFIRM_REDISPATCH` dict（6h TTL，仅真实派发盖戳）。纯 E1 语义下每个未终态预注册每 cycle 重派 peek ≈ 1.2 万行/预注册；节流后 ~4 行/天。重启各放行一次（进程内状态，有意为之）。notice refs 扩展 `redispatch_throttle` / `not_ready` 两个状态码，数据闸门未过不盖戳（下次仍重试，闸门本身廉价）。
- **E3 确认行不进探索复测**：`_retest_candidates` 排除 run_mode=="confirmation" 或带 prereg_id 的行。否则 peek（status=ok、gate_pass=False、0<n<RETEST_GATE_N）天然满足复测入选条件，被当探索复测会生成无 run_mode/prereg_id 的同 vid 探索行，快照 last-wins 覆盖 peek → prereg_id 从快照消失 → 去重失效 → 振荡。
- **E4 协变量闸门口径**：`_covariate_filter_check` 补 `_is_confirmable_failure` 门（与 e155474 的 `_sector_filter_check` 同口径），描述性失败不再计入协变量淘汰。
- **E5 慢环错误墓碑盖戳**：aligned_slow_loop 错误路径的 make_error_tombstone 后补盖 run_mode/prereg_id/confirm_from_ts 三字段（调用点级，:221 后）。否则慢环错误墓碑与 D2 修复前的空评估墓碑同型——不带身份、不进去重。
- **E6 停机信号外层贯通**：慢环外层批循环遇 `_SHUTDOWN_REQUESTED` break 后补 `return [], stats`。e155474 #3 只修了 harvest_proposals 内层；外层会继续派发下一批，停机信号照样被吃。
- **测试侧适配**：B1/B2（test_confirm_bugs docstring 与断言清理）、W1（wiring fixture 改满样终态）、W2/W3（清理）、C1-C3（test_covariate_filter：docstring 口径 + `_v` helper 默认 `dm_status="ok"` 保旧用例原意 + 新增 `test_descriptive_failures_not_counted`）、新增 **tests/test_confirmation_finality_20261004.py（11 项）** 锁定 E1-E6 语义。

## 三、验证证据

- **测试新增**：tests/test_fixes_20261003.py（~~10 项~~ **6 项**，勘误 10-04）、tests/test_confirm_bugs_20261003.py（5 项，含 test_no_data_tombstone_does_not_block_reenqueue——不打桩 rl、走真实队列写入断言）、tests/test_confirmation_finality_20261004.py（11 项，10-04）。
- **10-03 相关面子集门**（隔离 worktree，11 个测试文件）：259 passed / 1 failed；唯一失败 test_harvest_survivors_enter_slow_no_start_no_cycle 为 HEAD 基线既有红（独立于本批修复）。
- **10-04 全量恒等门**（f4e8e90，隔离 worktree /tmp/wt-e16-20261004 vs 干净 HEAD /tmp/wt-head-20261004）：
  - 定向 42 passed（confirm_bugs → finality 11 项 → wiring → fixes）；
  - HEAD 复跑 8 个失败文件基线：17 failed + 9 errors 全部预存（sector_filter 5、t7 3、vwap 4、index 2+9 errors、数据依赖 3：aligned real_data / daily_pred ab_bitexact / new_cov all_four_in_combo——与 1H 停更同因，见 §五.1）；
  - 既有红在 HEAD 同样失败（`assert 1 == 0`，test_supervisor.py:376）；
  - 全量 **1624 passed / 18 failed / 5 skipped / 1 xfailed / 9 errors**，failed+errors 与 HEAD 完全一致，**零新增失败**。唯一中间态新增（test_covariate_filter 4 例，E4 语义使无 dm_status 的合成行不再计数）由 C1-C3 适配收敛。
- **部署实测**（PID 5207，23:09:25 起载入 b4c2e00）：
  - 一个完整 cycle 内恰好 2 条节流后的 confirmation_not_enqueued（jd/sr；重启后节流字典重置、各记一次，随后 6h 静默）；
  - registry 267 行 / 26 座墓碑 **零增长**（修复前每 cycle 每预注册 +1 座）；
  - 常规业务不受影响：proposal_scan seen=3689、收割 3 条入队、slow loop 正常。
- **部署实测**（PID 403，2026-10-04 15:24 起载入 f4e8e90）：
  - 协议指纹 `f02b2a433fd572ea…` 磁盘现算一致 → 基线零重生（E1-E6 不触协议指纹；`compute_protocol_fingerprint` 只哈希语义常量）；
  - 首 tick 正常派发慢环批次（batch_4f7be781）；确认通道首 tick 恰好 2 条 confirmation_not_enqueued（jd/sr，refs 携带 E2C 新状态码 `not_ready`，.omc/supervisor_decisions.jsonl 15:25:22），随后 6h 记账静默——E2C 状态码与记账节流（重启各放行一次）在生产首次验证；数据闸门因 1H 停更 fail-closed，符合预期。

## 四、专家审核（10-03 提交 → 10-04 独立复核与全修）

- **审核方式**：外部专家对 e155474 / b8a2118 / b4c2e00 三笔做分级审核（P0/P1/P2），聚焦确认通道终态语义、重派行为与闸门盲区的时序推演。
- **核心发现（P0，已证实）**：§2.3 的推论链「闸门通过 ⇒ 真实裁决落账 ⇒ 去重永久生效」第二环起不成立——D1 只保证 ≥1 根 bar 越过 confirm_from_ts，而确认评估需 n_confirm_required 个带 24h 前向标签的样本（jd 1199 / sr 986）；数据恢复后的首裁决必然是 status=ok 的未满样 peek（`_finalize_confirmation_verdict` 既有语义），b4c2e00 的 already 语义会将其计为已跑过 → 通道永久锁死，且比墓碑占坑更隐蔽（peek 是「成功」行，status=ok）。
- **独立复核（09-28 纪律：审核断言必须独立复核）**：全部断言锚点逐一 grep/read 复核——`wait_for_batch` 实际签名为 4 参 `(batch_id, batch_records, registry_path, timeout=7200)`（needed 从 batch_records 派生），复核时纠正了测试草稿中错误的 5 参猜测（若未复核将 TypeError）；`_covariate_filter_check` 返回三元组 `(blocked, n_fail, n_pass)`；`time` 为模块级导入（:3 多导入行）；E 系全部锚点逐字匹配后才落地。
- **修复与裁决**：P0/P1/P2 对应 E1-E6 全修（f4e8e90），见 §2.4；测试 42 项定向 + 全量恒等门通过（§三）；无保留意见。
- **部署纪律**：提交前隔离 worktree 全量回归（失败集与 HEAD 恒等）；提交后先验证协议指纹不变再重启（避免意外触发基线重生波）。

## 五、新发现与待办

1. **1H 主连数据停更 11 天（已排查收口）**：jd/sr 的 max 1H dt 同刻停在 2026-09-23 14:00——10-04 复查为**全局停更**（30 个 futures_*.db 的 mtime 全部冻结在 09-23 17:47–18:04，单次顺序扫描特征，与 data_management.py 编排一致）；**不存在任何调度器**（无 crontab、无自定义 systemd timer、无 bash_history 记录、无 Windows 计划任务）→ 根因是手动管道在审计/预注册密集周被遗忘，非本批改动造成。闸门 fail-closed 恰好诚实暴露（无闸门则墓碑 churn 会持续刷 10 天+）。**10-04 处置（已完成收口）**：①恢复拉取 16:04:59–16:55 全程 ~50 分钟，28 品种三阶段全绿（collect_1h ✅ / pull_history_1h ✅ / daily_update ✅），抽样 5 品种（jd/sr/ss/cj/rb）max_dt 全部推进至 **2026-09-30 14:00**——实际漏掉 4 个交易日（09-24、09-28、09-29、09-30；中秋 09-25~27 本就休市），09-30 为国庆前最后交易日且无夜盘；3 个数据依赖测试全部自愈（real_data / ab_bitexact / all_four_in_combo，3 passed 42.6s）。②用户级 cron 挂上（**Mon-Sat 17:45** + Sat 02:35 抓周五夜盘，日志 logs/pull_cron.log；工作日 cron 扩到周六以覆盖调休交易日，正常周六为无害空拉）。**勘误**：初稿曾按「10-05 周一开闸」估算，经 data/holidays.py 2026 表核实国庆休市为 **10/1–10/7**，**10-10（周六）为调休交易日**——**闸门放行最早发生在 10-08（周四）数据入库后**（confirm_from_ts=2026-10-03 之后的第一个交易日）。
2. **实验指纹随数据流动（设计行为，但 v4 下未实测）**：`compute_experiment_fingerprint` 按设计「随运行变化」（target_snapshot_hash 哈希全序列，决定实验记录可否合并；研究问题身份由 research_target_hash 承载）。fp-vid 自 10-01（c0e3aa4）上线以来**从未在数据流动状态下运行**（停更先于上线）——10-04 恢复拉取已使序列延长至 09-30，此后任何 run 的实验指纹即发生变化，**观察窗口就此打开**（首个观察点 = 恢复完成后首个慢环批次），需观察 vid 轮换与队列/快照匹配行为是否符合预期（16:06 启动的 run 横跨恢复期，可能读到新旧混合快照——探索性 run 可接受，确认侧有 fail-closed 闸门不受影响）。
3. **supervisor TERM 行为（runbook 记载两处有误，已实证）**：PID 5207 于 10-04 15:14:38 收到单次 `kill -TERM` 后**即时优雅退出**（exit_code 0，uptime 57,916s），`supervisor_stopped{reason: signal_received}` 写入 data/cache/supervisor_events.jsonl 与 stop_report.json——**不在** runbook 所述的 data/cache/supervisor.out（标记位置记载错误）；退出亦非「最迟下个 tick（≤300s）」而是即时（时延记载错误）。未复现未决清单「SIGTERM 首次被忽略」。重启前需手动清理 stale 锁（supervisor.lock / aligned_slow_loop.lock，已按 clean 脚本先例处理）。
4. 已知盲区（接受并有界）：闸门通过但评估无可标记样本（summarize → None）时，墓碑 → 下轮重派，直至首个可标记样本出现——每循环至多一座墓碑，可见、自愈。

## 六、遗留

- 既有红 test_harvest_survivors_enter_slow_no_start_no_cycle（HEAD 基线同样失败）。
- 3 个数据依赖测试失败（real_data / ab_bitexact / all_four_in_combo）与停更同因——**10-04 恢复拉取完成后已验证自愈（3 passed，42.6s）**。
- #6「首条真实确认裁决」的实盘闭环：待 **10-08（周四）** 数据越过 2026-10-03 00:00 后闸门放行（国庆 10/1–10/7 休市，见 §五.1 勘误）→ E1 语义下首个未满样 peek 落账（不占坑）→ E2 6h 节流有界重派 → 样本累积至 n_confirm_required 后终态裁决。
- TERM 信号处理路径待查（§五.3）。
