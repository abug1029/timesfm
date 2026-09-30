"""
Test how far back TqSdk can provide 1H kline data for futures.
Tests multiple symbols with data_length=10000 (TqSdk max).
"""
import os
import sys
import time
from datetime import datetime

import pandas as pd
from tqsdk import TqApi, TqAuth


def ns_to_datetime(ts):
    """Convert nanosecond timestamp to datetime."""
    if pd.isna(ts) or ts == 0:
        return None
    if ts > 1e18:  # nanoseconds
        return datetime.fromtimestamp(ts / 1e9)
    elif ts > 1e15:  # microseconds
        return datetime.fromtimestamp(ts / 1e6)
    else:  # seconds
        return datetime.fromtimestamp(ts)


def test_symbol(api, symbol, duration_sec, data_length, label=None):
    """Test 1H kline data for a symbol and print results."""
    tag = label or symbol
    try:
        klines = api.get_kline_serial(symbol, duration_sec, data_length=data_length)
        # Wait for data to arrive
        deadline = api._loop.time() + 30
        api.wait_update(deadline=deadline)

        df = pd.DataFrame(klines)
        if df.empty:
            print(f"  [{tag}] No data returned")
            return None

        # Filter out rows with no valid datetime
        valid = df[df['datetime'].notna() & (df['datetime'] > 0)]
        if valid.empty:
            print(f"  [{tag}] No valid datetime rows")
            return None

        earliest_ts = valid['datetime'].min()
        latest_ts = valid['datetime'].max()
        earliest_dt = ns_to_datetime(earliest_ts)
        latest_dt = ns_to_datetime(latest_ts)

        print(f"  [{tag}]")
        print(f"    Records: {len(valid)}")
        print(f"    Earliest: {earliest_dt} (ts={earliest_ts})")
        print(f"    Latest:   {latest_dt} (ts={latest_ts})")
        if earliest_dt and latest_dt:
            span_days = (latest_dt - earliest_dt).days
            print(f"    Span: ~{span_days} days ({span_days/365:.1f} years)")

        return valid
    except Exception as e:
        print(f"  [{tag}] ERROR: {e}")
        return None


def main():
    account = os.environ.get("TQSDK_ACCOUNT")
    password = os.environ.get("TQSDK_PASSWORD")
    if not account or not password:
        print("ERROR: TQSDK_ACCOUNT and TQSDK_PASSWORD must be set")
        sys.exit(1)

    print(f"TqSdk version: {__import__('tqsdk').__version__}")
    print(f"Account: {account[:4]}***")
    print()

    api = TqApi(auth=TqAuth(account, password))

    # ============================================================
    # Test 1: Continuous main contracts with 1H (3600s), max length
    # ============================================================
    print("=" * 60)
    print("TEST 1: Continuous main contracts (KQ.m@) — 1H klines, data_length=10000")
    print("=" * 60)

    symbols_1h = [
        ("KQ.m@CZCE.CF", "CF (cotton, CZCE)"),
        ("KQ.m@SHFE.rb", "RB (rebar, SHFE)"),
        ("KQ.m@DCE.i",   "I  (iron ore, DCE)"),
        ("KQ.m@CZCE.SR", "SR (sugar, CZCE)"),
    ]

    for sym, label in symbols_1h:
        test_symbol(api, sym, 3600, 10000, label)
        time.sleep(1)  # small pause between requests

    # ============================================================
    # Test 2: Specific contracts — compare with continuous
    # ============================================================
    print()
    print("=" * 60)
    print("TEST 2: Specific contracts vs continuous — 1H klines, data_length=10000")
    print("=" * 60)

    # Try specific contracts (some may have expired but TqSdk may still have history)
    specific_tests = [
        # CF specific contracts
        ("KQ.m@CZCE.CF", "CF continuous"),
        ("CZCE.CF501",   "CF501 (Jan 2025)"),
        ("CZCE.CF505",   "CF505 (May 2025)"),
        ("CZCE.CF509",   "CF509 (Sep 2025)"),
        # RB specific contracts
        ("KQ.m@SHFE.rb", "rb continuous"),
        ("SHFE.rb2410",  "rb2410 (Oct 2024)"),
        ("SHFE.rb2501",  "rb2501 (Jan 2025)"),
        ("SHFE.rb2510",  "rb2510 (Oct 2025)"),
    ]

    for sym, label in specific_tests:
        test_symbol(api, sym, 3600, 10000, label)
        time.sleep(1)

    # ============================================================
    # Test 3: Try even older specific contracts
    # ============================================================
    print()
    print("=" * 60)
    print("TEST 3: Older specific contracts — 1H klines")
    print("=" * 60)

    old_tests = [
        ("CZCE.CF301",   "CF301 (Jan 2023)"),
        ("CZCE.CF401",   "CF401 (Jan 2024)"),
        ("SHFE.rb2301",  "rb2301 (Jan 2023)"),
        ("SHFE.rb2401",  "rb2401 (Jan 2024)"),
        ("DCE.i2301",    "i2301 (Jan 2023)"),
        ("DCE.i2401",    "i2401 (Jan 2024)"),
    ]

    for sym, label in old_tests:
        test_symbol(api, sym, 3600, 10000, label)
        time.sleep(1)

    # ============================================================
    # Test 4: Daily klines for comparison — how far back?
    # ============================================================
    print()
    print("=" * 60)
    print("TEST 4: Daily klines (86400s) for comparison, data_length=10000")
    print("=" * 60)

    daily_tests = [
        ("KQ.m@CZCE.CF", "CF daily"),
        ("KQ.m@SHFE.rb", "rb daily"),
    ]

    for sym, label in daily_tests:
        test_symbol(api, sym, 86400, 10000, label)
        time.sleep(1)

    # ============================================================
    # Test 5: 15min klines — how far back?
    # ============================================================
    print()
    print("=" * 60)
    print("TEST 5: 15min klines (900s) for comparison, data_length=10000")
    print("=" * 60)

    min15_tests = [
        ("KQ.m@CZCE.CF", "CF 15min"),
        ("KQ.m@SHFE.rb", "rb 15min"),
    ]

    for sym, label in min15_tests:
        test_symbol(api, sym, 900, 10000, label)
        time.sleep(1)

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)

    api.close()


if __name__ == "__main__":
    main()
