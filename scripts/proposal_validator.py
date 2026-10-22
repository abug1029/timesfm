#!/usr/bin/env python3
"""提案结构验证器：写盘前 / 收割前门禁。

验证项:
  1. JSON 格式有效性
  2. 必填字段 (symbol, cov_override, mechanism, symbol_fit, predicted_direction)
  3. 关键字段类型 (必须为 str)
  4. 中英门禁 (mechanism / symbol_fit 禁止中文字符)
  5. Laya 禁用词检测 (P0 红线)
  6. stem / variant_id 口径一致性

Usage:
    from proposal_validator import validate_proposal, validate_proposal_dict
    result = validate_proposal("/path/to/proposal.json")
    result = validate_proposal_dict(proposal_data)
"""
import json
import os
import re
from typing import Any, Dict, List

# 东亚宽字符正则（与 SPEC 验收字符类一致）
_EAST_ASIAN_WIDE = re.compile(
    r"[一-鿿"
    r"　-〿"
    r"！-／：-＠［-｀｛-･]"
)

REQUIRED_FIELDS = [
    "symbol",
    "cov_override",
    "mechanism",
    "symbol_fit",
    "predicted_direction",
]

TYPE_CHECKS = {
    "symbol": str,
    "cov_override": str,
    "mechanism": str,
    "symbol_fit": str,
    "predicted_direction": str,
}

CHINESE_GATED_FIELDS = ["mechanism", "symbol_fit"]

# R5: Laya prohibited words (P0 red line: Laya only judges, cannot learn/train/evolve)
LAYA_PROHIBITED_PATTERNS = [
    (re.compile(r"(?:训练|进化|微调|优化)\s*[Ll]aya"), "laya_training"),
    (re.compile(r"[Ll]aya[^\n]{0,15}(?<!不)可学习"), "laya_learnable"),
    (re.compile(r"(?<!不)可学习[^\n]{0,15}[Ll]aya"), "learnable_laya"),
]


def contains_chinese(text: str) -> bool:
    """检测字符串是否包含中文字符（东亚宽字符）。"""
    return bool(_EAST_ASIAN_WIDE.search(text))


def _scan_strings(data, path=""):
    """Recursively collect all (field_path, string_value) pairs."""
    results = []
    if isinstance(data, str):
        results.append((path, data))
    elif isinstance(data, dict):
        for k, v in data.items():
            results.extend(_scan_strings(v, f"{path}.{k}" if path else k))
    elif isinstance(data, (list, tuple)):
        for i, v in enumerate(data):
            results.extend(_scan_strings(v, f"{path}[{i}]"))
    return results


def validate_proposal_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证提案 dict，返回 {valid, errors, warnings}。"""
    errors: List[str] = []
    warnings: List[str] = []

    # 1. 必填字段
    for field in REQUIRED_FIELDS:
        if field not in data or data[field] is None:
            errors.append("missing_required:" + field)

    # 2. 类型验证
    for field, expected_type in TYPE_CHECKS.items():
        if field in data and data[field] is not None:
            if not isinstance(data[field], expected_type):
                errors.append(
                    "type_error:%s:expected_%s:got_%s"
                    % (field, expected_type.__name__, type(data[field]).__name__)
                )

    # 3. 中英门禁
    for field in CHINESE_GATED_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and contains_chinese(value):
            errors.append("chinese_field:" + field)

    # 4. R5: Laya prohibited words (full-text scan with regex)
    for field_path, text in _scan_strings(data):
        for pattern, label in LAYA_PROHIBITED_PATTERNS:
            if pattern.search(text):
                errors.append(f"laya_prohibited_word:{label}:in_field:{field_path}")

    # 5. R6: stem / variant_id consistency
    symbol = data.get("symbol")
    cov_override = data.get("cov_override")
    variant_id = data.get("variant_id")
    if (isinstance(symbol, str) and isinstance(cov_override, str)
            and isinstance(variant_id, str)):
        expected_stem = f"{symbol}_{cov_override}"
        if not variant_id.startswith(expected_stem):
            errors.append(
                f"variant_id_mismatch:expected_{expected_stem}:got_{variant_id}"
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_proposal(proposal_path: str) -> Dict[str, Any]:
    """验证提案 JSON 文件，返回 {valid, errors, warnings}。"""
    try:
        with open(proposal_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "errors": ["unparseable_json:" + str(e)],
            "warnings": [],
        }
    except OSError as e:
        return {
            "valid": False,
            "errors": ["io_error:" + str(e)],
            "warnings": [],
        }

    return validate_proposal_dict(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python proposal_validator.py <proposal_path>", file=sys.stderr)
        sys.exit(1)
    result = validate_proposal(sys.argv[1])
    if result["valid"]:
        print("PASS")
        sys.exit(0)
    else:
        print("FAIL: %s" % result["errors"])
        sys.exit(1)
