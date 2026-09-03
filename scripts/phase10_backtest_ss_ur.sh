#!/bin/bash
# Phase 10 SS/UR 完整 backtest (16 作业)
# 用法: bash scripts/phase10_backtest_ss_ur.sh

set -e
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
cd D:/FlyBuddy/fm_a

echo "=== Phase 10 SS/UR 完整 backtest ==="
echo "开始时间: $(date)"
echo ""

# SS 8 个 backtest
echo "--- SS baseline (reversal_shadow) ---"
python scripts/monthly_backtest.py ss --resume reports/ss_phase10_baseline.jsonl

echo "--- SS-1 (ha_body) ---"
python scripts/monthly_backtest.py ss --cov-override ha_body --resume reports/ss_phase10_1.jsonl

echo "--- SS-2 (ha_body+calendar) ---"
python scripts/monthly_backtest.py ss --combo "ha_body,calendar_cyclical" --resume reports/ss_phase10_2.jsonl

echo "--- SS-3 (ha_body+oi) ---"
python scripts/monthly_backtest.py ss --combo "ha_body,oi" --resume reports/ss_phase10_3.jsonl

echo "--- SS-4 (ha_body+reversal_shadow) ---"
python scripts/monthly_backtest.py ss --combo "ha_body,reversal_shadow" --resume reports/ss_phase10_4.jsonl

echo "--- SS-5 (oi+hurst) ---"
python scripts/monthly_backtest.py ss --combo "oi,hurst" --resume reports/ss_phase10_5.jsonl

echo "--- SS-6 (bb_squeeze) ---"
python scripts/monthly_backtest.py ss --cov-override bb_squeeze --resume reports/ss_phase10_6.jsonl

echo "--- SS-7 (vor) ---"
python scripts/monthly_backtest.py ss --cov-override vor --resume reports/ss_phase10_7.jsonl

echo "--- SS-8 (rsi_state+oi) ---"
python scripts/monthly_backtest.py ss --combo "rsi_state,oi" --resume reports/ss_phase10_8.jsonl

# UR 8 个 backtest
echo "--- UR baseline (ao_accel) ---"
python scripts/monthly_backtest.py ur --resume reports/ur_phase10_baseline.jsonl

echo "--- UR-1 (ha_body) ---"
python scripts/monthly_backtest.py ur --cov-override ha_body --resume reports/ur_phase10_1.jsonl

echo "--- UR-2 (ha_body+calendar) ---"
python scripts/monthly_backtest.py ur --combo "ha_body,calendar_cyclical" --resume reports/ur_phase10_2.jsonl

echo "--- UR-3 (calendar+oi) ---"
python scripts/monthly_backtest.py ur --combo "calendar_cyclical,oi" --resume reports/ur_phase10_3.jsonl

echo "--- UR-4 (rsi_state+oi) ---"
python scripts/monthly_backtest.py ur --combo "rsi_state,oi" --resume reports/ur_phase10_4.jsonl

echo "--- UR-5 (hourly_slope+oi) ---"
python scripts/monthly_backtest.py ur --combo "hourly_slope,oi" --resume reports/ur_phase10_5.jsonl

echo "--- UR-6 (bb_squeeze) ---"
python scripts/monthly_backtest.py ur --cov-override bb_squeeze --resume reports/ur_phase10_6.jsonl

echo "--- UR-7 (vor) ---"
python scripts/monthly_backtest.py ur --cov-override vor --resume reports/ur_phase10_7.jsonl

echo "--- UR-8 (reversal_shadow) ---"
python scripts/monthly_backtest.py ur --cov-override reversal_shadow --resume reports/ur_phase10_8.jsonl

echo ""
echo "=== Phase 10 SS/UR 完成 ==="
echo "结束时间: $(date)"
