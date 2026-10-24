"""tests/test_laya_queue_backoff.py — 队列感知退避（滑动窗口 p80）测试"""

from cascade import laya_prescreen as lp


class TestQueueBackoff:
    def setup_method(self):
        lp._latency_window.clear()
    
    def test_under_5_samples_never_skips(self):
        """样本 < 5 时不启用退避（冷启动期）。"""
        for lat in [1.0, 2.0, 3.0, 4.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is False

    def test_p80_under_20s_does_not_skip(self):
        """p80 <= 20s 时正常调用。"""
        for lat in [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 15.0]:
            lp._record_latency(lat)
        # p80 = sorted[7] = 12.0
        assert lp._should_skip_prescreen() is False

    def test_p80_over_20s_skips(self):
        """p80 > 20s 时跳过后续请求。"""
        for lat in [5.0, 6.0, 7.0, 8.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0]:
            lp._record_latency(lat)
        # sorted = [5,6,7,8,21,22,23,24,25,26]; p80 = sorted[7] = 24.0 > 20
        assert lp._should_skip_prescreen() is True

    def test_window_is_bounded_at_10(self):
        """滑动窗口最多保留 10 条。"""
        for i in range(20):
            lp._record_latency(float(i))
        assert len(lp._latency_window) == 10

    def test_recovery_after_backoff(self):
        """p80 回落到 < 15s 后恢复正常调用。"""
        # 先拥堵
        for lat in [5.0, 6.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0, 31.0, 32.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is True
        
        # 恢复到正常
        lp._latency_window.clear()
        for lat in [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is False
