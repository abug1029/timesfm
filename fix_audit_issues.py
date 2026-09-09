"""修复审计发现的问题"""
import sqlite3
import os
import sys
import pandas as pd

os.chdir(os.path.expanduser("~/timesfm"))

# === Fix 1: 清空 ta 的过期合约数据 ===
print("=" * 60)
print("Fix 1: 清理 TA 过期合约数据")
conn = sqlite3.connect("db/futures_ta.db")
for code in ["TA2609", "TA2611"]:
    cur = conn.execute(
        "DELETE FROM kline_1h WHERE contract_code = ?", (code,)
    )
    print(f"  DELETE kline_1h WHERE contract_code='{code}': {cur.rowcount} rows")
conn.commit()
conn.close()
print("  ✅ TA 清理完成")

# === Fix 2: 全品种修复 ccl_label 空字符串 ===
print()
print("=" * 60)
print("Fix 2: 修复 ccl_label 空字符串 → NULL")
total_fixed = 0
for fn in sorted(os.listdir("db")):
    if not fn.startswith("futures_") or not fn.endswith(".db"):
        continue
    sym = fn.replace("futures_", "").replace(".db", "")
    conn = sqlite3.connect(f"db/{fn}")
    for table in ["kline_1d", "kline_1h"]:
        try:
            cur = conn.execute(
                f"UPDATE {table} SET ccl_label = NULL WHERE ccl_label = ''"
            )
            if cur.rowcount > 0:
                total_fixed += cur.rowcount
                print(f"  {sym}/{table}: {cur.rowcount} rows fixed")
        except sqlite3.OperationalError:
            pass  # table might not have ccl_label
    conn.commit()
    conn.close()
print(f"  ✅ 共修复 {total_fixed} 行")

# === Fix 3: cf/sr/jm 日线指标重算 ===
print()
print("=" * 60)
print("Fix 3: 重算 cf/sr/jm 日线指标")
sys.path.insert(0, ".")
from data.indicator_calculator import IndicatorCalculator

calc = IndicatorCalculator()
for sym in ["cf", "sr", "jm"]:
    conn = sqlite3.connect(f"db/futures_{sym}.db")
    # 读取全部日线数据
    df = pd.read_sql_query(
        "SELECT * FROM kline_1d ORDER BY dt", conn
    )
    # 检查有多少 NULL ma20
    null_before = df["ma20"].isna().sum()

    # 重算指标
    df_calc = df.rename(columns={"open_price": "open", "close_price": "close"})
    df_calc = calc.calculate_all(df_calc)
    df_calc = df_calc.rename(columns={"open": "open_price", "close": "close_price"})

    null_after = df_calc["ma20"].isna().sum()
    print(f"  {sym}: ma20 NULL {null_before} → {null_after}")

    # 写回 DB
    cols = [desc[0] for desc in conn.execute("PRAGMA table_info(kline_1d)").fetchall()]
    for _, row in df_calc.iterrows():
        updates = []
        values = []
        for col in cols:
            if col in ("dt", "contract_code"):
                continue
            if col in row.index:
                val = row[col]
                if pd.isna(val):
                    updates.append(f"{col} = NULL")
                else:
                    updates.append(f"{col} = ?")
                    values.append(val)
        if updates:
            values.extend([row["dt"], row["contract_code"]])
            conn.execute(
                f"UPDATE kline_1d SET {', '.join(updates)} WHERE dt = ? AND contract_code = ?",
                values,
            )
    conn.commit()
    conn.close()
    print(f"  ✅ {sym} 指标重算完成")

print()
print("=" * 60)
print("全部修复完成!")
