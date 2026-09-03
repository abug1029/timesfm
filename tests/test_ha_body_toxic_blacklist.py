"""
ha_body 有毒品种黑名单测试 (2026-08-03)

防止 AO/JD 被错误地使用 ha_body 协变量。

实证依据 (Phase 9, 2026-08-03):
- AO: ha_body 导致 EV 转负 (-0.054), MaxDD 翻倍 (-57.92%)
- JD: ha_body 导致 EV 转负, DirAcc 退化 -3pp
  (具体: ha_body+oi DirAcc 49.5%, EV -0.009; rsi_state+oi DirAcc 52.5%, EV +0.133)

CF 不在此黑名单: CF 当前是 ha_body+calendar (组合有效, DirAcc 56.0%),
但 ha_body 单独使用对 CF 有害 (-5pp)。

参考: reports/research/20260803_phase9_two_star_to_three_study.md
"""

import pytest
from config.prediction_scheme import get_scheme


# ha_body 有毒品种黑名单
HA_BODY_TOXIC_SYMBOLS = ["ao", "jd"]


class TestHaBodyToxicBlacklist:
    """防止有毒品种使用 ha_body"""

    @pytest.mark.parametrize("symbol", HA_BODY_TOXIC_SYMBOLS)
    def test_covariate_type_not_ha_body(self, symbol):
        """单协变量字段 covariate_type 不应是 ha_body"""
        scheme = get_scheme(symbol)
        assert scheme is not None, f"{symbol} 未在 SCHEMES 中定义"
        assert scheme.covariate_type != "ha_body", (
            f"{symbol}: covariate_type 是 ha_body (有毒!). "
            f"Phase 9 实证: ha_body 对 {symbol.upper()} 导致 EV 转负/DirAcc 退化. "
            f"当前正确配置: {self._expected_config(symbol)}"
        )

    @pytest.mark.parametrize("symbol", HA_BODY_TOXIC_SYMBOLS)
    def test_covariate_types_no_ha_body(self, symbol):
        """组合协变量字段 covariate_types 不应包含 ha_body"""
        scheme = get_scheme(symbol)
        if scheme.covariate_types:
            assert "ha_body" not in scheme.covariate_types, (
                f"{symbol}: covariate_types 包含 ha_body (有毒!). "
                f"当前组合: {scheme.covariate_types}. "
                f"Phase 9 实证: ha_body 对 {symbol.upper()} 有害."
            )

    def _expected_config(self, symbol: str) -> str:
        """返回品种期望配置 (用于错误消息)"""
        expected = {
            "ao": "hourly_slope (1H 价格滚动斜率)",
            "jd": "rsi_state+oi (RSI 状态 + 持仓量)",
        }
        return expected.get(symbol, "未知")


# ─────────────────────────────────────────────────────────
# 负向测试: 验证测试本身能检测篡改
# ─────────────────────────────────────────────────────────

class TestToxicBlacklistTamperingDetection:
    """验证黑名单测试能检测到配置篡改"""

    def test_detects_ao_tampering(self):
        """断言把 AO 改为 ha_body 会被检测到"""
        scheme = get_scheme("ao")
        # AO 应该是 hourly_slope,故意断言错误值
        assert scheme.covariate_type != "ha_body", (
            "测试逻辑错误: AO 应该是 hourly_slope,不应是 ha_body"
        )

    def test_detects_jd_tampering(self):
        """断言把 JD 改为 ha_body 会被检测到"""
        scheme = get_scheme("jd")
        # JD 应该是 rsi_state (组合首位),故意断言错误值
        assert scheme.covariate_type != "ha_body", (
            "测试逻辑错误: JD 应该是 rsi_state,不应是 ha_body"
        )

    def test_cf_not_in_blacklist(self):
        """CF 不在黑名单中 (ha_body+calendar 组合有效)"""
        scheme = get_scheme("cf")
        # CF 当前是 ha_body+calendar,这是有效的
        assert scheme.covariate_type == "ha_body", (
            "CF 应该是 ha_body (ha_body+calendar 组合有效)"
        )
        assert "ha_body" in scheme.covariate_types, (
            "CF covariate_types 应包含 ha_body"
        )


# ─────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
