"""
KB-SCHEMES 一致性测试 (2026-08-03)

验证 knowledge_base.json 与 config/prediction_scheme.py 的 SCHEMES 字典保持一致。

防止 KB 重建后与 SCHEMES 不同步,或 SCHEMES 修改后 KB 未更新。
数据来源: build_knowledge_base.py 生成的 KB,SCHEMES 是唯一真值源。
"""

import json
import pytest
from pathlib import Path

from config.prediction_scheme import SCHEMES, get_scheme


# KB 路径
KB_PATH = Path(__file__).parent.parent / "config" / "knowledge_base.json"


@pytest.fixture(scope="module")
def kb_symbols():
    """加载 KB symbols 字典"""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)
    assert "symbols" in kb, "KB 缺少 'symbols' 字段"
    return kb["symbols"]


class TestKBSchemesConsistency:
    """KB 与 SCHEMES 一致性断言"""

    def test_kb_file_exists(self):
        """knowledge_base.json 存在"""
        assert KB_PATH.exists(), f"KB 文件不存在: {KB_PATH}"

    def test_symbol_set_matches(self, kb_symbols):
        """KB 品种集合与 SCHEMES 一致"""
        kb_set = set(kb_symbols.keys())
        scheme_set = set(SCHEMES.keys())
        assert kb_set == scheme_set, (
            f"品种集合不一致\n"
            f"KB 独有: {kb_set - scheme_set}\n"
            f"SCHEMES 独有: {scheme_set - kb_set}"
        )

    @pytest.mark.parametrize("symbol", list(SCHEMES.keys()))
    def test_covariate_matches(self, kb_symbols, symbol):
        """KB covariate 字段与 SCHEMES 一致

        KB 设计惯例:
        - 组合模式: KB covariate = "+".join(scheme.covariate_types)
          如 'ha_body+calendar_cyclical', 'rsi_state+oi+calendar_cyclical'
        - 单协变量模式: KB covariate = scheme.covariate_type
          如 'ha_body', 'reversal_shadow', 'ao_accel'
        """
        scheme = get_scheme(symbol)
        kb_cov = kb_symbols[symbol].get("covariate")

        # 按 SCHEMES 的实际结构构造期望值
        if scheme.covariate_types and len(scheme.covariate_types) > 0:
            expected = "+".join(scheme.covariate_types)
        else:
            expected = scheme.covariate_type

        assert kb_cov == expected, (
            f"{symbol}: KB covariate={kb_cov!r} != 期望 {expected!r} "
            f"(covariate_type={scheme.covariate_type!r}, "
            f"covariate_types={scheme.covariate_types})"
        )

    @pytest.mark.parametrize("symbol", list(SCHEMES.keys()))
    def test_scheme_stars_matches(self, kb_symbols, symbol):
        """KB scheme_stars 字段与 SCHEMES stars 一致"""
        scheme = get_scheme(symbol)
        kb_stars = kb_symbols[symbol].get("scheme_stars")
        assert kb_stars == scheme.stars, (
            f"{symbol}: KB scheme_stars={kb_stars} "
            f"!= SCHEMES stars={scheme.stars}"
        )

    @pytest.mark.parametrize("symbol", list(SCHEMES.keys()))
    def test_historical_diracc_matches(self, kb_symbols, symbol):
        """KB historical_diracc 与 SCHEMES dir_acc 一致 (容差 0.01)

        注: 两者都是小数形式 (0.55 表示 55%),无需 *100 转换
        """
        scheme = get_scheme(symbol)
        kb_diracc = kb_symbols[symbol].get("historical_diracc")
        assert kb_diracc is not None, f"{symbol}: KB 缺少 historical_diracc"
        assert abs(kb_diracc - scheme.dir_acc) < 0.01, (
            f"{symbol}: KB historical_diracc={kb_diracc:.3f} "
            f"!= SCHEMES dir_acc={scheme.dir_acc:.3f} "
            f"(差 {abs(kb_diracc - scheme.dir_acc):.3f} > 容差 0.01)"
        )

    @pytest.mark.parametrize("symbol", list(SCHEMES.keys()))
    def test_scheme_type_matches(self, kb_symbols, symbol):
        """KB scheme_type 与 SCHEMES scheme_type 一致"""
        scheme = get_scheme(symbol)
        kb_type = kb_symbols[symbol].get("scheme_type")
        assert kb_type == scheme.scheme_type, (
            f"{symbol}: KB scheme_type={kb_type!r} "
            f"!= SCHEMES scheme_type={scheme.scheme_type!r}"
        )

    @pytest.mark.parametrize("symbol", list(SCHEMES.keys()))
    def test_short_horizon_consistency(self, kb_symbols, symbol):
        """KB short_horizon_only 与 SCHEMES short_horizon_only 一致"""
        scheme = get_scheme(symbol)
        kb_short = kb_symbols[symbol].get("short_horizon_only")
        assert kb_short == scheme.short_horizon_only, (
            f"{symbol}: KB short_horizon_only={kb_short} "
            f"!= SCHEMES short_horizon_only={scheme.short_horizon_only}"
        )


# ─────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
