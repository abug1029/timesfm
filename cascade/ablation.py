"""三路消融系统（PR-B5）

区分内容效应与通道效应。审计集上跑完整三路对照。

消融模式：
- FULL: 真实协变量
- BASELINE: 无协变量（纯 TimesFM）
- CONTENT: 结构保留，内容随机（shuffle）
- STRUCTURAL: 协变量置零（走相同代码路径）
"""

from enum import Enum
from typing import Dict, Optional
import numpy as np


class AblationMode(Enum):
    """消融模式枚举"""
    FULL = "full"
    BASELINE = "baseline"
    CONTENT = "content"
    STRUCTURAL = "structural"


def ablate_content_covariates(covariates: Dict[str, np.ndarray], seed: int = 42) -> Dict[str, np.ndarray]:
    """内容消融：保持 shape 不变，沿时间轴(axis 0)打乱

    保留 marginal distribution，破坏 autocorrelation。

    **输入形状语义（务必注意，两种形状不等价）**：
    - 本管线按通道传入 **1-D 数组**（`{name: arr}`），各通道**独立**打乱，
      通道间同期相关性一并被破坏 —— 这是审计集采用的语义。
    - 若传入 (T, K) 矩阵，则整行一起移动，**保留**通道间同期相关性。
    两种形状的消融不可比，审计集一律走 1-D 逐通道，不要混用。

    Args:
        covariates: 协变量字典 {name: 1-D array}
        seed: 随机种子（保证确定性）

    Returns:
        消融后的协变量字典
    """
    if not covariates:
        return {}

    rng = np.random.default_rng(seed)
    ablated = {}

    for name, arr in covariates.items():
        if not isinstance(arr, np.ndarray):
            ablated[name] = arr
            continue

        # 沿 axis 0 (时间轴) 打乱（保持 shape）；显式写出轴，避免多维下语义含糊
        idx = rng.permutation(arr.shape[0])
        ablated[name] = arr[idx]

    return ablated


def ablate_structural_covariates(covariates: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """结构消融：协变量通道全部置零

    与 baseline 的区别：走 forecast_with_covariates 相同代码路径，
    分离"代码路径差异"和"协变量信息差异"。

    Args:
        covariates: 协变量字典 {name: array}

    Returns:
        消融后的协变量字典（全部置零）
    """
    if not covariates:
        return {}

    ablated = {}
    for name, arr in covariates.items():
        if not isinstance(arr, np.ndarray):
            ablated[name] = arr
            continue

        # 置零（保持 shape 和 dtype）
        ablated[name] = np.zeros_like(arr)

    return ablated


def load_ablation_audit_config(config_path: Optional[str] = None) -> Dict:
    """加载消融审计集配置

    Args:
        config_path: 配置文件路径（默认 task_FM/config/ablation_audit_config.json）

    Returns:
        配置字典
    """
    import json
    import os

    if config_path is None:
        # 默认路径：config/ 存放静态策略配置（task_FM/config/ 存放运行时状态）
        fm_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(fm_root, "config", "ablation_audit_config.json")

    if not os.path.exists(config_path):
        # 返回默认配置
        return {
            "schema": "fm.ablation_audit.v1",
            "symbols": ["ss", "sr", "m"],
            "covariates": ["rsi_state", "calendar_cyclical", "hourly_slope"],
            "modes": ["full", "content", "structural", "baseline"]
        }

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def is_audit_candidate(symbol: str, covariate: str, config: Optional[Dict] = None) -> bool:
    """检查是否是审计集候选

    Args:
        symbol: 品种代码
        covariate: 协变量名称
        config: 审计集配置（默认加载）

    Returns:
        是否是审计集候选
    """
    if config is None:
        config = load_ablation_audit_config()

    audit_symbols = config.get("symbols", [])
    audit_covariates = config.get("covariates", [])

    return symbol in audit_symbols and covariate in audit_covariates
