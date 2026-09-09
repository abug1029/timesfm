## Covariate pool (supervisor snapshot)
Propose symbol x covariate combos ONLY with ACTIVE covariates below.
Each covariate carries a mechanism hypothesis — your own mechanism argument must extend it to the chosen symbol.
archived covariates are RETIRED: do NOT propose them.

### family: calendar
- calendar_cyclical: 日历周期/季节性：交割月、季节性供需周期效应，对交割敏感品种(农产品)尤强。 [track: sr_calendar_cyclical PF0.97/经济PF1.04 近门]

### family: oscillator
- qstick: QStick=收盘-开盘的均值，量化净买卖压力方向与持续性。
- rsi12: RSI(12)中周期超买超卖，灵敏度介于rsi6与rsi_state之间。
- rsi24: RSI(24)长周期超买超卖，噪声更小、信号更稳但滞后。
- rsi6: RSI(6)短周期超买超卖，比rsi_state更灵敏，捕捉短线极端反转。
- rsi_slope: RSI变化斜率动量：动量转折常领先价格转折，捕捉超买超卖的加速/衰竭。
- rsi_state: RSI(14)超买超卖体制：极端读数后均值回归，体制状态(超买/中性/超卖)引导方向。 [track: ss_rsi_state 经济PF最高1.16/ic0.01；eg_rsi_state PF0.97 近门]

### family: positioning
- ccl: 仓差线(CCL)：主力资金净持仓变化方向，定位主力多空意图。 [track: ss_ccl PF1.02/经济PF1.13]
- oi: 持仓量变化率：增仓代表资金流入、趋势可信度高；缩仓代表行情缺乏新资金。 [track: jd_oi PF0.97/ic0.046 近门]

### family: price_action
- ha_body: Heikin-Ashi实体方向与大小：平滑后的K线实体动能，过滤噪声识别趋势延续。 [track: ss_ha_body 经济PF1.13/ic0.02]
- reversal_shadow: 反转影线比率：长上/下影线相对ATR占比，极端影线标志遇阻/遇撑反转。
- reversal_shadow_gated_02: 反转影线门控版(最小影线/ATR=0.2)：仅在影线足够显著时触发反转信号。
- reversal_shadow_gated_03: 反转影线门控版(最小影线/ATR=0.3)：更严格的显著影线阈值。
- reversal_shadow_gated_05: 反转影线门控版(最小影线/ATR=0.5)：最严格阈值，仅极端影线触发。

### family: statistical
- hurst: Hurst指数：判别趋势持续性(H>0.5)或均值回归(H<0.5)体制，元信号。
- pca_momentum: 多品种主成分(PCA)动量：提取市场宽度第一主成分，识别系统性趋势共振。 [track: sp_pca_momentum PF0.87 失败]
- regime_gated: 体制自适应融合：按Hurst体制动态加权pca/rsi/oi，趋势市跟趋势、震荡市跟回归。

### family: structure
- basis_momentum: 基差动量：现货-期货升贴水的变化趋势，反映期现结构强弱与交割压力。
- crack_spread_level: 压榨/裂解产业链利润价差水平：利润极端值均值回归，仅对产业链品种(豆粕/油脂等)有意义。
- crack_spread_slope: 产业链利润价差斜率：利润扩张/收缩的动量方向，引领产业链品种价格。
- crack_spread_zscore: 产业链利润价差Z-score：利润相对历史中枢的偏离度，极端偏离反转。
- vwap_deviation: 价格对成交量加权均价(VWAP)的偏离：短期过度延伸后回归，量化拥挤度。

### family: trend
- ao_accel: Awesome Oscillator加速度：动量的二阶变化，提前捕捉趋势启动/衰竭。
- gated_slope: Hurst门控斜率：仅趋势体制(H>0.5)跟随斜率，震荡体制屏蔽假突破。
- hourly_slope: 小时级别价格斜率：短期趋势动能方向与强度。
- sar_dist: 抛物线SAR距离：价格与SAR的距离衡量趋势持仓位置与反转距离。 [track: cf_sar_dist PF0.75 失败]

### family: volatility
- bb_squeeze: 布林带挤压：带宽收敛至极窄预示波动即将扩张，突破方向跟随。 [track: ta_bb_squeeze PF1.005/经济PF1.07 近门]
- stddev: 滚动标准差：波动率水平，高波风险规避、低波蓄势突破。
- vor: 波动率范围(VOR)：真实波幅相对历史的压缩/扩张，低波压缩后突破。 [track: m_vor PF1.30 最高/MaxDD最低/ic0.048近门]

### family: volume
- nvi: 负量指标(NVI)：仅在缩量日累计涨跌，跟踪聪明钱在散户离场时的方向。 [track: sh_nvi n142样本不足/PF0.64]

### symbol sample ceiling (valid aligned points now; hard gate n>=350)
BELOW GATE symbols cannot pass today regardless of covariate (1H bars accrue over time; supervisor auto-retests near-misses):
- ao: n=205 BELOW GATE
- bu: n=396 gate-reachable
- cf: n=396 gate-reachable
- cj: n=324 BELOW GATE
- eg: n=396 gate-reachable
- fg: n=396 gate-reachable
- fu: n=396 gate-reachable
- i: n=396 gate-reachable
- jd: n=396 gate-reachable
- jm: n=396 gate-reachable
- lh: n=238 BELOW GATE
- m: n=396 gate-reachable
- ma: n=396 gate-reachable
- p: n=396 gate-reachable
- rb: n=396 gate-reachable
- sh: n=142 BELOW GATE
- sp: n=396 gate-reachable
- sr: n=396 gate-reachable
- ss: n=396 gate-reachable
- ta: n=396 gate-reachable
- ur: n=309 BELOW GATE

