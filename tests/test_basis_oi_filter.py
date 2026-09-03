"""basis 历史 OI 过滤单测 (方向 2)
合约自身百分位法: 当 near_oi 或 far_oi < 该合约全周期 P95×5% 时 basis 置 NaN。
"""
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np


class TestBasisOiFilter(unittest.TestCase):
    """合约自身 P95×5% 门槛, 低于则置 NaN"""

    def test_low_oi_history_becomes_nan(self):
        """远月早期 OI=1 (挂单价) → 该段 basis 为 NaN; 后期 OI 正常 → basis 正常"""
        from data.data_store import DataStore
        # 20 bar: 近月 OI 全程 10000
        near_oi = [10000] * 20
        # 远月: 前 10 bar OI=1 (挂单价,无效), 后 10 bar OI=10000
        # 注意: SQL 返回 "ORDER BY dt DESC"(最晚→最早),然后 iloc[::-1] 反转为 ASC(最早→最晚)
        # 所以在 DESC 顺序的 mock 中: 前 10 个(最晚时间)对应后期 OI=10000,
        # 后 10 个(最早时间)对应早期 OI=1; 反转后即为: 早期 OI=1, 后期 OI=10000
        far_oi_desc = [10000] * 10 + [1] * 10
        near_close = [5000.0] * 20
        far_close = [4950.0] * 20
        # 按 dt DESC 构造 mock 返回(匹配 SQL ORDER BY dt DESC)
        dts_desc = pd.date_range("2024-01-01", periods=20, freq="h")[::-1].astype(str).tolist()

        # 构造 JOIN 结果 (get_basis_1h 内 SQL 输出,DESC 顺序)
        join_df = pd.DataFrame({
            "dt": dts_desc,
            "near_close": near_close,
            "far_close": far_close,
            "near_oi": near_oi,
            "far_oi": far_oi_desc,
        })

        store = MagicMock()
        store.conn = MagicMock()

        def _execute(sql, params=None):
            sql = sql if isinstance(sql, str) else str(sql)
            # P95 查询: SELECT open_interest FROM kline_1h WHERE contract_code=?
            if "open_interest" in sql and "FROM kline_1h" in sql and "AVG" not in sql:
                cc = params[0] if params else ""
                if str(cc).upper().startswith("NEAR"):
                    return MagicMock(fetchall=lambda: [(v,) for v in near_oi])
                else:
                    return MagicMock(fetchall=lambda: [(v,) for v in far_oi_desc])
            # 自动识别 AVG 查询
            if "AVG(open_interest)" in sql:
                return MagicMock(fetchall=lambda: [("NEAR01", 10000), ("FAR01", 5000)])
            return MagicMock(fetchall=lambda: [])
        store.conn.execute = _execute
        store.conn.close = lambda: None
        with patch("data.data_store.pd.read_sql_query", return_value=join_df):
            df = DataStore.__new__(DataStore)
            df.conn = store.conn
            df.symbol = "TA"
            # 显式传入,跳过自动识别
            result = df.get_basis_1h(near_contract="NEAR01", far_contract="FAR01", limit=999)
        # 早期 10 bar far_oi=1 < 500 → basis NaN
        self.assertTrue(np.isnan(result["basis"].iloc[0]), "早期低 OI 段 basis 应为 NaN")
        self.assertTrue(np.isnan(result["basis"].iloc[9]), "低 OI 段最后一根应 NaN")
        # 后期 10 bar far_oi=10000 >= 500 → basis 正常
        self.assertFalse(np.isnan(result["basis"].iloc[10]), "后期正常 OI 段 basis 不应 NaN")
        self.assertAlmostEqual(result["basis"].iloc[10], (5000 - 4950) / 4950, places=6)
        # 时间轴完整保留 (不删行)
        self.assertEqual(len(result), 20)

    def test_no_filter_when_all_oi_high(self):
        """OI 全程高 → 无 NaN,basis 全段正常"""
        from data.data_store import DataStore
        near_oi = [10000] * 10
        far_oi = [8000] * 10  # P95=8000 阈值 400,全程 8000 满足
        # 按 dt DESC 构造 mock 返回(匹配 SQL ORDER BY dt DESC)
        dts_desc = pd.date_range("2024-01-01", periods=10, freq="h")[::-1].astype(str).tolist()
        join_df = pd.DataFrame({
            "dt": dts_desc,
            "near_close": [5000.0] * 10, "far_close": [4950.0] * 10,
            "near_oi": near_oi, "far_oi": far_oi,
        })
        store = MagicMock()
        store.conn = MagicMock()

        def _execute(sql, params=None):
            sql = sql if isinstance(sql, str) else str(sql)
            if "open_interest" in sql and "AVG" not in sql:
                cc = params[0] if params else ""
                return MagicMock(fetchall=lambda: [(v,) for v in (
                    near_oi if str(cc).upper().startswith("NEAR") else far_oi)])
            return MagicMock(fetchall=lambda: [])
        store.conn.execute = _execute
        store.conn.close = lambda: None
        with patch("data.data_store.pd.read_sql_query", return_value=join_df):
            df = DataStore.__new__(DataStore)
            df.conn = store.conn
            df.symbol = "TA"
            result = df.get_basis_1h(near_contract="NEAR01", far_contract="FAR01", limit=999)
        self.assertTrue(result["basis"].notna().all(), "全段高 OI 时 basis 不应有 NaN")
        self.assertEqual(len(result), 10)


if __name__ == "__main__":
    unittest.main()
