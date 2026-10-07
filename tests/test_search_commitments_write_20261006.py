"""搜索树 commitments 写路径测试 — spec 2026-10-05 §6.5/§6.7 / plan 2.3（T3、T9）。

锁定：
- append_commitment（写入器）：append-only 事件行（schema/ts/B/τ 随行）；
  accept/stop/promote 三型；stop 带 stop_reason、promote 可带
  delta_post/n_required（触发语义 2.4/2.7 接线，此处锁写入器本身）；
  非法 event / 缺 tree_id fail-loud；历史行字节级不被改写
- 队列行（enforce）落账辅助字段 search_family / search_proposal_id
  （spec §6.2 三字段之外的记账辅助，写入器消费；off/shadow 行不带）
- _commit_search_accepts：只对将真实入队的搜索行落 accept（镜像
  rl.queue_enqueue 的 vid 去重：dead/existing/在队/批内首见）；
  被 vid 去重拦下的行不落账（防「成员永不评估」的持久幻影占位）；
  off/shadow 行天然空操作；置于 queue_enqueue 之前（崩溃重放：已入队
  者被过滤跳过、未入队者重写——成员集合语义幂等）
- T3 端到端：真实 accept 事件累计 4 条 ok 成员 → 下一份子提案
  search_budget_exhausted；重复 accept（同 vid）不重复计数（集合语义）
- T9 写入器→读路径：event=stop 落盘后子提案 search_tree_closed
- 扫描序不变量：run 目录 mtime 降序 → 新 run 提案先占角色座（陈旧提案
  不得饿死新提案；翻转 mtime 即翻转占座——锁定该依赖）
- _maybe_harvest 接线：入队后落 accept（wiring 级，mock 外围）
- 近失上边界等号（2.2 审核 NIT-3）：dir_acc == effective_min →
  not_near_miss（在 test_search_tree_admission 中补参数化，本文件不含）
"""
import json
import os
import sys
import time
import types

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
FP_ALT = "cd" * 32   # bb_squeeze 用
FP_A3 = "ef" * 32    # stddev 用
FP_A4 = "1212" * 16  # cycle4 的 vor 子用（与根 vid 区分）
FP_A5 = "3434" * 16  # cycle5 的提案用

TID_M = "m::volatility::aaaa00000001"
PVID_M = "m_volatility_parent01"


def _make_run(root, proposal, filename=None, run="run_T"):
    symbol = str(proposal.get("symbol", "m")).lower()
    cov = proposal.get("cov_override") or "newcov"
    pdir = os.path.join(root, "task_FM", "experiments", run,
                        "results", "gen_0", "peer0", "proposals")
    os.makedirs(pdir, exist_ok=True)
    fn = filename or ("%s_%s.json" % (symbol, cov))
    with open(os.path.join(pdir, fn), "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False)
    # run 目录 mtime 受控：收割按 mtime 降序扫描（新 run 先占座不变量）
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


def _touch_run(root, run, t):
    os.utime(os.path.join(root, "task_FM", "experiments", run), (t, t))


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
    monkeypatch.setattr(S, "QUEUE", str(tmp_path / "aligned_pending.jsonl"))
    monkeypatch.setattr(S, "INPROGRESS", str(tmp_path / "aligned_pending.inprogress.jsonl"))
    return str(tmp_path)


def _harvest(root, search_policy="enforce", **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600),
                               search_policy=search_policy)


def _enqueue_and_commit(rows):
    """复刻 _maybe_harvest 生产顺序：先落账（预判将入队者）再入队。"""
    n = S._commit_search_accepts(rows)
    rl.queue_enqueue(S.QUEUE, rows, set(), set())
    return n


def _read_commitments():
    with open(S.SEARCH_COMMITMENTS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


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


def _child(symbol="m", cov="vor", tree_id=TID_M, parent=PVID_M, role="exploit", **over):
    p = _prop(symbol, cov, search_role=role, search_parent_id=parent,
              tree_id=tree_id)
    p.update(over)
    return p


def _seed_tree(root, snap):
    """直接用写入器落一棵 (m, volatility) 树：根 accept + 近失 ok 裁决。"""
    pid = "task_FM/experiments/run_A/results/gen_0/peer0/proposals/m_vor.json"
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=TID_M,
                         symbol="m", family="volatility", proposal_id=pid,
                         variant_id=PVID_M, search_role="root", search_parent_id="")
    snap[PVID_M] = _vrow(PVID_M)


# ── 写入器单元级 ──────────────────────────────────────────────

def test_append_accept_row_schema_roundtrip(tmproot):
    rec = ST.append_commitment(
        S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=TID_M, symbol="m",
        family="volatility", proposal_id="p/m_vor.json",
        variant_id=PVID_M, search_role="root", search_parent_id="")
    assert rec["schema"] == "fm.search_commitments.v1"
    assert rec["event"] == "accept" and rec["B"] == 4 and rec["tau"] == 0.04
    assert rec["ts"]
    (line,) = _read_commitments()
    assert line["tree_id"] == TID_M and line["variant_id"] == PVID_M
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    tree = idx.trees[TID_M]
    assert tree.symbol == "m" and tree.family == "volatility"
    assert tree.member_vids == {PVID_M} and TID_M not in idx.stopped


def test_append_stop_promote_rows_and_append_only(tmproot):
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=TID_M,
                         symbol="m", family="volatility", proposal_id="p",
                         variant_id=PVID_M, search_role="root")
    with open(S.SEARCH_COMMITMENTS_PATH, "rb") as f:
        first_line = f.readline()
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "stop", tree_id=TID_M,
                         stop_reason="budget")
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "promote", tree_id=TID_M,
                         delta_post=0.05, n_required=588)
    recs = _read_commitments()
    assert [r["event"] for r in recs] == ["accept", "stop", "promote"]
    assert recs[1]["stop_reason"] == "budget"
    assert recs[2]["delta_post"] == 0.05 and recs[2]["n_required"] == 588
    with open(S.SEARCH_COMMITMENTS_PATH, "rb") as f:
        assert f.readline() == first_line  # 历史行字节级不动
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert TID_M in idx.stopped  # stop 与 promote 同为终态（§6.5）


def test_append_rejects_bad_event_and_missing_tree_id(tmproot):
    with pytest.raises(ValueError):
        ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "bogus", tree_id=TID_M)
    with pytest.raises(ValueError):
        ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id="")
    assert not os.path.exists(S.SEARCH_COMMITMENTS_PATH)  # fail-loud 不留半行


def test_duplicate_accept_same_vid_counts_once(tmproot):
    """同一 vid 重复 accept（重提/重放）不重复计预算（成员集合语义）。"""
    for _ in range(2):
        ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "accept", tree_id=TID_M,
                             symbol="m", family="volatility", proposal_id="p",
                             variant_id=PVID_M, search_role="root")
    guard = ST.SearchGuard.load(S.SEARCH_COMMITMENTS_PATH, {PVID_M: _vrow(PVID_M)})
    assert guard._budget[TID_M] == 1


# ── 队列行落账辅助字段 ────────────────────────────────────────

def test_harvest_rows_carry_writer_fields(tmproot):
    """enforce 行带 search_family/search_proposal_id 且与 tree_id 一致；off 行不带。"""
    _make_run(tmproot, _prop("m", "vor", search_role="root"),
              filename="m_vor_root.json")
    rows, _ = _harvest(tmproot)
    assert rows and rows[0]["search_role"] == "root"
    assert rows[0]["search_family"] == "volatility"
    assert rows[0]["search_proposal_id"] == (
        "task_FM/experiments/run_T/results/gen_0/peer0/proposals/m_vor_root.json")
    assert ST.tree_id_for("m", "volatility",
                          rows[0]["search_proposal_id"]) == rows[0]["search_tree_id"]
    rows_off, _ = _harvest(tmproot, search_policy="off")
    assert rows_off and all(
        k not in rows_off[0] for k in
        ("search_role", "search_tree_id", "search_parent_id",
         "search_family", "search_proposal_id"))


# ── _commit_search_accepts ───────────────────────────────────

def test_commit_accepts_only_actually_enqueued(tmproot):
    """两根（不同 symbol 身份、同族不同树）真实入队 → 各落一条 accept。

    批内处理顺序不确定（run 内 glob 序任意）→ 断言一律按 symbol 键控。
    """
    _make_run(tmproot, _prop("m", "vor", search_role="root"), filename="m_root.json")
    _make_run(tmproot, _prop("rb", "vor", search_role="root"), filename="rb_root.json")
    rows, _ = _harvest(tmproot)
    assert len(rows) == 2
    rows_by_sym = {r["symbol"]: r for r in rows}
    n = _enqueue_and_commit(rows)
    assert n == 2
    assert len(rl.queue_load(S.QUEUE)) == 2
    recs = _read_commitments()
    assert len(recs) == 2
    for r in recs:
        assert r["event"] == "accept" and r["B"] == 4 and r["tau"] == 0.04
        row = rows_by_sym[r["symbol"]]
        assert r["tree_id"] == row["search_tree_id"]
        assert r["variant_id"] == row["variant_id"]
        assert r["proposal_id"] == row["search_proposal_id"]
        assert r["family"] == "volatility" and r["search_role"] == "root"
        assert r["search_parent_id"] == ""
        assert ST.tree_id_for(r["symbol"], r["family"],
                              r["proposal_id"]) == r["tree_id"]
    idx = ST.load_tree_index(S.SEARCH_COMMITMENTS_PATH)
    assert len(idx.unstopped()) == 2


def test_commit_skips_dropped_row(tmproot):
    """入队会被 vid 去重拦下的行不落账（防持久幻影成员）——生产顺序。"""
    _make_run(tmproot, _prop("m", "vor", search_role="root"), filename="m_root.json")
    rows, _ = _harvest(tmproot)
    # 预置同 vid 行 → 该行在入队时会被去重
    rl.queue_enqueue(S.QUEUE, [dict(rows[0])], set(), set())
    assert S._commit_search_accepts(rows) == 0
    assert not os.path.exists(S.SEARCH_COMMITMENTS_PATH)
    # 一致性：入队同样把它拦下
    assert rl.queue_enqueue(S.QUEUE, rows, set(), set()) == 0


def test_commit_off_rows_noop(tmproot):
    _make_run(tmproot, _prop())
    rows, _ = _harvest(tmproot, search_policy="off")
    assert rows
    assert S._commit_search_accepts(rows) == 0
    assert not os.path.exists(S.SEARCH_COMMITMENTS_PATH)


# ── T9：写入器 → 读路径 ──────────────────────────────────────

def test_T9_stop_written_then_children_closed(tmproot):
    snap = {}
    _seed_tree(tmproot, snap)
    ST.append_commitment(S.SEARCH_COMMITMENTS_PATH, "stop", tree_id=TID_M,
                         stop_reason="dominated")
    _make_run(tmproot, _child())
    rows, stats = _harvest(tmproot, snap=snap)
    assert rows == [] and stats["selected"] == 0
    assert stats["reject_reasons"].get("search_tree_closed") == 1


# ── 扫描序不变量：新 run 先占座 ──────────────────────────────

def test_scan_order_fresh_run_claims_seat_first(tmproot):
    """mtime 降序 → 新 run 的子提案先占 exploit 座；陈旧提案不得饿死新提案。

    反向翻转 mtime 即翻转占座——锁定收割扫描序是角色座活性的承重依赖
    （陈旧已入队子提案每轮重扫：晚于新 run 处理 → 只产生 conflict 噪音）。
    """
    snap = {}
    _seed_tree(tmproot, snap)
    _make_run(tmproot, _child(cov="bb_squeeze"), filename="a_stale.json",
              run="run_old")
    _make_run(tmproot, _child(cov="stddev"), filename="b_fresh.json",
              run="run_new")
    t0 = time.time()
    _touch_run(tmproot, "run_old", t0 - 50)
    _touch_run(tmproot, "run_new", t0)
    rows, stats = _harvest(tmproot, snap=snap)
    assert [r["cov_override"] for r in rows] == ["stddev"]
    assert stats["reject_reasons"].get("search_role_conflict") == 1
    # 翻转 mtime：旧 run 先占座（锁定依赖方向）
    _touch_run(tmproot, "run_old", t0 + 50)
    rows2, stats2 = _harvest(tmproot, snap=snap)
    assert [r["cov_override"] for r in rows2] == ["bb_squeeze"]
    assert stats2["reject_reasons"].get("search_role_conflict") == 1


# ── T3 端到端：真实 accept 累计预算 ──────────────────────────

def test_T3_budget_exhausted_via_real_accepts(tmproot, monkeypatch):
    """cycle1 根 → cycle2-4 三份 exploit 子（真实入队+落账+裁决）→
    cycle5 下一份子提案 search_budget_exhausted。"""
    fps = {"vor": FP_TEST}

    def _fp(s, c):
        return fps.get(c, FP_TEST)

    monkeypatch.setattr(S, "_experiment_fp_for", _fp)

    def _vid(cov):
        return "m_volatility_" + fps[cov][:12]

    snap = {}
    # cycle 1：根
    _make_run(tmproot, _prop("m", "vor", search_role="root"),
              filename="m_root.json", run="run_c1")
    rows, _ = _harvest(tmproot, snap=snap)
    assert [r["search_role"] for r in rows] == ["root"]
    _enqueue_and_commit(rows)
    root_vid = "m_volatility_" + FP_TEST[:12]
    snap[root_vid] = _vrow(root_vid, dir_acc=0.495, emin=0.5)
    tid = ST.tree_id_for("m", "volatility", rows[0]["search_proposal_id"])

    # cycle 2-4：三份 exploit 子（异 cov / 异 fp → 异 vid）
    for k, (cov, fp) in enumerate(
            [("bb_squeeze", FP_ALT), ("stddev", FP_A3), ("vor", FP_A4)], start=2):
        fps[cov] = fp
        _make_run(tmproot, _child(cov=cov, tree_id=tid, parent=root_vid),
                  filename="m_child_%d.json" % k, run="run_c%d" % k)
        _touch_run(tmproot, "run_c%d" % k, time.time() - 10000 + k)
        rows, stats = _harvest(tmproot, snap=snap)
        assert [r["search_role"] for r in rows] == ["exploit"], (k, stats)
        _enqueue_and_commit(rows)
        snap[_vid(cov)] = _vrow(_vid(cov), dir_acc=0.48)

    recs = _read_commitments()
    assert len(recs) == 4 and all(r["event"] == "accept" for r in recs)
    guard = ST.SearchGuard.load(S.SEARCH_COMMITMENTS_PATH, snap)
    assert guard._budget[tid] == 4

    # cycle 5：第 5 份子提案 → 预算已满
    fps["stddev"] = FP_A5
    _make_run(tmproot, _child(cov="stddev", tree_id=tid, parent=root_vid),
              filename="m_child_5.json", run="run_c5")
    _touch_run(tmproot, "run_c5", time.time() - 10000 + 5)
    rows, stats = _harvest(tmproot, snap=snap)
    assert rows == [] and stats["selected"] == 0
    # 4 份子提案（1 新 + 3 陈旧重扫）全撞预算满（budget(3) 先于 parent
    # 检查；且守卫先于族死亡检查——4 条 volatility ok 已够族死亡阈值，
    # 但守卫先命中）；陈旧根提案撞 busy。计数是全 run_* 重扫的确定性结果。
    assert stats["reject_reasons"].get("search_budget_exhausted") == 4
    assert stats["reject_reasons"].get("search_tree_busy") == 1
    assert len(_read_commitments()) == 4  # 无新落账


# ── _maybe_harvest 接线（wiring 级） ─────────────────────────

def test_maybe_harvest_writes_accepts(tmproot, monkeypatch):
    """入队后、merge_save 前落 accept：mock 外围，真实走 enqueue+落账。"""
    _make_run(tmproot, _prop("m", "vor", search_role="root"),
              filename="m_root.json")
    rows, _ = _harvest(tmproot)
    monkeypatch.setattr(S, "_run_active", lambda: False)
    monkeypatch.setattr(
        S, "load_state",
        lambda: {"last_run_id": "run_T", "last_harvested_run_id": "run_OLD"})
    monkeypatch.setattr(S, "_merge_save", lambda d: None)
    monkeypatch.setattr(S, "_log_decision", lambda *a, **k: None)
    monkeypatch.setattr(
        S, "_harvest_rows",
        lambda goal: (rows, set(), set(),
                      {"seen": 1, "rejected": 0, "backlog": 0,
                       "reject_reasons": {}}))
    fake = types.ModuleType("praxist_assets_archive")
    fake.archive_fast_harvest = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "praxist_assets_archive", fake)
    st = {"last_run_id": "run_T", "last_harvested_run_id": "run_OLD"}
    assert S._maybe_harvest(st, {}, None) is True
    recs = _read_commitments()
    assert len(recs) == 1 and recs[0]["event"] == "accept"
    assert recs[0]["tree_id"] == rows[0]["search_tree_id"]
    queued = rl.queue_load(S.QUEUE)
    assert [r["variant_id"] for r in queued] == [rows[0]["variant_id"]]
