"""P2.8 同伴表面（spec 2026-10-05 §6.8 / §6.9）。

未停止的树写进 known_verdicts；没有树时写「无」。
族线索注明仅当前协议。prompt 教三个新字段，success_delta 原文不动。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402
import search_trees as st  # noqa: E402

FP = "f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5"


def _write(tmp_path, snap, commitments):
    dest = tmp_path / "known.md"
    S.materialize_known_verdicts(
        snap, str(dest), proposed_ids=set(), status_map={}, queue_ids=set(),
        commitments_path=str(commitments))
    return dest.read_text(encoding="utf-8")


def test_open_tree_section_says_none_when_empty(tmp_path):
    commitments = tmp_path / "search_commitments.jsonl"
    text = _write(tmp_path, {}, commitments)
    assert "## 未停止的树" in text
    assert "\n无\n" in text
    assert "本轮两份提案应为本轮扩展树" not in text


def test_open_tree_section_lists_parent_and_extension(tmp_path):
    commitments = tmp_path / "search_commitments.jsonl"
    st.append_commitment(
        str(commitments), "accept", tree_id="jd::momentum::aaa",
        symbol="jd", family="momentum", proposal_id="p1",
        variant_id="jd_mom_parent", search_role="root")
    snap = {
        "jd_mom_parent": {
            "variant_id": "jd_mom_parent",
            "symbol": "jd",
            "cov_override": "vor",
            "cov_family": "momentum",
            "status": "ok",
            "gate_pass": False,
            "dir_acc": 0.50,
            "effective_min": 0.52,
            "n": 100,
            "protocol_fingerprint": FP,
            "ev": 0.0,
            "schema": "fm.aligned_verdict.v2",
        }
    }
    text = _write(tmp_path, snap, commitments)
    assert "jd::momentum::aaa" in text
    assert "jd_mom_parent" in text
    assert "near_miss=yes" in text
    assert "budget=4" in text
    assert "本轮两份提案应为本轮扩展树的 exploit 与 falsifier。" in text


def test_family_clue_notes_current_protocol_only(tmp_path):
    snap = {
        "m1": {
            "variant_id": "m1", "symbol": "m", "cov_override": "mom",
            "cov_family": "momentum", "status": "ok", "gate_pass": True,
            "dir_acc": 0.55, "n": 100, "protocol_fingerprint": FP,
            "ev": 0.0, "schema": "fm.aligned_verdict.v2", "effective_min": 0.52,
        }
    }
    text = _write(tmp_path, snap, tmp_path / "missing.jsonl")
    assert "仅当前协议，旧协议已滤除；分母含描述性裁决。" in text
    assert "- momentum: 1/1 gate_pass low-n" in text


def test_prompt_teaches_search_fields_and_keeps_success_delta():
    path = os.path.join(ROOT, "task_FM", "prompt_base.jinja2")
    text = open(path, encoding="utf-8").read()
    assert "search_role" in text
    assert "search_parent_id" in text
    assert "tree_id" in text
    assert "`root`" in text or "root" in text
    assert "falsifier" in text
    assert "exploit" in text
    assert "缺 `success_delta` 的复跑会被拒收 (`no_success_delta`)。" in text
    assert "success_delta" in text.split("search_role")[0]
