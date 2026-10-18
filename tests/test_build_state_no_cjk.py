# tests/test_build_state_no_cjk.py
import re
from cascade.typesafe_prescreen import _build_state

# 东亚宽字符正则（与门禁脚本一致）
_EAST_ASIAN_WIDE = re.compile(
    r"[\u4e00-\u9fff\u3000-\u303f"
    r"\uff01-\uff0f\uff1a-\uff20\uff3b-\uff3f\uff5b-\uff65]"
)

def test_build_state_strips_chinese_pd():
    """predicted_direction 含中文 -> strip 后无东亚宽字符"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": "seasonal_supply_peak(7-9\u6708\u51fa\u680f\u9ad8\u5cf0) -> short",
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    assert not _EAST_ASIAN_WIDE.search(pd), f"PD still has East Asian wide chars: {pd!r}"

def test_build_state_shell_pd_fallback():
    """空壳 PD -> 置为空串"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": "\u4ef7\u5dee\u52a0\u901f\u5ea6\u8f6c\u6b63 -> long, \u52a0\u901f\u5ea6\u8f6c\u8d1f -> short",
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    assert pd == ""

def test_build_state_short_formula_shell():
    """短公式空壳（Review Focus 5）：RSI(6)>80 超买 -> short -> 空壳"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "rsi",
        "covariate_family": "momentum",
        "predicted_direction": "RSI(6)>80 \u8d85\u4e70 -> short",
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    assert pd == ""

def test_build_state_language_field():
    """state 包含 language: en（best-effort）"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": "oi_up_with_price -> long",
    }
    state = _build_state(proposal, "p", None, None)
    assert state.get("language") == "en"

def test_build_state_preserves_other_fields():
    """其他字段不受影响"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "JD",
        "cov_override": "rsi",
        "covariate_family": "momentum",
        "predicted_direction": "RSI(6)>80 \u8d85\u4e70 -> short",
    }
    state = _build_state(proposal, "JD", None, None)
    assert state["proposal_summary"]["proposal_id"] == "p_test"
    assert state["proposal_summary"]["symbol"] == "JD"
    assert state["proposal_summary"]["cov_override"] == "rsi"
    assert state["proposal_summary"]["covariate_family"] == "momentum"

def test_build_state_handles_null_pd():
    """predicted_direction 为 None -> 空串（reviewer 建议）"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": None,
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    assert pd == ""

# ── Task 4: _call_laya tests ──────────────────────────
from unittest.mock import patch, MagicMock
import inspect

def test_call_laya_payload_includes_language():
    """_call_laya payload 顶层包含 language: en"""
    from cascade.typesafe_prescreen import _call_laya
    state = {
        "language": "en",
        "symbol": "p",
        "proposal_summary": {"predicted_direction": "oi_up -> long"},
    }
    with patch('requests.post') as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"answers": {"mechanism_plausibility": {"noul": 0.7, "confidence": 0.8}}}
        mock_post.return_value = mock_resp
        _call_laya(state)
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs.get('json')
        assert payload is not None
        assert payload.get("language") == "en"
        assert payload.get("model") == "laya-rl-agent"

def test_call_laya_timeout_signature():
    """_call_laya 签名默认超时 60s（从 30s 统一）"""
    from cascade.typesafe_prescreen import _call_laya
    sig = inspect.signature(_call_laya)
    timeout_param = sig.parameters.get('timeout')
    assert timeout_param is not None
    assert timeout_param.default == 60.0
