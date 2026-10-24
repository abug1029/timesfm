"""
品种板块划分 — 全项目唯一板块表。

供 Regime / VolRisk R1 / Neutral A/B Domain-Shift 审计共用。
禁止在脚本内再硬编码 black/chem/agri 集合。
"""

from __future__ import annotations

# 板块 → 品种（小写）
SECTORS: dict[str, list[str]] = {
    # 黑色系
    "black_metals": ["rb", "i", "jm", "ss"],
    # 能化
    "energy_chem": ["fu", "bu", "eg", "ma", "ta", "sp", "sh"],
    # 农产品 + 软商品
    "agri": ["m", "p", "cf", "sr", "jd", "lh", "cj", "ur", "fg", "ao"],
}

SECTOR_NAMES = {
    "black_metals": "黑色系",
    "energy_chem": "能化",
    "agri": "农产品",
}


def get_sector_symbols(sector: str) -> list[str]:
    key = sector.lower().strip()
    if key not in SECTORS:
        raise KeyError(f"未知板块 {sector!r}，可选: {list(SECTORS)}")
    return list(SECTORS[key])


def list_sectors() -> list[str]:
    return list(SECTORS.keys())


def sector_of(sym: str) -> str:
    """返回品种所属板块 key；未知则 'other'。"""
    s = sym.lower().strip()
    for name, members in SECTORS.items():
        if s in members:
            return name
    return "other"


def black_symbols() -> set[str]:
    return set(SECTORS["black_metals"])


def chem_symbols() -> set[str]:
    return set(SECTORS["energy_chem"])


def agri_symbols() -> set[str]:
    return set(SECTORS["agri"])
