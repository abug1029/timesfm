# FM_a 技术债收口方案与实施计划

> **日期**: 2026-10-07
> **输入**: `docs/superpowers/reports/2026-10-07-tech-debt-inventory.md`（23 条：P0=4 / P1=5 / P2=5 / P3=9）
> **核实**: 全部 23 条已对照当前代码（master@5e7237a）与 live 数据逐一核实。**其中 6 条清单说法已过时**（§0.1 勘误表），另核实出 4 项清单未列的新事实（§0.2 N1-N4）。
> **执行约定**: worktree `feat/tech-debt-closure-2026-10-07` + TDD 先红后绿 + 全量回归失败集恒等零新增 + 每批次独立专家审核 + 中文提交。
> **状态**: 待宿主审定（§7 裁定点 Q1-Q6）。

---

## 0. 盘点核实与勘误

### 0.1 勘误表（清单说法 vs 2026-10-07 上午核实）

| 条目 | 清单说法 | 核实结果 | 证据 |
|---|---|---|---|
| L1 `_dead_families` 误判 | set_mismatch_descriptive 计入死亡阈值，term_structure 5 条全判死 | **已修复**：`_family_confirmatory_counts`（praxist_supervisor.py:1736-1751）只数 `_CONFIRMATORY_DM = {ok, set_mismatch_ok}`（:1714）；live registry 393 行实跑 `_dead_families` 返回**空集**，term_structure（68 行：None×24 / set_mismatch_descriptive×43 / insufficient_common×1）未判死 | live 验证脚本（本计划附件说明） |
| L5 data_stale 无验收测试 | dfd1f43 设计正确但未写测试 | **已有** `tests/test_success_gate_stale_20261006.py` 共 9 用例：国庆空窗 fail-open、3 天边界仍拒、4 天开闸、同锚新 bar 仍拒、per-symbol、warning-once、时区回退——覆盖完整 | tests/ 目录 |
| M2 Locked this window 未触发 | 函数存在但未写入 peer prompt | **已接线**：prompt builder :1350 `lines.extend(_locked_window_lines(...))`，与 Dead families / Cross matrix / Old-protocol priors / Do-not-re-propose 同段物化 | 代码 :1350 / :2463 |
| D3 user_paused 死标志 | clear_supervisor_pause.py 与 restart 脚本空转 | **已归档**：clear_supervisor_pause.py 已入 `scripts/archive/2026-09-30-dead-code/`；全仓零活代码引用（仅残留 .pyc） | grep -rln 全仓 |
| D8 lgbm 死代码 | 复活代价高 | **已归档**：`cascade/lgbm_features.py` 不存在（09-30 死代码清扫 49 文件之一） | ls |
| D9 prereg writer 未挂账 | 出处不明 | **已挂账**：脚本 docstring 写明一次性用途/拒绝重写语义，出处 commit 34fedcb（v4 预注册写入器） | head 脚本 |
| D7 specs 积压 13 个 | 13 个 | 实为 **9 个**（specs/ 目录实数） | ls |
| M5 n_eff 恒 73 | 所有裁决都显示 73，是常数函数 | **主导但非全量**：73×664 行，另有 1×52、0×52、71×18；且存在真实估计量 `measured_n_eff`（statistical_tests.py:205/:405，与 DM 共用实现）——恒定值需溯源查根因，不能直接判死刑 | registry `uniq -c` |
| A2 三代备份在 /home/abug/ | 同盘风险 | **更糟**：三代 .bak 与 live 文件**同目录**（`task_FM/config/`），同在 `git clean -xdf` 爆炸半径内 | ls task_FM/config/ |

### 0.2 新发现（清单未列）

- **N1（重要）**: L1 修复后的新语义空转——live registry 393 行中 `fam_ok = {}`（**零行**同时满足 status=ok + dm_status∈{ok,set_mismatch_ok} + cov_family 非空）→ `_dead_families` 恒返回空集 → "## Dead families" prompt 段永久为空、family_dead 门永不触发。**与正期望搜索 P2.6 专家审核发现的「生产 dm_status 口径活性风险」同根因**（生产裁决 dm_status 绝大多数为 set_mismatch_descriptive/缺省）。应并入同一宿主裁定统一处理（Q6），不宜单独修。
- **N2**: `aligned_max_points` 代码默认 400（praxist_supervisor.py:3399）vs goal.yaml 600——与 L4 survivors_per_cycle 同类漂移，应同修。
- **N3**: 数据资产远不止裁决文件。gitignored 的还有：`.omc/supervisor_decisions.jsonl`（285KB，18 门拒收历史，今晨仍在追加）、`data/cache/`（supervisor_state.json、aligned_pending* 队列、aligned_checkpoints/）、baseline_points_*.jsonl 约 30 份。备份范围必须覆盖整组。
- **N4**: 今晨另一会话已建立 git 层备份（`BACKUP_SYNC_GUIDE.md` + 根目录未提交的 `sync_backup.sh`，master → backup 机 git 仓）。方向正确，但 **git push/bundle 天然不覆盖 gitignored 数据资产**——P0 缺口仍在，且两者互补不应重复建设。

---

## 1. 批次总览

```
批次 0（批准当天 ~1h）  P0 应急数据备份 ─── 纯 rsync，零代码，零冲突，立即可做
批次 1（1-2 天）        P0 工程化（cron / safe_clean / 资产分级） ── 脚本层，与 pevs 无冲突
────── 以下批次改 praxist_supervisor.py，与在途正期望分支（P2.7-P3 未合入）同文件，须串行 ──────
批次 2（1 天）          P1 差距收口：L2 配对键 / L3 单源化 / L4 默认值对齐（含 N2）/ L1+L5 勘误收口
批次 3（3-4 天）        P2 peer 学习：M1 跨 run 统计 / M3 拒收回写 / M4 abandon / M5 n_eff 溯源（含 D1 锚点）
批次 4（见缝插针）      P3：D2 star→tier / D4 看门狗 / D5 孤儿 run / D6 消歧 / D7 spec 结案
收口（0.5 天）          清单勘误回写 reports/ + changelog
```

**串行红线**：批次 2/3 与 D5 都改 supervisor；正期望分支 P2.7-P3 合入部署（自带重启窗口）完成后，tech-debt 基于新 master 开工。批次 0/1 与在途工作零冲突，批准后当天启动。

---

## 2. 批次 0+1：P0 数据资产保护（A1-A4，合计 1-2 天）

### 2.1 资产分级（核实后精确化）

| 级别 | 内容 | git 状态 | 现有保护 |
|---|---|---|---|
| S1 不可重生 | `task_FM/config/aligned_verdicts.jsonl`（984KB，393 行 walk-forward 裁决史）+ 3 份 .bak（**同目录**） | ignore（.gitignore:76） | 无 |
| S1 不可重生 | `.omc/supervisor_decisions.jsonl`（285KB，18 门拒收历史） | ignore（.gitignore:26） | 无 |
| S2 重生昂贵 | `baseline_points_*.jsonl` 约 30 份 + `baseline_metrics.json`（v4 指纹 f02b2a43 绑定，重生耗机时） | ignore（.gitignore:101） | 无 |
| S3 状态类 | `data/cache/`：supervisor_state.json、aligned_pending*.jsonl、aligned_checkpoints/、supervisor_events.jsonl | ignore（.gitignore:50） | 无 |
| 已被 git 覆盖 | preregistry.jsonl、family_registry.jsonl(+bak)、covariate_pool.json、covariate_backlog.jsonl、symbol_status.json、covariate_family_verdict.json | 已跟踪 | sync_backup.sh（今晨在建） |

**结论**：A1-A4 的实际缺口 = 上表前四行（全部 gitignored）。git 层备份（sync_backup.sh / bundle）覆盖不到它们；`git clean -xdf` 能一锅端它们；三代备份与 live 同目录连备份都一起端。

### 2.2 方案（三层防护）

1. **异机每日快照**（批次 0 当天先手动跑一次，批次 1 脚本化）：
   - `scripts/backup_data_assets.sh`：rsync S1+S2+S3 → backup 机 `chong@100.96.19.116` → WSL `/root/timesfm-data/`（复用 BACKUP_SYNC_GUIDE.md 的 ssh 通道与密钥）
   - 双份布局：`latest/`（覆盖）+ `daily/`（日期快照，保留 90 天）+ `md5sums.txt` 核对清单
   - md5 不一致 / rsync 失败 → 退出码非零 + 写日志（供 D4 看门狗类机制后续消费）
   - crontab：每日 02:15（避开既有 17:45 数据拉取与周六 02:35 任务）
2. **防误删**（批次 1）：
   - `scripts/safe_clean.sh`：`git clean -xdf -e task_FM/config/ -e .omc/ -e data/cache/` 白名单包装，dry-run 先行
   - AGENTS.md + runbook 加禁令注记：清理一律走 safe_clean，禁止裸 `git clean -xdf`
   - **根治**（迁移 live 数据出 repo tree，使 git clean 永远够不着）：路径常量改为可配置（env 覆盖），迁移 + 改配置 + 重启原子完成——**搭正期望 P3 部署的重启窗口顺风车**，不单独重启
3. **第二异地（可选，Q2）**：rclone → S3 兼容对象存储。S1+S2 总量 <10MB，成本可忽略；backup 机已消单盘单机风险，此项降级为可选加固。

### 2.3 与在途工作的关系

sync_backup.sh（另一会话未提交）管 git 层，本方案管数据层，职责分离互补。建议该会话采纳本计划后，把 `sync_backup.sh push` 与 `backup_data_assets.sh` 挂进同一 cron 条目，一次跑齐。

### 2.4 验收

- [ ] backup 机存在当日快照，md5 与本地一致
- [ ] 连续 3 天 cron 零失败（日志佐证）
- [ ] `safe_clean.sh` dry-run 不命中任何 S1/S3 资产；裸 clean 禁令写入 AGENTS.md
- [ ] （迁移后）`git clean -xdfn` 对数据零威胁；supervisor 重启后首轮裁决追加正常、指纹 f02b2a43 不变、baseline 零重生

---

## 3. 批次 2：P1 差距收口（1 天，pevs 合入后）

### L2 `_has_prior_failure` 单键 OR → 配对键（0.5 天，本批次唯一的真开门修复）

- **现状**（:1426-1442）：10-03 已收窄到可确认失败（`_is_confirmable_failure`），但仍是 symbol **OR** cov 单键命中即拦——同 symbol 异 cov、异 symbol 同 cov 都被误拦，污染半径大于文档描述。
- **方案**：改 (symbol, cov_override) **配对 AND** 匹配；docstring 同步；测试三例：同对拦截 / 同 symbol 异 cov 放行 / 异 symbol 同 cov 放行。
- **影响**：拦截面收窄 → 探索提案增加；dedup 门与 Do-not-re-propose 段兜底。
- **注意**：属准入语义，verdict 行 schema 不变，协议指纹不动。

### L3 GOAL_SYMBOLS_SET 单源化（0.5 天）

- **现状**：:1673 硬编码 9 品种 vs goal.yaml `target_symbols` 24（10-02 goal 重写后遗留）；:1303 prompt "## Symbol status" 只报 9 个；:1028 变量名 `n_one_star_symbols_hit` 还是 star 时代（随 D2 改名）。
- **方案**：启动时从 goal.yaml 读 target_symbols 构建 GOAL_SYMBOLS_SET，删除硬编码；新增测试断言 goal.yaml 增删品种 → 集合跟随。
- **影响**：goal 完成度统计范围 9→24，属 goal 语义**对齐**（yaml 是契约），非 gate 语义；随重启生效。
- **前置**：Q3 宿主确认（排除 9 个有 phase1 子集独立语义的可能——从 goal.yaml 注释「所有品种都需达标」看应当合并）。

### L4 cadence 默认值对齐（0.25 天，含 N2）

- **现状**：:3398 `survivors_per_cycle` 默认 2 vs yaml 3；:3399 `aligned_max_points` 默认 400 vs yaml 600。
- **方案**：两处默认改与 yaml 一致；缺键回退时打 WARN 日志；**新增一致性回归测试**（加载 goal.yaml，断言代码全部 cadence 默认值 = yaml 值，防再漂移）；runtime_contract.md 记录。

### L1 / L5 收口（0.25 天）

- L1：修复与测试已在（test_supervisor.py / test_harvest_proposals.py 引用 `_dead_families`）；收口动作 = §0.1 勘误回写 + N1 空转观察并入 Q6 裁定，**不在本批次改代码**。
- L5：test_success_gate_stale_20261006.py 已 9 用例含边界与恢复；收口动作 = 勘误回写，无代码。

### 批次 2 验收

- 全量回归失败集恒等零新增（以开工分支基线为准）
- L2/L3/L4 各带新测试；L4 一致性测试入常备套件
- 生效需一次 supervisor 重启——**与批次 3 合入后一次重启**，不单独重启

---

## 4. 批次 3：P2 peer 学习差距（3-4 天，pevs 合入后）

M2 已接线无需实施；D1 锚点随本批次 prompt 组装重写顺带完成。

### M1 跨 run 统计通道（1.5 天，设计取舍见 Q4）

- **现状**：shared_store.db / research_memory.jsonl / cross_run_learning.jsonl 均不存在（仅 cleanup 脚本挂名）；历史 gate_pass 统计 peer 看不到，每次 run 近乎从零开始。
- **方案（推荐：聚合既有源，不引入第三份状态存储）**：从 aligned_verdicts.jsonl + .omc/supervisor_decisions.jsonl 聚合 (symbol, cov, family, 门, 结果, 时间) 滚动统计 → 物化 `known_verdicts_stats.inc.md` 注入 prompt。
- **备选**：按 peer-memory-loop-closure spec D1 建 sqlite——引入新状态与锁语义，需另行评估（Q4）。

### M3 拒收理由回写（1 天）

- **现状**：prompt 已含 Symbol status / Effective clues / Dead families / Cross matrix / Old-protocol priors / Locked this window / Do-not-re-propose，**唯独没有拒收原因段**；no_failure_delta 等纯规则门的拒收 peer 全看不到。
- **方案**：从 supervisor_decisions.jsonl 聚合近 7 天拒收分布（门 × 组合频次 top-N + 一句话原因）→ prompt 新段 "## Why proposals were rejected recently"。
- **注意**：清单引用的 57%/18%/16% 分布是修复前统计（family_dead 在现行代码下因 N1 恒空已归零）——实施时以 decisions 日志**现算**为准，不搬旧数字。

### M4 `decision: abandon`（1 天）

- **现状**：supervisor 全文零 abandon 引用（spec D4 未实施），falsifier 被迫用正例提案表达反对。
- **方案**：peer 输出 schema 增 `decision: "abandon"` 字段 → supervisor 记 decisions 行 + 跳过 run 派发 + 回写教学注记；存量正例提案路径不变。

### M5 n_eff 恒值溯源（0.5 天调查 + 0.5 天处置）

- **现状**：73×664 行主导 + 1×52 + 0×52 + 71×18；存在真实估计量（statistical_tests.py:205/:405 与 DM 共用）——恒 73 疑为共用基准 d 序列或缓存所致，需溯源 build_summary 的 n_eff 来源。
- **高危注意**：n_eff 喂 `tier_classifier._score_n_eff`（:76/:127）→ 改语义 = 改 tier = **触碰 gate 评估语义 → 协议指纹纪律适用**（须按 v4 指纹流程评估重生影响，不可裸改）。
- **处置二选一（溯源后 Q1 裁定）**：(a) 若 tier 评分依赖且现值失真 → per-variant 真实计算 + 指纹流程；(b) 若仅显示误导 → 移除显示字段（tier 若依赖则不可行）。

### D1 行号 → 章节锚点（0.5 天，随批次顺带）

- prompt 内嵌的规格**行号**引用全部改为**章节锚点**，一劳永逸免疫代码合入导致的行号漂移；M1/M3 重写 prompt 组装时一并处理，单独做成本最低。

### 批次 3 验收

- peer prompt 含三块新上下文：跨 run 统计 + 拒收摘要 + （既有）locked window
- falsifier abandon 通道端到端可用（提案 → 记录 → 不派 run）
- 观察指标（sprint 后一周）：dedup 拒收占比显著下降；重复探索提案减少
- 全量回归恒等 + 专家审核 + 一次 supervisor 重启生效（与批次 2 合并重启）

---

## 5. 批次 4：P3 慢性腐烂（见缝插针；D3/D8/D9 已结，仅剩收口）

| # | 方案 | 工作量 |
|---|---|---|
| D2 | star→tier 清扫：文档多处改口径 + :1028 `n_one_star_symbols_hit` 改名 + tier_classifier.py 注「评级唯一承载字段」 | 0.5 天 |
| D4 | 看门狗：Windows Task Scheduler 每 15 分钟 `wsl -d Ubuntu-22.04 -- pgrep -f praxist_supervisor \|\| 重启脚本`；带维护窗口旗标守卫（`data/cache/` 已有 supervisor.pid / supervisor_heartbeat 可复用）；日志入 data/cache/ | 0.5 天 |
| D5 | 孤儿 run 治理：:3665 spawn 前把子进程 PID + 提案上下文写 `data/cache/active_runs.json`；supervisor 退出钩子 kill + 重启脚本按文件扫尾（现状：start_new_session=True 派发，父死子孤烧 token） | 1 天 |
| D6 | `docs/superpowers/specs/praxist_control_plane.md` 与 runtime_contract.md 同名不同物 → specs 版改名 + 双向交叉引用 | 0.25 天 |
| D7 | 9 份 spec 加状态头（结案/在途/废弃 + 日期）：jev-prescreen、typesafe-prescreen、credibility、prediction-quality-v23 可结案；phase3-todo、peer-memory-closure、positive-ev-factor-search 在途；control_plane 随 D6 | 0.5 天 |
| D3/D8/D9 | 已完成（归档/挂账）；剩 stale .pyc 清理 + changelog 一行 + 勘误回写 | 0.1 天 |

D4/D5 优先级最高（运维风险：supervisor 被回收无人拉起 / 父死子孤烧 token）。

---

## 6. 协调与风险

1. **与正期望分支串行**（Q5）：批次 2/3/D5 改同一 supervisor 文件；pevs P2.7-P3 合入部署后开工，避免双向 rebase。
2. **活跃会话现场**：live repo 有另一会话未提交改动（STATE.md / prompt_base.jinja2 / sync_backup.sh / holiday 报告）——不碰不收；P0 与其 git 层备份互补（N4）。
3. **重启窗口最小化**：批次 2+3 全部合入后**一次重启**生效；A3 根治迁移同窗完成。
4. **指纹纪律**：M5 是唯一可能触碰 gate 语义的条目（tier 依赖 n_eff），必须走 v4 指纹评估流程；L2/L3/L4 属准入/goal 语义，verdict schema 不变，指纹不动。
5. **回滚**：每批次独立提交独立可 revert；P0 迁移失败回滚 = 改回路径常量 + 还原文件 + 重启。

---

## 7. 宿主裁定点（开工前）

| # | 问题 | 建议 |
|---|---|---|
| Q1 | M5 n_eff 溯源后：per-variant 修复（走指纹流程）还是移除显示字段？ | 先溯源；tier 评分依赖 n_eff，大概率只能修复 |
| Q2 | 对象存储第二异地要不要？ | 建议要（<10MB 成本可忽略）；backup 机已消单盘单机风险，可降级可选 |
| Q3 | L3：GOAL_SYMBOLS_SET 从 9 → 24 是否符合本意（硬编码 9 疑为 10-02 goal 重写遗留）？ | 建议单源化到 goal.yaml |
| Q4 | M1：聚合既有 jsonl（推荐，零新状态）还是按 spec D1 建 sqlite？ | 建议聚合既有源 |
| Q5 | 批次 2/3 与 pevs 串行（pevs 先合入）确认？ | 建议确认 |
| Q6 | N1（dead families 生产空转）与 pevs P2.6 生产活性风险**合并**为一次 dm_status 口径裁定？ | 建议合并——同根因两处症状，分开修必然返工 |

---

## 8. 时间表

| 时间 | 内容 |
|---|---|
| 10-07（批准后当天） | 批次 0：应急数据备份（手动 rsync 一次到位） |
| 10-07 ~ 10-09 | 批次 1：工程化（脚本 + cron + safe_clean + 禁令），与 pevs 收尾并行 |
| pevs 合入部署（在途） | 重启窗口顺带完成 A3 根治迁移 |
| pevs 后 +1 天 | 批次 2：P1 差距收口 |
| pevs 后 +1 周 | 批次 3：peer 学习 sprint（3-4 天） |
| 穿插进行 | 批次 4：D4/D5 优先，D2/D6/D7 任意时机 |
| 全部收口 | 清单勘误回写 reports/ + changelog + AGENTS.md 同步 |

---

## 9. 验收总表

| 批次 | 核心验收 |
|---|---|
| 0 | backup 机当日快照 md5 一致 |
| 1 | 3 天 cron 零失败；safe_clean dry-run 零误伤；禁令入 AGENTS.md |
| 2 | 回归恒等；L2/L3/L4 新测试全绿；L4 一致性测试入常备 |
| 3 | prompt 三块新上下文物化；abandon 端到端；dedup 拒收占比下降；专家审核 PASS |
| 4 | D4 看门狗演练（kill 后 15 分钟内拉起）；D5 孤儿清理演练；spec 状态头齐 |
| 收口 | 清单勘误回写 + changelog + AGENTS.md 同步 |

---

## 相关文档

- `docs/superpowers/reports/2026-10-07-tech-debt-inventory.md` — 输入清单（23 条，6 条已过时见 §0.1）
- `docs/superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md` — M1/M4 的 D1/D4 依据
- `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis.md` — peer 学习断裂分析
- `docs/superpowers/plans/2026-10-05-positive-ev-factor-search-plan.md` — 在途正期望分支（串行前置）
- `BACKUP_SYNC_GUIDE.md` — git 层备份指南（P0 数据层方案的互补件）

**计划生成**: 2026-10-07 上午（核实基于 master@5e7237a + live registry 393 行实跑验证）
