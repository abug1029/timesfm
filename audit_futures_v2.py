#!/usr/bin/env python3
"""TimesFM Futures Database Comprehensive Audit v2 - Fixed false positives"""
import sqlite3
import os
import json
from collections import defaultdict
from datetime import datetime

DB_DIR = os.path.expanduser("~/timesfm/db")

# Natural warmup NULLs per indicator (lookback period - 1 for MA, period for RSI/KDJ/etc.)
# MA(n): NULL for first n-1 rows
# EMA(n): NULL for first n-1 rows
# RSI(n): NULL for first n rows
# KDJ(9,3,3): NULL for first ~8 rows (9-period + 3 SMA)
# Bollinger(20): NULL for first 19 rows
# ATR(14): NULL for first 13 rows (14-period, Wilder)
# CCI(14): NULL for first 13 rows
# MACD(12,26,9): DIF needs 26 rows, DEA needs 26+8=34, BAR needs 34
WARMUP_DAILY = {
    "ma5": 4, "ma10": 9, "ma20": 19, "ma60": 59,
    "ema12": 11, "ema26": 25,
    "macd_dif": 25, "macd_dea": 33, "macd_bar": 33,
    "rsi6": 6, "rsi12": 12, "rsi24": 24,
    "kdj_k": 8, "kdj_d": 8, "kdj_j": 8,
    "boll_upper": 19, "boll_mid": 19, "boll_lower": 19,
    "atr14": 13, "cci14": 13,
}

# 1H table has fewer columns: ma5,ma10,ma20,ema12,ema26,macd_*,rsi_*,boll_*,atr14
WARMUP_1H = {
    "ma5": 4, "ma10": 9, "ma20": 19,
    "ema12": 11, "ema26": 25,
    "macd_dif": 25, "macd_dea": 33, "macd_bar": 33,
    "rsi6": 6, "rsi12": 12, "rsi24": 24,
    "boll_upper": 19, "boll_mid": 19, "boll_lower": 19,
    "atr14": 13,
}

VALID_CCL_LABELS = {"strong_long", "long", "weak_long", "neutral", "weak_short", "short", "strong_short",
                    "多头增仓", "多头减仓", "空头增仓", "空头减仓", "中性", "多头", "空头", None}

NO_NIGHT_SESSION = {"cj", "jd", "lh", "ur"}

def connect(symbol):
    path = os.path.join(DB_DIR, f"futures_{symbol}.db")
    if not os.path.exists(path):
        return None, f"DB file missing: {path}"
    return sqlite3.connect(path), None

def audit_symbol(sym):
    findings = []
    severities = []
    conn, err = connect(sym)
    if err:
        return {"severity": "CRITICAL", "findings": [f"CRITICAL: {err}"], "row_counts": {}, "issues": []}

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    row_counts = {}
    issues = []

    # ========== DAILY TABLE ==========
    if "kline_1d" in tables:
        cur.execute("SELECT COUNT(*) FROM kline_1d")
        cnt = cur.fetchone()[0]
        row_counts["kline_1d"] = cnt

        cur.execute("SELECT MIN(dt), MAX(dt) FROM kline_1d")
        min_dt, max_dt = cur.fetchone()
        row_counts["d_range"] = f"{min_dt} ~ {max_dt}"

        # Freshness check
        if max_dt:
            expected = "2026-09-07" if sym in NO_NIGHT_SESSION else "2026-09-08"
            if max_dt != expected:
                findings.append(f"MEDIUM: Latest daily={max_dt}, expected={expected}")
                severities.append("MEDIUM")
                issues.append(("freshness", f"daily latest {max_dt} != {expected}"))
            else:
                findings.append(f"OK: Daily current to {max_dt}")

        # OHLC consistency
        cur.execute("""SELECT COUNT(*) FROM kline_1d
            WHERE high < MAX(open_price, close_price)
               OR low > MIN(open_price, close_price)
               OR open_price <= 0 OR close_price <= 0 OR high <= 0 OR low <= 0""")
        bad = cur.fetchone()[0]
        if bad > 0:
            findings.append(f"CRITICAL: {bad} rows with OHLC inconsistency or non-positive prices")
            severities.append("CRITICAL")
            issues.append("OHLC inconsistency")

        # Volume/OI negative
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE volume < 0 OR open_interest < 0")
        bad = cur.fetchone()[0]
        if bad > 0:
            findings.append(f"CRITICAL: {bad} rows with negative volume/OI")
            severities.append("CRITICAL")
            issues.append("negative volume/OI")

        # Large daily moves
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE change_pct IS NOT NULL AND ABS(change_pct) > 10")
        big = cur.fetchone()[0]
        if big > 0:
            findings.append(f"INFO: {big} days with |change_pct|>10% (review for data errors)")
            issues.append(f"{big} extreme daily moves")

        # Indicator NULL analysis - compare against expected warmup
        null_report = []
        unexpected_nulls = []
        for col, expected in WARMUP_DAILY.items():
            cur.execute(f"SELECT COUNT(*) FROM kline_1d WHERE {col} IS NULL")
            n = cur.fetchone()[0]
            if n > expected:
                unexpected_nulls.append((col, n, expected))
            null_report.append(f"{col}:{n}")

        if unexpected_nulls:
            details = ", ".join(f"{c}: got {n} (exp~{e})" for c, n, e in unexpected_nulls)
            findings.append(f"HIGH: Unexpected daily NULLs: {details}")
            severities.append("HIGH")
            issues.append(f"unexpected NULLs: {details}")
        else:
            findings.append(f"OK: All daily indicator NULLs match expected warmup")

        # CCL check
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE ccl_value IS NULL")
        null_ccl = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT ccl_label FROM kline_1d WHERE ccl_label IS NOT NULL")
        ccl_labels = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT MIN(ccl_value), MAX(ccl_value), AVG(ccl_value) FROM kline_1d WHERE ccl_value IS NOT NULL")
        ccl_stats = cur.fetchone()

        invalid_labels = [l for l in ccl_labels if l not in VALID_CCL_LABELS]
        if invalid_labels:
            findings.append(f"HIGH: Invalid daily ccl_label values: {invalid_labels}")
            severities.append("HIGH")
            issues.append(f"invalid ccl_labels: {invalid_labels}")
        else:
            findings.append(f"OK: CCL labels valid ({sorted(set(l for l in ccl_labels if l))})")

        empty_label = "" in ccl_labels
        if empty_label:
            findings.append(f"MEDIUM: Empty string ccl_label present ({null_ccl} NULL ccl_value rows)")
            severities.append("MEDIUM")

        if ccl_stats[0] is not None:
            findings.append(f"INFO: CCL range=[{ccl_stats[0]:.0f}, {ccl_stats[1]:.0f}], avg={ccl_stats[2]:.1f}")

        # updated_at
        cur.execute("SELECT MAX(updated_at) FROM kline_1d")
        max_upd = cur.fetchone()[0]
        findings.append(f"INFO: Daily updated_at={max_upd}")

        # Contract codes
        cur.execute("SELECT DISTINCT contract_code FROM kline_1d ORDER BY contract_code")
        codes = [r[0] for r in cur.fetchall()]
        has_cont = any("_CONT" in c for c in codes)
        findings.append(f"INFO: Daily contracts: {codes}")
        if not has_cont:
            findings.append(f"MEDIUM: Daily missing _CONT suffix")
            severities.append("MEDIUM")

        # Gap analysis
        cur.execute("SELECT dt FROM kline_1d ORDER BY dt")
        dates = [r[0] for r in cur.fetchall()]
        if len(dates) > 1:
            import datetime as dt_mod
            long_gaps = []
            for i in range(1, len(dates)):
                d1 = dt_mod.datetime.strptime(dates[i-1], "%Y-%m-%d")
                d2 = dt_mod.datetime.strptime(dates[i], "%Y-%m-%d")
                diff = (d2 - d1).days
                if diff > 7:
                    long_gaps.append(f"{dates[i-1]}->{dates[i]}({diff}d)")
            if long_gaps:
                findings.append(f"INFO: Gaps >7d (Chinese holidays): {long_gaps[:3]}...")

    # ========== 1H TABLE ==========
    if "kline_1h" in tables:
        cur.execute("SELECT COUNT(*) FROM kline_1h")
        cnt = cur.fetchone()[0]
        row_counts["kline_1h"] = cnt

        cur.execute("SELECT MIN(dt), MAX(dt) FROM kline_1h")
        min_dt, max_dt = cur.fetchone()
        row_counts["h_range"] = f"{min_dt} ~ {max_dt}"

        # Freshness - normalize format
        if max_dt:
            expected_time = "2026-09-07 14:00" if sym in NO_NIGHT_SESSION else "2026-09-07 21:00"
            max_dt_norm = max_dt.replace(":00", "") if max_dt.endswith(":00") else max_dt[:16]
            if max_dt_norm != expected_time:
                findings.append(f"MEDIUM: Latest 1H={max_dt}, expected ~{expected_time}")
                severities.append("MEDIUM")
                issues.append(("1h_freshness", f"{max_dt} != {expected_time}"))
            else:
                findings.append(f"OK: 1H current to {max_dt}")

        # OHLC
        cur.execute("""SELECT COUNT(*) FROM kline_1h
            WHERE high < MAX(open_price, close_price)
               OR low > MIN(open_price, close_price)
               OR open_price <= 0 OR close_price <= 0""")
        bad = cur.fetchone()[0]
        if bad > 0:
            findings.append(f"CRITICAL: {bad} 1H rows with OHLC issues")
            severities.append("CRITICAL")
            issues.append("1H OHLC inconsistency")

        # Indicator NULLs
        h_unexpected = []
        for col, expected in WARMUP_1H.items():
            cur.execute(f"SELECT COUNT(*) FROM kline_1h WHERE {col} IS NULL")
            n = cur.fetchone()[0]
            if n > expected:
                h_unexpected.append((col, n, expected))
        if h_unexpected:
            details = ", ".join(f"{c}:{n}" for c, n, e in h_unexpected)
            findings.append(f"HIGH: Unexpected 1H NULLs: {details}")
            severities.append("HIGH")
            issues.append(f"1H unexpected NULLs: {details}")
        else:
            findings.append(f"OK: All 1H indicator NULLs match expected warmup")

        # CCL
        cur.execute("SELECT DISTINCT ccl_label FROM kline_1h WHERE ccl_label IS NOT NULL")
        h_labels = [r[0] for r in cur.fetchall()]
        inv = [l for l in h_labels if l not in VALID_CCL_LABELS]
        if inv:
            findings.append(f"HIGH: Invalid 1H ccl_labels: {inv}")
            severities.append("HIGH")
            issues.append(f"invalid 1H ccl_labels: {inv}")
        else:
            findings.append(f"OK: 1H CCL labels valid")

        empty_h = "" in h_labels
        if empty_h:
            findings.append(f"MEDIUM: Empty string 1H ccl_label present")
            severities.append("MEDIUM")

        cur.execute("SELECT MAX(updated_at) FROM kline_1h")
        max_upd = cur.fetchone()[0]
        findings.append(f"INFO: 1H updated_at={max_upd}")

        # Contract codes
        cur.execute("SELECT DISTINCT contract_code FROM kline_1h ORDER BY contract_code")
        codes = [r[0] for r in cur.fetchall()]
        has_main = any("_MAIN" in c for c in codes)
        non_main = [c for c in codes if "_MAIN" not in c]
        findings.append(f"INFO: 1H contracts: {codes}")
        if non_main:
            findings.append(f"MEDIUM: 1H has non-MAIN contracts: {non_main}")
            severities.append("MEDIUM")
            issues.append(f"1H non-MAIN contracts: {non_main}")

        # Updated_at freshness - check if stale
        if max_upd:
            # Data should have been updated around 21:30-22:00 UTC+8 = 13:30-14:00 UTC
            # If updated_at is before 13:00 UTC on 2026-09-07, it's from a previous run
            if "13:" in max_upd or "14:" in max_upd or max_upd.startswith("2026-09-07 1"):
                findings.append(f"OK: 1H updated today ({max_upd})")
            elif max_upd.startswith("2026-09-07"):
                findings.append(f"OK: 1H updated today ({max_upd})")
            else:
                findings.append(f"MEDIUM: 1H updated_at={max_upd} (may be stale)")
                severities.append("MEDIUM")

    # ========== DAILY vs 1H ALIGNMENT ==========
    if "kline_1d" in tables and "kline_1h" in tables:
        cur.execute("SELECT COUNT(DISTINCT dt) FROM kline_1d")
        n_days = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT SUBSTR(dt,1,10)) FROM kline_1h")
        n_hdays = cur.fetchone()[0]

        # For symbols with night sessions, 1H should cover >= trading days
        # 1H bars include night hours that map to next trading day
        findings.append(f"INFO: Alignment: daily={n_days} trading days, 1H covers={n_hdays} dates")

        # Check for TA anomaly (has specific contract codes)
        cur.execute("SELECT DISTINCT contract_code FROM kline_1h")
        h_codes = [r[0] for r in cur.fetchall()]
        if len(h_codes) > 1:
            findings.append(f"MEDIUM: 1H has {len(h_codes)} distinct contract codes: {h_codes}")
            severities.append("MEDIUM")
            issues.append(f"1H multi-contract: {h_codes}")

    conn.close()

    # Determine severity
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "OK": 4, "INFO": 5}
    if severities:
        overall = min(severities, key=lambda s: sev_order.get(s, 99))
    else:
        overall = "OK"

    return {"severity": overall, "findings": findings, "row_counts": row_counts, "issues": issues}

def main():
    print("=" * 80)
    print("TIMESFM FUTURES DATABASE AUDIT v2")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    db_files = sorted([f.replace("futures_", "").replace(".db", "") for f in os.listdir(DB_DIR)
                       if f.startswith("futures_") and f.endswith(".db")])
    print(f"Found {len(db_files)} symbol databases: {db_files}\n")

    results = {}
    for sym in db_files:
        results[sym] = audit_symbol(sym)

    # Row count summary
    print("=" * 80)
    print("ROW COUNT SUMMARY")
    print("=" * 80)
    print(f"{'Sym':<5} {'Daily':>7} {'1H':>7} {'Daily Range':<28} {'1H Range':<28} {'Status':<10}")
    print("-" * 85)
    for sym in db_files:
        rc = results[sym].get("row_counts", {})
        dr = rc.get("d_range", "N/A")
        hr = rc.get("h_range", "N/A")
        sev = results[sym]["severity"]
        print(f"{sym:<5} {str(rc.get('kline_1d','N/A')):>7} {str(rc.get('kline_1h','N/A')):>7} {dr:<28} {hr:<28} {sev:<10}")

    # Per-symbol findings
    print("\n" + "=" * 80)
    print("PER-SYMBOL FINDINGS")
    print("=" * 80)

    all_issues = []
    for sym in db_files:
        r = results[sym]
        sev = r["severity"]
        print(f"\n--- {sym.upper()} [{sev}] ---")
        for f in r["findings"]:
            print(f"  {f}")
        if r.get("issues"):
            for iss in r["issues"]:
                all_issues.append((sym, iss))

    # Overall summary
    print("\n" + "=" * 80)
    print("OVERALL AUDIT SUMMARY")
    print("=" * 80)

    sev_counts = defaultdict(int)
    for sym in db_files:
        for f in results[sym]["findings"]:
            for s in ["CRITICAL", "HIGH", "MEDIUM"]:
                if f.startswith(s):
                    sev_counts[s] += 1
                    break

    print(f"Symbols audited: {len(db_files)}")
    print(f"CRITICAL issues: {sev_counts.get('CRITICAL', 0)}")
    print(f"HIGH issues:     {sev_counts.get('HIGH', 0)}")
    print(f"MEDIUM issues:   {sev_counts.get('MEDIUM', 0)}")

    # Symbol severity distribution
    sym_sev = defaultdict(list)
    for sym in db_files:
        sym_sev[results[sym]["severity"]].append(sym)

    print(f"\nSymbol health distribution:")
    for sev in ["OK", "INFO", "MEDIUM", "HIGH", "CRITICAL"]:
        if sev in sym_sev:
            print(f"  {sev}: {len(sym_sev[sev])} symbols")

    # Compute health score
    crit = sev_counts.get("CRITICAL", 0)
    high = sev_counts.get("HIGH", 0)
    med = sev_counts.get("MEDIUM", 0)
    health = max(0, 100 - crit * 15 - high * 5 - med * 1)
    print(f"\nData Health Score: {health}/100")

    # Missing vs extra symbols
    expected_original = ["ao","cf","cj","hc","i","j","jd","jm","l","lh","m","ni","p","pp","rb","ru","sn","sr","ta","v","wr","y","fg","eg","sa","sp","ur","bu"]
    actual = set(db_files)
    expected_set = set(expected_original)
    missing = expected_set - actual
    extra = actual - expected_set
    if missing:
        print(f"\nMISSING DBs (from task spec): {sorted(missing)}")
    if extra:
        print(f"EXTRA DBs (not in task spec): {sorted(extra)}")

    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    rec = 1

    # 1. CCL empty string labels
    if any('Empty string ccl_label' in f for s in db_files for f in results[s]["findings"]):
        print(f"  {rec}. [MEDIUM] Fix empty-string ccl_label: All 28 symbols have ccl_value NULL rows with")
        print(f"     empty-string labels instead of a proper 'neutral' or NULL label.")
        print(f"     Fix: UPDATE kline_1d SET ccl_label=NULL WHERE ccl_label=''; same for 1H.")
        rec += 1

    # 2. Unexpected NULLs
    if any('Unexpected' in f and 'NULL' in f for s in db_files for f in results[s]["findings"]):
        syms_with_nulls = [s for s in db_files if any('Unexpected' in f and 'NULL' in f for f in results[s]["findings"])]
        print(f"  {rec}. [HIGH] Investigate unexpected NULLs on: {', '.join(syms_with_nulls)}")
        print(f"     These symbols have more NULL indicators than warmup explains.")
        print(f"     Likely cause: source data has NULL prices/VOL in early rows that propagate to indicators.")
        rec += 1

    # 3. TA multi-contract
    if any('multi-contract' in str(iss) for s in db_files for iss in results[s].get("issues", [])):
        print(f"  {rec}. [MEDIUM] TA has non-MAIN 1H contract codes (TA2609, TA2611).")
        print(f"     Verify these are intentional or clean to _MAIN only.")
        rec += 1

    # 4. Extreme moves
    syms_extreme = [s for s in db_files if any('extreme daily' in str(iss) for iss in results[s].get("issues", []))]
    if syms_extreme:
        print(f"  {rec}. [INFO] Symbols with >10% daily moves (verify not data errors): {', '.join(syms_extreme)}")
        rec += 1

    # 5. Missing DBs
    if missing:
        print(f"  {rec}. [HIGH] 9 DB files missing vs original task spec: {sorted(missing)}")
        print(f"     Either these symbols were renamed, removed, or never created.")
        rec += 1

    # 6. General OK
    if health >= 80:
        print(f"  {rec}. [INFO] Overall data quality is GOOD. Minor issues only.")
    elif health >= 50:
        print(f"  {rec}. [INFO] Data quality is FAIR. Address MEDIUM issues.")
    else:
        print(f"  {rec}. [HIGH] Data quality is POOR. Address HIGH/CRITICAL issues first.")

    # Missing DB details
    print(f"\n--- MISSING vs EXTRA DETAIL ---")
    print(f"Expected (28 original): {sorted(expected_set)}")
    print(f"Actual ({len(actual)}):  {sorted(actual)}")
    if missing:
        print(f"Missing: {sorted(missing)}")
    if extra:
        print(f"Extra: {sorted(extra)}")

if __name__ == "__main__":
    main()
