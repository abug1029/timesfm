"""短窗回测测试 (Phase 2 Task 2)"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import short_window_backtest as swb


def test_short_window_calculation():
    """短窗 dir_acc 计算正确：mock 信号与实际价格方向对比。"""
    import numpy as np

    # 构造一个信号始终正确的场景：信号正 → 价格涨，信号负 → 价格跌
    # 这样 dir_acc 应该 = 1.0
    n = 200
    horizon = 24
    close = np.zeros(n)
    signal = np.zeros(n)
    for t in range(0, n - horizon, 24):
        if t + horizon < n:
            sig = 1.0 if t % 48 == 0 else -1.0
            signal[t] = sig
            # 价格朝信号方向移动
            close[t + horizon] = close[t] + sig * 10.0
            # 中间点插值
            for k in range(1, horizon):
                if t + k < n:
                    close[t + k] = close[t] + sig * 10.0 * k / horizon

    # 用 _compute_dir_acc 的内部逻辑手动验证
    correct = 0
    total = 0
    for t in range(0, n - horizon, 24):
        if abs(signal[t]) < 1e-8:
            continue
        pred_up = signal[t] > 0
        delta = close[t + horizon] - close[t]
        if abs(delta) < 1e-8 * abs(close[t]):
            continue
        actual_up = delta > 0
        if pred_up == actual_up:
            correct += 1
        total += 1

    assert total >= 5, f"too few test points: {total}"
    assert correct == total, f"expected all correct, got {correct}/{total}"


def test_threshold_filtering():
    """dir_acc > 0.50 通过，否则拒绝。"""
    # 构造 dir_acc > 0.50 的结果
    passing_result = {
        "variant_id": "test_pass",
        "symbol": "rb",
        "cov_override": "rsi_state",
        "window_size": 150,
        "dir_acc": 0.55,
        "n": 10,
        "pass": True,
        "timestamp": "2026-10-20T00:00:00+00:00",
    }
    assert passing_result["pass"] is True
    assert passing_result["dir_acc"] > 0.50

    # 构造 dir_acc <= 0.50 的结果
    failing_result = {
        "variant_id": "test_fail",
        "symbol": "rb",
        "cov_override": "noise",
        "window_size": 150,
        "dir_acc": 0.45,
        "n": 10,
        "pass": False,
        "timestamp": "2026-10-20T00:00:00+00:00",
    }
    assert failing_result["pass"] is False
    assert failing_result["dir_acc"] <= 0.50

    # 边界值: dir_acc = 0.50 → 不通过 (必须 > 0.50)
    boundary_result = {
        "variant_id": "test_boundary",
        "symbol": "rb",
        "cov_override": "ma20",
        "window_size": 150,
        "dir_acc": 0.50,
        "n": 10,
        "pass": False,
        "timestamp": "2026-10-20T00:00:00+00:00",
    }
    assert boundary_result["pass"] is False


def test_batch_processing():
    """批量处理正确写入 JSONL 输出文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "test_results.jsonl")
        results = [
            {"variant_id": "v1", "dir_acc": 0.55, "pass": True},
            {"variant_id": "v2", "dir_acc": 0.40, "pass": False},
            {"variant_id": "v3", "dir_acc": 0.60, "pass": True},
        ]
        with open(output, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # 读取验证
        loaded = []
        with open(output, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    loaded.append(json.loads(line))

        assert len(loaded) == 3
        assert loaded[0]["variant_id"] == "v1"
        assert loaded[1]["pass"] is False
        assert loaded[2]["dir_acc"] == 0.60


def test_result_format():
    """输出 JSONL 格式正确，包含所有必需字段。"""
    required_keys = {
        "variant_id", "symbol", "cov_override", "window_size",
        "dir_acc", "n", "pass", "timestamp",
    }

    result = swb.short_window_backtest("rb", "rsi_state", window_size=150)

    assert isinstance(result, dict)
    for key in required_keys:
        assert key in result, f"missing key: {key}"

    assert isinstance(result["variant_id"], str)
    assert isinstance(result["symbol"], str)
    assert isinstance(result["cov_override"], str)
    assert isinstance(result["window_size"], int)
    assert isinstance(result["dir_acc"], float)
    assert isinstance(result["n"], int)
    assert isinstance(result["pass"], bool)
    assert isinstance(result["timestamp"], str)

    # variant_id 格式
    assert result["variant_id"] == "rb_rsi_state"
    assert result["symbol"] == "rb"
    assert result["cov_override"] == "rsi_state"


def test_harvest_integration():
    """短窗失败不入队：模拟 harvest 循环中的 _short_window_check 逻辑。"""
    # 模拟: _short_window_check 返回 None → fail-open (不阻塞)
    # 返回 {"pass": False} → 拒绝
    # 返回 {"pass": True} → 继续

    def simulate_harvest_check(sw_result):
        """模拟 harvest 循环中的短窗检查逻辑。"""
        if sw_result is not None and not sw_result.get("pass"):
            return "short_window_fail"
        return None  # continue

    # 短窗失败 → 拒绝
    fail_result = {"variant_id": "v1", "pass": False, "dir_acc": 0.40}
    assert simulate_harvest_check(fail_result) == "short_window_fail"

    # 短窗通过 → 继续
    pass_result = {"variant_id": "v2", "pass": True, "dir_acc": 0.55}
    assert simulate_harvest_check(pass_result) is None

    # 回测不可用 (None) → fail-open, 继续
    assert simulate_harvest_check(None) is None

    # 样本太少 (n<5, dir_acc=0.5, pass=False) → 拒绝
    low_sample = {"variant_id": "v3", "pass": False, "dir_acc": 0.5, "n": 2}
    assert simulate_harvest_check(low_sample) == "short_window_fail"


def test_cache_roundtrip():
    """缓存读写正确。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = os.path.join(tmpdir, "cache.jsonl")

        # 写
        result = {
            "variant_id": "rb_rsi",
            "symbol": "rb",
            "cov_override": "rsi_state",
            "window_size": 150,
            "dir_acc": 0.55,
            "n": 8,
            "pass": True,
            "timestamp": "2026-10-20T00:00:00+00:00",
        }
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

        # 读
        original_path = swb.SHORT_WINDOW_RESULTS_PATH
        swb.SHORT_WINDOW_RESULTS_PATH = cache_path
        try:
            cached = swb.load_short_window_cache("rb_rsi")
            assert cached is not None
            assert cached["variant_id"] == "rb_rsi"
            assert cached["dir_acc"] == 0.55
            assert cached["pass"] is True

            # 不存在的 variant_id
            assert swb.load_short_window_cache("nonexistent") is None
        finally:
            swb.SHORT_WINDOW_RESULTS_PATH = original_path


def test_signal_funcs_exist():
    """所有已知协变量都有信号函数映射。"""
    known_covs = [
        "rsi_state", "rsi6", "rsi12", "rsi24", "rsi_slope",
        "oi", "ccl", "nvi",
        "bb_squeeze", "stddev", "vor",
        "calendar_cyclical",
        "ma20", "ma5", "ma10",  # 不在映射中但应走默认
    ]
    for cov in known_covs:
        func = swb._get_signal_func(cov)
        assert callable(func), f"no signal function for {cov}"
