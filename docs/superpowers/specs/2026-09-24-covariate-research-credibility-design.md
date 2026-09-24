# 协变量研究可信度重构 Spec（全局）

> 日期: 2026-09-24
> 上游: `FM_a_eg_jd_lh_expert_report.html`（2026-09-24）+ 宿主审核意见（同批次）
> 状态: **待宿主批准后实施**。实施计划另出（`docs/2026-09-24-covariate-credibility-impl-plan.md`）。
> 权威关系: 本文修订 v23 评估口径的**执行细节**（`n_eff` 口径、成功判定、留出协议、诊断字段），
> **不改 `gate()` 的质量筛选语义**。裁决公式唯一权威仍是
> `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`（下称 v23）。
> 范围: **全局**。适用于 `praxist_goal.yaml` 全部 24 个目标品种，不针对 EG/JD/LH 单点修补。

---

## 1. 目的与完成标准

专家报告把问题归因为"数据量不足 + 协变量覆盖不全 + 品种特性"，并建议"对 LH 的 NVI 精细调参以突破 0.50"。审核意见正确地指出：在评估口径未经审计前，这些结论都只是待检验假设。

本 spec 的目标不是提高过门数，而是**让"过门"重新具备证据含义**。完成标准（全部满足才算落地）：

1. 每一个 verdict 携带**窗口指纹**、**协变量指纹**、**有效样本量与实测 `n_eff`**、**方向准确率置信区间**、**DM 配对数**；缺任一字段的 verdict 视为不完整，不得进入成功判定。
2. `n_eff` 由数据自相关**实测**得出，不再是 `fallback_n_eff(588, 24, 2)` 的配置常数；`n_eff >= 50` 这道门必须真正具备筛选力（或明确废止）。
3. DM 检验在配对点不足时**显式落 `dm_status`**，禁止静默返回 `None`；当前"42/98 checkpoint 零配对却无告警"必须变成可观测。
4. 对照基线包含**无协变量 TimesFM**（当前基线是 `ccl` 协变量运行）。
5. 复权缺失、`bfill` 非因果、1-bar 前视三类数据缺陷**逐项出裁定**：修，或登记为已知偏差并量化。
6. 克隆现象由**指纹相同**判定，而非"指标四舍五入相同"；静默零填充改 fail-loud。
7. 预注册从自由文本升级为**带时间戳的机器可读登记**，且**前向确认集**由预注册时间切分，不依赖事后挑选。
8. **horizon 尾填充缺陷修复**：协变量按"未来可知性"强制分类（`known_ahead` / `persistence` / `self_referential` / `unknowable`），`known_ahead` 类真正携带未来外生信息，其余类显式标记为不携带；并有不变量测试证明修复**未引入前视**（§4.5）。
9. 24 个品种的可预测性判定**由实测功效派生**，取代手写 `symbol_status.json`。
10. **提案质量门生效**：协变量必须登记 `applicable_sectors` 且与目标品种匹配；`mechanism` 为可证伪的结构化声明（`driver`/`channel`/`expected_sign`/`test_point`），`crack_spread` 类跨板块错配提案被**确定性拒绝**（§4.7 W6.1）。
11. **Jev 预注册门为结果盲**：门控字段只取自 `jev_blind`（上下文中不含 `gate_pass`/`dir_acc`/`tier`/`fdr_pass`），`jev_informed` 与门控字段物理隔离（§4.7 W6.2）。
12. **身份、门槛、口径三项一致**：`variant_id` 由 `cov_fingerprint` 派生；成功判定要求基线存在；`dir_acc` 单一定义（零变动剔除而非判负）（§4.7 W6.4/W6.5/W6.6）。
13. **verdict 可归属**：携带 `proposer_model` / `run_id` / `peer_role`，报告可按模型与角色分解（§4.7 W6.3）。

---

## 2. 核实结论

证据等级：✅ 宿主会话内直接验证 · 🔬 代理实测（命令已跑，结论待复现）· 📄 代码阅读

### 2.1 评估口径

| ID | 事项 | 报告/审核说法 | 核实结论 | 证据 | 处置 |
|---|---|---|---|---|---|
| E1 | 过门门槛 | 报告把 `DirAcc≥0.50` 当硬门 | **门槛 = `max(0.50, min(0.52, baseline))`**；8 品种中 6 个 = **0.5000**，正好等于硬币抛掷率（z=0.00） | ✅ `evaluator.py:397-417`、`baseline_metrics.json` | 门槛保留为**筛选器**；成功判定换口径（§4.3） |
| E2 | `n_eff` | 报告称 "Gate=73"（当成质量门槛计数） | **误读**。73 是 `fallback_n_eff(588,24,2)` 的配置常数（`h=12`, `factor=8.028`, `588/8.028→73`） | ✅ `evaluation_metrics.py:377-396` | 改实测；报告该列作废 |
| E3 | `n_eff>=50` 门 | — | **恒真**（73≥50），零筛选力 | ✅ 同上 | 并入 E2 |
| E4 | 统计晋升 | — | 143 条中 **0 条**由 DM+BH-FDR 晋升；最小 DM p = **0.0302**（`sr_calendar_cyclical`），**无一条过 0.025**；3 条 `fdr_pass=true` 全是 `migrated_v1` 迁移产物且 `p_value=null` | 🔬 + ✅（`fdr_pass` 计数已验） | 修 `migrated_pass` 后门（§4.1） |
| E5 | BH-FDR | 审核要求多重比较校正 | **从未真正运行**：58 批次、每批 1–2 个变体 → 恒触发 `K<min_batch_size=4` 降级分支 → 实际是固定 Bonferroni `p<=0.025` | 🔬 `statistical_tests.py:229-312` | 批次语义重定义（§4.3） |
| E6 | DM 静默失效 | — | **42/98 checkpoint 与基线零重叠 cutoff** → `len(v_series)>=100` 为假 → `p_value=None`，**无告警**。根因：窗口随数据末端滑动 + `STEP=2` 相位随 `total` 奇偶翻转 → n 在 588/589 间跳 | 🔬 `monthly_backtest.py:256-264`、`statistical_tests.py:98-148` | 加 `dm_status` 显式字段（§4.1） |
| E7 | 对照基线 | 审核要求"与无协变量 TimesFM 比较" | **基线是 `ccl` 协变量运行**，不是无协变量 | ✅ `praxist_supervisor.py:2006,2025` `gbp.generate(sym_lower, "ccl", root)` | 补无协变量基线（§4.1） |
| E8 | 不确定性 | 审核要求置信区间 | verdict **无 CI、无标准误**；全库唯一 bootstrap 属 A2 LGBM 子项目，不进 FM_a 门 | 🔬 | 补 CI（§4.1） |
| E9 | verdict 可比性 | — | 窗口 `eval_start = total - EVAL_WINDOW_BARS` 随数据滑动，checkpoint 按**位置索引**续跑 → 同一变体不同时间跑在**不同窗口**上 → 143 条 verdict **彼此不可比** | 🔬 `monthly_backtest.py:259`、`aligned_slow_loop.py:116-137` | 落窗口指纹；跨窗口比较一律禁止（§4.1） |

### 2.2 数据与价格序列

| ID | 事项 | 核实结论 | 证据 | 处置 |
|---|---|---|---|---|
| D1 | 复权 | **完全没有复权**。`detect_rolls_from_price_gaps` / `apply_backward_adjustment_robust` 存在但守卫自毁：`main_continuous_1d` 恒有 `raw_close` 列（实测 2606 行全 NULL、`adjustment_factor` 全 0.0）→ 分支永不执行；1H 路径也无复权 | 🔬 `data_store.py:418-425` | 换月跳变入 label，加 roll 守卫（§4.1） |
| D2 | 换月污染 | `HORIZON=24` 窗口跨换月时，拼接跳变进入 `Δreal` 与 `dir_ok` 端点；**评估侧无 roll 守卫**。实测 SR_MAIN 1H 有 3 根 |1-bar 收益|>3%（+5.08%、−3.65%、−5.52%） | 🔬 | 同 D1 |
| D3 | `xreg_factors` 表 | **死表**。`get_xreg_factors()` / `get_xreg_matrix()` 除自身定义与内部互调外**无任何调用者**；仓库自述"预测时不读取此表"。协变量实为从 `kline_1h` 实时计算 | ✅ | 报告"数据量对比"表作废（§2.4） |
| D4 | `bfill` 非因果 | `oi_smooth = oi_smooth.bfill()`、`scale = mad.bfill()` → 用**未来**值回填 context 内 NaN | 🔬 `features.py:644,1975` | 改因果填充（§4.1） |
| D5 | 1-bar 前视 | `dt` 是 bar **开盘**时间（tqsdk kline `datetime`），回测 cutoff 取该 bar 的 `dt`（开盘），但同索引协变量与目标用该 bar **收盘**值（1 小时后才知）。注释声称防前视，实际只防日期级 | 🔬 `tqsdk_fetcher.py:204`、`monthly_backtest.py:305-309` | 修或量化（§4.1） |
| D6 | 自引用协变量 | `daily_slope` / `rsi_state` 的 horizon 尾值来自 TimesFM 自己的日线预测输出 → 该协变量的未来段是模型自身输出的函数，非外生信息 | 🔬 | 登记 + 排除出"外生协变量"口径 |

### 2.3 协变量通路

| ID | 事项 | 核实结论 | 证据 | 处置 |
|---|---|---|---|---|
| C1 | 协变量是否进模型 | **进**。经 `past_future_covariates` 作为额外 variate 通道，走 variate attention；实测能改变点预测 | 🔬 `hourly_model.py:211-226`、`model.py:461-585` | 通路成立，无需重建 |
| C2 | 克隆根因 | **确定性，非假设**：① 常数协变量 = **数学精确 no-op**（per-variate RevIN `(x-μ)/σ`，常数→0，实测 diff=0.000000）；② 全 NaN 协变量静默变 0 = 精确 no-op（实测 diff=0.0）；③ 多条构造路径静默零填充（`features.py:1198/1336/1367/1443-1448/1501`） | 🔬 | fail-loud + 指纹（§4.2） |
| C3 | 零填充审计覆盖 | 唯一守卫只覆盖 6 类（rsi_state/ha_body/reversal_shadow/stddev/nvi/qstick）；**ccl/oi/basis/vor/crack_spread 未覆盖**——而克隆高发族恰是 ccl/nvi/vor/crack_spread | ✅（守卫范围已验） | 扩到全部类型（§4.2） |
| C4 | `xreg_fallback` | 该标志在实盘侧被追踪（`live_ledger.py` 落库、`copilot.py:729` 分支），但在**产出 verdict 的评估路径**（`task_FM/evaluations/fm_eval/`、`monthly_backtest.py`）**零引用** → 回退到无协变量的运行被写成"用了协变量"的 verdict | ✅ | 评估路径消费该标志（§4.2） |
| C5 | 结构性天花板 | 每个协变量的 horizon 尾部都是常数（zeros/末值/decay；实测 `hz_std=0, hz_uniq=1`）→ 经 RevIN 归一化为 ~0 → **未来段不含外生信息** | 🔬 | 见 §4.5（开放） |
| C6 | ablation 混淆 | 实测（cf, 480bar, H=24）：真实 vs 清零 = 52.97 tick（价格 0.335%）；常数 vs 清零 = 0；**完全不带协变量 vs 清零 = 97.07（0.615%）**——结构性通道效应 > 内容效应，且样本中**符号相反**。仓库自身 ablation 把两者混同，且 `visualize=False` → `baseline_forecast` **从不落盘** | 🔬 | 分离报告 + 落盘（§4.2） |
| C7 | 死配置 | `prediction_scheme.py:132 xreg_covariates` 唯一消费者是打印语句；改它必然是静默 no-op | 🔬 | 删除或标注 |

### 2.4 对专家报告的裁定

报告的四条核心论据，逐条核实：

| 报告论据 | 裁定 |
|---|---|
| "三个品种 0 过门率，SR 68%" | **口径不可信**：门槛压在硬币率上，且 0 条经统计晋升。0% 与 68% 的差异不是品种差异，是噪声（E1/E4） |
| "数据量不足导致失败"（kline/xreg 行数表） | **论据失效**：`xreg_factors` 是死表（D3）；评估样本 `n=588` 对全部品种相同。报告该表整体作废 |
| "Metrics 克隆 → 协变量未被利用" | **结论方向错、机制对**：协变量确实进模型（C1），克隆来自常数/NaN 协变量的精确 no-op 与静默零填充（C2），不是"未被利用" |
| "LH 最接近阈值，精细调参可突破 0.50" | **反模式**：0.488 低于硬币率，0.012 = 0.2 SE。此为典型 p-hacking，**禁止**作为实施方向 |
| "Gate=73" | 误读（E2），该列作废 |
| 报告未涉及 | 复权缺失（D1）、DM 静默失效（E6）、基线非无协变量（E7）、verdict 不可比（E9）——均比报告所述更严重 |

### 2.5 污染审计

按三类污染重新扫了一遍。证据等级同 §2.1。

#### 2.5.1 数据污染

| ID | 污染 | 核实结论 | 证据 |
|---|---|---|---|
| X1 | 换月跳变入 label | 无复权 + 无 roll 守卫，拼接跳变进入 `Δreal` 与 `dir_ok` | D1/D2 |
| X2 | `bfill` 非因果 | 用未来值回填 context 内 NaN | D4 |
| X3 | 1-bar 前视 | cutoff 取 bar 开盘，同索引值取收盘 | D5 |
| X4 | **门槛跨品种不一致** | 6 个品种（cf/i/jm/ma/p/sh）**有 verdict 但无基线** → `gate()` 回退 `min_dir_acc=0.52`，比另 8 个品种的 **0.50 更严** → 同一 registry 并存两套门槛，`gate_pass` 跨品种不可比。且 `p` 的 3 条过门全部 `p_value=null`（无基线 → 无 DM 对照），本质是迁移产物 | ✅ 实测 |
| X5 | **`variant_id` 身份不稳定** | key = **请求的** `cov_override`，实际送入模型的矩阵可与之不同（C2/C3）→ 同名跨运行语义漂移 | C2/C3 |
| X6 | **registry 去重语义** | 按 `(batch_id, variant_id)` 去重 + `load_snapshot` **last-wins** → 同 `variant_id` 的多窗口记录被静默取一条 | E9 |
| X7 | **单条 verdict 内部可能混窗口** | checkpoint 按 `(symbol, idx)` **位置索引**续跑；窗口滑动后同一 `idx` 指向不同 cutoff → 一条 verdict 内部混合两个窗口的点。这比"跨 verdict 不可比"更严重：记录**自相矛盾** | E9 |
| X8 | **活表历史修订无防护** | `future_bar_guard.purge_future_bars` 只删 `date(dt) > max_allowed_daily_label(now)` 的**未来**行，不防**历史 bar 被修订**；`kline_1h` 由 `daily_update.py` 持续写入 | 📄 |
| X9 | **zero-move 强制判负** | `abs(delta_real) < eps → dir_ok=False`（零变动既非命中亦非失误，却被判负）。实测占比：sr 0.3% / rb **2.0%** / m 0.7% / cj 0.5% / eg 0.2% / jd 0.7% / lh 1.0% / ss 0.3% | ✅ 实测 |
| X10 | **`dir_acc` 同名两义** | gate 消费 full-sample 口径（零变动算 miss）；`calc_net_metrics` 另有 active-only `DirAcc`，而模块 docstring 宣传的是后者。同一名词两个含义 | 📄 |
| X11 | 预训练污染 | **风险低**。模型卡标注：Wikipedia Pageviews cutoff **Nov 2023**、Google Trends **EoY 2022**、GiftEvalPretrain（剔除与 fev-bench 重叠者）、合成数据。评估窗为 2026-01→2026-09，与已标注 cutoff 间隔 ≥2 年；且中国期货 1H 合约数据不太可能进入 Google 语料。**但 `GiftEvalPretrain` 自身 cutoff 未标注** → 残余风险，非零 | ✅ 模型卡 |

#### 2.5.2 思考链污染

| ID | 污染 | 核实结论 | 证据 |
|---|---|---|---|
| Y1 | **机制文本是装饰性的** | `crack_spread_*`（**裂解价差**，原油炼化概念）被评到 **LH 生猪、m 豆粕、cj 红枣、sr 白糖、ss 不锈钢、rb 螺纹钢** —— 这些品种与原油裂解无关。`mechanism` 仅要求 ≥40 字符、非空即 `+1.0` 分，**无任何"机制与协变量构造是否一致"的检验** | ✅ 实测 |
| Y2 | **Jev 判断被结果污染** | `_extract_relevant_history` 注入 Jev 的历史经 `v.get("gate_pass")` **过滤** → Jev 的合理性/新颖性建立在被选择偏差污染的集合上，**不是独立先验** | ✅ 代码 |
| Y3 | **`exploit` 角色被显式指示追噪声尾部** | 角色描述要求"在近门/过硬门未过 FDR 的变体上精炼 symbol×cov" → 搜索被制度性地导向噪声尾部 | 📄 |
| Y4 | **peer 被 best/near-miss 锚定** | `known_verdicts.inc.md` 注入 best `dir_acc` 与 near-miss 列表 → 假设从观测数字反推，机制文本成为事后叙事 | 📄 |
| Y5 | **提案模型无归属** | verdict schema **无** `model` / `provider` / `proposer` / `peer` 字段（实测探测全 ABSENT）→ primary（`claude-opus-4-7`）与 failover（`qwen3.7-plus`）的提案混入同一 registry，**无法归因、无法控制** | ✅ 实测 |
| Y6 | **协变量菜单被跨品种无差别枚举** | `oi` 出现在 11 个品种、`calendar_cyclical` / `ccl` 各 9 个、`bb_squeeze` / `nvi` 各 8 个 → 提案是菜单枚举，不是品种推理 | ✅ 实测 |

#### 2.5.3 治理与报告层污染

| ID | 污染 | 核实结论 |
|---|---|---|
| Z1 | **"探索次数"被当成绩** | 报告称"EG 探索最充分（24 次）"——尝试次数被表述为优点 |
| Z2 | **幸存者偏差进文档** | `results_summary.md` 只列 S/A 级；143 条真实分布（均值 0.4818、68.5% 低于 0.50）不可见 |
| Z3 | **tier 是 `dir_acc` 的再编码** | `neff_score` 只取 **7 或 10**（因 `n_eff` 是常数，近乎二值）→ 该分量几乎不 discriminate；S/A/B/C 标签制造虚假粒度 | ✅ 实测 |
| Z4 | **tier 含 `prescreen_score`** | tier 被 Jev 污染，而 Jev 又被 `gate_pass` 污染 → **环路** |
| Z5 | 报告把噪声理性化 | 专家报告"LH 最接近阈值，精细调参可突破 0.50" |
| Z6 | **`rb` 基线 0.396 远低于随机** | 与无复权/换月跳变耦合的**可检验假设**：换月拼接制造模型不可预测的大幅 `Δreal` → 压低 `dir_acc`。检验：剔除跨换月 cutoff 后重测 `rb` 基线；若显著回升则 D1/D2 是主因 |

**三条改变设计的发现**：Y1/Y6 → 需要**提案质量门**（W6.1）；Y2 → **Jev 必须结果盲化**（W6.2，直接修正 §4.3 W3.2 的设计）；X4 → **门槛一致性前置条件**（W6.6）。

---

## 3. 非目标

- **不**把 `gate()` 的 `effective_min` 改回全局 0.52 硬切（v23 已批准的品种自适应，回退会杀掉低基线品种的近门信号）。
- **不**修改 `.venv` / Praxist 发行源码。
- **不**新增基本面协变量数据通道（外部数据源、发布时滞登记）——宿主已划出本轮范围。
- **不**新增扣费后经济价值评估层（换手/回撤/风险暴露）——宿主已划出本轮范围。
- **不**恢复 PF/EV/MaxDD 进裁决链（v23 已退役）。
- **不**为单个品种（EG/JD/LH）做特调。全部改动按全局口径实施。
- **不**把"前向确认需要日历时间"当成拖延理由去继续刷变体；确认期内探索预算受 §4.3 约束。

---

## 4. 设计

### 4.1 W1 — 审计与不变量

**W1.1 修 `migrated_pass` 后门（E4）**

`registry_lib.pass_variants()` 现为 `gate_pass AND (fdr_pass OR migrated_pass)`。改为：

```
pass = gate_pass AND fdr_pass AND p_value is not None
```

`migrated_pass` 保留为**历史标记字段**（可读、可展示），但**退出成功判定**。历史 3 条迁移记录在新口径下自动降为"未检验"。禁止回填。

**层级说明**：`pass_variants()` 是**登记层**判定（"这条 verdict 算不算通过统计检验"）；§4.3 W3.4 是**成功层**判定（"这个假设算不算被确认"），后者在前者之上追加确认集与指纹约束。两层不得互相覆盖，也不得只实现其中一层。

**W1.2 `n_eff` 改实测（E2/E3）**

唯一家：`cascade/evaluation_metrics.py`。新增 `measured_n_eff(point_dir_ok_list)`：

```
n_eff = n * sigma0^2 / sigma_LR^2
```

其中 `sigma_LR^2` 复用 DM 检验已有的 Newey-West(Bartlett) 长程方差估计（`statistical_tests.py:154-227`），`sigma0^2` 为样本方差。**禁止**在别处再写一套。

- gated 协变量的 `n_eff` 必须在 **active 子集上独立重算**（关闭 `evaluator.py:269-274` 登记的开放问题 #4）。当前 `min(全量 ESS, n_active)` 被代码自述为"门偏松"，必须废止。
- verdict 同时落 `n_eff_nominal`（旧常数，仅供历史对比）与 `n_eff`（实测）。成功判定只读 `n_eff`。
- `n_eff >= 50` 门保留但改用实测值；若实测 `n_eff` 使全部历史变体不达标，**如实反映**，不得放宽阈值救结果。

**W1.3 DM 显式状态（E6）**

`build_summary` 落 `dm_status ∈ {"ok", "insufficient_pairs", "d_bar_nonpositive", "no_baseline"}` 与 `dm_pair_count`。`insufficient_pairs` 时 `p_value=null` **且 stderr 打 WARN**，并计入 supervisor 的可见统计（禁止静默）。

窗口对齐的根因必须一并修：`eval_start` 的奇偶漂移改为**按绝对 cutoff 时间戳对齐**，禁止用位置索引续跑 checkpoint（`aligned_slow_loop.py:116-137` 的 `(symbol, idx)` 键改为 `(symbol, cutoff_ts)`）。

**W1.4 无协变量基线（E7）**

新增 `baseline_points_{sym}_nocov.jsonl`：同一窗口、同一 cutoff、**不传 `past_future_covariates`** 的 TimesFM 运行。DM 检验的对照改为**该无协变量基线**；`ccl` 基线降级为"另一个协变量变体"，仅供诊断对照。

理由：审核意见明确要求"与无协变量的 TimesFM 比较"。用协变量运行当基线，等于在问"这个协变量比 ccl 好吗"，而非"协变量有没有用"。

**W1.5 窗口指纹与 CI（E8/E9）**

verdict 新增：

| 字段 | 类型 | 含义 |
|---|---|---|
| `window_start_ts` / `window_end_ts` | str | 评估窗口首末 cutoff（绝对时间） |
| `window_n` / `window_parity` | int | 名义点数与相位 |
| `dir_acc_ci_lo` / `dir_acc_ci_hi` | float | 95% CI，用**实测** `n_eff` 的二项标准误 |
| `roll_in_horizon` | bool | 该 cutoff 的 `idx+1..idx+HORIZON` 是否跨换月 |
| `price_series_adjusted` | bool | 该次评估的价格序列是否已复权 |
| `cov_fill_version` | str | horizon 填充策略版本（W5 落地前后不可比） |
| `dm_status` / `dm_pair_count` | str / int | 见 W1.3 |

**跨窗口指纹不同的 verdict 禁止直接比较**。supervisor 与报告生成器必须拒绝跨窗口排序（当前 `known_verdicts.inc.md` 的"best dir_acc"与 tier 排名会跨窗口比较，必须加窗口一致性过滤）。

**W1.6 价格序列缺陷裁定（D1/D2/D4/D5）**

- **复权（D1/D2）**：优先修守卫，让 `apply_backward_adjustment_robust` 在生产路径真正执行；1H 路径补 roll 处理。若短期无法修，则**必须**加 `roll_in_horizon` 守卫——跨换月的 cutoff 从 `dir_ok` 分母中剔除（或单独成组报告），且该剔除量必须落盘可见。
- **`bfill`（D4）**：`oi_smooth` / `scale` 的 `bfill` 改因果填充（`ffill` + 冷启动 NaN 显式处理）。禁止用未来值回填。
- **1-bar 前视（D5）**：二选一——(a) 把 cutoff 改为该 bar 的**收盘**时间（`dt + 1h`），使"cutoff 时点已知的信息"与所用值一致；(b) 若维持现状，必须在 verdict 落 `cutoff_convention="bar_open"` 并把该 1-bar 偏差**量化**进报告。推荐 (a)，因为它同时消除 D5 与 D6 的口径歧义。

**W1.7 死表与死配置（D3/C7）**

`xreg_factors` 表在 `data_store.py` 的方法 docstring 标注 `[DEAD TABLE — 预测路径不读取]`；所有分析脚本（含专家报告那类数据量对比）禁止引用其行数。`prediction_scheme.py:132 xreg_covariates` 删除或标注 `[DEAD CONFIG]`。

### 4.2 W2 — 协变量使用诊断

把审核意见的"协变量未利用"从**推断**变成**可验证事实**。

**W2.1 协变量指纹（C2）**

verdict 新增 `cov_fingerprint`：

```
{
  "keys": ["daily_slope", "ccl", "rsi_state"],   # 实际送入模型的**有序**键
  "matrix_sha256": "<past_future_covariates 的 float32 字节哈希>",
  "n_channels": 3
}
```

键取自 `hourly_model.py:211` 的 `covariate_keys`（**实际**集合），不是请求的 `cov_override`。

**克隆判定从此确定**：`matrix_sha256` 相同 = 同一输入，无论请求名是否不同。禁止再用"指标四舍五入相同"推断克隆。

**W2.2 逐协变量有效性（C2/C3）**

verdict 新增 `cov_effective`，对每个实际键记录：`std`、`n_unique`、`nonzero_frac`、`horizon_std`、`horizon_n_unique`。

判定规则（确定性，写入代码而非文档）：

- `std == 0` 或 `n_unique == 1` → 该通道**必然 no-op**（RevIN），落 `inert_constant=true`
- `horizon_std == 0` → 未来段无外生信息，落 `horizon_flat=true`
- `nonzero_frac == 0` → 落 `all_zero=true`

**静默零填充改 fail-loud**：`features.py:1198/1336/1367/1443-1448/1501` 等路径在零填充时 `stderr` 打 WARN 并把该通道标记进 verdict。零填充审计测试覆盖**全部**协变量类型（关闭 C3 缺口），新增的协变量类型必须同步登记，否则测试失败。

**W2.3 消融落盘与效应分离（C6）**

- `visualize=False` 导致的 `baseline_forecast=None` 必须消除：评估路径**强制**计算并落盘"有/无协变量"的逐点端点差。
- verdict 新增两个**分离**字段：
  - `ablation_content_delta`：真实协变量 vs **清零同形**（同通道数）→ 纯内容效应
  - `ablation_structural_delta`：**完全不带协变量** vs 清零同形 → 纯结构性通道效应
- 报告必须**分开呈现**，禁止合并成"协变量贡献"。

理由：实测两者符号相反（C6）。合并会把结构性偏移误读为协变量价值。

**W2.4 `xreg_fallback` 贯通（C4）**

评估路径消费该标志：`xreg_fallback=True` 的 verdict 落 `covariates_used=false`，**不得**参与成功判定，且 supervisor 统计中单列。回退运行与真实协变量运行必须可区分。

### 4.3 W3 — 预注册与前向确认（Jev 升级为门）

**W3.1 预注册登记（取代自由文本）**

新文件 `task_FM/config/preregistry.jsonl`，append-only，是预注册的**唯一家**：

| 字段 | 说明 |
|---|---|
| `prereg_id` | 唯一 ID |
| `symbol` / `cov_fingerprint_keys` | 假设对象 |
| `mechanism` | 机制陈述 |
| `predicted_direction` | 方向 |
| `kill_condition` / `promote_condition` | **结构化**阈值（数值 + 字段名），非自由文本 |
| `registered_at` | **时间戳（UTC）**，写入后不可修改 |
| `confirm_from_ts` | 确认集起点 = `registered_at` 之后首个可用 cutoff |
| `jev` | Jev 三问输出快照（plausibility / novelty / effect_size）+ 判定 |
| `n_planned` | 该假设计划评估的点数 |

`_proposal_priority_score` 的 `+1.0` 非空字符串奖励**废除**；改为"无有效预注册 → 不入队"。

**W3.2 Jev 从降权改门（事前）**

现状：Jev 只做**事后调度降权**（`_apply_prescreen_score`）。改为**事前门**：

- `compute_skip_suggested=True` → **拒绝入队**（不再是 −15/−30 分）
- 判定写入 `preregistry.jsonl` 的 `jev` 字段，作为预注册的一部分
- **门控判定必须结果盲**：只允许取自 `jev_blind`（上下文不含 `gate_pass`/`dir_acc`/`tier`/`fdr_pass`）。现行 `_extract_relevant_history` 注入 `gate_pass=True` 过滤后的战绩，会让 Jev 继承选择偏差——用它做门控等于把偏差洗成"独立判断"。详见 §4.7 W6.2（该条为**前置依赖**，未落地前本工作包不得实施）
- 保留降级路径：`TYPESAFE_API_KEY` 缺失或连续超时 → `status="degraded"`，此时**降级为人工确认队列**，禁止静默放行（当前 degraded 会被当成"无意见"）

**W3.3 确认集定义（取代不存在的留出期）**

- 确认集 = `cutoff >= confirm_from_ts` 的评估点。**注册时该数据不存在**。
- **禁止**用切分现有 588 点来制造确认集：切分后确认集 `n_eff ≈ 29`，SE ≈ 0.093，需 DirAcc ≈ 0.68 才显著——等于确认不了任何东西，是假动作。
- 确认需要日历时间，这是本 spec 的**显式代价**，不是缺陷。
- 复测通道（`_retest_candidates`，checkpoint 只算新点）就是确认集的天然实现，无需新机制。

**W3.4 成功判定换口径**

```
confirmed = (gate_pass                        # 质量筛选，保留
             AND fdr_pass                      # 统计晋升（真实检验）
             AND p_value is not None
             AND covariates_used == True       # 非 xreg_fallback
             AND window_fingerprint 一致        # 同一窗口
             AND 在确认集上 DM 显著优于无协变量基线)
```

`gate_pass` 退回 v23 §5 本来的角色——**质量筛选器，不是成功**。

**W3.5 功效表与可检出下限**

verdict 落 `mde_dir_acc`（minimum detectable effect）：

```
SE          = 0.5 / sqrt(n_eff)                 # 二项，H0: p=0.5
mde_dir_acc = baseline_dir_acc + z * SE
```

`z = 1.645`（**单侧 α=0.05**，与 DM 检验同侧，不得改用双侧 1.96）。

**当前实测**：`n_eff=73` → SE=0.0585 → MDE = baseline + 0.0962。以 `rb`（baseline 0.396）为例 MDE≈0.492，以 `sr`（baseline 0.502）为例 MDE≈0.598。**整个 0.50–0.52 波段在 `sr`/`ss` 这类高基线品种上原理上不可检出**。

报告必须公开该下限。若目标效应小于 MDE，**唯一正确动作是按功效计算累积样本量**，而不是继续加变体。

**W3.6 预算与多重比较纪律**

- `praxist_goal.yaml` 的 `max_cycles: 999999` / `cpu_hours: 999999` / `token_budget_m: 999999` / `deadline: 2099-12-31` 是**无界搜索 + 无多重比较记账**，与预注册纪律直接冲突。改为按 §4.6 的阶段预算。
- 必须登记"**总共计划试多少个变体**"（`n_planned_total`），并在 `preregistry` 里累计实际数。BH-FDR 的 `K` 取该累计数，而不是每批 1–2 个——否则 FDR 永远退化为 Bonferroni 且批次语义无意义（E5）。
- 未预注册的变体可以继续探索（探索自由），但**不计入成功判定**，且必须落 `prereg_id=null` 以示区分。

### 4.4 W4 — 协变量库重整

**依据改为诊断证据，而非过门率。**

- 归档判据：某协变量在**跨品种多数**（≥60% 的已评估品种）上满足 `inert_constant=true` 或 `all_zero=true`，或 `ablation_content_delta` 在多数品种上低于浮点噪声（`< 1e-3 * price`）。
- 这正好化解 2026-09-19 spec 的反对理由（"3–4 条 verdict 不够判死一族"）——现在判据是**机制性**的（该通道恒为常数 → 数学上必然 no-op），不是统计性的，不依赖样本量。
- 输出 `task_FM/config/covariate_family_verdict.json`：族×品种矩阵 + 归档理由 + 证据指针。
- **单品种惰性不整族归档**（族在某品种有效、在另一品种惰性要能分别判定）。

### 4.5 W5 — horizon 尾填充（**已裁定：纳入本轮修**）

**事实（C5）**：每个协变量的 horizon 尾段都是常数（zeros / 末值 / decay），实测 `hz_std=0, hz_uniq=1`。经 per-variate RevIN 后常数尾归一化为 ~0，**未来段不含任何外生信息**。协变量只能通过 context 编码间接影响预测——C6 实测的内容效应（0.335%）就是在该天花板下的表现。

**宿主裁定：本轮修。** 这是**现有架构缺陷**，不是"新增基本面协变量通道"，故不违反 §3 范围。

#### W5.1 协变量按"未来可知性"强制分类

`task_FM/config/covariate_pool.json` 每个条目**必须**新增 `horizon_known`，取值为**受控词表**四选一。缺失即校验失败（禁止默认值兜底）：

| `horizon_known` | 含义 | horizon 填充策略 | 是否算外生信息 |
|---|---|---|---|
| `known_ahead` | cutoff 时点**确实已知**未来值（日历、合约到期日、已公布的排产/节假日） | 填**真实未来值** | ✅ 是 |
| `persistence` | 未来不可知，但可用末值延续近似 | 填**末值** | ❌ 否（RevIN 下 ~0，必须标记） |
| `self_referential` | 未来值来自**模型自身输出**（现状：`daily_slope`、`rsi_state` 取自 TimesFM 日线预测） | 现状保留，但**必须标记** | ❌ 否（自引用，不得当外生） |
| `unknowable` | 既不可知也无法近似（库存、持仓、基差、基本面） | 填**末值** + 标记 | ❌ 否 |

**唯一家**：该分类只写在 `covariate_pool.json`，代码、文档、报告一律读它。禁止在 `features.py` 里按协变量名硬编码判断。

#### W5.2 填充实现

- `known_ahead` 类：从**cutoff 时点可确定的来源**取未来值。日历类可由 `generate_trading_dates` 直接生成；合约到期类由合约日历生成。**禁止**从任何含未来数据的表取值。
- 其余三类：填末值（替代当前 zeros/decay），并落 `horizon_fill="persistence"`。
- **`horizon_std > 0` 只允许出现在 `known_ahead` 类**。其余类 `horizon_std == 0` 是**预期行为**，落 `horizon_flat=true` 并计入 §4.2 的有效性字段。

#### W5.3 前视防护（本工作包的安全关键项）

修 horizon 填充**最容易引入前视**。必须有不变量：

1. `features.py` 的 horizon 填充函数**只接受** `horizon_known` 参数决定分支，不接受协变量名。
2. 新增测试：对每个 `horizon_known != "known_ahead"` 的协变量，断言其 horizon 段**逐值等于** context 末值（即确实是 persistence，而非泄漏了真值）。
3. 新增测试：对每个 `known_ahead` 协变量，断言其 horizon 值**可由 cutoff 时点已知的输入重算得出**（构造用例：改变 cutoff 之后的数据，horizon 填充值不得改变）。
4. 变体评估若使用了 `known_ahead` 协变量，verdict 落 `horizon_exogenous=true`；否则 `false`。§4.3 的成功判定**不因该字段加分**——它只用于诊断"这次评估是否真的拿到了未来信息"。

#### W5.4 验收标准

- 至少一个 `known_ahead` 协变量（预期 `calendar_cyclical`）满足 `horizon_std > 0`。
- 该协变量的 `ablation_content_delta`（§4.2 W2.3）相对"常数尾"基线**显著上升**——这是"尾填充确实让协变量产生了未来段效应"的唯一可信证据。若上升不显著，**如实报告**：说明该架构下外生信息的可达增益有限，W5 的收益上限被证实。
- 全部非 `known_ahead` 协变量的 `horizon_flat` 标记与实际一致（不得有漏标）。

**注**：W5 会改变协变量的输入矩阵，因此 **W5 落地后全部历史 verdict 不可与新 verdict 比较**。§4.1 W1.5 的窗口指纹必须扩展一位 `cov_fill_version`，跨版本比较一律禁止。

### 4.6 阶段二 — 品种分级（全局 24 品种）

按 W1–W4 落地后的新口径重跑，对全部 24 个目标品种出统一判定：

| 判定 | 条件 | 处置 |
|---|---|---|
| **可预测** | 存在 ≥N 个 `confirmed` 变体，且 `mde_dir_acc <= baseline + 目标效应` | 正常目标 |
| **需更多样本** | 效应量疑似存在但 `mde` 高于目标效应 | 给出**所需 n 与预计日历周期**（按功效计算），不靠刷变体 |
| **当前不可验证** | `mde_dir_acc` 已高于任何合理目标效应（如短历史品种实测 `n_eff` 过低） | **停止探索**，如实报告边界 |

**N 由该品种自身功效计算得出**，不是全局常数——短历史品种的 N 更高（更难确认）或直接判为不可验证。

**品种状态改为派生**：`symbol_status.json` 的手写 `DEAD`/`HOLD`（现为 eg=DEAD、jd/lh=HOLD）退休，改由上述判定**计算**得出，代码可复现。手写状态是临时绷带，与"全局统一口径"直接冲突。

**成功条件重写**（`praxist_goal.yaml`）：从 `n_gate_pass_variants >= 10` 改为 `n_confirmed_variants >= N(该品种)`。现 Phase 1 的 `avg_dir_acc_gate_pass >= 0.51` 同样作废——0.51 远低于 MDE 0.615，是不可检出的目标。

### 4.7 W6 — 污染控制与提案质量门

治 §2.5 的三类污染。**本工作包与 W1–W5 同等优先**：W1–W5 修的是"测量"，W6 修的是"被测量的对象本身如何被生成"。

#### W6.1 提案质量门（治 Y1 / Y6）

`mechanism` 从"≥40 字符"改为**可证伪的结构化声明**，四个必填字段：

| 字段 | 要求 |
|---|---|
| `driver` | 驱动变量（必须是该协变量构造中真实存在的量） |
| `channel` | 传导路径（从 driver 到该品种价格的因果链） |
| `expected_sign` | 预期符号 |
| `test_point` | 可观测的检验点（若机制为真，应在何处看到什么） |

**确定性一致性检查（代码判，不靠模型判）**：

- `covariate_pool.json` 每个协变量**必须**新增 `applicable_sectors`（受控词表，取值同 `config/sector_map.py`）。
- harvest 时校验：目标品种的 sector ∈ `applicable_sectors`。不匹配 → **拒绝入队**，除非提案提供 `cross_sector_rationale` 且 `channel` 字段非空。
- 缺失 `applicable_sectors` 的协变量即校验失败（禁止默认"全部适用"兜底）。

这一条直接拦掉 `crack_spread` 类提案（原油炼化 ≠ 生猪/白糖/螺纹钢/红枣/豆粕/不锈钢）。**禁止**用 LLM 判断"机制是否合理"来替代该检查——sector 匹配是确定性事实。

#### W6.2 Jev 结果盲化（治 Y2）— **修正 §4.3 W3.2**

`_extract_relevant_history` 现注入 `gate_pass=True` 过滤后的历史。这使 Jev 的"合理性/新颖性"建立在被污染的选择结果上，**Jev 因此不是独立先验，不能直接当预注册门**。

改为**两次分离调用**：

| 调用 | 上下文 | 用途 | 可否进 `preregistry` 门控字段 |
|---|---|---|---|
| `jev_blind` | **结果盲**：只给机制文本、品种 sector、协变量的**构造定义**；**不得**含 `gate_pass` / `dir_acc` / `tier` / `fdr_pass` / near-miss 列表 | 预注册门 | ✅ 仅此可 |
| `jev_informed` | 现行含战绩上下文 | 仅诊断 | ❌ 禁止 |

`skip_suggested` 的判定**只允许**取自 `jev_blind`。`jev_informed` 的输出必须落库但与门控字段物理隔离（不同键名 + 测试断言不可互读）。

理由：用被污染的历史去"预筛"，是把选择偏差洗成看似独立的判断——比不做预筛更危险，因为它给出虚假的独立性。

#### W6.3 提案归属（治 Y5）

verdict 新增 `proposer_model`、`proposer_provider`、`run_id`、`peer_role`。缺失即校验失败。报告必须能按模型/角色分解（如"opus 提案 vs qwen failover 提案的过门率"），否则 failover 期间混入的提案无法归因。

#### W6.4 身份与去重（治 X5 / X6 / X7）

- `variant_id` 改为**由指纹派生**：`{symbol}_{cov_family}_{matrix_sha256[:12]}`。请求名降级为 `cov_requested` 仅保留可读性。**禁止**用请求名作身份键。
- `load_snapshot` 的 last-wins 改为**按窗口指纹分组**；同 `variant_id` 跨窗口视为**不同记录**，禁止静默覆盖。
- checkpoint 键从 `(symbol, idx)` 改为 `(symbol, cutoff_ts, cov_fingerprint)`；窗口指纹或填充版本变化即**作废重算**，禁止复用位置索引。

#### W6.5 指标口径统一（治 X9 / X10 / Z3）

- `dir_acc` 只保留**一个**定义。零变动点（`|Δreal| < eps`）从分母**剔除**并落 `n_zero_move`——零变动既非命中亦非失误，判负会机械压低 `dir_acc`（rb 实测 2.0%）。同时报告剔除前后两值，防止口径争议。
- active-only 口径**改名** `active_dir_acc`，仅 gated 路径使用，消除同名两义。
- tier 的 `neff_score` 改用实测 `n_eff`；若实测后仍近乎常数（现只取 7 或 10），**从 tier 中移除该项**，而不是留一个不 discriminate 的分量制造虚假粒度。
- tier 的 `prescreen_score` 改用 `jev_blind`（W6.2），切断 Z4 环路。

#### W6.6 门槛一致性前置条件（治 X4）

成功判定**要求** `baseline_dir_acc is not None`。无基线的 verdict 落 `gate_basis="fallback_0.52"`，**不参与跨品种比较，也不参与成功判定**，直到无协变量基线补齐。PR4 的 `baseline_points_{sym}_nocov.jsonl` 必须覆盖全部**有 verdict 的品种**（当前缺 cf/i/jm/ma/p/sh 六个），而不只是现有 8 个。

#### W6.7 历史修订防护（治 X8）

verdict 落 `context_hash`：该 cutoff 的 context 窗口（480 bar 的收盘序列）内容哈希。后续重算发现哈希变化 → 该 verdict 标记 `data_revised=true` 并**退出成功判定**。`future_bar_guard` 只防未来行，历史修订必须靠哈希自证。

#### W6.8 预训练污染登记（治 X11）

登记为**残余风险**，附模型卡证据（已标注 cutoff 2022/2023 vs 评估窗 2026；`GiftEvalPretrain` 自身 cutoff 未标注）。

建议**诊断性**检验（不作门控）：评估窗内**时间分半**——若模型在窗内早期与晚期的相对表现无系统性差异，则无窗内预训练泄漏迹象。该检验的结论必须如实报告，包括"无法判定"。

---

## 5. 测试要求

每个行为必须有**失败先于实现**的测试（仓库既有风格：`tests/test_praxist_fm_evaluator.py`、`tests/test_supervisor.py`、`tests/test_covariate_audit.py`）。最低用例：

1. `measured_n_eff` 对已知自相关序列返回与解析值一致的估计；常数序列 `n_eff→1`。
2. gated 协变量的 `n_eff` 在 active 子集上独立重算，与全量值不同。
3. `pass_variants` 在 `p_value=None` 时返回 False，即使 `migrated_pass=True`。
4. `dm_status="insufficient_pairs"` 时 `p_value is None` **且** stderr 有 WARN。
5. `cov_fingerprint.matrix_sha256` 对"请求不同名但实际矩阵相同"的两个变体返回**相同**哈希；对真实不同矩阵返回不同哈希。
6. 常数协变量 → `inert_constant=true`；全 NaN 协变量 → 同样标记（二者都不得静默通过）。
7. 零填充路径触发 WARN 并在 verdict 留痕；零填充审计覆盖**全部**协变量类型（新增类型未登记则测试失败）。
8. `xreg_fallback=True` → `covariates_used=false` 且不参与成功判定。
9. 跨窗口指纹不同的两个 verdict **不能**被排序函数放在一起（报告生成器测试）。
10. `roll_in_horizon=true` 的 cutoff 从 `dir_ok` 分母剔除，且剔除量落盘。
11. `bfill` 移除后，含 NaN 的 context 不再用未来值填充（构造用例断言）。
12. 预注册：无有效 `prereg_id` 的提案不入队；`registered_at` 写入后不可修改（写保护测试）。
13. Jev `skip_suggested=True` → 拒绝入队；`status="degraded"` → 进人工队列而非静默放行。
14. `mde_dir_acc` 计算与 `n_eff` 一致；`n_eff=73` 时 ≈ 0.615。
15. **W6.1**：`crack_spread_*` 对 `lh`/`m`/`sr`/`rb`/`ss`/`cj` 被拒绝入队；`applicable_sectors` 缺失即校验失败；提供 `cross_sector_rationale` 的提案可通过。
16. **W6.2**：`jev_blind` 的输入上下文中**不含** `gate_pass`/`dir_acc`/`tier`/`fdr_pass` 任一字符串（断言）；`skip_suggested` 只来自 `jev_blind`；`jev_informed` 的输出键与门控键不同名且测试断言不可互读。
17. **W6.3**：缺 `proposer_model` 的 verdict 校验失败；报告能按模型分解过门率。
18. **W6.4**：请求不同名但矩阵相同的两个提案得到**同一** `variant_id`；同 `variant_id` 跨窗口不被静默覆盖；`(symbol, cutoff_ts, cov_fingerprint)` 变化即重算。
19. **W6.5**：零变动点从 `dir_acc` 分母剔除并落 `n_zero_move`；剔除前后两值都可读；`active_dir_acc` 不与 `dir_acc` 同名。
20. **W6.6**：`baseline_dir_acc is None` 的 verdict 落 `gate_basis="fallback_0.52"` 且不参与成功判定与跨品种比较。
21. **W6.7**：context 内容变化后重算的 verdict 落 `data_revised=true` 并退出成功判定。
22. **W6.8**：时间分半诊断能输出结论（含"无法判定"），且结论字段不参与门控。

---

## 6. Key Decisions

1. **`gate()` 公式不动，改的是"过门≠成功"这个误用。** v23 §5 本来就要求 `gate_pass AND (fdr_pass OR migrated_pass)`；漏洞在 `migrated_pass` 后门（E4）与 `gate_pass` 被当成成功（E1）。改成功判定，不改质量筛选器。
2. **`n_eff` 改实测是还债，不是改口径。** `evaluator.py:269-274` 已把它登记为开放问题 #4 并自述"门偏松"。关闭它是登记在案的修正。
3. **确认靠前向数据，不靠切分现有 588 点。** 切分后确认集 `n_eff≈29` → MDE≈0.68，等于确认不了任何东西。切分是假动作，会给出虚假的"已确认"安全感。
4. **接受"多数品种当前不可验证"是合法结果。** 这是本次审计最可能的真实产出，也是止住预算空转（快环最近两次 harvest 入队 0 条）的唯一诚实路径。禁止为了让结果好看而放宽阈值。
5. **`xreg_factors` 死表从一切分析口径剔除。** 专家报告的核心论据建立在其行数上，该论据失效。分析脚本引用该表行数即为错误。
6. **协变量指纹是克隆判定的唯一依据。** 指标四舍五入相同只能"疑似"，指纹相同才是"确定"。这是确定性问题，用代码判，不靠模型推断。
7. **结构效应与内容效应必须分开报告。** 实测两者符号相反，合并会把"多塞了通道"误读成"协变量有价值"。
8. **Jev 从降权改事前门。** 事后降权挡不住"试到够数"；事前门 + 时间戳预注册才能约束多重比较。
9. **品种状态改派生。** 手写 DEAD/HOLD 与全局统一口径冲突，且不可复现。
10. **零填充改 fail-loud。** 静默零填充是克隆的根因之一，沉默本身就是缺陷（v23 已有"fail visibly"精神）。
11. **Jev 不能在被污染的历史上做门控判断。** 现行 `_extract_relevant_history` 注入 `gate_pass` 过滤后的战绩，使 Jev 继承了选择偏差。用它当预注册门会把偏差洗成"独立判断"——比不做门控更危险，因为它提供虚假的独立性。故门控字段只取自结果盲的 `jev_blind`（§4.7 W6.2）。
12. **机制合理性用确定性检查，不用模型判断。** `crack_spread` 评到生猪/白糖/螺纹钢/红枣/豆粕/不锈钢，证明机制文本是装饰性的。sector 匹配是可判定的**事实**，交给代码；"机制是否讲得通"是**判断**，不能作为入队闸门（v23 Rule 5：能确定性判的不要走模型）。
13. **`variant_id` 必须由指纹派生。** 请求名作身份键会让同一 id 跨运行指向不同输入（X5），并使"同名"看起来可比。身份必须绑定实际输入。
14. **零变动点不该判负。** 零变动既非命中亦非失误；判负机械压低 `dir_acc`（rb 实测 2.0%），且对低波动品种/时段系统性不利。剔除并单列，而不是计为 miss。
15. **tier 不得含不 discriminate 的分量。** `neff_score` 在 `n_eff` 为常数时只取 7/10，近乎二值；留着它让 S/A/B/C 看起来比实际更有区分度。要么用实测 `n_eff`，要么移除。
16. **历史数据修订必须自证。** `future_bar_guard` 只防未来行；活表的历史 bar 可被后续写入修订。verdict 必须带 context 哈希，否则"同一 cutoff 的历史值"会随时间漂移而无人察觉。

---

## 7. 开放问题

宿主可裁定，不挡 W1/W2 实施：

1. **D5 1-bar 前视**：修 cutoff 为收盘时间（推荐），还是量化后保留现状？修会改变全部历史 verdict 的口径，需要重跑。
2. **历史 143 条 verdict 的处置**：建议**不回填、不删除**，全部标记为 `legacy_untrusted`，仅作探索记录。新口径从 W1 落地后写入的 verdict 起算。若宿主希望重跑历史变体，需明确重跑清单与预算。
3. **`praxist_goal.yaml` 的 24 品种目标集**：若阶段二判定多数品种"当前不可验证"，是否把目标集收缩到"可预测"品种？本 spec 不预设。
4. **文档漂移**：`docs/runbook_praxist_three_loop.md:147` 仍写着旧的 `n_one_star_symbols_hit >= 4` 成功条件，与 live `praxist_goal.yaml`（per-symbol 三阶段）不一致。建议随本 spec 一并修正。
5. **W5 的四类归属**：`covariate_pool.json` 的 `horizon_known` 初版分类由谁定？建议由宿主/研究侧逐协变量确认（尤其 `known_ahead` 的准入——它直接决定是否引入未来信息，宁可保守）。本 spec 只定词表与不变量，不代填分类。
6. **W6.1 的 `applicable_sectors` 初版归属**：同样建议逐协变量确认。`crack_spread` 显然应限 `eg`/`sc` 类能化品种，但边界案例（如 `oi`/`ccl` 这类交易所通用数据）需要你裁定是"全板块"还是逐板块列举。本 spec 只定机制，不代填。
7. **X11 预训练污染的处置深度**：登记为残余风险（推荐，附模型卡证据），还是要求做时间分半诊断（W6.8）后才放行阶段二？分半诊断不能证伪泄漏，只能提供"无迹象"证据。
8. **`dir_acc` 零变动剔除的兼容性**：剔除会改变全部历史 `dir_acc` 数值（rb 约 +2pp）。是否接受历史 verdict 全部标记 `legacy_untrusted`（推荐），还是要求重算以保持可比？重算需重跑慢环。

---

## 8. PR 切分

| 顺序 | 标题 | 主要文件 | 依赖 |
|---|---|---|---|
| PR1 | 成功判定去后门 + DM 显式状态 | `registry_lib.py`, `evaluator.py`, `statistical_tests.py` + 测试 | 无 |
| PR2 | `n_eff` 实测（含 active 子集独立重算） | `evaluation_metrics.py`, `evaluator.py` + 测试 | 无（可与 PR1 并行） |
| PR3 | 窗口指纹 + CI + 跨窗口排序拒绝 | `evaluator.py`, `praxist_supervisor.py`, 报告生成器 + 测试 | PR1 |
| PR4 | 无协变量基线 | `generate_baseline_points.py`, `praxist_supervisor.py` + 测试 | PR1 |
| PR5 | 协变量指纹 + 有效性字段 + 零填充 fail-loud + 审计扩容 | `hourly_model.py`, `features.py`, `evaluator.py` + 测试 | 无 |
| PR6 | ablation 落盘 + 效应分离 | `hourly_model.py`, `monthly_backtest.py`, `evaluator.py` + 测试 | PR5 |
| PR7 | `xreg_fallback` 贯通评估路径 | `evaluator.py`, `monthly_backtest.py`, `aligned_slow_loop.py` + 测试 | 无 |
| PR8 | 价格序列缺陷（复权守卫 / `bfill` / roll 守卫 / cutoff 口径） | `data_store.py`, `features.py`, `monthly_backtest.py` + 测试 | 宿主裁定 D5 |
| PR9 | **horizon 尾填充修复（W5）**：`horizon_known` 分类 + 填充实现 + 前视不变量 | `covariate_pool.json`, `features.py`, `hourly_model.py` + 测试 | PR5（需指纹字段） |
| PR10 | 预注册登记 + Jev 事前门 + 预算纪律 | `praxist_supervisor.py`, `typesafe_prescreen.py`, `preregistry.jsonl`, `praxist_goal.yaml` + 测试 | **PR14**（Jev 盲化）、PR1–PR4 |
| PR11 | 协变量族裁定（族×品种矩阵） | `covariate_family_verdict.json`, 裁定脚本 + 测试 | PR5/PR6/PR9 |
| PR12 | 阶段二 品种分级 + 成功条件重写 + `symbol_status` 退休 | `praxist_goal.yaml`, `praxist_supervisor.py` + 测试 | PR1–PR11、PR18 |
| PR13 | **提案质量门**（`applicable_sectors` + 结构化 `mechanism`） | `covariate_pool.json`, `praxist_supervisor.py`, `prompt_base.jinja2` + 测试 | 无 |
| PR14 | **Jev 结果盲化**（`jev_blind` / `jev_informed` 分离） | `typesafe_prescreen.py`, `praxist_supervisor.py` + 测试 | 无 |
| PR15 | **提案归属字段**（`proposer_model` / `run_id` / `peer_role`） | `evaluator.py`, `registry_lib.py`, `praxist_supervisor.py` + 测试 | 无 |
| PR16 | **身份与去重**（`variant_id` 由指纹派生 + 窗口分组 + checkpoint 键） | `registry_lib.py`, `aligned_slow_loop.py`, `evaluator.py` + 测试 | PR5 |
| PR17 | **指标口径统一**（零变动剔除 + `active_dir_acc` 改名 + tier 去伪粒度） | `evaluation_metrics.py`, `evaluator.py`, `tier_classifier.py` + 测试 | PR2 |
| PR18 | **门槛一致性 + 历史修订防护 + 预训练登记** | `evaluator.py`, `registry_lib.py`, `generate_baseline_points.py`, `docs/` + 测试 | PR4 |

每个 PR 必须带绿测试，禁止把"下一步再写测试"写进 diff。

**依赖说明**：

- **PR9（W5）必须早于 PR12（品种分级）**——尾填充修复改变协变量的可达增益，分级必须在修复后的口径上做，否则会把架构天花板误判成"品种不可预测"。
- **PR14（Jev 盲化）必须早于 PR10（Jev 事前门）**——否则会把被污染的判断固化成门控字段，且事后难以分辨哪些门控决定是盲的。
- **PR16 依赖 PR5**（指纹字段）——身份派生需要指纹先存在。
- **PR17 与 PR18 会改变历史 `dir_acc` 与门槛语义**，故 PR12 必须在其后；历史 verdict 建议统一标记 `legacy_untrusted`（§7 开放问题 8）。
- PR8（价格序列）依赖宿主对 D5 的裁定，可延后，但**必须早于 PR12**——复权与 roll 守卫会改变全部 `dir_acc`。
