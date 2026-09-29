"""实验身份指纹系统（PR-B1）

**状态：库实现。生产接线留待 Stage 3。**

`compute_variant_id()` 当前**无生产调用方**（仅测试调用）。原计划（PR-B1 步骤 2）
要求把指纹嵌入 `variant_id`，但取证后决定不接线，理由：

1. 生产 registry 的 143 条裁决**全部**为 `"{symbol}_{cov}"` 旧格式。
   改格式会使 `dead_variants()` / `pass_variants()` / 新颖性判定全部落空 ——
   已失败组合会被当作新颖重新提案，且同一实验可能出现两个 id。
2. 这 143 条同时**缺失全部 18 个 A1 字段**（`pass_variants` 返回 0），
   属 pre-Stage-1 遗留数据（registry 冻结于 2026-09-24 06:25，
   Stage 1 A1 接线落于 2026-09-27）。迁移它们收益存疑。
3. Stage 1 已在 verdict 上落地 per-verdict 指纹字段
   （`protocol_fingerprint` / `cov_fingerprint` / `sample_fingerprint`），
   承载同一"内容可比性"能力，无需在 variant_id 上重复编码。

**命名注意（PR-B1 评审修复）**：本模块的配置指纹函数已重命名为
`compute_cov_config_fingerprint` / `compute_protocol_config_fingerprint`，
以区别于 `task_FM/evaluations/fm_eval/evaluator.py` 中 Stage 1 的同名函数
（后者哈希**数值矩阵** `compute_cov_fingerprint(matrix, keys)`，
本模块哈希**配置 dict**）。两者语义不同、不可互换。

指纹类型：
- cov_config_fingerprint: 协变量**配置**指纹（哈希 config dict）
- protocol_config_fingerprint: 协议**配置**指纹（哈希 config dict）
- weight_fingerprint: 模型权重指纹
- seed_fingerprint: 随机种子指纹

规范序列化规则（所有指纹共享）：
- dict 按键排序后 JSON dumps
- NaN → 字符串 "<NaN>"
- Inf/-Inf → 抛 ValueError (fail-loud)
- SHA-256 十六进制前 16 位
"""

import hashlib
import json
import math
import os
from pathlib import Path


def _canonical_serialize(obj):
    """规范序列化对象为字符串

    规则：
    - dict: 按键排序后 JSON dumps
    - NaN: 转为字符串 "<NaN>"
    - Inf/-Inf: 抛 ValueError (fail-loud)
    - 嵌套 dict/list: 递归处理
    """
    if isinstance(obj, dict):
        # 按键排序
        sorted_items = sorted(obj.items(), key=lambda x: x[0])
        serialized = {}
        for k, v in sorted_items:
            serialized[k] = _canonical_serialize(v)
        return serialized
    elif isinstance(obj, list):
        return [_canonical_serialize(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj):
            return "<NaN>"
        elif math.isinf(obj):
            raise ValueError(f"Infinite values not allowed in fingerprint input: {obj}")
        return obj
    else:
        return obj


def _compute_sha256(data_str):
    """计算 SHA-256 哈希，返回前 16 位十六进制"""
    hash_bytes = hashlib.sha256(data_str.encode('utf-8')).digest()
    return hash_bytes.hex()[:16]


def compute_cov_config_fingerprint(cov_config):
    """协变量配置指纹

    Args:
        cov_config: 协变量配置 dict，例如：
            {"covariate_type": "rsi_state", "horizon": 24,
             "half_life_bars": 12, "fill_strategy": "zero"}

    Returns:
        dict: {"keys_sha256": "...", "n_channels": 1, "hash_version": "v1"}

    Raises:
        ValueError: 如果配置包含 Inf 值
    """
    try:
        canonical = _canonical_serialize(cov_config)
        json_str = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
        sha256 = _compute_sha256(json_str)

        # n_channels: 从配置推断通道数
        # 简单实现：如果配置中有 "channels" 键则使用，否则默认为 1
        n_channels = cov_config.get('n_channels', 1)

        return {
            "keys_sha256": sha256,
            "n_channels": n_channels,
            "hash_version": "v1"
        }
    except ValueError as e:
        raise ValueError(f"Failed to compute cov_fingerprint: {e}")


def compute_protocol_config_fingerprint(protocol_config):
    """协议配置指纹

    Args:
        protocol_config: 协议配置 dict，例如：
            {"min_n": 350, "min_ic": 0.05, "stage": "aligned",
             "max_points": 600, "aligned": true}

    Returns:
        dict: {"protocol_sha256": "...", "hash_version": "v1"}

    Raises:
        ValueError: 如果配置包含 Inf 值
    """
    try:
        canonical = _canonical_serialize(protocol_config)
        json_str = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
        sha256 = _compute_sha256(json_str)

        return {
            "protocol_sha256": sha256,
            "hash_version": "v1"
        }
    except ValueError as e:
        raise ValueError(f"Failed to compute protocol_fingerprint: {e}")


def compute_weight_fingerprint(weights_dir):
    """模型权重指纹

    扫描权重目录下所有模型文件，计算指纹。
    对每个文件流式哈希**完整内容**（SHA-256），
    然后合并所有文件指纹再做一次 SHA-256。

    Args:
        weights_dir: 权重目录路径 (str 或 Path)

    Returns:
        dict: {"weights_sha256": "...", "n_files": 3, "hash_version": "v1"}

    Raises:
        FileNotFoundError: 如果目录不存在
    """
    weights_path = Path(weights_dir)
    if not weights_path.exists():
        raise FileNotFoundError(f"Weights directory not found: {weights_dir}")

    # 支持的模型文件扩展名
    model_extensions = {'.safetensors', '.bin', '.pt', '.pth', '.ckpt'}

    # 收集所有模型文件
    model_files = []
    for file_path in weights_path.rglob('*'):
        if file_path.is_file() and file_path.suffix in model_extensions:
            model_files.append(file_path)

    if not model_files:
        raise FileNotFoundError(f"No model files found in {weights_dir}")

    # 对每个文件计算指纹
    file_fingerprints = []
    for file_path in sorted(model_files):  # 排序保证确定性
        # PR-B1 评审修复: 流式哈希**整个文件**，不再只取前 4KB。
        # 原实现只读前 4KB + 文件大小，对"仅末层权重变化、文件大小不变"的
        # 重训练会给出相同指纹 → 不同模型被误判为同一实验（假去重）。
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                hasher.update(chunk)
        file_fingerprints.append(hasher.hexdigest())

    # 合并所有文件指纹
    combined = ":".join(file_fingerprints)
    combined_sha256 = _compute_sha256(combined)

    return {
        "weights_sha256": combined_sha256,
        "n_files": len(model_files),
        "hash_version": "v1"
    }


def compute_seed_fingerprint(seed):
    """随机种子指纹

    Args:
        seed: 随机种子整数

    Returns:
        dict: {"seed": 42, "seed_sha256": "...", "hash_version": "v1"}
    """
    if not isinstance(seed, int):
        raise TypeError(f"seed must be int, got {type(seed)}")

    seed_str = str(seed)
    sha256 = _compute_sha256(seed_str)

    return {
        "seed": seed,
        "seed_sha256": sha256,
        "hash_version": "v1"
    }


def compute_variant_id(symbol, cov, cov_config, protocol_config, weights_dir, seed=None):
    """计算基于指纹的 variant_id。

    H3 (spec W6.4 fail-loud)：指纹计算失败**不再**静默回退到旧格式，必须抛出。

    Args:
        symbol: 品种代码 (str)
        cov: 协变量名称 (str)
        cov_config: 协变量配置 dict
        protocol_config: 协议配置 dict
        weights_dir: 权重目录路径
        seed: 随机种子 (可选)

    Returns:
        str: variant_id
    """
    # H3 (spec W6.4 fail-loud)：指纹计算失败必须原样抛出。
    # 旧版本曾静默回退到 "{symbol}_{cov}" 格式（违反 fail-loud），现已移除。
    cov_fp = compute_cov_config_fingerprint(cov_config)
    proto_fp = compute_protocol_config_fingerprint(protocol_config)
    weight_fp = compute_weight_fingerprint(weights_dir)

    # 截取指纹前 8 位
    cov_short = cov_fp["keys_sha256"][:8]
    proto_short = proto_fp["protocol_sha256"][:8]
    weight_short = weight_fp["weights_sha256"][:8]

    vid = f"{symbol}_{cov}_cov_{cov_short}_proto_{proto_short}_wt_{weight_short}"

    if seed is not None:
        seed_fp = compute_seed_fingerprint(seed)
        seed_short = seed_fp["seed_sha256"][:8]
        vid = f"{vid}_seed_{seed_short}"

    return vid, {
        "cov_fingerprint": cov_fp,
        "protocol_fingerprint": proto_fp,
        "weight_fingerprint": weight_fp,
        "seed_fingerprint": seed_fp if seed is not None else None
    }
