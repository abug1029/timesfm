"""supervisor.harvest_proposals 测试 (2026-09-08)

断言机制化假设收割:
- 合格提案入队 (source=peer_proposal, max_points 用 cadence)
- mechanism<40 字 / 非法 symbol / 不在池 cov 被拒绝并计数 (fail visibly)
- dead / passing / in-flight / seen 去重
- 新协变量想法进 backlog, 不入队
- family QD 多样性 seat-fill
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402

LONGM = ("波动率范围(VOR)压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
         "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。")


def _make_run(root, proposal, filename=None):
    symbol = str(proposal.get("symbol", "m")).lower()
    cov = proposal.get("cov_override") or "newcov"
    pdir = os.path.join(root, "task_FM", "experiments", "run_T",
                        "results", "gen_0", "peer0", "proposals")
    os.makedirs(pdir, exist_ok=True)
    fn = filename or ("%s_%s.json" % (symbol, cov))
    with open(os.path.join(pdir, fn), "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False)


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
    return str(tmp_path)


def _harvest(root, **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600))


def test_good_proposal_enqueued(tmproot):
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 1
    r = rows[0]
    assert r["variant_id"] == "m_vor"
    assert r["source"] == "peer_proposal"
    assert r["max_points"] == 600
    assert r["stage"] == "aligned"


def test_short_mechanism_rejected(tmproot):
    _make_run(tmproot, _prop(symbol="ss", cov="ccl", mechanism="太短"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "mechanism_too_short" in stats["reject_reasons"]


def test_unknown_cov_rejected(tmproot):
    _make_run(tmproot, _prop(symbol="m", cov="bogus_covariate_xyz"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "cov_not_in_active_pool" in stats["reject_reasons"]


def test_illegal_symbol_rejected(tmproot):
    _make_run(tmproot, _prop(symbol="zz", cov="vor"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "symbol_not_allowed" in stats["reject_reasons"]


def test_new_covariate_goes_to_backlog(tmproot):
    _make_run(tmproot, {"schema": "fm.hypothesis_proposal.v1", "symbol": "m",
                        "cov_override": None,
                        "new_covariate": {"name": "volume_profile", "formula": "...",
                                          "mechanism": LONGM, "family": "volume"}},
              filename="new_cov_volume_profile.json")
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert stats["backlog"] == 1
    assert os.path.exists(S.BACKLOG_PATH)
    rec = [json.loads(l) for l in open(S.BACKLOG_PATH, encoding="utf-8")][0]
    assert rec["name"] == "volume_profile"


def test_dead_dedup(tmproot):
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, dead={"m_vor"})
    assert stats["selected"] == 0
    assert "dedup" in stats["reject_reasons"]


def test_family_diversity_pass_one(tmproot):
    # 三个: 两个 volatility 族 (vor, bb_squeeze) + 一个 positioning (oi); top_k=2
    _make_run(tmproot, _prop(symbol="m", cov="vor", family="volatility"))
    _make_run(tmproot, _prop(symbol="ta", cov="bb_squeeze", family="volatility"))
    _make_run(tmproot, _prop(symbol="ss", cov="oi", family="positioning"))
    rows, stats = _harvest(tmproot, top_k=2)
    assert stats["selected"] == 2
    families = set()
    # 从 backlog 看不到 family (已 pop); 用 variant 推断: 两个选中应来自不同族
    assert len({r["variant_id"] for r in rows}) == 2
    # Pass1 每族一个 → 选中集合必含 positioning 的 ss_oi
    assert "ss_oi" in {r["variant_id"] for r in rows}


def test_priority_symbols_tiered_seat_fill(tmproot, monkeypatch):
    """扩目标: 1 星品种优先选座 —— tier0(1星 n>=350) > tier1(1星样本不足) > tier2(2星)。"""
    monkeypatch.setattr(S, "load_covariate_pool", lambda: {})
    nmap = {"m": 396, "jd": 396, "cj": 324, "fu": 396, "p": 396, "i": 396}
    monkeypatch.setattr(S, "_valid_n_for_symbol", lambda s: nmap.get(s))
    pri = ["m", "ss", "sr", "cj", "jd", "lh", "eg", "rb"]
    # 同分 (空 snapshot, 机制齐全) 跨 4 个族; 2 个 1 星可过门 + 1 个 1 星欠样本 + 3 个 2 星
    for sym, cov, fam in [("jd", "nvi", "positioning"), ("m", "oi", "volume"),
                          ("cj", "vor", "volatility"),
                          ("fu", "ccl", "structure"), ("p", "hurst", "statistical"),
                          ("i", "rsi_state", "oscillator")]:
        _make_run(tmproot, _prop(sym, cov, family=fam))
    rows, stats = S.harvest_proposals(
        tmproot, {}, set(), set(), {}, top_k=3,
        aligned_max_points=600, priority_symbols=pri)
    vids = {r["variant_id"] for r in rows}
    assert stats["selected"] == 3
    # tier0 两个必选, 第三席给 tier1(cj, 欠样本的 1 星) 而非任何 2 星
    assert {"jd_nvi", "m_oi", "cj_vor"} == vids

def test_priority_symbols_disabled_keeps_score_order(tmproot, monkeypatch):
    """不传 priority_symbols 时行为不变 (按分数/族/vid)。"""
    monkeypatch.setattr(S, "load_covariate_pool", lambda: {})
    called = {"n": 0}
    def _n(s):
        called["n"] += 1
        return 396
    monkeypatch.setattr(S, "_valid_n_for_symbol", _n)
    _make_run(tmproot, _prop("fu", "nvi", family="positioning"))
    _make_run(tmproot, _prop("m", "oi", family="volume"))
    rows, stats = S.harvest_proposals(
        tmproot, {}, set(), set(), {}, top_k=2, aligned_max_points=600)
    assert stats["selected"] == 2
    # 无 priority: 分层逻辑不查 DB
    assert called["n"] == 0

def test_new_covariate_dedup_across_harvests(tmproot):
    """同一 new_cov 被后续 cycle 重扫 (harvest 每 cycle glob 所有 run) 只入 backlog 一次。"""
    _make_run(tmproot, {"schema": "fm.hypothesis_proposal.v1", "symbol": "m",
                        "cov_override": None,
                        "new_covariate": {"name": "term_spread", "formula": "...",
                                          "mechanism": LONGM, "family": "structure"}},
              filename="new_cov_term_spread.json")
    _harvest(tmproot)
    rows2, stats2 = _harvest(tmproot)  # 第二 cycle 重扫同一 run
    assert stats2["backlog"] == 0
    assert "backlog_dup" in stats2["reject_reasons"]
    recs = [json.loads(l) for l in open(S.BACKLOG_PATH, encoding="utf-8") if l.strip()]
    assert [r["name"] for r in recs].count("term_spread") == 1
