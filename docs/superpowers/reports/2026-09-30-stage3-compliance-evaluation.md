# Stage 3 设计文档符合性评估报告（FM_a 协变量可信度）

- 日期：2026-09-30
- 评估对象：`docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15/v16，1586 行）及其 Stage 3 交付物（381f31e 及后续）
- 方法：只读审计（audit112–118）+ 全量 pytest + 与项目自审报告（`2026-09-29-spec-implementation-audit.md` @ eecf05a）交叉核对
- 性质：第三方符合性评估，评估期不改仓内任何文件；处置行动见 `plans/2026-09-30-v4-convergence-implementation-plan.md`

## 一、三层结论

| 层 | 结论 | 依据 |
|---|---|---|
| L1 交付物 vs 设计文档 | **基本满足** | PR-C1/C2/C5/C6 兑现；项目自审 P1/P2/P3 已由 381f31e 修复，本次逐项实证 |
| L2 流程与测试 | **满足**（带 1 项高优先缺口 A） | 分层 commit、配对测试在位；但全量基准当时为 2 failed |
| L3 Stage 4 前置 | **未实施（合规延期）** | PR-D1 预注册、PR-D2 goal 重写均未动；Q7 未裁定，spec 认可该延期 |

**总结论：满足「阶段 3 完成」的主体判定；不满足「可进阶段 4」的出口条件**（A/B/E 必修 + Q7 裁定）。

## 二、全量测试基准（评估时点）

`pytest tests/ -q` = **2 failed / 1644 passed / 7 skipped / 1 xfailed**（858.82s，audit116）。

两失败均为「测试未随生产收紧回填」型，生产语义符合 spec：

1. `test_prc6_horizon_known.py::test_schema_version_bumped` —— 时间炸弹：断言 `pool.updated == date.today()`，而 `updated` 是 PR-C6 落地日的一次性 stamp，自落地次日起每日假失败。
2. `test_prediction_quality_e2e.py::test_e2e_snapshot_goal_combo` —— 夹具 `_v2_row` 假指纹 `"pf"` 被 `build_snapshot` 的 `only_protocol=_current_protocol_fingerprint()`（5eab80d）整行过滤 → `min_pass_variant_dir_acc=None`。

> 处置：实施计划 0.1，已修复（119e28c），基准恢复 **1646 passed / 0 failed / 7 skipped / 1 xfailed**（323s）。
>
> 评估期自勘误：初判「夹具缺 A1 字段被确认门拦」不成立——夹具已含全部 A1_REQUIRED_FIELDS 18 项；`n_dir_total` 等四分母不在现行强制清单（见发现 E），失败机制唯一为假指纹。

## 三、八项发现（A–H）

### A（高）2 个测试失败
见上节。处置 → 0.1（已完成）。

### B（高）PR-A1 半实现：窗口语义未收口
- checkpoint 键仍 `(symbol, idx)`（`scripts/aligned_slow_loop.py:127`）——同品种重启即复用旧 checkpoint，评估集随数据末端的滑动窗口漂移（X7 混窗口结构风险）。
- `eval_start = max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)`（`scripts/monthly_backtest.py:294`）——相对滑动而非绝对锚定，违背 W1.3「窗口可复现」意图。
- 处置 → 2.1（绝对锚定）+ 2.2（键改造）+ 2.3（窗口语义入指纹 v4）。

### C（中）variant_id 未接线
生产注册表 0/43 行带指纹后缀；`build_variant_id` 生产调用者 0（唯一合成调用者为 `restart_readiness_check.check_phase7` 的格式断言 `ss_momentum_`+12hex）。变体身份仍退化为 `symbol_covariate` 字符串。处置 → 2.4。

### D（中）W6.7 context_hash 生产休眠
43/43 新协议行 `context_hash=None`；增量追加路径不写哈希。处置 → 2.5。

### E（高）v3 行缺顶层四分母（潜伏确认门阻断）
16 条 v3 行缺顶层 `n_dir_total / n_dir_active / n_zero_move / n_zero_ratio`。该四项**不在现行 A1_REQUIRED_FIELDS**；待 2.6 将其纳入强制清单后，旧 v3 确认行会被 `a1_missing_fields` 拦截。当前全为 exploration 行故无生产影响。处置 → 2.6（writer 补字段）+ v4 收口（旧 v3 行随指纹升级自然退场，无需回填迁移）。

### F（低）legacy_untrusted 0/143
143 条遗留行无一被标 untrusted；靠 schema 区分（v1 无指纹）+ only_protocol 过滤双重兜底。无需行动，观察项。

### G（低）supervisor 注释漂移
`scripts/praxist_supervisor.py` ~:536 注释仍写「pass_variants = gate_pass 且 (fdr_pass 或 migrated_pass)」；W1.1 已退役 migrated_pass 通道，代码行为正确、仅注释错。处置 → 2.7。

### H（合规延期）PR-D1/D2 未实施
预注册与 goal 重写均未动，被 Q7（最小可检测效应/样本量裁定）阻塞。spec 认可。处置 → 阶段 3。

## 四、与项目自审报告的差异

- 自审 P1/P2/P3（PR-C1/C2/C5/C6）已由 381f31e 兑现——本评估逐项实证，无异议。
- 自审盲区 = 本报告 **A / B / E / G** 四项（测试漂移、窗口语义、四分母、注释漂移）。
- 自审「完成声明每轮需重跑三层核对」的结论成立。

## 五、评估期自勘误

1. 变体身份函数实际导出名 `build_variant_id`（非 derive_variant_id）；「生产接线 0」结论不变。
2. W1.4 基线重生记录修正：实为 **8/9**（fu 仍 v2 `bd851c9ca0730dc5`，588 行），非 9/9。此点随后被死代码 spec 审核独立证实。

## 六、处置顺序（已进入实施计划）

1. 0.1 修 2 测试（已完成，119e28c）
2. 0.2 报告入库 + 0.3 死代码 spec 修订
3. 0.4 宿主裁定包（Q7 备忘录等）
4. 阶段 2 v4 代码批次 + 一次重启 + 重生波
5. Q7 裁定后阶段 3（Stage 4）
