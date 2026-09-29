====================================================================================================
三环系统成果总览
生成时间: 2026-09-24 10:03:19
====================================================================================================

【总体统计】
----------------------------------------------------------------------------------------------------
总评估数: 143
过门变体: 42 (29.4%)
  S 级 (卓越): 10
  A 级 (优秀): 22
  B 级 (良好): 54
排序逻辑: 无排序，按等级从高到低展示

【品种成果汇总】
----------------------------------------------------------------------------------------------------
品种     过门数      平均DirAcc     S级     A级     B级     FDR通过   
----------------------------------------------------------------------------------------------------
cf     1        0.531        0      1      0      1       
cj     8        0.511        0      3      5      0       
m      7        0.511        0      1      6      0       
p      3        0.565        1      2      0      2       
rb     6        0.514        3      3      0      0       
sr     13       0.528        4      9      0      0       
ss     4        0.544        2      2      0      0       
排序逻辑: 按品种代码字母顺序 (cf → cj → m → p → rb → sr → ss)

【顶级成果 (S级 + A级)】
----------------------------------------------------------------------------------------------------
排名   变体ID                                品种   DirAcc   等级   协变量                       FDR 
----------------------------------------------------------------------------------------------------
1    sr_calendar_cyclical                sr   0.617    S    calendar_cyclical         ❌   
2    p_oi                                p    0.568    A    oi                        ✅   
3    ss_calendar_cyclical                ss   0.568    S    calendar_cyclical         ❌   
4    p_calendar_cyclical                 p    0.563    A    calendar_cyclical         ✅   
5    p_ccl                               p    0.563    S    ccl                       ❌   
6    sr_crack_spread_slope               sr   0.549    S    crack_spread_slope        ❌   
7    ss_crack_spread_zscore              ss   0.544    S    crack_spread_zscore       ❌   
8    m_rsi12                             m    0.541    A    rsi12                     ❌   
9    sr_rsi_slope                        sr   0.539    S    rsi_slope                 ❌   
10   ss_rsi6                             ss   0.537    A    rsi6                      ❌   
11   cf_rsi6                             cf   0.531    A    rsi6                      ✅   
12   ss_crack_spread_slope               ss   0.529    A    crack_spread_slope        ❌   
13   rb_regime_gated                     rb   0.527    S    regime_gated              ❌   
14   cj_bb_squeeze                       cj   0.524    A    bb_squeeze                ❌   
15   sr_rsi24                            sr   0.524    A    rsi24                     ❌   
16   sr_oi                               sr   0.522    A    oi                        ❌   
17   sr_vor                              sr   0.522    A    vor                       ❌   
18   cj_rsi24                            cj   0.520    A    rsi24                     ❌   
19   cj_crack_spread_level               cj   0.520    A    crack_spread_level        ❌   
20   sr_ao_accel                         sr   0.520    S    ao_accel                  ❌   
21   sr_hourly_slope                     sr   0.520    A    hourly_slope              ❌   
22   rb_rsi12                            rb   0.520    S    rsi12                     ❌   
23   rb_vwap_deviation                   rb   0.517    S    vwap_deviation            ❌   
24   sr_ha_body                          sr   0.514    A    ha_body                   ❌   
25   sr_bb_squeeze                       sr   0.512    A    bb_squeeze                ❌   
26   sr_rsi12                            sr   0.512    A    rsi12                     ❌   
27   rb_ao_accel                         rb   0.512    A    ao_accel                  ❌   
28   sr_crack_spread_level               sr   0.510    A    crack_spread_level        ❌   
29   sr_crack_spread_zscore              sr   0.509    A    crack_spread_zscore       ❌   
30   rb_nvi                              rb   0.507    A    nvi                       ❌   
31   rb_crack_spread_zscore              rb   0.500    A    crack_spread_zscore       ❌   
排序逻辑: 按 DirAcc (方向准确率) 降序，数值越高预测能力越强

【FDR 严格检验通过变体】
----------------------------------------------------------------------------------------------------
排名   变体ID                                品种   DirAcc   等级   协变量                      
----------------------------------------------------------------------------------------------------
1    p_oi                                p    0.568    A    oi                       
2    p_calendar_cyclical                 p    0.563    A    calendar_cyclical        
3    cf_rsi6                             cf   0.531    A    rsi6                     
排序逻辑: 按 DirAcc 降序，FDR 通过代表统计学强证据，是最严格的质量标准
