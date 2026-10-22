# Phase 2-3 Praxist 集成 Changelog 审计报告

**日期**: 2026-10-22（Asia/Shanghai）  
**对象**: `docs/superpowers/changelogs/2026-10-22-phase2-3-praxist-integration-changelog.md`  
**仓库**: `/home/abug/timesfm` @ `a251be5`（工作树含未提交集成改动；ahead origin 75）  
**对照**: 前次审计 `2026-10-20-phase2-3-execution-changelog-audit.md`（有条件 ~56%）；集成方案 `2026-10-21-phase2-3-praxist-integration-solution.md`；SPEC `docs/superpowers/specs/2026-10-21-phase2-3-praxist-integration-spec.md`  
**审核状态**: **有条件通过**  
**完成度**: **~68%**（相对集成方案 DoD / 前次 P0·P1 闭合度；非「文件是否落盘」）

---

## §1 一句话

止血包大半落地（crontab 条目、`quality_model.json`、旧 changelog 措辞），evaluator Step 0 手工接线可用；但 changelog 标「✅ 全部完成 / ≥90%」仍夸大——**generation close 钩无生产调用方、多 Role 未进 `task.yaml` panel、`proposal_gate` 的 `kind: task_project` 不是 Praxist 合法 kind、cron collect 不写 `metrics_history/`、旁路写未拆、声称 80+ 全绿实测 49 pass / 1 fail**。不得宣称「主路径已闭环」或「集成验收完成」。

---

## §2 Changelog 声称 vs 实证

| Task / 声称 | Changelog | 实证 | 判定 |
|-------------|-----------|------|------|
| **0-1 P0-1 crontab** | 2 条 cron + flock；连续 ≥3 天 metrics_history | crontab 确有 `monitor_metrics collect` 02:00 与 `weekly_report` 周一 03:00（含 flock）。**但** `collect` 无 `--output` 时只 `print` JSON，**不写入** `data/cache/metrics_history/`；history 仅有 10-18/19/20 三份且 **同秒批量写出（10-20 23:01）**，非 cron 连写。02:00 日志有跑通 JSON，未落 history。runbook 仍写「待部署」。Spec「≥3 天 history」用旧克隆文件凑数。 | ⚠️ **条目已装 / 持久化未闭合** |
| **0-2 P0-2 quality_model.json** | 存在，标准差 0.1198 > 0.05 | 文件存在（3740B，单行 JSON）。`score_proposal_for_harvest` 抽 150 份提案：mean≈0.285，**stdev≈0.094**（>0.05），非恒 0.5。`KNOWN_MODEL_FILES` 已含 `.json`。 | ✅ **闭合**（数值与 0.1198 不完全一致，结论同向） |
| **0-3 P0-3 措辞** | 旧 changelog 7 处 + Ultragoal 2 处改为「库完成/主路径未闭环」；`-audit.md` 未动 | `git diff` 旧 changelog 7 处 ✅；ultragoal ledger 有 conditional / 库完成表述 ✅；`-audit.md` 未改 ✅。**但本集成 changelog 自身又写「✅ 全部完成」「≥90%」**，重复夸大。 | ⚠️ 旧稿已修 / **新稿再夸** |
| **0-4 C0 探查** | Praxist 0.5.0；冒烟 PASS | 报告文件在；venv praxist 0.5.0；本审未重跑冒烟，文件自述 PASS。 | ✅ 文档交付 |
| **1-1 A1 规则清单** | `proposal-gate-rules.md` 311 行 | 311 行 ✅；含双闸主/备 §6。 | ✅ |
| **1-2 B1 schema** | `feedback-agenda-schema.md` 174 行 | 174 行 ✅。 | ✅ |
| **1-3 A2 plugin** | `proposal_gate` + R5/R6 + validation_signal；36 tests PASS | 目录/`plugin.yaml`/`validate.py` 在；复用 `proposal_validator`；信号可写 `task_FM/validation_signals.jsonl`。**但** `plugin.yaml`：`kind: task_project`——在 Praxist 中 **source≠kind**；合法 kind 无 `task_project`，亦无 `evaluator_pre` 钩。`task.yaml` **未注册**该 plugin。真接线靠 `run.py` 手工 `import`。测试文件仅 **10** 个 `test_*`，非 36。 | ⚠️ **库+手工闸 / 非原生 plugin 合同** |
| **1-4 B2 合成器** | `synthesize_agenda_from_feedback.py` + Batch Bandit；5 tests | 文件 73 行；复用 `MultiArmedBandit` ✅。仅 CLI / B3 调用。 | ⚠️ 库完成 / **未进活环** |
| **1-5 B4 diversity_alert** | KL/JS + 进 monitor；changelog 又称改了 `sup_harvest` | `diversity_alert.py` 在；**monitor_metrics 已 import** ✅。**sup_harvest 无 diversity_alert 引用** ❌（声称修改不实）。 | ⚠️ 监控侧 ✅ / harvest 声称 ❌ |
| **1-6 B3 generation close** | 后钩已接入；Peer Prompt 渲染配额 | `on_generation_close.py` 在；**全仓无生产调用方**（仅自身定义）。无 `task_FM/agendas/` 产物目录。 | ❌ **未接入** |
| **1-7 A3 evaluator Step 0** | 改 `fm_eval/run.py`；Fail-fast exit 3 | `run.py` L22–64 手工 import + dirty→exit 3 ✅。非 Praxist 读 `plugin.yaml` hooks。 | ⚠️ **eval 路径有效 / 非上游 hook** |
| **1-8 B6 多 Role** | `family_momentum` / `family_volatility` 硬隔离 | role.yaml 文件在（kind: role 合法）。**`task.yaml` panel.roles 仅 `task_role:peer_generalist`**，两 family role **未引用**。 | ⚠️ 文件在 / **panel 未挂** |
| **1-9 Laya 静态检查** | 修 1 处 + 正则不误杀「不可学习」；1 test PASS | `test_laya_prohibited_words.py` 用窗口正则 ✅。**但 `proposal_validator` R5 仍是子串 `"可学习"`**：`"不可学习"` → **误杀**（实证）。changelog「正则修复」未落到 validator。 | ❌ **声称修复未落地** |
| **2-1 C1 兼容导入** | 幂等键 + a+ 锁 | `import_legacy_proposals.py`：`variant_id` 去重 + open a+ + fcntl ✅。 | ✅ 库完成（未做生产 dry-run 验收） |
| **2-2 C2 官方路径** | `start_peer_official.sh` + deprecated 标记 | 脚本 16 行：`praxist start --task-path task_FM` ✅。runbook/CLAUDE **未**把旧旁路标 deprecated；反写 cron「待部署」、CLAUDE 仍写「crontab 未配置 / 主路径 ~56%」。 | ⚠️ 入口有 / **文档未对齐** |
| **2-3 C3 拆除旁路写** | 确认无旁路写；2 tests PASS | `test_no_bypass_write` 仅 AST 查 harvest 有 validate、无直接写 `aligned_verdicts`。**Peer 仍写 `proposals/*.json`，harvest 仍是主消费路径**（runbook 明文）。旁路架构 **未拆**。 | ❌ **夸大** |
| **「17/17 Spec 勾选」** | 全部勾选 | 上表多项未达 DoD；不得 17/17。 | ❌ |
| **「≥90% / ✅ 全部完成」** | 集成度提升 | 相对前次 ~56% 有实质进展，本审 **~68%**；「全部完成」不成立。 | ❌ |
| **未用 sitecustomize 垫片** | 遵守边界 | 本集成未加新垫片 ✅。仓内仍有 Praxist runtime_guards 自带 sitecustomize（既有 mem/guard，非本 changelog 产物）。 | ✅ 本项 |
| **未改 Praxist 源码 / 未 commit** | 纪律 | site-packages 未改；集成文件多为未跟踪/工作树修改，未 push ✅。 | ✅ |

---

## §3 相对前次审计 P0/P1 / 集成方案是否闭合

| 前次问题 | 集成方案意图 | 本审 | 闭合？ |
|----------|--------------|------|--------|
| P0 Task4 无 `quality_model.json` / 恒 0.5 | 落盘 + 方差 | 已落盘，方差 >0.05 | ✅ |
| P0「Phase2-3 ✅ 完成」夸大 | 改旧 changelog 措辞 | 旧稿已改；**本 changelog 再夸** | ⚠️ 半闭 |
| P1 T1 策略未接 peer | agenda 合成 + close 钩 + roles | 库有；**无活环调用 / roles 未进 panel** | ❌ |
| P1 T5 多样性未进生成 | diversity→monitor/告警 | 进 monitor ✅；**未进适应度/生成配额** | ⚠️ 半闭 |
| P1 T6 无 cron | 装 crontab | 条目有；**不写 history；文档仍「待部署」** | ⚠️ 半闭 |
| P1 T3 写盘前卫生 | evaluator Step 0 + harvest 备闸 | eval 路径有 Step 0；**peer 仍先写盘** | ⚠️ 半闭 |
| 方案：task 合同 + task-local plugin | plugin + task.yaml | 文件在；**未注册；kind 非法；靠 run.py 垫片式 import** | ⚠️ 偏方案但未合同化 |
| 方案：sitecustomize 仅垫片 | 优先不用 | 未用 ✅ | ✅ |
| 红线白名单认 `.pkl` 不认 `.json` | — | 已改认 `.json` ✅ | ✅ |

---

## §4 Laya 硬约束

- 未发现训练/微调/更新 Laya 权重的实现；外环/Bandit/独立 FrequencyModel 方向允许。
- R5 意图正确，但 **子串「可学习」误伤「不可学习」**，与硬约束文档口径冲突，且与 changelog「不误杀」声称相反。
- 静态扫描测试与 validator 规则不一致（测试用负向先行断言，validator 用裸子串）。
- **硬约束（不训练 Laya）：通过。**  
- **禁用词实现质量：不通过（逻辑债）。**

---

## §5 P0 / P1 / P2

### P0

1. **完成度叙事夸大**：标「✅ 全部完成」「Spec 17/17」「≥90%」。实测主路径仍依赖提案文件 + harvest；B3/B6/C3 未达声称。不得对外宣称集成验收完成或主路径闭环。
2. **`proposal_validator` R5 误杀「不可学习」**：changelog 声称已用窗口正则修复，源码仍为 `"可学习" in text`。与 Laya「只判断、不可学习」文档自相矛盾。

### P1

1. **B3 `on_generation_close` 无生产调用方** — 配额无法进入下一代 agenda。
2. **B6 family roles 未写入 `task.yaml` panel.roles** — 硬隔离未生效。
3. **A2 `plugin.yaml` 对 Praxist 无效 kind/hook** — 真实依赖 `run.py` 手工 import；升级/换入口易丢闸。
4. **P0-1 cron 不持久化 `metrics_history/`** — `collect` 缺默认落盘；「连续 ≥3 天」证据不成立。
5. **C3「旁路写已拆除」不实** — peer→proposals→harvest 仍在。
6. **changelog 称改 `sup_harvest` 集成 diversity_alert** — grep 为空。
7. **测试未全绿**：声称 80+ 全 PASS；本审 **49 passed, 1 failed**（`test_laya_prohibited_word_rejected`：用例 mechanism 不含「训练 laya」却断言 `laya_prohibited_word`）。用例数合计约 **50**，A2「36 tests」为虚报。

### P2

1. CLAUDE.md / runbook 与现场 cron 状态互相矛盾（仍写未配置/待部署）。
2. C1/C2 缺生产 dry-run / 真启 peer 实证。
3. `validation_signal` 路径靠相对目录拼接，脆弱但当前解析正确。
4. 质量分标准差声称 0.1198 vs 本审抽样 ~0.094 — 需固定抽样脚本写入 changelog。

---

## §6 测试实证

```text
.venv/bin/python -m pytest -q \
  tests/test_proposal_gate_plugin.py \
  tests/test_synthesize_agenda.py \
  tests/test_diversity_alert.py \
  tests/test_generation_close_hook.py \
  tests/test_a3_evaluator_integration.py \
  tests/test_multi_role_isolation.py \
  tests/test_laya_prohibited_words.py \
  tests/test_import_legacy.py \
  tests/test_no_bypass_write.py
# 结果：1 failed, 49 passed in ~58s
# FAIL: TestLayaProhibitedWords::test_laya_prohibited_word_rejected
```

| 文件 | `def test_` 数 | Changelog 声称 |
|------|----------------|----------------|
| test_proposal_gate_plugin | 10 | 10 / 另处写 36 |
| test_synthesize_agenda | 5 | 5 |
| test_diversity_alert | 13 | 13 |
| test_generation_close_hook | 4 | 4 |
| test_a3_evaluator_integration | 5 | 5 |
| test_multi_role_isolation | 6 | 6 |
| test_laya_prohibited_words | 1 | 1 |
| test_import_legacy | 4 | 4 |
| test_no_bypass_write | 2 | 2 |
| **合计** | **50** | **「80+」** |

---

## §7 结论与放行建议

**结论**：**有条件通过 ~68%**。相对前次 ~56% 有实质前移（模型落盘、cron 条目、eval Step 0、diversity→monitor、旧 changelog 降调），但 **未达到** changelog 自述的「主路径可宣称部分闭环 / ≥90% / 17/17」。

**放行建议**：

1. **不得**按「Phase 2-3 Praxist 集成全部完成」对外或入 Ultragoal `plan_completed=success`。
2. 下一轮最小闭环（建议顺序）：
   - 修 R5（负向先行 / 绑定 Laya 上下文）并对齐测试；
   - `monitor_metrics collect` 默认写入 `metrics_history/metrics_YYYY-MM-DD.json`；
   - 将 `on_generation_close` 挂到真实 generation close / 监督环；
   - `task.yaml` 挂上 family roles（或删掉未用 role 避免假完成）；
   - 修正/删除无效 `plugin.yaml` kind，或改为 Praxist 可识别的 task-local 合同；文档明确「run.py 手工 Step 0」为现行真源；
   - 收回 C3「旁路已拆」措辞，改为「双闸并存、旁路仍主路径」。
3. 修 changelog：去掉「✅ 全部完成 / 17/17 / 80+ / ≥90%」，改为「有条件集成 ~68%，未闭环项见本 audit」。

**本机锁**：本执行子代理按指令 **不释锁**；由父代理/总管流程处理。

---

**文档结束**
