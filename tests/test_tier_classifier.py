"""tests/test_tier_classifier.py -- tier 等级分类器测试"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from cascade.tier_classifier import compute_tier_score, _score_decay


def test_s_tier():
    """S 级: dir_acc=0.617, decay=1.43, mape=0.88, n_eff=73, 无 prescreen → score=85, tier=S"""
    verdict = {
        "dir_acc": 0.617,
        "decay": 1.43,
        "mape": 0.88,
        "n_eff": 73,
    }
    result = compute_tier_score(verdict)
    assert result["tier_score"] == 85
    assert result["tier"] == "S"
    assert result["tier_label"] == "卓越"
    assert result["tier_breakdown"]["dir_acc_score"] == 40
    assert result["tier_breakdown"]["decay_score"] == 15
    assert result["tier_breakdown"]["mape_score"] == 20
    assert result["tier_breakdown"]["neff_score"] == 10
    assert result["tier_breakdown"]["prescreen_score"] == 0


def test_a_tier():
    """A 级: dir_acc=0.529, decay=0.97, mape=4.45, n_eff=73, prescreen pl=0.65 → score=73, tier=A"""
    verdict = {
        "dir_acc": 0.529,
        "decay": 0.97,
        "mape": 4.45,
        "n_eff": 73,
        "metadata": {
            "prescreen": {
                "plausibility": 0.65,
            }
        }
    }
    result = compute_tier_score(verdict)
    assert result["tier_score"] == 73
    assert result["tier"] == "A"
    assert result["tier_label"] == "优秀"
    assert result["tier_breakdown"]["dir_acc_score"] == 25
    assert result["tier_breakdown"]["decay_score"] == 30
    assert result["tier_breakdown"]["mape_score"] == 5
    assert result["tier_breakdown"]["neff_score"] == 10
    assert result["tier_breakdown"]["prescreen_score"] == 3


def test_b_tier():
    """B 级: dir_acc=0.500, decay=1.38, mape=2.04, n_eff=73 → score=50, tier=B"""
    verdict = {
        "dir_acc": 0.500,
        "decay": 1.38,
        "mape": 2.04,
        "n_eff": 73,
    }
    result = compute_tier_score(verdict)
    assert result["tier_score"] == 50
    assert result["tier"] == "B"
    assert result["tier_label"] == "良好"


def test_none_values():
    """None 值处理: decay=None, mape=None → 不崩溃, 给默认分"""
    verdict = {
        "dir_acc": 0.52,
        "decay": None,
        "mape": None,
        "n_eff": 71,
    }
    result = compute_tier_score(verdict)
    assert result["tier"] in ["S", "A", "B", "C", "D"]
    assert result["tier_breakdown"]["decay_score"] == 15  # None → 15
    assert result["tier_breakdown"]["mape_score"] == 10   # None → 10
    assert result["tier_breakdown"]["neff_score"] == 7    # 71 ≥ 70 → 7


def test_prescreen_scoring():
    """prescreen 加分: pl=0.75→5, pl=0.67→3, 无 prescreen→0"""
    # pl=0.75 → 5
    v1 = {"metadata": {"prescreen": {"plausibility": 0.75}}}
    assert compute_tier_score(v1)["tier_breakdown"]["prescreen_score"] == 5

    # pl=0.67 → 3
    v2 = {"metadata": {"prescreen": {"plausibility": 0.67}}}
    assert compute_tier_score(v2)["tier_breakdown"]["prescreen_score"] == 3

    # 无 prescreen → 0
    v3 = {}
    assert compute_tier_score(v3)["tier_breakdown"]["prescreen_score"] == 0


def test_migrate_idempotent():
    """migrate 脚本幂等性: 已有 tier 字段的跳过"""
    from scripts.migrate_verdicts_tier import migrate_registry

    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Path(tmpdir) / "test.jsonl"
        v1 = {"dir_acc": 0.6, "decay": 1.0, "mape": 1.5, "n_eff": 73}
        v2 = {"dir_acc": 0.55, "decay": 1.2, "mape": 2.0, "n_eff": 70}

        # 第一次写入
        with open(registry, "w", encoding="utf-8") as f:
            f.write(json.dumps(v1, ensure_ascii=False) + "\n")
            f.write(json.dumps(v2, ensure_ascii=False) + "\n")

        # 第一次迁移
        migrate_registry(str(registry))
        with open(registry, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 2
        assert "tier" in lines[0]
        assert "tier" in lines[1]
        tier1_first = lines[0]["tier"]
        score1_first = lines[0]["tier_score"]

        # 第二次迁移 (幂等)
        migrate_registry(str(registry))
        with open(registry, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 2
        assert lines[0]["tier"] == tier1_first
        assert lines[0]["tier_score"] == score1_first


def test_d_tier_boundary():
    """D 级: score < 30"""
    verdict = {"dir_acc": 0.40, "decay": 1.80, "mape": 6.0, "n_eff": 50}
    result = compute_tier_score(verdict)
    assert result["tier"] == "D"
    assert result["tier_score"] < 30


def test_empty_verdict():
    """空 verdict 不崩溃"""
    result = compute_tier_score({})
    assert result["tier"] == "D"
    # dir_acc(None->0) + decay(None->15) + mape(None->10) + n_eff(None->0) + prescreen(0) = 25
    assert result["tier_score"] == 25


def test_prescreen_nan():
    """NaN plausibility 得 0 分"""
    import math
    verdict = {
        "dir_acc": 0.52, "decay": 1.0, "mape": 2.0, "n_eff": 73,
        "metadata": {"prescreen": {"plausibility": float("nan")}}
    }
    result = compute_tier_score(verdict)
    assert result["tier_breakdown"]["prescreen_score"] == 0


def test_decay_low_values():
    """decay < 0.90 分层正确"""
    assert _score_decay(0.88) == 15  # 轻度衰减
    assert _score_decay(0.80) == 10  # 中度衰减
    assert _score_decay(0.60) == 5   # 严重衰减
    assert _score_decay(0.30) == 0   # 几乎失效
    assert _score_decay(2.50) == 0   # 严重过预测
