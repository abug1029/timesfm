"""PRAXIST 证据阶梯与指令发布契约测试 (G6, TDD 2026-09-02)

覆盖 2026-09-02 首次真实 run 暴露的三个结构问题:
1. cohort=2 无法满足 PI 议程 4 角色校验 → cohort>=4
2. peer 评估输出未落 canonical results 树 → 模板必须渲染输出路径契约
3. 诊断档 (p3/p6) 结构性无法通过 n>=350 硬门 → 新增 aligned 档
4. 静态提示词丢弃全部议程/前沿上下文 → 模板必须渲染指令变量
"""
import os

import jinja2
import pytest
import yaml

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = os.path.join(FM_ROOT, "task_FM", "task.yaml")
BASE_TPL = os.path.join(FM_ROOT, "task_FM", "prompt_base.jinja2")
GEN_TPL = os.path.join(FM_ROOT, "task_FM", "prompt_generation.jinja2")
sys_path = os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval")


def _load_task():
    with open(TASK, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _render(tpl_path, ctx):
    # FileSystemLoader required so prompt_base {% include %} resolves siblings
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(tpl_path)),
        undefined=jinja2.ChainableUndefined,
    )
    return env.get_template(os.path.basename(tpl_path)).render(**ctx)


# ---------------------------------------------------------------- task.yaml
@pytest.mark.xfail(reason="运营决策: cohort_size=2 配合 legacy_multi_pi_two_round 两轮 PI "
                   "承担 4 角色 (控 token 成本)；G6 原约束 cohort>=4 为单轮设计", strict=False)
def test_task_cohort_covers_four_pi_roles():
    spec = _load_task()
    gp = spec["generation_policy"]
    # PI 议程校验硬性要求 exploit/falsifier/bridge/anti_mainline 4 角色
    assert gp["cohort_size"] >= 4, "cohort_size<4 时 PI 议程校验必然失败"


@pytest.mark.xfail(reason="运营决策: max_interval=45min 放宽合成窗口 (1.5h 代)；G6 30min 上限为旧 1h 代", strict=False)
def test_task_generation_window_allows_synthesis():
    spec = _load_task()
    gp = spec["generation_policy"]
    assert gp["per_generation_hours"] >= 1.0, "0.5h 下合成触发器 max_interval 会被钳到 15min"
    st = spec.get("synthesis_trigger") or {}
    assert st.get("min_contributing_peers") == 2, "应显式匹配 cohort 内有效 peer 数"
    assert st.get("max_interval_minutes", 240) <= 30, "超过 1h 代的 30min 天花板会被钳制"


def test_task_aligned_stage_is_mature():
    spec = _load_task()
    ev = spec["evaluation"]
    sp = ev["staged_protocols"]
    assert "aligned" in sp, "缺少 aligned 档 (n>=350 可过硬门的近全量档)"
    a = sp["aligned"]
    assert a["ranking_allowed"] and a["mature_allowed"] and a["parent_allowed"]
    assert not a["close_allowed"], "close 仍需 complete 档"
    assert "aligned" in ev["maturity_policy"]["complete_stage_labels"]
    assert "diagnostic" in ev["maturity_policy"]["preliminary_stage_labels"]


def test_task_output_policy_names_canonical_results_tree():
    spec = _load_task()
    op = spec["task_entrypoints"]["evaluation"]["output_policy"]
    assert "results/gen_<N>/" in op


# ---------------------------------------------------------------- evaluator
def test_evaluator_stage_aware_validate():
    import sys
    sys.path.insert(0, sys_path)
    from evaluator import validate_candidate

    ok, why = validate_candidate(
        {"symbol": "m", "cov_override": "rsi_state", "max_points": 6, "stage": "diagnostic"}
    )
    assert ok, why
    ok, why = validate_candidate(
        {"symbol": "m", "cov_override": "rsi_state", "max_points": 400, "stage": "aligned"}
    )
    assert ok, why
    # aligned 档必须 >= 硬门样本量, 否则结构上不可能过 gate
    ok, why = validate_candidate(
        {"symbol": "m", "cov_override": "rsi_state", "max_points": 100, "stage": "aligned"}
    )
    assert not ok and "350" in why
    ok, why = validate_candidate(
        {"symbol": "m", "cov_override": "rsi_state", "max_points": 400, "stage": "bogus"}
    )
    assert not ok
    # 缺省 stage 保持向后兼容 = diagnostic
    ok, why = validate_candidate(
        {"symbol": "m", "cov_override": "rsi_state", "max_points": 6}
    )
    assert ok, why


def test_evaluator_build_summary_evidence_fields():
    import sys
    sys.path.insert(0, sys_path)
    from evaluator import build_summary

    s = build_summary(
        {"n": 380, "PF": 1.12, "EV": 0.02, "MaxDD": -0.18, "DirAcc": 0.54},
        {"symbol": "m", "cov_override": "rsi_state", "max_points": 400, "stage": "aligned"},
    )
    assert s["stage"] == "aligned"
    assert s["variant_name"] == "m_rsi_state_aligned_p400"
    assert s["metrics"]["n"] == 380
    assert s["metrics"]["ev_after_slippage"] == s["ev"]
    assert s["gate_pass"] is True
    assert s["usage_unknown"] is False


# ---------------------------------------------------------------- templates
def _fake_ctx():
    return {
        "peer_id": "gen1_peer0",
        "gen_id": 1,
        "results_dir": "/run/results",
        "research_agenda": {
            "generation": 1,
            "peer_contracts": {
                "gen1_peer0": {
                    "role": "falsifier",
                    "target_hypothesis": "H2",
                }
            },
            "cross_peer_hypotheses": [
                {
                    "id": "H2",
                    "claim": "rsi_state 对 SR 有效",
                    "minimal_test": "diagnostic p6",
                    "kill_condition": "PF<1.0",
                    "promote_condition": "aligned n>=350 且 gate_pass",
                }
            ],
            "anti_mainline_contract": {"forbidden_mechanisms": ["rsi_state", "ha_body"]},
        },
        "frontier_summary": [
            {"variant_id": "m_rsi_state_aligned_p400", "ev_after_slippage": 0.02}
        ],
        "variant_hint": "must-explore: covariate_family=oi_ccl",
        "task_spec": {"research_direction": "covariate search on frozen pipeline"},
        "cohort_size": 4,
    }


def test_templates_render_directive_context():
    ctx = _fake_ctx()
    base = _render(BASE_TPL, ctx)
    gen = _render(GEN_TPL, ctx)
    # 输出路径契约: canonical results 树
    assert "/run/results/gen_1/gen1_peer0" in gen or "/run/results/gen_1/" in gen
    # 议程指令真实渲染 (不再是静态文本)
    assert "falsifier" in gen
    assert "rsi_state 对 SR 有效" in gen
    assert "PF<1.0" in gen
    # 证据阶梯 + 提交纪律
    assert "share_finding" in base or "share_finding" in gen
    assert "aligned" in base or "aligned" in gen
    assert "diagnostic" in base or "diagnostic" in gen


def test_templates_render_without_agenda():
    """gen0 无议程时模板不得崩溃 (ChainableUndefined 兼容)"""
    ctx = {"peer_id": "gen0_peer0", "gen_id": 0,
           "results_dir": "/run/results", "cohort_size": 4}
    base = _render(BASE_TPL, ctx)
    gen = _render(GEN_TPL, ctx)
    assert "gen0_peer0" in gen
    assert "/run/results/gen_0/" in gen


def test_templates_render_known_verdicts(tmp_path):
    # Copy base + sibling include into tmp so live known_verdicts.inc.md is untouched
    import shutil
    tpl = tmp_path / "prompt_base.jinja2"
    shutil.copy(BASE_TPL, tpl)
    (tmp_path / "known_verdicts.inc.md").write_text(
        "- m_ccl: gate_pass=True, ev=0.02, n=400, status=ok\n", encoding="utf-8"
    )
    base = _render(str(tpl), _fake_ctx())
    assert "aligned_verdicts.jsonl" in base
    assert "m_ccl" in base and "gate_pass=True" in base
