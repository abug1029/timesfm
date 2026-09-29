"""实验指纹（spec §4.2 W2.1③ / §4.5 W6.4）。

**唯一家**：`experiment_fingerprint` 由本模块计算，任何其它地方不得自造。

组成（spec W2.1③）：
- `weight_fingerprint`：模型权重身份（路径 + 版本 hash）
- `target_snapshot_hash`：本次实验所用目标数据的内容 hash（**随运行变化**）
- `context_config_hash`：context 配置身份（bars / horizon / 协变量组合）

**命名注意**（spec v8）：
- `experiment_fingerprint` = 单次实验身份，随运行变化
- `research_target_hash`（cascade/research_family.py）= 研究问题**身份**，稳定
- 二者不得混用：前者决定"实验记录可否合并"，后者决定"是不是同一 family"
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Sequence

# ── 48-bit 截断常量（spec W6.4）─────────────────────────────

TRUNCATE_HEX_LEN = 12  # 12 hex = 48 bits
FULL_HEX_LEN = 64       # SHA-256 完整长度


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── 子指纹 ──────────────────────────────────────────────────


def weight_fingerprint(weights_dir: str | Path) -> str:
    """模型权重身份：对权重目录路径 + 版本文件内容哈希。

    不含权重数值本身（太大），只标识"这组权重"。同一路径 + 同一版本文件
    内容 -> 同指纹；权重更新后版本文件必变，故指纹必变。
    """
    weights_dir = Path(weights_dir)
    if not weights_dir.is_dir():
        raise FileNotFoundError(f"weights_dir 不存在: {weights_dir}")
    version_file = weights_dir / "version.txt"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "no-version-file"
    payload = f"weights:{weights_dir.resolve()}|version:{version}"
    return _sha256_hex(payload)


def target_snapshot_hash(target_data: Sequence[float] | bytes) -> str:
    """目标数据内容 hash（**随运行变化**）。

    spec v8：`target_snapshot_hash` 决定"实验记录可否合并"，与决定"是不是同一 family"
    的 `research_target_hash` **不得混用**。
    """
    if isinstance(target_data, (bytes, bytearray)):
        payload_bytes = bytes(target_data)
    else:
        # 浮点序列：按字节序列化（little-endian double），确保字节级确定性
        import struct

        payload_bytes = b"".join(struct.pack("<d", float(x)) for x in target_data)
    return hashlib.sha256(payload_bytes).hexdigest()


def context_config_hash(
    context_bars: int,
    horizon: int,
    step: int,
    covariates: Iterable[str],
) -> str:
    """context 配置身份。"""
    covs_sorted = "|".join(sorted(covariates))
    payload = f"ctx:{context_bars}|hz:{horizon}|step:{step}|covs:{covs_sorted}"
    return _sha256_hex(payload)


# ── 主指纹 ──────────────────────────────────────────────────


def compute_experiment_fingerprint(
    weights_dir: str | Path,
    target_data: Sequence[float] | bytes,
    context_bars: int,
    horizon: int,
    step: int,
    covariates: Iterable[str],
) -> str:
    """spec W2.1③ / W6.4 实验指纹（唯一家）。

    Returns:
        完整 SHA-256 hex（64 字符）。调用方通过 [:12] 取 48-bit 截断用于 variant_id。
    """
    wf = weight_fingerprint(weights_dir)
    ts = target_snapshot_hash(target_data)
    cc = context_config_hash(context_bars, horizon, step, covariates)
    payload = f"{wf}|{ts}|{cc}"
    return _sha256_hex(payload)


def truncate_for_variant_id(experiment_fingerprint: str) -> str:
    """48-bit 截断用于 variant_id。"""
    if len(experiment_fingerprint) != FULL_HEX_LEN:
        raise ValueError(f"指纹长度错误: {len(experiment_fingerprint)} != {FULL_HEX_LEN}")
    return experiment_fingerprint[:TRUNCATE_HEX_LEN]


# ── variant_id 构造 ──────────────────────────────────────────


def build_variant_id(
    symbol: str,
    cov_family: str,
    experiment_fingerprint: str,
) -> str:
    """spec W6.4 variant_id 身份键。

    格式：`{symbol}_{cov_family}_{experiment_fingerprint[:12]}`
    协变量请求名（cov_override）**不参与**身份键，只作 `cov_requested` 可读字段。
    """
    if not symbol:
        raise ValueError("symbol 不得为空")
    if not cov_family:
        raise ValueError("cov_family 不得为空")
    trunc = truncate_for_variant_id(experiment_fingerprint)
    return f"{symbol}_{cov_family}_{trunc}"


# ── 48-bit 碰撞论证（H4）───────────────────────────────────


def birthday_collision_probability(n_variants: int, bits: int = 48) -> float:
    """经典生日问题：n 个变体在 2^bits 空间中的至少一次碰撞概率近似。

    p ≈ 1 - exp(-n(n-1)/2 * 2^-bits)
    """
    import math

    space = 2.0 ** bits
    exponent = -n_variants * (n_variants - 1) / (2.0 * space)
    return 1.0 - math.exp(exponent)


def expected_collisions(n_variants: int, bits: int = 48) -> float:
    """期望碰撞对数 ≈ n(n-1)/2 * 2^-bits。"""
    return n_variants * (n_variants - 1) / (2.0 * (2 ** bits))
