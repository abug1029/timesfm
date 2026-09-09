#!/bin/bash
# Phase 10 JD/I/P 完整 backtest (12 作业)
# 用法: bash scripts/phase10_backtest_jd_i_p.sh

set -e
source .praxist-venv/bin/activate
cd D:/FlyBuddy/fm_a

echo "=== Phase 10 JD/I/P 完整 backtest ==="
echo "开始时间: $(date)"
echo ""

# JD 4 个 backtest
echo "--- JD baseline (rsi_state+oi) ---"
python scripts/monthly_backtest.py jd --resume reports/jd_phase10_baseline.jsonl

echo "--- JD-A (rsi_state+calendar) ---"
python scripts/monthly_backtest.py jd --combo "rsi_state,calendar_cyclical" --resume reports/jd_phase10_JDA.jsonl

echo "--- JD-B (rsi_state+oi+reversal_shadow) ---"
python scripts/monthly_backtest.py jd --combo "rsi_state,oi,reversal_shadow" --resume reports/jd_phase10_JDB.jsonl

echo "--- JD-C (calendar+oi) ---"
python scripts/monthly_backtest.py jd --combo "calendar_cyclical,oi" --resume reports/jd_phase10_JDC.jsonl

# I 4 个 backtest
echo "--- I baseline (ha_body) ---"
python scripts/monthly_backtest.py i --resume reports/i_phase10_baseline.jsonl

echo "--- I-A (ha_body+calendar) ---"
python scripts/monthly_backtest.py i --combo "ha_body,calendar_cyclical" --resume reports/i_phase10_IA.jsonl

echo "--- I-B (ha_body+oi) ---"
python scripts/monthly_backtest.py i --combo "ha_body,oi" --resume reports/i_phase10_IB.jsonl

echo "--- I-C (ha_body+bb_squeeze) ---"
python scripts/monthly_backtest.py i --combo "ha_body,bb_squeeze" --resume reports/i_phase10_IC.jsonl

# P 4 个 backtest
echo "--- P baseline (ha_body+reversal_shadow) ---"
python scripts/monthly_backtest.py p --resume reports/p_phase10_baseline.jsonl

echo "--- P-A (ha_body+reversal_shadow+oi) ---"
python scripts/monthly_backtest.py p --combo "ha_body,reversal_shadow,oi" --resume reports/p_phase10_PA.jsonl

echo "--- P-B (ha_body+oi) ---"
python scripts/monthly_backtest.py p --combo "ha_body,oi" --resume reports/p_phase10_PB.jsonl

echo "--- P-C (ha_body+calendar) ---"
python scripts/monthly_backtest.py p --combo "ha_body,calendar_cyclical" --resume reports/p_phase10_PC.jsonl

echo ""
echo "=== 完成 ==="
echo "结束时间: $(date)"
