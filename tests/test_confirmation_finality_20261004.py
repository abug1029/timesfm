"""2026-10-04 专家审核缺陷收口的回归测试（E1–E6）。

背景：b4c2e00 只把 no_data 墓碑排除出「已跑过」去重；专家审核证伪了它的
核心推论——D1 闸门只保证 1 根 bar 越过 confirm_from_ts，数据恢复后的首裁决
必然是 status=ok 的未满样 peek，计入 already 会把确认通道永久锁死。

E1 确认终态语义：只有满样终态裁决（status=ok 且 n_confirm_actual >=
   n_confirm_required）才永久占用「已跑过」名额。
E2 非终态重派节流：每 prereg 至少间隔 6h，防 ~250 行/天的 peek/墓碑 churn。
E3 探索复测排除确认通道的行（防 last-wins 覆盖 peek → 去重失效 → 振荡）。
E4 协变量跨品种拦截只认可确认的 DM 失败（对齐 _sector_filter_check）。
E5 error / timeout 墓碑保身份（prereg_id / run_mode / confirm_from_ts）。
E6 harvest 外层停机路径不返回半份候选。
"""
import json
import os
import sys
import time as _time_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import praxist_supervisor as sup  # noqa: E402
import aligned_slow_loop as slow  # noqa: E402


def _vid():
    return "jd_momentum_" + ("ab" * 32)[:12]


def _prereg(pid, symbol="jd", n_req=1199):
    return {
        "prereg_id": pid, "symbol": symbol,
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": n_req, "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }


def _wire(monkeypatch, tmp_path, preregs, snap):
    """标准接线：真实 rl / 派发；快照与数据闸门打桩；节流状态清零。"""
    p = tmp_path / "preregistry.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in preregs), encoding="utf-8")
    monkeypatch.setattr(sup, "PREREGISTRY_PATH", str(p))
    monkeypatch.setattr(sup, "FAMILY_REGISTRY", str(tmp_path / "family_registry.jsonl"))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "pending.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sup, "_active_protocol_snapshot", lambda path: snap)
    monkeypatch.setattr(sup, "_confirm_data_ready", lambda s, t: True)
    sup._CONFIRM_REDISPATCH.clear()
    return str(tmp_path / "decisions.jsonl")


def _confirmation_row(pid, **extra):
    v = {"variant_id": _vid(), "prereg_id": pid, "run_mode": "confirmation"}
    v.update(extra)
    return v


# ── E1 ───────────────────────────────────────────────────────────────
def test_final_confirmation_blocks_redispatch(tmp_path, monkeypatch):
    """满样终态裁决（n_confirm_actual >= n_confirm_required）永久阻断重派。"""
    pid = "p-final"
    snap = {_vid(): _confirmation_row(pid, status="ok",
                                      n_confirm_actual=1199, n_confirm_required=1199)}
    log = _wire(monkeypatch, tmp_path, [_prereg(pid)], snap)
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 0


def test_underfilled_peek_does_not_block_redispatch(tmp_path, monkeypatch):
    """未满样 peek 不占坑：数据恢复后首裁决必为 peek，必须还能重派。"""
    pid = "p-peek"
    snap = {_vid(): _confirmation_row(pid, status="ok", n=240,
                                      n_confirm_actual=240, n_confirm_required=1199)}
    log = _wire(monkeypatch, tmp_path, [_prereg(pid)], snap)
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 1


def test_verdict_missing_confirm_fields_not_final(tmp_path, monkeypatch):
    """n_confirm 字段缺失 → 非终态（防 None 比较崩溃 + 走节流自愈）。"""
    pid = "p-legacy"
    snap = {_vid(): _confirmation_row(pid, status="ok")}
    log = _wire(monkeypatch, tmp_path, [_prereg(pid)], snap)
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 1


def test_error_tombstone_with_prereg_does_not_block(tmp_path, monkeypatch):
    """带身份的 error 墓碑不占坑（E1）；重派频次由 E2 节流控制。"""
    pid = "p-err"
    snap = {_vid(): _confirmation_row(pid, status="error", n=0)}
    log = _wire(monkeypatch, tmp_path, [_prereg(pid)], snap)
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 1


# ── E2 ───────────────────────────────────────────────────────────────
def test_redispatch_throttled_six_hours(tmp_path, monkeypatch):
    """非终态重派 6h 节流：派发一次 → TTL 内不再派 → TTL 过期恢复。"""
    pid = "p-throttle"
    snap = {_vid(): _confirmation_row(pid, status="ok", n=5,
                                      n_confirm_actual=5, n_confirm_required=1199)}
    p = tmp_path / "preregistry.jsonl"
    p.write_text(json.dumps(_prereg(pid)) + "\n", encoding="utf-8")
    monkeypatch.setattr(sup, "PREREGISTRY_PATH", str(p))
    monkeypatch.setattr(sup, "FAMILY_REGISTRY", str(tmp_path / "family_registry.jsonl"))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "q.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "i.jsonl"))
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sup, "_active_protocol_snapshot", lambda path: snap)
    monkeypatch.setattr(sup, "_confirm_data_ready", lambda s, t: True)
    # 只隔离队列侧：in_flight 恒空、enqueue 记数，让节流成为唯一变量
    monkeypatch.setattr(sup.rl, "in_flight_ids", lambda q, i: set())
    monkeypatch.setattr(sup.rl, "queue_enqueue", lambda path, rows, dead, existing: len(rows))
    log = str(tmp_path / "decisions.jsonl")
    sup._CONFIRM_REDISPATCH.clear()
    sup._CONFIRMATION_NOTICE.clear()
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 1
    assert pid in sup._CONFIRM_REDISPATCH
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:05:00") == 0, "TTL 内不得重派"
    sup._CONFIRM_REDISPATCH[pid] = _time_mod.time() - sup._CONFIRM_REDISPATCH_TTL_S - 1
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:10:00") == 1, "TTL 过期应恢复重派"


def test_not_enqueued_notice_carries_throttle_state(tmp_path, monkeypatch):
    """节流期间 confirmation_not_enqueued 记账带上 redispatch_throttle 状态码。"""
    pid = "p-notice"
    snap = {_vid(): _confirmation_row(pid, status="ok", n=5,
                                      n_confirm_actual=5, n_confirm_required=1199)}
    p = tmp_path / "preregistry.jsonl"
    p.write_text(json.dumps(_prereg(pid)) + "\n", encoding="utf-8")
    monkeypatch.setattr(sup, "PREREGISTRY_PATH", str(p))
    monkeypatch.setattr(sup, "FAMILY_REGISTRY", str(tmp_path / "family_registry.jsonl"))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "q.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "i.jsonl"))
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sup, "_active_protocol_snapshot", lambda path: snap)
    monkeypatch.setattr(sup, "_confirm_data_ready", lambda s, t: True)
    monkeypatch.setattr(sup.rl, "in_flight_ids", lambda q, i: set())
    monkeypatch.setattr(sup.rl, "queue_enqueue", lambda path, rows, dead, existing: len(rows))
    log = str(tmp_path / "decisions.jsonl")
    sup._CONFIRM_REDISPATCH.clear()
    sup._CONFIRMATION_NOTICE.clear()
    sup._CONFIRM_REDISPATCH[pid] = _time_mod.time()   # 预置：TTL 内
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 0
    recs = [json.loads(l) for l in open(log, encoding="utf-8") if l.strip()]
    hit = [r for r in recs if r.get("action") == "confirmation_not_enqueued"]
    assert hit, "节流期间应有一条 not_enqueued 记账"
    assert hit[0]["refs"][-1] == "redispatch_throttle"


# ── E3 ───────────────────────────────────────────────────────────────
def test_retest_candidates_exclude_confirmation_rows():
    """peek 天然满足复测入选条件（ok + gate False + 0<n<350 + dir_acc>=0.50），
    但确认通道的行绝不能进探索复测。"""
    peek = {"variant_id": "jd_momentum_abc", "symbol": "jd", "cov_override": "vor",
            "schema": "fm.aligned_verdict.v2", "status": "ok", "gate_pass": False,
            "n": 240, "dir_acc": 0.55, "run_mode": "confirmation", "prereg_id": "p1"}
    expl = {"variant_id": "jd_momentum_xyz", "symbol": "jd", "cov_override": "vor",
            "schema": "fm.aligned_verdict.v2", "status": "ok", "gate_pass": False,
            "n": 240, "dir_acc": 0.55}
    out = sup._retest_candidates({peek["variant_id"]: peek, expl["variant_id"]: expl})
    assert [v["variant_id"] for v in out] == ["jd_momentum_xyz"]


# ── E4 ───────────────────────────────────────────────────────────────
def test_covariate_filter_counts_only_confirmable_failures():
    """描述性行不计数：3 座描述性失败不拦截；3 条可确认失败才拦截（阈值 3）。"""
    def row(vid, sym, dm):
        return {"variant_id": vid, "symbol": sym, "cov_override": "vor",
                "schema": "fm.aligned_verdict.v2", "status": "ok",
                "gate_pass": False, "dm_status": dm}

    descriptive = {f"v_d{i}": row(f"v_d{i}", f"s{i}", "set_mismatch_descriptive")
                   for i in range(3)}
    blocked, n_fail, _ = sup._covariate_filter_check("vor", "jd", descriptive)
    assert blocked is False and n_fail == 0, "描述性失败不得计数"

    confirmable = {f"v_c{i}": row(f"v_c{i}", f"s{i}", "ok") for i in range(3)}
    blocked, n_fail, _ = sup._covariate_filter_check("vor", "jd", confirmable)
    assert blocked is True and n_fail == 3, "可确认失败应计数并拦截"

    with_self = dict(confirmable)
    with_self["v_self"] = row("v_self", "jd", "ok")
    blocked, n_fail, _ = sup._covariate_filter_check("vor", "jd", with_self)
    assert blocked is True and n_fail == 3, "本品种自身失败不计数"

    with_pass = dict(confirmable)
    with_pass["v_p"] = dict(row("v_p", "s9", "ok"), gate_pass=True)
    blocked, _, n_pass = sup._covariate_filter_check("vor", "jd", with_pass)
    assert blocked is False and n_pass == 1, "任一品种过门即放行"


# ── E5 ───────────────────────────────────────────────────────────────
def test_error_tombstone_stamps_confirmation_identity(tmp_path, monkeypatch):
    """确认行评估异常时，error 墓碑必须带 prereg_id/run_mode/confirm_from_ts。"""
    reg = tmp_path / "registry.jsonl"
    reg.write_text("", encoding="utf-8")
    row = {"variant_id": "jd_momentum_abc", "symbol": "jd", "cov_override": "vor",
           "run_mode": "confirmation", "prereg_id": "p1",
           "confirm_from_ts": "2026-10-03 00:00:00", "max_points": 1199}

    def boom(*a, **k):
        raise RuntimeError("eval down")

    monkeypatch.setattr(slow, "_run_inner", boom)
    tomb = slow.run_aligned_candidate(row, str(tmp_path / "daily"), str(tmp_path / "ckpt"),
                                      str(reg), batch_id="b1")
    assert tomb["status"] == "error"
    assert tomb["prereg_id"] == "p1"
    assert tomb["run_mode"] == "confirmation"
    assert tomb["confirm_from_ts"] == "2026-10-03 00:00:00"
    lines = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines and lines[-1]["prereg_id"] == "p1", "落盘墓碑必须保留确认身份"


def test_timeout_tombstone_stamps_confirmation_identity(tmp_path):
    """batch 超时补墓碑时保留确认身份（batch_records 来自派发行）。"""
    reg = tmp_path / "registry.jsonl"
    reg.write_text("", encoding="utf-8")
    rows = [{"variant_id": "jd_momentum_abc", "symbol": "jd", "batch_id": "b1",
             "run_mode": "confirmation", "prereg_id": "p1",
             "confirm_from_ts": "2026-10-03 00:00:00"}]
    out = sup.wait_for_batch("b1", rows, str(reg), 0)
    assert out == []
    lines = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines and lines[-1]["status"] == "timeout"
    assert lines[-1]["prereg_id"] == "p1"
    assert lines[-1]["run_mode"] == "confirmation"


# ── E6 ───────────────────────────────────────────────────────────────
def test_harvest_outer_loop_shutdown_returns_empty(monkeypatch, tmp_path):
    """E6：停机信号在扫描中途（外层 run_dir 边界）置位 → 不得返回半份候选。"""
    monkeypatch.setattr(sup, "_load_evaluator", lambda: type("EV", (), {
        "VALID_COVARIATES": {"vor"}, "ALLOWED_SYMBOLS": {"jd"}, "ARCHIVED_COVARIATES": {},
    })())
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_symbol_status", lambda: {})
    monkeypatch.setattr(sup, "_dead_families", lambda snap: set())
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "baseline_points_jd_nocov.jsonl").write_text(
        json.dumps({"protocol_fingerprint": "fp-current", "cutoff": "2026-01-01 00:00:00",
                    "dir_ok": True}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp-current")
    for name in ("run_x", "run_y"):
        d = tmp_path / "task_FM" / "experiments" / name / "results" / "gen_0" / "proposals"
        d.mkdir(parents=True)
        (d / "jd_vor.json").write_text(
            json.dumps({"schema": "fm.hypothesis_proposal.v1", "symbol": "jd",
                        "cov_override": "vor", "mechanism": "x" * 60}), encoding="utf-8")

    # 对照组：未置标志时必须能产出候选（否则下面的断言空转）
    monkeypatch.setattr(sup, "_SHUTDOWN_REQUESTED", False)
    rows, stats = sup.harvest_proposals(str(tmp_path), {}, set(), set(),
                                        {"vor": {"family": "momentum"}}, top_k=3)
    assert rows, f"对照组：未置标志时应能产出候选（stats={stats}）"

    class _FlipAfter:
        """前 n 次 bool() 为 False，之后 True —— 模拟扫描途中置位。"""

        def __init__(self, n):
            self.n = n

        def __bool__(self):
            self.n -= 1
            return self.n < 0

    # 期望序列：#1 外层 run_x 检查、#2 run_x 文件内检查、#3 外层 run_y 检查 → True
    flip = _FlipAfter(2)
    monkeypatch.setattr(sup, "_SHUTDOWN_REQUESTED", flip)
    rows2, stats2 = sup.harvest_proposals(str(tmp_path), {}, set(), set(),
                                          {"vor": {"family": "momentum"}}, top_k=3)
    assert rows2 == [], "外层停机路径不得返回半份候选"
    assert stats2.get("aborted_by_shutdown") is True
    assert flip.n == -1, f"翻转应落在外层 run_y 检查（bool 计数异常：{flip.n}）"
