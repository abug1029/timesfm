# 未提交改动综合审核报告（commit 84205f2 + 全分支 spec 符合性）

- **日期**: 2026-09-16
- **对象**: WSL `/home/abug/timesfm` 分支 `feat/prediction-quality-redesign-v23`，HEAD `84205f2`
- **审核方式**: 双专家并行独立审核（A: 84205f2 修复复核；B: 全分支 vs 规格 + 未跟踪文件卫生），主会话交叉验证分歧点
- **规格基准**: `D:\FlyBuddy\docs\2026-09-14-prediction-quality-redesign-design.md`（1020 行，含 v20/v23 修正条款）——注意 **WSL 仓库内仅有 324 行早期稿**，完整封版稿未落库（见 §5）
- **测试证据**: 6 个相关测试文件全跑 → **77 passed, 2 xfailed, 0 failed**（127s）；全分支相关单测累计 103 passed

---

## 1. 总体结论

| 审核域 | 判定 | 风险 |
|--------|------|------|
| commit 84205f2（复审修复增量） | ✅ **可合入（低风险）** | 低 |
| 全分支 vs 完整规格 | ⚠️ **不可直接合入主线（中偏高）** | 中偏高 |
| 未跟踪文件 | 需处置（1 入库 + 3 gitignore + 10 删除） | 低 |

**关键判定：84205f2 本身干净，可保留；不可合入的根因不在本次修复，而在全分支范围内
规格强制、却属于 Task 13-15 范围或本应在 Task 1-12 内完成的契约同步缺失。**

两个审核员对 84205f2 的判定不矛盾：A 审的是修复增量（干净），B 审的是 30 个 commits
的全分支（契约层不同步）。分歧点已由主会话对照 1020 行完整规格原文裁决：

- **"ccl" 基线协变量**：规格 L1084/L1275/L1337-1344 明文规定 baseline 用 `cov_override="ccl"`，
  84205f2 的硬编码**符合规格**，B 的 HIGH 存疑不成立。
- **Bonferroni 固定阈值 0.025**：规格 L345 明文"小批次降级 — 固定 Bonferroni 阈值"，
  非常数阈值**符合规格**，B 的 MEDIUM 存疑不成立。

---

## 2. 84205f2 修复复核（审核员 A）

| 复审问题 | 判定 | 证据 |
|----------|------|------|
| 1. wait_for_batch 超时墓碑 | ⚠️ **部分修** | 真修：`make_timeout_tombstone` + 路径版 append（锁+fsync+校验+去重），字段完整，测试锁定（praxist_supervisor.py:1461-1474）。**未修**：drain 完成后仍空等最多 7200 秒（timeout 默认 get_batch_timeout，goal.yaml 未配 batch_timeout_s） |
| 2. 冷启动基线 | ✅ **真修** | cov=`ccl`（praxist_supervisor.py:1403,1422，规格 L1289 约定）；`DailyModel()+HourlyModel(shared_model=...)` 与生产同构（generate_baseline_points.py:60-68）；失败可见 |
| 3. GOAL_SYMBOLS_SET | ✅ **真修** | 硬编码 8 品种 frozenset（praxist_supervisor.py:551），与 task.yaml / goal.yaml 三处一致，2 星品种不再凑数 |

**顺带修复**：路径版 append 的 batch_id+variant_id 去重顺带修掉了"已有 no_data 行会再追加 timeout"问题。
**残留 Minor**:①drain 后空等 7200s；②generate 每次重新加载 200M 模型 ×8 品种，无缓存；
③generate 模型加载失败 fail-open 降级 None（误导性错误信息）；④墓碑 symbol=""；
⑤goal.yaml:6 注释仍写 ev>0。fix 2/fix 3 无回归测试锁定。

**测试**: 77 passed, 2 xfailed（6 文件全跑）。

---

## 3. 全分支 spec 符合性（审核员 B，主会话已按完整规格裁决）

### 3.1 属于 Task 13-15 明确推迟范围（不阻塞本分支，但需列清单）

| 条款 | 现状 | 计划归属 |
|------|------|----------|
| C1. 非注册契约文件 config/praxist_task.yaml 仍写 objective.primary=ev_after_slippage、min_ic 0.05 | 有真实消费方（praxist_pareto.py:18、praxist_validate_task.py），系统声明的口径与 v23 直接矛盾 | **Task 13** |
| I4. Peer prompt（prompt_base.jinja2:33,84,118）仍教 peer 按 PF>1.05 且 ev>0 提报 | 快环仍按已废弃的 PF 门优化 | **Task 13** |
| I5. 无 migrate_verdicts_v1_to_v2.py，旧 checkpoint 无法转 v2 | 当前注册表 9 行全 v1 | **Task 14** |
| 端到端夹具测试缺失 | — | **Task 15** |
| goal.yaml 缺 `min(pass_variant_dir_accs) > 0.52` 类条件 | 自适应门可降至 0.50，过门变体 dir_acc 可能 <0.52 | **Task 13** |

### 3.2 属于本应在 Task 1-12 内完成但未完成的（真正缺陷）

| # | 问题 | 分级 | 证据 |
|---|------|------|------|
| D1 | **自适应门未接入慢环**：aligned_slow_loop.py:150-152 调 build_summary 时未传 `baseline_dir_acc`，慢环（v23 主产出路径）恒用 0.52，自适应门在主管线是死代码。此问题 Phase 4 审核已指出（#9），未修 | **Important** | aligned_slow_loop.py:150-152 vs run.py:107-113（run.py 路径有传） |
| D1b | `gate()` 不认旧 summarize 的 `DirAcc` 别名键（evaluator.py:170,249-262），旧路径 verdict 会被当 null → False | Important | 同 Phase 4 审核 #9 |
| D2 | **协变量词表冲突**：cov_family.py:12-19 受控词表 6 族（momentum/volatility/inventory/calendar/term_structure/macro_sentiment）vs covariate_pool.json 实际 9 族（calendar/oscillator/positioning/price_action/statistical/structure/trend/volatility/volume）。Level 1 精确匹配对全部池内协变量必然落空，sar_dist/ao_accel/hurst/vwap_deviation 等 → family="unknown" → 被 build_snapshot 排除出 families_hit，`n_families_hit≥1` 目标可达面被无谓收窄 | **Important** | cov_family.py:12-19 vs task_FM/config/covariate_pool.json |
| D2b | 慢环仍在 verdict 中塞 `margin_maxdd` 非法外字段（aligned_slow_loop.py:155-164，`_net_pnl_pts`/`calc_margin_maxdd_robust` import 保留），墓碑行无此字段 → registry 记录形态不一致 | Important | aligned_slow_loop.py:19,31-35,155-164 |
| D3 | PF/EV/MaxDD 计算未按规格 §8.1/§8.2 删除（evaluation_metrics.py:29,178,旧函数保留、monthly_backtest.py:372,409 逐点 pnl 仍算、summarize 仍产出 PF/EV/MaxDD/WinRate） | 部分符合 | evaluation_metrics.py:29,178,203,243；monthly_backtest.py:490-535 |
| D4 | `_trade_label` 未删（signal_contract.py:28,67,90） | Minor | cascade/signal_contract.py:28 |
| D5 | harvest_survivors docstring 仍写 EV 排序（实际按 dir_acc）；materialize_known_verdicts 仍写 ev>0 | Minor | praxist_supervisor.py:437-441,475 |
| D6 | `_proposal_priority_score` 仍用 v1 的 pf/ic 字段排序，对 v2 verdict 恒为 0，履历加分静默失效 | Minor | praxist_supervisor.py:558-563 |
| D7 | generate 模型加载失败 fail-open 降级 None 模型 | Minor | generate_baseline_points.py:61-68 |

### 3.3 符合项（不再复述，摘要）

自适应门公式、DM（NW HAC + HLN，配对<100→p=None）、BH-FDR per-symbol + 小批量固定 0.025、
v2 schema 26 字段/12 可空、墓碑工厂字段完备、慢环 OMP/MKL=4 前置 + 外层 try/except + 路径版 append
+ --batch-id + 失败也 ack、generate 的 cutoff 校验/锁/原子写、Supervisor 八件套、STEP=2/HORIZON=24、
registry v2 IO（flock+fsync 真 append、首写胜出去重、坏行保真、原子替换——全分支质量最高部分）。
测试 103 passed / 2 xfailed。

---

## 4. 未跟踪文件处置表

| 类别 | 项目 | 处置 |
|------|------|------:|
| 规格文档 | docs/superpowers/specs/2026-09-14-...design.md（324行稿） | 入库（specs/ 目录惯例）——但建议以 Windows 侧 1020 行完整版替换 |
| 审核报告 ×8 | docs/superpowers/2026-09-15/16-*.md（归档审核轨迹） | 入库 |
| 运行报告 ×1 | task_FM/docs/praxist_reports/20260914_..._gen1.md | 入库（目录惯例） |
| 环境补丁脚本 ×2 | scripts/patch_praxist_*.sh（扫描无密钥） | 入库 |
| 运行产物 | logs/、task_FM/.runtime_guards/ | gitignore |
| 代码备份 ×10 | *.bak*（supervisor×3, prediction_scheme, prompt_base, task.yaml, start_praxist.sh×2, aligned_verdicts.jsonl.bak, test_supervisor.py.bak） | 删除（git 历史即备份） |

**建议追加 .gitignore**（当前零覆盖，已确认）：
```gitignore
# 运行日志与运行时防护产物
logs/
task_FM/.runtime_guards/
```
追加规则不影响已跟踪的 models/regime_kmeans_1h.pkl.bak。

---

## 4b. 规格文档版本问题（双审核员一致发现，主会话验证）

- WSL 仓库内 `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md` 实为 **324 行**（§1-§12 初始设计，无 v20/v23 修正条款，无 §8.10）。完整封版稿不在 WSL 仓库内。
- 完整版在 Windows 侧 `D:\FlyBuddy\docs\2026-09-14-prediction-quality-redesign-design.md`（1020 行，主会话已确认含 v20/v23 修正条款：L199 自适应门公式、L219 DM、L296 BH-FDR、L345 固定 Bonferroni、L1084 `cov_override="ccl"` 原文）。
- **建议**：把 Windows 侧 1020 行完整版复制进 WSL 仓库（替换 324 行稿）并入库，作为 v23 的唯一权威 spec。落库后再按 §3.2 修复。
- 另注：分支实际领先 master 30 个 commits（25 文件 / +2801/-209），此前记录的"11 commits"只是 Phase 3 封段+Phase 4。

**Next**: 把完整版规格落库后，可按 §3.2 的 D1/D1b/D2/D2b 四项 Important 修复（预计 1-2 个 commit），其余为 Minor 与 Task 13-15。

---

## 5. 风险总评

- **84205f2**: 低风险，可保留。
- **全分支**: 中偏高。不存在数据损坏类缺陷（103 测试通过，IO/统计实现扎实），但契约层三处系统性不同步
  （praxist_task.yaml、peer prompt、协变量词表），其中 task.yaml 有真实消费方，系统会以与规格矛盾的口径运转。
  其中 contract 层（Task 13/14/15）是计划明确推迟的已知项；**真正计划内未完成的只有 D1/D1b/D2/D2b 四项**
 （自适应门慢环接入、DirAcc 别名、词表冲突、慢环 margin_maxdd 外字段）。
- **建议合入路径**：修复 D1/D1b/D2/D2b（1-2 commits）→ 未跟踪文件处置 + 完整版规格落库（1 commit）→
  Task 13-15 另行立项 → 合入主线。

---

**审核人**: 双专家独立审核（A: 84205f2 复核 / B: 全分支 spec 符合性），主会话交叉验证
**审核日期**: 2026-09-16
