"""快环提示词的品种与族权威（spec 2026-11-18-proposal-quality-design.md）。

覆盖 prompt_base.jinja2 的四条规则：品种只指向目标文件、示例族为 inventory、
两份以上提案才要求跨族、不再另写方向准确率门槛。同时覆盖配对条件和两个品种这句。
同时覆盖会进入同一次渲染的 skill.md 与 prompt_generation.jinja2。
只读这三个文本。不断言运行中的监督环，也不读裁决文件。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "task_FM", "prompt_base.jinja2")
SKILL = os.path.join(ROOT, "task_FM", "roles", "peer_generalist", "skill.md")
GEN = os.path.join(ROOT, "task_FM", "prompt_generation.jinja2")
SHORT = "{m, ss, sr, cj, jd, lh, eg, rb}"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_prompt_base_symbol_family_and_gate():
    text = _read(BASE)
    for banned in (
        SHORT,
        "2-star",
        '"covariate_family": "positioning"',
        "macro_sentiment",
        "n>=350",
        "n_eff>=50",
        "DirAcc>=0.52",
    ):
        assert banned not in text, banned
    for required in (
        "/home/abug/timesfm/scripts/praxist_goal.yaml",
        "target_symbols",
        '"covariate_family": "inventory"',
        "When you write two or more proposals",
        "Do not invent a family the menu does not list",
        "the slow loop's existing aligned gate",
    ):
        assert required in text, required
    assert "cohort_size | default(4)" in text
    assert "n=350-600" in text
    assert "covariate_menu.inc.md" in text
    assert "known_verdicts.inc.md" in text
    assert "p_oi.json" in text
    assert "failure_delta" in text
    assert "ACTIVE 品种优先" in text
    assert "缺 `success_delta` 的复跑会被拒收 (`no_success_delta`)。" in text
    assert "低于该品种 adaptive effective_min" in text
    assert "positioning/calendar/structure" in text
    RULE8 = (
        "8. **failure_delta**：若该 symbol 与该 cov 的组合已有可确认失败"
        "（`gate_pass` 为假，且 `dm_status` 为 `ok` 或 `set_mismatch_ok`），"
        "必须填写 ≥20 字，并且原文包含该组合至少一条失败裁决的 `variant_id`。"
        "只提到品种或只提到协变量不算。没有点名会被拒收 (`no_failure_delta`)。"
    )
    EXAMPLE = (
        '  "failure_delta": "仅当本 symbol 与本 cov 的组合已有可确认失败时必填：'
        '原文包含该失败裁决的 variant_id，并写清这次机制差在哪（≥20字）",'
    )
    DIVERSITY = (
        "When you write two or more proposals in this generation, at least one must "
        "use an ACTIVE covariate family from the menu below that differs from the "
        "family of your other proposal. A single proposal is valid when its covariate "
        "is an ACTIVE row in that menu. Do not invent a family the menu does not list."
    )
    TWO_SYMBOLS = (
        "When you write two or more proposals in this generation, use at least two symbols. "
        "For a symbol and covariate that already has a confirmable failure, write at most "
        "one more proposal in this generation, and only with a failure_delta that contains "
        "that failure's variant_id."
    )
    assert RULE8 in text
    assert EXAMPLE in text
    assert DIVERSITY in text
    assert TWO_SYMBOLS in text
    assert "本 symbol 或本 cov" not in text
    between = text[text.index(DIVERSITY) + len(DIVERSITY):text.index(TWO_SYMBOLS)]
    assert between.strip() == ""


def test_skill_scope_uses_goal_file_and_english_kill():
    text = _read(SKILL)
    for banned in (
        SHORT,
        "2-star",
        "dir_acc<0.52",
        "低于该品种",
        "failure_delta",
        "symbol or cov",
        "本 symbol 或",
        "use at least two symbols",
    ):
        assert banned not in text, banned
    for required in (
        "/home/abug/timesfm/scripts/praxist_goal.yaml",
        "target_symbols",
        "below that symbol's adaptive effective_min",
    ):
        assert required in text, required
    assert "positioning/calendar/structure" in text
    assert '"covariate_family": "volatility"' in text


def test_generation_anti_mainline_does_not_name_macro_sentiment():
    text = _read(GEN)
    assert "macro_sentiment" not in text
    assert "Do not invent a family the menu does not list" in text
    assert "adaptive gate (0.50-0.52)" in text
    assert "ACTIVE covariate from the pool menu" in text
    assert "use at least two symbols" not in text
