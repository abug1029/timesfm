"""cascade/tier_classifier.py -- 协变量等级分类器

根据 aligned verdict 的多维指标计算综合评分, 将二元过门升级为 S/A/B/C/D
五级评价体系. 满分 105 分.

评分维度:
  - dir_acc  (0-40): 方向准确率
  - decay    (0-30): 远端衰减比
  - mape     (0-20): 端点 MAPE
  - n_eff    (0-10): 有效样本量
  - prescreen(0-5):  TypeSafe 预筛 plausibility

口径（D2，2026-10-08）: verdict 上的评级**唯一承载字段是 tier**（本模块产出）。
历史文档里的 star 字段在裁决 schema 中自始不存在，不要再据它写代码或口径。
另注: 品种信用星（scheme.stars / list_by_stars）已于 2026-10-08 退役 ——
它与本模块无关，且从来不是同一套东西。
"""
from __future__ import annotations

import math
from typing import Any


def _score_dir_acc(v: float | None) -> int:
    if v is None:
        return 0
    if v >= 0.56:
        return 40
    if v >= 0.54:
        return 35
    if v >= 0.53:
        return 30
    if v >= 0.52:
        return 25
    if v >= 0.51:
        return 20
    if v >= 0.50:
        return 15
    return 5


def _score_decay(v: float | None) -> int:
    if v is None:
        return 15
    if 0.93 <= v <= 1.10:
        return 30
    if 0.90 <= v <= 1.20:
        return 25
    if 1.20 < v <= 1.45:
        return 15
    if 1.45 < v <= 1.70:
        return 10
    if 1.70 < v <= 2.00:
        return 5
    if v > 2.00:
        return 0  # 严重过预测
    # v < 0.90
    if 0.85 <= v < 0.90:
        return 15  # 轻度衰减
    if 0.75 <= v < 0.85:
        return 10  # 中度衰减
    if 0.50 <= v < 0.75:
        return 5   # 严重衰减
    return 0       # 几乎完全失效 (v < 0.50)


def _score_mape(v: float | None) -> int:
    if v is None:
        return 10
    if v <= 1.0:
        return 20
    if v <= 2.0:
        return 15
    if v <= 3.0:
        return 10
    if v <= 5.0:
        return 5
    return 0


def _score_n_eff(v: int | float | None) -> int:
    if v is None:
        return 0
    if v >= 73:
        return 10
    if v >= 70:
        return 7
    return 5


def _score_prescreen(verdict: dict[str, Any]) -> int:
    md = verdict.get("metadata") or {}
    ps = md.get("prescreen") or {}
    pl = ps.get("plausibility")
    if pl is None:
        return 0
    try:
        pl = float(pl)
    except (TypeError, ValueError):
        return 0
    if math.isnan(pl):
        return 0
    if pl >= 0.75:
        return 5
    if pl >= 0.65:
        return 3
    return 1


def _tier_from_score(score: int) -> tuple[str, str]:
    if score >= 75:
        return "S", "卓越"
    if score >= 60:
        return "A", "优秀"
    if score >= 45:
        return "B", "良好"
    if score >= 30:
        return "C", "及格"
    return "D", "边缘"


def compute_tier_score(verdict: dict[str, Any]) -> dict[str, Any]:
    """根据 verdict 字典计算 tier 评分.

    Returns:
        包含 tier / tier_score / tier_label / tier_breakdown 的字典.
    """
    breakdown = {
        "dir_acc_score": _score_dir_acc(verdict.get("dir_acc")),
        "decay_score": _score_decay(verdict.get("decay")),
        "mape_score": _score_mape(verdict.get("mape")),
        "neff_score": _score_n_eff(verdict.get("n_eff")),
        "prescreen_score": _score_prescreen(verdict),
    }
    total = sum(breakdown.values())
    tier, label = _tier_from_score(total)
    return {
        "tier": tier,
        "tier_score": total,
        "tier_label": label,
        "tier_breakdown": breakdown,
    }
