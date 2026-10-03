"""2026-10-03 #6 端到端验证挖出的三缺陷的回归测试。

D1 确认集数据未越过 confirm_from_ts 时不派发（否则空评估 + 墓碑 + 重复入队）
D2 no_data 墓碑必须保留 run_mode / prereg_id（否则「已跑过」去重失效）
D3 family 成员登记不得被测试 fixture 污染（本测试自身隔离 FAMILY_REGISTRY，
   并断言 fixture vid 不出现在生产 family_registry.jsonl 里）
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import praxist_supervisor as sup  # noqa: E402
import aligned_slow_loop as slow  # noqa: E402


# ── D2 ────────────────────────────────────────────────────────────
def test_no_data_tombstone_keeps_run_mode_and_prereg_id():
    """墓碑不是评估产物，但必须保留身份，否则去重看不见它。

    修复前：run_mode=None、prereg_id 字段不存在 → 确认行每 ~5.7 分钟重入队一次，
    实测 jd/sr 各 11 座no_data 墓碑 + confirmation_enqueued 20 次。
    """
    row = {
        "variant_id": "jd_volatility_120f6854dbf5", "symbol": "jd",
        "cov_override": "vor", "run_mode": "confirmation",
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "confirm_from_ts": "2026-10-03 00:00:00",
    }
    v = slow._no_data_verdict(row, batch_id="b1")
    assert v["run_mode"] == "confirmation"
    assert v["prereg_id"] == "6f944c74e2c94ca5a5b70e64676e518b"
    assert v["confirm_from_ts"] == "2026-10-03 00:00:00"
    # 仍然不是评估产物：不得进入成功计数
    assert v["status"] == "no_data" and v["n"] == 0
    assert v["fdr_pass"] is False and v["p_value"] == 1.0


# ── D1 ────────────────────────────────────────────────────────────
def test_confirm_data_ready_is_fail_closed_and_cached(monkeypatch):
    """数据未越过边界 → False（不派发）；越过 → True；查询失败 → False。"""

    class FakeStore:
        def __init__(self, symbol, rows):
            self.rows = rows

        def get_main_contract_1h(self, limit=None):
            import pandas as pd
            return pd.DataFrame({"dt": self.rows})

        def close(self):
            pass

    sup._CONFIRM_DATA_CACHE.clear()
    # 数据最新 10-02 < confirm_from 10-03 → 未就绪
    monkeypatch.setattr("data.data_store.DataStore",
                        lambda s: FakeStore(s, ["2026-10-01 22:00:00", "2026-10-02 22:00:00"]))
    assert sup._confirm_data_ready("jd", "2026-10-03 00:00:00") is False
    # 数据最新 10-04 > 边界 → 就绪
    sup._CONFIRM_DATA_CACHE.clear()
    monkeypatch.setattr("data.data_store.DataStore",
                        lambda s: FakeStore(s, ["2026-10-04 22:00:00"]))
    assert sup._confirm_data_ready("jd", "2026-10-03 00:00:00") is True
    # 查询异常 → fail-closed
    sup._CONFIRM_DATA_CACHE.clear()

    def boom(s):
        raise RuntimeError("db down")

    monkeypatch.setattr("data.data_store.DataStore", boom)
    assert sup._confirm_data_ready("jd", "2026-10-03 00:00:00") is False


def test_maybe_enqueue_confirmations_respects_data_gate(tmp_path, monkeypatch):
    """数据未到位 → 一行都不派发（不写队列、不登记 family）。"""
    prereg = tmp_path / "preregistry.jsonl"
    fam = tmp_path / "family.jsonl"
    q = tmp_path / "q.jsonl"
    reg = {
        "prereg_id": "p1", "symbol": "jd", "confirm_from_ts": "2026-10-03 00:00:00",
        "registered_at": "2026-10-02T00:00:00+00:00",   # queue_decision 要求（W3.1）
        "n_confirm_required": 1199, "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    prereg.write_text(json.dumps(reg) + "\n", encoding="utf-8")
    monkeypatch.setattr(sup, "PREREGISTRY_PATH", str(prereg))
    monkeypatch.setattr(sup, "FAMILY_REGISTRY", str(fam))
    monkeypatch.setattr(sup, "QUEUE", str(q))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "i.jsonl"))
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sup, "rl", type("RL", (), {
        "in_flight_ids": staticmethod(lambda a, b: set()),
        "queue_enqueue": staticmethod(lambda *a, **k: 0),
        "load_snapshot": staticmethod(lambda p, only_protocol=None: {}),
    })())
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp")
    # 数据闸门关闭
    monkeypatch.setattr(sup, "_confirm_data_ready", lambda s, t: False)
    log = str(tmp_path / "d.jsonl")
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 0
    assert not q.exists(), "数据未到位时不得写队列"
    assert not fam.exists(), "数据未到位时不得登记 family 成员"
    # 闸门打开 → 派发
    monkeypatch.setattr(sup, "_confirm_data_ready", lambda s, t: True)
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 0  # queue_enqueue 桩返回 0
    assert fam.exists(), "闸门打开后应登记 family 成员"
    members = [json.loads(l) for l in open(fam, encoding="utf-8") if l.strip()]
    assert members and members[0]["run_mode"] == "confirmation"


# ── D3 ─────────────────────────────────────────���──────────────────
def test_production_family_registry_has_no_fixture_members():
    """生产 family_registry.jsonl 不得含测试 fixture 的 vid。

    2026-10-03 实测：6 个 member 里 4 个是测试夹具（vid 含 abababababab /
    0eab46f69739 / 0dc4dfe4079c），会虚增 family BH-FDR 的 K。已清理并备份为
    *.bak-20261003-fixture-pollution。
    """
    fr = os.path.join(ROOT, "task_FM", "config", "family_registry.jsonl")
    if not os.path.exists(fr):
        pytest.skip("family_registry.jsonl 尚未创建")
    members = [json.loads(l) for l in open(fr, encoding="utf-8") if l.strip()]
    fixture_markers = ("abababababab", "0eab46f69739", "0dc4dfe4079c")
    bad = [m for m in members
           if any(k in str(m.get("variant_id", "")) for k in fixture_markers)]
    assert not bad, f"生产 family_registry 含 fixture 成员：{[m['variant_id'] for m in bad]}"