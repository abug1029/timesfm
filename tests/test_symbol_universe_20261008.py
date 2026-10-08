"""四套品种宇宙对齐（2026-10-08）

修���一条双向割裂：候选准入门（evaluator.ALLOWED_SYMBOLS）与攻坚目标
（praxist_goal.yaml goal.cadence.target_symbols）此前是两份独立硬编码，
且准入门的内容恰好等于信用档表 SCHEMES(21) 而非目标(24)。后果：

- 只在目标里的 oi/px/y 任何候选都在第一道 validate_candidate 被拒
  —— goal 要求它们达标，却无法为它们产生任何候选；
- 只在准入门里的 jm 能过门但不被 goal 统计（孤儿品种）。

本次裁定：goal.yaml 为唯一来源，evaluator 从它派生；删 sc（原油不再作为
攻坚目标）、增 jm（补齐孤儿）。两套集合归一为同一 24 个品种。
"""
import os
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as sup  # noqa: E402
from task_FM.evaluations.fm_eval import evaluator as ev  # noqa: E402

LIVE_GOAL = os.path.join(ROOT, "scripts", "praxist_goal.yaml")


def _live_target_symbols():
    with open(LIVE_GOAL, encoding="utf-8") as f:
        goal = yaml.safe_load(f)["goal"]
    return set(sup._goal_target_symbols(goal))


def test_allowed_symbols_equals_target_symbols():
    """准入门与攻坚目标必须恒等 —— 双向割裂不允许存在。"""
    assert set(ev.ALLOWED_SYMBOLS) == _live_target_symbols()


def test_goal_symbols_set_also_matches():
    """supervisor 侧的 GOAL_SYMBOLS_SET 与准入门同源，三处不得再分叉。"""
    assert set(sup.GOAL_SYMBOLS_SET) == _live_target_symbols()
    assert set(sup.GOAL_SYMBOLS_SET) == set(ev.ALLOWED_SYMBOLS)


def test_sc_removed_from_both_universes():
    """sc（原油）已裁定不再作为攻坚目标。

    注意：sc 仍作为 fu/bu 裂解价差的原料输入保留在 config/crack_spread_pairs.py，
    那是数据依赖，不是研究目标 —— 不要连带删除。
    """
    assert "sc" not in _live_target_symbols()
    assert "sc" not in set(ev.ALLOWED_SYMBOLS)


def test_jm_no_longer_orphan():
    """jm（焦煤）此前只在准入门/SCHEMES、缺攻坚目标；现两处都有。"""
    assert "jm" in _live_target_symbols()
    assert "jm" in set(ev.ALLOWED_SYMBOLS)


@pytest.mark.parametrize("sym", ["oi", "px", "y", "jm"])
def test_previously_blocked_symbols_now_admissible(sym):
    """oi/px/y 此前被准入门挡死，无法为它们产出任何候选。"""
    ok, msg = ev.validate_candidate({
        "symbol": sym, "cov_override": "oi", "stage": "diagnostic", "max_points": 6})
    assert ok is True, "%s 应可准入：%s" % (sym, msg)


def test_unknown_symbol_still_rejected():
    """准入门收敛后仍必须拒不在清单内的品种（不能变成放行一切）。"""
    ok, msg = ev.validate_candidate({
        "symbol": "zzz", "cov_override": "oi", "stage": "diagnostic", "max_points": 6})
    assert ok is False
    assert "不在允许清单" in msg


def test_allowed_symbols_loader_fails_loud_without_contract(tmp_path):
    """契约缺失必须抛错，禁止回退内置副本（回退会让割裂重新出现）。"""
    p = tmp_path / "goal.yaml"
    p.write_text("goal:\n  cadence: {survivors_per_cycle: 3}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="target_symbols"):
        ev._load_allowed_symbols(str(p))


def test_allowed_symbols_source_is_goal_yaml():
    """守卫：ALLOWED_SYMBOLS 必须来自 goal.yaml，不得再内联字面量。"""
    src_path = ev.__file__
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "ALLOWED_SYMBOLS = {" not in src, \
        "ALLOWED_SYMBOLS 又被写死成字面量了（应从 goal.yaml 派生）"
    assert "ALLOWED_SYMBOLS = _load_allowed_symbols()" in src