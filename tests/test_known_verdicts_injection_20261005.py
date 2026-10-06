"""T1 (2026-10-05) known_verdicts 注入通道硬化 — 计划 v2 T1 验收测试。

依据 docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md:
1. 族计数一律 pass/n（Passing/Weak 同记法），样本 <10 追加 low-n，全文无裸比率
2. 头部含 generated_at / protocol_fp8 / 源 registry mtime
3. 品种×族交叉矩阵只列非空格，行数预算内截断注明
4. 旧协议先验注记（excluded_items，或输入内非主协议组兜底）：
   仅上下文、不进主排名，预算 ≤20 行、confirmation/gate_pass 优先
5. 近失谓词与 _effective_clue_lines 活代码一致（不造第二套定义）
6. 幂等重写（除 generated_at 行外输出恒等）
"""
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import praxist_supervisor as sup  # noqa: E402

FP = "f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5"
FP_OLD = "bd851c9c" + "1" * 56


def _v(vid, symbol, cov, fam, *, gate_pass=False, dir_acc=0.45, fp=FP,
       run_mode="exploration", decided_at="2026-10-01T00:00:00", n=100,
       status="ok", effective_min=0.52):
    return {"schema": "fm.aligned_verdict.v2", "variant_id": vid,
            "symbol": symbol, "cov_override": cov, "cov_family": fam,
            "status": status, "gate_pass": gate_pass, "dir_acc": dir_acc,
            "n": n, "effective_min": effective_min, "ev": 0.0,
            "protocol_fingerprint": fp, "run_mode": run_mode,
            "decided_at": decided_at, "fdr_pass": False, "p_value": None}


def _write(tmp_path, snap, **kw):
    dest = tmp_path / "known_verdicts.inc.md"
    sup.materialize_known_verdicts(snap, str(dest), proposed_ids=set(),
                                   status_map={}, queue_ids=set(), **kw)
    return dest.read_text(encoding="utf-8")


def test_family_counts_carry_denominator_and_low_n(tmp_path):
    snap = {}
    for i in range(12):
        vid = "m_mom_%02d" % i
        snap[vid] = _v(vid, "m", "mom%d" % i, "momentum",
                       gate_pass=(i < 5), dir_acc=0.55 if i < 5 else 0.45)
    for i in range(6):
        vid = "jd_cal_%02d" % i
        snap[vid] = _v(vid, "jd", "cal%d" % i, "calendar",
                       gate_pass=(i < 2), dir_acc=0.55 if i < 2 else 0.46)
    text = _write(tmp_path, snap)
    assert "- momentum: 5/12 gate_pass" in text
    assert "- calendar: 2/6 gate_pass low-n" in text
    # 无裸比率：计数行必须带 pass/n 分母，全文不出现百分比
    assert not re.search(r"- \S+: \d+ gate_pass$", text, re.M), \
        "族计数不允许「N gate_pass」裸计数（缺分母）"
    assert "%" not in text


def test_weak_families_pass_n_notation(tmp_path):
    snap = {}
    for i in range(4):
        vid = "sr_ts_%d" % i
        snap[vid] = _v(vid, "sr", "ts%d" % i, "term_structure", dir_acc=0.44)
    for i in range(3):  # 3 < 4：不构成 weak family
        vid = "eg_spread_%d" % i
        snap[vid] = _v(vid, "eg", "spread%d" % i, "spread", dir_acc=0.44)
    text = _write(tmp_path, snap)
    assert "- term_structure: 0/4 gate_pass low-n" in text
    assert "- term_structure: 4 ok, 0 pass" not in text
    weak_sec = text.split("### Weak families", 1)[1].split("\n## ", 1)[0]
    assert "spread" not in weak_sec


def test_generated_at_fp8_registry_mtime_header(tmp_path, monkeypatch):
    from datetime import datetime
    reg = tmp_path / "verdicts.jsonl"
    reg.write_text(json.dumps(_v("m_mom", "m", "mom", "momentum")) + "\n",
                   encoding="utf-8")
    monkeypatch.setattr(sup, "REGISTRY", str(reg))
    snap = {"m_mom": _v("m_mom", "m", "mom", "momentum",
                        gate_pass=True, dir_acc=0.55)}
    text = _write(tmp_path, snap)
    hdr = next(ln for ln in text.splitlines() if ln.startswith("generated_at="))
    m = re.match(r"generated_at=(\S+) protocol_fp8=(\S+) registry_mtime=(\S+)$", hdr)
    assert m, "头部缺 generated_at/protocol_fp8/registry_mtime: %r" % hdr
    datetime.fromisoformat(m.group(1))
    assert m.group(2) == FP[:8]
    assert m.group(3) == datetime.fromtimestamp(reg.stat().st_mtime).isoformat()


def test_cross_matrix_only_nonempty_cells_and_budget(tmp_path, monkeypatch):
    snap = {
        "jd_mom": _v("jd_mom", "jd", "mom", "momentum",
                     gate_pass=True, dir_acc=0.55),
        "jd_cal1": _v("jd_cal1", "jd", "cal1", "calendar", dir_acc=0.44),
        "jd_cal2": _v("jd_cal2", "jd", "cal2", "calendar", dir_acc=0.44),
        "jd_cal3": _v("jd_cal3", "jd", "cal3", "calendar", dir_acc=0.44),
        "m_vol1": _v("m_vol1", "m", "vol1", "volatility",
                     gate_pass=True, dir_acc=0.53),
        "m_vol2": _v("m_vol2", "m", "vol2", "volatility", dir_acc=0.47),
    }
    text = _write(tmp_path, snap)
    assert "## Symbol x family" in text
    sec = text.split("## Symbol x family", 1)[1].split("\n## ", 1)[0]
    jd = next(ln for ln in sec.splitlines() if ln.startswith("- jd:"))
    m_line = next(ln for ln in sec.splitlines() if ln.startswith("- m:"))
    assert "momentum 1/1" in jd
    assert "calendar 0/3 low-n" in jd
    assert "volatility 1/2 low-n" in m_line
    # 只列非空格：无裁决的品种不出行
    assert not any(ln.startswith("- sr:") for ln in sec.splitlines())
    # 行数预算：超出行截断注明
    monkeypatch.setattr(sup, "CROSS_MATRIX_MAX_ROWS", 1, raising=False)
    text2 = _write(tmp_path, snap)
    sec2 = text2.split("## Symbol x family", 1)[1].split("\n## ", 1)[0]
    assert sum(1 for ln in sec2.splitlines() if ln.startswith("- ")) == 1
    assert "cross_matrix_truncated=1" in sec2


def test_old_protocol_priors_context_only(tmp_path):
    snap = {"jd_mom": _v("jd_mom", "jd", "mom", "momentum",
                         gate_pass=True, dir_acc=0.55)}
    excluded = {
        "m_old": _v("m_old", "m", "oi_slope", "inventory", fp=FP_OLD,
                    gate_pass=True, dir_acc=0.512,
                    decided_at="2026-09-20T10:00:00"),
        "sr_old": _v("sr_old", "sr", "rsi6", "momentum", fp=FP_OLD,
                     gate_pass=False, dir_acc=0.47,
                     decided_at="2026-09-21T10:00:00"),
        # fp == 主协议的行不得进注记区（调用侧混入时的安全网）
        "samefp_row": _v("samefp_row", "m", "mom", "momentum"),
    }
    text = _write(tmp_path, snap, excluded_items=excluded)
    assert "## Old-protocol priors" in text
    sec = text.split("## Old-protocol priors", 1)[1].split("\n## ", 1)[0]
    assert "仅上下文，不构成当前证据" in sec
    m_line = next(ln for ln in sec.splitlines() if "m_old" in ln)
    assert m_line.startswith("- [%s] " % FP_OLD[:12]), m_line
    assert "gate_pass=True" in m_line
    assert "decided_at=2026-09-20T10:00:00" in m_line
    assert "dir_acc=0.512" in m_line
    sr_line = next(ln for ln in sec.splitlines() if "sr_old" in ln)
    assert "gate_pass=False" in sr_line
    # 旧协议行只出现在注记区，不进主排名/逐行裁决区
    assert text.count("m_old") == 1
    assert "samefp_row" not in text
    assert "另有 1 个协议组的 2 条 verdict 未进主排名" in text


def test_old_priors_derived_from_input_without_kwarg(tmp_path):
    snap = {
        "m_fpA": _v("m_fpA", "m", "mom", "momentum", gate_pass=True,
                    dir_acc=0.60, run_mode="confirmation"),
        "m_fpB": _v("m_fpB", "m", "mom2", "momentum", gate_pass=True,
                    dir_acc=0.90, fp=FP_OLD),
        "legacy": dict(_v("legacy", "fu", "x", "momentum"),
                       protocol_fingerprint=None),
    }
    text = _write(tmp_path, snap)
    sec = text.split("## Old-protocol priors", 1)[1].split("\n## ", 1)[0]
    assert "m_fpB" in sec
    assert FP_OLD[:12] in sec
    # 「有旧指纹」才注记：无指纹（v1 legacy）行不进注记区
    assert "legacy" not in sec
    assert "另有 1 个协议组的 1 条 verdict 未进主排名" in text


def test_old_priors_budget_and_priority(tmp_path, monkeypatch):
    excluded = {}
    for i in range(25):
        vid = "s%02d_old" % i
        excluded[vid] = _v(vid, "s%02d" % (i % 5), "cov%02d" % i, "momentum",
                           fp=FP_OLD, gate_pass=(i >= 8),
                           decided_at="2026-09-%02dT00:00:00" % (i + 1))
    snap = {"jd_mom": _v("jd_mom", "jd", "mom", "momentum",
                         gate_pass=True, dir_acc=0.55)}
    text = _write(tmp_path, snap, excluded_items=excluded)
    sec = text.split("## Old-protocol priors", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("- [")]
    assert len(rows) == sup.OLD_PRIORS_MAX_ROWS
    assert "old_priors_truncated=5" in sec
    # gate_pass 行优先于未过门行
    assert all("gate_pass=True" in ln for ln in rows[:17]), \
        "预算内应先展示 gate_pass 行"


def test_near_miss_predicate_matches_live_code(tmp_path):
    snap = {
        "a": _v("a", "m", "c1", "momentum", dir_acc=0.495),
        "b": _v("b", "m", "c2", "momentum", dir_acc=0.489),
        "c": _v("c", "m", "c3", "momentum", dir_acc=0.505, gate_pass=True),
        "d": _v("d", "m", "c4", "momentum", dir_acc=0.515, effective_min=0.52),
        "e": _v("e", "m", "c5", "momentum", dir_acc=0.51, effective_min=0.50),
    }
    text = _write(tmp_path, snap)
    near = text.split("### Near-miss", 1)[1].split("\n###", 1)[0]
    assert "- a dir_acc=0.495 min=0.520" in near
    assert "- d dir_acc=0.515 min=0.520" in near
    for vid in ("b", "c", "e"):
        assert ("\n- %s " % vid) not in near, vid
    # 与活代码同源：materialize 的近失段 == _effective_clue_lines 直出
    direct = "\n".join(sup._effective_clue_lines(list(snap.values())))
    direct_near = direct.split("### Near-miss", 1)[1].split("\n###", 1)[0]
    assert near.strip() == direct_near.strip()


def test_idempotent_rewrite_except_generated_at(tmp_path):
    snap = {"jd_mom": _v("jd_mom", "jd", "mom", "momentum",
                         gate_pass=True, dir_acc=0.55),
            "m_cal": _v("m_cal", "m", "cal", "calendar", dir_acc=0.47)}
    t1 = _write(tmp_path, snap)
    t2 = _write(tmp_path, snap)
    norm = lambda t: [ln for ln in t.splitlines()
                      if not ln.startswith("generated_at=")]
    assert norm(t1) == norm(t2), "除 generated_at 外输出必须幂等"


def test_locked_section_lists_same_window_combo(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    row = _v("rb_basis_1", "rb", "basis_momentum", "basis", gate_pass=True)
    row["eval_end_ts"] = "2026-09-30 15:00:00"
    text = _write(tmp_path, {"rb_basis_1": row})
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert "rb cov=basis_momentum prior=rb_basis_1 class=hard-gate-but-losing eval_end_ts=2026-09-30 15:00:00" in sec
    assert text.index("## Locked this window") < text.index("## Do not re-propose")


def test_locked_section_empty_when_data_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-09-30 14:00:00")
    row = _v("rb_basis_1", "rb", "basis_momentum", "basis", gate_pass=True)
    row["eval_end_ts"] = "2026-09-30 15:00:00"
    text = _write(tmp_path, {"rb_basis_1": row})
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert "- (none)" in sec
    assert "basis_momentum" not in sec


def test_locked_section_uses_checkpoint_when_row_has_no_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    row = _v("rb_basis_1", "rb", "basis_momentum", "basis", gate_pass=True,
             run_mode="confirmation")
    row["fdr_pass"] = True
    row["p_value"] = 0.01
    cp = tmp_path / "data" / "cache" / "aligned_checkpoints"
    cp.mkdir(parents=True)
    (cp / "rb_basis_1.jsonl").write_text(
        json.dumps({"eval_end_ts": "2026-09-30 15:00:00"}) + "\n",
        encoding="utf-8")
    text = _write(tmp_path, {"rb_basis_1": row}, root=str(tmp_path))
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert "class=v2-pass" in sec
    assert "eval_end_ts=2026-09-30 15:00:00" in sec


def test_locked_section_truncates_at_40(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    snap = {}
    for i in range(41):
        vid = "s%02d_basis" % i
        row = _v(vid, "s%02d" % i, "basis_momentum", "basis", gate_pass=True)
        row["eval_end_ts"] = "2026-10-08 15:00:00"
        snap[vid] = row
    text = _write(tmp_path, snap)
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert sum(1 for ln in sec.splitlines() if ln.startswith("- ")) == 40
    assert "locked_window_truncated=1" in sec
