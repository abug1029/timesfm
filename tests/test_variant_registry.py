"""Tests for variant_registry module."""
import json
import os
import sys
import threading

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
scripts_dir = os.path.join(_repo_root, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import pytest
from variant_registry import VariantRegistry


@pytest.fixture
def tmp_registry(tmp_path):
    return str(tmp_path / "variant_registry.jsonl")


class TestVariantRegistry:

    def test_load_empty(self, tmp_registry):
        reg = VariantRegistry(tmp_registry)
        assert reg.load() == 0
        assert len(reg) == 0

    def test_register_and_has_stem(self, tmp_registry):
        reg = VariantRegistry(tmp_registry)
        reg.load()
        assert not reg.has_stem("eg_rsi_state")
        reg.register("eg_rsi_state", "run_001")
        assert reg.has_stem("eg_rsi_state")
        assert len(reg) == 1

    def test_register_idempotent(self, tmp_registry):
        reg = VariantRegistry(tmp_registry)
        reg.load()
        reg.register("eg_rsi_state", "run_001", ts="2026-10-20T12:00:00Z")
        reg.register("eg_rsi_state", "run_002", ts="2026-10-20T13:00:00Z")
        assert len(reg) == 1
        assert reg._stems["eg_rsi_state"]["first_seen"] == "2026-10-20T12:00:00Z"
        assert reg._stems["eg_rsi_state"]["run_id"] == "run_001"

    def test_persistence(self, tmp_registry):
        reg1 = VariantRegistry(tmp_registry)
        reg1.load()
        reg1.register("eg_rsi_state", "run_001")
        reg1.register("sr_vor", "run_001")
        assert len(reg1) == 2
        reg2 = VariantRegistry(tmp_registry)
        count = reg2.load()
        assert count == 2
        assert reg2.has_stem("eg_rsi_state")
        assert reg2.has_stem("sr_vor")

    def test_jsonl_format(self, tmp_registry):
        reg = VariantRegistry(tmp_registry)
        reg.load()
        reg.register("eg_rsi_state", "run_001", ts="2026-10-20T12:00:00Z")
        reg.register("sr_vor", "run_002", ts="2026-10-20T13:00:00Z")
        lines = open(tmp_registry, encoding="utf-8").readlines()
        assert len(lines) == 2
        rec1 = json.loads(lines[0])
        assert rec1["stem"] == "eg_rsi_state"
        assert rec1["first_seen"] == "2026-10-20T12:00:00Z"
        assert rec1["run_id"] == "run_001"

    def test_get_stems(self, tmp_registry):
        reg = VariantRegistry(tmp_registry)
        reg.load()
        reg.register("eg_rsi_state", "run_001")
        reg.register("sr_vor", "run_001")
        assert reg.get_stems() == {"eg_rsi_state", "sr_vor"}

    def test_concurrent_safety(self, tmp_registry):
        def register_stems(start, end):
            r = VariantRegistry(tmp_registry)
            r.load()
            for i in range(start, end):
                r.register(f"stem_{i}", f"run_{i}")
        threads = [
            threading.Thread(target=register_stems, args=(0, 50)),
            threading.Thread(target=register_stems, args=(50, 100)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        reg2 = VariantRegistry(tmp_registry)
        count = reg2.load()
        assert count == 100

    def test_cross_instance_same_stem_single_line(self, tmp_registry):
        """4 线程各用独立实例注册同一 stem → JSONL 仅 1 行。"""
        barrier = threading.Barrier(4)
        results = []

        def worker(run_id):
            r = VariantRegistry(tmp_registry)
            r.load()
            barrier.wait()
            results.append(r.try_register("shared_stem", run_id))

        threads = [
            threading.Thread(target=worker, args=(f"run_{i}",))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 恰好一个线程拿到 True
        assert sum(1 for ok in results if ok) == 1

        # 磁盘上只有 1 行
        lines = [l for l in open(tmp_registry, encoding="utf-8").readlines() if l.strip()]
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["stem"] == "shared_stem"

        # 新实例 load 返回唯一 stem 数 = 1
        reg3 = VariantRegistry(tmp_registry)
        assert reg3.load() == 1

    def test_try_register_returns_false_if_exists(self, tmp_registry):
        reg = VariantRegistry(tmp_registry)
        reg.load()
        assert reg.try_register("x", "run_1") is True
        assert reg.try_register("x", "run_2") is False
        assert len(reg) == 1

    def test_load_deduplicates_repeated_lines(self, tmp_registry):
        """即便盘上有重复行，load 返回唯一 stem 数。"""
        with open(tmp_registry, "w", encoding="utf-8") as f:
            f.write('{"stem": "a", "first_seen": "t1", "run_id": "r1"}\n')
            f.write('{"stem": "a", "first_seen": "t2", "run_id": "r2"}\n')
            f.write('{"stem": "b", "first_seen": "t3", "run_id": "r3"}\n')
        reg = VariantRegistry(tmp_registry)
        assert reg.load() == 2  # 唯一 stem 数，非行数
        assert reg.has_stem("a")
        assert reg.has_stem("b")
