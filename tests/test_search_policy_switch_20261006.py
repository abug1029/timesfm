"""search_policy 开关读取测试（spec 2026-10-05 §6.1 / plan 2.1 / T1 前半）。

锁定：
- goal 缺 search_policy 键 / 值为 None → off（批准前后默认，行为与今日相同）
- 合法值 off|shadow|enforce 原样通过；非法值 fail-closed 回 off 并 warning 留痕
- off 下无新字段的旧提案仍按今天的规则入队（T1 前半）
- 2.1 阶段 plumbing 惰性：shadow/enforce 形参传递不改变选座行为
  （2.2 起 enforce 的拒绝语义、2.9 起 shadow 的「本会拒绝」计数另行锁定，
  届时由专项测试取代本文件的惰性断言）
- 生产 praxist_goal.yaml 显式声明 search_policy: off（宿主改键的落点）
"""
import json
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402

LONGM = ("波动率范围(VOR)压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
         "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。")

FP_TEST = "ab" * 32


def _make_run(root, proposal, filename=None):
    symbol = str(proposal.get("symbol", "m")).lower()
    cov = proposal.get("cov_override") or "newcov"
    pdir = os.path.join(root, "task_FM", "experiments", "run_T",
                        "results", "gen_0", "peer0", "proposals")
    os.makedirs(pdir, exist_ok=True)
    fn = filename or ("%s_%s.json" % (symbol, cov))
    with open(os.path.join(pdir, fn), "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False)
    config = os.path.join(root, "task_FM", "config")
    os.makedirs(config, exist_ok=True)
    base = os.path.join(config, "baseline_points_%s_nocov.jsonl" % symbol)
    if not os.path.exists(base):
        with open(base, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "protocol_fingerprint": "current-protocol",
                "cutoff": "2026-01-01 00:00:00",
                "dir_ok": True,
            }) + "\n")


def _prop(symbol="m", cov="vor", **over):
    p = {"schema": "fm.hypothesis_proposal.v1", "symbol": symbol,
         "cov_override": cov, "covariate_family": over.pop("family", "volatility"),
         "mechanism": LONGM, "symbol_fit": "该品种适配该协变量",
         "kill_condition": "ev<0", "promote_condition": "gate"}
    p.update(over)
    return p


@pytest.fixture
def tmproot(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "BACKLOG_PATH", str(tmp_path / "backlog.jsonl"))
    status_path = tmp_path / "symbol_status.json"
    status_path.write_text(
        '{"schema": "fm.symbol_status.v1", "symbols": {}}', encoding="utf-8")
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", str(status_path))
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: FP_TEST)
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
    return str(tmp_path)


def _vid(sym, cov, family="volatility"):
    fam = (S.load_covariate_pool().get(cov, {}) or {}).get("family") or family
    return "%s_%s_%s" % (sym, fam, FP_TEST[:12])


def _harvest(root, search_policy="off", **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600),
                               search_policy=search_policy)


# ── §6.1 档位解析 ────────────────────────────────────────────

def test_search_policy_missing_defaults_to_off():
    assert S._norm_search_policy({}) == "off"


def test_search_policy_none_defaults_to_off():
    assert S._norm_search_policy({"search_policy": None}) == "off"


@pytest.mark.parametrize("val", ["off", "shadow", "enforce"])
def test_search_policy_valid_passthrough(val):
    assert S._norm_search_policy({"search_policy": val}) == val


def test_search_policy_invalid_falls_back_to_off(caplog):
    with caplog.at_level(logging.WARNING):
        assert S._norm_search_policy({"search_policy": "bogus"}) == "off"
        assert S._norm_search_policy({"search_policy": "SHADOW"}) == "off"
    assert any("search_policy" in r.getMessage() for r in caplog.records)


def test_search_policy_bool_fail_closed_direct(caplog):
    """YAML 1.1 裸 off → False(bool) 的降级路径直接单测（审核 MINOR-2：
    此前仅由生产 yaml 字符串等式间接锁定）。"""
    with caplog.at_level(logging.WARNING):
        assert S._norm_search_policy({"search_policy": False}) == "off"
        assert S._norm_search_policy({"search_policy": True}) == "off"
        assert S._norm_search_policy({"search_policy": 1}) == "off"
    msgs = [r.getMessage() for r in caplog.records if "search_policy" in r.getMessage()]
    assert len(msgs) == 3, msgs


def test_search_policy_whitespace_not_normalized(caplog):
    """空白填充值不得无痕归一为合法档位（审核 NIT-1）：
    2.2 起 enforce 生效后，" enforce" 静默激活拒绝是不可接受的。"""
    with caplog.at_level(logging.WARNING):
        assert S._norm_search_policy({"search_policy": " enforce"}) == "off"
        assert S._norm_search_policy({"search_policy": "enforce "}) == "off"
        assert S._norm_search_policy({"search_policy": "sh adow"}) == "off"
    msgs = [r.getMessage() for r in caplog.records if "search_policy" in r.getMessage()]
    assert len(msgs) == 3, msgs


# ── T1 前半：off 下旧提案走今天的规则 ───────────────────────

def test_off_keeps_legacy_proposal_rules(tmproot):
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, search_policy="off")
    assert stats["selected"] == 1
    assert rows[0]["variant_id"] == _vid("m", "vor")
    assert stats["search_policy"] == "off"
    for reason in stats["reject_reasons"]:
        assert not reason.startswith("search_"), stats["reject_reasons"]


def test_21_plumbing_is_inert_for_shadow(tmproot):
    """2.1 只做开关管道：形参已通、行为未接。enforce 的拒绝语义自 2.2 起由
    test_search_tree_admission_20261006.py 接管（旧式提案 → search_role_missing，
    不再断言惰性）；shadow 的「本会拒绝」计数 2.9 接线，届时同样由专项测试取代。"""
    _make_run(tmproot, _prop())
    rows_off, stats_off = _harvest(tmproot, search_policy="off")
    rows_sh, stats_sh = _harvest(tmproot, search_policy="shadow")
    assert stats_off["selected"] == stats_sh["selected"] == 1
    assert [r["variant_id"] for r in rows_sh] == [r["variant_id"] for r in rows_off]
    assert stats_sh["search_policy"] == "shadow"


# ── 生产配置落点 ─────────────────────────────────────────────

def test_production_goal_declares_search_policy_off():
    goal = S.load_goal(os.path.join(ROOT, "scripts", "praxist_goal.yaml"))
    assert goal.get("search_policy") == "off"
