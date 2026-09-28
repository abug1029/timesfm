"""PR-B4 测试：dir_acc 口径变更（spec W6.5）"""

import pytest
import numpy as np
from cascade.evaluation_metrics import calc_prediction_quality


def test_dir_acc_excludes_zero_move():
    """spec W6.5①: 主口径 dir_acc 应剔除零变动点"""
    # 构造含零变动的样本
    pred = np.array([1.0, 2.0, 3.0])
    real = np.array([1.0, 2.0, 3.0])  # 全部命中
    base = np.array([0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    # 无零变动时，dir_acc = 1.0
    assert result["dir_acc"] == 1.0
    assert result["n_zero_move"] == 0
    assert result["n_dir_active"] == 3


def test_dir_acc_zero_move_excluded_from_denominator():
    """spec W6.5①: 零变动点从分母剔除（非算 miss）"""
    # real deltas: [0, +5, 0] → 2 个零变动，1 个非零
    pred = np.array([0.0, 10.0, 0.0])
    real = np.array([0.0, 5.0, 0.0])  # 零/正/零
    base = np.array([0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    # 零变动点被剔除，只剩 1 个非零点（命中）
    assert result["n_zero_move"] == 2
    assert result["n_dir_active"] == 1
    assert result["dir_acc"] == 1.0, "唯一非零点命中，dir_acc 应为 1.0"

    # full 口径包含零变动（算 miss）
    assert result["dir_acc_full"] == 1/3, "full 口径含 2 个 miss"


def test_dir_acc_full_includes_zero_move():
    """spec W6.5①: dir_acc_full 不剔除任何点"""
    pred = np.array([1.0, 2.0, 3.0, 4.0])
    real = np.array([1.0, 0.0, 3.0, 0.0])  # 2 个零变动
    base = np.array([0.0, 0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    # full 口径：4 个点，2 个零变动（miss），2 个命中
    assert result["n"] == 4
    assert result["n_zero_move"] == 2
    assert result["dir_acc_full"] == 0.5, "full 口径：2/4 = 0.5"

    # 主口径：剔除 2 个零变动，剩 2 个命中
    assert result["n_dir_active"] == 2
    assert result["dir_acc"] == 1.0, "主口径：2/2 = 1.0"


def test_denominator_fields_present():
    """spec W6.5①: 必须同时落盘分母全套字段"""
    pred = np.array([1.0, 2.0, 3.0])
    real = np.array([1.0, 2.0, 3.0])
    base = np.array([0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    # 检查所有必需字段
    required_fields = [
        "dir_acc", "dir_acc_full", "dir_acc_ex_roll",
        "n_dir_total", "n_dir_active", "n_zero_move",
        "n_roll_excluded", "n_zero_ratio", "n_roll_ratio"
    ]
    for field in required_fields:
        assert field in result, f"缺少字段: {field}"


def test_n_dir_total_equals_n():
    """n_dir_total 应等于名义点数 n"""
    pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    real = np.array([1.0, 0.0, 3.0, 0.0, 5.0])
    base = np.array([0.0, 0.0, 0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    assert result["n_dir_total"] == 5
    assert result["n_dir_total"] == result["n"]


def test_n_dir_active_plus_zero_move_equals_total():
    """n_dir_active + n_zero_move 应等于 n_dir_total"""
    pred = np.array([1.0, 2.0, 3.0, 4.0])
    real = np.array([1.0, 0.0, 3.0, 0.0])
    base = np.array([0.0, 0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    assert result["n_dir_active"] + result["n_zero_move"] == result["n_dir_total"]


def test_zero_ratio_calculation():
    """n_zero_ratio 应正确计算"""
    pred = np.array([1.0, 2.0, 3.0, 4.0])
    real = np.array([1.0, 0.0, 3.0, 0.0])  # 2/4 零变动
    base = np.array([0.0, 0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    assert result["n_zero_ratio"] == 0.5, "2/4 = 0.5"


def test_dir_acc_ex_roll_combines_exclusions():
    """dir_acc_ex_roll 应在主口径基础上再剔跨换月"""
    pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    real = np.array([1.0, 0.0, 3.0, 0.0, 5.0])  # 2 个零变动
    base = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    roll_flags = [False, False, True, False, False]  # 1 个跨换月

    result = calc_prediction_quality(pred, real, base, roll_flags=roll_flags)

    # 主口径：剔 2 个零变动，剩 3 个（索引 0, 2, 4），全部命中
    assert result["n_dir_active"] == 3
    assert result["dir_acc"] == 1.0

    # ex_roll：再剔 1 个跨换月（索引 2），剩 2 个（索引 0, 4），全部命中
    assert result["n_roll_excluded"] == 1
    assert result["dir_acc_ex_roll"] == 1.0


def test_all_zero_move():
    """全部零变动时的边界情况"""
    pred = np.array([1.0, 2.0, 3.0])
    real = np.array([0.0, 0.0, 0.0])  # 全零变动
    base = np.array([0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    assert result["n_zero_move"] == 3
    assert result["n_dir_active"] == 0
    # keep_active.any() == False → dir_acc = 0.0
    assert result["dir_acc"] == 0.0


def test_no_zero_move():
    """无零变动时主口径与 full 口径相等"""
    pred = np.array([1.0, 2.0, 3.0])
    real = np.array([1.0, 2.0, -3.0])  # 无零变动，1 个 miss
    base = np.array([0.0, 0.0, 0.0])

    result = calc_prediction_quality(pred, real, base)

    assert result["n_zero_move"] == 0
    assert result["n_dir_active"] == 3
    assert result["dir_acc"] == result["dir_acc_full"]
    assert result["dir_acc"] == 2/3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
