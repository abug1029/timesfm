# FM_a 技术债收口方案与实施计划

> **日期**: 2026-10-07
> **输入**: `docs/superpowers/reports/2026-10-07-tech-debt-inventory.md`（23 条：P0=4 / P1=5 / P2=5 / P3=9）
> **核实**: 全部 23 条已对照当前代码（master@5e7237a）与 live 数据逐一核实。**其中 6 条清单说法已过时**（§0.1 勘误表），另核实出 4 项清单未列的新事实（§0.2 N1-N4）。
> **裁定**: 2026-10-07 宿主六项裁定已全部落定（§8）；同日修复裁定落定——**B+C 批准为主菜、不 bump 指纹、第 1 步等待**（§6.4 落地五步）；**事项三（确认派发活性调研）立项并当日完成**（§6.5）。Q6 调研已交付、Q1 溯源已结案（设计使然，M5 关闭零改动）。批次 0/1 设计获批、执行时点待宿主确认。
> **执行约定**: worktree `feat/tech-debt-closure-2026-10-07` + TDD 先红后绿 + 全量回归失败集恒等零新增 + 每批次独立专家审核 + 中文提交。

---

## 0. 盘点核实与勘误

### 0.1 勘误表（清单说法 vs 2026-10-07 上午核实）

| 条目 | 清单说法 | 核实结果 | 证据 |
|---|---|---|---|
| L1 `_dead_families` 误判 | set_mismatch_descriptive 计入死亡阈值，term_structure 5 条全判死 | **已修复**：`_family_confirmatory_counts`（praxist_supervisor.py:1736-1751）只数 `_CONFIRMATORY_DM = {ok, set_mismatch_ok}`（:1714）；live registry 393 行实跑 `_dead_families` 返回**空集**，term_structure（68 行：None×24 / set_mismatch_descriptive×43 / insufficient_common×1）未判死 | live 验证脚本 |
| L5 data_stale 无验收测试 | dfd1f43 设计正确但未写测试 | **已有** `tests/test_success_gate_stale_20261006.py` 共 9 用例：国庆空窗 fail-open、3 天边界仍拒、4 天开闸、同锚新 bar 仍拒、per-symbol、warning-once、时区回退——覆盖完整 | tests/ 目录 |
| M2 Locked this window 未触发 | 函数存在但未写入 peer prompt | **已接线**：prompt builder :1350 `lines.extend(_locked_window_lines(...))`，与 Dead families / Cross matrix / Old-protocol priors / Do-not-re-propose 同段物化 | 代码 :1350 / :2463 |
| D3 user_paused 死标志 | clear_supervisor_pause.py 与 restart 脚本空转 | **已归档**：clear_supervisor_pause.py 已入 `scripts/archive/2026-09-30-dead-code/`；全仓零活代码引用（仅残留 .pyc） | grep -rln 全仓 |
| D8 lgbm 死代码 | 复活代价高 | **已归档**：`cascade/lgbm_features.py` 不存在（09-30 死代码清扫 49 文件之一） | ls |
| D9 prereg writer 未挂账 | 出处不明 | **已挂账**：脚本 docstring 写明一次性用途/拒绝重写语义，出处 commit 34fedcb（v4 预注册写入器） | head 脚本 |
| D7 specs 积压 13 个 | 13 个 | 实为 **9 个**（specs/ 目录实数） | ls |
| M5 n_eff 恒 73 | 所有裁决都显示 73，是常数函数 | **主导但非全量**：73×664 行，另有 1×52、0×52、71×18；且存在真实估计量 `measured_n_eff`（statistical_tests.py:205/:405，与 DM 共用实现）——恒定值需溯源查根因 | registry `uniq -c` |
| A2 三代备份在 /home/abug/ | 同盘风险 | **更糟**：三代 .bak 与 live 文件**同目录**（`task_FM/config/`），同在 `git clean -xdf` 爆炸半径内 | ls task_FM/config/ |

### 0.2 新发现（清单未列）

- **N1（重要）**: L1 修复后的新语义空转——live registry 393 行中 `fam_ok = {}`（**零行**同时满足 status=ok + dm_status∈{ok,set_mismatch_ok} + cov_family 非空）→ `_dead_families` 恒返回空集 → "## Dead families" prompt 段永久为空、family_dead 门永不触发。**与正期望搜索 P2.6 专家审核发现的「生产 dm_status 口径活性风险」同根因**（生产裁决 dm_status 绝大多数为 set_mismatch_descriptive/缺省）。**裁定：并入 Q6 独立子项目（§6）先根因调研，不单独修。**
- **N2**: `aligned_max_points` 代码默认 400（praxist_supervisor.py:3399）vs goal.yaml 600——与 L4 survivors_per_cycle 同类漂移，应同修。
- **N3**: 数据资产远不止裁决文件。gitignored 的还有：`.omc/supervisor_decisions.jsonl`（285KB，18 门拒收历史，今晨仍在追加）、`data/cache/`（supervisor_state.json、aligned_pending* 队列、aligned_checkpoints/）、baseline_points_*.jsonl 约 30 份。备份范围必须覆盖整组。
- **N4**: 今晨另一会话已建立 git 层备份（`BACKUP_SYNC_GUIDE.md` + 根目录未提交的 `sync_backup.sh`，master → backup 机 git 仓）。方向正确，但 **git push/bundle 天然不覆盖 gitignored 数据资产**——P0 缺口仍在，且两者互补不应重复建设。

---

## 1. 批次总览

```
批次 0（批准当天 ~1h）  P0 应急数据备份 ─── 纯 rsync，零代码，零冲突，立即可做 ✅设计已获裁定
批次 1（1-2 天）        P0 工程化（cron / safe_clean / 对象存储默认层） ── 脚本层，与 pevs 无冲突 ✅设计已获裁定
Q6 子项目（0.5-1 天）   dm_status 生产活性根因调研（§6）── 只读零冲突，与一切并行 ✅已启动
Q1 溯源（0.5 天）       n_eff 计算路径溯源（§4 M5 第一步）── 只读，与一切并行 ✅已启动
────── 以下批次改 praxist_supervisor.py，与在途正期望分支（P2.7-P3 未合入）同文件，串行（Q5 已裁定确认）──────
批次 2（1 天）          P1 差距收口：L2 配对键 / L3 单源化（Q3 已裁定：24 品种）/ L4 默认值对齐（含 N2）/ L1+L5 勘误收口
批次 3（3-4 天）        P2 peer 学习：M1 跨 run 统计（Q4 已裁定：方案 A）/ M3 拒收回写 / M4 abandon / M5 n_eff 处置（按 Q1 溯源结论）
批次 4（见缝插针）      P3：D2 star→tier / D4 看门狗 / D5 孤儿 run / D6 消歧 / D7 spec 结案
收口（0.5 天）          清单勘误回写 reports/ + changelog
```

**串行红线（Q5 已裁定确认）**：批次 2/3 与 D5 改 supervisor；正期望分支 P2.7-P3 合入部署（自带重启窗口）完成后，tech-debt 基于新 master 开工。批次 0/1、Q6 调研、Q1 溯源与在途工作零冲突，并行推进。

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

> **2026-10-07 宿主四项裁定**（question 工具落定）：① 批次 0 并入批次 1 一次执行（不做单独手动应急备份）② 目的地=备份机 ③ `.env` 系列**明文包含**（远端 root-only，600 权限随档）④ 一次性全量+里程碑增量+cron 自动化。

1. **异机每日快照**（批次 0+1 合并，2026-10-07 当日实施完成）：
   - `scripts/backup_data_assets.sh`：**tar-over-ssh**（远端 WSL 无 rsync，2026-10-07 实测只有 tar/md5sum）→ backup 机 `chong@100.96.19.116` → WSL `/root/timesfm-data/`（复用 BACKUP_SYNC_GUIDE.md 的 ssh 通道与密钥）
   - 双份布局：`latest/`（tmp 原子换名）+ `daily/`（日期快照，远端 cp，保留 180 天）+ `md5sums.txt`/`md5sums.remote.txt` 核对清单
   - 远端调用一律**单命令**（sshd→cmd→wsl→sh 链路吃复合命令引号，实测）；校验用绝对路径清单 `md5sum -c --quiet`，不过即非零退出
   - tar `--owner=0 --group=0`：远端全档 root:root（明文 .env 600，卫生）
   - 明示出备：`data/cache/daily_pred/`（预测产出可再生，~170MB）、`.git/`（sync_backup.sh 另轨）、`logs/`
   - crontab：每日 02:15（避开既有 17:45 数据拉取与周六 02:35 任务）；操作副本部署 `/home/abug/bin/`，改版后须重新 `install -m 755`
2. **防误删**（批次 1，2026-10-07 实施完成）：
   - `scripts/safe_clean.sh`：`git clean -xdf` 白名单包装，排除 `-e task_FM/config/ -e .omc/ -e data/cache/ -e logs/ -e .env -e .env.*`；默认 dry-run + 白名单自检（命中保护路径即 FATAL），`--apply` 才执行
   - AGENTS.md「数据资产与清理禁令」节 + runbook「数据资产备份与清理」节已落（2026-10-07）：清理一律走 safe_clean，禁止裸 `git clean -xdf`
   - **根治**（迁移 live 数据出 repo tree，使 git clean 永远够不着）：路径常量改为可配置（env 覆盖），迁移 + 改配置 + 重启原子完成——**搭事项一 B+C 合入的重启窗口顺风车**（与 A3 同窗），不单独重启
3. **第二异地（Q2 已裁定：默认层，宿主设计）**：rclone → S3 兼容对象存储，**每次同步默认包含**（backup_data_assets.sh 内置 rclone 步；本机未装 rclone 时 WARN 跳过不报错——2026-10-07 当前状态）。S1+S2 总量 <10MB，成本可忽略。**前置**：宿主提供 S3 兼容端点 + 密钥（Backblaze B2 / Cloudflare R2 / 阿里云 OSS 或已有云盘均可，rclone 皆支持）。daily 快照保留 180 天（防勒索软件潜伏期）。

### 2.3 与在途工作的关系

sync_backup.sh（另一会话未提交）管 git 层，本方案管数据层，职责分离互补。建议该会话采纳本计划后，把 `sync_backup.sh push` 与 `backup_data_assets.sh` 挂进同一 cron 条目，一次跑齐。

### 2.4 验收

- [X] backup 机存在当日快照，md5 与本地一致（2026-10-07 首份全量：458 文件/140M，`latest/`+`daily/2026-10-07/` 双落位；远端 `md5sum -c` 全量通过 + 本地↔远端独立抽查一致；`.env` 系列远端 `-rw------- root root`）
- [ ] 对象存储端存在当日快照（rclone 默认步）——**待宿主端点+密钥**（本机未装 rclone，脚本 WARN 跳过中）
- [ ] 连续 3 天 cron 零失败（2026-10-07 02:15 首跑观察期，日志 `logs/backup_assets_cron.log`）
- [X] `safe_clean.sh` dry-run 不命中任何 S1/S3 资产（2026-10-07 活仓实跑：零保护路径命中，自检 FATAL 未触发）；裸 clean 禁令写入 AGENTS.md（+runbook 节）
- [ ] （迁移后）`git clean -xdfn` 对数据零威胁；supervisor 重启后首轮裁决追加正常、指纹 f02b2a43 不变、baseline 零重生——**A3 搭事项一 B+C 重启窗口，未到期**

### 2.5 实施记录（2026-10-07，批次 0+1 合并执行）

- 首份全量 34 秒完成（16:57:03→16:57:37）；458 资产/140M（含 aligned_checkpoints 135M、.omc 全目录、明文 .env×5、git 留证、未跟踪脚本×3）
- 通道实测两次踩坑后定型：① 远端无 rsync → tar-over-ssh；② 复合命令引号被 sshd→cmd→wsl→sh 链路吃掉 → **单命令铁律** + 绝对路径 md5 清单
- 部署：`/home/abug/bin/{backup_data_assets.sh,safe_clean.sh}`（755）；cron `15 2 * * *` 已装（原 crontab 备份 `~/crontab.backup.20261007`）
- 文档：AGENTS.md 禁令节 + runbook「数据资产备份与清理」节
- 探针/验证脚本留档：`/tmp/probe_backup_channel.sh`、`/tmp/verify_backup_remote.sh`（会话临时件，未入仓）

---

## 3. 批次 2：P1 差距收口（1 天，pevs 合入后）

### L2 `_has_prior_failure` 单键 OR → 配对键（0.5 天，本批次唯一的真开门修复）

- **现状**（:1426-1442）：10-03 已收窄到可确认失败（`_is_confirmable_failure`），但仍是 symbol **OR** cov 单键命中即拦——同 symbol 异 cov、异 symbol 同 cov 都被误拦，污染半径大于文档描述。
- **方案**：改 (symbol, cov_override) **配对 AND** 匹配；docstring 同步；测试三例：同对拦截 / 同 symbol 异 cov 放行 / 异 symbol 同 cov 放行。
- **影响**：拦截面收窄 → 探索提案增加；dedup 门与 Do-not-re-propose 段兜底。
- **注意**：属准入语义，verdict 行 schema 不变，协议指纹不动。

### L3 GOAL_SYMBOLS_SET 单源化（0.5 天，Q3 已裁定：研究 24 个品种而非 9 个）

- **现状**：:1673 硬编码 9 品种 vs goal.yaml `target_symbols` 24（10-02 goal 重写后遗留）；:1303 prompt "## Symbol status" 只报 9 个；:1028 变量名 `n_one_star_symbols_hit` 还是 star 时代（随 D2 改名）。
- **方案（按裁定）**：启动时从 goal.yaml 读 target_symbols 构建 GOAL_SYMBOLS_SET，**删除硬编码**；goal.yaml 缺 target_symbols → 启动失败（fail loud，禁止静默回退——静默回退正是 9 vs 24 分裂的成因）；新增测试断言 goal.yaml 增删品种 → 集合跟随。
- **影响**：goal 完成度统计范围 9→24，属 goal 语义**对齐**（yaml 是契约），非 gate 语义；随重启生效。

### L4 cadence 默认值对齐（0.25 天，含 N2）

- **现状**：:3398 `survivors_per_cycle` 默认 2 vs yaml 3；:3399 `aligned_max_points` 默认 400 vs yaml 600。
- **方案**：两处默认改与 yaml 一致；缺键回退时打 WARN 日志；**新增一致性回归测试**（加载 goal.yaml，断言代码全部 cadence 默认值 = yaml 值，防再漂移）；runtime_contract.md 记录。

### L1 / L5 收口（0.25 天）

- L1：修复与测试已在（test_supervisor.py / test_harvest_proposals.py 引用 `_dead_families`）；收口动作 = §0.1 勘误回写 + N1 空转观察并入 Q6 子项目（§6），**不在本批次改代码**。
- L5：test_success_gate_stale_20261006.py 已 9 用例含边界与恢复；收口动作 = 勘误回写，无代码。

### 批次 2 验收

- 全量回归失败集恒等零新增（以开工分支基线为准）
- L2/L3/L4 各带新测试；L4 一致性测试入常备套件
- 生效需一次 supervisor 重启——**与批次 3 合入后一次重启**，不单独重启

---

## 4. 批次 3：P2 peer 学习差距（3-4 天，pevs 合入后）

M2 已接线无需实施；D1 锚点随本批次 prompt 组装重写顺带完成。

### M1 跨 run 统计通道（1.5 天，Q4 已裁定：方案 A——聚合既有源）

- **现状**：shared_store.db / research_memory.jsonl / cross_run_learning.jsonl 均不存在（仅 cleanup 脚本挂名）；历史 gate_pass 统计 peer 看不到，每次 run 近乎从零开始。
- **方案（按裁定）**：**读时聚合，不引入第三份状态存储**——从 aligned_verdicts.jsonl + .omc/supervisor_decisions.jsonl 聚合 (symbol, cov, family, 门, 结果, 时间) 滚动统计 → 物化 `known_verdicts_stats.inc.md` 注入 prompt。spec D1 补实施注记（"以读时聚合实现，shared_store.db 缓发"）。

### M3 拒收理由回写（1 天）

- **现状**：prompt 已含 Symbol status / Effective clues / Dead families / Cross matrix / Old-protocol priors / Locked this window / Do-not-re-propose，**唯独没有拒收原因段**；no_failure_delta 等纯规则门的拒收 peer 全看不到。
- **方案**：从 supervisor_decisions.jsonl 聚合近 7 天拒收分布（门 × 组合频次 top-N + 一句话原因）→ prompt 新段 "## Why proposals were rejected recently"。
- **注意**：清单引用的 57%/18%/16% 分布是修复前统计（family_dead 在现行代码下因 N1 恒空已归零）——实施时以 decisions 日志**现算**为准，不搬旧数字。

### M4 `decision: abandon`（1 天）

- **现状**：supervisor 全文零 abandon 引用（spec D4 未实施），falsifier 被迫用正例提案表达反对。
- **方案**：peer 输出 schema 增 `decision: "abandon"` 字段 → supervisor 记 decisions 行 + 跳过 run 派发 + 回写教学注记；存量正例提案路径不变。

### M5 n_eff 恒值溯源（Q1 已裁定：两步走）

- **现状**：73×664 行主导 + 1×52 + 0×52 + 71×18；存在真实估计量（statistical_tests.py:205/:405 与 DM 共用）——恒 73 疑为共享评估窗 + 相似自相关结构所致（71×18 的存在说明对样本长度有响应），**也可能输入序列被错误共享**。
- **第一步（溯源已完成 2026-10-07，结论 (a) 设计使然，详见 dm-status 报告 §8）**：追 build_summary 里 `verdict["n_eff"]` 的来源；手算 2-3 个变体 d 序列的 n_eff 对照。三种结论：(a) 设计使然（共享窗 + 取整）→ 关闭 M5 勘误回写，零改动；(b) 输入序列错误共享 → per-variant 修复 + v4 指纹流程；(c) 显示层缓存 → 修显示层。
- **第二步（处置）**：按第一步结论执行；**"移除"选项作废**（tier_classifier._score_n_eff 依赖 n_eff，:76/:127）。
- **高危注意**：任何 n_eff 语义变更 = tier 变更 = 触碰 gate 评估语义 → 协议指纹纪律适用，绝不能裸改。

### D1 行号 → 章节锚点（0.5 天，随批次顺带）

- prompt 内嵌的规格**行号**引用全部改为**章节锚点**，一劳永逸免疫代码合入导致的行号漂移；M1/M3 重写 prompt 组装时一并处理。

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

## 6. Q6 独立子项目：dm_status 生产活性根因调研

> **裁定（2026-10-07）**：作为独立子项目，**先彻底调研清楚根因，再讨论修复方案**。调研阶段只读零冲突，与 pevs 收尾、批次 0/1 并行。

### 6.1 背景：两个症状 + 共同根因假说

- **症状一（N1）**：`_dead_families` 只数可确认行（`_CONFIRMATORY_DM = {ok, set_mismatch_ok}`，:1714）→ 生产恒返回空集（live 实测 393 行 `fam_ok={}`）→ "## Dead families" prompt 段永久为空、family_dead 门永不触发 → 真死家族持续吃提案预算。
- **症状二（pevs P2.6 专家审核）**：`compute_incremental_vs_incumbent` 按 spec §6.4 要求可确认 dm_status → 生产增量 DM 恒 fail → 途径 (b) 晋升部署即休眠。
- **共同根因假说**：可确认判据（dm_status ∈ {ok, set_mismatch_ok}）在生产裁决中占比≈0；`set_mismatch_descriptive`（样本集错位仅描述性）是生产常态——变体与基准的样本集错位（数据可得性、协变量 NaN、评估窗漂移）可能才是需要解释的现象。

### 6.2 调研问题（四层）

1. **分布层**：393 行 dm_status 全量分布（× status × gate_pass × 协变量族 × 时间趋势）；可确认行历史上是否曾非零；descriptive 占比是否随协议版本/时间变化。
2. **机制层**：dm_status 赋值代码路径——ok / set_mismatch_ok / set_mismatch_descriptive / no_common_cutoff / insufficient_common 的判据与阈值；dm_diag（variant_series / baseline_series / pairing_valid / missingness_admissible）各字段语义与生产取值分布。
3. **根因层**：错位从哪来，逐行量化各成因占比——(a) 基准锚定时间 vs 变体评估时间差（eval_end_ts 漂移；T2d 修过 eval_end_ts 兜底说明窗漂移真实存在）；(b) 协变量 NaN 裁剪变体序列；(c) baseline_points 重生时点 vs 新变体数据可得性；(d) 其他（配对窗锚、cutoff 不一致）。
4. **影响层**：若维持现状——途径 (b) 晋升激活需要什么条件、何时可能达成；家族死亡门休眠的预算成本估算（多少提案浪费在真死家族上）。

### 6.3 交付物与边界

- **交付物**：`docs/superpowers/reports/2026-10-07-dm-status-liveness-root-cause.md`（已交付 2026-10-07）——证据 + 机制 + 根因占比 + **修复选项清单（只列选项不决策）**；修复方案讨论 → 宿主裁定 → 届时回写本计划或另立实施计划。
- **边界**：只读调研（registry / checkpoints / 代码），零代码改动；调研阶段不预设修复方案（避免锚定效应）；工作量 0.5-1 天。
- **关联**：调研结论同时服务 pevs P2.7 的 dm_status 口径实现与 N1 修复——一份证据，两处消费。

### 6.4 修复裁定与落地五步（2026-10-07 下午，宿主裁定，Q6-续）

> 裁定要旨全文见 dm-status 报告 §6 裁定段 + 附录 A（A.1-A.9）；报告开放问题 #1/#4 已关闭，#2/#3 升格为通电前置检查（五步中第 5 步）。

**裁定**：**B 批准**（边缘连续块豁免——变体侧最新连续块 / 基线侧最旧连续块 + 有界性双条件「每侧 ≤30 日期」，任一不满足落回 descriptive；窗内缺失仍 False；只翻转 missingness_admissible，不改 dir_acc/d_t/DM 统计量与 p 值）；**C 批准**（基线快照版本化为前置；守卫断言 = 重锚不得删除 cutoff ≥ confirm_from_ts 的基线快照；unmatched 预期 ≈ 拉取滞后 1-3 点，**B 不因 C 省略**）；**A 缓发**（待真实窗内状态相关缺失案例带实测数据再裁）；**D、E 不采用**；**不 bump 协议指纹**（admissibility_rule 行级标记替代；限定 = 只改 missingness_admissible 判定规则，将来 d_t/DM 估计量、带宽、配对集计算本身变化必须 bump；实施前断言同一行 protocol_fingerprint 前后不变，若指纹分量实际哈希 dm 层内容则作废回 bump 评估）；**第 1 步等待**（观察条件 = B+C 上线满一个完整慢环周期、可确认行仍为零 → 带实测数据重开；期间 min_ok=4 与 gate_pass 不改）；**pevs P2.7 可恢复**（消费端接线待 B+C 合入 master）。

**落地五步（顺序执行，每步独立提交）**：

1. **基线快照版本化**（第 2 步前置；**批次 0 数据备份先行**——版本化改变 baseline_points 布局）✅ **完成 2026-10-07 21:15**（`4ae5336`）
2. **C**：拉取日重锚 + 守卫断言 ✅ **完成 2026-10-07 21:45**（`bd1cd16`）
3. **B + 采集包**：admissibility_rule 行级可选字段——唯一写入路径 = 裁决行产出；五个读取点（fdr_pass_persistable / _test_invalid / _passes_confirmation / classify_confirmation / _family_confirmatory_counts）只计匹配预注册钉定规则的行；旧行缺字段不计入、不回溯解释 ✅ **完成 2026-10-07 22:00**（`e3cc1dd` + P1 修复 `71f8517`）
4. **补盖两条预注册**（jd daily_slope+vor、sr daily_slope+vwap_deviation；补盖前必须重核验各自可确认行数 = 0 并留痕命令/时间/结果，非零则暂停另行裁定）✅ **完成 2026-10-07 22:20**（`3233a75`）
5. **通电前置核查 #2/#3**（#2 判定标准见派发活性报告 §4）⏳ **blocked**——待数据恢复（1H 数据末端越过 confirm_from_ts 2026-10-03，预计 ~10-09）+ supervisor 重启加载步①②③④新代码

**实施记录（2026-10-07 晚，事项一五步）**：

- **前置**：rebase tech-debt 分支到最新 master f0a7c23（零冲突，三提交重写 `e475aab/ad81e1d/01d593d`）+ force-push backup
- **测试基线钉死**（@`01d593d`，183 秒）：18F / 1799P / 5S / 1X / 9E——27 项非绿全部 pre-existing（分支 diff 纯 docs+shell 零 .py）
- **步① 基线快照版本化**（`4ae5336`）：`_archive_baseline_before_regen()` + ensure_baselines 三重生点统一插桩（归档→重生）；归档名 `{stem}.archive_{锚定日}{ext}`（锚定日=旧档最后可解析行 cutoff，全坏回退 mtime，同名冲突追加序号）；copy 语义、归档失败仅 WARN 不阻塞、归档不清理。测试 5 例全绿。全量回归 18F/1804P（+5P，零新增失败）
- **步② C 拉取日重锚 + 守卫**（`bd1cd16`）：`_latest_data_dt()` 抽出（与 `_confirm_data_ready` 共享 `_CONFIRM_DATA_CACHE` 30 分钟 TTL）；`_baseline_reanchor_reason()` 双条件重锚判定（(a) 确认窗覆盖缺口 + (b) 漂移上界 168h=7 天）；fail-open（数据/基线末端读不到不动作）；`_guard_confirm_from_ts_after_regen()` 守卫断言（新档丢失旧档 ≥ confirm_from_ts 的 cutoff → 从归档恢复 + ERROR 留痕）；`_regen_baseline_with_archive()` 三重生点统一入口。测试 12 例全绿。全量回归 18F/1816P（+12P，零新增失败）
- **步③ B + 采集包**（`e3cc1dd` + P1 修复 `71f8517`）：`pair_dir_ok_series_with_diagnostics` 增加边缘连续块 + 有界性双条件检查（变体侧尾部连续块 / 基线侧头部连续块 + 每侧 ≤30 日期）；不通过落回 `set_mismatch_descriptive`；通过返回 `admissibility_rule="edge_continuous_block_30d"` + `unmatched_variant_dates` / `unmatched_baseline_dates` 位置信息；五读取点加 `admissibility_rule is not None` 过滤。测试 14 例全绿（含 P2 补测 4 例）。测试 fixture 批量更新（16 个测试文件）。全量回归 18F/1830P（+14P，零新增失败）。专家审核：P1（Critical）边缘连续块检查缺失 → 已修复；P2（Major）测试覆盖缺失 → 已补；R2（Major）位置信息采集缺失 → 已补；复审通过
- **步④ 补盖两条预注册**（`3233a75`）：重核验留痕（2026-10-07 22:18 CST，jd/sr 可确认行数 = 0，各 13 行全为非确认状态）；`task_FM/config/preregistry.jsonl` 两行加 `"admissibility_rule": "edge_continuous_block_30d"` + `"admissibility_note": "admissibility_rule 系 2026-10-07 裁定补设，confirm_from_ts 与 n_confirm_required 不变"`。测试修复 `test_first_preregistry.py`。全量回归 18F/1830P（零新增失败）。专家审核：有条件通过（已补正 changelog + 重核验留痕 `86c5902`）
- **步⑤ 通电前置核查 #2/#3**：blocked——待数据恢复（1H 数据末端越过 confirm_from_ts 2026-10-03，预计 ~10-09）+ supervisor 重启加载步①②③④新代码
- **总测试状态**：基线 18F/1799P → 步①②③④后 18F/1830P（+31P，零新增失败）
- **提交清单**：`4ae5336`（步①）→ `bd1cd16`（步②）→ `e3cc1dd`（步③）→ `71f8517`（步③ P1 修复）→ `3233a75`（步④）→ `86c5902`（changelog 补步③④条目）

**证据基线**：逐行边缘连续审计 106/106 非零 unmatched 行通过、零内部散点（报告附录 B，两次读数恒等：(14,13)×57 / (11,10)×35 / (17,16)×14，每侧实测最大 17 < 30）；21 行基线覆写留痕入报告附录 C（全部 recorded (0,0)，评估后覆写，不推翻审计）。

**实施基线更新（2026-10-07 晚）**：pevs P2.1-P2.9 已合入 master（b86ddba + ca4a3b9 执行位修复）；本分支 merge-base = 5e7237a → **开工第一步 = rebase 到最新 master**；supervisor 行号已漂移（_family_confirmatory_counts :1766、_dead_families :1784、ensure_baselines :3697、两 TTL :1748/:1752——dm-status 报告正文行号系 master@5e7237a 读数，其附录 A 头注已声明）。

### 6.5 事项三：确认派发活性调研（2026-10-07 立项，当日完成）

- **背景**：dm-status 报告 §7 #2 通电前置检查——2026-10-03 两条预注册落地后 registry 仅 4 行 no_data 存根、`__prereg_` 检查点 0 字节，确认派发链是否仍在运转需独立查证（B+C 让 dm_status 可确认，但不保证派发与评估运转）。
- **交付**：`reports/2026-10-07-confirmation-dispatch-liveness.md`（机制层派发链全图 + 实证留痕 + 结构结论 + 通电判定标准）。
- **结论**：派发机制健康、全程在线——主循环每拍尝试派发（:4210 → :490），数据闸门（:444，1H 最新 bar 须 > confirm_from_ts，30 分钟按 symbol 缓存，10-03 深夜上线）因国庆数据缺口（末端 2026-09-30 14:00）全部拦截，decisions 日志 50 条 `confirmation_not_enqueued`（~6h 精确节奏）留痕完整；存根与 0 字节检查点系数据闸门上线前的最后墓碑，非机制失联。
- **结构发现**：**B+C 是确认轨道的结构性前置**——`ensure_baselines`（:3697）无数据新鲜度检查 → 冻结基线对确认窗（≥10-03）零覆盖 → 数据恢复后无 C = no_common_cutoff 6h 一座 × 2 预注册无限循环（派发能入队、评估恒失败）；无 B = descriptive 拦截 `_passes_confirmation`（评估能跑、确认恒不通过）。与 #3（十月探索行 no_common_cutoff×9，B 不豁免，正交）边界已划清。

---

## 7. 协调与风险

1. **与正期望分支串行（Q5 已裁定确认；2026-10-07 晚状态更新：pevs P2.1-P2.9 已合入 master，b86ddba + ca4a3b9）**：批次 2/3/D5 改同一 supervisor 文件，基于 post-merge master 开工（本分支 merge-base 5e7237a，开工先 rebase）；P2.7 消费端接线待 B+C 合入 master（§6.4 第 3 步后）。supervisor 重启窗口未发生（PID 146369 仍跑 pre-merge 内存代码，子进程已用 post-merge 磁盘代码）——批次 2+3 与 A3 根治迁移合并一次重启。批次 0/1 与调研类工作不受约束。
2. **活跃会话现场**：live repo 有另一会话未提交改动（STATE.md / prompt_base.jinja2 / sync_backup.sh / holiday 报告）——不碰不收；P0 与其 git 层备份互补（N4）。
3. **重启窗口最小化**：批次 2+3 全部合入后**一次重启**生效；A3 根治迁移同窗完成。
4. **指纹纪律**：M5 是唯一可能触碰 gate 语义的条目（tier 依赖 n_eff），必须走 v4 指纹评估流程；L2/L3/L4 属准入/goal 语义，verdict schema 不变，指纹不动。Q6 调研阶段零改动，调研后若涉及 dm_status 口径变更，属 gate 语义，同样走指纹纪律评估。
5. **回滚**：每批次独立提交独立可 revert；P0 迁移失败回滚 = 改回路径常量 + 还原文件 + 重启。

---

## 8. 宿主裁定点与裁定结果（2026-10-07 全部落定）

| # | 问题 | 裁定 |
|---|---|---|
| Q1 | M5 n_eff 溯源后：per-variant 修复还是移除显示字段？ | **两步走**：先溯源（已完成 2026-10-07：确认非 bug，n_eff=解析式 Bartlett 修正，M5 关闭，详见 dm-status 报告 §8）；确证 bug 才修且走 v4 指纹流程；**移除选项作废**（tier 评分依赖 n_eff） |
| Q2 | 对象存储第二异地要不要？ | **要，且为默认层（宿主设计）**：每次同步默认包含 rclone 步；前置 = 宿主提供 S3 兼容端点 + 密钥；daily 保留延至 180 天 |
| Q3 | L3：GOAL_SYMBOLS_SET 从 9 → 24 是否符合本意？ | **确认：应研究 24 个品种而非 9 个**。单源化到 goal.yaml，删除硬编码，缺键 fail loud |
| Q4 | M1：聚合既有 jsonl 还是按 spec D1 建 sqlite？ | **方案 A**：读时聚合既有 jsonl，零新状态；spec D1 补实施注记，sqlite 缓发 |
| Q5 | 批次 2/3 与 pevs 串行（pevs 先合入）？ | **确认串行，pevs 先行**；批次 0/1、Q6、Q1 溯源并行不受限 |
| Q6 | N1 + pevs P2.6 生产活性风险如何裁定 dm_status 口径？ | **独立子项目（§6）**：先彻底调研清楚根因（分布/机制/根因/影响四层），再讨论修复方案；调研只列选项不决策 |
| Q6-续（2026-10-07 下午） | 修复选项 A-E 择何？是否 bump 指纹？第 1 步 min_ok 观察是否调整？ | **B+C 批准为主菜**；采集包同步落地；**不 bump**（admissibility_rule 行级标记替代）；**第 1 步等待**（min_ok=4 与 gate_pass 不动）；A 缓发；D/E 不采用。全文 = dm-status 报告 §6 裁定段 + 附录 A；落地五步 = §6.4 |

---

## 9. 时间表

| 时间 | 内容 |
|---|---|
| 10-07（已批准） | 批次 0 应急备份（执行时点待确认）+ **Q6 调研启动** + **Q1 溯源启动**（两者只读并行） |
| 10-07 晚（回写中） | Q6 修复裁定落定 → §6.4 五步；事项三立项并当日完成调研 → §6.5；dm-status 报告补附录 A/B/C（裁定要旨 + 106/106 逐行审计 + 21 行覆写勘误）；pevs 合入 master（b86ddba） |
| 批次 0+1 落地后 | **事项一（§6.4 五步）实施**：步①②③④已完成（`4ae5336`→`bd1cd16`→`e3cc1dd`+`71f8517`→`3233a75`→`86c5902`）；步⑤ blocked（待数据恢复 ~10-09 + supervisor 重启） |
| 10-07 16:57（已完成） | 批次 0+1 合并执行：首份全量 458 文件/140M + md5 全过 + cron 02:15 装机 + safe_clean + AGENTS/runbook 禁令；rclone 层待宿主端点+密钥（WARN 跳过中） |
| pevs 合入部署（已完成 10-07，重启待宿主窗口） | 重启窗口顺带完成 A3 根治迁移；P2.7 消费端接线待 B+C |
| Q6 调研交付（0.5-1 天） | 根因报告 → 宿主裁定 dm_status 口径 → 反哺 pevs P2.7 与 N1 修复 |
| pevs 后 +1 天 | 批次 2：P1 差距收口 |
| pevs 后 +1 周 | 批次 3：peer 学习 sprint（3-4 天） |
| 穿插进行 | 批次 4：D4/D5 优先，D2/D6/D7 任意时机 |
| 全部收口 | 清单勘误回写 reports/ + changelog + AGENTS.md 同步 |

---

## 10. 验收总表

| 批次/项目 | 核心验收 |
|---|---|
| 0+1（合并执行，10-07 完成） | backup 机当日快照 md5 一致 ✅（458 文件/140M，latest+daily 双落位）；safe_clean dry-run 零误伤 ✅；禁令入 AGENTS.md ✅；cron 3 天观察期进行中；对象存储端待宿主端点（WARN 跳过） |
| Q6 子项目 | 根因报告交付（四层问题全答 + 修复选项清单）；宿主据此裁定口径 |
| Q1 溯源 | n_eff 来源结论明确（三种假设之一落定）；若需修复则指纹评估先行 |
| 事项一（dm_status 口径修复 = Q6-续） | 步①②③④已完成 ✅（基线快照版本化 + C 拉取日重锚 + B 边缘连续块 + 补盖预注册）；测试 18F/1830P（+31P，零新增失败）；步⑤ blocked（待数据恢复 + supervisor 重启） |
| 事项三（派发活性调研） | 报告交付：派发链机制全图 + 50 条留痕实证 + 结构结论（B+C 为确认轨道结构性前置）+ 通电判定标准 |
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
- `docs/superpowers/changelogs/2026-10-07-tech-debt-closure-plan-and-rulings.md` — 本计划的裁定记录
- `BACKUP_SYNC_GUIDE.md` — git 层备份指南（P0 数据层方案的互补件）

**计划生成**: 2026-10-07 上午（核实基于 master@5e7237a + live registry 393 行实跑验证）
**裁定回写**: 2026-10-07（宿主六项裁定全落定）
**修复裁定回写**: 2026-10-07 晚（Q6-续 B+C/不 bump/第 1 步等待 → §6.4；事项三立项并完成 → §6.5；pevs 合入注记 → §7.1）
