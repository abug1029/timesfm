# 三环运行成果报告：v4 协议重启至收割修复验证
> **代码基线**: `1c6222a`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

- **报告日期**：2026-10-03
- **覆盖窗口**：2026-10-01 11:09（v4 重启）→ 2026-10-03 09:33（约 46h，含 1h22m 维护停机）
- **协议指纹**：v4 `f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5`（全窗口未变）
- **关联文档**：
  - 计划 `docs/superpowers/plans/2026-09-30-v4-convergence-implementation-plan.md`（任务 2.9）
  - changelog `docs/superpowers/changelogs/2026-10-01-v4-stage2-done-stage3-start.md`
  - spec `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15 §4.3 W3 / §4.6 / §1.4）
  - 重启档案 `docs/supervisor_restart_backlog.md`

## 一、数据源（可复核）

| 用途 | 文件 |
|---|---|
| 裁决唯一家 | `task_FM/config/aligned_verdicts.jsonl` |
| 收割/复测/慢环决策账 | `.omc/supervisor_decisions.jsonl`（`action` 键；**注意** `data/cache/supervisor_events.jsonl` 是另一套 `event`/`level` 事件流，收割账不在其中） |
| 进程生命周期 | `data/cache/supervisor_events.jsonl` |
| 队列三态 | `data/cache/aligned_pending{,.inprogress,.done}.jsonl` |
| 基线 | `task_FM/config/baseline_points_{sym}_nocov.jsonl` |
| 运行时输出 | `data/cache/supervisor.out`（本次窗口轮转为 `supervisor_pre_restart_20261002_202719.out`，1,498 行） |

## 二、总体战果

| 指标 | 数值 |
|---|---|
| v4 裁决 | **44 条**（registry 232 行 = 188 跨协议旧行 + 44 v4） |
| gate_pass=True | **13/44（29.5%）** |
| DM 单侧 p<0.05 | **2 条** |
| fdr_pass=True | **1/44** |
| FDR 累计晋升 | 阶段① 23 个 ·阶段② 21 个 |
| horizon_known=known_ahead | **3/44**（cf/fu/cj 的 calendar_cyclical） |
| 基线 | 9/9 品种 × 588 行 × v4 指纹，**全窗口零重生** |
| 提案存量 | 2,582 → 3,592（+1,010） |
| run 目录 | 189 |
| cycles_done | 178 → 203（+25） |
| 停机 | 2026-10-02 19:05:40 干净退出（`signal_received`, `exit_code 0`, uptime 114,956.8s） |
| 重启 | 2026-10-02 20:27 **PID 416**（SID 416 自有会话，PPID=`/init`） |

## 三、核心发现与修复验证（本报告的主要结论）

### 3.1 现象：收割枯竭

阶段① 后半程连续 **9 轮 `harvest_empty`**（0 入队），入队量呈衰减 3→3→3→3→3→3→3→**1**→**1**，每轮可用候选从 44 跌至 0（`seen - rejected` 转负；负值系 `backlog_dup` 与 `rejected` 双计的记账小差，实质为 0）。

### 3.2 根因：收割门用了跨协议旧代快照

- 代码事实：`scripts/praxist_supervisor.py` 的 `_harvest_rows` 调用 `rl.load_snapshot(REGISTRY)`，**未带 `only_protocol`**；而 `build_snapshot` / `pass_variants` 已按方案 A 采用协议过滤视图。
- 机制：`_has_prior_failure(snapshot, symbol, cov)` 按 **(symbol, cov)** 配对（非 vid），故被 v4 波作废的 188 条旧代裁决仍在压制新提案；叠加 `_proposal_quality_gate` 的 −20（协变量跨品种近期全失败）/ −15（品种近期全失败）惩罚被 v4 波喂满（17/23 gate_pass=False）。
- 主导拒收原因：`no_failure_delta` **2,384 份**（占 seen 的 ~75%，要求重提组合须附 `failure_delta` ≥20 字改进说明，而磁盘提案语料多数早于该要求）。

### 3.3 A/B 对照实测（同门链、只换快照口径，只读复刻真实 helper）

| 快照口径 | 快照行数 | `no_failure_delta` 拒 | **可入队候选** |
|---|---|---|---|
| A 修复前（未过滤） | 199 | 1,854 | **7** |
| B 方案 A 口径（v4 过滤） | 22 | 1,178 | **134** |

→ 同一提案池，正确口径下每轮多 **127 个**候选机会，覆盖 14 个品种。

### 3.4 修复（对方 agent `045c7e2`）与生产验证

修复引入 `_active_protocol_snapshot()`：收割与复测只看当前协议，无指纹/旧指纹留jsonl 不参与拒绝或复测。

**阶段② 首轮收割即入队 3 行**（对比阶段① 连续 9 轮 0 入队）。

| 指标 | 阶段① 修复前（32h） | 阶段② 修复后（13h） |
|---|---|---|
| 收割轮入队率 | 9/18 = **50%** | **7/7 = 100%** |
| 每轮可用候选 | 44 → 10 → **0** | **123 → 67** |
| `no_failure_delta` 拒收 | 2,384 | **1,226** |
| 裁决产出速率 | 0.72 条/h | **1.62 条/h** |
| FDR 晋升 | 23 个 / 9 批 | 21 个 / 7 批 |

**吞吐提升 2.3 倍，入队率恢复至100%。**

> 该风险模式在代码注释中已被预警过（`praxist_supervisor.py` 板块过滤处：「与 2026-09-24 no_failure_delta 饿死同构」）。板块过滤装了 circuit-breaker，这道门当时没有，本波被v4 波重新触发。

## 四、过门变体榜（13 个，按 dir_acc）

| variant | dir_acc | p_value | horizon_known |
|---|---|---|---|
| `cf_calendar_5bd18d23ae63` | **0.576** | None | **known_ahead** |
| `sh_momentum_3bd3de5a6fd8` | 0.564 | None | persistence |
| `sh_momentum_f8bc3e69c749` | 0.550 | None | persistence |
| `cf_volatility_480314cc2384` | 0.544 | None | persistence |
| `i_inventory_1bc2bfa3aea7` | 0.542 | None | unknowable |
| `cf_momentum_9559380178e0` | 0.540 | None | persistence |
| `p_inventory_bf6661363084` | 0.531 | None | unknowable |
| `jd_momentum_9d8acd820fc8` | 0.528 | 0.157 | persistence |
| **`m_momentum_b06ddbcd88e3`** | 0.515 | **0.0236** | self_referential |
| `ss_volatility_1d59dee016a4` | 0.515 | 0.484 | persistence |
| `jd_momentum_db87a4341c10` | 0.511 | 0.182 | self_referential |
| `jd_inventory_a44d2d7f27cb` | 0.503 | 0.222 | unknowable |
| `lh_momentum_7c99f56aba69` | 0.500 | 0.109 | self_referential |

**品种扩散**：cf 3 / lh 3 / sh 2 / jd 2 / m 1 / ss 1 / p 1 = 7 品种（较阶段①的 6 品种新增 i / p / cf）。
**family 覆盖**：momentum / volatility / inventory / **calendar** 四族。
**DM 显著（p<0.05）两条**：`m_momentum_b06ddbcd88e3`(p=0.0236)、`lh_momentum_8c75bd7b917f`(p=0.0374, dir=0.531, gate_pass=False)。

## 五、运行态快照（2026-10-03 09:33）

| 项 | 值 |
|---|---|
| supervisor | PID 416，存活 13h06m，CPU 2.8%，SID 416（会话无依赖持续成立） |
| 快环 run | PID 28520（09:26 发起，在跑） |
| 相位 | `phase=fast`，心跳 `2026-10-03T09:31:18` |
| 队列 | pending 0 / inprogress 0，7 批全部 `slow_drain_complete` |
| 协议物化 | `active=26/203 fp=f02b2a43…`（排除 v3 18 + v2 16 + legacy） |

## 六、运行期事件档案

### 6.1 WSL VM 回收事件（阶段①）
PID 393 于重生波中途（eg 201/589）被 WSL VM 回收击杀：无traceback、无 Windows 睡眠事件、VM 10:32:46 重启。重跑 launcher幂等续跑（cj 持久化跳过）→ **重生波可恢复性获生产实证**。

### 6.2 SIGTERM 首次被忽略（阶段① 收机）
19:0x 首次 SIGTERM 后 supervisor **继续收割并发起新 run**，180s 未退出，与既有规程「约 90s 干净退出」不符；第二次 SIGTERM 生效（约 35s），最终 `exit_code 0`。**信号处理路径待复核**（一次忽略 + 期间继续产出，疑似 handler 与主循环竞争）。

### 6.3 重启加载的新代码（对方 agent，10 笔）

| commit | 内容 | 对应阶段 3 清单 |
|---|---|---|
| `eee38fb` | 确认窗口 + checkpoint 命名空间隔离 + family 分派接线 | B |
| `f687fcf` | underpowered 成员可封账 + DM 字段映射 | B |
| `05cb8f4` | 确认窗口保持开放至预定样本填满 | B |
| `9c08c1a` | 用确认分层 + 有限预算替换 0.51 goal | C |
| `53f0899` / `b79f93a` | 测试对齐 + sealed confirmation 计数修复 | C |
| `34fedcb` | 注册首批两个确认假设 | D |
| `045c7e2` | **收割/复测只看当前协议** + token 预算可解除 | 收割修复 |
| `b745831` | 记录 oi_gated_ha_body backlog 提案 | — |

预注册首批（`task_FM/config/preregistry.jsonl` 2 行）：jd `daily_slope+vor` n_confirm_required=1,199；sr `daily_slope+vwap_deviation` n_confirm_required=986；`confirm_from_ts=2026-10-03 00:00:00`（固定日历边界，注册时锁定）。

## 七、未解缺口

1. **确认级产出 = 0（符合设计，非故障）**：44/44 为 `run_mode=exploration`；活跃视图 `passing=0`。两条 p<0.05 候选的 `pairing_valid=False` 且 `missingness_admissible=False`（§7.8 裁定前保守默认），按 W3.4 不可确认。确认通道需累积 986–1,199 个新 cutoff（约 1.2–2.0 年）。
2. ~~**`star` 字段 44/44 为 None**：评级链在 v4 行未产出，与 `gate_pass` 判定脱节，跨两夜未解。~~
   【勘误 2026-10-03】**该表述不成立**：`star` 键在 v4 44 行与旧代 188 行中**均不存在**（并非"未产出"）。
   真实评级由 **`tier`** 承载（`cascade/tier_classifier.py:133`），v4 分布 S6/A6/B21/C11，过门行 S6/A4/B2/C1。
   `star` 是未使用的遗留字段名（`--three-star` 系历史 CLI 名，现映射"信用≥2星"）。
   详见 `docs/superpowers/reports/2026-10-03-fm-a-open-issues.md` §4。
3. **两条 DM 显著候选的协变量均 `self_referential`**：`m_momentum` / `lh_momentum` 自指类协变量需 known_ahead 或等价论证才能进入确认集。**`cf_calendar_5bd18d23ae63`（dir_acc 0.576、known_ahead）是当前唯一同时满足过门 + 前视安全的组合**，是最值得追加预注册的候选。
4. **`family_dead` 曾拒 602 条**：v4 仅 44 条裁决时即有多个 family 被判死（4+ 评估全败），建议复核 `_dead_families` 的最小样本要求，避免新代样本尚小时过早判死。

## 八、遗留待办

| 项 | 说明 |
|---|---|
| 测试红 2 处 | `test_maybe_enqueue_retests_gating_and_dedup`（fixture 裁决缺 `protocol_fingerprint`，被新的协议过滤正确排除）；`test_no_unaccounted_modules`（一次性脚本 `scripts/write_first_preregistry.py` 已执行完但零引用未挂账）。均为测试侧，不影响运行时 |
| SIGTERM 首次被忽略 | 复核 supervisor 信号处理路径 |
| 收割配额 | 瓶颈已从门链拒收转为每轮 `top_k=3` 配额；候选 123→67 的下滑随裁决累积需观察 |
| 确认集激活 | 两条预注册自 2026-10-03 起累积，按 live 密度预计 jd 约 2.0y、sr 约 1.2y |

---
*报告生成：2026-10-03 09:33（数据取至该时刻）*