import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import monthly_backtest as mb


def test_run_symbol_backtest_closes_store_if_read_raises(monkeypatch):
    closed = []

    class Boom:
        def __init__(self, symbol):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            closed.append(True)
            return False
        def close(self):
            closed.append("close")
        def get_main_contract_1h(self, limit=None):
            raise RuntimeError("boom")
        def get_main_continuous(self, limit=None):
            raise AssertionError("should not be reached")

    monkeypatch.setattr(mb, "DataStore", Boom)
    try:
        mb.run_symbol_backtest("ss", None, None)
        raise AssertionError("should raise")
    except RuntimeError as e:
        assert "boom" in str(e)
    assert True in closed
