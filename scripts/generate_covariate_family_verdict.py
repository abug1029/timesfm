"""生成协变量族诊断矩阵 — PR-C5 实施"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional


def load_verdicts(registry_path: str) -> list[dict]:
    """加载 registry 文件"""
    verdicts = []
    with open(registry_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                verdicts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return verdicts


def build_verdict_matrix(
    verdicts: list[dict],
    protocol_fingerprint: str,
    all_symbols: Optional[set[str]] = None,
) -> dict:
    """
    生成族×品种诊断矩阵（spec §4.4 W4①）

    Args:
        verdicts: 裁决列表
        protocol_fingerprint: 协议指纹（用于过滤可比 verdict）
        all_symbols: 全部品种集合（默认 8 品种）

    Returns:
        dict: 诊断矩阵

    分母要求:
        n_evaluated 定义：有 verdict 且 protocol_fingerprint 一致
        且 covariates_used == True 的品种数
        无法计算的品种（数据缺失/构造失败）不计入分母，且必须单列
    """
    if all_symbols is None:
        all_symbols = {"ss", "sr", "m", "jd", "lh", "cj", "fu", "rb"}

    # 过滤: protocol_fingerprint 一致 + covariates_used == True
    filtered = [
        v for v in verdicts
        if v.get("protocol_fingerprint") == protocol_fingerprint
        and v.get("covariates_used") is True
    ]

    # 按协变量类型分组
    by_cov = defaultdict(list)
    for v in filtered:
        # cov_override 是协变量类型字段名（可能是 covariate_type 或 cov_override）
        cov_type = v.get("covariate_type") or v.get("cov_override")
        if cov_type:
            by_cov[cov_type].append(v)

    # 计算 n_evaluated（每个协变量类型被评估的品种数）
    n_evaluated = {
        cov: len(vs) for cov, vs in by_cov.items()
    }

    # 构建矩阵
    matrix = {}
    for cov_type, vs in by_cov.items():
        matrix[cov_type] = {}
        for v in vs:
            symbol = v.get("symbol")
            if symbol:
                matrix[cov_type][symbol] = {
                    "inert_constant": v.get("inert_constant", False),
                    "all_zero": v.get("all_zero", False),
                    "ablation_content_delta": v.get("ablation_content_delta"),
                    "evidence": f"verdict_{v.get('variant_id', 'unknown')}"
                }

    # 识别不可计算品种
    evaluated_symbols = set()
    for cov_matrix in matrix.values():
        evaluated_symbols.update(cov_matrix.keys())
    incomputable = all_symbols - evaluated_symbols

    return {
        "schema": "fm.covariate_family_verdict.v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_evaluated": n_evaluated,
        "matrix": matrix,
        "incomputable_symbols": {
            sym: "no_verdict" for sym in sorted(incomputable)
        },
        "diagnostic_thresholds": {
            "n_evaluated_min": 8,
            "sector_coverage_min": 2,
            "inert_ratio_max": 0.6,
            "note": "仅诊断提示, 不自动归档"
        }
    }


def generate_verdict_matrix(
    registry_path: str,
    protocol_fingerprint: str,
    output_path: str = "task_FM/config/covariate_family_verdict.json",
) -> dict:
    """
    生成并保存协变量族诊断矩阵

    Args:
        registry_path: registry 文件路径
        protocol_fingerprint: 协议指纹
        output_path: 输出文件路径

    Returns:
        dict: 诊断矩阵
    """
    verdicts = load_verdicts(registry_path)
    matrix = build_verdict_matrix(verdicts, protocol_fingerprint)

    # 保存到文件
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, ensure_ascii=False)

    return matrix


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成协变量族诊断矩阵")
    parser.add_argument("--registry", required=True, help="registry 文件路径")
    parser.add_argument("--protocol-fingerprint", required=True, help="协议指纹")
    parser.add_argument(
        "--output",
        default="task_FM/config/covariate_family_verdict.json",
        help="输出文件路径"
    )
    args = parser.parse_args()

    matrix = generate_verdict_matrix(
        args.registry,
        args.protocol_fingerprint,
        args.output
    )

    print(f"Generated {args.output}")
    print(f"  n_evaluated: {matrix['n_evaluated']}")
    print(f"  matrix keys: {list(matrix['matrix'].keys())}")
    print(f"  incomputable: {list(matrix['incomputable_symbols'].keys())}")
