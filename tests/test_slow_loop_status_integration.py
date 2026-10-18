# tests/test_slow_loop_status_integration.py
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_slow_loop_writes_verdicted_status():
    """慢环 verdict 落盘时写入 status (verdicted) — 至少一个真实断言"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        sf = f.name
    try:
        write_proposal_status(sf, "test_prop", 1, "verdicted", "run1",
                              variant_id="m_momentum_abc123")
        with open(sf) as f:
            r = json.loads(f.readline())
            assert r["status"] == "verdicted"
            assert r["variant_id"] == "m_momentum_abc123"
            assert r["proposal_id"] == "test_prop"
            assert r["version"] == 1
    finally:
        if os.path.exists(sf): os.remove(sf)
        lf = sf + ".lock"
        if os.path.exists(lf): os.remove(lf)
