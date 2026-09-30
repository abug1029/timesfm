# v4 收口统一实施计划（Stage 3 评估 + 死代码审核合并处置）

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

- 1.1 D3 批次（名单以 0.3 修订稿落纸为准）
- 1.2 D2 批次（同上）
- 1.3 D1 批次（证据保留档，8 文件 802 行；regen 双件顺延 2.9 → 立即 6 文件 690 行）
- 1.4 clear_supervisor_pause.py 归档 + `restart_three_loop_clean.sh` 摘除第 [4/6] 步（P0-4）
- 1.5 A2 整簇退役（裁定 e）：10 脚本 + `cascade/lgbm_features.py` + 5 个测试（`test_a2_*` 4 件 + `test_lgbm_features.py`——命名模式漏网补录）+ `module_freeze.md` CF-13 注记；合计 16 文件 / 5,257 行
- 1.6 检测测试重设计落地：AST 导入图分析（含相对导入形态）+ allowlist + archive 排除 + **pytest.ini**（testpaths=tests；P1-5）
- 1.7 文档同步：runbook.md / three_loop_restart_protocol.md / three_loop_workflow.md / praxist_llm_env.md / WSL 根 AGENTS.md / `D:\FlyBuddy\AGENTS.md` FM_a 行 / agent 记忆
- （暂缓至 2.9）regenerate_all_baselines / regen_rb / monitor_rb_regen.sh 三件套

## 三、阶段 2：v4 代码批次（结果语义变更集中于此）

- 2.1 eval_start 绝对锚定（修复 B 左半）
- 2.2 checkpoint 键 → `(symbol, cutoff_ts, experiment_fingerprint)`（修复 B 右半）
- 2.3 协议指纹纳入窗口语义 → v3→v4（PR-A5 教训；裁定 d）
- 2.4 `build_variant_id` 生产接线（修复 C）
- 2.5 增量追加写 context_hash（修复 D）
- 2.6 顶层四分母写入 + 纳入 A1_REQUIRED_FIELDS（修复 E writer 侧；存量靠 v4 退场）
- 2.7 supervisor 注释修正（修复 G）
- 2.8 配对测试：同数据末端 ±1 bar 两次运行，评估 cutoff 集合必须相同；v4 指纹快照测试
- 2.9 一次重启（three_loop_restart_protocol）→ v4 重生波（fu 随波补 v4）→ 验证活跃视图 v4 → regen 三件套归档 + allowlist 释放
- 2.10 `detection_threshold_vs_baseline` 补 /n（**发现 I**，0.4(a) 实测导出）：门槛改 SE(d̄)=√(σ_LR²/n)；黄金测试改 spec 真实构造（rho=0.5 AR(1)，断言 0.096 不变）；evaluator.py 死 import 随 2.6 接线一并处置。零生产调用 → 无结果语义变更，不搭 v4 指纹波，可随批次先行

## 四、阶段 3：Stage 4 启动包（Q7 裁定后）

- 3.1 PR-D1 预注册
- 3.2 PR-D2 goal 重写（0.51 阈值退役）
- 3.3 首批确认运行
- 3.4 Phase 3 TODO spec

## 五、缺口 → 任务映射

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
| P1-4（monitor_rb_regen） | 2.9 |
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
- （后续追加）
