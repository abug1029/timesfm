# Phase 2-3 Praxist 集成实施规范

**日期**: 2026-10-21  
**作者**: FM研（基于总管修改意见）  
**状态**: 草案（待用户授权开工）  
**依据**:
- 障碍报告：`docs/superpowers/reports/2026-10-21-phase2-3-integration-barriers-analysis.md`
- 修改意见：`docs/superpowers/reports/2026-10-21-phase2-3-praxist-integration-solution.md`
- 审计结论：`docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md`（有条件通过 ~56%）

---

## 0. 执行摘要

Phase 2-3 库代码已齐但主路径未闭环。根因不是「上游绝对无 hook」，而是当前跑法（site-packages 内 peer → 提案文件 → `sup_harvest` 旁路）绕开了 Praxist 上游设计的 **task 合同 + findings 证据链**。

本规范目标：把生成策略 / 多样性 / 提案卫生落到 **task 合同与 task-local plugin**，使新产生的候选默认不依赖「先写脏提案再 harvest 洗」才能进慢环队列。

**当前集成度**: ~56%（库完成 / 主路径未闭环）  
**目标集成度**: ≥90%（主路径可宣称部分闭环）  
**预计工期**: 3 周（Week 0-3）

---

## 1. 问题陈述

### 1.1 现状架构差

```text
【当前跑法】
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

### 1.2 四个卡点

| ID | 卡点 | 库侧状态 | 主路径状态 | 根因 |
|----|------|----------|------------|------|
| C1 | 生成策略 → peer 生成 | `scripts/generation_strategy.py` ✅ | ❌ 无调用方 | peer 在框架内，无法从外部注入 |
| C2 | 多样性 → 生成 | `scripts/diversity_metrics.py` ✅ | ❌ 无接入点 | 同上 |
| C3 | 提案卫生 → 写盘前 | `proposal_validator.py` ✅；harvest 已调 ✅ | ❌ peer 写盘前未调 | 同上 |
| C4 | 监控自动化 | `monitor_metrics.py` 等 ✅ | ❌ 未配 crontab | 纯执行疏漏 |

### 1.3 旁路导致的结构性缺口

- `generation_strategy` / `diversity_metrics` 无法「影响 peer」，因为 peer 根本不读它们
- `proposal_validator` 只能在 harvest「事后」拦，写盘已经发生 → 与 Phase1「写盘前登记」同类结构性缺口
- 审计只能判 CONDITIONAL_APPROVE：库可用，主路径叙事不能勾完成

---

## 2. 目标状态

### 2.1 架构目标

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
peer（只读 agenda / role / 允许面）→ variants/
        │
        ▼
【Step 0 提案卫生预检】← 拦格式/中英泄漏/Laya 禁词，不跑模型
  ├─ 不合格 → validation_signal only（短路拒绝，省算力）
  └─ 合格 ↓
        │
        ▼
task evaluator（跑昂贵模型评估）→ results/
        │
        ▼
【task_audit 证据物化门禁】← 拦评估指标不达标的候选
  ├─ 不合格 → 不进入 frontier
  └─ 合格 ↓
        │
        ▼
findings → frontier/incubator/Gems
        │
        ▼
兼容层（过渡期）：旧提案文件 ──导入──▶ finding（只读一侧真相）
```

### 2.2 成功标准（Definition of Done）

1. 新产生的候选 **默认不依赖**「先写脏提案再 harvest 洗」才能进慢环队列
2. 不合格提案在 **证据物化前** 被拒绝或降级，且可审计
3. 生成配额变化可在 `agendas/` 或 QD 分配记录中复盘，而不是只在 Python 堆栈里
4. `sitecustomize` 若仍存在，仅覆盖遗留路径，并有拆除 issue
5. crontab 每日/周指标持续写入 `data/cache/metrics_history/`
6. **状态机边界明确**：`variants/` 与 `results/` 定义为 **非承诺沙盒暂存区（Uncommitted Scratch）**，只有物化进入 `findings / frontier / 慢环队列` 才算正式"入库/写盘"；不合法的候选仅留存 `validation_signal` 供审计追溯，绝不污染正式队列

### 2.3 写盘前的架构定义（审计口径）

**关键澄清**：在 Praxist 标准生命周期（`peer → variants/ → task evaluator → results/ → findings/`）中，当流程走到 `result → finding` 时，`variants/` 和 `results/` 目录下的文件其实已经写盘，且已经消耗算力跑完了 evaluator。

**本规范的"写盘前"定义**：

- **物理写盘**：`variants/` 和 `results/` 属于框架内部的 **非承诺沙盒暂存区（Uncommitted Scratch）**
- **逻辑写盘**：只有物化进入 `findings / frontier / 慢环队列` 才算正式"入库"
- **拦截时机**：将 `proposal_validator` 作为 `task evaluator` 的 **Step 0 前置关卡**（或 `audit_rules` 预检），一旦 JSON/类型/中英泄漏/stem 口径不合法，**立即短路拒绝评估**（Fail-fast in Evaluator），不消耗昂贵算力，输出失败信号

**审计验收口径**：
- 不合格提案在 `evaluator` 启动前被拒绝（省算力 + 收紧拦截点）
- `variants/` 和 `results/` 中的非法文件不进入 `findings / frontier`
- 审计追溯时可通过 `validation_signal` 定位被拒候选

### 2.4 上游 Praxist 边界（不可越界）

| 所有者 | 负责 | 禁止 |
|--------|------|------|
| Praxist core | 协议、解析、存储、replay、凭证、预算、扩展接口 | 任务事实、具体科学假设 |
| Generic plugins | runtime / provider / workflow_stage / tool_server / graph / budget / topology… | 只服务单一任务的事实与 prompt |
| **Task project** | 目标、基线、evaluator、metrics、证据政策、roles、prompts、assets | 改 Praxist 源码、替代 `praxist start` |
| Run directory | 单次 run 的冻结配置与证据 | 当作「当前任务配置」的可变真相 |

**合法扩展面**（按推荐强度）：

1. **Task 合同**（最优先）：`task.yaml`、`roles/`、`prompt_*.jinja2`、`audit_rules/`、`evaluations/`、`budget_profiles/`
2. **Task-local generic plugins**：`<task_path>/.praxist/plugins/`，`source="task_project"`，仅在该 `--task-path` 下可见
3. **官方研究机制**：Quality-Diversity（QD）分配、可选 Deep Innovation Gate（DIG）、PI/Chair agenda
4. **上游 generic plugin PR**：仅当能力真正跨任务可复用
5. **禁止当默认**：改 `.venv/.../site-packages/praxist/`、无版本钉扎的 `sitecustomize` 永久方案、长期 fork 全量 Praxist

---

## 3. 任务分解

### 3.1 P0 — 止血包（立即做，与框架无关）

**目的**：关掉障碍报告里所有「纯执行疏漏」与审计 P0 违规项。

#### P0-1：监控 crontab 部署

**步骤**：

1. 在实际跑 timesfm 环境编辑 crontab
2. 添加以下条目（含 `mkdir -p` 与 `flock` 保护，防目录缺失与僵尸进程）：

```cron
0 2 * * * mkdir -p /home/abug/timesfm/logs && flock -n /tmp/tfm_mon.lock timeout 1800s bash -c 'cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/monitor_metrics.py collect' >> /home/abug/timesfm/logs/monitor_metrics.log 2>&1
0 3 * * 1 mkdir -p /home/abug/timesfm/logs && flock -n /tmp/tfm_weekly.lock timeout 3600s bash -c 'cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/generate_weekly_report.py --days 7' >> /home/abug/timesfm/logs/weekly_report.log 2>&1
```

**验收**：

- [ ] 次日出现新的 `data/cache/metrics_history/` 记录
- [ ] 日志无持续 Traceback
- [ ] 红线告警路径至少跑通一次 dry-run：`monitor_metrics.py collect` 手工一次

#### P0-2：quality_model.json 落盘与红线白名单

**目的**：解决质量分恒为 0.5 导致的 Garbage In Garbage Out 问题，使合成器读到的质量分具备区分度。

**步骤**：

1. 落盘 `quality_model.json`（或等效模型文件）到 `data/cache/` 或配置指定路径
2. 红线白名单放行 `.json` 扩展名（若当前白名单只认 `.pkl` / `.joblib`）
3. 验证 harvest 产出的 quality score 具备非零方差

**验收**：

- [ ] `quality_model.json` 存在于配置指定路径
- [ ] 红线白名单包含 `.json`
- [ ] **实测 harvest 产出的 quality score 具备非零方差，不再恒定为 0.5**（抽取最近 100 条提案，计算标准差 > 0.05）

#### P0-3：Changelog 与 Ultragoal 措辞修正

**目的**：立即消除审计 P0 违规，修正"Phase 2-3 ✅完成"的夸大叙事。

**步骤**：

1. 修正 **被审计的原始执行 Changelog 文档**（如 `2026-10-20-phase2-3-execution-changelog.md` 或主 Changelog）中所有"✅完成"措辞为"库完成 / 主路径未闭环"
2. 修正 Ultragoal 中对应状态表述
3. 明确标注：当前集成度 ~56%，按 2026-10-21 方案推进中

**⚠️ 不可篡改**：`2026-10-20-phase2-3-execution-changelog-audit.md` 是审计报告，属于不可篡改的审计留痕，**禁止修改**。

**验收**：

- [ ] 原始 Changelog 与 Ultragoal 中无"Phase 2-3 验收完成"表述
- [ ] 统一改为"能力库已入库；主路径按 2026-10-21 方案推进中"
- [ ] `-audit.md` 审计报告原文保持不动

**不做**：把监控塞进 Praxist peer（边界错误）。

**预计工期**: 1 天（P0-1/2/3 合计）

---

### 3.2 P1-A — 提案卫生：迁到 task_audit / evaluation 门禁（含 Fail-fast 短路）

**目的**：替代「peer 写盘前注入 validator」的伪需求，并在 evaluator 启动前短路拒绝非法候选（省算力 + 收紧拦截点）。

**设计**：

1. 把 `scripts/proposal_validator.py` 的规则整理成 **可声明合同**（JSON Schema 或 task_audit 规则模块）：
   - JSON/类型/中英泄漏（沿用 Laya「只是判断、不可学习」红线）
   - stem / variant_id 口径（对照已通过的 proposals-evaluation-optimization SPEC）

2. **状态机边界明确**（参见 §2.3）：
   - `variants/` 与 `results/` 定义为 **非承诺沙盒暂存区（Uncommitted Scratch）**
   - 只有物化进入 `findings / frontier / 慢环队列` 才算正式"入库/写盘"
   - 不合法的候选仅留存 `validation_signal` 供审计追溯

3. **Fail-fast in Evaluator（评估前短路）**：
   - 将 `proposal_validator` 作为 `task evaluator` 的 **Step 0 前置关卡**（或 `audit_rules` 预检）
   - 一旦 JSON/类型/中英泄漏/stem 口径不合法，**立即短路拒绝评估**，不消耗昂贵算力
   - 输出 `validation_signal` 失败信号，记录拒绝原因

4. 在证据链上设两道门（至少一道硬门）：
   - **门 1（推荐硬，Fail-fast）**：evaluator Step 0 预检：失败则短路拒绝，不跑评估
   - **门 2（兼容）**：保留 harvest 内 `validate_proposal_dict()`，防止旧旁路漏网

5. 实现位置优先级：
   - 首选：`task` 下 `audit_rules/` 或 `evaluations/` + 必要时 `<task>/.praxist/plugins/` 内小 adapter
   - 次选：包装现有 `validate_all_proposals.py` 为「导入旧提案 → finding」的批处理，不改上游

**派工切片**：

| ID | 内容 | 产出 | 验收 |
|----|------|------|------|
| A1 | 规则清单 ↔ SPEC/审计 P0 对齐 | `docs/.../proposal-gate-rules.md` | 与 validator 测试一一对应 |
| A2 | task_audit 或 task-local plugin 骨架（含 evaluator Step 0 接入） | `.praxist/plugins/` 或 `audit_rules/` | 单测：合法过 / 非法拒（含 Fail-fast 短路验证） |
| A3 | 接到物化或导入路径 | 代码 + 1 条集成测 | 脏提案不进 frontier |
| A4 | harvest 保留为旁路闸 | `sup_harvest` 仍调 validator | 双闸文档写明主/备 |

**Laya 红线固化**：

- 将 Laya 禁用词（"训练 Laya"、"进化 Laya"、"可学习"）直接写进 `proposal_validator.py`
- 在仓库静态检查测试（`tests/test_laya_prohibited_words.py`）中用单测固化红线
- CI 每次提交自动扫描，违规即 fail

**明确不做**：为了「写盘前」去 patch `site-packages/praxist` 的写文件函数（除非 3.5 临时垫片）。

**预计工期**: 3-4 天

---

### 3.3 P1-B — 生成策略 / 多样性：走 agenda + QD，不走 peer 内采样劫持（Batch Bandit 模式）

**目的**：让 `GenerationStrategy` / `MultiArmedBandit` / `ElitePreservation` / `diversity_metrics` **有正规消费者**。

**映射表**：

| 现有模块 | 上游落点 | 做法 |
|----------|----------|------|
| 规则采样配额 | 下一轮 `agendas/research_agenda_gen*.yaml` + peer role 约束 | close 后由合成步骤写配额（家族/符号/机制桶） |
| UCB / Thompson | 同一合成步骤的分配策略 | 读 `data/cache/bandit_feedback.jsonl`，输出可审计的桶权重 |
| ElitePreservation | frontier / Gems | 禁止第二套平行精英库；Top-K 应对齐 committed lane |
| symbol/family 熵、覆盖率 | PI 证据包中的 diversity diagnostics | 每代写入 derived_view；覆盖率目标进 agenda |
| DIG | 仅在需要「跳出局部」时开启 | 默认关；与障碍报告「生成策略」解耦 |

**Bandit 模式显式声明**：

- 本规范采用 **Generation-level Batch Bandit** 模式（按代批式更新），而非逐提案在线更新（Online Bandit）
- 审计时不得按逐次采样的在线 Bandit 语义挑刺
- 每代 close 后，合成器读取 `bandit_feedback.jsonl`，输出下一代桶权重

**配额执行强化（防 Prompt 软约束失真）**：

- **问题**：LLM Peer 可能忽略 Prompt 里的比例要求，继续扎堆生成热门家族
- **对策 1（推荐）**：利用 Praxist 的多 Role / 多 Worker 机制，将不同家族/符号桶拆分为独立的 **Role 实例或受限允许面（Allowed Surface）**，用"给不同 Peer 分配不同只读工具/符号子集"的 **硬隔离** 保障配额落地
- **对策 2（辅助）**：在 B4 监控中增加 **Agenda 目标配额 vs 实际产出分布的 KL 散度/偏差告警**，阈值超标即触发人工复盘

**派工切片**：

| ID | 内容 | 产出 | 验收 |
|----|------|------|------|
| B1 | 定义「反馈 → agenda」schema | JSON/YAML schema + 样例 | harvest 写出的 feedback 可被解析 |
| B2 | 离线合成器（可先不接 PI LLM） | `scripts/synthesize_agenda_from_feedback.py` | 给定 feedback 文件 → 稳定 agenda 文件；Bandit 采用 Batch 模式 |
| B3 | 接入 generation close 后钩（task-local 或运维脚本） | 文档化调用点 | 新一代 peer prompt/role 能读到新配额 |
| B4 | diversity 报告进 metrics_history + KL/JS 散度告警 | 与 monitor 打通 | 组合覆盖率趋势可见；**Agenda 目标配额 vs 实际产出散度超阈值即告警**（见下方计算约束） |
| B5 | （可选）评估官方 QD 是否覆盖 B2 | 对比备忘 | 能覆盖则删自研重复部分 |
| B6 | （可选）多 Role 硬隔离配额 | Role 实例配置 + Allowed Surface 定义 | 不同 Peer 只能生成指定家族/符号桶 |

**关键约束**：

- Bandit **不得**宣称「已控制 peer 采样」除非 agenda/role 被 peer 实际读取（写集成测或人工抽检 prompt 渲染）
- 多样性「奖励」若无法进入评分合同，就只做 **分配与诊断**，避免再发明平行 reward 通道导致与慢环 gate 双口径

**B4 散度告警计算约束**：

1. **零概率平滑**：计算前必须执行 **拉普拉斯平滑（Laplace Smoothing，ϵ=10⁻³）**，或直接改用 **对称有界的 JS 散度（Jensen-Shannon Divergence，取值范围 [0,1]）**，避免分母为 0 导致除零异常
2. **最小样本量门槛**：设置 **N≥30**（单代或滑动窗口内有效提案数），低于该样本量仅记录数值、**不触发告警**，防止小样本离散采样波动导致误报
3. **告警阈值**：建议初始设为 0.3（KL 散度）或 0.1（JS 散度），根据实际数据分布调整

**预计工期**: 4-5 天

---

### 3.4 P1-C — 写盘路径对齐（兼容期双写 / 单真相 / 幂等键）

**目的**：消灭「框架内写盘无法注入」的结构性理由。

**阶段 C0 — 探查（0.5–1 天）** ⚠️ **前置阻塞门（Blocking Gate）**

在跑机上记录：

1. `python -c "import praxist,pkgutil; print(praxist.__file__, getattr(praxist,'__version__',None))"`
2. peer 实际创建的提案/variant 路径（strace 或 Praxist trajectory / 现有日志）
3. 与上游文档路径 `variants/`、`results/`、`findings/` 的差集
4. 是否已有 `<task>/.praxist/plugins/` 或 `task.yaml`

**C0 冒烟验证（必须通过，方可进入 Week 1 A2/B2）**：

1. **Plugin 加载能力验证**：创建一个空壳 `<task>/.praxist/plugins/test_plugin/`，验证当前 `.venv` 中的 Praxist 能否成功加载
2. **Agenda Schema 验证**：提取当前版本 Peer 实际渲染 Prompt 时读取的 Agenda/Role 上下文结构，确认与上游最新文档一致

产出：`docs/superpowers/reports/2026-10-21-praxist-runtime-path-inventory.md`（含冒烟验证结果）

**阶段 C1 — 兼容导入（含幂等键与并发互斥）**

- 旧提案树 → 规范化 → validator →（可选）短窗/quality → 写入 finding 兼容结构或慢环队列
- **单真相规则**：committed 状态只认 findings/frontier（或明文指定的一个 registry）；提案文件降级为输入缓存
- **幂等键（Idempotency Key）**：以规范化后的 `variant_id`（或 AST/内容哈希）作为全局幂等键，防止 C1 导入批处理与新路径 Peer 原生产出重复消费同一候选
- **并发互斥**：导入批处理脚本必须遵守 `local-pc.lock` 纪律，防止与 Peer 运行时并发写冲突

**阶段 C2 — 新 peer 默认走官方路径**

- 新实验只开 `--task-path` 标准环
- cascade 旁路只读历史

**阶段 C3 — 拆除旁路写**

- 停止 peer 直接写「未经验证提案」到生产队列目录

**预计工期**: 3-4 天（C0-C3 合计）

---

### 3.5 P2 — `sitecustomize` 仅作临时垫片

**何时允许**：C0 证明短期内无法改 peer 启动合同，且业务必须立刻挡脏写。

**规则**：

1. 钉死 `praxist==x.y.z`（或内容哈希）
2. 每个垫片函数有：目标符号、期望签名、失败则 fail-closed 或显式告警
3. CI/手工：`pytest` + 「升级演练」job（故意升一小版本看是否炸）
4. Issue 写明：**拆除条件 = A3+B3 合并且 C2 默认路径切换完成**
5. 禁止在垫片里实现完整 GenerationStrategy（只做最小拦截：validate / register）

现有参考（障碍报告已列）：
`docs/archive/peer-proposals-pre-0918/run_*/.runtime_guards/*/python_site/sitecustomize.py`

**预计工期**: 1-2 天（若需要）

---

### 3.6 明确降级 / 不采纳为默认的路径

| 路径 | 态度 | 原因 |
|------|------|------|
| Fork 全量 Praxist 加 hook | 备选 B，非默认 | Fair Source、同步、人力 |
| 上游 PR 加「timesfm 专用 hook」 | 仅当做成 **通用** plugin 合同 | 上游不会收任务私货 |
| 把 peer 生成整段搬进 timesfm（障碍报告 4.3） | 长期研究项，不挡 P1 | 1–3 月级，与控制面重复 |
| 继续只扩 harvest | 不足 | 无法声称写盘前卫生 / 生成闭环 |

---

## 4. 验收清单

### 4.1 监控（P0-1）

- [ ] crontab 已装且连续 ≥3 天有 metrics_history
- [ ] 周报至少生成 1 次
- [ ] crontab 条目含 `mkdir -p` 与 `flock` 保护

### 4.2 质量分区分度（P0-2）

- [ ] `quality_model.json` 存在于配置指定路径
- [ ] 红线白名单包含 `.json`
- [ ] **实测 harvest 产出的 quality score 具备非零方差，不再恒定为 0.5**（抽取最近 100 条提案，计算标准差 > 0.05）

### 4.3 叙事修正（P0-3）

- [ ] Changelog 与 Ultragoal 中无"Phase 2-3 验收完成"表述
- [ ] 统一改为"能力库已入库；主路径按 2026-10-21 方案推进中"

### 4.4 卫生门禁（P1-A）

- [ ] 非法提案无法进入 frontier / 慢环「已验证」口径（双口径若并存须在文档声明）
- [ ] harvest 旁路仍挡脏数据
- [ ] **evaluator Step 0 Fail-fast 短路生效**：非法候选在 evaluator 启动前被拒绝，不消耗算力
- [ ] `variants/` 和 `results/` 中的非法文件不进入 `findings / frontier`
- [ ] Laya 禁用词（"训练 Laya"、"进化 Laya"、"可学习"）写进 `proposal_validator.py`
- [ ] **仓库静态检查测试 `tests/test_laya_prohibited_words.py` 存在且通过**，CI 自动扫描

### 4.5 生成 / 多样性（P1-B）

- [ ] 至少 1 次：feedback 变化 → 新 agenda 桶权重变化 → peer 渲染上下文可见
- [ ] diversity 覆盖率进入监控序列
- [ ] 无第二套与 frontier 冲突的精英库写生产
- [ ] **Bandit 采用 Generation-level Batch 模式**，审计时按批式更新语义验收
- [ ] **Agenda 目标配额 vs 实际产出分布的 KL 散度告警已接入监控**，阈值超标即触发人工复盘
- [ ] （可选 B6）多 Role 硬隔离配额已实施，不同 Peer 只能生成指定家族/符号桶

### 4.6 路径（P1-C）

- [ ] C0 清单落档（含 Plugin 加载能力验证 + Agenda Schema 验证）
- [ ] **C0 冒烟验证通过**：空壳 plugin 可加载、Agenda Schema 与上游一致
- [ ] 新候选默认路径文档化；旁路标 deprecated
- [ ] 若存在 sitecustomize：有版本钉与拆除条件
- [ ] **C1 导入批处理采用幂等键（variant_id 或内容哈希）**，防止重复消费
- [ ] C1 导入批处理遵守 `local-pc.lock` 并发互斥纪律

### 4.7 叙事（总体验收）

- [ ] changelog / Ultragoal **不得**写「Phase 2-3 验收完成」，直到上列主路径项勾完
- [ ] 允许写：「能力库已入库；主路径按 2026-10-21 方案推进中」

---

## 5. 实施顺序

```text
Week 0（立即）
  ├─ P0-1 crontab（含 mkdir -p + flock 保护）
  ├─ P0-2 quality_model.json 落盘 + 红线白名单
  ├─ P0-3 Changelog / Ultragoal 措辞修正
  └─ C0 运行时路径与版本清单（含 Plugin 加载能力 + Agenda Schema 冒烟验证）
      ⚠️ C0 为 Week 1 A2/B2 的前置阻塞门（Blocking Gate）

Week 1（C0 冒烟验证通过后方可启动 A2/B2）
  ├─ A1 门禁规则对齐（纯文档，可先启动）
  ├─ B1 反馈→agenda schema 定义（纯文档，可先启动）
  │   └─ 先冻结输入侧 feedback Schema；输出侧 agenda Schema 待 C0 冒烟验证确认后定稿
  ├─ A2 task_audit / plugin 骨架（含 evaluator Step 0 Fail-fast）← 依赖 C0
  └─ B2 离线合成器（Batch Bandit 模式）← 依赖 C0

Week 2
  ├─ A3–A4 门禁接入 + harvest 双闸 + Laya 禁用词静态检查
  ├─ B3–B4 agenda 接入 + diversity 进监控 + KL 散度告警
  ├─ （可选 B6）多 Role 硬隔离配额
  └─ 评估是否需要 P2 垫片；需要则最小实现 + 拆除 issue

Week 3
  ├─ C1–C2 兼容导入（含幂等键 + 并发互斥）与新路径默认
  ├─ 短窗效果数据累计（障碍报告 4.1.2）
  └─ 再审：目标从「有条件通过」升到「主路径可宣称部分闭环」
```

**并行纪律**：

- 流式启动 bot
- 本地 PC 写档走 `local-pc.lock`
- 无用户明示不 commit/push
- **C0 冒烟验证未通过前，禁止启动 A2/B2 代码编写**（可先启动纯文档性质的 A1/B1）

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 本机 praxist 与上游差太远，task-local plugin 加载不到 | C0 先定量；必要时升级/对齐公开包后再 P1 |
| PI LLM 合成不稳定 | B2 先做确定性合成器；LLM 只做润色 |
| 双路径双真相 | 明文 single source；导入任务幂等 |
| 垫片升级即碎 | 钉版本 + 演练 job + 拆除 deadline |
| 许可（Fair Source） | 内部用注意营收阈值；对外发布输出需保留产品名归属（以官方许可证为准） |
| 与「先不动」用户决策冲突 | 本规范只落方案；开工需用户显式授权 |

---

## 7. 与 Phase1 / 审计债的衔接

| 债 | 与本规范关系 |
|----|----------------|
| Phase1 Task1「写盘前登记」名实不符 / 返工 ~58% | 本规范 P1-A/C 是结构性修复；用户若仍「先不动」返工，至少不要再扩 harvest 假完成 |
| Phase2-3 changelog「✅完成」夸大 | 本规范 DoD 取代勾选叙事；changelog 应改为「库完成 / 主路径未闭环」 |
| `quality_model.json` 缺失、分数恒 0.5 | 并行 P0：落盘模型 + 红线白名单认 `.json`；否则 harvest 质量分无区分度 |
| Laya 不可学习 | 全文与 PR 描述禁止「训练/进化 Laya」；违规标 P0 |

---

## 8. 参考链接与本地路径

**上游**

- https://github.com/sapientinc/PRAXIST
- https://praxist.sapient.inc/en/docs
- arXiv: https://arxiv.org/abs/2608.25955（2608 为 2026 年 8 月，当前日期 2026-10-21 的两个月前，年月无误；执行 §9.4 时只需核验 `.25955` 序号及链接可达性）

**本机 / 仓内（相对 timesfm 根）**

- `docs/superpowers/reports/2026-10-21-phase2-3-integration-barriers-analysis.md`
- `docs/superpowers/reports/2026-10-21-phase2-3-praxist-integration-solution.md`
- `docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md`
- `scripts/generation_strategy.py`
- `scripts/diversity_metrics.py`
- `scripts/proposal_validator.py`
- `scripts/sup_harvest.py`
- `scripts/monitor_metrics.py`

---

## 9. 下一步（需用户拍板）

### 9.1 授权立即执行 P0（含补充项）

批准执行 `§3.1` 的完整 P0 止血包：

- **P0-1**：Crontab 部署（含 `mkdir -p` 与 `flock` 保护）
- **P0-2**：`quality_model.json` 落盘 + 红线白名单放行 `.json`
- **P0-3**：Changelog 与 Ultragoal 措辞修正

**要求**：今日内闭环所有审计 P0 项。

### 9.2 分阶段授权 Week 1 任务（先 C0，后 A1/B1，再 A2/B2）

**第一阶段（立即启动）**：

- **C0**：运行时路径与版本探查（含 Plugin 加载能力 + Agenda Schema 冒烟验证）
- **A1**：门禁规则对齐（纯文档性质）
- **B1**：反馈→agenda schema 定义（纯文档性质）

**第二阶段（C0 冒烟验证通过后启动）**：

- **A2**：task_audit / plugin 骨架（含 evaluator Step 0 Fail-fast）
- **B2**：离线合成器（Batch Bandit 模式）

**纪律**：保持只写本地、不 commit/push，除非另说。

### 9.3 暂缓 P2（`sitecustomize` 垫片）

维持默认建议：在 C0 结论出来之前 **不写** `sitecustomize` 垫片。

**启用条件**：仅当 C0 证实本机 Praxist 版本无法通过 Task 合同或 Evaluator Step 0 拦截脏提案、且短期无法升级时，再按 `§3.5` 启用最小垫片。

### 9.4 核验 arXiv 论文链接可达性

指派 FM研 核验 `§8` 中 arXiv 链接 `https://arxiv.org/abs/2608.25955` 在公网或内部知识库中是否真实可达（2608 为 2026 年 8 月，年月无误，只需核验 `.25955` 序号及链接可达性）。

---

**文档结束**
