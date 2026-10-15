"""SymbolLock 单元测试"""
import pytest
import subprocess
import time
from pathlib import Path
from scripts.lock_utils import SymbolLock


def test_symbol_lock_basic():
    """基本加锁/解锁"""
    lock_file = Path("task_FM/config/.test_basic.lock")
    assert not lock_file.exists(), "锁文件应不存在"
    
    with SymbolLock("test_basic"):
        assert lock_file.exists(), "锁文件应存在"
    
    assert not lock_file.exists(), "锁文件应在退出后清理"


def test_symbol_lock_timeout():
    """超时机制（跨进程测试，因 Linux fcntl 同进程可重入）"""
    with SymbolLock("test_timeout"):
        # 子进程尝试获取同一把锁，应超时失败
        result = subprocess.run(
            ["python3", "-c", 
             "from scripts.lock_utils import SymbolLock; "
             "SymbolLock('test_timeout', timeout=1, poll_interval=0.1).__enter__()"],
            capture_output=True, text=True,
            cwd="/home/abug/timesfm"
        )
        assert result.returncode != 0, "子进程应失败"
        assert "锁冲突" in result.stderr, f"应报锁冲突错误: {result.stderr}"


def test_symbol_lock_concurrent():
    """跨进程并发竞争与交接"""
    lock_file = Path("task_FM/config/.fg.lock")
    
    # 1. 主进程获取锁
    with SymbolLock("fg"):
        assert lock_file.exists()
        
        # 2. 子进程尝试获取，应该失败
        result = subprocess.run(
            ["python3", "-c", 
             "from scripts.lock_utils import SymbolLock; "
             "SymbolLock('fg', timeout=1, poll_interval=0.1).__enter__()"],
            capture_output=True, text=True,
            cwd="/home/abug/timesfm"
        )
        assert result.returncode != 0
        assert "锁冲突" in result.stderr
    
    # 3. 主进程释放锁后，锁文件应该被清理
    assert not lock_file.exists()
    
    # 4. 新进程可以成功获取锁
    result = subprocess.run(
        ["python3", "-c",
         "from scripts.lock_utils import SymbolLock; "
         "lock = SymbolLock('fg'); lock.__enter__(); "
         "print('SUCCESS'); lock.__exit__(None, None, None)"],
        capture_output=True, text=True,
        cwd="/home/abug/timesfm"
    )
    assert result.returncode == 0
    assert "SUCCESS" in result.stdout


def test_symbol_lock_path():
    """锁文件路径正确"""
    lock = SymbolLock("fg")
    assert str(lock.lock_file) == "task_FM/config/.fg.lock"
    
    lock = SymbolLock("CJ")
    assert str(lock.lock_file) == "task_FM/config/.cj.lock"


def test_symbol_lock_cleanup_on_exception():
    """异常退出后锁文件清理"""
    lock_file = Path("task_FM/config/.test_exception.lock")
    
    try:
        with SymbolLock("test_exception"):
            assert lock_file.exists()
            raise ValueError("模拟异常")
    except ValueError:
        pass
    
    assert not lock_file.exists(), "异常后锁文件应被清理"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
