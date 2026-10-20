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
