"""协变量诊断系统（PR-B2）

采集诊断字段，让"协变量未利用"成为可验证事实。

诊断字段：
- cov_effective: 有效协变量通道数（非全零且 horizon 非全零）
- inert_constant: 惰性常数通道名列表（context 部分 std < 1e-12）
- horizon_flat: horizon 平坦通道名列表（horizon 部分全零）
- all_zero: 全零通道名列表
"""

import numpy as np


def diagnose_covariates(covariates, context_len):
    """诊断协变量有效性

    Args:
        covariates: 协变量字典，例如：
            {"daily_slope": np.array([...]), "ccl_pct": np.array([...])}
        context_len: context 长度

    Returns:
        dict: {
            "cov_effective": int,  # 有效通道数
            "inert_constant": list,  # 惰性常数通道名
            "horizon_flat": list,  # horizon 平坦通道名
            "all_zero": list  # 全零通道名
        }
    """
    if not covariates:
        return {
            "cov_effective": 0,
            "inert_constant": [],
            "horizon_flat": [],
            "all_zero": []
        }

    inert_constant = []
    horizon_flat = []
    all_zero = []
    cov_effective = 0

    for name, arr in covariates.items():
        if not isinstance(arr, np.ndarray):
            continue

        # PR-B2 评审修复: NaN 通道不应被计为有效
        if np.all(np.isnan(arr)):
            continue

        # 分割 context 和 horizon
        context_part = arr[:context_len]
        horizon_part = arr[context_len:]

        # 检查全零
        if np.all(arr == 0):
            all_zero.append(name)
            continue

        # 检查 context 部分是否惰性常数（std < 1e-12）
        # PR-B2 评审修复: 使用 nanstd 避免 NaN 污染
        context_std = np.nanstd(context_part)
        if context_std < 1e-12:
            inert_constant.append(name)
            continue

        # 检查 horizon 部分是否平坦（全零）
        if len(horizon_part) > 0 and np.all(horizon_part == 0):
            horizon_flat.append(name)
            continue

        # 有效通道
        cov_effective += 1

    return {
        "cov_effective": cov_effective,
        "inert_constant": inert_constant,
        "horizon_flat": horizon_flat,
        "all_zero": all_zero
    }
