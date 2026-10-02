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


FP_TEST = "ab" * 32


def _vid(sym, cov, family="volatility"):
    """镜像生产 fam 推导 (pool 优先, 提案 family 兜底) 的 W6.4 vid。"""
    fam = (S.load_covariate_pool().get(cov, {}) or {}).get("family") or family
    return "%s_%s_%s" % (sym, fam, FP_TEST[:12])


@pytest.fixture
def tmproot(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "BACKLOG_PATH", str(tmp_path / "backlog.jsonl"))
    status_path = tmp_path / "symbol_status.json"
    status_path.write_text(
        '{"schema": "fm.symbol_status.v1", "symbols": {}}', encoding="utf-8")
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", str(status_path))
    # W6.4: 固定实验指纹, 测试 vid 确定性 (真实 fp 由生产路径覆盖)
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: FP_TEST)
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
    assert r["variant_id"] == _vid("m", "vor")
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
    rows, stats = _harvest(tmproot, dead={_vid("m", "vor")})
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
    assert _vid("ss", "oi", family="positioning") in {r["variant_id"] for r in rows}


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
    assert {_vid("jd", "nvi", "positioning"),
            _vid("m", "oi", "volume"),
            _vid("cj", "vor", "volatility")} == vids

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

def test_missing_schema_rejected(tmproot):
    p = _prop()
    del p["schema"]
    _make_run(tmproot, p)
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert rows == []
    assert "schema_mismatch" in stats["reject_reasons"]


def test_wrong_schema_rejected(tmproot):
    _make_run(tmproot, _prop(schema="fm.hypothesis_proposal.v0"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert rows == []
    assert "schema_mismatch" in stats["reject_reasons"]


def test_new_covariate_without_schema_still_backlog(tmproot):
    """schema 校验只拦 symbol+cov 收割候选；new_cov 无 schema 仍进 backlog。"""
    _make_run(tmproot, {"symbol": "m", "cov_override": None,
                        "new_covariate": {"name": "volume_profile", "formula": "...",
                                          "mechanism": LONGM, "family": "volume"}},
              filename="new_cov_volume_profile.json")
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert stats["backlog"] == 1
    assert "schema_mismatch" not in stats["reject_reasons"]
    rec = [json.loads(l) for l in open(S.BACKLOG_PATH, encoding="utf-8")][0]
    assert rec["name"] == "volume_profile"


def test_dead_symbol_rejected(tmproot, monkeypatch):
    status_path = os.path.join(tmproot, "symbol_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"schema": "fm.symbol_status.v1", "symbols": {
            "eg": {"status": "DEAD", "reason": "x"},
            "jd": {"status": "HOLD", "hold_generations": 5, "reason": "y"},
        }}, f)
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", status_path)
    _make_run(tmproot, _prop(symbol="eg", cov="oi"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "symbol_dead" in stats["reject_reasons"]


def test_hold_symbol_rejected(tmproot, monkeypatch):
    status_path = os.path.join(tmproot, "symbol_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"schema": "fm.symbol_status.v1", "symbols": {
            "jd": {"status": "HOLD", "hold_generations": 5, "reason": "y"},
        }}, f)
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", status_path)
    _make_run(tmproot, _prop(symbol="jd", cov="ccl"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "symbol_hold" in stats["reject_reasons"]


def test_active_symbol_still_enqueued(tmproot, monkeypatch):
    status_path = os.path.join(tmproot, "symbol_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"schema": "fm.symbol_status.v1", "symbols": {
            "eg": {"status": "DEAD", "reason": "x"},
        }}, f)
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", status_path)
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 1
    assert rows[0]["variant_id"] == _vid("m", "vor")


def test_production_goal_survivors_per_cycle_is_3():
    goal = S.load_goal(os.path.join(ROOT, "scripts", "praxist_goal.yaml"))
    assert goal["cadence"]["survivors_per_cycle"] == 3


DELTA = ("相对 m_vor（dir_acc 未过门），本次改用持仓量 oi："
         "豆粕有主力换月与套保盘，持仓方向比波动率压缩更贴机制。")


def test_failure_delta_required_when_symbol_already_failed(tmproot):
    snap = {"m_vor": {"variant_id": "m_vor", "symbol": "m", "cov_override": "vor",
                      "status": "ok", "gate_pass": False, "dir_acc": 0.45}}
    _make_run(tmproot, _prop(symbol="m", cov="oi"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "no_failure_delta" in stats["reject_reasons"]


def test_failure_delta_required_when_cov_already_failed(tmproot):
    snap = {"rb_oi": {"variant_id": "rb_oi", "symbol": "rb", "cov_override": "oi",
                      "status": "ok", "gate_pass": False, "dir_acc": 0.40}}
    _make_run(tmproot, _prop(symbol="m", cov="oi"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "no_failure_delta" in stats["reject_reasons"]


def test_failure_delta_short_rejected(tmproot):
    snap = {"m_vor": {"variant_id": "m_vor", "symbol": "m", "cov_override": "vor",
                      "status": "ok", "gate_pass": False, "dir_acc": 0.45}}
    _make_run(tmproot, _prop(symbol="m", cov="oi", failure_delta="太短"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "no_failure_delta" in stats["reject_reasons"]


def test_failure_delta_enqueued_when_present(tmproot):
    snap = {"m_vor": {"variant_id": "m_vor", "symbol": "m", "cov_override": "vor",
                      "status": "ok", "gate_pass": False, "dir_acc": 0.45}}
    _make_run(tmproot, _prop(symbol="m", cov="oi", failure_delta=DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 1
    assert rows[0]["variant_id"] == _vid("m", "oi")


def test_dead_family_harvest_rejected(tmproot):
    """Proposals for DEAD families (4+ ok, 0 pass) rejected at harvest."""
    # ccl -> pool family "inventory". Use pool family name in snapshot.
    snap = {
        "m_ccl_prev": {"variant_id": "m_ccl_prev", "symbol": "m",
                       "cov_override": "ccl_prev", "cov_family": "inventory",
                       "status": "ok", "gate_pass": False, "dir_acc": 0.45},
        "ss_ccl_prev": {"variant_id": "ss_ccl_prev", "symbol": "ss",
                        "cov_override": "ccl_prev2", "cov_family": "inventory",
                        "status": "ok", "gate_pass": False, "dir_acc": 0.44},
        "rb_ccl_prev": {"variant_id": "rb_ccl_prev", "symbol": "rb",
                        "cov_override": "ccl_prev3", "cov_family": "inventory",
                        "status": "ok", "gate_pass": False, "dir_acc": 0.43},
        "jd_ccl_prev": {"variant_id": "jd_ccl_prev", "symbol": "jd",
                        "cov_override": "ccl_prev4", "cov_family": "inventory",
                        "status": "ok", "gate_pass": False, "dir_acc": 0.42},
    }
    _make_run(tmproot, _prop(symbol="m", cov="ccl", family="inventory"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0, "DEAD family proposal should not be selected"
    assert "family_dead" in stats["reject_reasons"], \
        "reject_reason should be family_dead, got %s" % list(stats["reject_reasons"].keys())


def test_live_family_still_enqueued(tmproot):
    """Families with at least 1 pass should NOT be rejected as dead."""
    # oi -> pool family "inventory"
    snap = {
        "m_oi_prev": {"variant_id": "m_oi_prev", "symbol": "m",
                      "cov_override": "oi_prev", "cov_family": "inventory",
                      "status": "ok", "gate_pass": True, "dir_acc": 0.55},
    }
    _make_run(tmproot, _prop(symbol="ss", cov="oi", family="inventory"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 1, "Live family should be enqueued"
    assert "family_dead" not in stats["reject_reasons"]


# ---------------------------------------------------------------------------
# PR-B6 提案质量门 / 板块过滤 / 协变量过滤 —— 端到端接线测试
# 口径: v2 verdict 无 pf/ev/ic，"失败" = status=ok 且 gate_pass=False
# ---------------------------------------------------------------------------

def _sv(symbol, cov, gate_pass, decided_at, status="ok"):
    return {"schema": "fm.aligned_verdict.v2",
            "variant_id": "%s_%s" % (symbol, cov),
            "symbol": symbol, "cov_override": cov, "cov_family": "f",
            "status": status, "gate_pass": gate_pass, "decided_at": decided_at}


# 有失败履历的组合必须带 failure_delta，否则先被 no_failure_delta 拦截
# （该检查位于 PR-B6 质量门之前，故 PR-B6 测试须满足它才能到达新门）
FAIL_DELTA = "本次改用衰减填充并缩短 horizon，与上次失败口径不同，可区分机制是否成立。"


def test_cold_start_not_blocked_by_quality_gates(tmproot):
    """空 snapshot 不得被新门挡住（防止重演 2026-09-24 提案门禁饿死慢环）"""
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap={})
    assert stats["selected"] == 1
    assert stats["quality_below_threshold"] == 0
    assert stats["sector_blocked"] == 0
    assert stats["cov_cross_fail"] == 0


def test_quality_score_and_sector_recorded_on_row(tmproot):
    """入队行留痕 quality_score / sector，供宿主审查门是否过严"""
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, _ = _harvest(tmproot, snap={})
    r = rows[0]
    # 空 snapshot: novel +3, mechanism +3
    assert r["quality_score"] == 6.0
    assert r["sector"] == "agri"


def test_sector_blocked_rejected(tmproot):
    """板块全集（sector_map 定义的全部成员）最近裁决未过门 → sector_blocked

    circuit-breaker 语义: 仅当板块全集失败才拦，部分失败（即便 ≥3）不拦。
    用最小的板块 black_metals (4 个) 构造全集失败。
    """
    from config.sector_map import SECTORS
    bm = SECTORS["black_metals"]
    assert len(bm) == 4
    snap = {"%s_c" % s: _sv(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
            for i, s in enumerate(bm)}

    # 查询板块内品种 (rb)
    _make_run(tmproot, _prop(symbol="rb", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "sector_blocked" in stats["reject_reasons"]
    assert stats["sector_blocked"] == 1


def test_sector_partial_failure_does_not_block(tmproot):
    """板块部分失败不拦（防止生产快照三板块全拦的饿死问题）"""
    from config.sector_map import SECTORS
    # agri 10 个成员, 让 9 个失败 → 仍放行
    agri = SECTORS["agri"]
    snap = {"%s_c" % s: _sv(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
            for i, s in enumerate(agri[:9])}

    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert "sector_blocked" not in stats["reject_reasons"]


def test_cov_cross_fail_rejected(tmproot):
    """该协变量在其他品种失败 >=3 且从无过门 → cov_cross_fail"""
    # vor 在黑色系 3 品种失败；m(agri) 所在板块无失败 → 不会先触发 sector_blocked
    snap = {
        "rb_vor": _sv("rb", "vor", False, "2026-09-01T00:00:00"),
        "i_vor": _sv("i", "vor", False, "2026-09-02T00:00:00"),
        "jm_vor": _sv("jm", "vor", False, "2026-09-03T00:00:00"),
    }
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "cov_cross_fail" in stats["reject_reasons"]
    assert stats["cov_cross_fail"] == 1


def test_quality_below_threshold_rejected(tmproot):
    """净负分提案被拦截。

    构造: vor 早年在一个品种过门(使 covariate_filter 豁免)，
    但最近 3 次跨品种全失败 → -20；novel +3 + 机制 +3 → 合计 -14 < 0。
    """
    snap = {
        "sr_vor": _sv("sr", "vor", True, "2026-01-01T00:00:00"),
        "rb_vor": _sv("rb", "vor", False, "2026-09-01T00:00:00"),
        "i_vor": _sv("i", "vor", False, "2026-09-02T00:00:00"),
        "jm_vor": _sv("jm", "vor", False, "2026-09-03T00:00:00"),
    }
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "quality_below_threshold" in stats["reject_reasons"]
    assert stats["quality_below_threshold"] == 1


def test_covariate_filter_exempt_when_any_pass(tmproot):
    """该协变量在任一品种过门 → 不拦截（品种特异性优先）。

    注意窗口语义: 过门那次必须落在"最近 3 条"内，否则 cov_recent_fail 仍扣 -20。
    此处 sr 的过门是最新的，故豁免 + 不扣分，提案正常入队。
    """
    snap = {
        "rb_vor": _sv("rb", "vor", False, "2026-09-01T00:00:00"),
        "i_vor": _sv("i", "vor", False, "2026-09-02T00:00:00"),
        "jm_vor": _sv("jm", "vor", False, "2026-09-03T00:00:00"),
        "sr_vor": _sv("sr", "vor", True, "2026-09-04T00:00:00"),
    }
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert "cov_cross_fail" not in stats["reject_reasons"]
    assert "quality_below_threshold" not in stats["reject_reasons"]
    assert stats["selected"] == 1


def test_stale_pass_does_not_exempt_covariate_filter(tmproot):
    """过门若在窗口之外，covariate_filter 仍豁免，但 cov_recent_fail 照扣。

    锁定窗口语义: 豁免看全历史(有任一过门即放行)，
    扣分只看最近 COV_FAIL_WINDOW 条 —— 两者口径不同，不可混淆。
    """
    snap = {
        "sr_vor": _sv("sr", "vor", True, "2026-01-01T00:00:00"),
        "rb_vor": _sv("rb", "vor", False, "2026-09-01T00:00:00"),
        "i_vor": _sv("i", "vor", False, "2026-09-02T00:00:00"),
        "jm_vor": _sv("jm", "vor", False, "2026-09-03T00:00:00"),
    }
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=FAIL_DELTA))
    rows, stats = _harvest(tmproot, snap=snap)
    assert "cov_cross_fail" not in stats["reject_reasons"], "有历史过门 → 不拦截"
    assert "quality_below_threshold" in stats["reject_reasons"], \
        "窗口内 3 连败 → -20 使其净负"


def test_reject_reasons_and_counters_stay_consistent(tmproot):
    """新计数与 reject_reasons 必须一致（防止两套计数漂移）"""
    from config.sector_map import SECTORS
    # 用最小的板块 black_metals (4 个) 构造全集失败触发 sector_blocked
    bm = SECTORS["black_metals"]
    snap = {"%s_c" % s: _sv(s, "c", False, "2026-09-0%dT00:00:00" % (i + 1))
            for i, s in enumerate(bm)}

    _make_run(tmproot, _prop(symbol="rb", cov="vor", failure_delta=FAIL_DELTA))
    _, stats = _harvest(tmproot, snap=snap)
    # 键名已与 reject_reasons 对齐，相等即一致
    assert stats["sector_blocked"] == stats["reject_reasons"].get("sector_blocked", 0)
    assert stats["cov_cross_fail"] == stats["reject_reasons"].get("cov_cross_fail", 0)
    assert stats["quality_below_threshold"] == stats["reject_reasons"].get(
        "quality_below_threshold", 0)



def test_experiment_fp_unavailable_rejects(tmproot, monkeypatch):
    """W6.4: 指纹要素不可解析 → 拒收 (experiment_fp_unavailable), 不回退旧式身份。"""
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: None)
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("experiment_fp_unavailable") == 1


def test_family_unresolved_rejects(tmproot, monkeypatch):
    """pool 无该 cov 且提案未带 covariate_family → family_unresolved。"""
    monkeypatch.setattr(S, "load_covariate_pool", lambda: {})
    _make_run(tmproot, _prop(cov="vor", family=""))
    rows, stats = _harvest(tmproot)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("family_unresolved") == 1


def test_variant_id_format_is_experiment_identity(tmproot):
    """vid = {symbol}_{cov_family}_{fp[:12]}: 请求名不进身份键 (W6.4)。"""
    _make_run(tmproot, _prop())
    rows, _stats = _harvest(tmproot)
    assert rows and rows[0]["variant_id"] == _vid("m", "vor")
    assert rows[0]["variant_id"] != "m_vor"


def _write_registry(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _mixed_protocol_rows():
    def row(vid, symbol, cov, fp):
        item = {
            "variant_id": vid, "symbol": symbol, "cov_override": cov,
            "schema": "fm.aligned_verdict.v2", "status": "ok",
            "gate_pass": False, "n": 100, "dir_acc": 0.55,
        }
        if fp is not None:
            item["protocol_fingerprint"] = fp
        return item
    return [
        row("legacy_m", "m", "vor", "legacy"),
        row("nofp_sr", "sr", "rsi6", None),
        row("current_jd", "jd", "oi", "current"),
    ]


def test_harvest_snapshot_ignores_other_protocols(tmp_path, monkeypatch):
    """旧指纹和无指纹的失败不得进入收割快照，当前协议的失败仍要进入。"""
    reg = tmp_path / "aligned_verdicts.jsonl"
    _write_registry(reg, _mixed_protocol_rows())
    monkeypatch.setattr(S, "REGISTRY", str(reg))
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current")
    captured = {}

    def fake_harvest(root, snapshot, dead, existing, pool, **kwargs):
        captured["snapshot"] = snapshot
        captured["existing"] = existing
        return [], {"seen": 0}

    monkeypatch.setattr(S, "harvest_proposals", fake_harvest)
    S._harvest_rows({"cadence": {}})
    assert set(captured["snapshot"]) == {"current_jd"}
    assert "legacy_m" not in captured["existing"]
    assert "nofp_sr" not in captured["existing"]
    assert S._has_prior_failure(captured["snapshot"], "m", "vor") is False
    assert S._has_prior_failure(captured["snapshot"], "jd", "oi") is True


def test_retest_plan_ignores_other_protocols(tmp_path, monkeypatch):
    """复测计划同样只排当前协议里 n 不足的未过门裁决。"""
    reg = tmp_path / "aligned_verdicts.jsonl"
    _write_registry(reg, _mixed_protocol_rows())
    monkeypatch.setattr(S, "REGISTRY", str(reg))
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current")
    monkeypatch.setattr(S, "_valid_n_for_symbol", lambda symbol: 400)
    monkeypatch.setattr(S.rl, "in_flight_ids", lambda *a, **k: set())
    plan = S.plan_sample_retests({
        "cadence": {"retest_min_new_points": 1, "aligned_max_points": 600},
    })
    assert [item[0]["variant_id"] for item in plan] == ["current_jd"]
