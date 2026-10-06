"""搜索树资格门（enforce 档）测试 — spec 2026-10-05 §6.2 / plan 2.2。

锁定（T 序号见 spec §7）：
- T2  子角色父节点不是本树当前协议 ok 裁决 → search_parent_missing
      （父非树成员 / 父是成员但裁决非 ok / 父有 ok 裁决但非本树成员 三型）
- T4  同轮同品种同族第二棵根 → search_tree_busy
- T11 存在未停止树时 root（不撞 busy 的组合）→ search_root_while_tree_active
- T12 exploit 父节点非近失 → search_parent_not_near_miss
      （过阈 / 未达 0.49 / effective_min 缺失 fail-closed 三型；0.49 边界含等号）
- T17 扩展树 = event=accept 最早；平手按 tree_id 字典序；
      指向其他未停止树的子提案 → search_tree_busy
- T18 扩展树同角色第二份合法提案 → search_role_conflict；首份被拒不占座；
      exploit 与 falsifier 各占一席不冲突

解释锁定（spec 未逐字规定处，解读依据见 scripts/search_trees.py 模块 docstring）：
- enforce 下旧式提案（缺三字段）→ search_role_missing
- root 带非空 parent / child 缺 parent 或 tree_id → search_role_missing（字段合同）
- root 的 tree_id 字段值被收割忽略重写（队列行带收割指派的 id）
- 停止树（stop / promote）子提案 → search_tree_closed（读路径；写入路径 T9 在 2.4）
- 预算 = 树成员 ∩ 当前协议 ok 裁决（distinct vid）；no_data 不占预算
      （读路径；T3 在 2.3 锁写入回程）
- falsifier 与父同 cov → search_falsifier_same_cov；异 cov 放行
- 检查顺序 first-hit：role_missing 最前；busy 先于 root_while_tree_active 与
      parent_missing；budget 先于 parent_missing
- 根提案重提已停止树的同名 id → search_tree_closed（防御，防重开已探索的树）
- 子提案 (symbol, family) 与树身份不匹配 → search_tree_busy
- commitments 坏行 / 撕裂行跳过不炸（append-only 容错）
- 族未解析时守卫跳过（family_unresolved 归因不变）
- off 档带新字段的提案不触发任何 search_* 拒绝、队列行不带 search_* 键（S1）
- 队列行（enforce）携带 search_role/search_tree_id/search_parent_id（2.3 落账依据）

写入路径（accept/stop/promote 落盘、B/τ 记账）在 2.3 锁定（T3/T9）。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402
import search_trees as ST  # noqa: E402

LONGM = ("波动率范围(VOR)压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
         "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。")

FP_TEST = "ab" * 32
FP_ALT = "cd" * 32   # 与 FP_TEST 不同的实验指纹（同轮异 cov 时区分 vid 用）

TID_M = "m::volatility::aaaa00000001"      # (m, volatility) 树
PVID_M = "m_volatility_parent01"           # 该树根节点 vid（近失父）
TID_RB = "rb::volatility::bbbb00000002"    # (rb, volatility) 树
PVID_RB = "rb_volatility_parent02"


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
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH",
                        str(tmp_path / "search_commitments.jsonl"))
    return str(tmp_path)


def _harvest(root, search_policy="enforce", **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600),
                               search_policy=search_policy)


def _commit(event, tree_id, symbol="m", family="volatility", role="root",
            parent="", vid="", pid="", ts="2026-10-01T00:00:00", **extra):
    """向（monkeypatch 后的）search_commitments.jsonl 追加一条事件行。"""
    rec = {"schema": "fm.search_commitments.v1", "ts": ts, "event": event,
           "tree_id": tree_id, "symbol": symbol, "family": family,
           "proposal_id": pid, "variant_id": vid, "search_role": role,
           "search_parent_id": parent, "B": ST.BUDGET_B, "tau": ST.TAU_SD}
    rec.update(extra)
    path = S.SEARCH_COMMITMENTS_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _vrow(vid, symbol="m", cov="vor", fam="volatility", dir_acc=0.495,
          emin=0.5, gate_pass=False, status="ok", **extra):
    row = {"schema": "fm.aligned_verdict.v2", "variant_id": vid, "symbol": symbol,
           "cov_override": cov, "cov_family": fam, "status": status,
           "gate_pass": gate_pass, "dir_acc": dir_acc, "baseline_dir_acc": 0.46,
           "n": 588, "protocol_fingerprint": "current-protocol",
           "decided_at": "2026-10-01T00:00:00"}
    if emin is not None:
        row["effective_min"] = emin
    row.update(extra)
    return row


def _tree(tree_id=TID_M, symbol="m", family="volatility", vid=PVID_M,
          ts="2026-10-01T00:00:00"):
    """一棵未停止的树：根 accept（根节点 vid 即近失父）。"""
    _commit("accept", tree_id, symbol=symbol, family=family, role="root",
            vid=vid,
            pid="task_FM/experiments/run_A/results/gen_0/peer0/proposals/%s_vor.json" % symbol,
            ts=ts)


def _near_miss_snap(**over):
    return {PVID_M: _vrow(PVID_M, **over)}


def _child(symbol="m", cov="vor", tree_id=TID_M, parent=PVID_M, role="exploit", **over):
    p = _prop(symbol, cov, search_role=role, search_parent_id=parent,
              tree_id=tree_id)
    p.update(over)
    return p


# ── T2：父节点不是本树 ok 裁决 ────────────────────────────────

def test_T2_parent_not_tree_member(tmproot):
    _tree()
    _make_run(tmproot, _child(parent="m_volatility_not_a_member"))
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_parent_missing") == 1


def test_T2_parent_member_but_verdict_not_ok(tmproot):
    _tree()
    snap = {PVID_M: _vrow(PVID_M, status="no_data")}
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, snap=snap)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_parent_missing") == 1


def test_T2_parent_ok_verdict_but_not_member(tmproot):
    """父 vid 有当前协议 ok 裁决、但不是本树成员 → 仍 parent_missing（『本树』条件）。"""
    _tree()
    outsider = "m_volatility_outsider"
    snap = _near_miss_snap()
    snap[outsider] = _vrow(outsider)
    _make_run(tmproot, _child(parent=outsider))
    rows, stats = _harvest(tmproot, snap=snap)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_parent_missing") == 1


# ── T4：同轮同品种同族第二棵根 ────────────────────────────────

def test_T4_second_root_same_symbol_family_busy(tmproot):
    _make_run(tmproot, _prop(search_role="root"), filename="m_vor_a.json")
    _make_run(tmproot, _prop(search_role="root"), filename="m_vor_b.json")
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 1
    assert stats["reject_reasons"].get("search_tree_busy") == 1


# ── T11：存在未停止树时 root ─────────────────────────────────

def test_T11_root_while_tree_active(tmproot):
    _tree()
    # root 用不撞 busy 的组合（树是 (m, volatility)，root 提案 (rb, volatility)）
    _make_run(tmproot, _prop("rb", "vor", search_role="root"))
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_root_while_tree_active") == 1


def test_order_busy_before_root_while_tree_active(tmproot):
    """root 与既有未停止树同 (symbol, family) → busy(4) 先于 root_while_tree_active(8)。"""
    _tree()
    _make_run(tmproot, _prop(search_role="root"))
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_tree_busy") == 1
    assert "search_root_while_tree_active" not in stats["reject_reasons"]


# ── T12：exploit 父节点非近失 ─────────────────────────────────

@pytest.mark.parametrize("dir_acc,emin", [(0.51, 0.5), (0.48, 0.5)])
def test_T12_exploit_parent_not_near_miss(tmproot, dir_acc, emin):
    _tree()
    _make_run(tmproot, _child())
    rows, stats = _harvest(
        tmproot, snap={PVID_M: _vrow(PVID_M, dir_acc=dir_acc, emin=emin)})
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_parent_not_near_miss") == 1


def test_T12_effective_min_missing_fail_closed(tmproot):
    """父行缺 effective_min → 近失不可判 → fail-closed 拒（not_near_miss）。"""
    _tree()
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, snap={PVID_M: _vrow(PVID_M, emin=None)})
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_parent_not_near_miss") == 1


def test_T12_boundary_049_is_near_miss(tmproot):
    """0.49 <= dir_acc 边界含等号：0.49 是近失 → exploit 放行。"""
    _tree()
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, snap={PVID_M: _vrow(PVID_M, dir_acc=0.49)})
    assert stats["selected"] == 1
    assert "search_parent_not_near_miss" not in stats["reject_reasons"]


# ── T17：扩展树仲裁 ───────────────────────────────────────────

def test_T17_expansion_earliest_accept(tmproot):
    _tree(TID_M, vid=PVID_M, ts="2026-10-01T00:00:00")
    _tree(TID_RB, symbol="rb", vid=PVID_RB, ts="2026-10-02T00:00:00")
    snap = {PVID_M: _vrow(PVID_M), PVID_RB: _vrow(PVID_RB, symbol="rb")}
    # 扩展树 = TID_M（accept 更早）；TID_RB 的子提案 → busy
    _make_run(tmproot, _child(), filename="m_exploit.json")
    _make_run(tmproot, _child("rb", tree_id=TID_RB, parent=PVID_RB),
              filename="rb_exploit.json")
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 1
    assert stats["reject_reasons"].get("search_tree_busy") == 1
    assert rows[0]["search_tree_id"] == TID_M
    assert rows[0]["search_parent_id"] == PVID_M


def test_T17_tie_tree_id_lexicographic(tmproot):
    """同时刻 accept → tree_id 字典序小者为扩展树。"""
    _tree(TID_M, vid=PVID_M, ts="2026-10-01T00:00:00")
    _tree(TID_RB, symbol="rb", vid=PVID_RB, ts="2026-10-01T00:00:00")
    snap = {PVID_M: _vrow(PVID_M), PVID_RB: _vrow(PVID_RB, symbol="rb")}
    _make_run(tmproot, _child(), filename="m_exploit.json")
    _make_run(tmproot, _child("rb", tree_id=TID_RB, parent=PVID_RB),
              filename="rb_exploit.json")
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 1
    assert stats["reject_reasons"].get("search_tree_busy") == 1
    assert rows[0]["search_tree_id"] == TID_M


# ── T18：同角色占座 ───────────────────────────────────────────

def test_T18_role_conflict_second_exploit(tmproot):
    _tree()
    _make_run(tmproot, _child(), filename="m_exploit_a.json")
    _make_run(tmproot, _child(), filename="m_exploit_b.json")
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert stats["selected"] == 1
    assert stats["reject_reasons"].get("search_role_conflict") == 1


def test_T18_first_rejected_does_not_claim_seat(tmproot):
    """占座只认通过树检查的合法提案：首份 parent_missing 不占 exploit 座。"""
    _tree()
    _make_run(tmproot, _child(parent="m_volatility_bogus"),
              filename="m_exploit_bad.json")
    _make_run(tmproot, _child(), filename="m_exploit_good.json")
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert stats["selected"] == 1
    assert stats["reject_reasons"].get("search_parent_missing") == 1
    assert "search_role_conflict" not in stats["reject_reasons"]


def test_T18_exploit_and_falsifier_both_fit(tmproot, monkeypatch):
    """扩展树一轮各占一席：exploit 与 falsifier 不冲突（falsifier 用异 cov）。

    vid 不含 cov（W6.4），同轮同 (symbol, family) 异 cov 的 vid 靠实验指纹
    区分——生产中 fp 含请求协变量，此处按 cov 区分 monkeypatch 以复刻。
    """
    _tree()
    monkeypatch.setattr(S, "_experiment_fp_for",
                        lambda s, c: FP_TEST if c == "vor" else FP_ALT)
    _make_run(tmproot, _child(), filename="m_exploit.json")
    _make_run(tmproot, _child(cov="bb_squeeze", role="falsifier"),
              filename="m_falsifier.json")
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert stats["selected"] == 2
    assert "search_role_conflict" not in stats["reject_reasons"]
    roles = sorted(r["search_role"] for r in rows)
    assert roles == ["exploit", "falsifier"]


# ── falsifier 同 cov 拒 ───────────────────────────────────────

def test_falsifier_same_cov_as_parent_rejected(tmproot):
    _tree()
    _make_run(tmproot, _child(role="falsifier"))  # cov=vor == 父 cov vor
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_falsifier_same_cov") == 1


# ── 三字段解析与字段合同 ──────────────────────────────────────

def test_enforce_legacy_proposal_role_missing(tmproot):
    """enforce 下缺三字段的旧式提案 → search_role_missing（队列长度不变）。"""
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_role_missing") == 1
    assert stats["search_policy"] == "enforce"


def test_order_role_missing_first(tmproot):
    """role_missing(1) 最前：树活跃时旧式提案仍记 role_missing（非 root_active/busy）。"""
    _tree()
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_role_missing") == 1
    assert "search_root_while_tree_active" not in stats["reject_reasons"]


def test_root_with_parent_rejected(tmproot):
    _make_run(tmproot, _prop(search_role="root", search_parent_id="some_vid"))
    rows, stats = _harvest(tmproot)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_role_missing") == 1


def test_child_missing_parent_or_tree_id(tmproot):
    _tree()
    _make_run(tmproot, _prop(search_role="exploit", tree_id=TID_M),
              filename="no_parent.json")
    _make_run(tmproot, _prop(search_role="exploit", search_parent_id=PVID_M),
              filename="no_tree.json")
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_role_missing") == 2


def test_root_tree_id_field_ignored_and_reassigned(tmproot):
    """root 自带 tree_id 值被收割忽略：放行且队列行带收割指派的 id。"""
    _make_run(tmproot, _prop(search_role="root", tree_id="garbage::value"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 1
    assert rows[0]["search_tree_id"].startswith("m::volatility::")
    assert rows[0]["search_tree_id"] != "garbage::value"
    assert rows[0]["search_role"] == "root"
    assert rows[0]["search_parent_id"] == ""


# ── 停止树与预算（读路径） ────────────────────────────────────

@pytest.mark.parametrize("stop_event", ["stop", "promote"])
def test_stopped_tree_child_closed(tmproot, stop_event):
    _tree()
    extra = {"stop_reason": "budget"} if stop_event == "stop" else {}
    _commit(stop_event, TID_M, **extra)
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_tree_closed") == 1


def test_budget_exhausted_reader(tmproot):
    """4 名成员全 ok → 预算满；budget(3) 先于 parent_missing(5)。"""
    _tree(vid="m_volatility_n1")
    for i in (2, 3, 4):
        _commit("accept", TID_M, role="exploit", parent="m_volatility_n1",
                vid="m_volatility_n%d" % i,
                pid="task_FM/experiments/run_A/x/n%d.json" % i)
    snap = {"m_volatility_n%d" % i: _vrow("m_volatility_n%d" % i)
            for i in (1, 2, 3, 4)}
    _make_run(tmproot, _child(parent="m_volatility_bogus"))  # 故意 bogus：锁顺序
    rows, stats = _harvest(tmproot, snap=snap)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_budget_exhausted") == 1
    assert "search_parent_missing" not in stats["reject_reasons"]


def test_budget_no_data_does_not_count(tmproot):
    """no_data 不占预算：3 ok + 1 no_data → 预算 3 → 合法子提案放行。"""
    _tree(vid="m_volatility_n1")
    for i, st in ((2, "ok"), (3, "ok"), (4, "no_data")):
        _commit("accept", TID_M, role="exploit", parent="m_volatility_n1",
                vid="m_volatility_n%d" % i,
                pid="task_FM/experiments/run_A/x/n%d.json" % i)
    snap = {"m_volatility_n%d" % i: _vrow("m_volatility_n%d" % i,
                                          dir_acc=0.495 if i == 1 else 0.48,
                                          status="ok" if i < 4 else "no_data")
            for i in (1, 2, 3, 4)}
    _make_run(tmproot, _child(parent="m_volatility_n1"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 1
    assert "search_budget_exhausted" not in stats["reject_reasons"]


# ── 检查顺序 first-hit ────────────────────────────────────────

def test_order_busy_before_parent_missing(tmproot):
    """未知 tree_id + bogus 父 → busy(4) 先于 parent_missing(5)。"""
    _tree()
    _make_run(tmproot, _child(tree_id="unknown::tree::xyz",
                              parent="m_volatility_bogus"))
    rows, stats = _harvest(tmproot, snap=_near_miss_snap())
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_tree_busy") == 1
    assert "search_parent_missing" not in stats["reject_reasons"]


# ── 族未解析：守卫跳过 ────────────────────────────────────────

def test_family_unresolved_skips_guard(tmproot, monkeypatch):
    """协变量在活跃池（过 cov_not_in_active_pool）但族不可解析 → 守卫跳过，
    归因仍走下方既有 family_unresolved。pool 置空 + 提案不声明族，复刻
    「池缺该协变量」的族解析失败（不用假协变量名——那会先撞池检查）。"""
    monkeypatch.setattr(S, "load_covariate_pool", lambda: {})
    _make_run(tmproot, _prop("m", "vor", family=""))
    rows, stats = _harvest(tmproot)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("family_unresolved") == 1
    assert not any(r.startswith("search_") for r in stats["reject_reasons"])


# ── off / shadow 档：行为与今日相同 ───────────────────────────

def test_off_ignores_search_fields(tmproot):
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, search_policy="off")
    assert stats["selected"] == 1
    assert not any(r.startswith("search_") for r in stats["reject_reasons"])
    assert all(not k.startswith("search_") for k in rows[0])


def test_shadow_is_inert_until_29(tmproot):
    """2.2 只接 enforce；shadow 的求值计数在 2.9 接线，此前不入队行为与 off 相同。"""
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, search_policy="shadow")
    assert stats["selected"] == 1
    assert not any(r.startswith("search_") for r in stats["reject_reasons"])


# ── 守卫单元级解释锁定 ────────────────────────────────────────

def test_unit_expansion_tie_lex(tmp_path, monkeypatch):
    path = str(tmp_path / "search_commitments.jsonl")
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH", path)
    _commit("accept", "m::volatility::t00000000001", ts="2026-10-01T00:00:00")
    _commit("accept", "rb::volatility::t00000000002", symbol="rb",
            ts="2026-10-01T00:00:00")
    guard = ST.SearchGuard.load(path, {})
    assert guard.expansion_tree == "m::volatility::t00000000001"
    assert guard.root_round is False


def test_unit_root_reassigned_stopped_tree_closed(tmp_path):
    """根提案计算出的 tree_id 与已停止树同名 → closed（不得重开已探索的树）。"""
    path = str(tmp_path / "search_commitments.jsonl")
    pid = "task_FM/experiments/run_A/results/gen_0/peer0/proposals/m_vor.json"
    tid = ST.tree_id_for("m", "volatility", pid)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"schema": "fm.search_commitments.v1",
                            "ts": "2026-10-01T00:00:00", "event": "accept",
                            "tree_id": tid, "symbol": "m", "family": "volatility",
                            "proposal_id": pid, "variant_id": "m_volatility_old",
                            "search_role": "root", "search_parent_id": "",
                            "B": 4, "tau": 0.04}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"schema": "fm.search_commitments.v1",
                            "ts": "2026-10-02T00:00:00", "event": "stop",
                            "tree_id": tid, "stop_reason": "budget"},
                           ensure_ascii=False) + "\n")
    guard = ST.SearchGuard.load(path, {})
    reason, info = guard.check({"search_role": "root"}, "m", "volatility",
                               "vor", pid)
    assert reason == "search_tree_closed" and info is None


def test_unit_child_symbol_family_mismatch_busy(tmp_path):
    """子提案 (symbol, family) 与树身份不匹配 → busy（tree_id 对该提案而言不可用）。"""
    path = str(tmp_path / "search_commitments.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"schema": "fm.search_commitments.v1",
                            "ts": "2026-10-01T00:00:00", "event": "accept",
                            "tree_id": TID_M, "symbol": "m", "family": "volatility",
                            "proposal_id": "p", "variant_id": PVID_M,
                            "search_role": "root", "search_parent_id": "",
                            "B": 4, "tau": 0.04}, ensure_ascii=False) + "\n")
    guard = ST.SearchGuard.load(path, {PVID_M: _vrow(PVID_M)})
    prop = {"search_role": "exploit", "search_parent_id": PVID_M, "tree_id": TID_M}
    reason, _ = guard.check(prop, "rb", "volatility", "vor", "p_rb.json")
    assert reason == "search_tree_busy"
    reason, _ = guard.check(prop, "m", "momentum", "rsi_state", "p_mom.json")
    assert reason == "search_tree_busy"


def test_unit_malformed_commitments_lines_skipped(tmp_path):
    """坏行/撕裂行跳过并告警，不炸守卫装载。"""
    path = str(tmp_path / "search_commitments.jsonl")
    good = {"schema": "fm.search_commitments.v1", "ts": "2026-10-01T00:00:00",
            "event": "accept", "tree_id": TID_M, "symbol": "m",
            "family": "volatility", "proposal_id": "p", "variant_id": PVID_M,
            "search_role": "root", "search_parent_id": "", "B": 4, "tau": 0.04}
    with open(path, "w", encoding="utf-8") as f:
        f.write("not json at all\n")
        f.write(json.dumps({"schema": "wrong.schema"}, ensure_ascii=False) + "\n")
        f.write(json.dumps(good, ensure_ascii=False) + "\n")
        f.write('{"schema": "fm.search_commitments.v1", "ts": "2026-10')  # 撕裂尾行
    guard = ST.SearchGuard.load(path, {})
    assert guard.expansion_tree == TID_M
