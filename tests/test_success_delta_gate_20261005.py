"""T2 (2026-10-05): 已成功组合的 success_delta 增量论证门.

背景（2026-10-04/05 审计）：v4 当前协议下 gate+fdr 仅 1 条 m_momentum_b06ddbcd88e3；
所谓「已解决」集合为空。若 peer 在**同一评估窗口**内对已过硬门的 (symbol, cov)
组合反复提案（实验指纹变化 → vid 变化 → dedup 失效），仅靠"曾经过门"就能反复
挤占队列席位。本门要求这类复跑必须用 success_delta (>=20 字) 写清相对上次成功
的增量论证；评估窗已平移或锚不可得时放行（fail-open，不用墙钟——与
2026-09-23→09-30 15:00 窗口整体平移的审计事实一致，窗口平移后旧成功不再是
当前窗证据）。

门位置：harvest_proposals 内 dedup + PR-B6 质量门之后、prescreen 之前——
只作用于此前会被选中的提案，既有 reject 归因绝对不变。
失败侧匹配 (symbol OR cov)；成功侧匹配 (symbol AND cov_override)——刻意不同。

六路径：
1. 同窗已成功组合 + 无 success_delta → 拒收 no_success_delta
2. 该组合无成功史 → 放行 no_prior_success
3. prior_ts != anchor（窗口平移）→ 放行 window_moved
4. 锚不可得（无行字段且无 checkpoint）→ 放行 anchor_unavailable；
   含 checkpoint 兜底两分支（行 checkpoint_path 字段 / root 相对路径末行胜出）
5. success_delta <20 字拒、>=20 字过
6. 复测豁免是结构性的：_maybe_enqueue_retests 直接入队，不经过 harvest_proposals
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


def _vid(sym, cov, family="volatility"):
    fam = (S.load_covariate_pool().get(cov, {}) or {}).get("family") or family
    return "%s_%s_%s" % (sym, fam, FP_TEST[:12])


def _sv(vid, symbol, cov, *, gate_pass=True, eval_end_ts=None, extra=None):
    """v2 裁决行（snapshot 形态）。gate_pass=True 且 status=ok 即"已成功"。

    刻意不带 fdr_pass/p_value → 不进 rl.pass_variants → 不触发 vid dedup；
    刻意不带 dm_status → 描述性行 → 不进 sector/cov 拦截计数。
    """
    v = {"schema": "fm.aligned_verdict.v2", "variant_id": vid,
         "symbol": symbol, "cov_override": cov, "status": "ok",
         "gate_pass": gate_pass, "dir_acc": 0.55 if gate_pass else 0.42,
         "n": 350, "decided_at": "2026-10-01T08:00:00",
         "protocol_fingerprint": "current-protocol"}
    if eval_end_ts is not None:
        v["eval_end_ts"] = eval_end_ts
    if extra:
        v.update(extra)
    return v


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


def _harvest(root, **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600))


def test_gate_rejects_rerun_without_success_delta(tmproot, caplog):
    """路径 1：同窗已成功组合，复跑不带 success_delta → 拒收并计数。

    拒收信息必须带先验分类（v2-pass / hard-gate-but-losing）与 run_mode：
    探索先验（gate 过了但 fdr/p_value 缺、run_mode=exploration）在日志里
    不得被封账为成功——按 known_verdicts 图例口径分类。
    """
    import logging as _logging
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00",
                extra={"run_mode": "exploration"})
    _make_run(tmproot, _prop())  # 无 success_delta
    with caplog.at_level(_logging.WARNING):
        rows, stats = _harvest(tmproot, snap={"m_volatility_prior": prior})
    assert stats["selected"] == 0
    assert stats.get("reject_reasons", {}).get("no_success_delta") == 1
    assert stats.get("success_gate_states", {}).get("no_success_delta") == 1
    warn = "\n".join(r.getMessage() for r in caplog.records
                     if "no_success_delta" in r.getMessage())
    assert "m_volatility_prior" in warn, "拒收信息须点名先验 variant_id"
    assert "hard-gate-but-losing" in warn, "探索先验不得封账为 v2-pass"
    assert "exploration" in warn, "拒收信息须带先验 run_mode"
    assert "v2-pass" not in warn


def test_gate_allows_when_no_prior_success_for_combo(tmproot):
    """路径 2：成功史在别的组合，本组合无成功史 → 放行。

    成功侧匹配 (symbol AND cov)：(ss, ccl) 过门不约束 (m, vor)。
    """
    other = _sv("ss_structure_prior", "ss", "ccl", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, snap={"ss_structure_prior": other})
    assert stats["selected"] == 1
    assert stats.get("success_gate_states", {}).get("no_prior_success") == 1


def test_gate_allows_when_window_moved(tmproot):
    """路径 3：prior 的 eval_end_ts 落后于当前窗锚 → 窗口已平移 → 放行。

    审计事实镜像：09-23→09-30 15:00 窗整体更换后，旧窗成功不再是当前证据。
    """
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-23 15:00:00")
    newer = _sv("ss_structure_recent", "ss", "ccl", gate_pass=False,
                eval_end_ts="2026-09-30 15:00:00")
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, snap={"m_volatility_prior": prior,
                                          "ss_structure_recent": newer})
    assert stats["selected"] == 1
    assert stats.get("success_gate_states", {}).get("window_moved") == 1


def test_gate_anchor_unavailable_fails_open_and_checkpoint_fallback(tmproot):
    """路径 4：锚不可得放行（fail-open）；checkpoint 两分支兜底后执法。"""
    # 4a: 行无 eval_end_ts 且无 checkpoint → 锚不可得 → 放行
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True)
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, snap={"m_volatility_prior": prior})
    assert stats["selected"] == 1
    assert stats.get("success_gate_states", {}).get("anchor_unavailable") == 1

    # 4b: 行字段缺失，root 相对 checkpoint 兜底（末行胜出）→ 执法
    root2 = os.path.join(tmproot, "r2")
    prior2 = _sv("m_volatility_prior2", "m", "vor", gate_pass=True)
    _make_run(root2, _prop())
    cp_dir = os.path.join(root2, "data", "cache", "aligned_checkpoints")
    os.makedirs(cp_dir, exist_ok=True)
    with open(os.path.join(cp_dir, "m_volatility_prior2.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"eval_end_ts": "2026-09-23 15:00:00"}) + "\n")
        f.write(json.dumps({"eval_end_ts": "2026-09-30 15:00:00"}) + "\n")
    rows2, stats2 = _harvest(root2, snap={"m_volatility_prior2": prior2})
    assert stats2["selected"] == 0
    assert stats2.get("reject_reasons", {}).get("no_success_delta") == 1

    # 4c: 行字段 checkpoint_path 指向的文件兜底 → 执法
    root3 = os.path.join(tmproot, "r3")
    os.makedirs(root3, exist_ok=True)
    cp_file = os.path.join(root3, "cp_prior3.jsonl")
    prior3 = _sv("m_volatility_prior3", "m", "vor", gate_pass=True,
                 extra={"checkpoint_path": cp_file})
    _make_run(root3, _prop())
    with open(cp_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"eval_end_ts": "2026-09-30 15:00:00"}) + "\n")
    rows3, stats3 = _harvest(root3, snap={"m_volatility_prior3": prior3})
    assert stats3["selected"] == 0
    assert stats3.get("reject_reasons", {}).get("no_success_delta") == 1


def test_gate_success_delta_length_threshold(tmproot):
    """路径 5：success_delta <20 字拒收；>=20 字放行。"""
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    snap = {"m_volatility_prior": prior}
    _make_run(tmproot, _prop(success_delta="太短"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert stats.get("reject_reasons", {}).get("no_success_delta") == 1

    root2 = os.path.join(tmproot, "r2")
    _make_run(root2, _prop(
        success_delta="本次改用持仓加权口径重算vor并前移评估起点，窗口锚定后增量显著"))
    rows2, stats2 = _harvest(root2, snap=snap)
    assert stats2["selected"] == 1
    assert stats2.get("success_gate_states", {}).get("success_delta_ok") == 1

    # T2c 边界补强：恰好 20 字放行（阈值语义 >=）
    root3 = os.path.join(tmproot, "r3")
    _make_run(root3, _prop(success_delta="增" * 20))
    rows3, stats3 = _harvest(root3, snap=snap)
    assert stats3["selected"] == 1
    assert stats3.get("success_gate_states", {}).get("success_delta_ok") == 1


def test_retest_bypasses_success_gate_structurally(tmp_path, monkeypatch):
    """路径 6：复测豁免是结构性的——_maybe_enqueue_retests 直接入队。

    毒化 harvest_proposals：若复测路径误走收割（从而误过 success 门），
    本测试立刻炸。近失误 v2 裁决走 plan_sample_retests → rl.queue_enqueue。
    """
    monkeypatch.setattr(S, "FM_ROOT", str(tmp_path))
    monkeypatch.setattr(S, "QUEUE", str(tmp_path / "pending.jsonl"))
    monkeypatch.setattr(S, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(S, "REGISTRY", str(tmp_path / "verdicts.jsonl"))
    monkeypatch.setattr(S, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(S, "EVENTS_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
    nearmiss = {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": "cj_oi_nearmiss", "symbol": "cj", "cov_override": "oi",
        "status": "ok", "gate_pass": False, "dir_acc": 0.55, "n": 324,
        "decided_at": "2026-10-01T08:00:00",
        "protocol_fingerprint": "current-protocol",
        "eval_end_ts": "2026-09-30 15:00:00",
    }
    with open(S.REGISTRY, "w", encoding="utf-8") as f:
        f.write(json.dumps(nearmiss) + "\n")
    monkeypatch.setattr(S, "_valid_n_for_symbol", lambda s: 350)
    monkeypatch.setattr(S.rl, "in_flight_ids", lambda *a, **k: set())

    def _poison(*a, **k):
        raise AssertionError("复测路径不得调用 harvest_proposals / success 门")
    monkeypatch.setattr(S, "harvest_proposals", _poison)

    goal = {"cadence": {"aligned_max_points": 600, "retest_min_new_points": 1}}
    added = S._maybe_enqueue_retests(goal, str(tmp_path / "decisions.jsonl"))
    assert added == 1
    queued = S.rl.queue_load(S.QUEUE)
    assert [r["variant_id"] for r in queued] == ["cj_oi_nearmiss"]
    assert queued[0]["source"] == "sample_retest"


def test_gate_survives_non_utf8_checkpoint_fails_open(tmproot):
    """T2c (2026-10-05 审计修复): checkpoint 含非 UTF-8 字节（崩溃撕裂多字节
    字符，WSL 强杀实证场景）不得以 UnicodeDecodeError 炸 harvest。

    语义（钉死契约）：字节级损坏的 checkpoint = 不可靠证据 → 文件级弃读 →
    该行无锚 → anchor_unavailable 放行。text 迭代器按块解码，撕裂可波及
    块内先行行——统一向 fail-open 收敛，不承诺部分读保留。文件级异常面 =
    OSError + ValueError（UnicodeDecodeError 子类）。
    """
    # 7a: 首行合法、尾部撕裂 → 弃读整文件 → anchor_unavailable 放行（不炸）
    root = os.path.join(tmproot, "r_corrupt")
    prior = _sv("m_volatility_corrupt", "m", "vor", gate_pass=True)
    _make_run(root, _prop())
    cp_dir = os.path.join(root, "data", "cache", "aligned_checkpoints")
    os.makedirs(cp_dir, exist_ok=True)
    with open(os.path.join(cp_dir, "m_volatility_corrupt.jsonl"), "wb") as f:
        f.write(b'{"eval_end_ts": "2026-09-30 15:00:00"}\n')
        f.write(b'\xff\xfe torn tail\n')  # 非 UTF-8 撕裂字节
    rows, stats = _harvest(root, snap={"m_volatility_corrupt": prior})
    assert stats["selected"] == 1
    assert stats.get("success_gate_states", {}).get("anchor_unavailable") == 1

    # 7b: 全文皆非 UTF-8 → 同样弃读 → anchor_unavailable 放行（不炸）
    root2 = os.path.join(tmproot, "r_corrupt2")
    prior2 = _sv("m_volatility_corrupt2", "m", "vor", gate_pass=True)
    _make_run(root2, _prop())
    cp_dir2 = os.path.join(root2, "data", "cache", "aligned_checkpoints")
    os.makedirs(cp_dir2, exist_ok=True)
    with open(os.path.join(cp_dir2, "m_volatility_corrupt2.jsonl"), "wb") as f:
        f.write(b'\xff\xfe\xff\xfe binary garbage\n')
    rows2, stats2 = _harvest(root2, snap={"m_volatility_corrupt2": prior2})
    assert stats2["selected"] == 1
    assert stats2.get("success_gate_states", {}).get("anchor_unavailable") == 1


def test_gate_window_judgment_on_first_run_row_post_t2d(tmproot):
    """T2d 契约（plan P1）：首跑裁决行 eval_end_ts 经 checkpoint 兜底落章后，
    首跑节点从「锚不可得放行」进入「可窗口判定」——设计语义补全（预期收紧）。

    8a: T2d 前形态（首跑，行无字段且无 checkpoint 可兜底）→ fail-open 放行。
    8b: T2d 后形态（同一行带回填锚，当前窗锚即该行）→ 同窗复跑缺
    success_delta 拒收——首跑成功正式进入执法。
    """
    # 8a: 首跑行无锚可寻 → anchor_unavailable 放行（T2d 前形态，保持不变）
    prior_a = _sv("m_volatility_firstrun_a", "m", "vor", gate_pass=True)
    _make_run(tmproot, _prop())
    rows, stats = _harvest(tmproot, snap={"m_volatility_firstrun_a": prior_a})
    assert stats["selected"] == 1
    assert stats.get("success_gate_states", {}).get("anchor_unavailable") == 1

    # 8b: 同一行带 T2d 回填锚 → 窗口判定 → 拒收（首跑节点执法生效）
    root2 = os.path.join(tmproot, "r_t2d")
    prior_b = _sv("m_volatility_firstrun_b", "m", "vor", gate_pass=True,
                  eval_end_ts="2026-09-30 15:00:00")
    _make_run(root2, _prop())
    rows2, stats2 = _harvest(root2, snap={"m_volatility_firstrun_b": prior_b})
    assert stats2["selected"] == 0
    assert stats2.get("reject_reasons", {}).get("no_success_delta") == 1
    assert stats2.get("success_gate_states", {}).get("no_success_delta") == 1
