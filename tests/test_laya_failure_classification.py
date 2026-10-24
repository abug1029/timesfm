"""Task 1 tests — Laya failure 统一分类 + 503 进熔断"""
import pytest
from unittest.mock import patch, MagicMock

from cascade.laya_prescreen import (
    LayaUnavailableError,
    _call_laya,
    _prescreen_impl,
    _fallback_result,
)
from cascade import laya_prescreen as lp


class TestLayaUnavailableError:
    def test_503_raises_laya_unavailable(self):
        """503 响应必须被 re-raise 为 LayaUnavailableError，不能被 ConnectionError 吞掉。"""
        import requests
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("cascade.laya_prescreen.requests.post") as mock_post:
            mock_post.side_effect = requests.HTTPError(response=mock_resp)
            with pytest.raises(LayaUnavailableError):
                _call_laya({"symbol": "rb", "sector": "black", "contract_details": "rb", "proposal": {}, "covariate_menu": {}, "recent_verdicts_summary": ""}, api_key="x", timeout=5.0)


class TestPrescreenFailureClassification:
    def _patch_common(self):
        return (
            patch.object(lp, "_get_laya_api_key", return_value="x"),
            patch.object(lp, "_check_circuit", return_value=False),
            patch.object(lp, "_build_state", return_value={"symbol": "rb"}),
        )

    def test_503_triggers_record_failure(self):
        """503 必须走 _record_failure，不能漏进泛 Exception 分支。"""
        recorded = []
        orig = getattr(lp, "_record_failure", None)
        lp._record_failure = lambda reason: recorded.append(reason)
        try:
            k1, k2, k3 = self._patch_common()
            with k1, k2, k3:
                with patch.object(lp, "_call_laya", side_effect=lp.LayaUnavailableError("503 from x")):
                    result = lp._prescreen_impl({"variant_id": "v1"}, "rb", None, None)
            assert result["status"] in ("degraded", "error")
            assert "503_unavailable" in recorded
        finally:
            if orig is not None:
                lp._record_failure = orig
            else:
                delattr(lp, "_record_failure")

    def test_timeout_triggers_record_failure(self):
        """超时也必须走 _record_failure（统一分类）。"""
        recorded = []
        orig = getattr(lp, "_record_failure", None)
        lp._record_failure = lambda reason: recorded.append(reason)
        try:
            k1, k2, k3 = self._patch_common()
            with k1, k2, k3:
                with patch.object(lp, "_call_laya", side_effect=lp.LayaTimeoutError("t")):
                    lp._prescreen_impl({"variant_id": "v1"}, "rb", None, None)
            assert any("timeout" in r for r in recorded)
        finally:
            if orig is not None:
                lp._record_failure = orig
            else:
                delattr(lp, "_record_failure")
