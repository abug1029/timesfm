# Phase 2-3 × 上游 PRAXIST 集成解决方案（细化）

**日期**: 2026-10-21（Asia/Shanghai）  
**作者**: 总管  
**依据**:
- 本机报告 `docs/superpowers/reports/2026-10-21-phase2-3-integration-barriers-analysis.md`
- 审计 `docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md`（有条件通过 ~56%）
- 上游仓库 [sapientinc/PRAXIST](https://github.com/sapientinc/PRAXIST)（调研时约 5500★；文档入口 [praxist.sapient.inc/en/docs](https://praxist.sapient.inc/en/docs)）
- 上游合约：`AGENTS.md`、`docs/concepts/architecture.md`、`docs/guides/research-loop-variant-generation-flow.md`、`docs/guides/plugins.md`

**状态**: 方案文档（待用户拍板开工；本文不授权改代码 / commit / push）

---

## 0. 一句话结论

Phase 2-3 **库代码已齐、主路径未闭环**的根因，不是「上游绝对无 hook」，而是你们当前跑法是 **site-packages 内 peer → 提案文件 → `sup_harvest` 旁路**，绕开了上游设计的 **task 合同 + findings 证据链**。

正确主线：**把生成策略 / 多样性 / 提案卫生落到 task 合同与 task-local plugin**；`sitecustomize` 只作迁移垫片；crontab 立刻补上。不要以长期 fork 或整段抽离 peer 作为默认路径。

---

## 1. 问题复述（与障碍报告对齐）

| 闭环 | 库侧状态 | 主路径状态 | 卡点 |
|------|----------|------------|------|
| 生成策略 → peer 生成 | `scripts/generation_strategy.py` ✅ | ❌ 无调用方 | peer 在框架内 |
| 多样性 → 生成 | `scripts/diversity_metrics.py` ✅ | ❌ 无接入点 | 同上 |
| 提案卫生 → 写盘前 | `proposal_validator.py` ✅；harvest 已调 ✅ | ❌ peer 写盘前未调 | 同上 |
| 监控自动化 | `monitor_metrics.py` 等 ✅ | ❌ 未配 crontab | 执行疏漏 |

审计侧仍阻塞「Phase 2-3 验收完成」叙事；另有 P0（如生产 `quality_model.json` / changelog 措辞）与本文正交，需并行关掉，但不替代集成方案。

---

## 2. 上游 PRAXIST 边界（解决方案的坐标系）

### 2.1 所有权

| 所有者 | 负责 | 禁止 |
|--------|------|------|
| Praxist core | 协议、解析、存储、replay、凭证、预算、扩展接口 | 任务事实、具体科学假设 |
| Generic plugins | runtime / provider / workflow_stage / tool_server / graph / budget / topology… | 只服务单一任务的事实与 prompt |
| **Task project** | 目标、基线、evaluator、metrics、证据政策、roles、prompts、assets | 改 Praxist 源码、替代 `praxist start` |
| Run directory | 单次 run 的冻结配置与证据 | 当作「当前任务配置」的可变真相 |

官方入口：`praxist start --task-path <task> --daemonize --json`。

### 2.2 一代研究环（写盘与继承顺序）

1. Resolve & freeze run  
2. Build generation context（task prompt、peer role、agenda、可选 DIG/QD、frontier/incubator/Gems、evaluator 合同）  
3. Peer 工作：假设 → `variants/<variant>/` → **只走 task 公共 evaluator** → `results/` → 发布 finding  
4. 物化证据：result summary → finding；lane 在 `frontier/`；不成熟输出只是 validation_signal  
5. Close：ingest → refresh → 更新 canonical → 写 `gen_N/generation_boundary.json`  
6. PI/Chair 合成下一议程 `agendas/research_agenda_gen<N+1>.yaml`  
7. 下一代继承 committed 状态，而非散落文件

**要点**：上游没有「任意 JSON 提案落盘再由外部 harvest 纠偏」的一等公民路径；**验收与继承发生在 findings / frontier / agenda**，不是在你们自定义的提案目录 alone。

### 2.3 合法扩展面（按推荐强度）

1. **Task 合同（最优先）**  
   - `task.yaml`、`roles/`、`prompt_*.jinja2`、`audit_rules/`、`evaluations/`、`budget_profiles/`  
   - 证据成熟度、lane、Gems 政策（见 Task Projects 指南）

2. **Task-local generic plugins**  
   - 路径：`<task_path>/.praxist/plugins/`  
   - `source="task_project"`，仅在该 `--task-path` 下可见  
   - 可声明 `v0_experimental`；适合放「可执行门禁 / 工具 / 轻量 stage 适配」

3. **官方研究机制（表达「生成策略」）**  
   - Quality-Diversity（QD）分配  
   - 可选 Deep Innovation Gate（DIG）  
   - PI/Chair agenda（下一轮探索配额的正规出口）  
   - Central experiment scheduler（资源准入，不选科学假设）

4. **上游 generic plugin PR（仅当能力真正跨任务可复用）**  
   - 走 `praxist/plugins/<kind>/` + conformance tests  
   - 不要把 timesfm 特有规则塞进上游 generic

5. **禁止当默认**  
   - 改 `.venv/.../site-packages/praxist/`  
   - 无版本钉扎的 `sitecustomize` 永久方案  
   - 长期 fork 全量 Praxist（许可 Fair Source + 同步成本）

---

## 3. 现状架构差（为什么「无 hook」是假象）

```text
【你们现在】
peer(框架内) ──写──▶ 提案文件/树
                      │
                      ▼
              scripts/sup_harvest.py  ◀── 短窗 / quality / validator / bandit 反馈
                      │
                      ▼
              慢环 aligned_slow_loop / 队列

【上游期望】
task 合同 + agenda/QD ──▶ peer ──▶ variants/ + results/
                                    │
                                    ▼
                              findings / frontier / Gems
                                    │
                                    ▼
                         generation_boundary + 下一 agenda
```

旁路导致：

- `generation_strategy` / `diversity_metrics` 无法「影响 peer」，因为 peer 根本不读它们；  
- `proposal_validator` 只能在 harvest「事后」拦，写盘已经发生 → 与 Phase1「写盘前登记」同类结构性缺口；  
- 审计只能判 CONDITIONAL_APPROVE：库可用，主路径叙事不能勾完成。

---

## 4. 目标架构（本方案要到达的状态）

```text
慢环 / harvest 产出
  ├─ bandit_feedback.jsonl
  ├─ diversity 快照
  └─ short_window / quality 统计
        │
        ▼
【Generation close / PI·Chair】消费反馈 → 写下一 agenda（+ 可选 QD 合同）
        │
        ▼
peer（只读 agenda / role / 允许面）→ variants/ → task evaluator → results/
        │
        ▼
【task_audit / evaluation 门禁】不合格 → validation_signal only
合格 → findings → frontier/incubator/Gems
        │
        ▼
兼容层（过渡期）：旧提案文件 ──导入──▶ finding（只读一侧真相）
```

成功标准（建议写进 DoD）：

1. 新产生的候选 **默认不依赖**「先写脏提案再 harvest 洗」才能进慢环队列。  
2. 不合格提案在 **证据物化前** 被拒绝或降级，且可审计。  
3. 生成配额变化可在 `agendas/` 或 QD 分配记录中复盘，而不是只在 Python 堆栈里。  
4. `sitecustomize` 若仍存在，仅覆盖遗留路径，并有拆除 issue。  
5. crontab 每日/周指标持续写入 `data/cache/metrics_history/`。

---

## 5. 分项解决方案（细化到可派工）

### 5.1 P0 — 监控 crontab（与框架无关，立即做）

**目的**：关掉障碍报告里唯一「纯执行疏漏」。

**步骤**：

```bash
# 在实际跑 timesfm 的环境（本机 WSL 或盒上约定根）编辑 crontab
crontab -e
```

建议条目（路径按部署根替换；以下沿用障碍报告示例）：

```cron
0 2 * * * cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/monitor_metrics.py collect >> /home/abug/timesfm/logs/monitor_metrics.log 2>&1
0 3 * * 1 cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/generate_weekly_report.py --days 7 >> /home/abug/timesfm/logs/weekly_report.log 2>&1
```

**验收**：

- 次日出现新的 `data/cache/metrics_history/` 记录  
- 日志无持续 Traceback  
- 红线告警路径至少跑通一次 dry-run：`monitor_metrics.py collect` 手工一次

**负责人建议**：行情/运维习惯上由 总管 协调；实际改 crontab 的机器以「跑 Praxist/慢环的那台」为准。

**勿做**：把监控塞进 Praxist peer（边界错误）。

---

### 5.2 P1-A — 提案卫生：迁到 task_audit / evaluation 门禁

**目的**：替代「peer 写盘前注入 validator」的伪需求。

**设计**：

1. 把 `scripts/proposal_validator.py` 的规则整理成 **可声明合同**（JSON Schema 或 task_audit 规则模块）：  
   - JSON/类型/中英泄漏（沿用 Laya「只是判断、不可学习」红线：审计文案不得写「训练 Laya」）  
   - stem / variant_id 口径（对照已通过的 proposals-evaluation-optimization SPEC）  
2. 在证据链上设两道门（至少一道硬门）：  
   - **门 1（推荐硬）**：result → finding 物化前：失败则只保留 validation_signal / partial_output  
   - **门 2（兼容）**：保留 harvest 内 `validate_proposal_dict()`，防止旧旁路漏网  
3. 实现位置优先级：  
   - 首选：`task` 下 `audit_rules/` 或 `evaluations/` + 必要时 `<task>/.praxist/plugins/` 内小 adapter  
   - 次选：包装现有 `validate_all_proposals.py` 为「导入旧提案 → finding」的批处理，不改上游

**派工切片**：

| ID | 内容 | 产出 | 验收 |
|----|------|------|------|
| A1 | 规则清单 ↔ SPEC/审计 P0 对齐 | `docs/.../proposal-gate-rules.md` | 与 validator 测试一一对应 |
| A2 | task_audit 或 task-local plugin 骨架 | `.praxist/plugins/` 或 `audit_rules/` | 单测：合法过 / 非法拒 |
| A3 | 接到物化或导入路径 | 代码 + 1 条集成测 | 脏提案不进 frontier |
| A4 | harvest 保留为旁路闸 | `sup_harvest` 仍调 validator | 双闸文档写明主/备 |

**明确不做**：为了「写盘前」去 patch `site-packages/praxist` 的写文件函数（除非 5.4 临时垫片）。

---

### 5.3 P1-B — 生成策略 / 多样性：走 agenda + QD，不走 peer 内采样劫持

**目的**：让 `GenerationStrategy` / `MultiArmedBandit` / `ElitePreservation` / `diversity_metrics` **有正规消费者**。

**映射表**：

| 现有模块 | 上游落点 | 做法 |
|----------|----------|------|
| 规则采样配额 | 下一轮 `agendas/research_agenda_gen*.yaml` + peer role 约束 | close 后由合成步骤写配额（家族/符号/机制桶） |
| UCB / Thompson | 同一合成步骤的分配策略 | 读 `data/cache/bandit_feedback.jsonl`，输出可审计的桶权重 |
| ElitePreservation | frontier / Gems | 禁止第二套平行精英库；Top-K 应对齐 committed lane |
| symbol/family 熵、覆盖率 | PI 证据包中的 diversity diagnostics | 每代写入 derived_view；覆盖率目标进 agenda |
| DIG | 仅在需要「跳出局部」时开启 | 默认关；与障碍报告「生成策略」解耦 |

**派工切片**：

| ID | 内容 | 产出 | 验收 |
|----|------|------|------|
| B1 | 定义「反馈 → agenda」schema | JSON/YAML schema + 样例 | harvest 写出的 feedback 可被解析 |
| B2 | 离线合成器（可先不接 PI LLM） | `scripts/synthesize_agenda_from_feedback.py` | 给定 feedback 文件 → 稳定 agenda 文件 |
| B3 | 接入 generation close 后钩（task-local 或运维脚本） | 文档化调用点 | 新一代 peer prompt/role 能读到新配额 |
| B4 | diversity 报告进 metrics_history | 与 monitor 打通 | 组合覆盖率趋势可见 |
| B5 | （可选）评估官方 QD 是否覆盖 B2 | 对比备忘 | 能覆盖则删自研重复部分 |

**关键约束**：

- Bandit **不得**宣称「已控制 peer 采样」除非 agenda/role 被 peer 实际读取（写集成测或人工抽检 prompt 渲染）。  
- 多样性「奖励」若无法进入评分合同，就只做 **分配与诊断**，避免再发明平行 reward 通道导致与慢环 gate 双口径。

---

### 5.4 P1-C — 写盘路径对齐（兼容期双写 / 单真相）

**目的**：消灭「框架内写盘无法注入」的结构性理由。

**阶段 C0 — 探查（0.5–1 天）**

在跑机上记录：

1. `python -c "import praxist,pkgutil; print(praxist.__file__, getattr(praxist,'__version__',None))"`  
2. peer 实际创建的提案/variant 路径（strace 或 Praxist trajectory / 现有日志）  
3. 与上游文档路径 `variants/`、`results/`、`findings/` 的差集  
4. 是否已有 `<task>/.praxist/plugins/` 或 `task.yaml`

产出：`docs/superpowers/reports/2026-10-21-praxist-runtime-path-inventory.md`（可另开）。

**阶段 C1 — 兼容导入**

- 旧提案树 → 规范化 → validator →（可选）短窗/quality → 写入 finding 兼容结构或慢环队列  
- **单真相规则**：committed 状态只认 findings/frontier（或你们明文指定的一个 registry）；提案文件降级为输入缓存

**阶段 C2 — 新 peer 默认走官方路径**

- 新实验只开 `--task-path` 标准环  
- cascade 旁路只读历史

**阶段 C3 — 拆除旁路写**

- 停止 peer 直接写「未经验证提案」到生产队列目录

---

### 5.5 P2 — `sitecustomize` 仅作临时垫片

**何时允许**：C0 证明短期内无法改 peer 启动合同，且业务必须立刻挡脏写。

**规则**：

1. 钉死 `praxist==x.y.z`（或内容哈希）  
2. 每个垫片函数有：目标符号、期望签名、失败则 fail-closed 或显式告警  
3. CI/手工：`pytest` + 「升级演练」job（故意升一小版本看是否炸）  
4. Issue 写明：**拆除条件 = A3+B3 合并且 C2 默认路径切换完成**  
5. 禁止在垫片里实现完整 GenerationStrategy（只做最小拦截：validate / register）

现有参考（障碍报告已列）：  
`docs/archive/peer-proposals-pre-0918/run_*/.runtime_guards/*/python_site/sitecustomize.py`

---

### 5.6 明确降级 / 不采纳为默认的路径

| 路径 | 态度 | 原因 |
|------|------|------|
| Fork 全量 Praxist 加 hook | 备选 B，非默认 | Fair Source、同步、人力 |
| 上游 PR 加「timesfm 专用 hook」 | 仅当做成 **通用** plugin 合同 | 上游不会收任务私货 |
| 把 peer 生成整段搬进 timesfm（障碍报告 4.3） | 长期研究项，不挡 P1 | 1–3 月级，与控制面重复 |
| 继续只扩 harvest | 不足 | 无法声称写盘前卫生 / 生成闭环 |

---

## 6. 与 Phase1 / 审计债的衔接

| 债 | 与本方案关系 |
|----|----------------|
| Phase1 Task1「写盘前登记」名实不符 / 返工 ~58% | 本方案 P1-A/C 是结构性修复；用户若仍「先不动」返工，至少不要再扩 harvest 假完成 |
| Phase2-3 changelog「✅完成」夸大 | 本方案 DoD 取代勾选叙事；changelog 应改为「库完成 / 主路径未闭环」 |
| `quality_model.json` 缺失、分数恒 0.5 | 并行 P0：落盘模型 + 红线白名单认 `.json`；否则 harvest 质量分无区分度 |
| Laya 不可学习 | 全文与 PR 描述禁止「训练/进化 Laya」；违规标 P0 |

---

## 7. 建议实施顺序（可直接变 sprint）

```text
Week 0（立即）
  └─ P0 crontab + quality_model.json / changelog 措辞（审计 P0）

Week 1
  ├─ C0 运行时路径与版本清单
  ├─ A1–A2 门禁规则与 task_audit/plugin 骨架
  └─ B1–B2 反馈→agenda 离线合成器

Week 2
  ├─ A3–A4 门禁接入 + harvest 双闸
  ├─ B3–B4 agenda 接入与 diversity 进监控
  └─ 评估是否需要 P2 垫片；需要则最小实现 + 拆除 issue

Week 3
  ├─ C1–C2 兼容导入与新路径默认
  ├─ 短窗效果数据累计（障碍报告 4.1.2）
  └─ 再审：目标从「有条件通过」升到「主路径可宣称部分闭环」
```

并行纪律（团队习惯）：流式启动 bot；本地 PC 写档走 `local-pc.lock`；无用户明示不 commit/push。

---

## 8. 验收清单（建议 New Bot / 自审用）

**监控**

- [ ] crontab 已装且连续 ≥3 天有 metrics_history  
- [ ] 周报至少生成 1 次

**卫生门禁**

- [ ] 非法提案无法进入 frontier / 慢环「已验证」口径（双口径若并存须在文档声明）  
- [ ] harvest 旁路仍挡脏数据  
- [ ] Laya 文案无「可学习」

**生成 / 多样性**

- [ ] 至少 1 次：feedback 变化 → 新 agenda 桶权重变化 → peer 渲染上下文可见  
- [ ] diversity 覆盖率进入监控序列  
- [ ] 无第二套与 frontier 冲突的精英库写生产

**路径**

- [ ] C0 清单落档  
- [ ] 新候选默认路径文档化；旁路标 deprecated  
- [ ] 若存在 sitecustomize：有版本钉与拆除条件

**叙事**

- [ ] changelog / Ultragoal **不得**写「Phase 2-3 验收完成」，直到上列主路径项勾完  
- [ ] 允许写：「能力库已入库；主路径按 2026-10-21 方案推进中」

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 本机 praxist 与上游差太远，task-local plugin 加载不到 | C0 先定量；必要时升级/对齐公开包后再 P1 |
| PI LLM 合成不稳定 | B2 先做确定性合成器；LLM 只做润色 |
| 双路径双真相 | 明文 single source；导入任务幂等 |
| 垫片升级即碎 | 钉版本 + 演练 job + 拆除 deadline |
| 许可（Fair Source） | 内部用注意营收阈值；对外发布输出需保留产品名归属（以官方许可证为准） |
| 与「先不动」用户决策冲突 | 本文只落方案；开工需用户显式授权 |

---

## 10. 参考链接与本地路径

**上游**

- https://github.com/sapientinc/PRAXIST  
- https://praxist.sapient.inc/en/docs  
- arXiv: https://arxiv.org/abs/2608.25955  

**本机 / 仓内（相对 timesfm 根）**

- `docs/superpowers/reports/2026-10-21-phase2-3-integration-barriers-analysis.md`  
- `docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md`  
- `scripts/generation_strategy.py`  
- `scripts/diversity_metrics.py`  
- `scripts/proposal_validator.py`  
- `scripts/sup_harvest.py`  
- `scripts/monitor_metrics.py`  

**本文落档**

- 本机：`/home/abug/timesfm/docs/superpowers/reports/2026-10-21-phase2-3-praxist-integration-solution.md`  
- 盒子镜像：`/workspace/shared/reviews/2026-10-21-phase2-3-praxist-integration-solution.md`

---

## 11. 下一步（需用户拍板）

1. 是否授权执行 **P0 crontab**（可单独做，风险低）  
2. 是否让 **FM研** 按 §7 Week1 开 C0+A1+B1（仍不 commit/push，除非另说）  
3. 是否允许 **临时 P2 垫片**（默认建议：等 C0 结论再定）

---

**文档结束**
