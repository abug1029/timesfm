"""Horizon 尾填充契约（spec §4.5 W5.1-W5.3）。

**唯一家**：horizon_known 分类只写在 `task_FM/config/covariate_pool.json`，
本模块与 `features.py` 一律读它。禁止按协变量名硬编码判断（spec W5.1）。

四类受控词表与填充策略（spec W5.1 表）：

| horizon_known      | 含义                                   | horizon 填充      | 外生 |
|--------------------|----------------------------------------|-------------------|------|
| `known_ahead`      | cutoff 时点确实已知未来值               | 真实未来值        | 是   |
| `persistence`      | 未来不可知，可用末值延续近似           | 末值              | 否   |
| `self_referential` | 未来值来自模型自身输出                  | 现状保留 + 标记   | 否   |
| `unknowable`       | 既不可知也无法近似                      | 末值 + 标记       | 否   |

W5.2：其余三类填**末值**（替代历史实现里的 zeros / decay），并落
`horizon_fill="persistence"`。`horizon_std > 0` 只允许出现在 `known_ahead` 类。

W5.3（安全关键项）不变量：
1. 填充函数**只接受** `horizon_known` 参数决定分支，**不**接受协变量名；
2. 非 `known_ahead` 的 horizon 段**逐值等于** context 末值；
3. `known_ahead` 的 horizon 值可由 cutoff 时点已知输入重算。
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

HORIZON_KNOWN_VOCAB = ("known_ahead", "persistence", "self_referential", "unknowable")

FILL_REAL_FUTURE = "real_future"
FILL_PERSISTENCE = "persistence"
FILL_SELF_REFERENTIAL = "self_referential"

_POOL_PATH = (
    Path(__file__).resolve().parent.parent / "task_FM" / "config" / "covariate_pool.json"
)


class HorizonContractError(ValueError):
    """违反 spec W5.3 前视防护不变量（fail-loud，不静默降级）。"""


@functools.lru_cache(maxsize=1)
def _load_pool() -> dict:
    with open(_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


def reload_pool() -> None:
    """测试用：pool 变更后清缓存。"""
    _load_pool.cache_clear()


# 输出标签 -> pool 键。仅做名称解析，分类仍一律读 covariate_pool.json。
# 这些标签由 features.py 的分支产出，与 pool 键同名的情况占绝大多数。
OUTPUT_LABEL_TO_POOL_KEY = {
    "oi_pct_change": "oi",
    "ccl_pct": "ccl",
    "calendar_doy_sin": "calendar_cyclical",
    "calendar_doy_cos": "calendar_cyclical",
    "calendar_month_sin": "calendar_cyclical",
    "calendar_month_cos": "calendar_cyclical",
}


def resolve_pool_key(label: str) -> str:
    """把构建器产出的输出标签解析回 covariate_pool.json 的键。"""
    return OUTPUT_LABEL_TO_POOL_KEY.get(label, label)


def get_horizon_known(covariate_type: str) -> str:
    """读该协变量的 horizon_known 分类（唯一家 = covariate_pool.json）。

    缺失即报错，**禁止默认值兜底**（spec W5.1：缺失即校验失败）。
    """
    covariates = _load_pool().get("covariates")
    if not isinstance(covariates, dict):
        raise HorizonContractError("covariate_pool.json 缺 covariates 段")

    entry = covariates.get(covariate_type)
    if entry is None:
        raise HorizonContractError(
            f"covariate_pool.json 无 {covariate_type!r} 条目，无法确定 horizon_known"
        )

    hk = entry.get("horizon_known")
    if hk is None:
        raise HorizonContractError(
            f"{covariate_type} 缺 horizon_known（spec W5.1 禁止默认值兜底）"
        )
    if hk not in HORIZON_KNOWN_VOCAB:
        raise HorizonContractError(
            f"{covariate_type}.horizon_known={hk!r} 不在受控词表 {HORIZON_KNOWN_VOCAB}"
        )

    if hk == "known_ahead" and not entry.get("known_ahead_evidence"):
        raise HorizonContractError(
            f"{covariate_type} 标 known_ahead 但缺 known_ahead_evidence（spec W5.1 必填）"
        )
    return hk


def fill_horizon(
    context: np.ndarray,
    horizon: int,
    horizon_known: str,
    *,
    real_future: np.ndarray | None = None,
) -> tuple[np.ndarray, str]:
    """按 horizon_known 决定 horizon 尾段填充（spec W5.3① 唯一分支点）。

    本函数**只接受** `horizon_known` 参数决定分支，**不**接受协变量名 ——
    分类由调用方从 pool 读好后传入，填充逻辑对任何协变量名一视同仁。

    Args:
        context: context 段序列（末值即 persistence 的填充值）
        horizon: horizon 段长度
        horizon_known: 四类受控词表之一
        real_future: known_ahead 类的真实未来值（其余类必须为 None）

    Returns:
        (horizon 段数组, horizon_fill 标签)

    Raises:
        HorizonContractError: 词表非法、known_ahead 缺真实未来值、
            或其余类误传 real_future。
    """
    if horizon_known not in HORIZON_KNOWN_VOCAB:
        raise HorizonContractError(
            f"horizon_known={horizon_known!r} 不在受控词表 {HORIZON_KNOWN_VOCAB}"
        )
    if horizon <= 0:
        raise HorizonContractError(f"horizon 必须为正，得到 {horizon}")

    ctx = np.asarray(context, dtype=float).ravel()
    if ctx.size == 0:
        raise HorizonContractError("context 为空，无法确定末值")

    last = float(ctx[-1])

    if horizon_known == "known_ahead":
        if real_future is None:
            raise HorizonContractError(
                "known_ahead 类必须提供 real_future（spec W5.2：禁止从含未来数据的表取值）"
            )
        rf = np.asarray(real_future, dtype=float).ravel()
        if rf.size != horizon:
            raise HorizonContractError(
                f"real_future 长度 {rf.size} != horizon {horizon}"
            )
        return rf, FILL_REAL_FUTURE

    if real_future is not None:
        raise HorizonContractError(
            f"{horizon_known} 类不得携带 real_future：非 known_ahead 不得引入未来信息"
        )

    if horizon_known == "self_referential":
        # spec W5.1：现状保留，但必须标记。现状即末值延续。
        return np.full(horizon, last, dtype=float), FILL_SELF_REFERENTIAL

    # persistence / unknowable：填末值（spec W5.2 替代历史 zeros / decay）
    return np.full(horizon, last, dtype=float), FILL_PERSISTENCE


def verify_horizon_invariant(
    covariate_type: str,
    covariate_full: np.ndarray,
    context_len: int,
    horizon: int,
) -> str:
    """加载时断言（spec W5.3② / W5.5③）：校验并返回 horizon_fill 标签。

    - 非 `known_ahead`：horizon 段必须**逐值等于** context 末值
      （确实是 persistence，而非泄漏了真值）；
    - `known_ahead`：允许非恒定（horizon_std > 0 是预期行为）。

    Raises:
        HorizonContractError: 不变量被破坏。
    """
    arr = np.asarray(covariate_full, dtype=float).ravel()
    if arr.size != context_len + horizon:
        raise HorizonContractError(
            f"{covariate_type}: 长度 {arr.size} != context {context_len} + horizon {horizon}"
        )

    hk = get_horizon_known(resolve_pool_key(covariate_type))
    hz = arr[context_len:]

    if hk == "known_ahead":
        return FILL_REAL_FUTURE

    last = float(arr[context_len - 1])
    if not np.allclose(hz, last, rtol=0, atol=1e-12):
        std = float(np.std(hz))
        raise HorizonContractError(
            f"{covariate_type}（{hk}）horizon 段非 persistence: "
            f"期望逐值 = {last:.6g}，实际 std={std:.6g}，"
            f"min={hz.min():.6g} max={hz.max():.6g}。"
            "spec W5.3②：非 known_ahead 的 horizon 段必须逐值等于 context 末值"
        )
    return FILL_SELF_REFERENTIAL if hk == "self_referential" else FILL_PERSISTENCE


def horizon_exogenous(covariate_types) -> bool:
    """verdict 的 horizon_exogenous：任一协变量为 known_ahead 即为 True（spec W5.3④）。

    §4.3 的成功判定**不因该字段加分** —— 它只用于诊断"这次评估是否真的拿到了未来信息"。
    """
    return any(get_horizon_known(c) == "known_ahead" for c in (covariate_types or []))
