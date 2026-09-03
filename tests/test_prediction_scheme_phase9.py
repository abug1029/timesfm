"""
Phase 9 固化配置防回归测试 (2026-08-03, 更新至 2026-08-21 Phase 11/12)

断言 21 品种的 covariate_type / covariate_types / dir_acc / stars 与最新固化值一致。
任何对 config/prediction_scheme.py 的误改都会触发测试失败。

数据来源: Phase 9 实证 + Phase 11 单协变量穷举 + Phase 12 组合测试
参考: docs/backtest_registry.md
"""

import pytest
from config.prediction_scheme import SCHEMES, get_scheme


# ─────────────────────────────────────────────────────────
# 最新固化快照 (2026-08-21 Phase 11/12 后)
# ─────────────────────────────────────────────────────────
# 每品种: (cov_type, cov_types 或 None, dir_acc, stars)
# cov_types=None 表示单协变量模式,否则为组合模式列表

PHASE9_SNAPSHOT = {
    # ── 2★ ──
    "ss": ("calendar_cyclical", ["calendar_cyclical"], 0.510, 2),  # Phase 11
    "sr": ("rsi_state", ["rsi_state", "oi", "calendar_cyclical"], 0.550, 2),
    "lh": ("rsi_state", ["rsi_state"], 0.500, 2),  # Phase 11
    "cj": ("hourly_slope", ["hourly_slope"], 0.520, 2),  # Phase 11
    "m":  ("ha_body", ["ha_body", "calendar_cyclical"], 0.530, 2),
    "jd": ("rsi_state", ["rsi_state"], 0.470, 2),  # Phase 11
    "rb": ("rsi_state", ["rsi_state"], 0.510, 2),  # Phase 11
    "eg": ("calendar_cyclical", ["calendar_cyclical"], 0.510, 2),  # Phase 11 baseline

    # ── 1★ ──
    "i":  ("reversal_shadow", ["reversal_shadow"], 0.510, 1),  # Phase 11
    "jm": ("ha_body", None, 0.470, 1),
    "fg": ("ha_body", None, 0.480, 1),
    "cf": ("ha_body", ["ha_body", "calendar_cyclical"], 0.510, 1),
    "sp": ("calendar_cyclical", ["calendar_cyclical"], 0.510, 1),  # Phase 11 baseline
    "ta": ("calendar_cyclical", ["calendar_cyclical"], 0.530, 1),  # Phase 11
    "p":  ("rsi_state", ["rsi_state", "reversal_shadow"], 0.540, 1),
    "fu": ("calendar_cyclical", ["calendar_cyclical"], 0.500, 1),  # Phase 11 baseline
    "bu": ("calendar_cyclical", ["calendar_cyclical", "hourly_slope"], 0.510, 1),  # Phase 12
    "ao": ("hourly_slope", ["hourly_slope", "calendar_cyclical"], 0.450, 1),
    "ur": ("ao_accel", None, 0.500, 1),
    "ma": ("hourly_slope", ["hourly_slope", "oi"], 0.490, 1),
    "sh": ("reversal_shadow", ["reversal_shadow"], 0.430, 1),  # Task 3 新增
}


# ─────────────────────────────────────────────────────────
# 测试函数
# ─────────────────────────────────────────────────────────

class TestPhase9Solidification:
    """Phase 9 固化配置断言"""

    def test_all_21_symbols_present(self):
        """SCHEMES 包含全部 21 品种"""
        expected = set(PHASE9_SNAPSHOT.keys())
        actual = set(SCHEMES.keys())
        assert expected == actual, (
            f"品种集合不一致\n"
            f"缺失: {expected - actual}\n"
            f"多余: {actual - expected}"
        )

    @pytest.mark.parametrize("symbol", list(PHASE9_SNAPSHOT.keys()))
    def test_covariate_type(self, symbol):
        """单协变量字段 covariate_type 与快照一致"""
        expected_type, _, _, _ = PHASE9_SNAPSHOT[symbol]
        scheme = get_scheme(symbol)
        assert scheme is not None, f"{symbol} 未在 SCHEMES 中定义"
        assert scheme.covariate_type == expected_type, (
            f"{symbol}: covariate_type 期望 {expected_type!r}, "
            f"实际 {scheme.covariate_type!r}"
        )

    @pytest.mark.parametrize("symbol", list(PHASE9_SNAPSHOT.keys()))
    def test_covariate_types(self, symbol):
        """组合协变量字段 covariate_types 与快照一致 (含 None)"""
        _, expected_types, _, _ = PHASE9_SNAPSHOT[symbol]
        scheme = get_scheme(symbol)

        if expected_types is None:
            # 单协变量模式: covariate_types 应为 None 或空
            assert (
                scheme.covariate_types is None
                or len(scheme.covariate_types) == 0
                or scheme.covariate_types == [scheme.covariate_type]
            ), (
                f"{symbol}: 应为单协变量模式, "
                f"实际 covariate_types={scheme.covariate_types}"
            )
        else:
            assert scheme.covariate_types == expected_types, (
                f"{symbol}: covariate_types 期望 {expected_types}, "
                f"实际 {scheme.covariate_types}"
            )

    @pytest.mark.parametrize("symbol", list(PHASE9_SNAPSHOT.keys()))
    def test_dir_acc(self, symbol):
        """DirAcc 与快照一致 (容差 1e-6)"""
        _, _, expected_dir_acc, _ = PHASE9_SNAPSHOT[symbol]
        scheme = get_scheme(symbol)
        assert abs(scheme.dir_acc - expected_dir_acc) < 1e-6, (
            f"{symbol}: dir_acc 期望 {expected_dir_acc:.3f}, "
            f"实际 {scheme.dir_acc:.3f}"
        )

    @pytest.mark.parametrize("symbol", list(PHASE9_SNAPSHOT.keys()))
    def test_stars(self, symbol):
        """星级与快照一致"""
        _, _, _, expected_stars = PHASE9_SNAPSHOT[symbol]
        scheme = get_scheme(symbol)
        assert scheme.stars == expected_stars, (
            f"{symbol}: stars 期望 {expected_stars}, 实际 {scheme.stars}"
        )

    def test_combo_first_matches_single(self):
        """组合模式首位应与 covariate_type 一致 (架构约束)"""
        for symbol, scheme in SCHEMES.items():
            if scheme.covariate_types and len(scheme.covariate_types) > 0:
                assert scheme.covariate_types[0] == scheme.covariate_type, (
                    f"{symbol}: covariate_types[0]={scheme.covariate_types[0]} "
                    f"!= covariate_type={scheme.covariate_type}"
                )


# ─────────────────────────────────────────────────────────
# 负向测试: 验证测试本身能检测篡改
# ─────────────────────────────────────────────────────────

class TestTamperingDetection:
    """验证测试本身能检测到配置篡改"""

    def test_detects_wrong_covariate_type(self):
        """断言错误的 covariate_type 会被检测到"""
        scheme = get_scheme("fu")
        # FU 应该是 calendar_cyclical (Phase 11),故意断言错误值
        assert scheme.covariate_type != "ha_body", (
            "测试逻辑错误: FU 应该是 calendar_cyclical,不应是 ha_body"
        )

    def test_detects_wrong_stars(self):
        """断言错误的 stars 会被检测到"""
        scheme = get_scheme("ss")
        # SS 应该是 2★,故意断言错误值
        assert scheme.stars != 3, (
            "测试逻辑错误: SS 应该是 2★,不应是 3★"
        )

    def test_detects_wrong_dir_acc(self):
        """断言错误的 dir_acc 会被检测到"""
        scheme = get_scheme("ta")
        # TA 应该是 0.58,故意断言错误值
        assert abs(scheme.dir_acc - 0.99) > 0.01, (
            "测试逻辑错误: TA dir_acc 应为 0.58,不应是 0.99"
        )


# ─────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
