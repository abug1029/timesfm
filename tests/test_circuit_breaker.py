import time
import threading
from cascade.laya_prescreen import CircuitBreaker


class TestCircuitBreakerBasic:
    def test_initial_state_closed(self):
        cb = CircuitBreaker(threshold=3, duration=300)
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.should_skip() is False

    def test_three_failures_open(self):
        cb = CircuitBreaker(threshold=3, duration=300)
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.should_skip() is True

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker(threshold=3, duration=300)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    def test_open_after_duration_transitions_to_half_open(self):
        cb = CircuitBreaker(threshold=3, duration=0.1)  # 100ms 用于测试
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.15)
        # 第一次 should_skip 触发 → HALF_OPEN，且允许 1 个探针
        assert cb.should_skip() is False
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_probe_success_closes(self):
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.should_skip()  # transition to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_probe_failure_reopens(self):
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.should_skip()  # transition to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN


class TestCircuitBreakerConcurrency:
    def test_half_open_only_one_probe_allowed(self):
        """HALF_OPEN 期间，第一次 should_skip 返回 False（放行探针），后续都返回 True。"""
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        # 第一个调用者拿到探针权
        assert cb.should_skip() is False
        # 后续调用者全部跳过
        assert cb.should_skip() is True
        assert cb.should_skip() is True
        assert cb.should_skip() is True

    def test_thread_safety(self):
        """多线程下不崩溃，且探针锁仍然有效。"""
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        results = []
        def probe():
            results.append(cb.should_skip())
        
        threads = [threading.Thread(target=probe) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 必须恰好有 1 个 False（探针），其余 True
        assert results.count(False) == 1
        assert results.count(True) == 9
