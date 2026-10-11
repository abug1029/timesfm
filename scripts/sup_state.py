import glob
import json
import logging
import os
import sys
import time

import yaml

import sup_paths

def load_preregistry(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows

_CONFIRM_DATA_TTL_S = 1800
_CONFIRM_DATA_CACHE: dict[str, tuple] = {}   # symbol -> (queried_at, latest_dt | None)


def _latest_data_dt(symbol):
    """该品种 1H 数据末端（str，如 "2026-09-30 14:00:00"）；读不到返回 None。

    步② C（2026-10-07 裁定）拉取日重锚的新鲜度数据源；与 _confirm_data_ready
    共享 _CONFIRM_DATA_CACHE（30 分钟 TTL），pre-flight 查过的主循环闸门直接命中。
    """
    key = str(symbol).lower()
    now = time.time()
    hit = _CONFIRM_DATA_CACHE.get(key)
    if hit is not None and now - hit[0] <= _CONFIRM_DATA_TTL_S:
        return hit[1]
    latest = None
    try:
        from data.data_store import DataStore
        store = DataStore(key)
        try:
            h1 = store.get_main_contract_1h(limit=99999)
        finally:
            store.close()
        if h1 is not None and not h1.empty:
            latest = str(h1["dt"].astype(str).max())
    except Exception:
        latest = None
    _CONFIRM_DATA_CACHE[key] = (now, latest)
    return latest

def load_state():
    if not os.path.exists(sup_paths.STATE_PATH):
        st = {"cycles_done": 0, "last_run_dir": None, "last_run_id": None,
              "last_harvested_run_id": None, "paused_429": False, "phase": "fast",
              "llm_provider": "primary", "llm_route": "primary"}
    else:
        try:
            st = json.load(open(sup_paths.STATE_PATH, encoding="utf-8"))
        except Exception:
            st = {"cycles_done": 0}
    return _ensure_tokens_baseline(st)

def save_state(st):
    os.makedirs(os.path.dirname(sup_paths.STATE_PATH), exist_ok=True)
    tmp = sup_paths.STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, sup_paths.STATE_PATH)

def load_goal(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["goal"]

# ── cadence 默认值单一来源（技术债 L4，2026-10-08）────────────────────
# 与 scripts/praxist_goal.yaml 的 goal.cadence 保持一致。此前默认值散落三处且
# 互相矛盾：survivors_per_cycle 默认 2（yaml=3）、aligned_max_points 在
# 3493 默认为 400 而 2958 与函数签名为 600（yaml=600）。
# 键缺失时的静默回退正是漂移的成因 → 回退必留痕，且有测试锁死与 yaml 一致。
_CADENCE_DEFAULTS = {
    "survivors_per_cycle": 3,
    "aligned_max_points": 600,
}


def _cad_int(cad, key):
    """读 cadence 整数键；缺键回退 _CADENCE_DEFAULTS 并打 WARN 留痕。"""
    val = (cad or {}).get(key)
    if val is None:
        print("[WARN] goal.cadence.%s 缺失，回退默认 %d（应与 praxist_goal.yaml 一致）"
              % (key, _CADENCE_DEFAULTS[key]), file=sys.stderr)
        return _CADENCE_DEFAULTS[key]
    return int(val)


def _norm_search_policy(goal):
    """spec 2026-10-05 §6.1：search_policy ∈ {off, shadow, enforce}，缺省 off。

    - off：批准前后默认，收割行为与今日相同。
    - shadow：树检查照常求值，只进拒绝计数与决策日志（plan 2.9）。
    - enforce：§6.2 起的拒绝生效（plan 2.2）。
    非法值 fail-closed 回 off 并 warning 留痕（打错键不得静默改变收割行为）。
    精确匹配三个字面量、不做空白归一：带引号的病态值（如 " enforce"）必须
    留痕走 off，不得无痕激活拒绝（审核 NIT-1，2026-10-06）。
    goal 每 poll 热重载（main 循环 load_goal，2026-09-08 起与 budgets/
    cadence 同一热重载设计），宿主改键下一轮 poll 生效、无需重启
    （审核 MINOR-1 勘正：此前「需重启」的说法与事实相反）。
    """
    raw = (goal or {}).get("search_policy", "off")
    if raw is None:
        return "off"
    if raw in ("off", "shadow", "enforce"):
        return raw
    logging.warning("search_policy 非法值 %r → 按 off 处理"
                    "（合法值 off|shadow|enforce，精确匹配）", raw)
    return "off"

def _goal_target_symbols(goal):
    cad = (goal or {}).get("cadence") or {}
    raw = cad.get("target_symbols") or []
    out = []
    seen = set()
    for item in raw:
        sym = str(item).lower().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


# ── 目标品种集单源化（技术债 L3，2026-10-08）─────────────────────────
# 修复前同一语义有三份副本且互相矛盾：
#   1) praxist_goal.yaml goal.cadence.target_symbols —— 24 个（契约本身）
#   2) GOAL_SYMBOLS_SET 硬编码 9 个 —— 1★ 信用品种，10-02 goal 重写后已陈旧
#   3) build_snapshot 内 TARGET_SYMBOLS 硬编码 24 个 —— 与 yaml 恰好重复
# 三份副本必然漂移。本组函数把 yaml 立为唯一来源；缺失即启动失败
# （见 _assert_goal_symbols_contract），禁止静默回退硬编码。
_GOAL_YAML_DEFAULT = os.path.join(sup_paths.FM_ROOT, "scripts", "praxist_goal.yaml")
_GOAL_SYMBOLS_CACHE = None


def _assert_goal_symbols_contract(goal, path=None):
    """启动期目标品种集契约校验。缺键/空列表 → 抛错（fail loud）。

    静默回退到陈旧硬编码正是 "9 vs 24" 语义分裂能长期存活的成因：
    契约缺失必须让启动失败，而不是悄悄按旧口径跑。
    """
    syms = _goal_target_symbols(goal)
    if not syms:
        raise ValueError(
            "目标品种集契约缺失：%s 的 goal.cadence.target_symbols 为空。"
            "该字段是目标品种的唯一来源，禁止回退任何硬编码集合。"
            % (path or _GOAL_YAML_DEFAULT))
    return syms


def _load_goal_symbols(path=None):
    """读目标品种集并缓存。传 path 时绕过缓存（测试用）。"""
    global _GOAL_SYMBOLS_CACHE
    if path is None and _GOAL_SYMBOLS_CACHE is not None:
        return _GOAL_SYMBOLS_CACHE
    p = path or _GOAL_YAML_DEFAULT
    syms = frozenset(_assert_goal_symbols_contract(load_goal(p), p))
    if path is None:
        _GOAL_SYMBOLS_CACHE = syms
    return syms


def _reset_goal_symbols_cache():
    """测试钩子：清缓存，使 _load_goal_symbols 重新读 yaml。"""
    global _GOAL_SYMBOLS_CACHE
    _GOAL_SYMBOLS_CACHE = None

# 目标品种集：唯一来源 = praxist_goal.yaml goal.cadence.target_symbols。
# 2026-10-08（L3）删除 9 个 1★ 信用品种的硬编码——它与 yaml 的 24 个早已分裂，
# 且已退役的信用档（scheme.stars / list_by_stars）与"目标品种"本就是两个概念，不可互代。
GOAL_SYMBOLS_SET = _load_goal_symbols()

def _ensure_tokens_baseline(st):
    """Freeze historical disk usage as baseline on first known read; budget the delta."""
    if "tokens_baseline_m" in st:
        return st
    tok_m, tok_unknown = _read_token_m()
    if tok_unknown:
        return st
    st["tokens_baseline_m"] = float(tok_m)
    save_state(st)
    return st


def _token_spend_m(st, tok_m):
    """Tokens used since supervisor baseline (pre-existing disk totals excluded)."""
    if "tokens_baseline_m" not in st:
        return float(tok_m)
    return max(0.0, float(tok_m) - float(st["tokens_baseline_m"]))

def _read_token_m():
    """Best-effort. 若所有 generation_results 都缺 runtime_usage, 返回 (0.0, True)=unknown, 跳过 token 预算。"""
    total = 0.0
    saw = False
    for gr in glob.glob(os.path.join(sup_paths.FM_ROOT, "task_FM", "experiments", "run_*", "gen_*", "generation_results.json")):
        try:
            d = json.load(open(gr, encoding="utf-8"))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else [d]):
            u = (it or {}).get("runtime_usage") or {}
            tok = u.get("total_tokens")
            if tok is None:
                tok = (it or {}).get("total_tokens")
            if tok is None:
                continue
            saw = True
            total += float(tok)
    return round(total / 1e6, 3), (not saw)

def _merge_save(updates):
    fresh = load_state()
    fresh.update(updates)
    save_state(fresh)
    return fresh
