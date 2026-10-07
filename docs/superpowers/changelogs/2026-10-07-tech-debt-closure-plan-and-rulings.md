# 技术债收口：盘点核实 + 收口计划 + 宿主六项裁定

> **日期**: 2026-10-07
> **分支**: feat/tech-debt-closure-2026-10-07（worktree /home/abug/timesfm-wt-techdebt）
> **输入**: reports/2026-10-07-tech-debt-inventory.md（23 条，另一会话 07:30 生成）

## 做了什么

1. **23 条全量核实**（代码对照 master@5e7237a + live registry 393 行实跑验证）：
   - **6 条勘误**（清单说法已过时）：L1 `_dead_families` 已修复（live 实跑返回空集）、L5 已有 9 用例测试、M2 Locked window 已接线（:1350）、D3/D8 已归档、D9 已挂账
   - **4 项新发现**：N1 dead families 生产空转（`fam_ok={}`，与 pevs P2.6 生产活性风险同根因）、N2 aligned_max_points 默认值漂移、N3 数据资产清单扩大（decisions/基线/cache 均 gitignored 无保护）、N4 git 层备份不覆盖数据资产
2. **收口计划** `plans/2026-10-07-tech-debt-closure-plan.md`：批次 0-4 + Q1-Q6 裁定点 + 验收总表
3. **宿主六项裁定**（同日全落定，回写计划 §8）

## 裁定记录

| Q | 裁定 | 计划影响 |
|---|---|---|
| Q1 n_eff | 两步走：先溯源（默认假设非 bug）；确证 bug 才修且走 v4 指纹流程；移除作废（tier 依赖） | §4 M5 拆为溯源+处置两步，溯源即日启动 |
| Q2 第二异地 | **要，且为默认层（宿主设计）**：每次同步默认含 rclone | §2.2 第三层从可选转默认；daily 保留 180 天；待端点+密钥 |
| Q3 品种集 | **研究 24 个品种而非 9 个** | §3 L3 单源化 goal.yaml、删硬编码、缺键 fail loud |
| Q4 M1 通道 | **方案 A**：读时聚合既有 jsonl | §4 M1 定案，零新状态存储；spec D1 补注记 |
| Q5 串行 | **确认串行，pevs 先行** | 批次 2/3/D5 排 pevs 合入后；批次 0/1 并行不受限 |
| Q6 dm_status 口径 | **独立子项目**：先彻底根因调研（分布/机制/根因/影响四层），再讨论修复 | 新增计划 §6 子项目章程；N1 并入；调研结论反哺 pevs P2.7 |

## 解锁与启动

- **批次 0/1（P0 资产保护）**：设计全部落定；批次 0 执行时点待宿主确认；对象存储待 S3 端点+密钥
- **Q6 调研子项目**：即日启动（只读零冲突）——交付 `reports/2026-10-07-dm-status-liveness-root-cause.md`（证据+机制+根因占比+修复选项清单，只列不决策）
- **Q1 溯源**：即日启动（只读）——追 n_eff 计算路径，三假设择一落定
- **批次 2/3**：待 pevs P2.7-P3 合入部署后基于新 master 开工

## 提交

- `767ad43` docs: 技术债收口方案与实施计划——23 条全核实（6 条勘误）+ 批次 0-4 + 裁定点 Q1-Q6
- 本次提交：裁定回写（§8 裁定表 + §6 Q6 子项目章程 + Q2/Q3/Q4/Q5 相关章节同步）+ 本 changelog


## 后续：Q6 调研 + Q1 溯源完成（2026-10-07 晚）

- 交付 `reports/2026-10-07-dm-status-liveness-root-cause.md`：根因 = spec §7.8 开放问题 #8 未裁定（missingness_admissible 恒 False，可确认分支结构不可达，396 行历史零可确认）；生产"mismatch"实证为基线快照 vs 滚动窗的良性边缘漂移（47.6% 行零不匹配，jd_ccl 案例首尾落点实证）；修复选项 A-E 只列不决策，待宿主裁定
- Q1 溯源结案：n_eff = fallback_n_eff 解析式 Bartlett 修正（n=588 → 恒 73，monthly_backtest.py:660 唯一生产路径），设计使然非 bug，**M5 关闭零改动**；measured_n_eff / effective_sample_size 为死代码（登记 D 类清理候选）
- 计划文档同步：§4 M5 溯源完成标记 / §6 交付物已交付标记 / §8 Q1 行补结论

## 后续：Q6 修复裁定回写 + 事项三立项并完成（2026-10-07 晚）

- **宿主修复裁定（事项一，Q6-续）**：**B+C 批准为主菜**（B = 边缘连续块 + 有界性双条件豁免，每侧 ≤30 日期，窗内缺失仍 False，只翻转 missingness_admissible；C = 基线快照版本化前置 + 拉取日重锚 + confirm_from_ts 守卫断言，B 不因 C 省略）；采集包同步落地；**不 bump 协议指纹**（admissibility_rule 行级标记替代；限定只改 missingness_admissible 判定规则；实施前断言同一行指纹不变）；**第 1 步等待**（min_ok=4 与 gate_pass 不动；B+C 满一慢环周期可确认行仍为零 → 带实测重开）；A 缓发、D/E 不采用；pevs P2.7 可恢复。报告开放问题 #1/#4 关闭、#2/#3 升格通电前置检查
- **裁定回写**：dm-status 报告补附录 A（裁定要旨 A.1-A.9）/ B（逐行边缘连续审计 106/106 通过、零内部散点、(14,13)×57/(11,10)×35/(17,16)×14，两次读数恒等）/ C（21 行基线覆写留痕 + 勘误：上午「今日行今晨拉取」推断被逐行证伪——实为 09-29~10-03 决定行被 10-01/10-03 两个已知再生波覆写，同型错误第四次留痕）；计划新增 §6.4（裁定 + 落地五步 + 实施基线更新）与 §6.5（事项三），§7.1/§8/§9/§10/尾注同步
- **事项三（确认派发活性调研）立项并当日完成**：机制健康——主循环每拍尝试派发，数据闸门（:444，10-03 深夜上线）因国庆缺口（1H 末端 2026-09-30 14:00）全部拦截，50 条 confirmation_not_enqueued 留痕 ~6h 精确节奏；4 存根 + 0 字节检查点系闸门上线前最后墓碑。**结构发现：B+C 是确认轨道结构性前置**（ensure_baselines :3697 无新鲜度检查 → 冻结基线对确认窗零覆盖 → 无 C = no_common_cutoff 无限循环；无 B = descriptive 拦截确认）。独立报告 `reports/2026-10-07-confirmation-dispatch-liveness.md`
- **上游状态**：pevs P2.1-P2.9 已合入 master（b86ddba + ca4a3b9）；上游 master f0a7c23（backup = origin）已含本分支全部提交（对方机器合并）；事项一六文件与上游零冲突，开工第一步 = rebase
- **待裁（事项二修订提案随本轮呈报）**：批次 0 执行时点 / 备份目的地 / .env 系列敏感文件处置 / 频率

## 后续：事项三交付——确认派发活性调研报告（2026-10-07 晚，续）

- 新增 `reports/2026-10-07-confirmation-dispatch-liveness.md`：机制层（派发链全图 ：4210/:490/:354/:444/:477/:517-529 + 提案支线 :222 + 6h 双 TTL）+ 实证层（50 条 not_enqueued 留痕 ~6h 精确节奏持续到 10-07 09:56；4 存根 + 2 个 0 字节检查点 = 闸门前最后墓碑；队列 pending 空）+ 结构层（ensure_baselines :3697 三再生条件无新鲜度检查 → **B+C 为确认轨道结构性前置**；时间线推演表）+ 通电判定标准（三正例 + 四反例诊断，服务计划 §6.4 第 5 步 #2）
- dm-status 报告 §7 #2 状态更新：「已调研（机制健康）」+ 指向派发活性报告；#3（十月探索行 no_common_cutoff×9）边界划清——正交，B 不豁免，待第 5 步单独验

## 后续：批次 0+1 合并执行完成（2026-10-07 17:03）

- **宿主四项裁定（事项二，question 工具落定）**：① 批次 0 并入批次 1 一次执行 ② 目的地=备份机 ③ `.env` 系列明文包含（远端 root-only，600 随档）④ 一次性全量+里程碑增量+cron 自动化
- **首份全量备份落地**（16:57:03→16:57:37，34 秒）：458 文件/140M → 备份机 WSL `/root/timesfm-data/{latest,daily/2026-10-07}/`；范围=S1 裁决史+.bak 族+`.omc` 全目录+S2 基线+S3 状态类（含 aligned_checkpoints 135M）+明文 `.env`×5+git 现场留证+未跟踪脚本快照；明示出备 daily_pred/.git/logs
- **通道定型（两次踩坑）**：① 远端 WSL 无 rsync（实测只有 tar/md5sum）→ tar-over-ssh；② 复合命令引号被 sshd→cmd→wsl→sh 链路吃掉（rsh_block 探针实证拆坏）→ **远端单命令铁律** + 绝对路径清单 `md5sums.remote.txt`（`md5sum -c --quiet` 单命令可跑）；tar `--owner=0 --group=0` 远端全档 root:root
- **验证全绿**：远端 `md5sum -c` 全量通过；独立抽查本地↔远端 md5 一致（aligned_verdicts.jsonl）；`.env` 系列远端 `-rw------- root root`；MANIFEST 记录源 HEAD ca4a3b9
- **部署与自动化**：`/home/abug/bin/{backup_data_assets.sh,safe_clean.sh}`（755）；cron `15 2 * * *` 已装（原 crontab 备份 `~/crontab.backup.20261007`，与既有 17:45/周六 02:35 拉取无时序冲突）；safe_clean 活仓 dry-run 零保护路径命中
- **禁令入册**：AGENTS.md 新增「数据资产与清理禁令」节（裸 `git clean -xdf` 禁止）；runbook 新增「数据资产备份与清理」节（备份范围/恢复步骤/单命令铁律）
- **rclone 第二异地层**：脚本内置，本机未装 → WARN 跳过（Q2 裁定默认层，待宿主 S3 端点+密钥，装 rclone 配 remote `timesfm-backup` 即自动生效）
- **过程事故留痕（无害）**：一次经 PowerShell 向 wsl 传复杂 heredoc 时引号被拆坏，changelog 内容的反引号被 bash 当命令替换执行——触发一场计划外备份（幂等设计兜住，daily/2026-10-07 原位刷新）+ safe_clean dry-run（只读）；cat>> 因 heredoc 语法错误未写入任何内容。教训固化：**复杂内容一律 write/edit 工具 UNC 直写，禁走 PowerShell 命令行**（本会话工作规则第 2/4 条的实证补强）
- **计划同步**：§2.2 按裁定+实测重写 / §2.4 验收勾选（3 项过、2 项观察期/待端点）/ §2.5 实施记录新增 / §9 §10 批次 0+1 行更新
- **解锁**：事项一（§6.4 五步）实施开工条件达成——下一步 rebase tech-debt 分支到最新 master 后 TDD 实施
