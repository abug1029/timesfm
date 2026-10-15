"""冷却期 + 频率限制单元测试"""
import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta


def test_cooldown_blocks_regen():
    """冷却期阻止重生"""
    from scripts.sup_evidence import _remember_stall, _in_cooldown, _RECENTLY_REGENED_NO_ADVANCE
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 清空内存表
        _RECENTLY_REGENED_NO_ADVANCE.clear()
        
        # 记录停滞（会自动设置冷却期）
        _remember_stall('test_sym', tmpdir, '2026-10-08T10:00:00')
        
        # 验证在冷却期内
        assert _in_cooldown('test_sym', tmpdir), '应在冷却期内'


def test_cooldown_expires():
    """冷却期过期"""
    from scripts.sup_evidence import _in_cooldown, _RECENTLY_REGENED_NO_ADVANCE
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 手动设置冷却期为过去时间
        _RECENTLY_REGENED_NO_ADVANCE['test_expired'] = {
            'data_end': '2026-10-08T10:00:00',
            'cooldown_until': (datetime.now() - timedelta(hours=1)).isoformat(),
            'last_regen': None
        }
        
        # 验证冷却期已过期
        assert not _in_cooldown('test_expired', tmpdir), '冷却期应已过期'


def test_frequency_limit():
    """24h 频率限制"""
    from scripts.sup_evidence import _record_regen, _frequency_exceeded, _RECENTLY_REGENED_NO_ADVANCE
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 清空内存表
        _RECENTLY_REGENED_NO_ADVANCE.clear()
        
        # 记录重生
        _record_regen('test_freq', tmpdir)
        
        # 验证超过频率限制
        assert _frequency_exceeded('test_freq', tmpdir), '应超过频率限制'


def test_frequency_expires():
    """频率限制过期"""
    from scripts.sup_evidence import _frequency_exceeded, _RECENTLY_REGENED_NO_ADVANCE
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 手动设置 last_regen 为 25 小时前
        _RECENTLY_REGENED_NO_ADVANCE['test_freq_expired'] = {
            'data_end': '2026-10-08T10:00:00',
            'cooldown_until': None,
            'last_regen': (datetime.now() - timedelta(hours=25)).isoformat()
        }
        
        # 验证频率限制已过期
        assert not _frequency_exceeded('test_freq_expired', tmpdir), '频率限制应已过期'


def test_breaker_backward_compatible():
    """breaker 向后兼容旧格式"""
    from scripts.sup_evidence import _load_regen_breaker, _RECENTLY_REGENED_NO_ADVANCE
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        breaker_path = Path(tmpdir) / 'data' / 'cache' / 'baseline_regen_breaker.json'
        breaker_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入旧格式（str → str）
        with open(breaker_path, 'w', encoding='utf-8') as f:
            json.dump({'test_old': '2026-10-08T10:00:00'}, f)
        
        # 加载
        _RECENTLY_REGENED_NO_ADVANCE.clear()
        _load_regen_breaker(tmpdir)
        
        # 验证自动转换为 dict 格式
        entry = _RECENTLY_REGENED_NO_ADVANCE.get('test_old')
        assert isinstance(entry, dict), '应自动转换为 dict 格式'
        assert entry.get('data_end') == '2026-10-08T10:00:00', 'data_end 应保留'
        assert entry.get('cooldown_until') is None, 'cooldown_until 应为 None'
        assert entry.get('last_regen') is None, 'last_regen 应为 None'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
