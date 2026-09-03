import numpy as np
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from cascade.evaluation_metrics import calc_vol_scaled_mae

def test_vol_scaled_mae_basic():
    # 误差 10 点, ATR 5 点 -> 缩放误差 2.0
    pred = np.array([100.0])
    actual = np.array([110.0])
    atr = np.array([5.0])
    assert calc_vol_scaled_mae(pred, actual, atr) == 2.0

def test_vol_scaled_mae_atr_zero_safe():
    # ATR=0 不应除零, 返回 inf 或大数
    pred = np.array([100.0])
    actual = np.array([110.0])
    atr = np.array([0.0])
    result = calc_vol_scaled_mae(pred, actual, atr)
    assert np.isinf(result) or result > 1e6

def test_vol_scaled_mae_multi_point():
    pred = np.array([100.0, 200.0])
    actual = np.array([110.0, 190.0])  # 误差 10 each
    atr = np.array([5.0, 10.0])        # 缩放 2.0, 1.0
    assert calc_vol_scaled_mae(pred, actual, atr) == 1.5  # mean(2.0, 1.0)
