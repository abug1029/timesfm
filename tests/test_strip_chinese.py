# tests/test_strip_chinese.py
import pytest
from cascade.typesafe_prescreen import _strip_chinese

def test_strip_chinese_basic():
    """纯中文前缀 -> 前导空格被 strip 掉"""
    assert _strip_chinese('价差加速度转正 -> long') == '-> long'

def test_strip_chinese_mixed():
    """中英文混合：括号内中文被剥，括号内空格保留"""
    assert _strip_chinese('seasonal_supply_peak(7-9月出栏高峰) -> short') == 'seasonal_supply_peak(7-9 ) -> short'

def test_strip_chinese_fullwidth_punct():
    """全角标点剥离（v3 二次清洗）"""
    assert _strip_chinese('价差（利润） -> long') == '-> long'
    assert _strip_chinese('RSI(6)>80 超买 -> short') == 'RSI(6)>80 -> short'

def test_strip_chinese_preserve_ascii():
    """保留 ASCII、下划线、数字、半角括号"""
    assert _strip_chinese('oi_up_with_price -> long') == 'oi_up_with_price -> long'
    assert _strip_chinese('RSI(6)>80 -> short') == 'RSI(6)>80 -> short'

def test_strip_chinese_empty():
    """空串"""
    assert _strip_chinese('') == ''

def test_strip_chinese_pure_chinese():
    """纯中文 -> 全空 -> strip -> 空串"""
    assert _strip_chinese('价差加速度转正利润加速扩张') == ''
