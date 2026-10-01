# FM_a 系统状态

> **canonical_state 声明 (2026-09-01, P0b)**：本文件是系统状态的**唯一事实所有者**。
> `reports/` 全部为 derived_view（可从 `predictions.json` / 回测 JSONL / db 产物重建），
> 冲突时以 **STATE.md + 磁盘回测产物**为准。此规则用于终结"滞后文档事故"（如 SH 状态那次）。

**最后更新**: 2026-10-01（v4 收口阶段 2 完成并重启：窗口锚 / checkpoint 身份 / 协议 v4 / vid 生产接线全部落地，v4 重生波 9/9 闭环。见下方「三环状态」与「Stage 3 交付状态」小节）

> **三环状态**：**运行中**，supervisor **PID 418**（2026-10-01 v4 重启，已加载 v4 收口全部代码）。
> `cycles_done` / PID / phase 是**活计数**，此处一律不记录 —— 读 `data/cache/supervisor_state.json`。
> 封存已于 **2026-09-28 解除**（停滞根因 = 快环提案被门禁 ~100% 拒绝 + 无基线 → 慢环饿死；
> 修复 = baselines 重生 + 提案门禁调整 + 1-bar 前视修复）。封存快照仍在
> `data/archive/fm_a_sealed_2026-09-24T1422/`（234MB）供对照，非当前状态。
>
> **v4 重启已执行**（2026-10-01，计划 2.9）。旧 PID 670 由宿主停机（日志已轮转
> `logs/supervisor_pre_restart_20260929.log`）。新代码生效的端到端证据：
> `protocol_fingerprint` **v4 = `f02b2a433fd572ea…`**，ensure_baselines 重生波 9/9
> （cj/eg/fu/jd/lh/m/rb/sr/ss 全带 v4 指纹；fu 为入集后首个有效基线），
> 活跃视图干净（188 旧行 = 143 legacy + 27 v2 + 18 v3 全排除，passing=0/dead=0），
> 首 tick 收割入队 vid 已是新格式（`{symbol}_{family}_{fp12}`，2.4 生产首验）。
> 执行记录见 `docs/superpowers/plans/2026-09-30-v4-convergence-implementation-plan.md` 执行日志。
**Phase 1 状态**: **L1 ops 全量完成 → ECONOMIC_PASS=False → 生产 REMAIN_OFF**  
**人类文档**: `docs/README.md`（含 product_positioning / module_freeze / 新口径全表链接）  
**冲突债**: `reports/research/20260808_conflict_debt_register.md`（绝大多数 DONE）  
**Ultragoal**: `20260808-tradable-alpha-debt` 完成；可交易 alpha **6.7/10**  
**新口径 monthly 20/20**: 全表 `reports/research/20260808_g005e_results.md`；最新批次报告 `monthly_backtest/20260808_2249_monthly_report.md`  
**信用档**: **无 3 星**；≥2★ = CJ/SS/SR/M/JD/LH + EG/RB（8 品种）；`--three-star` CLI = `list_by_stars(2)`  
**G004 (2026-08-17)**: P 固化 `rsi_state+reversal_shadow`（v2 GREEN-EV，PF=1.014，保持 1★）；BU 不固化。见 `reports/research/20260817_g004_verdict.md`  
**Phase 11 (2026-08-21 结案)**: 单协变量穷举 138 作业全完成，34 GREEN，12 品种协变量替换固化，M/P/SR 基线验证保持。详见下节。  
**Phase 12 (2026-08-21)**: BU 组合协变量 `calendar_cyclical+hourly_slope` 固化（PF=1.01 边际 GREEN，替换 ha_body）。
**Phase 13 (2026-08-22 结案)**: 弱信号品种组合探索 18 tests, 0 GREEN, 天花板确认。暂停协变量优化。
**Phase 15 (2026-08-23 结案, 2026-08-23 审核修订)**: 4 个全新维度协变量 (NVI/QSTICK/VWAP/StdDev) × 6 弱信号品种 = 24 tests, 0 GREEN, 全面弱于 baseline。**本次搜索的 4 个新协变量均未达标**(非"路径彻底穷尽",详见 §Phase 15 章节)。  
**Phase 15b (2026-08-29)**: StdDev 改 returns std **保留**（5/6 改善，AO PF +0.14；UR -0.11 例外退化待复评）；VWAP 衰减填充**回滚**（0/6 改善）。详见下节。  
**Phase Q1 (2026-08-29 结案)**: 协变量实现质量审计 6 方向裁决：D1 RSI 自适应 **REJECT**（JD -0.02 / P combo -0.10；信息量↑≠预测力↑，固定边界 91% 零输出=隐式信号门控）；D2/D4 CANCEL；D3 SKIP；D5 PAUSE；D6 审计框架 **ACCEPT**（`tests/test_covariate_audit.py` 19 测试）。实验性协变量代码已从 features.py 移除。SCHEMES 无变更。详见下节。
**MaxDD>100% bug (2026-08-30 闭环)**: 已于 2026-08-21 修复 (`cascade/evaluation_metrics.py` cumprod+clamp) 并 8 测试覆盖；-265%/-134% 为修复前旧口径 (batch_f1 2026-08-18)，Phase 11 裁决以 PF 为准不受影响。
**PRAXIST (2026-09-24 时点，三环当时封存；封存已于 2026-09-28 解除，见顶部声明)**: 此前的方案 A 三环进展：9/19 改进：failure_delta 硬门 + DEAD/HOLD 过滤 + fm_two_peer topology + 提案质量加固（84 tests）。9/20 改进：跨 run 重复惩罚 + DEAD 族拒绝。9/22 落地 **TypeSafe Jev 协变量预筛**（软建议模式：harvest 时三问判读 → `_proposal_priority_score` ± 调度分，不阻断慢环；质量门禁 50 样本）。2026-09-29 实际为 171 verdicts / 43 gate_pass=true（`cycles_done` 等活计数见 `data/cache/supervisor_state.json`；171 条历史裁决均无 prescreen metadata 与 A1 字段）。人类概览 `docs/praxist.md`；运维 `docs/runbook_praxist_three_loop.md`；机器状态 `data/cache/supervisor_state.json`；裁决 `task_FM/config/aligned_verdicts.jsonl`。



## Stage 3 交付状态（2026-09-29 结案）

> **原「进行中」记录保留在下方各小节**，但整体状态已变：spec v15 的 §8.3 八项出口
> 条件全部核验通过，Phase 1-10 于 2026-09-29 实施完毕（commit `381f31e`），
> 并经第六、七轮独立审计。**下方「当前阻塞点 / 待执行」描述的是 2026-09-28 的时点。**

### 交付摘要（2026-09-29）

| 项 | 状态 | 位置 |
|---|---|---|
| PR-C1 功效/门槛公式（`detection_threshold_*` / `n_required`） | ✅ 交付 | `cascade/statistical_tests.py` |
| PR-C2 研究 family + 封账 + BH-FDR + `T_max` | ✅ 交付 | `cascade/research_family.py` |
| PR-C6 horizon 契约（W5.2 归一化） | ✅ 交付 | `cascade/horizon_fill.py` |
| PR-A5 `protocol_fingerprint` v3（七组件） | ✅ 交付 | `task_FM/evaluations/fm_eval/evaluator.py` |
| PR-B1 `experiment_fingerprint` | ⚠️→✅ 模块就绪，真接线已完成（2026-10-01 `c0e3aa4`） | `cascade/experiment_fingerprint.py` |
| §8.3 出口条件核验记录 | ✅ | `docs/superpowers/reports/2026-09-29-stage3-verification-record.md` |

**测试**：`1646 passed / 7 skipped / 1 xfailed / 0 failed`。基线 eecf05a 的 14 项预存在
失败中 13 项由 Phase 9 修复，第 14 项（a2_p1 smoke）于 `b8a6d36` 退役。

**未做**：PR-D1 / PR-D2（Stage 4 正式）、supervisor variant_id 接线、
supervisor 重启（用户保留决定）。
**→ 2026-10-01 更新**：后两项已完成——variant_id 生产接线（commit `c0e3aa4`，计划 2.4）、
supervisor v4 重启（PID 418，计划 2.9）；PR-D1/PR-D2 = v4 计划阶段 3，待启动。

---

## Stage 3 协变量可信度重构（2026-09-28 时点记录，已结案）

> 上游 spec：`docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（**v15**，2026-09-28 修订）
> 计划：`docs/archive/superpowers-plans/2026-09-28-covariate-credibility-stage3.md`（已归档）（v5）
> 审核汇总：`docs/superpowers/reports/2026-09-28-stage3-review-summary.md`

**目标**：把 Stage 1/2 的降级声明解除；让协变量可信度从「推断」变成「可验证事实」。

### 已完成

| 任务 | 状态 | 关键提交 |
|------|------|---------|
| **T1a** nocov 基线重生 + registry 复活 | ✅ 完成（8/8，指纹正确） | `d621a1a` (D5) + `6c94275` (PR-A1) + `d4e7097` (ensure_baselines 指纹校验) |
| **T3** PR-B4 dir_acc 口径改档 | ✅ 文档 + 实施完成 | `2d38839` + `12e0850` + `ac979ef` + `4e092f1` (PR-B4 实施) |
| **T4** 审计集 fu 加入裁定 | ✅ 已追认 | `7d74c76` + `aa48aa6` + `ac979ef` |
| **T5 PR-C3** n_eff 实测 + meets_min_info | ✅ 实施（14 测试） | `8a772f9` |
| **T5 PR-C4** 门槛一致性 + 历史修订防护 + 预训练登记 | ✅ 实施（9 测试） | `f3552ee` |
| **T5 PR-C5** 协变量族诊断矩阵 | ✅ 实施（7 测试） | `9cef27e` |
| **T5 PR-C6** horizon_known 分类系统 | ✅ 实施（7 测试） | `d30cb1a` |
| **T6** PR-B1 接线 + Stage 2 登记小项 | ✅ 13 项评审登记闭环 | `e6c9760` |
| **T7** 板块部分退化 WARN | ✅ 实施 | `5dde4dc` |
| **M4** T1a 判据验证脚本 | ✅ 实施（42 测试） | `59c7d3b` + `f754762` |
| **spec v15** 三处结构性修订 | ✅ | `ac979ef`：① 字段改名 `n_total`/`n_active` → `n_dir_total`/`n_dir_active`；② 审计集规模 2–3 → 7 品种；③ §4.5 W5.5 horizon_known 裁定记录 |
| **R2+R5** STATE.md 刷新 + 审核汇总工件 | ✅ | `d67f85d` |
| **快慢环集成** | ✅ 修复 | 快环提案未入队 → `enqueue_fast_loop_proposals.py`；`eval_slots.lock` 残留阻塞 |
| **T1b** 手算核对预测点 | ✅ 通过 10/10 | `bade177`；首轮 3/10「不一致」经溯源为核对脚本口径误用 |
| **T2** 三路消融实跑 | ✅ 完成 16 裁决 | `5ed59f2`（消融接线）+ `0609e88`（对照表） |
| **消融模式接线** | ✅ 修复 | `aligned_slow_loop.py` 透传 `ablation_mode`（实测原为 0 引用） |

### 当前阻塞点

**T1a 判据 A/B' 待新裁决流**。基线已就绪，但慢环尚未产出首批 A1 完整裁决。
判据 A/B' 验证脚本就绪：`scripts/verify_t1a_criteria_a.py`，退出码 `3` = NO_NEW_VERDICTS（当前状态）。

### 待执行

| 任务 | 依赖 | 预计 |
|------|------|------|
| **T1a 判据 B' 重验** | 基线覆盖扩至 09-28 后 | 待基线重生 |
| **T2 扩样** | `max_points` ≥100 重跑消融 | 后续批次 |
| **checkpoint 口径字段** | Stage 4：增补 `delta_pred_endpoint` | 阶段 4 |
| **T2 扩样后的重验** | `max_points` ≥100 重跑消融 | 后续批次 |

### 本轮自查修正的过度推断（2026-09-28）

| 位置 | 初稿论断 | 修正后 |
|------|---------|--------|
| T2 报告 §3 | structural ≡ baseline 差异 0 → 验证消融实现正确 | pred_end 实测不同（3052.26 vs 3049.53），差异 0 是 n=6 下 dir_acc 二值粒度的假象 |
| T2 报告 §2 | full 劣于 baseline → 协变量有害 | 降级为「本样本未观察到 full 优于 baseline」，6 点均值无误差估计 |
| `t2_ablation_report.py` | 只按 dir_acc 唯一值数判「输入是否改变模型」 | 改 dir_acc + endpoint_mape 双指标，修正后 4/4 组均可区分 |
| T1b 报告 | 首轮报「3/10 不一致」称真实 bug | 溯源为核对脚本用错字段（信号口径 vs 端点口径），生产代码无误 |

**教训**：n 小时二值计数指标（`dir_acc` = k/n）会掩盖连续输出的差异，
不可单独用作「路径是否相同」的判据。`t2_run_ablation.py` 已按此在
variant_id 中带模式后缀，但判定逻辑需双指标交叉验证。

### 三路专家审核结果与修复（2026-09-28）

三路独立审核（统计核心 PR-C3/B4、接线配置 PR-C4/C6/T2、T1b/T2 方法论）
全部返回 REQUEST CHANGES。逐条**独立复核后**修复，未凭审核转述即改。

**审核报出、经复核成立（4 项阻塞）**

| # | 问题 | 证据 | 修复 |
|---|------|------|------|
| 1 | HAC 估计量不共用（spec §4.1 W1.2 明文禁止） | `compute_hac_se` 分母 `n-j`，`diebold_mariano_p` 分母 `T` | 统一 Newey-West 约定，DM 直接调用 `compute_hac_se`；加契约测试锁死 |
| 2 | `gate_basis` 键冲突 | 实测 3 个既有 gated 测试失败 | 拆为 `threshold_basis`，`gate_basis` 恢复原词表（active/full_fallback） |
| 3 | `context_hash` 生产上恒为 None | 实测 checkpoint 逐点**无** `context_window` 也无 `real_endpoint`，只有 `real_end`（未来真值） | 改为写入点就地算 480 根 1H 收盘摘要；拿不到就诚实返回 None |
| 4 | `estimation_failed` 死代码 | 全仓无分支产出该状态 | 按 spec 边界表重建 `VALID_ESTIMATE` |

**仅读 spec 才发现、审核未报（2 项）**

| # | 问题 | 证据 |
|---|------|------|
| 5 | 状态名与 spec §4.1 边界表不符 | 我写 `clipped_to_iid`，spec 钦定 `hac_nonpositive_clamped`；spec 另把「n_eff > n 夹取」单列为 `clamped_to_n`，我并进了 `ok` |
| 6 | `data_revised` 恒写 `False` | 把「没查过」伪装成「查过且未修订」，改为 `None` |

**审核 C 发现我自己报告里的 2 处事实错误**（已从 checkpoint 独立重算确认）

| 位置 | 我写的 | 实测 |
|------|--------|------|
| T2 报告 §2 | 「四组中 `full` 的 mape **均为最差**」 | jd 2 组成立；**rb 2 组 `structural` 更差**（1.014/0.925 > 0.950/0.903）|
| T2 报告 §3 | 「路径差 4 组**均为 0.0000**」 | jd 2 组是 **+0.1667**；只有 rb 两组是 0 |

第 2 条尤其值得记：我写那段话的动机是「差异 0 不能证明路径一致」，
但**前提数字本身就错**——我连自己表格里的数据都没读对。
另补充披露：4 组只有 **2 个独立品种**，且这 2 个方向相反，
「4/4 组方向一致」把 2 个独立实验当 4 个计，系统性夸大证据强度。

**审核建议但复核后判定不成立**

- 审核 A 称 `estimation_failed` 会让不可判定序列通过信息门 —— 不成立：
  该状态约定 `n_eff = None`，而布尔式已有 `n_eff is not None` 前置守卫。
  属死代码，非漏洞。仍按 spec 清理。

**教训（本轮新增）**

1. **审核的断言也必须复核**。审核 A 给的黄金值 `3.555664` 与我手算的
   `2.6667` 冲突，我一度以为审核错 —— 实为我漏了平稳方差因子
   `1/(1-ρ²)=1.3333`。用蒙特卡洛定谳后才写测试。
2. **Windows UNC 路径读到的是过期副本**。`\\wsl.localhost\...` 下 grep
   在 `cascade/` 零命中，而 WSL 内 grep 命中正确行号。代码审查一律走
   `wsl -d Ubuntu-22.04 -- bash -c`。
3. **"先读 spec 再信审核"**：审核未报的 2 项（状态名、`data_revised`）
   只有对照 spec 边界表逐字核对才发现。

### PR-C6 未完成项与待裁定冲突（2026-09-28，**阻塞 W5.2**）

第四路审核（`horizon_known` 领域审核）报出 PR-C6 **只交付了 1/3**。
已逐条独立复核（含可执行探针），结论如下。

**① PR-C6 范围缺口（确认）**

plan 的 P2 表把 PR-C6 文件范围列为
`covariate_pool.json, features.py, hourly_model.py`。实测：

| 文件 | `horizon_known` 引用数 |
|------|---------------------|
| `cascade/features.py` | **0** |
| `cascade/hourly_model.py` | **0** |

即 spec W5.2（按标签分支填充）、W5.3（前视不变量，**spec 自述"安全关键项"**）、
W5.5③（加载时断言 `known_ahead` iff 走 known_ahead 填充路径）**全部未实现**。
`horizon_fill` / `horizon_std` / `horizon_exogenous` 三个字段也不存在。

**当前定性**：`horizon_known` 是「只校验、不生效」的字段 —— 它不改变任何
数组，故**当前不污染任何实验**，但也**不提供它承诺的任何保护**。
危险在于它是定时炸弹：W5.2 一旦落地，标签会立刻决定填充行为，
且 spec L1031 明确「W5 落地后历史 verdict 不可与新 verdict 比较」。
**正确顺序：先修标签 → 再解禁令 → 最后才接线 W5.2。**

**② 宿主裁定 vs 代码的冲突（**需宿主二选一**）**

spec W5.5① 是**宿主裁定**，点名 `rsi_state` / `hourly_slope` 为
`self_referential`，理由写作「horizon 尾值取自 TimesFM 自身日线输出」。

**该理由被代码证伪**（可执行探针，非阅读推断）：

| 协变量 | 代码位置 | horizon 实际构造 | 探针结果 |
|--------|---------|-----------------|---------|
| `rsi_state` | `features.py:1047-1048` | `_generate_rsi_state_horizon(last_ctx_state)` — context 末态衰减 | 把 `predicted_daily_closes` 扰动 ×1.5+30 **→ horizon 逐值不变**；末态=2.0 时 horizon=`[2,2,1,1,0,0,…]` |
| `hourly_slope` | `features.py:1227` | `np.full(horizon, last_valid)`，`last_valid` 取自 **1H 收盘价** | 注释自述「短期动量延续假设」 |

`_build_rsi_state_from_daily` 的 docstring 自述：
> 「predicted_daily 参与全日 RSI 计算，**但不映射到 context**；horizon 从
> context 末端连续衰减，避免用远期预测状态在边界跳变。」

即代码在某次修改后已不再是「取自模型输出」，而 spec 的举例未同步。
按 W5.1 的**定义**（`self_referential` = 未来值来自模型自身输出），
二者应归 `persistence`（末值延续近似）。

**但不得由 agent 单方面改判**：这是宿主裁定，且
**影响面有限** —— `self_referential` 与 `persistence` 在 W5.2 下
**填充行为完全相同**（都是「填末值」），「是否算外生信息」也都是 ❌。
差别仅在标签的语义准确性。

**③ `calendar_cyclical` 的 `known_ahead` 资格（**需宿主裁定**）**

spec 自身矛盾，两个条款指向相反结论：

| 条款 | 内容 |
|------|------|
| W5.5① | `calendar_cyclical` = `known_ahead`（**有条件**）：核验判据「公告时间戳 ≤ cutoff」 |
| W5.1 | 「交易所**临时调整**（临时更改交易时段、临时休市、夜盘调整）→ **不是** known_ahead，除非当时已公告；默认按 `unknowable`」 |
| W5.5② | 「**不可追溯补填**」「历史已注册条目缺证据 → 降级 `unknowable` + WARN」 |

实测事实：
- 构造源是 `detect_trading_hours`（`data_validator.py:562-581`）= **从历史 1H 数据统计每小时频率反推**，不是交易所公布日历
- W5.5④ 要求的 `announced_at` 公告时间戳：全仓 **grep 零命中**，核验规则未实现
- `calendar_cyclical` 的 `track_record: "v22线索"` 说明是历史注册条目，
  而 `add_horizon_known.py` 于 2026-09-28 一次性补填证据 → 与 W5.5②「不可追溯补填」冲突

**必须向宿主明示的后果**：若按 W5.1 降级为 `unknowable`，
**全池 `known_ahead` 归零** → W5.4 验收条件「至少一个 known_ahead 协变量
满足 `horizon_std > 0`」**必然失效**。这不是 agent 能替宿主做的取舍。

**④ 已修复（不涉及裁定的部分）**

`tests/test_prc6_horizon_known.py` 原有两个测试把**争议中的标签分布**冻死：

| 原测试 | 问题 | 处置 |
|--------|------|------|
| `test_no_persistence_in_current_pool` | 断言池内**任何**协变量不得标 `persistence`。而 `persistence` 是 spec 受控词表的合法值，且语义上恰好是 persistence 的协变量会被挤进别的标签 —— **测试把唯一正确的标签堵死了** | 改为「取值须在受控词表内」 |
| `test_horizon_known_distribution` | 断言 `self_referential >= 10` / `unknowable >= 5` / `known_ahead >= 1`，冻住争议分布，一旦修正标签即假失败 | 改为覆盖性断言 |

**⑤ 回测前视问题（**新发现，需宿主裁定**）**

修复 context_hash 对齐时（`ecd0260`）意外发现：**模型输入含一根
cutoff 之后才收盘的 bar**。

证据（RB idx=8798）：

```
dt[idx]   = 2026-01-09 10:00   （dt 是 bar 开盘时间）
cutoff    = 2026-01-09 11:00   （bar idx 收盘时间，D5 修正后）
dt[idx+1] = 2026-01-09 11:00   ← 恰等于 cutoff

BacktestDataStore.get_main_contract_1h 的 SQL: dt <= cutoff_ts
  → 纳入 dt == cutoff 的那根，即 bar idx+1
  → 其收盘于 12:00，**晚于 cutoff**
```

而预测目标是 bar idx+1..idx+HORIZON —— 即模型**已经看过**它被要求预测的
第一根 bar 的收盘价。

`dt` = 开盘时间由两条独立证据确认：夜盘只有 21:00/22:00 两根、无 23:00
（若 dt 是收盘时间则必有 23:00 根）；相邻 bar 前收 == 后开。

**归因**：D5（`d621a1a`）把 cutoff 从开盘时间改为收盘时间，但**未同步
`data/data_store.py` 的 `dt <= cutoff_ts` 边界**（该 commit 未触及
data_store.py）。正确边界应为 `dt < cutoff_ts`。

**影响面**：所有走 `BacktestDataStore` 的回测 —— 即 Stage 1–3 的
全部结果。但注意 `max_points` 与 `eval_start` 逻辑不受影响，
`base`（= bar idx 收盘价）取值正确，受污染的只有模型输入的最后 1 根。

**未处置理由**：改动会再次改变全部 cutoff 语义 → 配对交集、DM 序列、
协议指纹、nocov 基线全部需要重跑（与 D5 的影响相同）。这是宿主决策，
不在本轮自行处理。**已在此登记，未静默。**

> **2026-09-28 更新：已修复**（commit `968945f`）。
> 新增 `BacktestDataStore._h1_upper_bound()` = `cutoff_ts − 1h`，
> `get_main_contract_1h` 用它作上界；`monthly_backtest` 的 context_hash
> 切片同步收紧。实测 12/12 与模型窗口逐值一致且无泄漏。
> 测试零新增失败（1484 passed / 13 failed，13 项均为既有）。
> 契约测试 `test_midday_excludes_later_same_day_bars` 已更新并注明变更理由。
>
> ⚠️ **待办：全部 baseline 需重跑**。模型输入已改变，nocov 基线、
> 配对交集、DM 序列、协议指纹均会变化 —— 影响面同 D5。
> 在重跑完成前，**现有裁决与新裁决不可比**（protocol_fingerprint 应随之变化）。

**⑥ 其他已核实但未处置**（`scripts/add_horizon_known.py`）

- 降级时不删除残留 `known_ahead_evidence` → 陈旧证据零告警存活
- `CALENDAR_EVIDENCE` 是模块级常量按引用赋值 → 多个 known_ahead 会共享同一 dict
- `pool["updated"]` 硬编码日期，重跑永不更新
- 池内 `horizon_known_note` 称「其余三类 horizon 尾填末值」，而
  `oi`/`ccl`/`pca_momentum`/`oi_gated_momentum` 实际**全零填充**，note 与代码不符


### 宿主裁定（2026-09-28）

| 裁定 | 内容 | spec 位置 |
|------|------|----------|
| M3 | 重置 eg/jd/lh 为 ACTIVE | `symbol_status.json` |
| T3 字段改名 | `n_total`/`n_active` → `n_dir_total`/`n_dir_active` | spec v15 §4.7 W6.5 |
| M6 | 审计集规模 2–3 → 7 品种 | spec v15 §1.1 L2 |
| M5 | horizon_known 分类 + verified_by 白名单 | spec v15 §4.5 W5.5 |

### 关键数据

| 项 | 当前值 |
|----|--------|
| nocov 基线 | 8/8 就绪，协议指纹全部一致（`bd851c9ca0730dc5…` = protocol_v2） |
| registry | 143 条 pre-A1 遗留（无 `protocol_fingerprint`），等待首批新裁决 |
| 品种状态 | 8 品种全部 ACTIVE（M3 重置后） |
| 测试 | 320+ Stage 2 + 21 (M4) + 13 (ensure_baselines) + 14 (PR-C3) + 9 (PR-C4) + 7 (PR-C5) + 7 (PR-C6) + 10 (PR-B4) = 401+ |

### 已知代码缺陷（Stage 3 实测发现）

| 缺陷 | 状态 | 处置 |
|------|------|------|
| `ensure_baselines` 不校验协议指纹 | ✅ 已修 (`d4e7097`) | `_baseline_protocol_fingerprint` + `_current_protocol_fingerprint` |
| PR-C1 `close_family` 重复 D3 违规 | ✅ 已修 (`12e0850`) | 整节删除，唯一所有者改为 PR-C2 |

---

## PRAXIST 运行快照（2026-09-20 档；2026-09-24 封存时点）

> Praxist 的**机器事实所有者**是 `data/cache/supervisor_state.json` 与 `task_FM/config/aligned_verdicts.jsonl`，不是本文件。本节省人类交接。过期时以 JSON 为准。停机报告仍落 `docs/superpowers/reports/`。
>
> **v23 裁决口径声明 (2026-09-16)**：v23 纯预测质量重构已合入 master（含 2970837/70b75bf 文档治理）。Praxist 裁决口径以 v23 spec（`docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）为准：硬门 n≥350 / n_eff≥50 / dir_acc≥0.52（品种自适应）+ DM 检验（Newey-West HAC + HLN）+ BH-FDR（per-symbol）；verdict schema `fm.aligned_verdict.v2`。PF/EV/MaxDD/IC 退役出裁决链，仅作经济报表字段。本文件带日期历史快照（含旧经济指标数值）不回写；机器事实以 `supervisor_state.json` / `aligned_verdicts.jsonl` 为准。

| 项 | 值 |
|----|-----|
| 宿主 | WSL2 Ubuntu-22.04 `/home/abug/timesfm`，`.venv` (Python 3.11) |
| 合同 | 方案 A：peer 写假设，慢环唯一验证器 |
| 目标 | 1 星集合过门 ≥4（且独立过门变体 ≥4）+ min dir_acc > 0.52 + ≥1 族；`goal.yaml` 预算已 999999 / deadline 2099-12-31 |
| 监督环 | `phase=fast`，`cycles_done=36`，`paused_429=false`；PID 31638（commit `6035c8e`）；`last_run_id=run_2026-09-20_09-28-32_primary_task_FM`；`last_harvested_run_id=run_2026-09-20_06-34-49_primary_task_FM` |
| 裁决统计 | 105 verdicts（v2 schema），22 gate_pass=true（21%），0 fdr_pass=true；品种分布：eg 24 / cj 19 / m 13 / rb 11 / ss 7 / sr 7 / lh 7 / jd 7 / p 5 / sh 4 / i 4 / ma 2 / jm 2 / cf 2 |
| 硬门但亏钱（v22 历史） | v22 口径 `i_oi`/ev<0 等已退役；v23 硬门 = n≥350 + n_eff≥50 + dir_acc≥adaptive + DM + BH-FDR，不再引用 PF/EV |
| 品种状态（9/19） | eg=DEAD（22 ok, 0 pass）；jd/lh=HOLD（hold_generations=5）；其余 17 品种 active |
| n 口径 | 磁盘 396×21 / 588×3 / 324 / 142。396=旧网格或 `max_points` 截断；588≈现行理论 589；600=goal 上限；350=硬门阈值 |

重启命令见 `docs/praxist.md` §4 或 `docs/runbook_praxist_three_loop.md`。

---

## A2-P1 通用 LGBM 门禁（2026-08-07 完整性硬化）

### 20 品种当前可复核状态

| 状态 | 数量 | 品种 |
|:----:|:----:|:-----|
| **complete** | 13 | ss, rb, sp, i, jm, m, p, eg, jd, cf, sr, ma, fg |
| **partial** | 5 | ao(258/396), lh(259/396), ta(397/396, +1 unexpected bar), ur(331/396), cj(345/396) |
| **duplicated** | 1 | fu (792 行 / 396 唯一 bar，已生成 `fu.jsonl.canonical`) |
| **missing** | 0 | — |

### 备份可恢复品种（4 个）

以下品种主目录无文件，但存在于 `reports/a2_p1_results_backup/` 中：
- **BU** — complete (396/396)
- **AO** — partial (258/396)
- **TA** — partial (397/396, +1 unexpected bar)
- **UR** — partial (331/396)

恢复命令：`python scripts/a2_p1_restore_manifest.py --restore`（仅 dry-run 预览，加 `apply=True` 才写磁盘）

### FU 重复写入说明

FU 主目录文件 `fu.jsonl` 有 792 行（396 唯一 bar × 2），系并发 Worker 追加导致的重复写入。
已运行 `--canonicalize` 生成 `fu.jsonl.canonical`（396 行，按 bar_idx 去重保留首次出现）。
原文件保持不变，不可覆盖。

### A2-P1 裁决

- A2-P1 原始运行：16 品种可复核，全部 NO-GO
- A2-P1.1 定向修复（FG/TA/BU/AO/UR）：去重后 **0/5 GO**
- 不满足启动 A2-P2 的预设门槛（≥2 GO）
- **用户批准后启动 A2-P2**（2026-08-07）

---

## A2-P2 残差叠加门禁（2026-08-07 完成）

**目标**：测试 LGBM 残差叠加架构能否改善预测质量（`Y_residual = Y - timesfm_pure_pred`，`stacked = timesfm_pure_pred + lgbm_residual_pred`）

**执行**：
- 5 品种：FG、TA、BU、AO、UR（A2-P1.1 中最接近 GO 的品种）
- 总耗时：~90 分钟（远快于预估 6 小时，TimesFM 缓存复用效果显著）
- 报告：`reports/research/20260807_a2_p2_verdict.md`

**裁决结果**：

| 品种 | gate | stacked PF | scheme PF | pure PF |
|------|------|-----------|-----------|---------|
| AO | NO-GO | 0.868 | 1.286 | 0.704 |
| BU | NO-GO | 0.937 | 1.313 | 0.892 |
| FG | NO-GO | 0.856 | 1.364 | 0.957 |
| TA | NO-GO | 0.845 | 1.426 | 0.913 |
| UR | NO-GO | 0.838 | 1.002 | 0.880 |

**结论**：
- **0/5 GO**，残差叠加架构未改善预测质量
- Stacked PF 全部 < 1.0，且低于 scheme PF
- LGBM 残差预测实际上**退化**了性能
- **关闭 Track B（残差叠加方向）**，不启动 A2-P3

**技术修复**（执行过程中发现并修复）：
- `a2_p2_orchestrator.py` line 216: `logs_dir` 未定义 → 改用 `config.logs_dir`
- `a2_p2_generate_report.py`: 报告生成器扫描实际结果文件而非使用全部 SYMBOLS
- `a2_p1_runtime.py`: A2-P2 允许部分 bar 的 scheme 失败（验证逻辑分 run_id 处理）

### 当前生产姿态不变

- Copilot 为推荐盘中入口；预测与 Vol Overlay 红线不因 A2 结果改变

---

## 一句话结论

- **R1 分板块** chem / agri 已训练；业务 thr：`operational_thr.json` chem **0.65** / agri **0.45** / black **0.55**（black 仍回落 R0 pkl）。
- **L1 全宇宙 Neutral Overlay FAIL** → 生产 **vol 压平默认 OFF**。
- **盘中入口**：`scripts/copilot.py`（预测永不压平；Vol 仅预警；**可交易方向=加权1H**）。
- **新口径经济现实（2026-08-08）**：20 品种 WF 后仅少数弱正（SS/SR/M/JD 等）；**short 全灭**；无 3 星。
- **数据层**：`trading_calendar` + `future_bar_guard.run_guard`（`daily_update` 唯一批量入口）。

---


## 技术债清理 (2026-08-03 Ralph) - ✅ 完成

> **MA 优化 (#5)**: CPU 回测 11/11 完成 (SS/UR/SP/SR baseline + 6 MA 候选); 结果 `reports/three_star_verify_results.jsonl`
> **MA 结论**: ao_accel 最优 (PF 1.12, +9.3%) 但 < v2 的 10% 门槛, 维持 1 星 (负结论已实证)

### P0 已修复

| # | 项 | 状态 |
|:--:|:--|:--:|
| 1 | knowledge_base.json 重建 (反映 Phase 9 固化) | ✅ |
| 2 | AO/BU/JM scheme dir_acc 过期值修复 (AO +19.6pp 最大漂移) | ✅ |
| 3 | KB-SCHEMES 全量一致性校验 (20 品种) | ✅ |

### P1 已完成

| # | 项 | 状态 |
|:--:|:--|:--:|
| 4 | 3 星品种新鲜度验证 (SS/UR/SP/SR) | ✅ 见下 |
| 5 | MA 甲醇再优化 (6 候选全跑, ao_accel 最优但未达 v2) | ✅ 维持 1 星 |
| 6 | Phase 8b 裂解价差复评计划文档化 (2027 Q4) | ✅ |
| 7 | BU 评级一致性确认 (credit_stars=1 不变) | ✅ |

### ⚠️ 3 星 stale 重大发现 (#4)

3 星品种自 2026-06 固化后从未复验, 新鲜 walk-forward (396pt) 揭示:

| 品种 | scheme DirAcc | 新鲜 DirAcc | 漂移 | scheme_stars | 新鲜推算 |
|:--:|:--:|:--:|:--:|:--:|:--:|
| **SS** | 72.7% | 54.8% | **-17.9pp** | 3 | 0-1 星 |
| **UR** | 70.0% | 53.8% | **-16.2pp** | 3 | 0-1 星 |
| SP | 57.0% | 57.1% | +0.1pp | 3 | OK |
| SR | 57.0% | 57.3% | +0.3pp | 3 | OK |

- **根因**: SS/UR 的 72.7%/70% 来自 2026-06 窗口, 过拟合; SP/SR (57%) 准确
- **处理**: SS/UR dir_acc/mape/decay 已更新为新鲜值; scheme_stars + KB credit_stars 均已 3->1 降级
- **降级**: SS/UR scheme_stars 3->1 (2026-08-03 用户决策, Rule 7; 根因见 memory/three-star-stale-rootcause.md)
- **复评计划**: reports/research/20260803_phase8b_reeval_plan.md (Phase 8b, 2027 Q4)

### P2 技术债

| # | 项 | 状态 |
|:--:|:--|:--|
| 11 | 测试覆盖补强 (Phase 9 防回归 + KB 一致性 + ha_body 黑名单) | ✅ 2026-08-04 194/194 PASS |
| 8 | 模型层突破 3 星天花板 (DirAcc 58%->65%) | ⏸️ 待排期 |
| 9 | ha_body 有毒品种专攻 (AO/JD/CF) | ✅ 2026-08-04 AO 固化 / JD 确认最优 |
| 10 | 动态 Regime 路由 | ⏸️ 待排期 |

#### #11 测试覆盖明细

| 文件 | 覆盖内容 | 测试数 |
|:--|:--|:--:|
| `test_prediction_scheme_phase9.py` | 20 品种 covariate_type/covariate_types/dir_acc/stars 快照 + 篡改检测 | 84 |
| `test_kb_schemes_consistency.py` | KB vs SCHEMES 品种集合/covariate/stars/dir_acc/type/short_horizon 一致性 | 103 |
| `test_ha_body_toxic_blacklist.py` | AO/JD 禁止使用 ha_body + CF 例外确认 + 篡改检测 | 7 |

#### #9 有毒品种专攻明细 (2026-08-04)

**AO 氧化铝** - 10 候选 walk-forward (n=193 underpowered):
- ✅ **hourly_slope+calendar_cyclical 固化** (v2 PASS: MAPE -15.7%, PF +16.5%, EV +0.014->+0.090, MaxDD 改善 17.3%)
- ⚠️ n=193 < 350, 待数据积累后复验; DirAcc 56%->52% (-3.7pp 代价)
- ha_body 确认有毒 (EV -0.054, MaxDD -57.92%); ao_accel/vor/bb_squeeze/reversal_shadow 全 FAIL

**JD 鸡蛋** - 8 候选 walk-forward (n=396 充分):
- ❌ 全 FAIL, `rsi_state+oi` 确认最优 (PF=1.31, EV=+0.133, 全场最高)
- hourly_slope+oi 最接近 (EV +0.131, PF 1.30) 但 MAPE 退化未达 v2
- calendar_cyclical+gated_slope 计算异常 (FAIL)

**实证报告**: `reports/research/20260804_phase9_toxic_variety_study.md`

---

## Phase 9 二星->三星全量实证 + 固化 (2026-08-03)

**队列**: 73 作业, 15 品种, 单模型加载, JSONL 断点续跑  |  **结果**: 73/73 完成
**数据**:  | **判定**: 

### 核心结论

- **3 星不可达**: DirAcc 天花板 ~58%, 距 65% 差 7pp; 1H 级联预测上限受限于品种可预测性
- **v2 PASS 16 候选** (9 品种): FU/FG/LH/CJ/M/P/I 已固化, 其余品种已最优或天花板

### 固化清单 (config/prediction_scheme.py 已更新)

| 品种 | 旧配置 | 新配置 | DirAcc | PF | v2 |
|:--:|:--|:--|:--:|:--:|:--:|
| FU | rsi_state+oi+bb_squeeze | ha_body | 55.0% | 1.45 | PASS |
| FG | reversal_shadow | ha_body | 55.3% | 1.36 | PASS |
| LH | reversal_shadow | ha_body | 58.4% | 1.31 | PASS |
| CJ | reversal_shadow_gated_05 | ha_body | 55.2% | 1.34 | GREEN-MAXDD |
| M | calendar_cyclical | ha_body+calendar_cyclical | 58.1% | 1.47 | PASS |
| P | ha_body | ha_body+reversal_shadow | 53.5% | 1.48 | PASS |
| I | rsi_state+oi+ha_body | ha_body | 52.3% | 1.29 | GREEN-MAXDD |

### ha_body 适用性名单 (Phase 9 实证)

- **提升型 (改用 ha_body 后 DirAcc +2~8pp, 已固化 7 品种)**: FU, FG, LH, CJ, M, P, I
- **已最优型 (当前即 ha_body, 替换候选全退化)**: RB, TA, JM, BU, EG, SP
- **有害型 (ha_body 致指标恶化, 禁用 3 品种)**: AO (EV 转负), CF (-5pp), JD (EV 转负)

### 不变品种 (已最优, 全 FAIL)

RB (ha_body), TA (ha_body), CF (ha_body+calendar), EG (ha_body+oi+reversal_shadow), JD (rsi_state+oi), JM (ha_body), BU (ha_body), AO (hourly_slope)

---

## 生产基线

| 项 | 状态 |
|----|------|
| 预测 | 静态 `prediction_scheme` |
| Absolute Risk Overlay | 🔒 **默认 OFF** |
| 实验压平 | `--vol-filter-neutral`（不推荐默认开） |
| 盘中主观 | `python scripts/copilot.py ss fu` |
| 知识库 | `config/knowledge_base.json`（`build_knowledge_base.py`） |
| 评分源（回测） | `cascade/neutral_ab_report.py`（唯一） |
| 板块表 | `config/sector_map.py`（唯一） |
| 操作 thr | `models/operational_thr.json` |

---

## Phase 1 里程碑（摘要）

| 里程碑 | 结果 |
|--------|------|
| S0–S3 L1 R0 Neutral | ✅ 工程 PASS / 生产 REMAIN_OFF（Domain Shift） |
| **R1 分板块训练** chem/agri | ✅ `vol_risk_filter_{chem,agri}.pkl` |
| thr 网格 + operational 文件 | ✅ 0.65 / 0.45 / 0.55 |
| **L1 ops 全量经济终审** | ❌ **ECONOMIC_PASS=False** |
| Copilot 领航员 | ✅ 预警-only，不压平 |
| 工程债 D1–D3 | ✅ 2026-07-27 收口 |

### L1 ops 经济门禁（2026-07-25）

| 条件 | 结果 |
|------|------|
| HURTS ≤ 15% | ✅ 10% |
| mean EV ON ≥ OFF | ❌ ΔEV ≈ **−10.80** |
| mean MaxDD 改善 | ✅ ΔDD ≈ **+0.079** |

产物：`reports/phase1/full_universe_neutral_r1_ops/`  
（含 `ECONOMIC_VERDICT.json` / `summary.md` / `by_symbol/`）

### R1 训练快照

| 板块 | pkl | n | IS cal thr | 说明 |
|------|-----|--:|-----------:|------|
| energy_chem | `models/vol_risk_filter_chem.pkl` | 1860 | ~0.54 | 6 品种等权 310 |
| agri | `models/vol_risk_filter_agri.pkl` | 3100 | ~0.62 | OOS 分数漂移 → 用 op 0.45 |
| black_metals | `models/vol_risk_filter_black.pkl` | — | — | **未训**；r1 resolve → R0 `v2.pkl` |

---

## 关键模块地图

| 文件 | 角色 |
|------|------|
| `scripts/copilot.py` | 主观领航员 CLI + MD；写入 live_ledger |
| `cascade/live_ledger.py` | Phase L SQLite 账本 API |
| `db/live_ledger.db` | 预测事件（跨品种可 SQL） |
| `scripts/ledger_backfill.py` / `live_cov_health.py` | 回填 / 分层健康 |
| `scripts/build_knowledge_base.py` | L1+SCHEMES → knowledge_base |
| `cascade/vol_risk_filter.py` | 熔断模型 + ThrPolicy + R1 路径决议 |
| `data/trading_calendar.py` | 会话感知交易日标签（夜盘/周末） |
| `data/future_bar_guard.py` | 幽灵 K 线防护（唯一批量入口 `run_guard`） |
| `data/config.py` | `FM_ROOT` / `resolve_under_root` 绝对路径 |
| `scripts/data_management.py` | 采集调度（动态 timeout；cwd=FM_ROOT） |
| `scripts/train_vol_risk_sector.py` | R1 训练（all=chem+agri；black 可选） |
| `scripts/backtest_vol_gating_fullchain.py` | Neutral A/B 全链路 |
| `cascade/neutral_ab_report.py` | 唯一 A/B 评分层 |
| `models/vol_risk_filter_v2.pkl` | R0 / black 回落 |
| `models/operational_thr.json` | 业务操作 thr |

---

## 使用

```bash
# 生产预测（无 vol 压平）
python scripts/cascade_predict.py sr

# 盘中领航员（推荐）
python scripts/build_knowledge_base.py   # L1 更新后
python scripts/copilot.py ss fu

# 数据：日线+1H（动态 timeout；采后自动 purge 幽灵日线）
python scripts/data_management.py --daily --1h
python scripts/data_management.py --validate

# 幽灵日线 CLI
python -m data.future_bar_guard
python -m data.future_bar_guard --dry-run

# R1 训练（默认不训 black）
python scripts/train_vol_risk_sector.py --sector all
# python scripts/train_vol_risk_sector.py --sector black_metals --force  # 仅当授权

# 单测
python -m unittest tests.test_future_bar_guard tests.test_vol_threshold_contract -v
```

---

## 后续优先级

1. ~~工程债 D1–D3 + 根因 hardening + 文档 neat-freak~~ **已完成 2026-07-27**
2. ~~Phase L live_ledger（SQLite 账本 + Copilot 写入 + 回填 + health）~~ **已完成 2026-07-27**
3. **Copilot Paper Trading 打磨** / Phase S 用 live_cov_health 扫候选
4. 白名单 / LH 排除子集经济复判（仅当仍要压平网关时）
5. Agri 分数校准 / 「有害高波」标签重定义
6. **暂停 L2** 直至子集或新模型过经济门禁
7. 法定节假日交易日历

---

## 月度回测 / 协变量路线图

**Phase 4-6 状态 (2026-07-29):**
- ✅ **Phase 4 JD 日历周期协变量**: `calendar_cyclical` 4 维正余弦 (DOY+Month),全品种通用,宏特征架构 (单入口 → 4×1D 拆分),Scan JD MAE=5.10% 排名第 3
- ✅ Phase 5 CJ 影线门控: 固化 `reversal_shadow_gated_05` (scan MAE 5.49%→4.87%, -11%)
- ✅ **Phase 6 TA 已归档**: 实证 `basis_momentum` 退化 (+0.074pp vs bb_squeeze),不固化,保 `bb_squeeze`
  - 理论依据: TA 单边价格由成本端跟涨跌 + 波动率爆发驱动,单品种 calendar spread 无效
  - 实证文档: `reports/research/20260729_phase5_6_summary.md`

**Phase 8 跨品种 Crack Spread (2026-08-01):**
- ✅ **Phase 8a 框架 + PX-TA 验证**: 跨品种协变量框架建立 (calc_crack_spread + _align_feedstock + feedstock_cache + DI 咽喉点),PX-TA 首验证 **弱信号 (+2% MAE 退化),不固化**
  - effective_n=120 (PX 2023-09 上市,仅 ~3 年),UNDERPOWERED
  - 完整 backtest: bb_squeeze 基线 MAPE=2.24% vs crack_spread_slope 2.23%,EV/PF/MaxDD 微幅改善但未达 v2 门槛
  - 文档: `reports/research/20260731_phase8a_summary.md` + `reports/research/20260801_phase8a_backtest_report.md`
- ✅ **Phase 8b SC-FU/BU 验证**: SC 原油注册 (INE) + 采集 (9,994 1H bars, 2022-10+) + OLS ratio 标定 (FU=4.72, BU=2.81) + 6 模式完整 backtest
  - FU: crack_spread replace 退化, **additive 盈利改善** (EV +5%, PF +2%, MaxDD 改善 4%)
  - BU: crack_spread **多维改善** (DirAcc +2pp, EV +7%, PF +2%, WR +2pp),scan 有误导 (未进 TOP 5)
  - effective_n=264,UNDERPOWERED,不固化 (~15 个月后 2027 Q4 可重新评估)
  - 文档: `reports/research/20260801_phase8b_summary.md`
- **关键结论**: 裂解价差 (crack spread) 在两对品种对上均不提供充分的短期预测信号。经济直觉 ≠ 预测信号。BU 改善最强但未达固化门槛。

**Phase 9 TA 协变量优化 (2026-08-02):**
- ✅ **TA bb_squeeze → ha_body 固化**: 8 候选 full backtest (377pts) 筛选,ha_body 单独全维最优
  - DirAcc 56%→**58%** (+2pp), MAPE 2.26%→**2.15%** (-4.9%), EV +0.120→**+0.175** (+46%)
  - PF 1.27→**1.43** (+12.6%), MaxDD -15.61%→**-12.43%** (改善 20%)
  - v2 verdict: **PASS (ordinary)** — MAPE -4.9%≥3%, PF +12.6%≥10%
  - 3 星距离: DirAcc 58% 距 65% 差 7pp, 受限于品种可预测性上限; PF=1.43 全系统最高
  - 关键发现: 所有组合 (bb+calendar/ha_body+calendar/ha_body+bb/ha_body+rsi+oi/ha_body+oi) 均退化,ha_body 单独最优

**Phase 9 一星品种优化 (2026-08-02, 进行中):**
- ✅ **EG 乙二醇 -> 2 星 (新进)**: 10 候选, 最佳 ha_body+oi+reversal_shadow (v2 PASS, PF+13.6%), 最佳 ha_body+oi (EV +0.103, PF 1.23) / ha_body+cal+oi (DirAcc 56%)
  - 趋势: 叠加 oi 显著提升 EV/PF; 叠加 calendar 提升 DirAcc
  - v2: 未达标 (PF +11.9% 接近 10% 门槛, DirAcc +1pp 差 2pp)
- ✅ **JD 鸡蛋 -> 2 星 (新进)**: 8 候选, 最佳 rsi_state+oi (v2 PASS, PF+20.2%), 最佳 **rsi_state+oi (v2 PASS, EV+196%, PF+20.2%)**
  - v2: **PASS (PF +20.2% ≥ 10%)** - 待固化决策
  - DirAcc 52% 距 3 星差 13pp; Round 2 验证 rsi+oi+ha_body 反而退化 (ha_body 稀释 JD 信号)
- ❌ **MA 甲醇**: 7 候选 396pt walk-forward 全 FAIL v2, 最优 ao_accel (EV+0.057, PF+1.121, PFΔ+9.3%<10%), 维持 hourly_slope+oi, 1 星
  - v2: 全未达标 (ao_accel PF +9.3% 最接近 10% 门槛, ha_body DirAcc+1.2pp 未达 3pp)
  - 关键发现: ha_body 改善方向正确但力度不足; 无候选显著优于 baseline hourly_slope+oi
- **共性问题**: 3 品种 DirAcc 均在 52-56% 区间, 距 3 星 (65%) 差 9-13pp, 受限于品种可预测性上限

**Phase 9 二星->三星 协变量优化 (2026-08-02, 进行中):**
- 🎯 **目标**: 所有 2 星品种 (15个) 协变量提升至 3 星 (DirAcc>=65% + PF>=1.15)
- **硬约束**: 3 星评分 (`_stars_from_metrics`) 要求 DirAcc>=65% (55-64%+PF>=1.4 仅 2.0 分->2 星); DirAcc>=65% 是必要条件
- **运行器**: `scripts/two_star_candidate_runner.py` (nohup 脱机, 73 作业, 单模型加载, JSONL 断点续跑)
- **critic**: `scripts/two_star_critic.py` (v2 判定复用 `verdict()` + 3 星检查)
- **结果**: `reports/two_star_results.jsonl` | **进度页**: `reports/two_star_to_three_progress.md`
- **关键发现 (新鲜基线)**: scheme DirAcc 全部 stale (旧窗口)。FU scheme 59.1% -> 新鲜 53.5% (-5.6pp), 实际距 65% 差 11.5pp (比预估 -5.9pp 更大)。3 星目标比预期更难。
- **Tier 分级 (按 scheme DirAcc, 待新鲜基线重定)**: A (FU/RB/FG/TA/LH) / B (M/CF/EG/CJ/JD) / C (JM/I/BU/P/AO)
- **候选设计**: ha_body 主攻 DirAcc + 正交三角 (ha_body+oi+reversal_shadow); 73 作业 ETA ~18h
- **状态**: ⏹️ **关机保存** (59/73, 12 品种完成), 完整实证报告: `reports/research/20260803_phase9_two_star_to_three_study.md`
  - 剩余: I(2)/BU(4)/P(4)/AO(4) = 14 作业
  - 恢复: `nohup python scripts/two_star_candidate_runner.py > reports/two_star_runner.log 2>&1 &` (自动跳过已完成)

**实证结果 (15/15 品种完成)**:
- ✅ **可改善型 (7 品种, ha_body 变体提升, v2 PASS, 已固化)**:
  - FU: rsi_state+oi+bb_squeeze → ha_body (DirAcc 53.5%→55.0%, PF 1.38→1.45, MaxDD 改善 23%)
  - FG: reversal_shadow → ha_body (DirAcc 51.3%→55.3% **+4pp 最大提升**, PF 1.14→1.36)
  - CJ: reversal_shadow_gated_05 → ha_body (DirAcc 53.6%→55.2%, MaxDD -61.80%→-46.09% GREEN-MAXDD)
  - M: calendar_cyclical → ha_body+calendar (DirAcc 56.3%→58.1%, PF 1.24→1.47)
  - LH: reversal_shadow → ha_body (DirAcc 56.7%→58.4%, ⚠️ n=231 underpowered)
  - P: ha_body -> ha_body+reversal_shadow (DirAcc 45.5%->53.5%, PF 1.48)
  - I: rsi_state+oi+ha_body -> ha_body (DirAcc 45.5%->52.3%, GREEN-MAXDD)
- ❌ **已最优型 (8 品种, 所有候选退化)**:
  - RB: ha_body 已最优 (5 候选全 FAIL, DirAcc -0~-3pp)
  - TA: ha_body 已最优 (3 候选全 FAIL, DirAcc 57.8% 最高)
  - CF: ha_body+calendar 已最优 (4 候选全 FAIL, ha_body 有害 -5pp)
  - EG: ha_body+oi+reversal_shadow 已最优 (Phase 9 配置, 4 候选全 FAIL)
  - JD: rsi_state+oi 已最优 (Phase 9 配置, ha_body 有害 -3pp, EV 转负)
  - JM: ha_body 已最优 (3 候选全 FAIL, DirAcc -1~-2pp)
  - BU: ha_body 已最优 (DirAcc 54.0%)
  - AO: hourly_slope 已最优 (ha_body 有毒 EV 转负, DirAcc 56.0%)
- **3 星不可达**: DirAcc 天花板 ~58%, 距 65% 差 7pp, 1H 级联预测上限

---

## Phase 11 单协变量穷举 (2026-08-21 结案)

**目标**: 对 20 品种 (含 SH 待固化) 进行 7 协变量完整 walk-forward 穷举，以 Phase 9/G004 固化方案为 baseline 对比。  
**规模**: 138/138 作业全完成 (含 M 补跑), 34 GREEN, 12 品种固化, 3 品种基线保持。  
**资产**: `docs/archive/history/backtest_registry.md`（已归档）(189 实验, 21 品种)

### Phase 11 固化替换 (12 品种)

| 品种 | 旧协变量 | 新协变量 | PF | GREEN 数 | 备注 |
|:----:|:---------|:---------|:--:|:--------:|------|
| SS | reversal_shadow | calendar_cyclical | 1.09 | 4 | cal 最稳 (hs/rsi/oi/ao 均 GREEN) |
| SP | ha_body+calendar | calendar_cyclical | 1.07 | 1 | 消融 ha_body |
| FU | ha_body | calendar_cyclical | 1.23 | 1 | baseline PF=0.93 FAIL |
| I | ha_body | reversal_shadow | 1.06 | 1 | baseline ha_body PF=0.98 |
| RB | ha_body | rsi_state | 1.09 | 5 | 审核修正: hs=1.05 → rsi 更高 |
| TA | ha_body | calendar_cyclical | 1.03 | 1 | ⚠️ 边界值 |
| EG | ha_body+oi+reversal_shadow | calendar_cyclical | 1.04 | 1 | 简化为单协变量 |
| CJ | ha_body | hourly_slope | 1.29 | 5 | 🔥 全场最高 |
| LH | ha_body | rsi_state | 1.24 | 4 | rsi 最强 |
| JD | hourly_slope | rsi_state | 1.09 | 3 | 审核修正: hs=1.06 → rsi 更高 |
| AO | hourly_slope+calendar | 保持 | 0.73 | 0 | best PF<1, 无 GREEN |
| BU | ha_body | calendar_cyclical+hourly_slope | 1.01 | 1 | Phase 12 组合, 见下 |

### Phase 11 基线保持 (3 品种)

| 品种 | 当前方案 | PF | Phase 11 最佳候选 PF | 决策 |
|:----:|:---------|:--:|:--------------------:|:----:|
| M | ha_body+calendar_cyclical | 1.13 | calendar=1.06 | 保持 (组合 > 单协变量) |
| P | rsi_state+reversal_shadow | 1.10 | cal/hb=1.02 | 保持 (G004 组合更优) |
| SR | rsi_state+oi+calendar_cyclical | 1.10 | rev=1.03 ⚠️ 边界 | 保持 (组合更优) |

### SH 烧碱 (待固化)

Phase 11 已穷举 7 协变量: 0 GREEN (best PF=0.90)。不纳入 SCHEMES，待后续数据积累后复评。

---

## Phase 12 BU 组合协变量 (2026-08-21)

**目标**: 为 BU 沥青 (short_horizon, ha_body baseline PF=0.79 FAIL) 寻找 2 协变量组合。  
**方法**: 2 cov × 2 模式组合穷举 (calendar_cyclical, hourly_slope, ha_body, reversal_shadow)。

| 品种 | 旧协变量 | 新协变量 | PF | GREEN | 备注 |
|:----:|:---------|:---------|:--:|:-----:|------|
| BU | ha_body | calendar_cyclical+hourly_slope | 1.01 | 1 | 边际 GREEN, stars=1 不变 |
| AO | hourly_slope+calendar | — | 0.76 | 0 | 组合未突破 |
| CF | ha_body+calendar | — | 0.94 | 0 | 组合未突破 |
| JM | ha_body | — | 0.98 | 0 | 组合未突破 |
| FG | ha_body | — | 0.93 | 0 | 组合未突破 |

**关键洞察**: calendar (季节性) + hourly_slope (日内趋势) 互补；ha_body 对 BU 短窗口无效。

## Phase 13 弱信号品种组合探索 (2026-08-22 结案)

**目标**: 拯救 6 个 0 GREEN 弱信号品种 (JM/MA/UR/FG/CF/AO)。
**方法**: 3 个正交方向 × 6 品种 = 18 次回测。

| 批次 | 策略 | 测试数 | GREEN | 最佳 PF |
|:-----|:-----|:------:|:-----:|:-------:|
| P13a | top-1 + calendar (通用增强) | 6 | 0 | UR 0.97 |
| P13b | top-3 三协变量组合 | 6 | 0 | AO 0.88 |
| P13c | 非 top 探索 (ha_body+calendar 等) | 6 | 0 | AO 0.95 |

**结论**: **0/18 GREEN**。弱信号品种协变量天花板确认，组合优化无法突破。
**关键规律**:
- calendar 增强假说被否定 (P13a: 0/6)
- 3-cov 组合全面退化 (P13b: PF 系统性下降 -0.05)
- M 的成功模式 (ha_body+calendar) 不可迁移 (P13c: 0/6)
- AO ha+cal PF=0.95 为弱信号最佳成绩 (仍 FAIL, n=199 underpowered)

**后续**: 暂停弱信号品种协变量优化。AO 列入"待数据积累复评" (n=199<350)。转向信号工程改造或模型层突破。

## Phase 15 新协变量开发 (2026-08-23 结案, 2026-08-23 专家审核修订)

**目标**: 用 4 个全新信号维度的协变量突破弱信号品种天花板。
**来源**: 知乎交易指标综合研究报告 → 遴选 NVI/QSTICK/VWAP偏离/StdDev
**方法**: 4 协变量 × 6 品种 = 24 tests

| 品种 | baseline PF | 最佳新协变量 | 最佳 PF | delta | 样本量 |
|:-----|:-----------:|:------------|:-------:|:-----:|:------:|
| JM | **0.87** | vwap_deviation | 0.86 | -0.01 | n=396 |
| MA | **0.84** | nvi | 0.89 | **+0.05** | n=396 |
| UR | **0.84** | stddev | 0.92 | **+0.08** | **n=306 ⚠️** |
| FG | **0.89** | vwap_deviation | 0.86 | -0.03 | n=396 |
| CF | **0.80** | nvi | 0.77 | -0.03 | n=396 |
| AO | **0.86** | qstick | 0.79 | -0.07 | **n=199 ⚠️** |

> 注: baseline PF 已根据 2026-08-23 全品种核实修正 (原值 JM=0.90/MA=1.00/UR=0.97/FG=0.93/CF=0.90/AO=0.95 与 G005 回测注释不一致)。修正后 MA/UR 实际有改善。

**结论**: **24 tests 全 FAIL, 0 GREEN**。修正基线后 MA (+0.05) / UR (+0.08) 实际有改善,但均未达 GREEN 门槛 (PF>=1.0, n>=350)。
- Phase 15b (组合优化) 不触发: 无 >5% PF 提升
- Phase 15c (已 GREEN 验证) 不触发: 无 GREEN
- **本次搜索的 4 个新协变量均未达标** (非"路径彻底穷尽")

**关键洞察**: 新协变量信息维度确实新 (相关性预检 PASS),但新信息不具备预测价值。弱信号品种的瓶颈**可能**不在于缺少信号维度,而在于信噪比不足 (此洞察尚未经验证)。

**专家审核发现 (2026-08-23)**:
1. 🔴 **StdDev 数学问题**: 用 `std(close_price, 20)` 而非 `std(returns, 20)`,在非平稳价格序列上引入价格水平伪信号。**待修复后重跑 6 品种测试**。
2. 🟡 **AO/UR 样本量不足**: AO n=199 (56.9% 门槛)、UR n=306 (87.4% 门槛),未达 GREEN 门槛 350,结论统计效力不足,**应单独标注或排除**。
3. 🟡 ~~**基线引用不一致**~~: **已修正** (2026-08-23 核实, 6 品种 baseline PF 已更新为回测真实值)。修正后 MA/UR 实际有改善 (+0.05/+0.08)。
4. 🟡 **VWAP 常数填充无实证**: 唯一用 `np.full(horizon, last_val)` 而非衰减,缺乏回测支持。
5. 🔴 **"穷尽"结论过度外推**: 24 tests 搜索空间不足 (未测试参数窗口变体、标准化方式、交互项、跨品种联动、微观结构、基本面数据)。

**历史总结**: Phase 11-15 共 200+ 次回测。**本次搜索范围内的协变量未达标**,但更广泛的信号工程路径尚未充分探索。

**下一步建议** (按优先级):
1. **立即修复**: StdDev 改用收益率 std,重跑 6 品种测试
2. **基线核实**: 统一 baseline PF 来源,在回测时同时输出 baseline 对照
3. **样本量积累**: AO/UR 等数据增长至 n>=350 后重新评估
4. **中间路径探索**: 信号工程 (现有协变量非线性变换、跨品种联动、微观结构特征)
5. **模型层突破**: TimesFM 微调或 XReg 改用 Lasso/ElasticNet
6. **接受天花板**: 运营 13 个 GREEN 品种,放弃弱信号品种

## Phase 15b StdDev/VWAP 修复重跑 (2026-08-29)

**目标**: 验证 Phase 15a 专家审核发现的两个修复是否有效。

### 修复 1: StdDev returns std (保留 ✓)

`_calc_stddev()` 从 `std(close_price, 20)` 改为 `std(returns, 20)`。

| 品种 | 旧 PF(price std) | 新 PF(returns std) | delta | 判定 |
|:----:|:---:|:---:|:---:|:---:|
| JM | 0.77 | 0.82 | +0.05 | ✅ |
| MA | 0.77 | 0.79 | +0.02 | ✅ |
| UR | **0.92** | **0.81** | **-0.11** | 🔴 退化 |
| FG | 0.80 | 0.81 | +0.01 | ≈ |
| CF | 0.73 | 0.76 | +0.03 | ✅ |
| **AO** | **0.76** | **0.90** | **+0.14** 🔥 | 🔥 大幅改善 (n=199 underpowered) |

**5/6 改善, 1/6 退化 (UR)**。保留修复。UR 例外待后续复评。

### 修复 2: VWAP 衰减填充 (回滚 ✗)

将 VWAP 从常数填充改为 `_decay_fill` (12-bar 半衰期)。

| 品种 | 旧 PF(常数) | 新 PF(衰减) | delta |
|:----:|:---:|:---:|:---:|
| JM | 0.86 | 0.83 | -0.03 |
| MA | 0.78 | 0.78 | 0.00 |
| UR | 0.77 | 0.71 | -0.06 🔴 |
| FG | 0.86 | 0.81 | -0.05 🔴 |
| CF | 0.77 | 0.76 | -0.01 |
| AO | 0.73 | 0.74 | +0.01 |

**0/6 改善, 3/6 退化**。衰减填充整体有害，**已回滚为常数填充**。

### 决策

- StdDev returns std: ✅ 保留 (5/6 改善)
- VWAP 衰减填充: ✗ 回滚 (0/6 改善)
- 报告: `reports/research/20260829_phase15b_rerun_results.md`

## Phase Q1 协变量实现质量验证 (2026-08-29)

**目标**: 审计现有协变量库的实现质量问题，验证 6 个改进方向。

### 审计结果

新增 `tests/test_covariate_audit.py` (19 测试, 5 维度: 平稳性/范围/NaN/前视偏差/信息量; D1 REJECT 后移除 4 项 adaptive 测试)。
关键发现: `rsi_state` 固定边界导致 91.2% 输出为 0 (信息量不足)。

### 6 方向裁决

| 方向 | 裁决 | 理由 |
|:-----|:----:|:-----|
| D1 RSI 自适应边界 | **REJECT** | JD PF -0.02, P combo PF -0.10; 固定边界的"低信息量"是有效噪声过滤 |
| D2 QSTICK 窗口 | CANCEL | Phase 15 已证 QSTICK 0 GREEN |
| D3 basis_momentum | SKIP | 已归档，无活跃方案 |
| D4 NVI lookback | CANCEL | Phase 15 已证 NVI 0 GREEN |
| D5 Horizon 填充 | PAUSE | Phase 15b VWAP 衰减否定后空间小 |
| **D6 审计框架** | **ACCEPT** | 19 测试入 `tests/test_covariate_audit.py` |

### 核心认知

信息量 ↑ ≠ 预测力 ↑。rsi_state 91% 零输出 = 隐式信号门控 ("当前无极端信号")，自适应版 56% 非零反而引入噪声。

- 报告: `reports/research/20260829_phase_q1_covariate_quality.md`

---


- ✅ 方向 1: `monthly_backtest.py` 加 `--cache-interval` / `--max-points` / `--resume` (JSONL 断点续跑,抗 OOM kill)
- ✅ 方向 2: `get_basis_1h` 加合约自身 P95×5% 历史 OI 过滤 (置 NaN 抗挂单价污染)
- ✅ 方向 3: `covariate_scan.py` 加 3% 显著性门槛 + DirAcc 改名 `DirAcc(展示)` (裁决仍按 MAE 不变)
- ✅ 方向 4: TA Phase 6 归档 (见上方)

**下一阶段候选 (按优先级):**
1. **Phase 9 — 历史 Rollover 动态映射** (让 basis_momentum 真正可用于长程回测,Phase 8 已验证跨品种路径可行)
2. **Phase 7 — LH 基本面数据** (母猪存栏/猪粮比,外部数据源接入)
3. **Phase 8b 复评** (~2027 Q4, SC 数据增长至 effective_n≥350 后重跑 BU backtest)

---

## 运维待办

- [x] 法定节假日日历 (2026-08-30: `data/holidays.py` 2025/2026 官方表; validator 时效性改交易日口径; trading_calendar 感知节假日+调休, 未知年份回退现状)
- [x] three_star ensure_data 原子化 (2026-08-30: 结构化返回 {ok, error}, 失败可见不静默; three_star 阶段0/cascade_predict/predict --collect 适配)
- [x] data_management 全品种 timeout
- [x] 幽灵 K 线 purge：会话语义 + daily_update 单一入口 + 失败 exit 2
- [x] R1 模型路径锚定 FM_ROOT；black 缺 pkl 回落 R0（`model_source`）
- [x] STATE 与磁盘事实对齐
- [x] 审计 nits 根因修复（2026-07-27）：cwd 无关路径、双 purge、静默失败、空 pkl
- [x] KB PF all null 调研归档（2026-09-20）：`docs/superpowers/specs/2026-09-20-kb-pf-degraded-fix-spec.md`。L1 全量回测产物（2026-07-25, ECONOMIC_PASS=False）未版本化后被清理，KB 自 09-17 起 degraded。**方案 C：标记已知退化，不改代码**。PF ratio gate 事实休眠（v23 不产出 PF + 复测队列空）。待 v23 评估器输出 PF 时再执行方案 A（重建 L1 管线）

## Supervisor budget_exhausted (20260903_130429)

历史（旧宿主，本仓无副本）：`/root/timesFM_fu/docs/superpowers/reports/supervisor_budget_exhausted_20260903_130429.md`

## Supervisor budget_exhausted (20260903_130629)

历史（旧宿主，本仓无副本）：`/root/timesFM_fu/docs/superpowers/reports/supervisor_budget_exhausted_20260903_130629.md`

## Supervisor budget_exhausted (20260903_131108)

历史（旧宿主，本仓无副本）：`/root/timesFM_fu/docs/superpowers/reports/supervisor_budget_exhausted_20260903_131108.md`

## Supervisor goal_reached (20260909_035816)

See /home/abug/timesfm/docs/superpowers/reports/supervisor_goal_reached_20260909_035816.md

## Supervisor goal_reached (20260909_041328)

See /home/abug/timesfm/docs/superpowers/reports/supervisor_goal_reached_20260909_041328.md

## Supervisor goal_reached (20260909_041429)

See /home/abug/timesfm/docs/superpowers/reports/supervisor_goal_reached_20260909_041429.md

## Supervisor budget_exhausted (20260909_232042)

See /home/abug/timesfm/docs/superpowers/reports/supervisor_budget_exhausted_20260909_232042.md
