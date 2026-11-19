# Peer 学习反馈硬化实施计划（v2，T0-T3）

> **日期**: 2026-10-05（v2，按独立审核修订；v1 见 ee01b56）
> **审核依据**: `reports/2026-10-05-peer-learning-review-and-plan-audit.md`（Issue 1-14；其关键断言已按 09-28 纪律独立复核，见 §0）
> **来源链**: 原报告（a5c1412）→ 评审 + 计划 v1（ee01b56）→ 独立审核 → **本计划 v2**
>
> **执行状态（2026-10-05 收口）**: T0 ✅ `4165554` · T1 ✅ `054de29`（重启后首份快照验收全过：pass/n+low-n、generated_at/protocol_fp8/registry_mtime 头、交叉矩阵 16 行、旧协议注记 34 行/2 组）· T2 ✅ `318daca` + T2b `739a583`（六路径测试 6/6；真实 v4 快照冒烟：118 行全可锚定、50 已成功组合 → 21 现窗执法 / 28 窗口平移放行；拒收日志带先验分类与 run_mode）· T3 部署 ✅（PID 403 单次 TERM exit_code 0 / uptime 26h；fp `f02b2a43` 不变、零基线重生；新 PID 77504）——**观察期开启（2026-10-05 → 10-19）**，观察项见 T3。
>
> **设计原则**（v2 修订）:
> 1. registry 唯一事实源；`task_FM/known_verdicts.inc.md` 是其按当前协议过滤的可再生视图，不另建平行快照
> 2. 注入统计一律带 `pass/n` + 协议指纹前缀 + `generated_at`；n<10 不出现裸比率
> 3. 只扩现有注入通道（`materialize_known_verdicts` / `_effective_clue_lines` / `prompt_base.jinja2:89` include），不新开 peer 可以不读的文件
> 4. 近失、已解决等谓词一律对齐活代码与 include 头部定义，不发明第二套
> 5. 拒收门逃逸阀跟 `eval_end_ts`（评估窗口锚）走，不用墙钟年龄
> 6. 不触碰 gate 评估语义——协议指纹不变、零基线重生
> 7. 代码任务一律在隔离 worktree 实现，回归失败集与 HEAD 恒等后方可合并；合并后先验指纹再重启

## 0. 背景（v2 更正，经独立复核）

审核报告修正了 v1 所依据的评审的两个关键误判，本计划据此重定向：

1. **「22/3/6」的来源是注入，不是 peer 自算**。`prompt_base.jinja2:89` include `known_verdicts.inc.md`（常量 `VERDICTS_INC`，supervisor:76）；`materialize_known_verdicts`（:1227）在慢环收尾（:3329）与主循环（:3405）按当前协议指纹重写；`_effective_clue_lines`（:1409）生成族计数但只打印通过数（`%d gate_pass`），分母 `fam_ok` 在函数内未打印。09:10 run 的 `gen0_peer0_prompt.md` 第 214-217 行即「momentum: 22 gate_pass / calendar: 6 / inventory: 3」。复核：10:40 快照（decided_at<2026-10-05T10:40）v4-only 族统计 momentum (50,22)、inventory (13,3)、calendar (10,6)，与 peer 引用精确一致。
2. **G1「反馈无系统保证」不成立**。真缺口（G1′）：快照族计数无分母、无品种×族交叉矩阵（品种级已有 n_ok/n_pass/best）、无 generated_at、旧协议先验被 N3 守卫静默排除（「另有 N 个协议组」只有计数无内容）。G3 收窄为「转述丢戳」（include 本身已带 fp12）；G4 证据改指 :1409 输出格式。
3. **16:55 是评估窗口切换，不是已证实的通过率跃升**。两侧 checkpoint `eval_end_ts` 整体更换（2026-09-23 15:00:00 → 2026-09-30 15:00:00，已复核 266 个 checkpoint 文件）；37.0%→58.3% 的比率差在该样本量下不显著（Fisher 双侧 p=0.2994，已复核）。归因表述一律以窗口事实为准，比率差只作伴随现象。

## 1. 任务分解

### T0（P0 · docs）三处勘误 + 审核报告入库 —— 先改文档再改代码

- [x] (a) 原报告 `reports/2026-10-05-peer-learning-gap-analysis.md` 顶部勘误块：
  1. 结论替换句（审核 Issue 2，不得写入「peer 自主读取注册表、反馈没有系统保证」）：「结果回传已由 `known_verdicts.inc.md` 注入每一代提示词（`prompt_base.jinja2:89`；supervisor 于慢环收尾与主循环按当前协议重写）；缺口是这份快照族计数无分母、无品种×族交叉矩阵、无生成时刻、不展示旧协议先验，成功侧仍只有散文约束」
  2. §1 通道表补三行：known_verdicts 注入通道（:76/:1227/:3329/:3405）、`no_failure_delta` 拒收门（:2147-2150）、PI agenda 回路
  3. §2/§4：「22/3/6」= 10:40 快照当前协议精确统计、由提示词送达，非幻觉非 peer 自算；原复核 41/96 混协议
  4. §5 归因：16:55 切开两个评估窗口（eval_end_ts 整体更换）；比率差不显著（Fisher 双侧 p≈0.30），不得写成已证实跃升；删除 E1-E6 机制归因；新协变量句改为「9522900 提交于 10-04 15:47，且截至审核无任何裁决使用 pmi/crack_spread_acceleration」
  5. 全部数字标注截止时刻与查询
- [x] (b) 评审报告 `reports/2026-10-05-peer-learning-gap-analysis-review.md` 顶部加审核指针块（不重写正文）：G1 不成立（Issue 1）；9522900 时间与「同向」证据勘误（Issue 7）；Fisher p=0.299（Issue 8）；附录 A 需加 decided_at 上限（Issue 9）；§7 否决理由部分不成立（示例有 ts 与 pass/fail，缺的是协议指纹；Issue 10）；G3 收窄、G4 改指 :1409（Issue 11）；211→212、225→226 带时刻（Issue 13）；族名单抄 ALLOWED_FAMILIES、PIAgentConfig :1328、07-18 仅 gen1（Issue 14）；变体名勘误（`sr_term_structure_b796d1e1483d`/`sr_term_structure_82991327cde2`，评审误写为协变量名）
- [x] (c) `docs/supervisor_restart_backlog.md` :78-104 调和勘误：结构根因分析保留为风险描述，但补记 10-04 15:14:38 实测单次 TERM 即时退出（exit_code 0，changelog :86）；操作口径与停机判据（stop_report.json / supervisor_events.jsonl）以 10-04 实证为准
- [x] (d) 审核报告若作者会话尚未入库，随本任务一并 commit（勘误链需要可追溯）
- 依赖：无
- 验收：原报告不含未修订的「盲猜/幻觉/矛盾」；不出现「peer 自算」结论；比率差不写成显著；所有数字带截止时刻

### T1（P1 · supervisor+prompt）扩展现有注入通道（合并原 T1/T2/T3；审核 Issue 3/4）

> 隔离 worktree 实现；回归失败集与 HEAD 恒等后方可合并。只改 `scripts/praxist_supervisor.py` 与 `task_FM/prompt_base.jinja2`，不动 site-packages。

- [x] `_effective_clue_lines`（:1409）：族计数从「N gate_pass」改为「N/M gate_pass」（pass/样本）；样本 <10 追加 `low-n`；不出现裸比率（分母 `fam_ok` 已在函数内）；Weak families 节同记法
- [x] `materialize_known_verdicts`（:1227）：
  1. 头部加 `generated_at`（ISO）+ `protocol_fp8` + 源 registry mtime
  2. 新增品种×族交叉矩阵：紧凑分组（按品种一行、族内 pass/n 列表），只列非空格，行数预算 ≤40，超出截断并注明
  3. 旧协议先验注记：N3 守卫（primary_fp 选择）排除的协议组不再只报计数——为有旧指纹裁决的 (symbol, cov) 附行（fp 前缀 + decided_at + gate_pass/dir_acc + 「仅上下文，不构成当前证据」），行数预算 ≤20，优先含 confirmation/gate_pass 行
  4. 近失节不动：谓词与截断即活代码（`0.49 <= dir_acc < effective_min`、12 条）——不新增第二套定义
- [x] `task_FM/prompt_base.jinja2` Known verdicts 节引用纪律：引用快照数字必须带 pass/n 与 generated_at；n<10 不得写成百分比结论；转述进 handoff/session 记忆时保留 fp12 前缀与 as-of（G3 收窄版）
- [x] 不新建任何快照文件、不加 .gitignore 条目（`known_verdicts.inc.md` 已被 .gitignore:106 忽略，由既有调用点 :3329/:3405 继续重写）
- 新测试：`tests/test_known_verdicts_injection_20261005.py`（fixture 混合协议 registry：族计数含分母与 low-n / 交叉矩阵只列非空 / generated_at 头 / 旧协议注记且不进主排名 / 近失谓词与 :1409 行为一致 / 幂等重写（除时间戳外输出恒等）/ 全文无裸比率）
- 依赖：T0
- 验收（可证伪）：合并重启后第一份 `known_verdicts.inc.md` 含 N/M 族计数、generated_at、旧协议注记；快照统计等于按当前协议当场重算（10:40 数字只作历史对照，活数据持续追加）

### T2（P2 · supervisor）success_delta 拒收门（原 T4 修正；审核 Issue 5/6）

> 隔离 worktree 实现；只改 `scripts/praxist_supervisor.py`（`no_failure_delta` 同域 :2147-2150 附近）与 `task_FM/prompt_base.jinja2`（proposal schema 增加可选字段说明）。

- [x] 执法对象 = `prompt_base.jinja2:80` 的集合：当前协议 `gate_pass=True` 的同一 (symbol, cov_override)。不按 gate+fdr 窄条件（当前仅 1 条探索行，打不中；「已解决」= confirmation+p_value 集合当前为空）；拒收信息中带先验分类（v2-pass / hard-gate-but-losing）与 run_mode，探索先验不当封账成功
- [x] 命中时要求 `success_delta` ≥20 字：点名先验 variant_id + 本次增量；拒收码 `no_success_delta`，计数日志与 `no_failure_delta` 同模式
- [x] 逃逸阀跟窗口锚走（Issue 6）：该 (symbol, cov) 最新 ok 裁决的 `eval_end_ts` ≠ 当前评估窗口锚 → 放行并记 notice（窗口已平移，旧 pass 不再是当前证据）。eval_end_ts 来源：新裁决落账行新增可选字段（append-only 兼容）；历史行按 variant_id 查 `data/cache/aligned_checkpoints`（已复核 266 文件均含 eval_end_ts）；仍不可得 → 放行并记 notice（fail-open = 现状语义）
- [x] 与 `_maybe_enqueue_retests`（:2422）的边界：本门只作用于 peer 提案校验路径；系统复测不经本门——实现时确认复测入队确绕过提案校验，若不绕过则加豁免标记
- [x] 不改失败侧 `_has_prior_failure`（:1390）的「品种或协变量」匹配
- 新测试：`tests/test_success_delta_gate_20261005.py`（命中拒收 / 未命中放行 / eval_end_ts 不等放行 / eval_end_ts 缺失放行 / 长度校验 / 复测豁免 六路径）
- 依赖：T0；建议在 T1 之后小步合并
- 验收：测试过；拒收计数入日志；慢环与复测队列深度无饿死迹象

### T3（P2 · 部署与观察）重启部署 + 观察两周（原 T5 修正；审核 Issue 12）

- [x] 部署：worktree 回归全绿（失败集与 HEAD 恒等）→ 合并 → 协议指纹校验（本计划不触碰评估语义，fp 应不变、零基线重生，实测确认）→ 单次 TERM 重启（10-04 实证即时退出；停机判据 stop_report.json / supervisor_events.jsonl）
- 观察指标（两周，均可证伪）：
  1. 重启后第一份快照含 N/M 族计数、generated_at、旧协议注记（T1 验收即时复查）
  2. peer handoff 对族计数的转述带 pass/n 与 generated_at（G3 收窄后的真风险点：转述丢戳）
  3. `no_success_delta` 拒收量、慢环队列深度、复测队列深度（无饿死）
  4. ~~PI main_risk「over-proposing」句消退~~（移除——该句源于「这一代不跑评估」，快照送达后仍会照常出现，不可作验收锚点；05-27 与 09:10 的 gen1 已非同句）
- 10-08 国庆开闸后确认通道流量与观察期重叠：归因先查数据/窗口断点（eval_end_ts），再查本计划改动
- 依赖：T1、T2 全部合入
- 验收：观察项 1-3 达成并留档

## 2. 明确不做

- 不新建 `registry_digest.md` 或任何平行快照（v1 核心错误，审核 Issue 3）
- 不新建 `cross_run_learning.jsonl` 第二事实源
- 不改框架（site-packages 的 memory_prompt 渲染、PI panel 机制）
- 不改 gate 评估语义、协议指纹、失败侧「品种或协变量」匹配
- 不动 `research_memory.jsonl`（框架脚手架占位）
- 不用墙钟年龄做逃逸阀（审核 Issue 6）

## 3. 顺序与依赖

```
T0（docs，先行）→ T1（扩现有通道）→ T2（success 门）→ T3（部署观察）
```

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| prompt 变更改变 peer 行为分布，gate_pass 率波动 | 归因先查数据/窗口断点（eval_end_ts），再查 prompt 变更 |
| success_delta 过严饿死慢环（09-24 同构事故） | 逃逸阀跟 eval_end_ts；慢环+复测队列深度监控；复测豁免 |
| eval_end_ts 在历史行缺失 | 新裁决落账携带可选字段 + checkpoint 回查 + 缺失放行（fail-open=现状语义） |
| 快照行数膨胀挤占 prompt 预算 | 交叉矩阵 ≤40 行、旧协议注记 ≤20 行预算，超出截断注明 |
| 快照与 registry 短暂不一致 | generated_at + 源 mtime 头部戳；既有调用点在批次回收后重写 |
| 10-08 开闸确认流量与观察期重叠 | 与确认通道观察合并跟踪，避免双重归因 |

## 5. 修订记录

- **v2（2026-10-05，本版）**：按独立审核（Issue 1-14）修订——①撤销平行 digest：原 T1/T2/T3 合并为新 T1，改为扩展现有 `known_verdicts.inc.md` 注入通道（补分母、交叉矩阵、generated_at、旧协议注记），依据是「22/3/6」实由该通道送达而非 peer 自算（09:10 提示词 :214-217 实证）；②近失谓词对齐活代码 :1409，不造第二套（Issue 4）；③success 门执法集合改 `prompt_base.jinja2:80` 全部 `gate_pass=True`，逃逸阀从 14 天墙钟改为 `eval_end_ts` 窗口锚（Issue 5/6）；④T0 勘误句采用审核 Issue 2 版本，增评审报告指针块与 restart backlog :78-104 调和勘误；⑤T3 验收改可证伪抽查、移除 main_risk 锚点（Issue 12）；⑥worktree 约束写入各代码任务正文。v1 的「两份名单并存 / 近失双定义 / 墙钟阀」三项风险随设计消除。
- **v1（2026-10-05，ee01b56）**：初版 T0-T5。核心落地方式（平行 digest、窄 success 条件、墙钟逃逸阀）经审核否决。

---

*执行遵循 09-28 纪律：实现前隔离 worktree 回归（失败集与 HEAD 恒等）、提交后先验指纹再重启；审核报告 Issue 1-14 全部落实到任务或勘误。*
