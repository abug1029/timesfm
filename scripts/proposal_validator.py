#!/usr/bin/env python3
"""提案结构验证器：写盘前 / 收割前门禁。

验证项:
  1. JSON 格式有效性
  2. 必填字段 (symbol, cov_override, mechanism, symbol_fit, predicted_direction)
  3. 关键字段类型 (必须为 str)
  4. 中英门禁 (mechanism / symbol_fit 禁止中文字符)

Usage:
    from proposal_validator import validate_proposal, validate_proposal_dict
    result = validate_proposal("/path/to/proposal.json")
    result = validate_proposal_dict(proposal_data)
"""
import json
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


def contains_chinese(text: str) -> bool:
    """检测字符串是否包含中文字符（东亚宽字符）。"""
    return bool(_EAST_ASIAN_WIDE.search(text))


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
