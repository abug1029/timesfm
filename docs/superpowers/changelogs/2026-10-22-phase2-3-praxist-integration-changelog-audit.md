# Phase 2-3 Praxist 集成 Changelog 审计报告（重审）

**日期**: 2026-10-22 12:58（Asia/Shanghai）  
**对象**: `docs/superpowers/changelogs/2026-10-22-phase2-3-praxist-integration-changelog.md`  
**性质**: **重审**（相对 t137u / 前次有条件 ~68%）  
**仓库**: `/home/abug/timesfm` @ `c55404e`（ahead origin 79；含 d52078f / 51a399a / c55404e 等修复提交）  
**对照**: 前次审计 ~68%（`/workspace/shared/reviews/2026-10-22-phase2-3-praxist-integration-changelog-audit.md`）；集成方案 / SPEC  
**审核状态**: **有条件通过**  
**完成度**: **~78%**（前次 ~68% → 本重审；相对集成 DoD / 前次 P0·P1 闭合度，非「文件是否落盘」）

---

## §0 Changelog 双路径分叉（本重审强制核对）

| 路径 | mtime (CST) | 大小 | MD5 前缀 | 状态行 |
|------|-------------|------|----------|--------|
| **主证据**：`/home/abug/timesfm/docs/superpowers/changelogs/...changelog.md` | 2026-10-22 **12:46** | 10426 B | `0262b4f1…` | `⚠️ 有条件集成 ~68%`；Spec 勾选改为 11/17；测试改为 49→51 |
| **分叉旧稿**：`D:\\FlyBuddy\\docs\\superpowers\\changelogs\\...changelog.md`（`/mnt/d/FlyBuddy/...`） | 2026-10-22 **06:36** | 10182 B | `4e7ceba6…` | 仍写 **`✅ 全部完成` / ≥90% / 17/17 / 80+** |

**裁定**：以 **WSL timesfm** 为证据主路径（较新、与工作树/源码同仓）。D: 盘副本**未同步**诚实降调，属文档分叉风险；本 audit 覆盖写入两处同目录，避免只修一边。

**额外**：WSL changelog 已降调到 ~68%，但相对后续修复提交（d52078f/c55404e）**偏旧**——仍把已闭合的 **B6 / Laya R5** 勾成 `[ ]`。c55404e 提交说明声称「changelog 追加 P0-P2 闭环记录」，`git show --name-only c55404e` **未改该 changelog**（仅 rules.md / import_legacy / run.py）。

---

## §1 一句话

相对 t137u：前次 **P0-R5、P1-B6、collect 默认落盘、diversity→harvest、plugin kind 清理、测试 51 全绿** 已在源码闭合；**叙事夸大在 WSL 主 changelog 已降调**，但 D: 仍夸、且 Bandit `on_generation_close` **仍无生产调用方**（刻意从 `run.py` 拆掉后改称「Praxist PI 原生」——自定义配额环仍未接入）。主路径仍是 peer→proposals→harvest。完成度 **~78%**，不得宣称「≥90% / 主路径闭环 / 集成验收完成」。

---

## §2 Changelog 声称 vs 实证（相对现码）

| Task / 声称 | WSL Changelog | 实证 | 判定 |
|-------------|---------------|------|------|
| **0-1 P0-1 crontab + history** | `[ ]` 未勾（诚实） | crontab 仍有 collect 02:00 / weekly 03:00 + flock。`collect` **无 `--output` 时默认写入** `data/cache/metrics_history/metrics_YYYY-MM-DD.json` ✅。已有 `metrics_2026-10-22.json`（含 diversity_alert）。旧 10-18/19/20 仍同秒批量。Spec「连续 ≥3 天 cron 证据」仍不足。 | ⚠️ **代码闭合 / Spec 证据半闭** |
| **0-2 quality_model.json** | `[x]` | 仍在；前次已验 stdev>0.05。本重审未重抽。 | ✅ |
| **0-3 措辞** | 自身已改为 ~68% | WSL ✅；**D: 仍 ✅全部完成** ❌；c55404e「追加闭环记录」未发生。 | ⚠️ **主仓诚实 / D: 分叉** |
| **A2 plugin** | `[ ]` | `plugin.yaml` **已去掉非法 kind/hooks**，注明手工 Step 0。`run.py` 仍 import + dirty→exit 3。非 Praxist 原生 hook。rules §7 已文档化风险。 | ⚠️ **手工闸有效 / 非原生合同** |
| **B3 generation close** | `[ ]` | `on_generation_close.py` 在；**生产无调用方**（仅 hook 自身 import synthesize）。`run.py` 注释称交 Praxist PI；rules §B3-3 写明 **task 无 generation_close 配置、Praxist 不提供 task-level hook**。Bandit 配额未进原生 agenda。无 `task_FM/agendas/` 产物。 | ❌ **语义撤退 ≠ 接入** |
| **B6 多 Role** | `[ ]`（changelog 过旧） | `task.yaml` panel.roles **已含** `family_momentum` / `family_volatility` + role.yaml。 | ✅ **源码已闭**（changelog 勾选滞后） |
| **Laya R5** | `[ ]`（changelog 过旧） | `proposal_validator` 用 `(?<!不)可学习`；「不可学习」不命中、「可学习Laya」命中。`test_proposal_gate_plugin` 含对应用例。 | ✅ **源码已闭** |
| **B4 / harvest diversity** | `[x]` B4 | `sup_harvest` **已** `compute_diversity_alert`；monitor 亦有。前次「sup_harvest 声称不实」**已闭**。 | ✅ |
| **C1 导入** | `[x]` | 幂等+锁；`--dry-run` 扫到 5 文件 **0 valid / 5 invalid**（prescreen 缺字段）。增强有、生产干跑未证明可导入。 | ⚠️ |
| **C2 官方路径** | `[x]` | `start_peer_official.sh` 在；runbook/CLAUDE 已改「crontab 已部署 / ~68%」。CLAUDE 仍一句写「B3 已挂 evaluator」与后文「B3 未闭环」**自相矛盾**。 | ⚠️ |
| **C3 旁路拆除** | `[ ]` | rules §8 **明文：旁路未拆**。`test_no_bypass_write` 只 AST 查 harvest validate。架构仍 peer→proposals→harvest。 | ❌ **未拆（文档已诚实）** |
| **「51/51」「修复后全绿」** | 写明 51 | 本审复跑 **51 passed**（约 53.6s）。用例合计 11+5+13+4+5+6+1+4+2=**51**。 | ✅ |
| **「17/17 / ≥90%」** | WSL 已删；D: 仍有 | 不得。 | ❌（仅 D:） |

---

## §3 前次 P0/P1 闭合表（相对 t137u）

| 前次项 | 本重审 | 闭合？ |
|--------|--------|--------|
| **P0** 叙事夸大（✅全部完成/17/17/≥90%） | WSL changelog 已改为 ~68%/11/17；**D: 未改** | ⚠️ **主仓闭 / D: 开** |
| **P0** R5 子串误杀「不可学习」 | 负向先行正则进 validator；实测 + 测试通过 | ✅ **已闭** |
| **P1** B3 无生产调用 | 仍无；从 run.py 拆掉并文档化「应交」 | ❌ **仍开**（且 CLAUDE 一句仍谎称已挂） |
| **P1** B6 roles 未进 task.yaml | panel.roles 已挂两 family | ✅ **已闭** |
| **P1** plugin.yaml `kind: task_project` | kind/hooks 已移除并注明手工加载 | ✅ **已闭**（残余：非原生 hook） |
| **P1** cron collect 不写 metrics_history | 默认落盘已实现；有 10-22 文件 | ✅ **代码已闭**（≥3 天连续证据仍弱） |
| **P1** C3「旁路已拆」不实 | 改为未勾选 + rules §8 承认未拆 | ✅ **措辞已闭** / ❌ **架构仍开** |
| **P1** diversity→harvest 声称空 | harvest 已接入 | ✅ **已闭** |
| **P1** 测试 49p/1f、虚报 80+ | **51 passed**；changelog 已改 51 | ✅ **已闭** |

**前次已闭合且本审抽查仍成立**：quality_model.json；crontab 条目；旧 Phase2-3 changelog 降调；KNOWN_MODEL_FILES；fm_eval Step0；diversity→monitor。

---

## §4 Laya 硬约束

- 未发现训练/微调/更新 Laya 权重；外环 Bandit / FrequencyModel 方向允许。
- R5 正则与测试对齐；「不可学习」不再误杀。
- **硬约束：通过。禁用词实现：通过（本重审）。**
- 文档债：`proposal-gate-rules.md` 总表仍标 R5/R6「❌ 待实现」，与源码不符（R5/R6 均已有实现）。

---

## §5 P0 / P1 / P2（本重审）

### P0（仍开）

1. **D: changelog 分叉仍夸大**：`D:\\FlyBuddy\\...changelog.md` 仍「✅ 全部完成 / ≥90% / 17/17」。若有人只读 D: 会误判验收完成。须与 WSL 对齐或标明废弃。

### P0（本重审已闭）

- ~~R5 误杀~~ → **已闭**。
- ~~WSL 主 changelog 自述 ≥90%~~ → **已降调**（但仍滞后于源码勾选）。

### P1（仍开）

1. **B3 Bandit/agenda 活环未接**：自定义 `on_generation_close` / `synthesize_agenda_from_feedback` 无生产调用；Praxist 原生 PI agenda ≠ Phase2 GenerationStrategy 配额环。不得把「拆掉错误挂点」写成「已接入」。
2. **C3 旁路架构仍在**：peer→proposals→harvest 主消费路径未拆；仅文档承认。
3. **A2 仍靠 run.py 手工 import**：升级/换入口可静默丢闸（rules §7 已写，风险仍在）。
4. **P0-1 Spec 连续 ≥3 天 history**：代码已能落盘，但 cron 新路径有效证据主要是 10-22 一天；旧三天同秒克隆不算。
5. **文档一致性**：WSL changelog 未把已闭的 B6/R5 勾上；rules 总表 R5/R6 仍「待实现」；CLAUDE「B3 已挂 evaluator」与「B3 未闭环」矛盾；c55404e 声称改 changelog 但未改。

### P2

1. C1 dry-run：样例 5/5 invalid（prescreen 缺字段）——导入器增强未证明生产可导入。
2. `on_generation_close` 硬编码 `AGENDAS_DIR=/home/abug/timesfm/task_FM/agendas`（目录当前不存在）。
3. 质量分 stdev 数字未用固定抽样脚本钉死。

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
# 结果：51 passed in ~53.6s（前次 49 passed / 1 failed）
```

| 文件 | `def test_` | 前次 |
|------|-------------|------|
| test_proposal_gate_plugin | **11**（+不可学习用例） | 10 |
| test_synthesize_agenda | 5 | 5 |
| test_diversity_alert | 13 | 13 |
| test_generation_close_hook | 4 | 4 |
| test_a3_evaluator_integration | 5 | 5 |
| test_multi_role_isolation | 6 | 6 |
| test_laya_prohibited_words | 1 | 1 |
| test_import_legacy | 4 | 4 |
| test_no_bypass_write | 2 | 2 |
| **合计** | **51** | **50** |

R5 现场：`"不可学习…Laya…"` → 无 laya 命中；`"可学习Laya"` → `learnable_laya`。

---

## §7 结论与放行建议

**结论**：**有条件通过 ~78%**（相对 t137u **~68% → ~78%**，+约 10pt）。止血与文档诚实明显改善；**生成策略外环仍未进入下一代 peer 配额**，旁路主路径未拆，D: changelog 仍夸大。

**对比前次放行清单完成度**：

| 前次 §7 建议 | 本重审 |
|--------------|--------|
| 修 R5 | ✅ |
| collect 默认写 history | ✅ |
| 挂 on_generation_close 真环 | ❌ |
| task.yaml 挂 family roles | ✅ |
| 修正 plugin.yaml kind + 文档真源 | ✅（kind 去；仍手工） |
| 收回 C3「已拆」措辞 | ✅（架构未拆） |
| changelog 去掉全部完成/90% | ✅ WSL / ❌ D: |

**放行建议**：

1. **不得**宣称「Praxist 集成验收完成 / 主路径闭环 / ≥90% / 17/17」。
2. **必须**同步或作废 `D:\\FlyBuddy\\...changelog.md` 夸大稿。
3. 下一轮最小闭环：把 Bandit/`synthesize_agenda` **真正**接到 Praxist generation_boundary / chair agenda 产物（或监督 cron），并留下 `task_FM/agendas/research_agenda_gen*.yaml` 现场证据；再积累 ≥3 天 cron history；更新 rules 总表 R5/R6 与 WSL changelog 勾选。
4. Ultragoal / 对外状态保持 **conditional**，不可 `plan_completed=success`。

**本机锁**：本执行子代理按父指令 **不释锁、不联系总管、不向用户发消息**。

---

**文档结束**
