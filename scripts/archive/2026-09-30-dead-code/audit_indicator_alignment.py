#!/usr/bin/env python3
"""指标新鲜度对齐审计 (2026-09-01, Linux 迁移后)

对每个 futures_*.db 检查:
  1. kline_1d / main_continuous_1d / kline_1h 三表最新 dt
  2. 每个指标列在 kline_1d / main_continuous_1d 上的最新非空 dt 是否与该表最新 dt 对齐
  3. xreg_factors 每个 factor_name 的最新 dt 是否与 kline_1d 最新 dt 对齐
损坏库 (ao/ur) 单独捕获, 不阻断整体审计。
"""
import sqlite3, glob, os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")

IND_1D = ['ma5', 'ma10', 'ma20', 'ma60', 'ema12', 'ema26', 'macd_dif', 'macd_dea', 'macd_bar',
          'rsi6', 'rsi12', 'rsi24', 'kdj_k', 'kdj_d', 'kdj_j', 'boll_upper', 'boll_mid',
          'boll_lower', 'atr14', 'cci14', 'oi_change', 'oi_trend_5d', 'oi_price_corr',
          'volume_oi_ratio', 'oi_signal', 'ccl_value', 'ccl_label']
IND_1H = ['ma5', 'ma10', 'ma20', 'ema12', 'ema26', 'macd_dif', 'macd_dea', 'macd_bar',
          'rsi6', 'rsi12', 'rwi24', 'boll_upper', 'boll_mid', 'boll_lower', 'atr14',
          'oi_change', 'volume_oi_ratio', 'oi_signal', 'ccl_value', 'rsi24']

