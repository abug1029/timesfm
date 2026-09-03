# FM_a 数据管理策略

## 核心原则：预测驱动采集 (Predict-then-Collect)

**不使用 cron 定时任务。** 每次预测请求时自动检查并补齐数据。

### 流程

```
用户请求预测 → 数据校验 → 数据过期? → 自动采集 → 重新校验 → 预测
                              ↓ 新鲜
                           直接预测
```

### 入口统一

所有预测入口在加载模型前，调用 `ensure_fresh_data(symbol)`:

| 入口 | 脚本 | 自动采集 |
|------|------|:---:|
| 级联预测 | `cascade_predict.py` | ✅ `--collect` / `--collect-if-stale` / auto-collect |
| 信用≥2星预测 | `three_star_predict.py`（历史名；`list_by_stars(2)`） | ✅ `ensure_data()` |
| 协变量扫描 | `covariate_scan.py` | N/A (回测模式, `cutoff_date` 跳过时效性) |
| 月度回测 | `monthly_backtest.py` | N/A (回测模式) |
| 指标分析 | `variety_analysis.py` | ✅ `--collect` / `--no-collect` |

### 手动采集 (仅运维用途)

```bash
python scripts/collect_1h.py              # 全品种 1H
python scripts/collect_1h.py ss rb        # 指定品种
python -m data.cli collect --all          # 全品种日线
python -m data.cli collect ss rb          # 指定品种日线
```

---

## 数据架构

- kline_1d / main_continuous_1d: TqSdk 主力连续合约 (`{SYM}_CONT`)
- kline_1h: 主力连续 1H (`{SYM}_MAIN`)
- 数据来源: TqSdk `KQ.m@`

## 数据验证管线

预测前自动校验 (fail-fast):
1. 数据量：1H ≥ 48 bars，日线 ≥ 60 天
2. 时效性：按星期放宽 (周一=3天, 周二=4天, ...)
3. 合约一致性、Gap 检测
4. 交易时段感知 bar 级检查

## Watch List

- FU 燃料油: TqSdk 历史数据有 384 天缺口 (2017-06 → 2018-07)
- 残差分析显示系统性高估 +2%

## 策略变更日志

2026-08-30 A3-Lasso 前置诊断 — XReg-Lasso 方向关闭 (报告: reports/research/20260830_a3_lasso_diagnostic.md):
- 无 TimesFM 稀疏线性诊断 (6 弱信号品种): 修复训练标签前视泄漏后 4/6 OOS IC<=0, 无信号
- 首次高 PF (CF 1.48/AO 1.39) 为诊断自身标签重叠泄漏假信号 (训练标签最后 23 行触未来), 已修复+独立因果性复核 PASS
- 生产级 XReg-Lasso walk-forward 不启动 (诊断 DOA + A2-P1/P2 负先验)
- CF/AO 边缘正 IC (+0.10/+0.08) 列入数据积累后复评观察项
- 方法论: 诊断与 213 次回测矛盾时优先怀疑诊断自身 bug — 本次当场验证

2026-08-30 数据层加固 (MaxDD 闭环 + 法定节假日 + ensure_data 原子化):
- MaxDD>100% bug 闭环: 根因确认已在 2026-08-21 修复 (evaluation_metrics.py cumprod+clamp, 8 测试覆盖); -265%/-134% 为修复前旧口径 (batch_f1 2026-08-18); Phase 11 裁决以 PF 为准不受影响 (backtest_registry 头部已标注)
- 新增 `data/holidays.py`: 2025/2026 官方节假日+调休表 (来源国务院通知, chinese-calendar 核对); API: is_holiday/is_workday/next_trading_day/count_holidays_between; 未知年份 (2027+) 回退纯周末逻辑
- `trading_calendar.py`: next/prev_weekday 委托 holidays (感知节假日+调休); max_allowed_daily_label 加纯周末口径保底 (cap 永不低于现状, 表错误不可能误删有效 bar); guard 删除逻辑不变
- `data_validator.py`: 1H 时效性检查扣除区间内法定节假日 (交易日口径), 长假不再误报; 错误信息提示未收录年份
- `ensure_data` 原子化 (three_star_predict.py): 返回 {ok, error} 结构, 失败打印 [FAIL] 不再静默; 原实现内联为 _ensure_data_impl (逻辑零变更)
- three_star 阶段0 强制采集 + cascade_predict/predict --collect 适配结构化结果
- 新增测试: test_holidays.py (11), test_ensure_data_result.py (3)

2026-08-29 Phase 15b 修复重跑 + Phase Q1 协变量质量审计 (实证: reports/research/20260829_phase15b_rerun_results.md + 20260829_phase_q1_covariate_quality.md):
- Phase 15b: StdDev `_calc_stddev()` 改 returns std **保留** (5/6 改善, AO PF 0.76→0.90 +0.14, UR -0.11 例外待复评); VWAP 衰减填充 **回滚** 为常数填充 (0/6 改善, 3/6 退化)
- Phase Q1 D1 RSI 自适应边界 **REJECT**: JD PF 1.09→1.07, P combo 1.10→1.00; 固定边界 91% 零输出 = 隐式信号门控, 信息量↑ ≠ 预测力↑
- Phase Q1 D2 QSTICK 窗口 / D4 NVI lookback **CANCEL** (Phase 15 已证 0 GREEN); D3 SKIP (已归档); D5 Horizon 填充 **PAUSE** (P15b 已否定衰减)
- Phase Q1 D6 审计框架 **ACCEPT**: tests/test_covariate_audit.py 19 测试 (平稳性/范围/NaN/前视偏差/信息量)
- 实验性协变量代码 (rsi_state_adaptive, qstick_w28/w42, nvi_w60/w120) 裁决后已全部从 features.py 移除, 无 SCHEMES 变更

2026-08-21 Phase 12 BU 组合协变量 (实证: docs/backtest_registry.md BU 表):
- 目标: 为 BU 沥青 (short_horizon, ha_body PF=0.79 FAIL) 寻找组合协变量
- 方法: 2 cov × 2 模式组合穷举 (calendar_cyclical, hourly_slope, ha_body, reversal_shadow)
- BU 沥青: ha_body → calendar_cyclical+hourly_slope 固化 (v2 GREEN, PF=0.79→1.01, 1 GREEN)
  - 边际 GREEN (PF 刚过 1.0), stars=1 不变, short_horizon_only=True 不变
  - 关键洞察: calendar (季节性) + hourly_slope (日内趋势) 互补，ha_body 对 BU 短窗口无效
- 其他 3 品种组合未突破: AO 0 GREEN, CF 0 GREEN, JM 0 GREEN, FG 0 GREEN

2026-08-20/21 Phase 11 单协变量穷举结案 (实证: docs/backtest_registry.md 各品种表):
- 目标: 对 20 品种 (含 SH 待固化) 进行 7 协变量 (ha_body/calendar_cyclical/hourly_slope/rsi_state/reversal_shadow/oi/ao_accel) 完整 walk-forward 穷举
- 规模: 138/138 作业全完成 (含 M 补跑), 34 GREEN, 12 品种固化替换, 3 品种基线保持
- 固化替换 (12 品种, Phase 11):
  - SS: reversal_shadow → calendar_cyclical (PF=1.09, 4 GREEN 中 rsi/hs/oi/ao 均 GREEN, calendar 最稳)
  - SP: ha_body+calendar → calendar_cyclical (PF=1.07, 消融 ha_body)
  - FU: ha_body → calendar_cyclical (PF=1.23, baseline PF=0.93 FAIL)
  - I: ha_body → reversal_shadow (PF=1.06, baseline ha_body PF=0.98)
  - RB: ha_body → rsi_state (PF=1.09, 审核修正: hs=1.05 → rsi 更高)
  - TA: ha_body → calendar_cyclical (PF=1.03 ⚠️ 边界)
  - EG: ha_body+oi+reversal_shadow → calendar_cyclical (PF=1.04)
  - CJ: ha_body → hourly_slope (PF=1.29 🔥 全场最高, 5 GREEN)
  - LH: ha_body → rsi_state (PF=1.24, 4 GREEN 中 rsi 最强)
  - JD: hourly_slope → rsi_state (PF=1.09, 审核修正: hs=1.06 → rsi 更高)
  - BU: ha_body → calendar_cyclical+hourly_slope (PF=1.01 Phase 12, 见上)
  - AO: hourly_slope+calendar 保持 (0 GREEN, best PF=0.73)
- 基线保持 (3 品种):
  - M: ha_body+calendar (PF=1.13) 优于 Phase 11 calendar 单协变量 (PF=1.06)
  - P: rsi_state+reversal_shadow (PF=1.10) 优于 Phase 11 cal/hb (PF=1.02)
  - SR: rsi_state+oi+calendar (PF=1.10) 优于 Phase 11 rev=1.03 (边界)
- SH 烧碱 (待固化): 0 GREEN (best PF=0.90), 不纳入 SCHEMES
- 共性规律: calendar_cyclical 成为最广泛适用的单一协变量 (SS/SP/FU/TA/EG 5 品种替换)

2026-08-17 G003/G004 Short 品种专项 — P 棕榈油协变量替换 (实证报告: reports/research/20260817_g001_diagnostic_results.md):
- 目标: 诊断 short_horizon 品种 (BU/P/CF/AO/CJ) 经济失效原因
- 方法: G001' 诊断矩阵 (16格/200pt均匀采样) → G002 分层 → G003 396pt WF → G004 裁决
- P 棕榈油: ha_body+reversal_shadow → rsi_state+reversal_shadow 固化 (v2 GREEN-EV Rule3: PF 0.89→1.014 +13.5%, EV -0.056→+0.007 翻正, MaxDD -79.3%→-51.7% 改善35%)
  - stars=1 不变 (PF 刚过线, EV 微正, 不足以升 2★)
  - 关键洞察: 1H RSI (均值回归因子) 比 ha_body (趋势因子) 更契合短持仓窗口
- BU 沥青: rsi_state 替换 FAIL (PF 0.84→0.83 退化), 保持 ha_body
  - 诊断 (200pt) 显示 C2h PF12=0.990 改善, 但 396pt WF 未复现 → 诊断只能做方向参考
- CF 棉花: 4 配置全 FAIL (unrecoverable), 保持 ha_body+calendar_cyclical
- AO 氧化铝: full_signal GREEN-EV (PF 0.925→1.078), 但 n=149 underpowered, 需另开工单
- CJ 红枣: 阳性对照 PF=1.298 ≈ G005 1.26, 管线验证通过
- 跨品种规律: 1H RSI 替换 ha_body 在 BU/P 有效, CF 无效; 叠加 oi 普遍有害
- 教训: 200pt 诊断对 BU 有误导 (PF12=0.990 但 396pt WF 退化), 最终裁决必须用 396pt WF

2026-08-04 Phase 9 有毒品种专攻 (实证报告: reports/research/20260804_phase9_toxic_variety_study.md):
- 目标: 为 ha_body 有毒品种 AO/JD 寻找替代协变量 (CF 已确认最优, 排除)
- 方法: 纯完整 walk-forward 回测 (AO 10候选 + JD 8候选), v2 裁决, 不用 scan 快筛
- AO 氧化铝: hourly_slope -> hourly_slope+calendar_cyclical 固化 (v2 PASS: MAPE 2.55%->2.15% -15.7%, PF 1.03->1.20 +16.5%, EV +0.014->+0.090 +543%, MaxDD 改善17.3%)
  - 代价: DirAcc 56%->52% (-3.7pp); n=193 underpowered 待复验
  - ha_body 确认有毒 (EV -0.054, MaxDD -57.92%); 其余 8 候选全 FAIL
- JD 鸡蛋: 8 候选全 FAIL, rsi_state+oi 确认最优 (PF=1.31 全场最高, EV=+0.133)
  - hourly_slope+oi 最接近 (EV +0.131, PF 1.30) 但 MAPE 退化未达 v2
  - calendar_cyclical+gated_slope 计算异常 FAIL
- 关键发现: ha_body 对 AO/JD 有毒机制确认; calendar_cyclical 叠加 hourly_slope 在 AO 上有效 (趋势+季节性互补)

2026-08-03 Phase 92026-08-03 Phase 9 二星→三星协变量优化 (实证报告: reports/research/20260803_phase9_two_star_to_three_study.md):
- 目标: 所有 2 星品种 (15个) 协变量提升至 3 星 (DirAcc≥65% + PF≥1.15)
- 硬约束: 3 星评分 (`_stars_from_metrics`) 要求 DirAcc≥65% 为硬性必要条件; DirAcc 55-64% 即使 PF≥1.4 也仅 2 星
- 运行器: `scripts/two_star_candidate_runner.py` (nohup 脱机, 73 作业, 单模型加载, JSONL 断点续跑)
- critic: `scripts/two_star_critic.py` (v2 判定复用 `phase4d_parse_results.verdict()` + 3 星检查)
- 结果: `reports/two_star_results.jsonl` | 进度页: `reports/two_star_to_three_progress.md`
- 实证 (全量 15/15 品种, 73/73 作业完成):
  - ✅ 可改善型 (7品种, v2 PASS, 已固化): FU ha_body (55.0%), FG ha_body (55.3% +4pp最大), CJ ha_body (55.2% GREEN-MAXDD), M ha_body+calendar (58.1% PF1.47), LH ha_body (58.4% underpowered), P ha_body+reversal_shadow (53.5% PF1.48), I ha_body (52.3% GREEN-MAXDD)
  - ❌ 已最优型 (8品种, 全FAIL): RB/TA/CF/EG/JD/JM/BU/AO 当前配置已最优, 所有候选退化 (注: AO ha_body有毒用hourly_slope, BU边际)
- 3星不可达: DirAcc 天花板 ~58%, 距 65% 差 7pp; 1H 级联预测上限约 58%
- ha_body 模式: 通用 DirAcc 推升器但非万能 (对 JD/CF 有害, 对 RB/TA/EG 无效)
- 组合叠加规律: 单协变量通常最优, 加 oi/reversal_shadow/calendar 普遍退化 (例外: M ha_body+calendar)
- scheme DirAcc 全 stale: FU 59.1%->53.5% (-5.6pp), FG 59.1%->51.3% (-7.8pp), AO 36.4%->56.0% (+19.6pp); 优化必须用同窗口新鲜 baseline
- ha_body 有毒品种: AO (EV转负, MaxDD翻倍), 验证了 'ha_body 非万能' 结论
- **固化 7 品种**: config/prediction_scheme.py 已更新
  - FU/FG/LH/CJ -> ha_body (单协变量)
  - M -> ha_body+calendar_cyclical (组合)
  - P -> ha_body+reversal_shadow (组合)
  - I -> ha_body (从 rsi_state+oi+ha_body 简化)

2026-08-02 Phase 9 一星品种优化 (EG/JD 固化, MA 暂缓):
- EG 乙二醇 -> 2 星 (新进): 10候选, ha_body+oi+reversal_shadow 全维最优 (EV+0.112, PF 1.25, v2 PASS PF+13.6%), 固化
- JD 鸡蛋 -> 2 星 (新进): 8候选, rsi_state+oi 全维最优 (EV+0.133, PF 1.31, v2 PASS PF+20.2%), 固化
- MA 甲醇: 7候选 396pt walk-forward 全 FAIL v2, 最优 ao_accel (EV+0.057, PF+1.121, PFΔ+9.3%<10%), 维持 hourly_slope+oi, 1 星
- 共性问题: 3 品种 DirAcc 52-56%, 距 3 星 (65%) 差 9-13pp, 受限于品种可预测性上限
- 关键发现: rsi_state+oi 对 JD 大幅改善但对 MA 退化; ha_body 对 EG/MA 正确但对 JD 有害

2026-08-02 Phase 9 TA 协变量优化 (bb_squeeze → ha_body 固化):
- 目标: TA 协变量配置提升至 ≥2 星 (当前 2 星, 目标 3 星)
- Round 1 (4 候选): bb_squeeze+calendar (全面退化), ha_body+calendar (盈利改善未达 v2), rsi_state+oi+calendar (退化), calendar_cyclical replace (全面退化)
- Round 2 (4 候选 ha_body 变体): **ha_body replace 全维最优** (DirAcc +2pp, MAPE -4.9%, EV +46%, PF +12.6%, MaxDD 改善 20%), ha_body+bb_squeeze/ha_body+rsi+oi/ha_body+oi 均退化
- v2 verdict: PASS (ordinary) — MAPE -4.9%≥3%, PF +12.6%≥10%, MaxDD 未恶化
- 固化: config/prediction_scheme.py TA covariate_type: bb_squeeze → ha_body
- 关键发现: 所有组合均退化, ha_body 单独最优; PF=1.43 全系统最高; DirAcc 58% 距 3 星 (65%) 差 7pp, 受限于品种可预测性上限
- 测试: 18/18 PASS, 导入 OK

2026-08-01 Phase 8a+8b 跨品种 Crack Spread 验证 (归档,不固化):
- Phase 8a PX-TA: 跨品种协变量框架建立 (calc_crack_spread + _align_feedstock + feedstock_cache DI 咽喉点),PX-TA 实证弱信号 (MAE +2%),完整 backtest 确认 EV/PF/MaxDD 微幅改善但未达 v2 门槛,effective_n=120 UNDERPOWERED,不固化
- Phase 8b SC-FU/BU: SC 原油注册 INE + 采集 (9,994 1H bars) + OLS ratio 标定 (FU=4.7191, BU=2.8067, returns+滚动500中位数) + 6 模式完整 backtest (396 eval/模式)
  - FU: crack_spread_slope replace 退化 (MAE+24%, EV-20%), additive 盈利改善 (EV+5%, PF+2%, MaxDD 改善 4%)
  - BU: crack_spread replace 多维改善 (DirAcc+2pp, EV+7%, PF+2%, WR+2pp), additive 类似; 7pt scan 有误导 (未进 TOP 5, backtest 揭示改善)
  - effective_n=264 < 350, UNDERPOWERED, 不固化 (~15 个月后 2027 Q4 可复评)
- 关键结论: 裂解价差 (crack spread) 在两对品种对上均不提供充分的短期预测信号; 经济直觉 ≠ 预测信号; scan 的 MAE 指标对 BU 有误导,完整 backtest 揭示 scan 未覆盖的改善信号
- 新增文件: config/crack_spread_pairs.py (fu/bu ratio), scripts/calibrate_crack_ratio.py (OLS 标定), tests/test_crack_spread_fu_bu.py (11 tests)
- 全量回归: 74/74 PASS
- 实证文档: reports/research/20260731_phase8a_summary.md + 20260801_phase8a_backtest_report.md + 20260801_phase8b_summary.md

2026-07-30 Phase 4d-2 判据升级 v2 + M Replace 固化 + SR Additive 固化:
- 判据升级 v2 (docs/validation_criteria.md): 旧"纯 OR 三选一"暴露 SP 漏洞 (MAPE 达标但 PF/EV 微降). 新增 5 条规则:
  - R1 MaxDD 一票否决 (相对恶化 >20% 否决) / R2 盈利保护 (仅 MAPE 达标时 PF 退化 <=2%)
  - R3 EV 翻正绿色通道 (负->正自动 PASS) / R4 MaxDD 回撤绿色通道 (改善 >=30% + EV 未退化 -> PASS)
  - R5 小样本标记 (n<350 负结果 underpowered)
- M 豆粕: 改 Replace 固化 (vor+calendar -> calendar_cyclical 单协变量, 剥离高噪声 vor). replace 全维优于 additive (MAPE 1.87<1.96, PF 1.24>1.19, MaxDD -22%>-28%, decay 1.36<1.47)
- SR 白糖: 改 Additive 固化 (rsi_state,oi +calendar_cyclical). Rule4 MaxDD 绿色通道 (MaxDD -19.55%->-9.81% 腰斩, EV +22%)
- JD 鸡蛋: Replace 固化 (gated_slope -> calendar_cyclical 单协变量). Rule4 MaxDD 绿色通道 (MaxDD -49%->-34% 改善31%), 精度持平 (DirAcc 50%/MAPE 2.49%), 纯回撤改善型
- UR: 确认 underpowered (1H 数据缺口, 密度 102 条/月 vs 141, n=303<350), 搁置待补数据
- phase4d_parse_results.py 实现 v2 verdict (GREEN-EV/GREEN-MAXDD/UNDERPOWERED/R1-VETO/R2-GUARD)
- 验证: tests/test_calendar_cyclical.py 7/7 PASS; 导入 OK; parse_results v2 输出符合预期

2026-07-30 Phase 4d 季节性固化回测 2026-07-30 Phase 4d 季节性固化回测 (calendar_cyclical 落地):
- 矩阵: 6 品种 (CF/M/SP/SR/JD/UR) × 3 模式 (baseline/replace/additive), walk-forward 2020-2025, 17 symbol-mode, 0 错误
- 判据 (三选一): MAPE 相对降 ≥3% / DirAcc ≥+3pp / PF 相对 +≥10%
- 固化 (covariate_types 追加 calendar_cyclical, 保留原主协变量):
  - CF 棉花: ha_body+calendar -> MAPE 1.66%->1.51% (-9%), DirAcc 51%->56% (+5pp), PF 0.94->1.09 (+16%), EV 翻正. 全达标
  - M 豆粕: vor+calendar -> MAPE 2.62%->1.96% (-25%), DirAcc 52%->55% (+3pp). 达标
  - SP 纸浆: ha_body+calendar -> MAPE 1.91%->1.78% (-6.8%). 达标 (精度补充, DirAcc/PF 持平)
- 不固化: SR (DirAcc+2pp/MaxDD 腰斩但未达硬门槛, 边界), JD (全持平), UR (全维变差, 日历有害)
- 脚本: scripts/phase4d_calendar_matrix.sh (矩阵) + phase4d_parse_results.py (判定)
- 验证: tests/test_calendar_cyclical.py 7/7 PASS; prediction_scheme 导入 OK
- 回测产物: reports/monthly_backtest/phase4d_incremental_results.jsonl (17 行)

2026-07-29 Phase 4+5+6 + 4 方向工程加固:
- Phase 4 JD 日历周期: `calc_calendar_cyclical` 4 维正余弦 (DOY+Month),宏特征架构 (单入口 `calendar_cyclical` → 4×1D 拆分),Scan JD MAE=5.10% 排名第 3
- Phase 5 CJ 影线门控: `reversal_shadow_gated_05` 固化 (scan MAE -11%),`min_shadow_atr=0.5`
- Phase 6 TA 基差实证: `basis_momentum` 退化 vs `bb_squeeze` (+0.074pp),归档保 `bb_squeeze`
- 工程加固: `monthly_backtest.py` 加 `--cache-interval/--max-points/--resume` (JSONL 断点续跑);`get_basis_1h` 加合约自身 P95×5% OI 过滤 (置 NaN 抗挂单价);`covariate_scan.py` 加 3% 显著性门槛 + `DirAcc(展示)` 改名
- 全品种通用: `calendar_cyclical` 加入 `COVARIATE_TYPES`,所有品种 scan 自动覆盖
- 单测: `tests/test_calendar_cyclical.py` (7 tests) / `test_basis_oi_filter.py` (2 tests) / `test_scan_significance.py` (4 tests)

2026-07-27 工程债 D1–D3 + 根因 hardening + 文档 neat-freak:
- 会话感知交易日: data/trading_calendar.py；幽灵 K 线: data/future_bar_guard.run_guard（日线+1H）
- daily_update 唯一 purge；失败 SystemExit(2)；data_management 不再二次 purge
- 模型路径 resolve_under_root(FM_ROOT)；ResolvedModelPath + model_source；空 pkl 拒绝
- R1 black 仅路径铺路、默认不训；缺 pkl → r0_fallback_black
- 单测: tests/test_future_bar_guard.py + test_vol_threshold_contract.py（25）
- 人类文档: docs/{README,runbook,copilot,vol-risk}.md

2026-07-27 Copilot 领航员 + variety_analysis 融合 + SH 烧碱:
- scripts/copilot.py: 永不压平；Vol 预警；knowledge_base 信用背书；reports/daily 研报
- scripts/build_knowledge_base.py + config/knowledge_base.json
- variety_analysis.py: 默认 Copilot 融合；--no-predict；Windows UTF-8 stdout
- data/config.py: 新增 SH (烧碱) CZCE
- 生产: vol 压平默认 OFF；盘中推荐 copilot

2026-07-25~26 Path2 Neutral L1 + R1 分板块:
- S0–S3 R0 L1：工程 PASS_NEUTRAL_OVERLAY；生产 REMAIN_OFF（Domain Shift）
- R1 已训 chem/agri pkl；operational_thr 0.65/0.45/0.55
- L1 ops 全量 ECONOMIC_PASS=False（ΔEV≈-10.8）；产物 reports/phase1/full_universe_neutral_r1_ops/
- 评分层: cascade/neutral_ab_report.py；暂停 L2

2026-07-10 协变量优化 (EG乙二醇):
- EG: regime_gated → hurst + covariate_types=["oi", "hurst"] (7pt扫描 MAE: 4.46%→4.33%, DirAcc: 71%)
- data_validator.py: 交易时段感知 bar 级检查 (新增 `_group_into_sessions`)
- covariate_scan.py / diracc_candidate_generator.py: 回测模式标记 `cutoff_date`

2026-07-08 协变量优化 (CF棉花):
- CF: vor → rsi_state (回测 EV: -0.104→+0.064, PF: 0.81→1.14, DirAcc: 49%→54%)

2026-07-08 协变量优化与历史追踪:
- JD: oi+hurst → gated_slope (回测 EV: 0.074→0.166, PF: 1.16→1.40)
- P: rsi_slope → pca_momentum (回测 EV: 0.155→0.186, PF: 1.34→1.46)
- 新增 cascade/prediction_tracker.py: 历史预测追踪模块

2026-07-07 协变量优化:
- P: rsi_slope → pca_momentum (7pt扫描MAE: 1.51%→1.11%)
- M: 保持 vor (回测最优 EV=0.131)
- LH: 保持 oi+hurst (回测最优 EV=0.131)

2026-07-06 预测管线加固:
- cascade_predict.py: --collect / --collect-if-stale 自动采集
- data_validator.py: 周末/假日感知时效性
- daily_model.py: 日线时效性检查
- hourly_model.py: skip_validation 仅抑制输出
- three_star_predict.py: 强制预校验，共享模型

2026-07-05 协变量全品种优化:
- v3 扫描器独立进程，7pt 验证
- 14 品种协变量更新，TA 归档
