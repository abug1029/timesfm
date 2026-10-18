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

# ── Task 2: _is_shell_pd 单元测试 ──────────────────────────
from cascade.typesafe_prescreen import _is_shell_pd

def test_is_shell_pd_typical_shell():
    """典型空壳：仅剩方向词 long/short"""
    # "-> long, -> short" -> 剥 - > , 空格 -> "longshort" len=9 < 12 -> True
    assert _is_shell_pd("-> long, -> short") == True

def test_is_shell_pd_short_formula():
    """短公式空壳：RSI(6)>80 -> short -> core='RSI680short' len=11 < 12"""
    assert _is_shell_pd("RSI(6)>80 -> short") == True

def test_is_shell_pd_valid_pd():
    """有效 PD：含条件描述，下划线保留"""
    # "oi_up_with_price -> long" -> 剥 -> 空格 -> "oi_up_with_pricelong" len=20 >= 12
    assert _is_shell_pd("oi_up_with_price -> long") == False
    # "seasonal_supply_peak(7-9 ) -> short" -> core len=29 >= 12
    assert _is_shell_pd("seasonal_supply_peak(7-9 ) -> short") == False

def test_is_shell_pd_threshold_boundary():
    """阈值边界：用无方向词纯 core 串，避免方向词干扰长度"""
    assert _is_shell_pd("abcdefghijk") == True       # len=11 < 12
    assert _is_shell_pd("abcdefghijkl") == False      # len=12 >= 12
    assert _is_shell_pd("abcdefghijklm") == False     # len=13 >= 12

def test_is_shell_pd_empty():
    """空串 -> core len=0 < 12 -> True"""
    assert _is_shell_pd("") == True
