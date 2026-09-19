# Task 3 Review — superpowers specs / plans 过期与冲突

- **被审**: `docs/superpowers/reports/2026-09-11-audit/task-3-superpower-specs.md`
- **计划**: `docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 3
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-3-brief.md`
- **审核日**: 2026-09-11
- **范围**: 只审 Task 3 报告是否按规格取证；不改生产代码

## Verdicts

| 项 | 结论 |
|----|------|
| **Spec** | ✅ |
| **Task quality** | **Approved** |

## Must-fix gaps

无。

---

## Spec 核对（计划 Step 1–4 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| 分类全部 `docs/superpowers/specs/*.md`：日期、状态、是否被取代、是否已 merge | §1 全量分类表 16/16 | 活仓 16 个 `.md` 均入表。状态栏独立抽查对齐：hardening「完成后可启动」、compile-skip「待审阅」、control_plane「已批准稳妥启动」、09-02「待审阅」、07/08 各 Draft/待审核/Phase 1 in progress。git 最后提交：historical 全是 `10dbeb3`；hardening `5925156`；compile-skip `c2d2336`；control_plane `9609d28`；ACCEPT `14131bf` |
| 记一笔 md/txt 双份 | §1 末 | 16 md / 9 txt。字节级相同 6 对；followup-4 `11662` vs `10899`；alpha2 `18183` vs `14755`；截断名 `...-desig.txt` `17732`。忽略 txt 当合同，正确 |
| 三环 spec vs 方案 A：列出仍会被当现行合同的句子 | §2.2 表 + C1 | 09-02 L38–39 diagnostic 筛选 / 诊断幸存者；计划绑定解释 L37「幸存者 = diagnostic + status=ok + ev>0」。现行合同：`loop-constraints.md:48-49`、`docs/praxist.md:65-67`、方案 A spec L4/L37。生产收割：`_harvest_rows` → `harvest_proposals`（`scripts/praxist_supervisor.py:1289`） |
| Hardening vs 已落地：SPEC-004…013 哪些在 master；「待启动」过期；抽 2 个接口到代码 | §3 | merge `243693d` 2026-09-11 08:31 是 HEAD 祖先；`CLAUDE.md:257-259`「已合并至 master」。10 项全部在 master。抽查 SPEC-004 `effective_sample_size`（`evaluator.py:206`，`aligned_slow_loop.py:12,105`，`tests/test_system_hardening.py:15` `== 71`）；SPEC-012 `_compute_direction_v2`（`daily_model.py:189` / L180，`copilot.py:384,434`，测试 `:171+`） |
| 读 hardening 计划头部完成态 + `git log --oneline -20` | §1 / §3.1 | 计划 0 个 `[x]`。HEAD `2855ebf`；`git log -20` 含 `243693d` / `cd29bb6` / `5925156` |
| 产出「仍约束 / 已被取代 / 与 runbook 冲突」；哪份还敢当合同；不重写 spec | §0 + §10 | 三份半合同划分正确。建议只改文档头/指针，不改生产代码 |

Task 1 权威链：报告未点名 `task-1-doc-authority.md`（1–4 并行）。自行采用同一顺序（`loop-constraints` > `praxist.md`/runbook > specs），与 Task 1 同向。不构成返工。

Critical 口径：全局规则「文档过期默认最高 Important，除非会直接导致改错生产路径」。C1 是覆盖链把执行者送回 diagnostic 收割，会把仍完整的 `harvest_survivors` 接回主路径并让 peer 加载 TimesFM。按该文档执行会改错生产合同，升 Critical 成立。未把「文档没勾选」写成代码没 merge。

## Quality 核对

| 检查 | 结果 |
|------|------|
| 每条 finding 有 file:line 或 git hash | 通过。C1 / I1–I6 均带合同原文 + 代码或 git。抽查 C1 指针链、I1 `243693d`、I2 `ensure_compiled`、I4 harvest-during-429 与源码一致 |
| 是否把过期文档写成活代码 bug | 否。hardening/compile-skip 标的是启动姿态撒谎，不是「代码没做」。I1 明确不要因「待启动」整份作废接口合同 |
| 严重度是否抬高 | 否。07/08 历史 spec 停在 Draft 是 Important（I6），不是 Critical。方案 A spec §1 现在时是 Minor |
| 越权改生产代码 | 否。`git status` 生产路径无改动。本任务产出仅报告 |

## 独立复验（活仓 `/home/abug/timesfm`）

```
HEAD                         2855ebf  docs(CLAUDE.md): add System Hardening v1.2 capability table
hardening merge              243693d  2026-09-11 08:31:24 +0800  ancestor of HEAD
critical-fixes merge         cd29bb6  ancestor of HEAD
compile-skip impl            a8b0b6b / b32ec93 / b354b5e  均为 HEAD 祖先
ensure_compiled              cascade/daily_model.py:53
hourly 调用                  cascade/hourly_model.py:17,82,87,118
_harvest_rows                scripts/praxist_supervisor.py:1283 定义，:1289 调 harvest_proposals
harvest_survivors            :419 仍是完整 diagnostic 实现（测试仍调用）；生产路径已断开
paused_429 不挡 harvest      :1299-1300 与控制面 L191 一致；runbook L82 与 L123 仍写不 harvest
mem_guard                    DEFAULT_MAX_SLOTS=1 / MIN_AVAIL_BYTES=2.5GiB（mem_guard.py:43-44）
SPEC-004 n_eff 不进 gate     hardening spec L760；Non-Goals L40 硬门不变
宿主                         host_environment_assessment.md:10  7.7 GiB；控制面 L3 仍 15GiB
绑定解释                     docs/superpowers/plans/2026-09-02-praxist-three-loop.md:30-37
praxist.md 指针              :154 冲突时以 runbook「Spec 绑定解释」为准
runbook 指针                 :192 绑定解释优先于过时 spec 句
hardening 计划勾选           72 个 [ ] / 0 个 [x]（报告写 71）
compile-skip 计划勾选        36 个 [ ] / 0 个 [x]（报告写 35）
```

方案 A 生产路径成立。C1 的危险性比「仅留函数体」更硬：`harvest_survivors` 仍读 `evaluation_summary.json`、筛 `stage=diagnostic` 且 `ev>0`，测试锁的是旧收割；执行者按绑定解释第 4 条会把它接回去。结论方向不变。

## 非阻塞偏差（不必返工）

- hardening 计划未勾选是 **72** 不是 71；compile-skip 计划是 **36** 不是 35。全空、与 merge 矛盾这一事实不变。
- 09-02 spec 行号有漂移：慢环唯一写注册表在 `:91`（报告写成 L109–110，那两行其实是配额窗调度）；收割幸存者在 `:111` 不是 L125；禁改 `cascade/` 在 `:186` 不是 L213；known verdicts 在 `:100-101` 不是 L110–111。引文本身对。
- `harvest_survivors` 不是空壳，是完整 diagnostic 实现；「仅留函数体」对应方案 A spec `:149`「保留函数体，仅断调用」。生产 `_harvest_rows` 确实只调 `harvest_proposals`。
- I4 还可加一条：runbook Harvest 节 `:123` 也写「非 `paused_429` 时才 `harvest_proposals`」，与 `:82` 同错。不改变 I4。
- 未点名回链 Task 1 报告。并行时 Task 1 可能尚未落盘；权威顺序已自洽。

以上不改变 C1（绑定解释把方案 A 绕回去）和 I1（`243693d` 已 merge、文档仍待启动），不要求重写报告。
