# v4 收口统一实施计划（Stage 3 评估 + 死代码审核合并处置）
> **代码基线**: `1c6222a`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

- 日期：2026-09-30
- 来源：`reports/2026-09-30-stage3-compliance-evaluation.md`（发现 A–H）+ `reports/2026-09-30-dead-code-spec-review.md`（P0×6 / P1×6）
- 汇合点：**协议 v4 收口**——所有改变结果语义的修复捆入一次指纹升级（v3→v4）、一次重启、一波重生。旧 v3 裁决随活跃视图机制（5eab80d）自然退场，发现 C/E 的存量问题自解；fu 随波直接补 v4（省掉 v3 下的白做重生）。

## 〇、宿主裁定记录（2026-09-30）

| # | 裁定 | 内容 |
|---|---|---|
| (d) | **协议 v4 现在捆绑** | 2.1–2.8 一批次、一次重启、一波重生；不分两次指纹升级 |
| (e) | **A2 整簇退役** | 10 个 a2 脚本 + `cascade/lgbm_features.py` + 配套测试一并 git mv 归档；`module_freeze.md` CF-13 行加一行归档注记；dead 结论入记忆文档；不做重量级归档 README |
| (b) | **撤销**（0.3 执行前自勘误） | oi_gated_momentum 实为活码（`features.py:1118` 相对导入 + `:1518` dispatch + `extract_xreg.py:85-89` 生产注册 + `covariate_pool.json:212` 在池）→ 模块、3 测试、spec 文档全部保留；审核报告 P1-3 作废（其 §八勘误） |
| (c) | install_praxist_llm_env_hook 保留 ACTIVE_CLI | 默认推荐执行（宿主未异议） |

## 一、阶段 0：清障与裁定包

- **0.1 修 2 个测试失败** → 基准恢复 1646/0/7/1 ✅（**119e28c**）
- **0.2 三文档入库**（**48ade27**）：评估报告 + 审核报告 + 本计划
- **0.3 死代码 spec 修订入库** ✅（**6455f6c**）：吸收 P0×6 / P1×6 + 裁定落纸 + D1/D2/D3 全名单 + 真实行数 + (b) 撤销自勘误
- **0.4(a) Q7 决策备忘录** ✅（本 commit）：生产函数实测途径 B 可行域表（16 条 v3 全长配对行，Var_LR 品种中位 × Δ × 功效）+ 三选项量化 + 倾向 (a′) → 交付宿主裁定

## 二、阶段 1：死代码归档（分层 commit，每层 scoped 测试）

- 1.1 D3 批次（名单以 0.3 修订稿落纸为准；(f) 勘误：pull_history_1h 撤回 → 5 文件/590 行）
- 1.2 D2 批次（同上）
- 1.3 D1 批次（证据保留档，8 文件 802 行；regen 双件顺延 2.9 → 立即 6 文件 690 行）
- 1.4 clear_supervisor_pause.py 归档 + `restart_three_loop_clean.sh` 摘除第 [4/6] 步（P0-4）
- 1.5 A2 整簇退役（裁定 e）：10 脚本 + `cascade/lgbm_features.py` + 5 个测试（`test_a2_*` 4 件 + `test_lgbm_features.py`——命名模式漏网补录）+ `module_freeze.md` CF-13 注记；合计 16 文件 / 5,257 行
- 1.6 检测测试重设计落地：AST 导入图分析（含相对导入形态）+ allowlist + archive 排除 + **pytest.ini**（testpaths=tests；P1-5）
- 1.7 文档同步：runbook.md / three_loop_restart_protocol.md / three_loop_workflow.md / praxist_llm_env.md / WSL 根 AGENTS.md / `D:\FlyBuddy\AGENTS.md` FM_a 行 / agent 记忆
- ~~（暂缓至 2.9）regenerate_all_baselines / regen_rb / monitor_rb_regen.sh 三件套~~ 2026-10-01 已归档（scripts/archive/2026-09-30-dead-code/）

## 三、阶段 2：v4 代码批次（结果语义变更集中于此）

- 2.1 eval_start 绝对锚定（修复 B 左半）
- 2.2 checkpoint 键 → `(symbol, cutoff_ts, experiment_fingerprint)`（修复 B 右半）
- 2.3 协议指纹纳入窗口语义 → v3→v4（PR-A5 教训；裁定 d）
- 2.4 `build_variant_id` 生产接线（修复 C）
- 2.5 增量追加写 context_hash（修复 D）
- 2.6 顶层四分母写入 + 纳入 A1_REQUIRED_FIELDS（修复 E writer 侧；存量靠 v4 退场）
- 2.7 supervisor 注释修正（修复 G）
- 2.8 配对测试：同数据末端 ±1 bar 两次运行，评估 cutoff 集合必须相同；v4 指纹快照测试
- 2.9 ✅（2026-10-01，见执行日志）一次重启（three_loop_restart_protocol）→ v4 重生波（fu 随波补 v4）→ 验证活跃视图 v4 → regen 三件套归档 + allowlist 释放
- 2.10 `detection_threshold_vs_baseline` 补 /n（**发现 I**，0.4(a) 实测导出）：门槛改 SE(d̄)=√(σ_LR²/n)；黄金测试改 spec 真实构造（rho=0.5 AR(1)，断言 0.096 不变）；evaluator.py 死 import 随 2.6 接线一并处置。零生产调用 → 无结果语义变更，不搭 v4 指纹波，可随批次先行

## 四、阶段 3：Stage 4 启动包（Q7 已裁定：(a′) Δ\*=0.08 / 80% / α=0.05 单侧）

- 3.1 PR-D1 预注册（裁定 (a′)：Δ\*=0.08、功效 80%、单侧 α=0.05、N(品种)=途径 B 实测口径 986–1,199 点、判负规则）
- 3.2 PR-D2 goal 重写（0.51 阈值退役）
- 3.3 首批确认运行
- 3.4 Phase 3 TODO spec

### 阶段 3 分层实施清单（A–E，2026-10-01 启动）

**状态图例**：`[ ]` 待办 · `[~]` 进行中 · `[x]` 完成

- [x] **勘查**（设计定型依据，见 changelog §4.2 六条决策）
  - [x] 基础设施盘点：family 记账全套在位但 supervisor 无调用点；run_mode 逐行落盘已通；
        symbol_status 已清空无存活读者；n_required 途径 B 接口确认
  - [x] 确认集窗口：`eval_indices[:max_points]` **取前 n** → 与 test 68 语义天然一致
  - [x] checkpoint 隔离必要性：resume 会把探索点混进确认 DM（消融批次同型先例）
  - [x] n_confirm_required 逐品种复算与 Q7 表逐项吻合（jd 1,199 / m 1,021 / rb 1,182 / sr 986 / ss 1,115）
  - [x] goal 阈值真判据在 `build_snapshot`（yaml `phase_definitions` 仅文档）；预算为真强制
- [x] **A** `scripts/preregistry.py` 纯逻辑 + `tests/test_preregistry.py`
  （spec §5.3 tests 37/38/40/44/68 + (a′) golden 数字 + 判负规则）
- [x] **B** 接线层：`run_symbol_backtest(eval_start_ts=)` + 慢环透传
  （run_mode/prereg_id/`{vid}__prereg_{id[:8]}.jsonl` 命名空间 + 个体 run_label）
  + supervisor 确认分派（no-peek 门 + 节流审计）+ 终结解析 + family 接线 + 测试
- [x] **C** PR-D2：`build_snapshot` 分级重写（`n_confirmed_variants` / 三档派生：
  可预测 / 需更多样本 / 当前不可验证；0.51 + `n_gate_pass>=10` + tier>=8 退役）
  + `praxist_goal.yaml` 有界预算 + symbol_status 退休 + 测试
- [x] **D** 首批预注册落 `task_FM/config/preregistry.jsonl`（jd_vor +078 / sr_vwap_deviation +063，
  跨品种 = 跨 family）+ Phase 3 TODO spec（multi_seed/decay 占位符）+ 计划日志
- [ ] **E** 三环一次重启加载新代码（确认集需 ~1.2–2.0y 累积，重启安全）+ 验收 + 文档/记忆同步

**跨层纪律**：① 预算 999999 无界值必改（spec W3.6④，与预注册纪律直接冲突）；
② 确认行不得与探索 checkpoint 混用；③ 成功判定只认含 `fdr_pass` 的严格链（family 封账盖章），
个体 run_label 不等于计入目标；④ 每个 PR 带绿测试（spec §8.5 硬约束 7）。## 五、缺口 → 任务映射

| 发现 | 任务 |
|---|---|
| A（2 测试） | 0.1 ✅ |
| B（窗口 / checkpoint） | 2.1 / 2.2 / 2.3 |
| C（variant_id） | 2.4 |
| D（context_hash） | 2.5 |
| E（四分母） | 2.6 + v4 退场 |
| F（legacy_untrusted） | 观察 |
| G（注释） | 2.7 |
| H（PR-D1/D2） | 阶段 3 |
| I（threshold 缺 /n） | 2.10（0.4(a) 实测导出；零生产调用，不搭 v4 波） |
| P0-1/2/3（cascade 活码） | 0.3 修订保留 |
| P0-4（pause / .sh） | 1.4 |
| P0-5（lgbm_features） | 1.5（裁定 e） |
| P0-6（测试基线） | 0.1 ✅ |
| P1-1/2（口径） | 0.3 修订 |
| P1-3（oi_gated） | **撤回**——实为活码，保留（0.3 执行前自勘误；审核报告 §八） |
| P1-4（monitor_rb_regen） | 2.9 ✅（2026-10-01 归档） |
| P1-5（检测测试 / pytest.ini） | 1.6 |
| P1-6（D1/D2/D3 落纸） | 0.3 修订 |

## 六、里程碑

- **M0（当日）**：0.1–0.4 完成，基准 0 failed，spec 修订入库
- **M1（+0.5–1 天）**：阶段 1 归档完成，全量测试复绿，检测测试在位
- **M2（+1 天）**：阶段 2 代码批次完成，配对测试过
- **M3（+1–2 天挂机）**：重启 + v4 重生波完成，活跃视图 v4，fu 补齐
- **M4（Q7 后）**：Stage 4 启动

## 七、执行日志

- 2026-09-30 0.1 ✅ **119e28c**（1646 passed / 0 failed / 7 skipped / 1 xfailed，323s；裸 pytest 收集 third_party 7 errors 中断的实证留档 → 1.6）
- 2026-09-30 0.2 ✅ **48ade27**
- 2026-09-30 0.3 ✅ **6455f6c**：spec v2 入库 + 审核报告 §八勘误（P1-3 撤回）+ 本计划 (b)/1.3/1.5/1.6/映射同步。执行前边界终验：oi_gated_momentum 为活码（相对导入盲区，第五次同型错误，裁定 b 撤销）；test_lgbm_features.py 补录；最终账：立即归档 50 文件 / 12,374 行 + 顺延 2.9 三件套 3 文件 / 153 行
- 2026-09-30 0.4(a) ✅ 本 commit：Q7 备忘录入库（`reports/2026-09-30-q7-target-effect-power-memo.md`）——途径 B 实测（16 条 v3 全长配对行 dm_common=588，与注册表逐行对账 ±0.002）：Var(d) 中位 0.45（rho≈0.1 非 0.5）、隐含 VIF 中位 2.85、Var_LR 中位 ~1.19（spec 情景 2.007 净保守 ~1.7×）；Δ_min@588(80%)=0.104–0.114；三选项量化+倾向 (a′)（Δ\*=0.08/80%，非约束）；连带发现 I（threshold 缺 /n，零生产调用）→ 新增 2.10；Q7 提交宿主裁定（不阻塞阶段 1/2）
- 2026-09-30 0.4(b) ✅ 本 commit：Q7 宿主裁定落纸——**(a′)** Δ\*=0.08、功效 80%（α=0.05 单侧、N(品种)=986–1,199 实测口径、分级表述按 (c) 改写、live 密度修订日历+每季实测 Var_LR 复核）；memo 头部裁定行 + 本计划阶段 3 标题/3.1 同步；阶段 3 解锁
- 2026-09-30 1.1 ✅ **1062b29**（D3 6/736）+ **1.1a 勘误**（本 commit）：复验发现 pull_history_1h 实为活码——data_management.py（在用采集调度入口）collect_1h()/backfill_gaps() 经 `run_script("pull_history_1h.py")` 裸文件名子进程边调用（五道筛第 3 筛漏检形态，第 6 次同型错误）→ 撤回归档；D3 立即账目 5/590，立即归档总量 49 文件/12,228 行；spec v2 §0(f)/E-3/§2.1/§4.2/§4.5/§7/§8 同步勘误；runbook.md:33 行保留
- 2026-09-30 1.2 ✅ **a32898e**（D2 22/5,691）+ 1.3 ✅ **0413230**（D1 6/690，regen 双件顺延 2.9）+ 1.4 ✅ **9b996a1**（restart_three_loop_clean.sh 摘除 [4/6] 步重编号 [x/5]；guard 扩裸 (name).py 后 train_regime_model.py:301 print 提示 adjudicated 非 blocker，1.7 修正）
- 2026-09-30 1.5 ✅ **6e7251d**（A2 16/5,257 全 100% rename + module_freeze CF-13 注记）；归档后全量对照：1544 passed/0 failed/6 skipped/1 xfailed = 1551 = 1654−103（A2 预点数）逐项吻合；tests/archive 归档测试收集 4 errors → pytest.ini norecursedirs 依据 +1
- 2026-09-30 1.6 ✅ 本 commit：检测测试落地（tests/test_no_dead_code.py 3 tests：挂账断言/名单时效性/archive 排除+stem 碰撞）+ pytest.ini（testpaths+norecursedirs）。AST 图：108 节点（scripts 80/cascade 28）、236 边源、96 被引用；首跑 12 零引用 = 6 文档化 LIVE + 6 REVIEW_CANDIDATES 挂账（ablation_context/add_horizon_known/resmoke_vol_thr_offline/scan_vol_thr_smoke/validate_context_length/verify_baseline_consistency——零引用零文档零配置调用，不在已批准归档清单，2.9 后宿主复核）

- 2026-09-30 2.1/2.2/2.3/2.5/2.6 ✅ 本 commit（v4 窗口锚 + checkpoint 身份 + 四分母顶层化）：monthly_backtest 加 eval_end_ts/protocol_fingerprint 参数（锚=末根 bar 收盘，截断 dt<锚，逐行落盘；CLI resume 从行内还原锚）；checkpoint 主键 (symbol, idx)→(symbol, cutoff)（idx 随数据漂移——recompute_dir_acc 实测同文件多段 run/idx 非单调/跨协变量逐字节同文件的病理根因）；慢环 _load_checkpoint_state 指纹门（旧协议行 fail-visible 丢弃、计数上报、全量重算）；协议指纹 v3→v4（+window_anchor 组件，WINDOW_ANCHOR_VERSION=eval_end_persisted_v1）；build_summary 四分母顶层化 + A1_REQUIRED_FIELDS 纳入（发现 E writer 侧：18/18 v3 行 metrics.n_dir_total 非空而顶层 None）。2.5 context_hash 经指纹门自然修复（混合覆盖→None 是 W6.7 fail-visible 设计；v4 重生波后全点带摘要→聚合非 None，无代码新增）。2.4/2.7 推迟：vid 生产接线点在 supervisor（vid 诞生地 :1573/:1734）与 2.7 同文件（宿主未提交 fu 编辑无法干净 stage），随 2.9 重启协调一并落地。测试：3 处 v3 版本 pin 升 v4；test_monthly_resume 模拟 loader 换 cutoff 键；test_verify_t1a_criteria_a fixture 补四分母真值；新增 tests/test_v4_window_anchor.py（配对不变量：同锚+数据+1 bar→cutoff 集合逐点相同；指纹门/锚还原单测；未传锚时末端自锚）

- 2026-09-30 2.4/2.7 ✅ 本 commit（宿主 fu 提交 bc6a9fb 后接力）：supervisor 新增 _experiment_fp_for（weights=get_timesfm_model_path 与 evaluator 同源、target=DataStore 1H close_price 逐品种缓存、CONTEXT_BARS/HORIZON/STEP+[cov] → compute_experiment_fingerprint 唯一家；任一环不可解析 → None fail-visible）；harvest_proposals :1519 生产路 fam 前移 + family_unresolved/experiment_fp_unavailable 拒收计数（归因顺序不变）+ vid=build_variant_id；harvest_survivors :663 回滚保留 utility 同接线（resolve_cov_family 定 family，unknown/None 跳过）；:1219 repeat penalty join 键保持旧式 symbol_cov + 澄清注释（与快环 shared_findings.variant_name 的 join 键，改实验身份会静默杀死惩罚）。过渡语义：load_snapshot 协议过滤（方案 A）已决定重生波语义，vid 迁移随波自然过渡、dedup 波后自愈；旧 vid checkpoint 文件成孤儿（磁盘垃圾非正确性）。2.7：:536 pass_variants 注释与 :728 报告头去 migrated_pass；:836 报表 display-only 保持（审计裁定可接受，出范围）。测试 +4（experiment_fp_unavailable 拒收 / family_unresolved 拒收 / vid 格式=实验身份 / survivors fp 不可得静默跳过），scoped 101 passed，全量 1557/0/6/1（=1553 基准 + 4 新测试）

- 2026-09-30 2.8/2.10 ✅ **e37e5c6**（2.10）/ 0015b00 内含（2.8）：2.10 门槛补 /n——detection_threshold_vs_baseline SE 改均值标度 √(σ_LR²/n)，黄金测试改 spec 真实构造（rho=0.5 AR(1)，断言 0.096 不变），test_statistical_verification 同步；零生产调用无结果语义变更。2.8 配对不变量随 0015b00 落地（tests/test_v4_window_anchor.py：同锚+数据+1 bar→cutoff 集合逐点相同；指纹门/锚还原单测；未传锚时末端自锚）

- 2026-10-01 2.9 ✅ 本 commit（重启后追加）：三环重启协议一次执行（readiness 6/6；supervisor PID 418，v4 协议指纹 f02b2a43… 上线）→ ensure_baselines 重生波 9/9 全带 v4 指纹落章（cj/eg/fu/jd/lh/m/rb/sr/ss；fu 为入集后首个有效基线 n=588 dir_acc=0.448；中途 WSL VM 回收击杀 PID 393，幂等重启 PID 418 续跑，波可恢复设计实证）→ 活跃视图 v4 干净（188 行=143 legacy+27 v2+18 v3 全排除，passing=0/dead=0，v4 裁决从零累积）→ 首 tick 收割入队 vid 全新格式（sh_momentum_f8bc3e69c749 / sr_volatility_3ede6200c5bd，2.4 生产首验）+ phase=slow + 慢环消费中 → regen 三件套归档 + TEMPORARY_ALLOWLIST 释放（本 commit）。REVIEW_CANDIDATES 6 件复核条件达成，待宿主裁定

- 2026-10-01 3.0 ✅ 本 commit（阶段 3 启动，设计定型）：PR-D1/D2 勘查完成，六条设计决策落纸（changelog `2026-10-01-v4-stage2-done-stage3-start.md` §4.2）——① `run_symbol_backtest` 缺 `eval_start_ts`，需新增，切片 `[:max_points]` 取前 n 与确认集语义一致；② 确认行须 `{vid}__prereg_{id[:8]}.jsonl` 隔离 checkpoint（resume 混探索点会污染 DM，消融批次同型先例）；③ `n_confirm_required` 用生产 `n_required(var_d=Var_LR, vif=1.0, delta=0.08)` 逐品种复算与 Q7 表逐项吻合（无实测品种取保守默认 Var_LR=1.240）；④ 确认 verdict 写时落个体标签 ∈ {confirmed, refuted, underpowered}，成功判定仍走含 `fdr_pass` 的严格链（只由 family 封账盖章）；⑤ goal 阈值硬编码在 `build_snapshot`，yaml `phase_definitions` 仅文档（PR-D2 重写对象 = build_snapshot per-symbol 判定 + all_symbols_pass_phase* 布尔族）；⑥ 预算为真强制（:2693 max_cycles / _deadline_passed），999999 无界须改有界。首批确认假设取 Q7 §3.4 观察带 top-2（jd_vor +0.078 z=1.63 / sr_vwap_deviation +0.063 z=1.51，跨品种=跨 family）。实施分层 A–E（本计划 §四清单）。同时补 2.8/2.10 执行日志（e37e5c6 / 0015b00 内含）

- 2026-10-02 D ✅ 本 commit：D 完成；两行预注册（jd vor，样本量 1199；sr vwap_deviation，样本量 986）；确认起点 `2026-10-03 00:00:00`；Phase 3 文档 `docs/superpowers/specs/2026-10-02-phase3-multiseed-decay-todo.md`；监督环仍不调用确认分派；E 尚未执行。生产函数对 ss 的样本量是 1116，备忘录印的 1115 不改函数。

- 2026-10-03 2.9 运行成果 ✅ 本 commit（46h 窗口收口）：报告落档 `reports/2026-10-03-three-loop-v4-operations-report.md`。要点——① **收割枯竭根因定位与修复验证**：阶段① 连续 9 轮 `harvest_empty`（每轮可用候选 44→0），根因为 `_harvest_rows` 用未过滤快照（`_has_prior_failure` 按 symbol×cov 配对，非 vid），使被 v4 波作废的 188 条旧代裁决继续压制新提案；A/B 实测正确口径下候选 7 → 134；对方 agent `045c7e2` 以 `_active_protocol_snapshot` 修复，阶段② 首轮即入队 3 行、入队率 50%→100%、`no_failure_delta` 2384→1226、裁决产出 0.72→1.62 条/h（**2.3×**）。② **46h 战果**：v4 裁决 44 条、gate_pass 13/44、单侧 p<0.05 两条、fdr_pass 1/44、known_ahead 3/44、FDR 晋升 44 个（23+21）；基线 9/9 零重生；提案 2582→3592；cycles 178→203。③ **确认级仍 0（符合设计）**：44/44 exploration，W3.4 严格链要求 run_mode=confirmation + fdr_pass；两条 p<0.05 候选 pairing_valid=False 且 missingness_admissible=False（§7.8 前保守默认），预注册通道已注册 jd(1199)/sr(986) 两项，confirm_from=2026-10-03。④ 未解缺口：`star` 字段 44/44 None；`family_dead` 在 44 条样本下已拒 602 条（建议复核最小样本要求）；SIGTERM 首次被忽略（信号处理路径待查）；两处测试红（fixture 缺指纹 / 一次性脚本未挂账，均测试侧）。

② **46h 战果**：v4 裁决 44 条、gate_pass 13/44、单侧 p<0.05 两条、fdr_pass 1/44、known_ahead 3/44、FDR 晋升 44 个（23+21）；基线 9/9 零重生；提案 2582→3592；cycles 178→203。③ **确认级仍 0（符合设计）**：44/44 exploration，W3.4 严格链要求 run_mode=confirmation + fdr_pass；两条 p<0.05 候选 pairing_valid=False 且 missingness_admissible=False（§7.8 前保守默认），预注册通道已注册 jd(1199)/sr(986) 两项，confirm_from=2026-10-03。④ 未解缺口：`star` 字段 44/44 None；`family_dead` 在 44 条样本下已拒 602 条（建议复核最小样本要求）；SIGTERM 首次被忽略（信号处理路径待查）；两处测试红（fixture 缺指纹 / 一次性脚本未挂账，均测试侧）。

- 2026-10-03 未决问题清单落档 ✅（46h 窗口巡检后）：报告 `reports/2026-10-03-fm-a-open-issues.md`。**P0**：`family_dead` 判据（≥4 ok 裁决且 0 pass）与确认机制耦合——`pass_variants` 要求 `run_mode=confirmation`+`fdr_pass`，确认产出前 pass 恒 0，故任何 family 累积 4 条 ok 裁决即被判死（`term_structure` 已死）；实测 `family_dead` 602→642、`no_failure_delta` 1226→1922、可用候选 123→67（13.6h 内 −46%），数日内将重演已修的收割饿死（病因不同、后果相同）。**P1**：确认通道空窗 1.2–2.0y（与 P0 互为因果）；两条 p<0.05 候选（m_momentum 0.0236 / lh_momentum 0.0374）协变量均为 self_referential 且 pairing/missingness 不可用；唯一「过门+known_ahead」组合 `cf_calendar_5bd18d23ae63`（dir 0.576）p_value=None，是最值得追加预注册的对象。**P2**：红测试 2 处（fixture 缺指纹 / 一次性脚本未挂账）、SIGTERM 首次被忽略、agri 板块 5/10 长期半退化。**勘误**：此前"`star` 字段 v4 未产出"不成立——该键全历史不存在，评级实由 `tier` 承载（v4 S6/A6/B21/C11），已在运行成果报告中同步更正。【2026-10-03 10:05 提交】

- （后续追加）
