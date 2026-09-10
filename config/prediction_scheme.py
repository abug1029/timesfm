"""
三星品种固化预测方案

基于 2026 年 6 月月度回测结果固化品种预测参数。
2026-06-28: 四轮回测 (OI/CCL/RSI斜率/1H斜率) 后更新协变量个性化匹配。

回测依据 (2026-06):
  SS (不锈钢): DirAcc=73%, MAPE=1.17%, decay=1.35x, 趋势型
  UR (尿素):   DirAcc=70%, MAPE=1.67%, decay=1.62x, 稳定型
  SR (白糖):   DirAcc=69%, MAPE=0.76%, decay=1.62x, 稳定型

四轮回测对比 (2026-06-28 ~ 06-29):
  16 品种已固化, 9 种协变量类型:
    OI(4) + PCA(2) + 1H斜率(3) + RSI斜率(4) + RSI状态(1) + Gated Slope(2) + Regime门控(1)
  详见: reports/monthly_backtest/20260628_covariate_research.md

修改历史:
  2026-06-27 初版固化 (基于 2026-06 回测)
  2026-06-28 四轮回测后更新协变量 (新增 rsi_slope, hourly_slope)
  2026-07-20 新协变量扫描升级:
    SS: pca_momentum+hurst → reversal_shadow (DirAcc +5.1%)
    UR: pca_momentum → ao_accel (DirAcc +3.0%)
    SP: rsi_state+oi → ha_body (DirAcc +2.3%)
    SR: 保持不变 (基线 rsi_state+oi 已最优)
  2026-07-21 二批次扫描升级:
    RB: rsi_state → ha_body (DirAcc +2.3%)
    JM: rsi_state+oi → ha_body (DirAcc +2.5%)
    I: rsi_state+oi → rsi_state+oi+ha_body (DirAcc +4.9%)
    FU: rsi_state+oi → rsi_state+oi+bb_squeeze (DirAcc +1.8%)
  2026-07-22 三批次扫描升级:
    FG: oi → reversal_shadow (DirAcc +2.5%)
    BU: pca_momentum → ha_body (DirAcc +2.0%)
    P: pca_momentum → ha_body (DirAcc +2.3%)
    CF: rsi_state → ha_body (DirAcc +2.6%)
    M: 保持不变 (基线 vor 已最优)
    AO: 保持不变 (基线 hourly_slope 已最优)
  2026-08-03 Phase 9 二星->三星全量实证固化 (73 作业, 15 品种):
    FU: rsi_state+oi+bb_squeeze -> ha_body (DirAcc 55.0%, PF 1.45, v2 PASS)
    FG: reversal_shadow -> ha_body (DirAcc 55.3%, +4pp, v2 PASS)
    LH: reversal_shadow -> ha_body (DirAcc 58.4%, PF 1.31, v2 PASS)
    CJ: reversal_shadow_gated_05 -> ha_body (DirAcc 55.2%, GREEN-MAXDD)
    M: calendar_cyclical -> ha_body+calendar_cyclical (DirAcc 58.1%, PF 1.47, v2 PASS)
    P: ha_body -> ha_body+reversal_shadow (DirAcc 53.5%, PF 1.48, v2 PASS)
    I: rsi_state+oi+ha_body -> ha_body (DirAcc 52.3%, GREEN-MAXDD)
    结论: 3 星不可达 (DirAcc 天花板 ~58%), ha_body 有效但非万能 (AO/JD/CF 有毒)
  2026-07-29 Phase 5 影线门控:
    CJ: reversal_shadow → reversal_shadow_gated_05 (scan MAE 5.49%→4.87%, -11%)
"""

from dataclasses import dataclass, field
from typing import Literal, Optional
import numpy as np


# ─────────────────────────────────────────────────────────
# 方案类型
# ─────────────────────────────────────────────────────────

SchemeType = Literal["trend", "stable", "short_range", "oscillation"]

# 信号衰减系数 — 用于校准远端预测置信度
# decay 越大，远端信号权重越低
DEFAULT_DECAY_FACTORS = {
    "trend":       1.35,
    "stable":      1.60,
    "short_range": 1.40,
    "oscillation": 1.50,
}


# ─────────────────────────────────────────────────────────
# 品种方案定义
# ─────────────────────────────────────────────────────────

@dataclass
class VarietyScheme:
    """单个品种的固化预测方案"""

    symbol: str
    name: str
    scheme_type: SchemeType
    stars: int = 3

    # ── 模型参数 (固化，不可调) ──
    context_bars: int = 480         # 1H context 长度
    horizon_bars: int = 24          # 1H 预测时域
    context_days: int = 250         # 日线 context 长度
    horizon_days: int = 22          # 日线预测天数

    # ── 信号质量指标 (来自回测，用于报告展示) ──
    dir_acc: float = 0.0            # 方向准确率
    mape: float = 0.0               # MAPE%
    decay: float = 1.0              # 衰减比
    coverage: float = 0.0           # P10-P90 覆盖率

    # ── 信号使用策略 ──
    use_full_signal: bool = True    # 是否使用 T+1~T+24 全段信号
    short_horizon_only: bool = False  # 若 True，只使用 T+1~T+12
    smooth_cutoff: bool = False  # cosine rolloff (default False = hard cutoff)
    confidence_multiplier: float = 1.0  # 置信区间乘数 (>1 = 更保守)

    # ── 协变量配置 ──
    covariate_type: str = "ccl"            # 单协变量模式: "ccl", "oi", "rsi_slope" 等
    covariate_types: list = None           # 组合模式: ["rsi_state", "oi"] 等 (daily_slope 自动包含)
    xreg_covariates: list = field(default_factory=lambda: [
        "daily_slope", "ccl_pct",
    ])

    # ── 趋势判断阈值 ──
    trend_threshold_pct: float = 0.1   # 斜率 > 此值视为上升/下降
    min_data_bars: int = 48            # 1H 最少数据量


# ─────────────────────────────────────────────────────────
# 三品种固化方案 (2026-06)
# ─────────────────────────────────────────────────────────

SCHEMES: dict[str, VarietyScheme] = {
    "ss": VarietyScheme(
        symbol="ss",
        name="不锈钢",
        scheme_type="trend",
        stars=2,  # G005-E: PF=1.15 EV_r=+0.068 n=396 → 升回2星
        dir_acc=0.510,  # G005-E 396pt
        mape=1.46,  # G005-E
        decay=1.30,  # G005-E
        coverage=0.644,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="calendar_cyclical",  # Phase 11 单协变量穷举 2026-08-20: PF=1.05 EV=+0.027 MaxDD=-22.7%
        covariate_types=["calendar_cyclical"],  # Phase 11: 3 GREEN (cal/hs/ao), calendar 最稳
    ),

    "ur": VarietyScheme(
        symbol="ur",
        name="尿素",
        scheme_type="stable",
        stars=1,  # G005-E: PF=0.84 n=303 underpowered 维持1星
        dir_acc=0.500,  # G005-E 303pt
        mape=2.71,  # G005-E
        decay=1.41,  # G005-E
        coverage=0.704,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.05,
        covariate_type="ao_accel",  # 2026-07-20 新协变量扫描: DirAcc 50.5%→53.5% (+3.0%)
    ),

    "sr": VarietyScheme(
        symbol="sr",
        name="白糖",
        scheme_type="stable",
        stars=2,  # 2026-08-08 CF-02 A + G005: PF1.10 维持2星
        dir_acc=0.550,  # G005 2026-08-08 新口径 396pt (was 0.570)
        mape=1.15,  # G005
        decay=1.43,  # G005
        coverage=0.648,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="rsi_state",  # combo 首位，与 covariate_types 对齐
        covariate_types=["rsi_state", "oi", "calendar_cyclical"],  # 2026-07-30 Phase4d 固化: Rule4 MaxDD 绿色通道 (MaxDD -19.55%->-9.81% 腰斩, EV +22%)
    ),

    # ── 以下品种 CCL 优于 OI ──

    "sp": VarietyScheme(
        symbol="sp",
        name="纸浆",
        scheme_type="trend",
        stars=1,  # G005-B 2026-08-08: PF=0.95 EV_r<0 MaxDD深 → 降1星
        dir_acc=0.510,  # G005-B 396pt (was 0.570)
        mape=1.97,  # G005-B
        decay=1.37,  # G005-B
        coverage=0.714,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="calendar_cyclical",  # Phase 11 基线对比 2026-08-20: baseline PF=0.97 FAIL → calendar PF=1.07 GREEN (消融 ha_body)
        covariate_types=["calendar_cyclical"],  # Phase 11: 1 GREEN (cal=1.07), 替换 ha_body+calendar_cyclical
    ),

    "fu": VarietyScheme(
        symbol="fu",
        name="燃料油",
        scheme_type="stable",
        stars=1,  # G005 2026-08-08: 新口径 PF=0.95 EV_r<0 → 降1星
        dir_acc=0.500,  # G005 396pt (was 0.550 Phase9 旧口径)
        mape=3.38,  # G005
        decay=1.27,  # G005
        coverage=0.638,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.1,
        covariate_type="calendar_cyclical",  # Phase 11 基线对比 2026-08-20: ha_body(PF=0.93) → calendar(PF=1.23)
        covariate_types=["calendar_cyclical"],
    ),

    "m": VarietyScheme(
        symbol="m",
        name="豆粕",
        scheme_type="stable",
        stars=2,  # G005-B: PF=1.08 弱正维持2星
        dir_acc=0.530,  # G005-B 396pt (was 0.581)
        mape=1.94,  # G005-B
        decay=1.37,  # G005-B
        coverage=0.697,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="ha_body",  # 2026-08-03 Phase 9 固化: ha_body+calendar 组合, DirAcc 58.1%, PF 1.47
        covariate_types=["ha_body", "calendar_cyclical"],
    ),

    "jm": VarietyScheme(
        symbol="jm",
        name="焦煤",
        scheme_type="stable",
        stars=1,  # G005-D: PF=0.85 → 降1星
        dir_acc=0.470,  # G005-D 396pt (was 0.533)
        mape=4.19,  # G005-D
        decay=1.28,  # G005-D
        coverage=0.680,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="ha_body",
    ),

    "i": VarietyScheme(
        symbol="i",
        name="铁矿石",
        scheme_type="stable",
        stars=1,  # G005-D: PF=0.70 EV_r=-0.18 → 降1星
        dir_acc=0.510,  # G005-D 396pt (was 0.523)
        mape=3.21,  # G005-D
        decay=1.30,  # G005-D
        coverage=0.534,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="reversal_shadow",  # Phase 11 基线对比 2026-08-20: ha_body(PF=0.98) → rev_shadow(PF=1.06)
        covariate_types=["reversal_shadow"],
    ),

    # ── 以下品种 OI 优于 CCL ──

    "rb": VarietyScheme(
        symbol="rb",
        name="螺纹钢",
        scheme_type="stable",
        stars=2,  # G005-C: PF=1.00 边界维持2星
        dir_acc=0.510,  # G005-C 396pt (was 0.550)
        mape=1.90,  # G005-C
        decay=1.27,  # G005-C
        coverage=0.527,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="rsi_state",  # Phase 11 审核修正 2026-08-20: hs(PF=1.05) → rsi_state(PF=1.09) 更优
        covariate_types=["rsi_state"],  # Phase 11: rsi/oi 均 1.09 > hs 1.05, 选 rsi_state
    ),

    "fg": VarietyScheme(
        symbol="fg",
        name="玻璃",
        scheme_type="stable",
        stars=1,  # G005-D: PF=0.91 → 降1星
        dir_acc=0.480,  # G005-D 396pt (was 0.553)
        mape=3.18,  # G005-D
        decay=1.35,  # G005-D
        coverage=0.759,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="ha_body",
    ),

    "bu": VarietyScheme(
        symbol="bu",
        name="沥青",
        scheme_type="short_range",
        stars=1,  # G005 2026-08-08: short加权后 PF=0.84 MaxDD深 → 降1星
        dir_acc=0.510,  # G005 396pt (was 0.540)
        mape=2.33,  # G005
        decay=1.27,  # G005
        coverage=0.525,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="calendar_cyclical",  # Phase 12 2026-08-21: baseline(ha_body) PF=0.79 FAIL → cal+hs PF=1.01 GREEN
        covariate_types=["calendar_cyclical", "hourly_slope"],  # Phase 12: 1 GREEN (cal+hs), 替换 ha_body
    ),

    "sh": VarietyScheme(
        symbol="sh",
        name="烧碱",
        scheme_type="oscillation",
        stars=1,  # 2026-08-21 初始: PF=0.74 DirAcc=43% 震荡型
        dir_acc=0.430,
        mape=2.68,  # 2026-08-21 refresh
        decay=1.35,  # 2026-08-21 refresh
        coverage=0.0,  # 短历史 (2023-08 上市), 138pts
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="reversal_shadow",  # Phase 11 best of 7 (PF=0.73 vs baseline ha_body 0.74), 弱信号品种
        covariate_types=["reversal_shadow"],
    ),

    "p": VarietyScheme(
        symbol="p",
        name="棕榈油",
        scheme_type="short_range",
        stars=1,  # G004: PF=1.014 刚过线、EV 微正，不足以升 2★
        dir_acc=0.540,  # G003 396pt (was 0.470 G005-B)
        mape=2.61,  # G003
        decay=1.32,  # G003
        coverage=0.610,  # G003 monthly report
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="rsi_state",  # combo 首位，与 covariate_types 对齐
        covariate_types=["rsi_state", "reversal_shadow"],  # G004 2026-08-17: G003 396pt v2 GREEN-EV (PF 0.89→1.014, EV 翻正, MaxDD -79.3%→-51.7%)
    ),

    "cf": VarietyScheme(
        symbol="cf",
        name="棉花",
        scheme_type="short_range",
        stars=1,  # G005-C: short PF=0.80 EV_r=-0.11 → 降1星
        dir_acc=0.510,  # G005-C 396pt (was 0.560)
        mape=1.56,  # G005-C
        decay=1.41,  # G005-C
        coverage=0.608,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="ha_body",  # combo 首位，与 covariate_types 对齐
        covariate_types=["ha_body", "calendar_cyclical"],  # 2026-07-30 Phase4d 固化: MAPE-9%/DirAcc+5pp/PF+16% 全达标
    ),

    "ao": VarietyScheme(
        symbol="ao",
        name="氧化铝",
        scheme_type="short_range",
        stars=1,  # G005-E: PF=0.86 n=193 维持1星
        dir_acc=0.450,  # G005-E 193pt
        mape=2.38,  # G005-E
        decay=1.40,  # G005-E
        coverage=0.619,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="hourly_slope",  # combo 首位，与 covariate_types 对齐
        covariate_types=["hourly_slope", "calendar_cyclical"],  # 2026-08-04 固化: v2 PASS (MAPE -15.7%, PF +16.5%, EV +543%)
        # ── Phase 9 有毒品种专攻 (2026-08-04) ──
        # ha_body 对 AO 有毒 (EV 转负 -0.054, MaxDD 翻倍 -57.92%)
        # 10 候选 walk-forward 回测, hourly_slope+calendar 唯一 v2 PASS
        # DirAcc 56%->52% (-3.7pp 代价), 但 EV +0.014->+0.090 (+543%), PF 1.03->1.20, MaxDD -35%->-29% (改善17.3%)
        # ⚠️ n=193 < 350 underpowered → stars=1 provisional (CF-21 A)
        # ── 历史归档 ──
        # Phase 9 (2026-08-03): hourly_slope 新鲜 baseline 56.0%, ha_body 有毒
    ),

    # ── 2026-06-28 新增: 基于四轮回测 (OI/CCL/RSI斜率/1H斜率) ──

    "eg": VarietyScheme(
        symbol="eg",
        name="乙二醇",
        scheme_type="stable",
        stars=2,  # G005-C: PF=1.00 边界维持2星
        dir_acc=0.510,  # G005-C 396pt (was 0.55)
        mape=2.46,  # G005-C
        decay=1.27,  # G005-C
        coverage=0.60,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="calendar_cyclical",  # Phase 11 基线对比 2026-08-20: baseline PF=0.92 FAIL → calendar PF=1.04 GREEN
        covariate_types=["calendar_cyclical"],  # Phase 11: 1 GREEN (cal=1.04), 替换 ha_body+oi+reversal_shadow
        # Phase 9: 10候选 backtest, ha_body+oi+reversal_shadow 全维最优
        # EV +0.047->+0.112 (+139%), PF 1.10->1.25, MaxDD -35.47%->-27.17%
        # 新进 2 星: DirAcc 55% 距 3 星差 10pp, 后续继续优化
    ),

    "lh": VarietyScheme(
        symbol="lh",
        name="生猪",
        scheme_type="stable",
        stars=2,  # G005-E: PF=1.05 n=231 underpowered 维持2星
        dir_acc=0.500,  # G005-E 231pt
        mape=2.82,  # G005-E
        decay=1.46,  # G005-E
        coverage=0.55,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.2,
        covariate_type="rsi_state",  # Phase 11 单协变量穷举 2026-08-20: PF=1.24 EV=+0.108 MaxDD=-36.7%
        covariate_types=["rsi_state"],  # Phase 11: 4 GREEN (rsi/rev/oi/ao), rsi 最强
        # 注: DirAcc 67%→57% (-10pp) 按 LH 特例 (spec §4) 可接受 — 看 EV/PF 含 clipping
    ),

    # ── 新增: 协变量扫描后补充的品种 ──

    "cj": VarietyScheme(
        symbol="cj",
        name="红枣",
        scheme_type="short_range",
        stars=2,  # G005-E: PF=1.26 n=317 维持2星（underpowered 但 PF 全场最高）
        dir_acc=0.520,  # G005-E 317pt
        mape=2.38,  # G005-E
        decay=1.47,  # G005-E
        coverage=0.5,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="hourly_slope",  # Phase 11 单协变量穷举 2026-08-20: PF=1.29 EV=+0.127 MaxDD=-21.4% 全场最高
        covariate_types=["hourly_slope"],  # Phase 11: 5 GREEN (hs/ao/oi/rev/rsi), hs 最强
        # scan 7pt: MAE 5.49%→4.87% (-0.62pp, 相对改善 11%); DirAcc 86% (scan 高估)
        # 注: monthly_backtest 396pt 因系统资源限制无法运行，基于 scan MAE 固化 (MAE 可靠 per spec §9.1)
        # 影线门控: 双向独立滤除 < 0.5 ATR 的小影线，滤除低流动性品种无意义日常波动
    ),

    "jd": VarietyScheme(
        symbol="jd",
        name="鸡蛋",
        scheme_type="stable",
        stars=2,  # G005-B: PF=1.06 弱正维持2星
        dir_acc=0.470,  # G005-B 396pt (was 0.52)
        mape=2.48,  # G005-B
        decay=1.42,  # G005-B
        coverage=0.51,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="rsi_state",  # Phase 11 审核修正 2026-08-20: hs(PF=1.06) → rsi_state(PF=1.09) 更优
        covariate_types=["rsi_state"],  # Phase 11: rsi_state(1.09) > hourly_slope(1.06)
        # ── Phase 9 优化历程 (2026-08-02) ──
        # 8 候选 full backtest: rsi_state+oi 全维最优
        # EV +0.045->+0.133 (+196%), PF 1.09->1.31 (+20.2%), MaxDD -33.92%->-30.10%
        # v2 verdict: PASS (ordinary) - PF +20.2%>=10%
        # 新进 2 星: DirAcc 52% 距 3 星 (65%) 差 13pp, 后续继续优化
        # 关键发现: ha_body 对 JD 有害 (EV 转负); calendar 稀释 rsi+oi 信号
        # ── 历史归档 ──
        # Phase 4d-2 (2026-07-30): calendar_cyclical, MaxDD 绿色通道
    ),

    "ma": VarietyScheme(
        symbol="ma",
        name="甲醇",
        scheme_type="stable",
        stars=1,  # G005-E: PF=0.71 维持1星
        dir_acc=0.490,  # G005-E 396pt
        mape=2.67,  # G005-E
        decay=1.29,  # G005-E
        coverage=0.5,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="hourly_slope",  # combo 首位，与 covariate_types 对齐
        covariate_types=["hourly_slope", "oi"],  # 扫描最优: T+1 bias=+2.26%
    ),

    "ta": VarietyScheme(
        symbol="ta",
        name="PTA",
        scheme_type="stable",
        stars=1,  # G005-B: PF=0.99 EV_r≈0 → 降1星（Phase9 PF1.43 旧口径虚高）
        dir_acc=0.530,  # G005-B 397pt (was 0.58)
        mape=2.33,  # G005-B
        decay=1.30,  # G005-B
        coverage=0.60,
        use_full_signal=True,
        short_horizon_only=False,
        confidence_multiplier=1.0,
        covariate_type="calendar_cyclical",  # Phase 11 单协变量穷举 2026-08-20: PF=1.03 EV=+0.015 MaxDD=-34.4% ⚠️ 边界值,待观察
        covariate_types=["calendar_cyclical"],  # Phase 11: calendar GREEN, ha_body 不在 GREEN 列
        # ── Phase 9 优化历程 (2026-08-02) ──
        # Round 1: 4 候选 (bb+calendar/ha_body+calendar/rsi+oi+calendar/calendar) → 全面退化或微幅改善未达 v2
        # Round 2: ha_body 变体 (ha_body/ha_body+bb/ha_body+rsi+oi/ha_body+oi) → ha_body 单独全维最优
        # v2 verdict: PASS (ordinary) — MAPE -4.9%≥3%, PF +12.6%≥10%, MaxDD 未恶化
        # 3 星距离: DirAcc 58% 距 65% 差 7pp, 受限于品种可预测性上限; PF=1.43 全系统最高
        # ── 历史归档 ──
        # Phase 2 (2026-07-28): ccl→bb_squeeze, DirAcc 43%→56%, MAPE 6.0%→2.26%
        # Phase 6 (2026-07-29): basis_momentum 退化, 归档
        # Phase 8a (2026-08-01): crack_spread 弱信号, 归档
    ),
}


# ─────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────

def get_scheme(symbol: str) -> Optional[VarietyScheme]:
    """获取品种方案，未固化则返回 None"""
    return SCHEMES.get(symbol.lower())


def is_solidified(symbol: str) -> bool:
    """品种是否已固化"""
    return symbol.lower() in SCHEMES


def list_solidified() -> list[str]:
    """所有已固化品种代码"""
    return list(SCHEMES.keys())


def list_by_stars(min_stars: int = 2) -> list[str]:
    """按 scheme.stars 筛选（信用档，2026-08-08 新口径 rebaseline 后无 3 星）。

    默认 min_stars=2 → 可辩护信用档（CJ/SS/SR/M/JD/LH/EG/RB）。
    CLI 历史名 --three-star 现映射到此列表。
    """
    return sorted(
        sym for sym, sc in SCHEMES.items() if int(sc.stars) >= int(min_stars)
    )


def signal_weight(horizon: int, scheme: VarietyScheme) -> np.ndarray:
    """
    根据衰减比为每个预测小时生成信号权重

    Args:
        horizon: 预测时域 (小时)
        scheme: 品种方案

    Returns:
        权重数组, shape (horizon,), 值域 [0, 1]
    """
    if scheme.use_full_signal and not scheme.short_horizon_only:
        # 全段信号: 按指数衰减加权
        decay = scheme.decay
        t = np.arange(1, horizon + 1, dtype=float)
        # 权重 = decay^(-t/horizon)，归一化到 [0, 1]
        w = decay ** (-t / horizon)
        return w
    else:
        if getattr(scheme, "smooth_cutoff", False):
            # Cosine rolloff (SPEC-007)
            plateau = 8   # Bar 1~8: full weight
            cutoff = 16   # Bar 9~16: cosine decay, Bar 17+: zero
            t = np.arange(1, horizon + 1, dtype=float)
            w = np.ones(horizon)
            decay_mask = (t > plateau) & (t <= cutoff)
            w[decay_mask] = 0.5 * (1 + np.cos(
                np.pi * (t[decay_mask] - plateau) / (cutoff - plateau)))
            w[t > cutoff] = 0.0
            return w
        else:
            # Hard cutoff (existing default)
            w = np.zeros(horizon, dtype=float)
            half = min(horizon // 2, 12)
            w[:half] = 1.0
            return w


def trend_direction(slope_pct_per_day: float, scheme: VarietyScheme) -> str:
    """
    判断趋势方向

    Args:
        slope_pct_per_day: 日线预测斜率 (已经是 %/天, 如 0.05 表示 0.05%/天)
        scheme: 品种方案

    Returns:
        "看多 ↑" / "看空 ↓" / "中性 →"
    """
    thr = scheme.trend_threshold_pct  # 已经是 %/天
    if slope_pct_per_day > thr:
        return "看多 ↑"
    elif slope_pct_per_day < -thr:
        return "看空 ↓"
    else:
        return "中性 →"


def confidence_band(
    quantile_forecast: np.ndarray,
    scheme: VarietyScheme,
) -> np.ndarray:
    """
    v2: log-space monotonic widening with Col 0 isolation.

    TimesFM 10-col contract:
      Col 0 = Point Forecast (Mean); Col 5 = P50 (Median)
      Col 1~4 = P10~P40; Col 6~9 = P60~P90

    Col 0 is NOT expanded or sorted — it passes through unchanged.
    """
    mult = scheme.confidence_multiplier
    if mult == 1.0:
        return quantile_forecast

    eps = 1e-6
    log_q = np.log(np.maximum(quantile_forecast, eps))
    log_median = log_q[:, 5:6]

    # Strict isolation: Col 0 keeps original value, only widen Col 1~9
    log_adjusted = log_q.copy()
    if log_adjusted.shape[-1] == 10:
        log_adjusted[:, 1:] = log_median + (log_q[:, 1:] - log_median) * mult
        log_adjusted[:, 1:] = np.sort(log_adjusted[:, 1:], axis=-1)
    else:
        log_adjusted[:, 1:] = log_median + (log_q[:, 1:] - log_median) * mult
        log_adjusted[:, 1:] = np.sort(log_adjusted[:, 1:], axis=-1)

    return np.exp(log_adjusted)


def scheme_summary(scheme: VarietyScheme) -> str:
    """生成品种方案摘要 (用于报告头部)"""
    lines = [
        f"**{scheme.name} ({scheme.symbol.upper()})** — {'⭐' * scheme.stars}",
        f"- 方案类型: {scheme.scheme_type}",
        f"- 回测 DirAcc: {scheme.dir_acc:.0%} | MAPE: {scheme.mape:.2f}% | 衰减: {scheme.decay:.2f}x",
        f"- 信号策略: {'全段 T+1~T+24' if scheme.use_full_signal else '短段 T+1~T+12'}",
        f"- 置信区间乘数: {scheme.confidence_multiplier:.2f}",
    ]
    return "\n".join(lines)
