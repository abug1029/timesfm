"""tests/test_prescreen_score.py — Test prescreen score adjustment in supervisor."""
import json
import os
import sys
from pathlib import Path

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from scripts.praxist_supervisor import _apply_prescreen_score


class TestApplyPrescreenScore:
    """Test prescreen score adjustment logic."""

    def test_no_proposal_path_returns_unchanged(self):
        assert _apply_prescreen_score(50.0, None) == 50.0

    def test_no_prescreen_file_returns_unchanged(self, tmp_path):
        prop_path = str(tmp_path / "p_001.json")
        # No .prescreen.json exists
        assert _apply_prescreen_score(50.0, prop_path) == 50.0

    def test_corrupted_prescreen_file_returns_unchanged(self, tmp_path):
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            f.write('{"status": "succe')
        assert _apply_prescreen_score(50.0, prop_path) == 50.0

    def test_degraded_prescreen_returns_unchanged(self, tmp_path):
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({"status": "degraded", "skip_suggested": None}, f)
        assert _apply_prescreen_score(50.0, prop_path) == 50.0

    def test_invalid_mechanism_penalty(self, tmp_path):
        """invalid → -100 (effectively removes from pool)."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "invalid", "mechanism_plausibility": 0.7,
                "effect_size": 3,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == -50.0

    def test_redundant_weak_penalty(self, tmp_path):
        """redundant + effect_size <= 1 → -30."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "redundant", "mechanism_plausibility": 0.6,
                "effect_size": 1,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 20.0

    def test_low_plausibility_penalty(self, tmp_path):
        """plausibility < 0.4 → -20."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "extension", "mechanism_plausibility": 0.3,
                "effect_size": 2,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 30.0

    def test_high_effect_reward(self, tmp_path):
        """skip_suggested=False + effect_size >= 2 → +10."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "novel", "mechanism_plausibility": 0.8,
                "effect_size": 3,
            }, f)
        result = _apply_prescreen_score(50.0, prop_path)
        # +10 (high effect) + 5 (novel + high plausibility) = +15
        assert result == 65.0

    def test_novelty_confirmed_reward(self, tmp_path):
        """novel/extension + plausibility > 0.6 → +5."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "extension", "mechanism_plausibility": 0.7,
                "effect_size": 1,
            }, f)
        result = _apply_prescreen_score(50.0, prop_path)
        # +5 (novelty confirmed), but effect_size < 2 so no +10
        assert result == 55.0

    def test_skip_false_low_effect_no_reward(self, tmp_path):
        """skip=False but effect_size=0 → no reward."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "novel", "mechanism_plausibility": 0.5,
                "effect_size": 0,
            }, f)
        result = _apply_prescreen_score(50.0, prop_path)
        # effect_size=0 < 2, plausibility=0.5 < 0.6 → no reward
        assert result == 50.0

    def test_skip_true_redundant_none_effect(self, tmp_path):
        """skip=True + redundant + effect_size=None → -30."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "redundant", "mechanism_plausibility": 0.5,
                "effect_size": None,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 20.0

    def test_combined_penalty_invalid_wins(self, tmp_path):
        """invalid should get -100, not also trigger other penalties."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "invalid", "mechanism_plausibility": 0.1,
                "effect_size": 0,
            }, f)
        # invalid triggers -100 first (early return)
        assert _apply_prescreen_score(50.0, prop_path) == -50.0


class TestPrescreenAsync:
    """Test fire-and-forget prescreen thread (daemon, non-blocking, silent failure)."""

    def test_returns_immediately_non_blocking(self):
        """_prescreen_async 应立即返回，不阻塞调用方。"""
        import time
        from scripts.praxist_supervisor import _prescreen_async
        prop = {"variant_id": "v_test_async", "cov_override": "cc", "symbol": "rb"}
        start = time.time()
        # 找不到 proposal 文件/无 key → daemon 线程静默失败, 主线程立即返回
        _prescreen_async(prop, "/nonexistent/p_001.json", "rb")
        elapsed = time.time() - start
        assert elapsed < 1.0  # 同步阻塞 (含 API) 会 > 1s; fire-and-forget 立返

    def test_launches_daemon_thread(self):
        """线程应为 daemon, 进程退出时不阻塞."""
        from scripts.praxist_supervisor import _prescreen_async
        import threading
        prop = {"variant_id": "v", "cov_override": "cc", "symbol": "rb"}
        orig_start = threading.Thread.__init__
        captured = {}
        def spy(self, *a, **k):
            captured["daemon"] = k.get("daemon", a[-1] if a else None)
            orig_start(self, *a, **k)
        threading.Thread.__init__ = spy
        try:
            _prescreen_async(prop, "/nonexistent/p_001.json", "rb")
        finally:
            threading.Thread.__init__ = orig_start
        assert captured.get("daemon") is True

    def test_import_error_silent(self):
        """prescreen 模块导入失败时静默返回, 不抛给调用方."""
        import scripts.praxist_supervisor as s

        class _FakeLog:
            def __init__(self): self.calls = []
            def warning(self, *a, **k): self.calls.append((a, k))

        # 模拟 prescreen 导入失败 → _prescreen_async 应记录 warning 后返回
        orig_log = s.logging
        result = _FakeLog()
        s.logging = result  # 替换模块级 logging (内含 warning 引用到模块级 logging)
        try:
            # 覆盖: 强制 typesafe 子模块导入抛错
            import builtins
            real_import = builtins.__import__
            def broken(name, *a, **k):
                if name == "cascade.typesafe_prescreen":
                    raise ImportError("simulated")
                return real_import(name, *a, **k)
            builtins.__import__ = broken
            try:
                # 不抛异常即通过
                s._prescreen_async({}, "/x.json", "rb")
                assert True
            finally:
                builtins.__import__ = real_import
        finally:
            s.logging = orig_log
        assert len(result.calls) >= 1  # 记录了 warning (导入失败)


    def test_zero_effect_mid_plausibility_penalty(self, tmp_path):
        """skip 第4分支: effect==0 且 plausibility ∈ [0.4,0.6) → -15 (WARN-2修复)."""
        prop_path = str(tmp_path / "p_z.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "extension", "mechanism_plausibility": 0.5,
                "effect_size": 0,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 35.0

    def test_zero_effect_high_plausibility_no_penalty(self, tmp_path):
        """skip=False 且 effect==0 高可信 → 无第4分支惩罚."""
        prop_path = str(tmp_path / "p_h.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "extension", "mechanism_plausibility": 0.7,
                "effect_size": 0,
            }, f)
        # effect<2 无 +10, plausibility>0.6 有 +5
        assert _apply_prescreen_score(50.0, prop_path) == 55.0


    def test_prescreen_async_skips_if_success_exists(self, monkeypatch, tmp_path):
        """WARN-3: 已有 status=success 结果则幂等跳过, 不启动 daemon 线程."""
        import threading
        from scripts.praxist_supervisor import _prescreen_async

        prop_path = str(tmp_path / "p.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({"status": "success", "skip_suggested": False}, f)

        started = []
        orig_start = threading.Thread.start
        def spy_start(self):
            started.append(self.name)
            return orig_start(self)
        monkeypatch.setattr(threading.Thread, "start", spy_start)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

        _prescreen_async({"variant_id": "v"}, prop_path, "rb")
        import time; time.sleep(0.2)
        assert started == [], "幂等守卫应跳过, 不启动线程"

    def test_prescreen_async_retries_if_degraded(self, monkeypatch, tmp_path):
        """WARN-3: 非 success (degraded/损坏) 结果允许重试, 启动线程."""
        import threading
        from scripts.praxist_supervisor import _prescreen_async
        import cascade.typesafe_prescreen as tp
        # 允许导入; 打桩 prescreen_and_save 避免真实网络
        calls = []
        tp.prescreen_and_save = lambda *a, **k: calls.append(k) or {}

        prop_path = str(tmp_path / "p2.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({"status": "degraded", "skip_suggested": None}, f)

        # 打桩 thread.start 记录
        orig_start = threading.Thread.start
        monkeypatch.setattr(threading.Thread, "start", lambda self: orig_start(self))
        _prescreen_async({"variant_id": "v"}, prop_path, "rb")
        import time; time.sleep(0.3)
        assert len(calls) >= 1, "degraded 结果应重试 prescreen_and_save"
        del tp.prescreen_and_save  # 清理打桩, 避免污染其他测试
