# Task 6：仍有效协变量 spec 对齐

- **任务**: spec–代码对齐计划 Task 6（只读生产代码，写报告）
- **计划**: `docs/superpowers/plans/2026-09-11-spec-code-alignment.md` Task 6
- **仓**: WSL `/home/abug/timesfm`，HEAD `9653264`（2026-09-11 11:19）
- **审核日**: 2026-09-11
- **合同**: 只读 `.md` spec；**忽略同名 `.txt`**。设计被 STATE / 后一份 spec 废掉的标「失效」，不当代码缺口。SCHEMES 未采用 ≠ 实现失效（池内代码仍要对齐）。
- **对照**: `cascade/features.py`、`config/prediction_scheme.py`、`config/crack_spread_pairs.py`、`data/data_store.py`、`cascade/hourly_model.py`、`STATE.md`
- **不改**: 生产代码、SCHEMES、verdicts；不启动 Praxist

## 结论先行

七份早期协变量 spec 都不是现行三环/硬门合同，但**机制还在生产路径或扫描池里的条款必须对齐**。活 `SCHEMES.covariate_type` 集合是 `ao_accel / calendar_cyclical / ha_body / hourly_slope / reversal_shadow / rsi_state`，组合里还有 `oi`。Phase 15「应固化 NVI/QSTICK/VWAP/StdDev」已被 STATE 0 GREEN 否决，标失效；四个函数仍在 `features.py` 当池代码。

| # | Spec | 总判定 | 一句话 |
|---|------|--------|--------|
| 1 | `2026-07-29-phase4-calendar-cyclical-design.md` | **部分对齐** | 4 维公式与精确 horizon 日历在；拆成 4×1D；horizon 时钟与 `daily_slope` 不是同一套 |
| 2 | `2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md` | **部分对齐** | 影线门控函数对齐；无无后缀 `reversal_shadow_gated`；CJ/TA 固化目标已失效；基差采集管道仍在 |
| 3 | `2026-07-29-followup-4-directions-optimization-design.md` | **部分对齐** | 方向 1/2/4 在；方向 3 显著性标签随 `covariate_scan.py` 一起消失 |
| 4 | `2026-07-31-phase8-crack-spread-design.md` | **对齐**（池内，非 SCHEMES） | 公式/对齐/ffill 守卫/截止注入都在；「8a 不固化」已兑现 |
| 5 | `2026-08-04-phase9-toxic-variety-design.md` | **部分对齐** | AO 固化仍在；JD `rsi_state+oi` 被 Phase 11 换成单 `rsi_state`；ha_body 黑名单在 |
| 6 | `2026-07-28-covariate-optimization-design.md` | **部分对齐** | 过程 spec；多数固化目标被后续 Phase 覆盖；候选函数仍在池 |
| 7 | `2026-08-22-phase15-new-covariates-design.md` | **部分对齐**（池）/ **失效**（固化合同） | 四函数在池；「应进 SCHEMES」0 GREEN 失效；StdDev 以 15b 为准 |

**生产信号路径上没有「有效 spec 写反、会改错仓位」的 Critical。** 最值得盯的有效缺口是日历 horizon 两套时钟（中）和 scan 显著性标签丢失（中，只伤扫描展示）。

---

## 0. 活 SCHEMES 与池

活 `covariate_type`（`config/prediction_scheme.py:119-490`）：

| 类型 | 在 SCHEMES 的品种 | 来源 spec（仍有效的机制） |
|------|-------------------|---------------------------|
| `calendar_cyclical` | ss, sp, fu, eg, ta；组合：sr, m, bu, cf, ao | Phase 4 |
| `ao_accel` | ur | 优化 spec 候选；函数来自 quant-trading 层 |
| `ha_body` | jm, fg；组合：m, cf | 优化 spec / Phase 9 |
| `hourly_slope` | cj；组合：ao, bu, ma | 优化 spec / Phase 9 AO |
| `reversal_shadow` | i, sh；组合：p | Phase 5 底层（无门控） |
| `rsi_state` | rb, lh, jd；组合：sr, p | Phase 9 JD 路径的后代 |
| `oi`（仅 combo） | sr, ma | 优化 spec 起一直在 |

**不在 SCHEMES、仍在 `features.py` 池里**：`basis_momentum`、`reversal_shadow_gated_{02,03,05}`、`crack_spread_{slope,level,zscore}`、`nvi` / `qstick` / `vwap_deviation` / `stddev`、`bb_squeeze`、`vor`、`gated_slope`、`regime_gated`、`ccl` 等。

单路径 `rsi_state` 用**日线** RSI（`features.py:1076-1119`），combo `rsi_state` 用 **1H** RSI（`:1483-1487`）。上一轮 Task 6 I-16 / SUMMARY I-16 已记。本任务不重审，但 Phase 9 JD 从 combo 退回单路径时，语义跟着变了。

---

## 1. Phase 4 `calendar_cyclical`

**文件**: `docs/superpowers/specs/2026-07-29-phase4-calendar-cyclical-design.md`  
**状态栏**: 待用户审核（不够当杀手）  
**有效性**: **部分有效**。4 维正余弦 + 精确未来日历仍在生产（多个品种 SCHEMES）。「先不改 JD scheme、等 scan 再固化」已被后续 Phase 覆盖 → 该固化目标 **失效**。

### 1.1 条款

| 条款 | spec | 代码 | 判定 |
|------|------|------|------|
| 4 维公式 `sin/cos(2π·DOY/365.25)` + `sin/cos(2π·Month/12)` | L22–29, L78–83 | `calc_calendar_cyclical` `:2180-2205` | **对齐** |
| 输入 `df_1h["dt"]`，无额外依赖 | L33–35 | `:2193-2194`，兼容 `date` | **对齐** |
| Horizon = 确定性未来日历，不用衰减 | L37–52, L116 | 函数自己拼 context+horizon，分发处不再 `_decay_fill`（`:1343-1353`, `:1588-1594`） | **对齐** |
| 返回 `(n+horizon, 4)` 一整块 | L71–72, L220 | 纯函数是 4 列；`build_*` **拆成 4 个 1D**（`calendar_doy_sin/cos` 等） | **部分对齐**。STATE `:344` 记「宏特征架构 (单入口 → 4×1D 拆分)」，高于 spec 矩阵形状 |
| 交易日历感知 horizon | L42–47 主路径；L90–91 简化成自然小时 | `:2210-2233` 走 `detect_trading_hours`，`replace(minute=0)` | **部分对齐**，见缺口 C1 |
| Combo 注册 | L120 | `:1588-1594` | **对齐** |
| 单测 5 项 | L149–195 | `tests/test_calendar_cyclical.py` 覆盖正交/跨年/horizon/拆分 | **对齐**（实现比 spec 片段更完整） |
| JD 暂不改 scheme | L135–137 | 现 JD = `rsi_state`（`:439-440`） | **失效**（Phase 11 固化 rsi，STATE / SCHEMES） |

spec 表头把 `month_sin` 写成「月内位置」，公式其实是月份/12（年周期）。代码跟公式走，不跟那句误写走。不当缺口。

### 1.2 缺口

**[MEDIUM] C1 — 日历 horizon 与 `daily_slope` 不是同一套未来轴**  
- spec: `docs/superpowers/specs/2026-07-29-phase4-calendar-cyclical-design.md:42-47`（复用交易日历）  
- 代码: `cascade/features.py:2226-2233` vs `cascade/data_validator.py:584-626`  
- `build_covariate_matrix:1029-1034` 给 `daily_slope` 用 `generate_trading_dates`（先 `+1h`，周末直接跳到下周一 00:00，**不** `replace(minute=0)`）。  
- `calc_calendar_cyclical` 自己再走一遍：`last_dt+1h` 后 **`replace(minute=0)`**，周末逐小时爬，不跳周一 00:00。  
- 不是把未来真收盘偷进 XReg（两边都是日历外推），但第 k 根 horizon 的日历编码和斜率映射可能对不上同一个时钟。上一轮 Task 6 cascade M2 / SUMMARY 已点名，本条把它挂回 Phase 4 条款。  
- **修**: 日历 horizon 直接用已经算好的 `future_dates` / `generate_trading_dates`，删掉第二套循环。

**[LOW] C2 — 4 列矩阵 vs 4×1D**  
- spec L220 验收 `shape (n, 4)`；生产是 4 个独立 XReg 通道。STATE 已承认拆分。改文档横幅即可，不要把 4 列矩阵改回去。

### 1.3 总判定

**部分对齐**。公式、不衰减、combo、测试、多品种 SCHEMES 都在。有效缺口是 horizon 双时钟。

---

## 2. Phase 5+6 影线门控 + 基差管道

**文件**: `docs/superpowers/specs/2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md`  
**状态栏**: Draft（不够当杀手）  
**有效性**: **部分有效**。门控算法与 `--with-basis` 管道仍在。CJ 改 `reversal_shadow_gated_*`、TA 改 `basis_momentum` 的固化目标被后续实证/Phase 11 **失效**。

### 2.1 Phase 5 影线

| 条款 | spec | 代码 | 判定 |
|------|------|------|------|
| `min_shadow_atr` 默认 0，零回归 | L72, L100 | `calc_reversal_shadow_ratio:1959-1988`；`tests/test_reversal_shadow_gated.py:18-30` | **对齐** |
| 双向独立滤除，先于 `directional_shadow` | L77–86 | `:2006-2017` | **对齐** |
| 注册 `_02/_03/_05` 三档 + `_decay_fill` | L91–96 | 单路径 `:1297-1319`；combo `:1547-1566` | **对齐**（档位） |
| 正式名 `reversal_shadow_gated`（无后缀） | L73, L96 | 两处 elif **没有**无后缀名；`supported` 也只有三档（`:1722-1723`） | **缺口** G1 |
| 达阈 → CJ scheme 改 gated | L105–107 | 现 CJ = `hourly_slope`（`:420-421`）。STATE `:345` 曾固化 `_05`，Phase 9/11 换掉 | **失效** |
| 未达阈则保 `reversal_shadow` | L107 | 现既不是 gated 也不是 raw shadow | **失效**（被更后的穷举取代） |

CJ scheme 注释仍写「影线门控: 双向独立滤除 < 0.5 ATR」（`:424`），和活 `hourly_slope` 矛盾。文档债，见 L1。

### 2.2 Phase 6 基差管道

| 条款 | spec | 代码 | 判定 |
|------|------|------|------|
| `--with-basis` 后置采集月度合约 | L120–126 | `scripts/collect_1h.py:225-226,254-264`；`collect_basis_contracts_for_symbol:62-70`（18 个月候选、OI 最高两份、try/except） | **对齐**（CLI 是 flag 不是 `<symbols>` 位置参数，见 L2） |
| `get_basis_1h` 不改算法、注入即可用 | L129 | `data/data_store.py:530-643`；后又加了方向 2 的 P95 过滤 | **对齐**（过滤是 followup-4 增量） |
| `basis_momentum` 算法完整 + 零填充回退 | L48, L55 | `calc_basis_momentum:656-712`；分发 `:1218-1245`, combo `:1638-1654` | **对齐**（池） |
| L4 达阈才改 TA scheme 为 `basis_momentum`，否则保 `bb_squeeze` | L135, L144 | 现 TA = `calendar_cyclical`（`:479-480`）；注释归档 Phase 6（`:488`） | **失效**（STATE `:346` 不固化；Phase 11 再换成日历） |
| 历史 NaN>30% 显式 SKIP | L133 | spec 自己说落点看实测；计划后来说整段空则不改 backtest | **失效/未锁形态**，不当缺口 |

### 2.3 缺口

**[LOW] G1 — 无无后缀 `reversal_shadow_gated`**  
- spec L73/L96：scan 胜者正式注册为 `reversal_shadow_gated`。  
- 代码只有 `_02/_03/_05`。SCHEMES 已不用，扫描时必须带后缀。池代码够用。  
- **修**: 若还要 scan，加别名指向胜出档（历史上是 0.5）；或改 spec 承认只留三档。

**[LOW] L1 — CJ 注释谎称影线门控**  
- `prediction_scheme.py:424` vs `:420-421`。改注释。

**[LOW] L2 — `--with-basis` CLI 形状**  
- spec 写 `--with-basis <symbols>`；实现是 `action="store_true"`，对本次命令的 symbols 生效。`collect_1h.py ta --with-basis` 仍能跑。

### 2.4 总判定

**部分对齐**。门控函数与基差采集是有效实现；两处「应改 SCHEMES」已被 STATE 否决。

---

## 3. 后续 4 方向

**文件**: `docs/superpowers/specs/2026-07-29-followup-4-directions-optimization-design.md`  
**有效性**: **部分有效**。方向 1/2/4 的机制仍在生产工具链。方向 3 绑定的 `covariate_scan.py` 已不在仓里。

### 3.1 条款

| 方向 | spec | 代码 | 判定 |
|------|------|------|------|
| 1 `--cache-interval` / `--max-points` / `--resume` JSONL | L30–57 | `scripts/monthly_backtest.py:780-803,864,901`；`tests/test_monthly_resume.py` | **对齐**。无参数不写 checkpoint（`:901`）比 spec 更严，零回归 |
| 2 `get_basis_1h` 合约自身 P95×5%，置 NaN 不删行 | L85–100 | `data/data_store.py:618-641`；`tests/test_basis_oi_filter.py` | **对齐** |
| 2 之后 `basis_momentum` 遇 NaN 走零填充 | L100 | `features.py:1234-1238` 对 NaN 窗口 `continue` 保持 0 | **对齐** |
| 3 DirAcc 改名 + 3% MAE 显著性标签 | L134–153 | 全仓 **无** `DirAcc(展示)` / `significance_label` / `无显著改善`。`scripts/covariate_scan.py` **不存在**；继任 `covariate_scan_new.py` 无这些标签。`tests/test_scan_significance.py` **不存在** | **缺口** S1 |
| 4 TA scheme 归档注释 | L177–184 | `prediction_scheme.py:487-489` Phase 6/8a 归档注释在 | **对齐**（注释）。活协变量已不是 `bb_squeeze`，那是后话，不是本方向违约 |
| 4 STATE 路线图 | L186–190 | STATE `:346-360` Phase 6 归档、Phase 8 已做 | **对齐** |

方向 1 的 resume 跳过点不回填 `points[]`、summarize 会残缺——这是后续效率审计 F-003 / `scripts/AGENTS.md`，不是本 spec 写明的条款。本任务不升级成 Phase 4 方向 1 的 Critical。

### 3.2 缺口

**[MEDIUM] S1 — 方向 3 展示/显著性门槛从活代码消失**  
- spec: `2026-07-29-followup-4-directions-optimization-design.md:134-153,238`  
- STATE `:601` 写「已完成」。磁盘上 `covariate_scan.py` 已删，`covariate_scan_new.py:38` 只扫 5 个 quant-trading 名，stdout 无「显著改善」。  
- 不改生产 SCHEMES 信号；会让后人再拿 7pt DirAcc 当裁决。  
- **修**: 在仍使用的 scan 入口（若还有）补标签；或在 spec/STATE 标明「旧 scan 已退役，方向 3 随文件删除」。

### 3.3 总判定

**部分对齐**。长跑治理和 OI 过滤是实的；scan 展示合同断了。

---

## 4. Phase 8a Crack Spread

**文件**: `docs/superpowers/specs/2026-07-31-phase8-crack-spread-design.md`  
**有效性**: **池内仍有效，非 SCHEMES 合同**。spec §6 自己锁「8a 不固化」。STATE `:350-351` PX-TA 弱信号不固化；8b 也 UNDERPOWERED。函数仍被 scan/覆盖路径调用。

### 4.1 条款

| 条款 | spec | 代码 | 判定 |
|------|------|------|------|
| `spread = TA − 0.655 × PX` | L52–55 | `calc_crack_spread:758,775`；`crack_spread_pairs.py:9` | **对齐** |
| 三模式 slope/level/zscore + tanh(gain×归一化) | L58–68 | `:780-811` | **对齐** |
| slope 对 **spread** 做 polyfit，不是 close | L67 | `:787-795` | **对齐** |
| Horizon：level 常数，slope/zscore 向 0 衰减 | L60–62 | `:786` `np.full`；`:799-800,809` `_decay_fill` | **对齐** |
| 主表 left-join + ffill | L73–76 | `_align_feedstock:715-746` | **对齐** |
| `max_ffill_gap=4` 超限置 NaN→0 | L80–85 | `:743-745,771,784` | **对齐** |
| feedstock 继承 `cutoff_date` | L89–94, L189–199 | `hourly_model.py:43-59,151-157`；`BacktestDataStore` 在 `data/data_store.py:769` | **对齐** |
| `feedstock_cache` 签名只膨胀一次 | L142–149 | `build_*:1001,1419` | **对齐** |
| 单+combo 三档注册 | L124–139 | `:1329-1341`, `:1575-1586` | **对齐** |
| 无配对 → 零填充 + 警告 | L235 | `hourly_model.py:156-159`；`calc_crack_spread:766-767` | **对齐** |
| 预热不足 warn 144 | L201 | `hourly_model.py:57-58` | **对齐** |
| 单测公式/对齐/间隙/零回归 | L243–256 | `tests/test_crack_spread.py` | **对齐** |
| verdict 用 `effective_n` | L218–223 | `scripts/phase4d_parse_results.py` + `test_verdict_uses_effective_n` | **对齐** |
| **8a 不改 SCHEMES** | L300 | TA 不是 `crack_spread_*` | **对齐**（非目标兑现） |
| 8b 预留 fu/bu | L160–163, L306–309 | `crack_spread_pairs.py:10-11` OLS ratio 4.7191 / 2.8067 | **对齐**（STATE 已跑 8b，仍不固化） |

spec §4.1 测试句写过「level 用 rolling ATR」；§1.1 公式是 `rolling_std`。代码跟公式。不当缺口。

### 4.2 总判定

**对齐**（池内实现 + 明确不固化）。没有有效条款被写反。

---

## 5. Phase 9 有毒品种

**文件**: `docs/superpowers/specs/2026-08-04-phase9-toxic-variety-design.md`  
**有效性**: **部分有效**。方法（完整 walk-forward + v2 规则 + ha_body 黑名单）仍约束 AO/JD。JD 的「固化 rsi_state+oi」被 Phase 11 **失效**。

### 5.1 条款

| 条款 | spec | 代码 / STATE | 判定 |
|------|------|--------------|------|
| 不用 7pt scan，完整 WF | L23–25 | 实证报告路径；与优化 spec §9.1 同向 | **对齐**（方法） |
| AO 候选含 `hourly_slope+calendar` | L47 | SCHEMES ao `:357-358` `["hourly_slope","calendar_cyclical"]` | **对齐** |
| AO 禁止 ha_body | L15, 黑名单测试 | `tests/test_ha_body_toxic_blacklist.py:22,29-47`；ao `covariate_type != ha_body` | **对齐** |
| JD 基线 `rsi_state+oi`，若 PASS 则写入 scheme | L50, L81 | STATE `:190-191,:374` 曾固化 combo；现 JD `:439-440` 只有 `rsi_state`（Phase 11） | **失效**（固化目标） |
| JD 禁止 ha_body | L16 | 黑名单 `"jd"`；现 `rsi_state` | **对齐**（禁令仍有效） |
| CF 不纳入、保留 ha_body+calendar | L18, L16 | cf `:341-342` | **对齐** |
| v2 规则 R1–R4 | L62–70 | 历史裁决已用；本任务不重跑回测 | 方法有效，不当代码缺口 |
| 产出报告 + 改 SCHEMES/KB/STATE | L89–93 | 报告在 `reports/research/20260804_phase9_toxic_variety_study.md`（STATE `:194`） | **对齐**（当时） |

黑名单测试错误信息仍写 JD 期望 `rsi_state+oi`（`test_ha_body_toxic_blacklist.py:54`），断言本身只禁 ha_body。见 L3。

### 5.2 缺口

**[LOW] L3 — 黑名单文案滞后**  
- `tests/test_ha_body_toxic_blacklist.py:54` 期望字符串还是 `rsi_state+oi`，活配置是单 `rsi_state`。测试不会因此失败。改文案。

### 5.3 总判定

**部分对齐**。AO 生产配置就是本 spec 的胜者；JD 固化目标被 Phase 11 废掉，ha_body 禁令还在。

---

## 6. 1 星 + PTA 协变量优化（2026-07-28）

**文件**: `docs/superpowers/specs/2026-07-28-covariate-optimization-design.md`  
**状态栏**: Approved (Phase 1 in progress) — 未关闭，但是过程 spec。  
**有效性**: **部分有效**。§9 方法论（scan DirAcc 不可信、WF 才是权威、不自动写 SCHEMES）仍有效。各品种「本轮应固化 XXX」几乎全部被 Phase 9/11/12 **失效**。`features.py` 本轮规定不动，所以本 spec **没有**公式对齐任务；候选后来都进了池。

### 6.1 条款

| 条款 | spec | 现状 | 判定 |
|------|------|------|------|
| Phase 0：scan 补 5 个 quant-trading 类型 | L43–52 | `covariate_scan.py` 已不在；`covariate_scan_new.py:38` `NEW_COVARIATES` 就是这 5 个 | **部分对齐**（工具换代） |
| 本轮不改 `features.py` | L201, L253 | 后续 Phase 改了大量 features，那是后合同 | **失效**（保护期已过） |
| MA 首选 ha_body，未达阈保 `hourly_slope+oi` | L94–104, L190 | 现 ma `:463-464` 仍是 `hourly_slope+oi`。STATE `:377` 全 FAIL | **对齐**（未达阈不固化） |
| CJ 砍 combo、试 reversal_shadow；阈值留给下 Phase | L106–116 | 现 cj `hourly_slope`；门控在 Phase 5 做完后又被换掉 | **失效**（固化目标） |
| JD 日历本轮不做 | L128, L252 | Phase 4 做了日历；JD 最终不是日历 | 非目标兑现，日历另审 |
| EG 不动 covariate，调 confidence | L136–140 | 现 eg `calendar_cyclical`（Phase 11） | **失效** |
| TA 解冻确认技术上限；basis 单独立项 | L155–163 | Phase 6/8/9/11 链条；现日历 | 立项 **对齐**；本轮固化目标无 |
| 固化阈值 DirAcc+2pp 且 scan 缓冲 | L185–192 | 同文件 §9.1 宣布 scan DirAcc 高估 19–33pp | **失效**（被本文 §9.1 取代） |
| §9.1 scan DirAcc 不可信；WF 唯一权威 | L260–276 | Phase 9 spec L23 沿用 | **对齐**（方法，仍有效） |
| ledger 不参与选型 | L220–243 | 仍是监控工具 | **对齐** |

### 6.2 总判定

**部分对齐**。把它当「现在还要按表固化」会做错；把它当「扫描不可信 + 这些候选函数进池」则仍对。

---

## 7. Phase 15 新协变量

**文件**: `docs/superpowers/specs/2026-08-22-phase15-new-covariates-design.md`  
**有效性**: **实现（池）部分有效；「应固化 / 应进 SCHEMES」失效。**  
杀手：`STATE.md:18,489-509` — 24 tests，0 GREEN，「本次搜索的 4 个新协变量均未达标」。计划预置与此一致。

### 7.1 公式（池代码仍要对齐）

| 条款 | spec | 代码 | 判定 |
|------|------|------|------|
| NVI 缩量累积，NVI[0]=1000，rolling z-score lookback=20 | L65–74 | `_calc_nvi:872-914` | **对齐** |
| volume NULL 跳过；连续 NULL>6 → NaN→0 | L82 | `:891-897` 后 `nan_to_num` | **部分对齐**（见 N1） |
| 不用 OI 替代 volume | L82 | 只读 `volume` | **对齐** |
| QSTICK = SMA(close−open,14) / rolling_std(60) | L88–93 | `_calc_qstick:917-927` | **对齐** |
| VWAP typical=(H+L+C)/3，窗口 24，(C−VWAP)/VWAP | L105–112 | `_calc_vwap_deviation:930-954` | **部分对齐**（见 N2） |
| high/low NULL → 0，不用 close 替代 | L118 | `:947-954` | **对齐** |
| StdDev = std(**close**,20) 再对 60 期均值做百分比偏离 | L123–128 | `_calc_stddev:957-979` 用 **收益率** std | **失效**（原公式）。**对齐** 到 STATE 15b（`:534-547` 保留 returns std） |
| 两处 elif + supported | L144–148 | 单 `:1356-1379`；combo `:1610-1635` | **对齐** |
| 单测 shape/NaN/combo | L150–152 | `tests/test_new_covariates.py` | **对齐** |
| 相关性预检脚本 | L191–192 | `scripts/p15_corr_precheck.py` 存在 | **对齐** |
| `batch_p15_new_cov.sh` | L154–156, L282 | **仓内无此文件** | **缺口** B1（交付物，非公式） |
| GREEN → 固化进 SCHEMES | L1, L244–256 | 0 GREEN，SCHEMES 无 nvi/qstick/vwap/stddev | **失效**（应固化） |
| 24 FAIL → 进 15b **组合** | L20 vs L256 | STATE `:507` 无 >5% PF，**不触发组合**；后来的 15b 是 StdDev/VWAP **修复重跑**，不是 combo | **失效**（以 §5 退出条件 + STATE 为准） |
| VWAP horizon 常数 vs 衰减 | spec 未锁；审核点过衰减 | 默认常数（`:1366-1373`）；`fill_strategy=="decay"` 可开。STATE `:549-562` 衰减 0/6 改善已回滚 | **对齐**（15b） |

### 7.2 缺口 / 偏差

**[LOW] N1 — NVI 连续空值计数多算了 `volume[i-1]`**  
- spec L82：NULL **该 bar** 跳过。  
- 代码 `:891`：`isnan(volume[i]) or isnan(volume[i-1])` 都加 streak。刚恢复的第一根有效 bar 仍可能被算进 streak，长洞之后 NVI 从 1000 重启（`:901`）。池内、未进 SCHEMES。  
- **修**: 只在 `volume[i]` 为 NULL 时加 streak；有效 bar 从上一有效 NVI 续算。

**[LOW] N2 — VWAP 分母用 `abs(vwap)`，且未裁到 [-1,1]**  
- spec L112「自然约束在 [-1,1]」是声称，不是 clip。价格远离 VWAP 时可以 |dev|>1。分母 `abs`（`:952`）在正价格下与 spec `/VWAP` 等价。  
- **修**: 文档改成「不保证 [-1,1]」；若要硬约束再 `clip`。

**[LOW] B1 — `scripts/batch_p15_new_cov.sh` 缺失**  
- 24 tests 已跑完（STATE），批次脚本不是活生产入口。补文档或从交付表删掉。

### 7.3 总判定

**部分对齐（池）+ 失效（固化合同）**。不要把「没写进 SCHEMES」报成代码缺口。StdDev 以 15b 为准，不要把价格 std 改回去。

---

## 8. 汇总

### 8.1 每份 spec 一行

| Spec | 有效性 | 实现对齐 | 有效缺口 | 失效（不当缺口） |
|------|--------|----------|----------|------------------|
| Phase 4 calendar | 部分有效 | 公式/不衰减/SCHEMES 多用 | C1 双时钟；C2 4×1D | JD 首验固化 |
| Phase 5+6 | 部分有效 | 门控函数、`--with-basis`、basis 池 | G1 无后缀名 | CJ gated 固化；TA basis 固化 |
| followup-4 | 部分有效 | CLI resume、P95 OI、TA 注释 | S1 scan 标签消失 | — |
| Phase 8 crack | 池内有效 | 公式/对齐/守卫/DI/截止/不固化 | 无 | 「应固化」本就不存在 |
| Phase 9 toxic | 部分有效 | AO combo、ha_body 黑名单、CF 例外 | L3 文案 | JD `rsi_state+oi` 固化 |
| 07-28 优化 | 部分有效 | MA 未达阈保持；§9.1 方法 | scan 工具换代 | 多数品种固化表；scan DirAcc 阈值 |
| Phase 15 | 池有效 / 固化失效 | 四函数+测试+预检 | N1/N2/B1 | 进 SCHEMES；15b 组合；原 StdDev 价格 std |

### 8.2 有效缺口（按严重度）

| ID | 严重度 | 置信度 | spec | 代码 | 修法 |
|----|--------|--------|------|------|------|
| C1 | MEDIUM | HIGH | Phase 4 L42–47 | `features.py:2226-2233` vs `data_validator.py:584-626` | 日历 horizon 复用 `generate_trading_dates` |
| S1 | MEDIUM | HIGH | followup-4 L134–153 | `covariate_scan.py` 已删；`covariate_scan_new.py` 无标签 | 补标签或声明旧 scan 退役 |
| G1 | LOW | HIGH | Phase 5 L73,96 | 无 `reversal_shadow_gated` 无后缀 | 别名或改 spec |
| N1 | LOW | MEDIUM | Phase 15 L82 | `_calc_nvi:891` | 只按当前 bar NULL 计 streak |
| N2 | LOW | HIGH | Phase 15 L112 | `_calc_vwap_deviation:952` | 改声称或 clip |
| B1 | LOW | HIGH | Phase 15 L154 | 无 `batch_p15_new_cov.sh` | 删交付行 |
| L1 | LOW | HIGH | Phase 5 固化后文档 | `prediction_scheme.py:424` | 删影线门控注释 |
| L2 | LOW | HIGH | Phase 6 L120 | `collect_1h.py:225` | 文档改成 flag |
| L3 | LOW | HIGH | Phase 9 | `test_ha_body_toxic_blacklist.py:54` | 文案改 `rsi_state` |
| C2 | LOW | HIGH | Phase 4 L220 | 4×1D 拆分 | 改 spec 验收形状 |

**Critical / High（高置信）: 0。** 不要为了「日历对不齐」去改 SCHEMES。

### 8.3 失效条款（杀手）

| 失效内容 | 杀手 |
|----------|------|
| Phase 15 四变量晋升 SCHEMES | `STATE.md:18,489-509` 0 GREEN |
| Phase 15 原文 StdDev=std(close) | `STATE.md:534-547` 15b 保留 returns std |
| Phase 15 24 FAIL 必须进组合 15b | `STATE.md:507` 无 >5% PF；spec §5 退出条件 |
| Phase 5 CJ → `reversal_shadow_gated_*` | STATE `:345` 曾固化，Phase 9/11 换成 `hourly_slope`（`:420`） |
| Phase 6 TA → `basis_momentum` | STATE `:346`；scheme `:488` |
| Phase 9 JD 保持 `rsi_state+oi` | Phase 11（scheme `:439-440`，STATE Phase 11 节） |
| 07-28 表内 EG/CJ/JD/TA「本轮固化」 | 被 Phase 9/11/12 覆盖 |
| 07-28 §4.3 用 scan DirAcc+2pp 固化 | 同文件 §9.1 |

### 8.4 与上一轮审计的挂接

- 日历双时钟 = Task 6 cascade M2。  
- 单/combo `rsi_state` 日线 vs 1H = SUMMARY I-16。Phase 9 JD 从 combo 退回单路径时踩过这个语义。  
- `get_safe_daily` 未接 `DailyModel.predict`、IC 公式、方案 A：本任务协变量 spec **未规定**，不评缺口。  
- combo 补 `ccl/basis_momentum/gated_slope/regime_gated`：HEAD `9653264`，SUMMARY 已作废旧 M6。Phase 5+6 的 combo 注册现在是齐的。

---

## 9. 正向观察

- `calc_calendar_cyclical` 自己返回 context+horizon，分发处没有用 spec 片段里那次错误的二次 `concatenate`。  
- 影线 `min_shadow_atr=0.0` 有字节级零回归测试。  
- Crack spread 把跨品种截止收在 `HourlyModel.predict` 一个咽喉点，生产/scan/回测共用，符合 spec 的 DI。  
- Phase 8a「不固化」写进 spec 又写进 scheme 注释，没有把 underpowered 信号塞进 SCHEMES。  
- Phase 15 失败后函数留在池里、SCHEMES 不动，符合「搜索失败 ≠ 删实现」。StdDev 15b 只改公式不改 key。  
- 活 SCHEMES 类型集合干净，没有把 nvi/crack/gated 影子写进生产品种。

---

## 10. 建议

1. **改文档横幅**（本轮对齐计划允许的文档债，不在本任务改）：Phase 4/5/6/15 状态栏；CJ 影线注释；Phase 15「应固化」加失效横幅，指向 STATE。  
2. **有效缺口另开 plan**：C1（日历 horizon 复用 `generate_trading_dates`）；S1（scan 标签或正式退役声明）。  
3. **不要做**：把 NVI/QSTICK/VWAP/StdDev 写进 SCHEMES；把 StdDev 改回价格 std；把 CJ 改回 gated；把 TA 改回 `basis_momentum`/`bb_squeeze`。

**Recommendation: COMMENT**

无高置信 Critical/High。有效 MEDIUM 两条不改现行品种仓位公式，但 C1 会让多个日历品种的 XReg horizon 对钟不准。
