"""OI 门控动量协变量 (oi_gated_momentum) — spec v2.1 唯一正式实现。

机制 (§2.2): 方向由价格单独决定，持仓项为非负门控 (半波整流截断门)：
    Signal_t = tanh(ΔP_5d,t × scale_P,t) × max(0, tanh(ΔOI^tot_5d,t × scale_OI,t))
增仓激活 (0→1 渐变)，减仓精确归零；四象限行为与 §2.1 机制表一致。

冻结口径：
- ΔP_5d = price.pct_change(5)，ΔOI^tot_5d = total_oi.pct_change(5)（相对变化，禁 diff）
- 定标：价格 |ΔP| 75% 分位（对称）；持仓带符号 ΔOI 85% 分位（单边非对称，免疫减仓下尾）
- 定标窗口 [t−K, t−1]：分位数算子显式 shift(1)，当期 bar 不进定标基准（§4.1 防样本内污染）
- 模块不内部 shift 输入序列（"已收盘"由调用方 get_safe_daily 保证）
- 输入 NaN/inf/bool/非数值 → 输出 NaN（fail-closed，§3.3）；纯函数，无 I/O，确定性
- 参数为冻结常量，慢环无运行时调参自由度；调用方见 spec §4
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sanitize_float(series: pd.Series) -> pd.Series:
    """float 化 + fail-closed 清洗：bool/非数值/inf → NaN，不做静默填充。"""
    if pd.api.types.is_bool_dtype(series):
        return pd.Series(np.nan, index=series.index, dtype=float)
    out = series
    if out.dtype == object:
        # bool 是 int 子类：混入 object 序列的 True/False 不得被当作 1/0
        out = out.map(lambda v: np.nan if isinstance(v, (bool, np.bool_)) else v, na_action="ignore")
    out = pd.to_numeric(out, errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan).astype(float)


def compute_oi_gated_momentum(
    price: pd.Series,
    total_oi: pd.Series,
    k: int = 120,
    q_price: float = 0.75,
    q_oi: float = 0.85,
) -> pd.Series:
    """计算 OI 门控动量日频信号（spec v2.1 §2.2/§2.3/§4.1 唯一口径）。

    Args:
        price: 已收盘日收盘价 (DatetimeIndex, 由 get_safe_daily 保证)。
        total_oi: 全市场总持仓 (KQ.i@m 指数合约)，同一日历、同为已收盘 bar (§3.4 对齐)。
        k: 定标窗口，冻结 (120)。
        q_price: 价格 |ΔP| 分位数，冻结 (0.75)。
        q_oi: 持仓带符号 ΔOI 分位数，冻结 (0.85)。

    Returns:
        日频信号 pd.Series (float, 同 index, name="oi_gated_momentum")，
        NaN = 不可用 (fail-closed)。

    参数冻结语义：参数仅为符合 spec §4 API 形状而存在；生产调用 (extract_xreg 注册 /
    cascade 特征流水线) 必须使用默认值，不允许运行时注入覆盖——慢环无调参自由度。

    输入契约：两序列同窗对齐于已收盘 bar；模块不内部 shift 输入序列；
    定标窗口 [t−K, t−1] 由分位数算子显式 shift(1) 实现 (§4.1)。
    """
    # 索引一致性硬校验（宿主要求：入口第一行；§2.2 同窗对齐前提）
    if not price.index.equals(total_oi.index):
        raise ValueError(
            "price 与 total_oi 索引必须完全一致 (同窗对齐于已收盘 bar): "
            f"price[{len(price)}] vs total_oi[{len(total_oi)}]"
        )

    p = _sanitize_float(price)
    oi = _sanitize_float(total_oi)

    # §2.3 算子口径：Δ = pct_change(5) 相对变化，禁 diff(5)
    abs_delta_p = p.pct_change(5).abs()
    delta_oi = oi.pct_change(5)

    # §4.1 标尺严格基于 [t−K, t−1]：必须显式 shift(1) 排除当期 bar（防样本内污染）
    q_p = abs_delta_p.shift(1).rolling(k).quantile(q_price)
    q_oi = delta_oi.shift(1).rolling(k).quantile(q_oi)

    # §3.3 定标分位数防御：非正/缺失 → NaN，绝不产生 inf
    with np.errstate(divide="ignore", invalid="ignore"):
        scale_p = np.where(q_p > 1e-6, 1.0 / q_p, np.nan)
        scale_oi = np.where(q_oi > 1e-6, 1.0 / q_oi, np.nan)
    scale_p = pd.Series(scale_p, index=p.index)
    scale_oi = pd.Series(scale_oi, index=p.index)

    # 因子本体用当期已收盘 bar t
    signal = np.tanh(p.pct_change(5) * scale_p) * np.maximum(
        0.0, np.tanh(delta_oi * scale_oi)
    )
    return pd.Series(signal, index=p.index, name="oi_gated_momentum", dtype=float)
