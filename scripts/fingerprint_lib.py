"""实验身份指纹系统（PR-B1）

基于内容哈希的实验身份系统，替代字符串 variant_id 去重。
检测"语义相同但 variant_id 不同"的实验。

指纹类型：
- cov_fingerprint: 协变量配置指纹
- protocol_fingerprint: 协议配置指纹
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


def compute_cov_fingerprint(cov_config):
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


def compute_protocol_fingerprint(protocol_config):
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
    对每个文件取前 4KB + 文件大小做 SHA-256，
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
        file_size = file_path.stat().st_size

        # 读取前 4KB
        with open(file_path, 'rb') as f:
            first_4kb = f.read(4096)

        # 计算文件指纹：大小 + 前 4KB
        file_data = f"{file_size}:{first_4kb.hex()}"
        file_sha256 = hashlib.sha256(file_data.encode('utf-8')).hexdigest()
        file_fingerprints.append(file_sha256)

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
    """计算基于指纹的 variant_id

    向后兼容：如果指纹计算失败，回退到旧格式（symbol_cov）+ WARN 日志。

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
    try:
        cov_fp = compute_cov_fingerprint(cov_config)
        proto_fp = compute_protocol_fingerprint(protocol_config)
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

    except (ValueError, FileNotFoundError, TypeError) as e:
        # 回退到旧格式
        import sys
        print(f"[WARN] Failed to compute fingerprint-based variant_id: {e}. "
              f"Falling back to legacy format.", file=sys.stderr)
        return f"{symbol}_{cov}", None
