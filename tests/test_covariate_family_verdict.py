"""协变量族诊断矩阵测试 — PR-C5 实施验收"""

import pytest
import json
from pathlib import Path
from scripts.generate_covariate_family_verdict import build_verdict_matrix


def test_verdict_matrix_structure():
    """测试诊断矩阵结构正确"""
    # 构造模拟数据
    mock_verdicts = [
        {
            "symbol": "ss",
            "covariate_type": "rsi_state",
            "protocol_fingerprint": "fp1",
            "covariates_used": True,
            "inert_constant": False,
            "all_zero": False,
            "variant_id": "v1"
        },
        {
            "symbol": "sr",
            "covariate_type": "rsi_state",
            "protocol_fingerprint": "fp1",
            "covariates_used": True,
            "inert_constant": True,
            "all_zero": False,
            "variant_id": "v2"
        },
    ]

    result = build_verdict_matrix(mock_verdicts, protocol_fingerprint="fp1")

    # 检查 schema
    assert result["schema"] == "fm.covariate_family_verdict.v1"

    # 检查必要字段
    assert "n_evaluated" in result
    assert "matrix" in result
    assert "incomputable_symbols" in result
    assert "diagnostic_thresholds" in result

    # 检查 n_evaluated 是整数
    for cov, n in result["n_evaluated"].items():
        assert isinstance(n, int)
        assert n >= 0


def test_n_evaluated_denominator():
    """spec §4.4 W4①: n_evaluated 分母只计「protocol_fingerprint 一致
    且 covariates_used == True」的品种数。

    审计 D8 修正: 原为空函数体（...），无任何断言。
    """
    mock_verdicts = [
        {"symbol": "ss", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "inert_constant": False, "all_zero": False, "variant_id": "v1"},
        {"symbol": "sr", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "inert_constant": True, "all_zero": False, "variant_id": "v2"},
        {"symbol": "m", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp2", "covariates_used": True,   # 协议不一致
         "variant_id": "v3"},
        {"symbol": "jd", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp1", "covariates_used": False,  # 非协变量运行
         "variant_id": "v4"},
    ]

    result = build_verdict_matrix(mock_verdicts, protocol_fingerprint="fp1")

    # 只有 ss 与 sr 计入（m 协议不符；jd 未用协变量）
    assert result["n_evaluated"]["rsi_state"] == 2, (
        "分母必须排除协议不一致与非协变量运行的裁决"
    )
    # 必须显式给出分母，不得只给百分比
    assert isinstance(result["n_evaluated"]["rsi_state"], int)


def test_incomputable_symbols_listed():
    """spec §4.4 W4①: 无法计算的品种必须**单列**清单，且不计入分母。

    审计 D8 修正: 原为空函数体（...），无任何断言。
    """
    mock_verdicts = [
        {"symbol": "ss", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "variant_id": "v1"},
    ]
    all_symbols = {"ss", "sr", "m", "jd", "lh", "cj", "fu", "rb"}

    result = build_verdict_matrix(
        mock_verdicts,
        protocol_fingerprint="fp1",
        all_symbols=all_symbols
    )

    incomputable = set(result["incomputable_symbols"].keys())
    assert incomputable == all_symbols - {"ss"}, "未评估品种必须单列"
    # 不可计算品种不得混入分母
    assert result["n_evaluated"]["rsi_state"] == 1


def test_diagnostic_thresholds_not_auto_archive():
    """spec §4.4 W4②③: 阈值只作诊断提示，**禁止**自动归档。

    审计 D8 修正: 原为空函数体（...），无任何断言。
    即使 n_evaluated >= 8、板块覆盖 >= 2、惰性占比 >= 60%，也不得自动归档。
    """
    # 构造一个「全部阈值都满足」的极端情形
    mock_verdicts = [
        {"symbol": sym, "covariate_type": "dead_cov",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "inert_constant": True, "all_zero": False, "variant_id": f"v_{sym}"}
        for sym in ["ss", "sr", "m", "jd", "lh", "cj", "fu", "rb"]
    ]

    result = build_verdict_matrix(mock_verdicts, protocol_fingerprint="fp1")

    # 阈值被计算并展示
    assert result["n_evaluated"]["dead_cov"] == 8
    inert_ratio = sum(
        1 for v in result["matrix"]["dead_cov"].values()
        if v["inert_constant"]
    ) / result["n_evaluated"]["dead_cov"]
    assert inert_ratio >= 0.6

    # 但**不得**产生任何归档动作
    assert "archived" not in result, "诊断矩阵不得自动归档"
    assert result["diagnostic_thresholds"]["note"].find("不自动归档") >= 0, (
        "阈值必须显式标注「仅诊断提示，不自动归档」"
    )
    # 归档决定权在人：矩阵只提供证据指针
    assert "evidence" in next(iter(result["matrix"]["dead_cov"].values()))


def test_matrix_entry_fields():
    """测试矩阵条目字段完整性"""
    mock_verdicts = [
        {
            "symbol": "ss",
            "covariate_type": "rsi_state",
            "protocol_fingerprint": "fp1",
            "covariates_used": True,
            "inert_constant": False,
            "all_zero": True,
            "ablation_content_delta": 0.05,
            "variant_id": "v1"
        },
    ]

    result = build_verdict_matrix(mock_verdicts, protocol_fingerprint="fp1")

    entry = result["matrix"]["rsi_state"]["ss"]
    assert "inert_constant" in entry
    assert "all_zero" in entry
    assert "ablation_content_delta" in entry
    assert "evidence" in entry

    assert entry["inert_constant"] is False
    assert entry["all_zero"] is True
    assert entry["ablation_content_delta"] == 0.05
    assert entry["evidence"] == "verdict_v1"


def test_empty_verdicts():
    """测试空裁决列表"""
    result = build_verdict_matrix([], protocol_fingerprint="fp1")

    assert result["n_evaluated"] == {}
    assert result["matrix"] == {}
    assert len(result["incomputable_symbols"]) == 8  # 全部 8 品种都不可计算


def test_mixed_covariate_types():
    """测试混合协变量类型"""
    mock_verdicts = [
        {"symbol": "ss", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "variant_id": "v1"},
        {"symbol": "sr", "covariate_type": "calendar_cyclical",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "variant_id": "v2"},
        {"symbol": "m", "covariate_type": "rsi_state",
         "protocol_fingerprint": "fp1", "covariates_used": True,
         "variant_id": "v3"},
    ]

    result = build_verdict_matrix(mock_verdicts, protocol_fingerprint="fp1")

    assert result["n_evaluated"]["rsi_state"] == 2  # ss + m
    assert result["n_evaluated"]["calendar_cyclical"] == 1  # sr
    assert "ss" in result["matrix"]["rsi_state"]
    assert "m" in result["matrix"]["rsi_state"]
    assert "sr" in result["matrix"]["calendar_cyclical"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
