# Task 1 Review — 文档权威链与矛盾矩阵

- **被审**: `docs/superpowers/reports/2026-09-11-audit/task-1-doc-authority.md`
- **计划**: `docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 1
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-1-brief.md`
- **审核日**: 2026-09-11
- **范围**: 只审 Task 1 报告是否按规格取证；不改生产代码

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
| 权威链表 +「谁覆盖谁」 | §1 六层表 + 五条裁决规则 | 与计划 Spec 1–6 同序：磁盘/`STATE` → `loop-constraints`+yaml+`backtest_config`+`SCHEMES` → praxist/runbook/product_positioning/validation_criteria → `system_design` → specs → research。`module_freeze.md` 放进层 3 不推翻该序 |
| 每份根/docs 人类文档标角色 | §2 角色表 | 简报必读 11 份均在：`docs/README.md` / `docs/AGENTS.md` / `AGENTS.md` / `CLAUDE.md` / `STATE.md` / `loop-constraints.md` / `docs/praxist.md` / `docs/product_positioning.md` / `docs/system_design.md` / `docs/module_freeze.md` / `docs/validation_criteria.md` |
| 文内日期 vs `git log -1 --format=%ci` 与 STATE 头 | §3 | 独立 `git log` 对齐：STATE `ee1f176` 2026-09-10 06:23；loop `3374dd6` 2026-09-09 11:22；praxist/runbook/README/AGENTS `6bc43ba` 2026-09-09 14:27；system_design `a1b298f` 2026-09-10 14:58；CLAUDE `2855ebf` 2026-09-11 08:36；product/module_freeze/validation/yaml 初始提交 2026-09-03。早于 2026-09-09 的「当前」口径：`docs/README.md` L103 标 Important；合同文档不当快照作废 |
| 7 对矛盾：文档 A 原文 + 文档 B 原文 + 判定 | §4.1–4.7 | 七对全在。独立复验见下。权威层 1–2 赢，未把文档债写成活代码 bug |
| 过期文档清单 | §5 | STATE 快照/死链、praxist 现场、system_design 合同旧、README 标题、yaml diagnostic、research 号召、peer_evaluation_fix 状态撒谎均列出 |
| 会误导、但不在先审主链的文件 | §6 | 点名 `docs/praxist_integration_plan.md` 的 `/root/timesFM_fu`（有 2026-09-09 横幅）、STATE 死链、`system_design` §9.2 Windows 树、`AGENTS.md` `timesFM_fu`、原始三环 spec |
| 给 Task 2–4 的必查矛盾 | §7 | 方向/IC/gate/SS/标题红线/Windows/单位；spec diagnostic；research STEP=24 vs STEP=2。与计划探索期嫌疑同向 |
| 每条 finding：路径+行号、严重度、合同原文、磁盘/代码、只建议 | §8 | I-01…I-09、M-01…M-08。Critical=0，符合「文档过期 ≠ 代码 bug」 |
| 只写报告，不改生产 | git status | 生产路径无改动。本任务产出仅报告 |

硬门口径：计划全局句是「n≥350 且 IC≥0.05 且扣滑点 EV>0」。报告拆成两扇门（`gate_pass` 字段 = n+ic；经济过门另加 ev>0），与磁盘 `i_oi`/`m_ccl`、`evaluator.gate`、`pass_variants()` 一致。这是命名裁决，不是漏掉硬门。

## Quality 核对

| 检查 | 结果 |
|------|------|
| 是否把过期文档写成活代码 bug | **否。** 文首与 §9 写明：方向走加权 1H，IC 走 `2×\|dir_acc−0.5\|`，Vol 默认 OFF，peer 不评估。建议改文档，禁止改 `signal_contract.py` / `evaluator.gate` / `SCHEMES` |
| 7 对判定是否被磁盘/代码证伪 | **否。** 见独立复验。`m_ccl` 补强 I-03，STATE 只写了 `i_oi` 的判断成立 |
| 严重度是否抬高 | **否。** 文档债最高 Important。I-01 若被当成「按文档改信号」在 Task 2 可升 Critical；Task 1 的合同是权威链，留 Important 不阻塞 |
| 越权改生产代码 | 否 |

## 独立复验（活仓 `/home/abug/timesfm`）

```
权威层 1 磁盘
  aligned_verdicts.jsonl     26 行，status=ok×26
  n 分布                     396×21 / 588×3 / 324×1 / 142×1
  ic vs 2*|dir_acc-0.5|      26/26 匹配
  gate_pass=true             ss_vor ev=+11.06；i_oi ev=−2.46；m_ccl ev=−3.64
                             m_ccl decided_at=2026-09-11T10:27 git_rev=2855ebf8 max_points=396
  588                        m_oi / eg_nvi / eg_ha_body（2026-09-10，STEP=2 后）
  supervisor_state.json      phase=fast cycles_done=1
                             last_run_id=run_2026-09-10_03-06-50_primary_task_FM

合同原文
  CF-01 A                    docs/product_positioning.md:15-22
  IC 公式                    loop-constraints.md:48
  方案 A                     loop-constraints.md:49
  硬门预注册含 EV            docs/praxist.md:91-95
  硬门只判 n+ic              docs/praxist.md:115
  yaml diagnostic + ev>0     config/praxist_task.yaml:16-20
  SCHEMES ss                 config/prediction_scheme.py:132-133 calendar_cyclical
  STEP / 窗口                config/backtest_config.py:55-56 = 2 / 1200
  Vol 永不默认 ON            docs/module_freeze.md:8
  peer 待执行撒谎            docs/praxist_peer_evaluation_fix.md:4
  研究号召过期               docs/research/slow_loop_evaluation_points_research.md:6,20
  误导路径横幅               docs/praxist_integration_plan.md:3-5
  STATE 死链                 STATE.md:623,627,631  /root/timesFM_fu/...
  Windows 活仓               docs/system_design.md:737-738
  goal 无限预算              scripts/praxist_goal.yaml:15-19,22 aligned_max_points=600

代码
  position_from_forecast     cascade/signal_contract.py:5-10,32-45
  _compute_direction_v2      cascade/daily_model.py:189-207（仓内无 _compute_direction）
  evaluator.gate             task_FM/evaluations/fm_eval/evaluator.py:163,199-203 只判 n+ic
  aligned ic 写入            scripts/aligned_slow_loop.py:101
  pass_variants              scripts/registry_lib.py:39-45 = gate_pass and ev>0
```

ee1f176 对 `STATE.md` 只 +4 行（budget_exhausted 链接），快照表 L32–38 仍是 2026-09-09 的 `cycles_done=6` / `phase=slow` / 有限预算。与报告 I-07 一致。

## 非阻塞偏差（不必返工）

- `config/backtest_config.py` 写成 L56–57。实际 `STEP`/`EVAL_WINDOW_BARS` 在 **L55–56**。数值对。
- `system_design.md` §9.2 Windows 路径写成「约 L747–748」。实际激活命令在 **L737–738**。
- STATE 死链写成 L621–627。第三条 `See /root/timesFM_fu/...131108.md` 在 **L631**，同一模式，已在 §6 覆盖。
- `config/prediction_scheme.py` 未进 §3 日期表；git 最后是 `e9b559c`（2026-09-11）。SS 仍是 `calendar_cyclical`，不改变 4.4。
- `docs/praxist_peer_evaluation_fix.md` 自承未挖 git。实际 `9a8dc31` 2026-09-08，「待执行」仍在 L4。

以上不改变七对判定与权威链，不要求重写报告。
