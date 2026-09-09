"""全量重算 cf/sr/jm 日线指标 - 直接替换整表"""
import sqlite3
import os
import sys
import pandas as pd

os.chdir(os.path.expanduser("~/timesfm"))
sys.path.insert(0, ".")
from data.indicator_calculator import IndicatorCalculator

calc = IndicatorCalculator()

for sym in ["cf", "sr", "jm"]:
    db_path = f"db/futures_{sym}.db"
    conn = sqlite3.connect(db_path)

    # 读取全部日线
    df = pd.read_sql_query("SELECT * FROM kline_1d ORDER BY dt", conn)
    print(f"=== {sym}: {len(df)} rows ===")

    # 检查修复前状态
    null_before = df["ma20"].isna().sum()
    null_ma5 = df["ma5"].isna().sum()
    print(f"  修复前: ma5 NULL={null_ma5}, ma20 NULL={null_before}")

    # 重算指标（在全量数据上）
    df_calc = df.copy()
    df_calc = df_calc.rename(columns={"open_price": "open", "close_price": "close"})
    df_calc = calc.calculate_all(df_calc)
    df_calc = df_calc.rename(columns={"open": "open_price", "close": "close_price"})

    null_after = df_calc["ma20"].isna().sum()
    null_ma5_after = df_calc["ma5"].isna().sum()
    print(f"  重算后: ma5 NULL={null_ma5_after}, ma20 NULL={null_after}")

    # 获取表结构
    cols_info = conn.execute("PRAGMA table_info(kline_1d)").fetchall()
    col_names = [c[1] for c in cols_info]

    # 逐行更新指标列
    indicator_cols = [c for c in col_names if c not in ("dt", "contract_code", "updated_at")]
    set_clause = ", ".join([f"{c} = ?" for c in indicator_cols])

    def to_native(val):
        """Convert any value to sqlite3-compatible native Python type."""
        if val is None:
            return None
        if isinstance(val, float) and pd.isna(val):
            return None
        if hasattr(val, 'item'):
            v = val.item()
            if isinstance(v, float) and pd.isna(v):
                return None
            return v
        if isinstance(val, (int, float, str)):
            return val
        # Fallback: try converting to float
        try:
            return float(val)
        except (TypeError, ValueError):
            return str(val) if val is not None else None

    rows_updated = 0
    for _, row in df_calc.iterrows():
        values = [to_native(row.get(c)) for c in indicator_cols]
        values.extend([row["dt"], row["contract_code"]])
        conn.execute(
            f"UPDATE kline_1d SET {set_clause} WHERE dt = ? AND contract_code = ?",
            values,
        )
        rows_updated += 1

    conn.commit()

    # 验证
    verify = conn.execute("SELECT COUNT(*) FROM kline_1d WHERE ma20 IS NULL").fetchone()[0]
    verify_ma5 = conn.execute("SELECT COUNT(*) FROM kline_1d WHERE ma5 IS NULL").fetchone()[0]
    print(f"  DB验证: ma5 NULL={verify_ma5}, ma20 NULL={verify}, updated={rows_updated} rows")
    print(f"  ✅ {sym} 完成")

    conn.close()
    print()

print("全部重算完成!")
