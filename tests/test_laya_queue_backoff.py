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
    def test_p80_calculation_at_n5(self):
        """热身期 n=5 时 p80 必须取 sorted[3]（严格 80th），而非 sorted[2]（60th）。

        sorted = [1,2,3,4,25]：
          - 修复前 idx=max(0,5-3)=2 → p80=3（60th，错误）
          - 修复后 idx=int(5*0.8)-1=3 → p80=4（80th，正确）
        当 p80=4 时 < 15s，应不跳过；把最后一个值调到 25s 使 p80=20 边界上
        不跳过（滞后：20s 时保守保持不跳）；要触发跳过需 p80 > 20s。
        这里 [1,2,3,4,100] → sorted[3]=4（<15s，不跳）；
        [1,2,3,25,100] → sorted[3]=25（>20s，跳过）——验证索引为 3 而非 2。
        """
        # n=5, 索引=3：[1,2,3,25,100] 的 sorted[3]=25 > 20，触发跳过
        for lat in [1.0, 2.0, 3.0, 25.0, 100.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is True, "n=5 p80 应取 sorted[3]=25"

        # 反证：若错误取 sorted[2]=3（60th），上例会误判为不跳过
        # 下面用例确保 sorted[3] < 15 时不跳过（证明取的确实是索引 3）
        lp._latency_window.clear()
        for lat in [1.0, 2.0, 3.0, 4.0, 100.0]:
            lp._record_latency(lat)
        # sorted=[1,2,3,4,100]，sorted[3]=4 < 15，应不跳过
        assert lp._should_skip_prescreen() is False, "n=5 sorted[3]=4 < 15，不应跳过"

    def test_p80_calculation_at_n7(self):
        """热身期 n=7 时 idx=int(7*0.8)-1=4（sorted[4]，≈71st，最接近 80th）。

        修复前 idx=max(0,7-3)=4，二者恰好相同；此用例确认 n=7 行为一致，
        并验证 sorted[4] 的语义：把阈值放在索引 4 位置可切换跳过状态。
        """
        # sorted=[1,2,3,4,5,6,100]，idx=4 → p80=5 < 15，不跳
        for lat in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 100.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is False

        # sorted=[1,2,3,4,25,30,100]，idx=4 → p80=25 > 20，跳过
        lp._latency_window.clear()
        for lat in [1.0, 2.0, 3.0, 4.0, 25.0, 30.0, 100.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is True
