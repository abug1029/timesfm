"""技术债收口 2026-10-08：L2 / L3 / L4 防回归

- L2 `_has_prior_failure` 单键 OR → (symbol, cov) 配对 AND
- L3 目标品种集单源化到 praxist_goal.yaml（删除两份硬编码 + 缺键 fail loud）
- L4 cadence 默认值与 yaml 对齐（survivors_per_cycle / aligned_max_points）

计划：docs/superpowers/plans/2026-10-07-tech-debt-closure-plan.md（批次 2）
"""
import os
import re
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as sup  # noqa: E402

LIVE_GOAL = os.path.join(ROOT, "scripts", "praxist_goal.yaml")
SUP_SRC = os.path.join(ROOT, "scripts", "praxist_supervisor.py")


def _write_goal(tmp_path, name, cadence_extra):
    """写一份最小 goal yaml，cadence 里塞入调用方给的内容。"""
    p = tmp_path / name
    p.write_text(
        "goal:\n"
        "  success_condition: ['all_symbols_pass_phase1']\n"
        "  cadence: {%s}\n" % cadence_extra,
        encoding="utf-8")
    return p


# ── L3：目标品种集单源化 ────────────────────────────────────────────

def test_goal_symbols_set_matches_yaml_not_a_stale_subset():
    """L3：GOAL_SYMBOLS_SET 必须等于 yaml 的 target_symbols，不是 9 个陈旧子集。

    修复前代码硬编码 9 个"1★ 信用品种"，yaml 是 24 个 —— 同一语义两份真相，
    goal 完成度统计与 peer "## Symbol status" 段都只按 9 个算，语义分裂。
    """
    with open(LIVE_GOAL, encoding="utf-8") as f:
        live = yaml.safe_load(f)["goal"]
    expected = set(sup._goal_target_symbols(live))
    assert expected, "yaml 必须声明目标品种"
    assert set(sup.GOAL_SYMBOLS_SET) == expected
    # 旧 9 个硬编码（自称"1★ 信用品种"）漏掉的品种必须真的在集合里。
    # 不硬编码具体清单 —— 从 yaml 派生，避免品种增删时本测试自身腐烂。
    stale_nine = {"m", "ss", "sr", "cj", "jd", "lh", "eg", "rb", "fu"}
    assert stale_nine < expected, (
        "yaml 目标品种不应少于旧硬编码的 9 个：缺 %s"
        % sorted(stale_nine - expected))
    assert expected - stale_nine, "yaml 应含旧硬编码之外的新增品种（否则本测试无意义）"


def test_goal_symbols_follow_yaml_edits(tmp_path):
    """L3：宿主在 yaml 里增删品种，集合必须跟随（证明真的没有第二份副本）。"""
    p = _write_goal(tmp_path, "goal.yaml", "target_symbols: [m, ss, xx]")
    assert set(sup._load_goal_symbols(str(p))) == {"m", "ss", "xx"}

    p2 = _write_goal(tmp_path, "goal2.yaml", "target_symbols: [m, ss, yy, zz]")
    assert set(sup._load_goal_symbols(str(p2))) == {"m", "ss", "yy", "zz"}


def test_goal_symbols_normalizes_case_and_duplicates(tmp_path):
    p = _write_goal(tmp_path, "goal.yaml", "target_symbols: ['M', ' m ', 'ss', 'ss']")
    assert sup._goal_target_symbols(sup.load_goal(str(p))) == ["m", "ss"]


def test_missing_target_symbols_fails_loud(tmp_path):
    """L3：契约缺失必须抛错，禁止静默回退硬编码（回退正是分裂能长期存活的成因）。"""
    for name, cadence in (
        ("a.yaml", "survivors_per_cycle: 3"),
        ("b.yaml", "target_symbols: []"),
    ):
        p = _write_goal(tmp_path, name, cadence)
        with pytest.raises(ValueError, match="target_symbols"):
            sup._load_goal_symbols(str(p))


def test_assert_goal_symbols_contract_fails_loud():
    """L3：main() 启动校验走 _assert_goal_symbols_contract，缺键必须抛错。"""
    for bad in ({"cadence": {}}, {"cadence": {"target_symbols": []}}, {}):
        with pytest.raises(ValueError, match="目标品种集契约缺失"):
            sup._assert_goal_symbols_contract(bad)
    # 合法 goal 原样返回，且已归一化
    got = sup._assert_goal_symbols_contract(
        {"cadence": {"target_symbols": ["M", "m", "ss"]}})
    assert got == ["m", "ss"]


def test_no_hardcoded_symbol_sets_remain():
    """L3：代码里不得再内联品种集合字面量（GOAL_SYMBOLS_SET / TARGET_SYMBOLS）。"""
    with open(SUP_SRC, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r'GOAL_SYMBOLS_SET\s*=\s*frozenset\(\s*\{', src), \
        "GOAL_SYMBOLS_SET 又被写死成字面量了"
    assert not re.search(r'TARGET_SYMBOLS\s*=\s*\{', src), \
        "TARGET_SYMBOLS 又被写死成字面量了"
    # 旧 9 个信用品种那一份
    assert 'frozenset({"m", "ss", "sr", "cj"' not in src


# ── L4：cadence 默认值与 yaml 对齐 ──────────────────────────────────

def test_cadence_defaults_match_goal_yaml():
    """L4：代码默认值必须与 praxist_goal.yaml 一致（防再漂移）。

    修复前：survivors_per_cycle 默认 2（yaml=3）、aligned_max_points 在收割处
    默认 400 而另两处是 600（yaml=600）—— 同一文件三处互相矛盾。
    """
    with open(LIVE_GOAL, encoding="utf-8") as f:
        cad = yaml.safe_load(f)["goal"]["cadence"]
    assert sup._CADENCE_DEFAULTS["survivors_per_cycle"] == cad["survivors_per_cycle"]
    assert sup._CADENCE_DEFAULTS["aligned_max_points"] == cad["aligned_max_points"]


def test_cad_int_reads_yaml_and_falls_back_with_warning(capsys):
    """L4：显式值优先；缺键回退默认值且必须留 WARN（静默回退是漂移的成因）。"""
    assert sup._cad_int({"survivors_per_cycle": 7}, "survivors_per_cycle") == 7
    assert capsys.readouterr().err == ""

    for key in ("survivors_per_cycle", "aligned_max_points"):
        assert sup._cad_int({}, key) == sup._CADENCE_DEFAULTS[key]
        assert key in capsys.readouterr().err


def test_no_hardcoded_cadence_fallbacks_remain():
    """L4：收割路径不得再有裸 cad.get(key, <数字>) 默认值。"""
    with open(SUP_SRC, encoding="utf-8") as f:
        src = f.read()
    leftovers = re.findall(
        r'cad\.get\("(survivors_per_cycle|aligned_max_points)"\s*,', src)
    assert not leftovers, "cadence 默认值仍散落：%r" % (leftovers,)


# ── L2：配对键 ──────────────────────────────────────────────────────

def _fail_row(vid, symbol, cov, **over):
    row = {"variant_id": vid, "symbol": symbol, "cov_override": cov,
           "status": "ok", "gate_pass": False,
           "dm_status": "set_mismatch_ok"}
    row.update(over)
    return row


def test_has_prior_failure_pairs_symbol_and_cov():
    """L2：只有 (symbol, cov) 同对的确认失败才否决提案。"""
    snap = {"a": _fail_row("a", "m", "vor")}

    # 同对 → 拦
    assert sup._has_prior_failure(snap, "m", "vor") is True
    # 同 symbol 异 cov → 放行（修复前误拦）
    assert sup._has_prior_failure(snap, "m", "oi") is False
    # 异 symbol 同 cov → 放行（修复前误拦）
    assert sup._has_prior_failure(snap, "rb", "vor") is False
    # symbol 大小写归一
    assert sup._has_prior_failure(snap, "M", "vor") is True


def test_has_prior_failure_pairing_ignores_non_failures():
    """L2：配对命中但行不是"可确认失败"时不得拦（过门行 / 描述性行 / 无共同 cutoff）。"""
    passing = {"a": _fail_row("a", "m", "vor", gate_pass=True)}
    assert sup._has_prior_failure(passing, "m", "vor") is False

    descriptive = {"a": _fail_row("a", "m", "vor",
                                  dm_status="set_mismatch_descriptive")}
    assert sup._has_prior_failure(descriptive, "m", "vor") is False

    no_cutoff = {"a": _fail_row("a", "m", "vor", dm_status="no_common_cutoff")}
    assert sup._has_prior_failure(no_cutoff, "m", "vor") is False

    # 同对另有可确认失败行时仍应拦（配对不等于"只认唯一一行"）
    mixed = {"a": descriptive["a"], "b": _fail_row("b", "m", "vor")}
    assert sup._has_prior_failure(mixed, "m", "vor") is True


def test_has_prior_failure_empty_snapshot():
    assert sup._has_prior_failure({}, "m", "vor") is False
    assert sup._has_prior_failure(None, "m", "vor") is False
    assert sup._has_prior_failure({"bad": "not-a-dict"}, "m", "vor") is False