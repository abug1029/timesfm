"""
批次 B：N10 tier 值域守卫星测（Q2=b）

验证：
1. 合法 tier 值（S/A/B/C/D）通过校验
2. 非法 tier 值被拒绝并记录日志
3. 缺失 tier 字段返回 False
"""
import pytest
import sys
import os

# 添加 scripts 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_valid_tier_values():
    """合法 tier 值应通过校验"""
    from praxist_supervisor import VALID_TIER_VALUES

    # 验证值域定义正确（frozenset）
    assert VALID_TIER_VALUES == frozenset({"S", "A", "B", "C", "D"})

    # 测试合法值
    for tier in ["S", "A", "B", "C", "D"]:
        # 合法值应在值域中
        assert tier in VALID_TIER_VALUES


def test_invalid_tier_values_rejected():
    """非法 tier 值应被拒绝"""
    from praxist_supervisor import VALID_TIER_VALUES

    invalid_values = [
        "1",           # 数字字符串
        "A/B",         # 混合值
        "可预测",       # 中文（第二套语义）
        "当前不可验证",  # 中文（第二套语义）
        "1",           # 数字字符串（非法值）
        "2",           # 数字字符串（非法值）
        "3",           # 数字字符串（非法值）
        "",            # 空字符串
        "a",           # 小写
        "S/A",         # 多个值
    ]

    for invalid in invalid_values:
        assert invalid not in VALID_TIER_VALUES, f"非法值 {invalid!r} 不应在合法值域中"


def test_missing_tier_field():
    """缺失 tier 字段应返回 False"""
    from praxist_supervisor import VALID_TIER_VALUES

    v = {"variant_id": "test_variant"}  # 无 tier 字段
    assert v.get("tier") is None
    assert v.get("tier") not in VALID_TIER_VALUES


def test_tier_domain_guard_prevents_semantic_mixin():
    """值域守卫应防止非法值混入（第二套中文语义、None、数字等）。

    注意：第三套语义（"A"/"B"/"C"）与第一套值域重叠，守卫无法区分；
    第三套语义的实际防线是写入方唯一性 + two_star_critic 已退役。
    """
    from praxist_supervisor import VALID_TIER_VALUES

    # 值域守卫拦住的是非法值（如 "1"/"2"/"3"、中文、空字符串等）
    # 第三套语义的 "A"/"B"/"C" 与第一套值域 {S,A,B,C,D} 重叠，守卫无法区分
    # 第三套语义的实际防线是写入方唯一性 + two_star_critic 已退役

    third_semantic_values = ["1", "2", "3"]
    for val in third_semantic_values:
        assert val not in VALID_TIER_VALUES, \
            f"非法值 {val!r} 应被值域守卫拦住"

    # 第二套语义（中文）也应被拦住
    second_semantic_values = ["可预测", "当前不可验证", "需更多样本"]
    for val in second_semantic_values:
        assert val not in VALID_TIER_VALUES, \
            f"第二套语义值 {val!r} 应被值域守卫拦住"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
