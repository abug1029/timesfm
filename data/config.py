"""配置管理"""

import logging
import os
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
FM_ROOT = Path(__file__).resolve().parent.parent          # D:/FlyBuddy/FM_a
DB_DIR = FM_ROOT / "db"
MODELS_DIR = FM_ROOT / "models"
DB_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_under_root(path: str | Path, root: Path | None = None) -> Path:
    """相对路径锚定到 FM_ROOT，不依赖进程 cwd。"""
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    base = root or FM_ROOT
    return (base / p).resolve()

logger = logging.getLogger(__name__)

TIMESFM_HUB_ID = "google/timesfm-2.5-200m-pytorch"
TIMESFM_LOCAL_DIRNAME = "timesfm-2.5-200m-pytorch"


def _env_nonempty(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    val = raw.strip()
    return val or None


def _abs_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = FM_ROOT / p
    return Path(os.path.abspath(str(p)))


def _dir_nonempty(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def _has_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    if path.is_dir():
        try:
            return any(child.is_symlink() for child in path.iterdir())
        except OSError:
            return False
    return False


def _warn_if_symlink(path: Path) -> None:
    if _has_symlink(path):
        logger.warning(
            "TimesFM weights at %s are a symlink; isolation should copy, not symlink",
            path,
        )


def get_timesfm_model_path() -> str:
    """Resolve TimesFM weights: env, local dir if nonempty, else HF hub id."""
    for key in ("FM_TIMESFM_MODEL_PATH", "TIMESFM_MODEL_PATH"):
        raw = _env_nonempty(key)
        if raw is not None:
            path = _abs_path(raw)
            _warn_if_symlink(path)
            return str(path)

    raw = _env_nonempty("TIMESFM_WEIGHTS_DIR")
    if raw is not None:
        path = _abs_path(raw)
        if path.exists():
            _warn_if_symlink(path)
            return str(path)

    local = MODELS_DIR / TIMESFM_LOCAL_DIRNAME
    if _dir_nonempty(local):
        local = _abs_path(local)
        _warn_if_symlink(local)
        return str(local)

    return TIMESFM_HUB_ID

# ── 品种 → 交易所映射 ─────────────────────────────────
# 仅保留 20 个有 DB 的跟踪品种，新品种由用户手动添加
SYMBOL_EXCHANGE_MAP = {
    # 上海期货交易所 (SHFE)
    "rb": "SHFE", "fu": "SHFE", "bu": "SHFE",
    "sp": "SHFE", "ss": "SHFE", "ao": "SHFE",
    # 大连商品交易所 (DCE)
    "i": "DCE", "jm": "DCE", "m": "DCE",
    "p": "DCE", "y": "DCE", "eg": "DCE", "jd": "DCE", "lh": "DCE", "pp": "DCE", "bz": "DCE", "eb": "DCE",
    # 郑州商品交易所 (CZCE)
    "ma": "CZCE", "ta": "CZCE", "cf": "CZCE", "sr": "CZCE",
    "cj": "CZCE", "ur": "CZCE", "fg": "CZCE", "px": "CZCE", "oi": "CZCE", "sh": "CZCE",
    # 上海国际能源交易中心 (INE)
    "sc": "INE",
}

# 品种中文名
SYMBOL_NAMES = {
    "rb": "螺纹钢", "fu": "燃料油", "bu": "沥青",
    "sp": "纸浆", "ss": "不锈钢", "ao": "氧化铝",
    "i": "铁矿石", "jm": "焦煤", "m": "豆粕",
    "p": "棕榈油", "y": "豆油", "eg": "乙二醇", "jd": "鸡蛋", "lh": "生猪", "pp": "聚丙烯",
    "ma": "甲醇", "ta": "PTA", "cf": "棉花", "sr": "白糖",
    "cj": "红枣", "ur": "尿素", "fg": "玻璃",
    "px": "对二甲苯", "bz": "纯苯", "eb": "苯乙烯", "oi": "菜油", "sh": "烧碱",
    "sc": "原油",
}

# 默认跟踪品种
# 核心品种池
DEFAULT_SYMBOLS = [
    # 郑商所
    "cf", "sr", "ta", "ma", "cj", "fg", "ur", "px", "oi", "sh",
    # 上期所
    "rb", "fu", "bu", "ss", "sp", "ao",
    # 大商所
    "i", "jm", "jd", "lh", "m", "p", "y", "eg", "pp", "bz", "eb",
    # 能源中心 (INE)
    "sc",
]

# ── 技术指标参数 ─────────────────────────────────────
INDICATOR_PARAMS = {
    "ma": [5, 10, 20, 60],
    "ema": [12, 26],
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "rsi": [6, 12, 24],
    "kdj": {"n": 9, "m1": 3, "m2": 3},
    "boll": {"period": 20, "std_dev": 2},
    "atr": [14],
    "cci": [14],
    "oi_analysis": {
        "trend_window": 5,
        "corr_window": 20,
    },
}

# ── 工具函数 ──────────────────────────────────────────

def get_db_path(symbol: str) -> Path:
    """获取品种的 SQLite 数据库路径"""
    symbol = symbol.lower()
    return DB_DIR / f"futures_{symbol}.db"

def get_exchange(symbol: str) -> str:
    """获取品种所属交易所"""
    sym = symbol.upper() if symbol.upper() in SYMBOL_EXCHANGE_MAP else symbol.lower()
    return SYMBOL_EXCHANGE_MAP.get(sym, SYMBOL_EXCHANGE_MAP.get(sym.lower(), ""))

def get_name(symbol: str) -> str:
    """获取品种中文名"""
    return SYMBOL_NAMES.get(symbol.lower(), SYMBOL_NAMES.get(symbol, symbol))


def parse_contract_info(contract_code: str) -> dict:
    """
    解析合约代码
    'rb2509' → {'product': 'rb', 'year': 2025, 'month': 9}
    'IF2603' → {'product': 'IF', 'year': 2026, 'month': 3}
    'CF_CONT' → {'product': 'cf', 'year': None, 'month': None}  (主力连续)
    """
    import re
    code = contract_code.lower()

    # 处理 _CONT / _MAIN 格式 (连续合约标记)
    if code.endswith('_cont') or code.endswith('_main'):
        product = code.rsplit('_', 1)[0]
        return {"product": product, "year": None, "month": None}

    m = re.match(r'^([a-z]+)(\d{4})$', code)
    if not m:
        return {"product": code, "year": None, "month": None}
    product = m.group(1)
    ym = m.group(2)
    year = 2000 + int(ym[:2])
    month = int(ym[2:])
    return {"product": product, "year": year, "month": month}
