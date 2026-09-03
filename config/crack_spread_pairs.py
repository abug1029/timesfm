"""跨品种 crack spread 品种配对配置 (Phase 8a)

Phase 8a: PX-TA 芳烃链 (PTA 加工费 = TA - 0.655·PX)
Phase 8b 预留: SC 采集就绪后加 fu/bu -> sc (需 bbl->吨换算)
"""
from typing import Optional, Tuple

CRACK_SPREAD_PAIRS: dict[str, dict] = {
    "ta": {"feedstock": "px", "ratio": 0.655},
    "fu": {"feedstock": "sc", "ratio": 4.7191},   # 2026-08-01 OLS 标定 (滚动500, 中位数)
    "bu": {"feedstock": "sc", "ratio": 2.8067},   # 2026-08-01 OLS 标定 (滚动500, 中位数)
}


def get_crack_pair(symbol: str) -> Optional[Tuple[str, float]]:
    """返回 (feedstock_sym, ratio) 或 None(无配对)"""
    cfg = CRACK_SPREAD_PAIRS.get(symbol.lower())
    if cfg is None:
        return None
    return (cfg["feedstock"], cfg["ratio"])
