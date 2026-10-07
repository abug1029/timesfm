"""搜索树停止规则测试 — spec 2026-10-05 §6.5 / plan 2.4（T9、T13）+ P2.3 审核处置。

锁定：
- evaluate_tree_stops（纯函数，只判定不落账）：§6.5 条件序 first-hit
  budget → dominated → family_dead（promoted 是 2.7 事件驱动落账，
  不由巡检判定；stop/promote 同为终态后不再巡检——幂等）；
- budget：树成员 ∩ 当前协议 status=ok 裁决数 ≥ B=4（与守卫预算同口径）；
- dominated（fail-closed，停止不可逆）：
  * 节点参与资格 = status=ok 且 dir_acc/baseline_dir_acc/se 均有限
    （「se 不可算的节点不参与」——今日裁决行尚无 se 字段 → 条件休眠，
    2.5 落字段后自然激活；本文件用合成行锁语义）；
  * 现任 = 同品种 ok∧gate_pass δ 最大者（§5）；无现任 → 下界 0；
    现任 se 不可算 → 条件禁用（宁不停勿错停）；
  * δ 最大者上界 δ+1.645×se 严格小于现任下界 δ−1.645×se 才停；
    δ 平手取 se 较大者（上界更高更难停——保守方向）；
- family_dead：树族 ∈ _dead_families(snapshot)（判据照旧 min_ok=4/gate_pass，
  只计 dm_status 可确认的 ok 行）；
- M1（P2.3 审核）：崩溃窗口 A（accept 已落账、入队未发生）的 root 重放
  通道——同 proposal_id 已是未停止树成员 → 幂等放行原指派，不撞 busy
  （守卫拒绝=整行丢弃：否则成员永不评估，幻影树作为唯一扩展树冻结
  整个搜索）；树已停止的重放仍撞 search_tree_closed；
- M3：load 侧 B/τ 存在性校验（行内值与常量不符 → ValueError fail-loud；
  字段缺席放行，兼容手写行；spec §8 首行写入后不得更改）；
- N2：append_commitment event=stop 必须带合法 stop_reason 枚举
  （budget/promoted/dominated/family_dead）；
- N4：_commit_search_accepts 对缺 search_tree_id 的病态行防御跳过；
- M2：_commit_search_accepts docstring 勘误（进程退出+外部重启重放，
  非「外层主循环整轮重试」）；
- supervisor 接线：_sweep_search_stops（enforce-only、快照入参、写 stop
  行+search_stop 决策日志、幂等、写失败向上传播）；主循环每轮在
  materialize 之后、同轮收割之前巡检（源码存在性断言）。
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402
import registry_lib as rl  # noqa: E402
import search_trees as ST  # noqa: E402

LONGM = ("波动率范围(VOR)压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
         "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。")

FP_TEST = "ab" * 32

PVID_M = "m_volatility_parent01"
PID_M = "task_FM/experiments/run_A/results/gen_0/peer0/proposals/m_vor.json"
# 夹具自洽：树 id 必须是根 proposal_id 的真实哈希（否则 guard 级重放
# 测试里 computed assigned 与落账 tree_id 不一致，停止后会被当成新根）
TID_M = ST.tree_id_for("m", "volatility", PID_M)


@pytest.fixture
def tmproot(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "BACKLOG_PATH", str(tmp_path / "backlog.jsonl"))
    status_path = tmp_path / "symbol_status.json"
    status_path.write_text(
        '{"schema": "fm.symbol_status.v1", "symbols": {}}', encoding="utf-8")
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", str(status_path))
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: FP_TEST)
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH",
                        str(tmp_path / "search_commitments.jsonl"))
    monkeypatch.setattr(S, "QUEUE", str(tmp_path / "aligned_pending.jsonl"))
    monkeypatch.setattr(S, "INPROGRESS", str(tmp_path / "aligned_pending.inprogress.jsonl"))
    return str(tmp_path)


# ── 夹具/辅助 ─────────────────────────────────────────────────

def _vrow(vid, symbol="m", cov="vor", fam="volatility", dir_acc=0.495,
          baseline=0.46, emin=0.5, gate_pass=False, status="ok", se=None,
          **extra):
    row = {"schema": "fm.aligned_verdict.v2", "variant_id": vid,
           "symbol": symbol, "cov_override": cov, "cov_family": fam,
           "status": status, "gate_pass": gate_pass, "dir_acc": dir_acc,
           "baseline_dir_acc": baseline, "n": 588,
           "protocol_fingerprint": "current-protocol",
           "decided_at": "2026-10-01T00:00:00",
           "admissibility_rule": "edge_continuous_block_30d"}   # 步③ B
    if emin is not None:
        row["effective_min"] = emin
    if se is not None:
        row["se"] = se          # 2.5 起裁决行携带；今日生产行无此键
    row.update(extra)
    return row


def _seed_tree(vids=(), family="volatility", symbol="m", tid=TID_M):
    """落一棵树：根 accept（PVID_M/PID_M）+ 额外成员 accept。返回成员列表。"""
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=tid,
                         symbol=symbol, family=family, proposal_id=PID_M,
                         variant_id=PVID_M, search_role="root",
                         search_parent_id="")
    members = [PVID_M]
    for i, vid in enumerate(vids):
        ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=tid,
                             symbol=symbol, family=family,
                             proposal_id="p/extra%d.json" % i, variant_id=vid,
                             search_role="exploit", search_parent_id=PVID_M)
        members.append(vid)
    return members


def _read_commitments():
    with open(S.SEARCH_COMMITMENTS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _eval(index, snap, dead=None):
    return ST.evaluate_tree_stops(index, snap, dead or set())


def _write_line(rec):
    with open(S.SEARCH_COMMITMENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _prop(symbol="m", cov="vor", **over):
    p = {"schema": "fm.hypothesis_proposal.v1", "symbol": symbol,
         "cov_override": cov,
         "covariate_family": over.pop("family", "volatility"),
         "mechanism": LONGM, "symbol_fit": "该品种适配该协变量",
         "kill_condition": "ev<0", "promote_condition": "gate"}
    p.update(over)
    return p


def _make_run(root, proposal, filename=None, run="run_T"):
    symbol = str(proposal.get("symbol", "m")).lower()
    cov = proposal.get("cov_override") or "newcov"
    pdir = os.path.join(root, "task_FM", "experiments", run,
                        "results", "gen_0", "peer0", "proposals")
    os.makedirs(pdir, exist_ok=True)
    fn = filename or ("%s_%s.json" % (symbol, cov))
    with open(os.path.join(pdir, fn), "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False)
    t = time.time() - 10000
    os.utime(os.path.join(root, "task_FM", "experiments", run), (t, t))
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


def _harvest(root, search_policy="enforce", **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600),
                               search_policy=search_policy)


# ── 条件 1：budget ────────────────────────────────────────────

def test_budget_stop_at_four_ok_members(tmproot):
    members = _seed_tree(vids=["v1", "v2", "v3"])          # 4 成员全 ok
    snap = {v: _vrow(v, dir_acc=0.48) for v in members}
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, snap) == [(TID_M, "budget")]
    # 3 ok + 1 no_data → 未达（no_data 不占预算）
    snap["v3"] = _vrow("v3", status="no_data", dir_acc=0.48)
    assert _eval(idx, snap) == []


# ── 条件 3：dominated（fail-closed；今日生产行无 se → 休眠）────

def test_dominated_stop_fires(tmproot):
    _seed_tree()
    snap = {PVID_M: _vrow(PVID_M, dir_acc=0.49, baseline=0.50, se=0.004)}
    # 现任 δ=+0.02（0.52−0.50）、se=0.005 → 下界 ≈ 0.011775
    snap["inc1"] = _vrow("inc1", cov="mom_cov", fam="momentum",
                         dir_acc=0.52, baseline=0.50, se=0.005,
                         gate_pass=True)
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    # 成员 δ=−0.01、se=0.004 → 上界 ≈ −0.00342 < 下界 → dominated
    assert _eval(idx, snap) == [(TID_M, "dominated")]


def test_dominated_dormant_without_se(tmproot):
    """今日生产形状：裁决行无 se 字段 → 无人参与 → 条件休眠。"""
    _seed_tree()
    snap = {PVID_M: _vrow(PVID_M, dir_acc=0.30, baseline=0.50)}   # 无 se
    snap["inc1"] = _vrow("inc1", cov="mom_cov", fam="momentum",
                         dir_acc=0.52, baseline=0.50, se=0.005,
                         gate_pass=True)
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, snap) == []


def test_dominated_incumbent_se_missing_disables(tmproot):
    """现任 se 不可算 → 现任下界不可算 → 条件禁用（停止不可逆）。"""
    _seed_tree()
    snap = {PVID_M: _vrow(PVID_M, dir_acc=0.49, baseline=0.50, se=0.004)}
    snap["inc1"] = _vrow("inc1", cov="mom_cov", fam="momentum",
                         dir_acc=0.52, baseline=0.50, gate_pass=True)  # 无 se
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, snap) == []


def test_dominated_no_incumbent_lb_zero(tmproot):
    _seed_tree()
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    # 无现任 → 下界 0；δ=−0.05、se=0.01 → 上界 ≈ −0.03355 < 0 → 停
    snap = {PVID_M: _vrow(PVID_M, dir_acc=0.45, baseline=0.50, se=0.01)}
    assert _eval(idx, snap) == [(TID_M, "dominated")]
    # δ=+0.02、se=0.03 → 上界 ≈ 0.06935 > 0 → 不停
    snap[PVID_M] = _vrow(PVID_M, dir_acc=0.52, baseline=0.50, se=0.03)
    assert _eval(idx, snap) == []


def test_dominated_strict_inequality(tmproot):
    """上界 == 下界（全零构造）→ 严格小于才停 → 不停。"""
    _seed_tree()
    snap = {PVID_M: _vrow(PVID_M, dir_acc=0.50, baseline=0.50, se=0.0)}
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, snap) == []


def test_dominated_excludes_non_ok_and_missing_fields(tmproot):
    _seed_tree(vids=["v1"])
    snap = {
        # 非裁决完成行：即使带数值也不参与
        "v1": _vrow("v1", status="no_data", dir_acc=0.30, baseline=0.50,
                    se=0.001),
        # ok 但缺 baseline_dir_acc → δ 不可算
        PVID_M: {"variant_id": PVID_M, "symbol": "m", "status": "ok",
                 "dir_acc": 0.30, "se": 0.001},
        # v2 无裁决行（成员未评估）→ 自然不参与
    }
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, snap) == []


def test_dominated_tie_prefers_larger_se_conservative(tmproot):
    """δ 平手：取 se 较大者（上界更高 → 更难停——保守方向）。"""
    _seed_tree(vids=["v_tight"])
    snap = {
        PVID_M: _vrow(PVID_M, dir_acc=0.49, baseline=0.50, se=0.001),
        "v_tight": _vrow("v_tight", dir_acc=0.49, baseline=0.50, se=0.05),
    }
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    # δ 均 −0.01（无现任 lb=0）：小 se 上界 < 0（会停）、大 se 上界 > 0
    # （不停）→ 保守取大 se → 不停
    assert _eval(idx, snap) == []


# ── 条件 4：family_dead ───────────────────────────────────────

def test_family_dead_stop(tmproot):
    _seed_tree()
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, {}, {"volatility"}) == [(TID_M, "family_dead")]
    assert _eval(idx, {}, {"momentum"}) == []


# ── 条件序 first-hit + 终态幂等 ───────────────────────────────

def test_condition_order_first_hit(tmproot):
    members = _seed_tree(vids=["v1", "v2", "v3"])
    snap = {v: _vrow(v, dir_acc=0.45, baseline=0.50, se=0.01) for v in members}
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    # budget（4 ok）与 family_dead 同时成立 → budget 先
    assert _eval(idx, snap, {"volatility"}) == [(TID_M, "budget")]
    # dominated 与 family_dead 同时成立（预算未满）→ dominated 先
    snap1 = {PVID_M: _vrow(PVID_M, dir_acc=0.45, baseline=0.50, se=0.01)}
    assert _eval(idx, snap1, {"volatility"}) == [(TID_M, "dominated")]


def test_stopped_and_promoted_trees_not_swept(tmproot):
    _seed_tree()
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "stop", tree_id=TID_M,
                         stop_reason="budget")
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx, {}, {"volatility"}) == []
    # promote 终态同样不巡检（§6.5：promoted 与 stop 同为终态）
    TID2 = "m::momentum::bbbb00000002"
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=TID2,
                         symbol="m", family="momentum", proposal_id="p2",
                         variant_id="v_mom", search_role="root",
                         search_parent_id="")
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "promote", tree_id=TID2)
    idx2 = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert _eval(idx2, {}, {"momentum"}) == []


# ── M1（P2.3 审核）：崩溃窗口 A 的 root 重放通道 ───────────────

def test_root_replay_channel_guard_level(tmproot):
    _seed_tree()
    prop = {"search_role": "root", "search_parent_id": ""}
    # 同 proposal_id 重放（成员尚无裁决）→ 幂等放行原指派
    guard = ST.SearchGuard.load(S.SEARCH_COMMITMENTS_PATH, {})
    reason, info = guard.check(prop, "m", "volatility", "vor", PID_M)
    assert reason is None
    assert info["search_role"] == "root" and info["search_tree_id"] == TID_M
    # 成员已有当前协议裁决（陈旧重扫）→ 通道静默 → busy
    # （防每轮收割重扫都把已裁决根重新放行；T3 既有行为保持）
    guard1b = ST.SearchGuard.load(
        S.SEARCH_COMMITMENTS_PATH, {PVID_M: _vrow(PVID_M)})
    reason1b, _ = guard1b.check(prop, "m", "volatility", "vor", PID_M)
    assert reason1b == "search_tree_busy"
    # 不同 proposal_id 的新根 → busy（既有语义不变）
    guard2 = ST.SearchGuard.load(S.SEARCH_COMMITMENTS_PATH, {})
    reason2, _ = guard2.check(prop, "m", "volatility", "vor",
                              "task_FM/experiments/run_B/proposals/other.json")
    assert reason2 == "search_tree_busy"
    # 树已停止 → 重放撞 closed（不得重开已探索的树）
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "stop", tree_id=TID_M,
                         stop_reason="family_dead")
    guard3 = ST.SearchGuard.load(S.SEARCH_COMMITMENTS_PATH, {})
    reason3, _ = guard3.check(prop, "m", "volatility", "vor", PID_M)
    assert reason3 == "search_tree_closed"


def test_root_replay_channel_harvest_level(tmproot):
    """崩溃窗口 A 行为级：accept 已落账、入队未发生 → 重放收割必须重新
    带搜索键选出该行（修复前：撞 busy 被整行丢弃 → 成员永不评估，
    幻影树作为唯一扩展树冻结整个搜索）。"""
    _make_run(tmproot, _prop("m", "vor", search_role="root"),
              filename="m_root.json")
    rows, _ = _harvest(tmproot)
    assert rows and rows[0]["search_role"] == "root"
    tid = rows[0]["search_tree_id"]
    # 崩溃窗口 A：只落账，不入队
    assert S._commit_search_accepts(rows) == 1
    # 重放：收割经重放通道重新带键选出同一根
    rows2, _ = _harvest(tmproot, snap={})
    assert rows2 and rows2[0]["search_role"] == "root"
    assert rows2[0]["search_tree_id"] == tid
    # 幂等重落（成员集合语义）+ 重放入队成功
    assert S._commit_search_accepts(rows2) == 1
    recs = _read_commitments()
    assert [r["event"] for r in recs] == ["accept", "accept"]
    assert {r["variant_id"] for r in recs} == {rows[0]["variant_id"]}
    assert rl.queue_enqueue(S.QUEUE, rows2, set(), set()) == 1


# ── N2：stop_reason 枚举（§6.5）────────────────────────────────

def test_append_stop_requires_valid_stop_reason(tmproot):
    for bad in ("bogus", "manual", "", None):
        with pytest.raises(ValueError):
            ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "stop",
                                 tree_id=TID_M, stop_reason=bad)
    assert not os.path.exists(S.SEARCH_COMMITMENTS_PATH)   # fail-loud 不留半行
    for good in ("budget", "promoted", "dominated", "family_dead"):
        ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "stop", tree_id=TID_M,
                             stop_reason=good)
    assert [r["stop_reason"] for r in _read_commitments()] == [
        "budget", "promoted", "dominated", "family_dead"]


# ── M3：load 侧 B/τ 存在性校验（spec §8 冻结）─────────────────

def test_load_validates_b_tau_when_present(tmproot):
    base = {"schema": ST.COMMITMENTS_SCHEMA, "event": "accept",
            "tree_id": TID_M, "variant_id": PVID_M, "search_role": "root",
            "ts": "2026-10-06T00:00:00"}
    # 字段缺席 → 放行（兼容手写行）
    _write_line(dict(base))
    assert TID_M in ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH).trees
    # B 不符 → fail-loud
    os.remove(S.SEARCH_COMMITMENTS_PATH)
    _write_line(dict(base, B=5))
    with pytest.raises(ValueError):
        ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    # tau 不符 → fail-loud
    os.remove(S.SEARCH_COMMITMENTS_PATH)
    _write_line(dict(base, tau=0.05))
    with pytest.raises(ValueError):
        ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    # B/τ 与常量一致 → 放行
    os.remove(S.SEARCH_COMMITMENTS_PATH)
    _write_line(dict(base, B=4, tau=0.04))
    assert TID_M in ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH).trees


# ── N4：_commit_search_accepts 防御 ───────────────────────────

def test_commit_skips_row_missing_tree_id(tmproot):
    row = {"search_role": "root", "variant_id": "v1", "symbol": "m",
           "search_family": "volatility", "search_proposal_id": "p1"}
    assert S._commit_search_accepts([row]) == 0
    assert not os.path.exists(S.SEARCH_COMMITMENTS_PATH)


# ── M2：docstring 勘误（外部重启重放，非「整轮重试」）──────────

def test_commit_docstring_documents_external_restart():
    doc = S._commit_search_accepts.__doc__
    assert "整轮重试" not in doc
    assert "外部重启" in doc


# ── supervisor 接线：_sweep_search_stops ──────────────────────

def test_sweep_writes_budget_stop(tmproot, monkeypatch):
    calls = []
    monkeypatch.setattr(S, "_log_decision", lambda *a, **k: calls.append(a))
    members = _seed_tree(vids=["v1", "v2", "v3"])
    snap = {v: _vrow(v, dir_acc=0.48) for v in members}
    assert S._sweep_search_stops({"search_policy": "enforce"}, None, snap) == 1
    stop = [r for r in _read_commitments() if r["event"] == "stop"]
    assert len(stop) == 1
    assert stop[0]["tree_id"] == TID_M
    assert stop[0]["stop_reason"] == "budget"
    assert stop[0]["symbol"] == "m" and stop[0]["family"] == "volatility"
    assert stop[0]["B"] == 4 and stop[0]["tau"] == 0.04
    assert any(a[1] == "search_stop" for a in calls)
    # 幂等：已停止树不再巡检
    assert S._sweep_search_stops({"search_policy": "enforce"}, None, snap) == 0
    assert len(_read_commitments()) == 5          # 4 accept + 1 stop


def test_sweep_writes_family_dead_stop(tmproot, monkeypatch):
    """family_dead 走真实 _dead_families：4 条可确认失败 + 0 过门。"""
    calls = []
    monkeypatch.setattr(S, "_log_decision", lambda *a, **k: calls.append(a))
    TID = "m::momentum::cccc00000003"
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=TID,
                         symbol="m", family="momentum", proposal_id="pm",
                         variant_id="v_mom", search_role="root",
                         search_parent_id="")
    snap = {"v_mom": _vrow("v_mom", cov="mom_cov", fam="momentum",
                           dir_acc=0.48)}
    for i in range(4):
        vid = "mom_fail_%d" % i
        snap[vid] = _vrow(vid, cov="mom_cov", fam="momentum", dir_acc=0.45,
                          dm_status="ok", gate_pass=False)
    assert S._sweep_search_stops({"search_policy": "enforce"}, None, snap) == 1
    stop = [r for r in _read_commitments() if r["event"] == "stop"]
    assert stop[0]["tree_id"] == TID
    assert stop[0]["stop_reason"] == "family_dead"
    assert any(a[1] == "search_stop" for a in calls)


def test_sweep_policy_gated(tmproot):
    _seed_tree()
    snap = {PVID_M: _vrow(PVID_M, dir_acc=0.45, baseline=0.50, se=0.01)}
    for policy in ("off", "shadow", "en force", None):
        assert S._sweep_search_stops({"search_policy": policy}, None, snap) == 0
    assert len(_read_commitments()) == 1          # 只有 seed 的 1 条 accept


def test_sweep_noop_without_trees(tmproot):
    assert S._sweep_search_stops({"search_policy": "enforce"}, None, {}) == 0
    assert not os.path.exists(S.SEARCH_COMMITMENTS_PATH)   # 不创建文件


def test_sweep_write_failure_propagates(tmproot, monkeypatch):
    members = _seed_tree(vids=["v1", "v2", "v3"])
    snap = {v: _vrow(v, dir_acc=0.48) for v in members}

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(ST, "append_commitment", boom)
    with pytest.raises(OSError):
        S._sweep_search_stops({"search_policy": "enforce"}, None, snap)


def test_sweep_called_every_cycle_in_main_loop():
    """主循环每轮巡检插桩存在性（materialize 之后、收割之前）。"""
    with open(S.__file__, encoding="utf-8") as f:
        src = f.read()
    assert '_sweep_search_stops(goal, log, snap["variants"])' in src
