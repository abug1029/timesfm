#!/usr/bin/env python3
"""品种级排他锁工具（与 generate_baseline_points.py 锁逻辑对齐）"""
import fcntl
import time
from pathlib import Path

class SymbolLock:
    """品种级排他锁（context manager）
    
    用法：
        with SymbolLock("fg", root="."):
            # 执行需要锁保护的操作
            ...
    
    特性：
    - 锁路径：task_FM/config/.{sym}.lock（与 gbp 一致）
    - 等待策略：LOCK_NB 轮询，最多等 timeout 秒（默认 3600s = 1h）
    - 60s 节流等待日志（与 gbp 一致）
    - 自动清理：退出时释放锁并删除锁文件
    """
    
    def __init__(self, symbol: str, root: str = ".", timeout: int = 3600, poll_interval: int = 5):
        """
        Args:
            symbol: 品种代码（会自动转小写）
            root: 项目根目录
            timeout: 锁等待超时（秒），默认 3600s = 1h
            poll_interval: 轮询间隔（秒），默认 5s
        """
        self.symbol = symbol.lower()
        self.lock_file = Path(root) / "task_FM" / "config" / f".{self.symbol}.lock"
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.lock_fp = None
        self._last_log_time = 0
    
    def __enter__(self):
        """获取锁"""
        self.lock_fp = open(self.lock_file, "w")
        start_time = time.time()
        while True:
            try:
                fcntl.flock(self.lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except IOError:
                elapsed = time.time() - start_time
                if elapsed >= self.timeout:
                    self.lock_fp.close()
                    raise RuntimeError(f"品种 {self.symbol.upper()} 锁冲突（等待 {self.timeout}s）")
                # 60s 节流等待日志（与 gbp 一致）
                if elapsed - self._last_log_time >= 60:
                    print(f"[INFO] 等待品种 {self.symbol.upper()} 锁释放... ({int(elapsed)}s/{self.timeout}s)")
                    self._last_log_time = elapsed
                time.sleep(self.poll_interval)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """释放锁并清理"""
        if self.lock_fp:
            fcntl.flock(self.lock_fp.fileno(), fcntl.LOCK_UN)
            self.lock_fp.close()
            if self.lock_file.exists():
                self.lock_file.unlink()
