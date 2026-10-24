"""Task 3 tests - P0-3 timeout tiers (primary 10s / fallback 5s) + 503 no-retry"""
import requests
from unittest.mock import patch, MagicMock

from cascade import laya_prescreen as lp


_STATE = {
    "symbol": "rb",
    "sector": "black",
    "contract_details": "rb",
    "proposal": {},
    "covariate_menu": {},
    "recent_verdicts_summary": "",
}


class TestTimeoutTiers:
    def test_primary_endpoint_uses_10s_timeout(self):
        captured_timeouts = []

        def fake_post(url, json, headers, timeout):
            captured_timeouts.append(timeout)
            raise requests.Timeout("simulated")

        with patch("cascade.laya_prescreen.requests.post", side_effect=fake_post):
            try:
                lp._call_laya(_STATE, "x")
            except (ConnectionError, lp.LayaTimeoutError):
                pass

        assert captured_timeouts[0] == 10.0, f"primary should be 10s, got {captured_timeouts[0]}"

    def test_fallback_endpoint_uses_5s_timeout(self):
        captured_timeouts = []

        def fake_post(url, json, headers, timeout):
            captured_timeouts.append(timeout)
            raise requests.Timeout("simulated")

        with patch("cascade.laya_prescreen.requests.post", side_effect=fake_post):
            try:
                lp._call_laya(_STATE, "x")
            except (ConnectionError, lp.LayaTimeoutError):
                pass

        assert len(captured_timeouts) >= 2, "should have tried both endpoints"
        assert captured_timeouts[1] == 5.0, f"fallback should be 5s, got {captured_timeouts[1]}"

    def test_503_does_not_retry_second_endpoint(self):
        call_count = 0

        def fake_post(url, json, headers, timeout):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 503
            raise requests.HTTPError(response=resp)

        with patch("cascade.laya_prescreen.requests.post", side_effect=fake_post):
            try:
                lp._call_laya(_STATE, "x")
            except lp.LayaUnavailableError:
                pass

        assert call_count == 1, f"503 should not retry, but got {call_count} calls"
