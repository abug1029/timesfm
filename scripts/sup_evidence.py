import glob
import json
import logging
import math
import os
import shutil
import sys
import fcntl
import atexit
from datetime import datetime, timezone
from pathlib import Path

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
del _repo_root

# Task 8: 使所有顶层导入可选，以便测试可以 monkeypatch 而不需要所有依赖
try:
    import registry_lib as rl
except ImportError:
    rl = None  # type: ignore

try:
    import search_trees as st
except ImportError:
    st = None  # type: ignore

try:
    from cascade import experiment_fingerprint as ef
except ImportError:
    ef = None  # type: ignore

try:
    from cascade.cov_family import ALLOWED_FAMILIES
except ImportError:
    ALLOWED_FAMILIES = None  # type: ignore

try:
    import sup_paths
except ImportError:
    sup_paths = None  # type: ignore

try:
    import sup_state
except ImportError:
    sup_state = None  # type: ignore

try:
    import sup_lifecycle
except ImportError:
    sup_lifecycle = None  # type: ignore

# 批次 B：tier 值域守卫（Q2=b，N10 语义消歧）
VALID_TIER_VALUES = frozenset({"S", "A", "B", "C", "D"})

def is_valid_tier(v, log=None):
    """校验 tier 值域，防止非法值混入。

    Args:
        v: variant dict（调用方保证非 None）。
        log: 可选日志函数。模块级调用时提供，
             build_snapshot 内不传（该作用域没有 log 路径）。
    """
    tier = v.get("tier")
    if tier is None:
        return False
    if tier not in VALID_TIER_VALUES:
        if log is not None:
            log("tier_domain_violation", f"variant={v.get('variant_id', 'unknown')} tier={tier}")
        return False
    return True

def symbol_goal_tier(variants, symbol, max_history_n=None):
    """三档。不读文件。

    计入：counts_as_success 为真，或已落盘的 run_label 恰好是 confirmed 且 fdr_pass 为真。
    不补写裁决里没有的分类字段。
    """
    import preregistry as _prereg

    n_confirm_required = _prereg.n_confirm_required_for_symbol(symbol)
    n_confirmed_variants = 0
    for row in variants:
        try:
            ok = _prereg.counts_as_success(row) is True
        except (TypeError, ValueError):
            ok = False
        getter = getattr(row, "get", None)
        if not ok and callable(getter):
            ok = (
                getter("run_label") == "confirmed"
                and getter("fdr_pass") is True
            )
        if ok:
            n_confirmed_variants += 1
    if n_confirmed_variants >= 1:
        tier = "可预测"
    elif max_history_n is not None and max_history_n < n_confirm_required:
        tier = "当前不可验证"
    else:
        tier = "需更多样本"
    return {
        "tier": tier,
        "n_confirmed_variants": n_confirmed_variants,
    }

def build_snapshot(registry_path, cycles_done, cpu_hours_used, tokens_used_m):
    # 跨协议不可比的裁决不得进入目标统计：无指纹 / 旧指纹的行一律排除。
    # jsonl 不改写，完整历史仍可用 rl.load_snapshot(path) 不带参数读到。
    snap = rl.load_snapshot(registry_path,
                            only_protocol=_current_protocol_fingerprint())
    passing = rl.pass_variants(snap)
    symbols_hit = {v["symbol"] for v in passing}
    families_hit = {
        v.get("cov_family")
        for v in passing
        if v.get("cov_family")
        and v.get("cov_family") != "unknown"
    } & ALLOWED_FAMILIES
    n_goal_symbols_hit = len(symbols_hit & sup_state.GOAL_SYMBOLS_SET)
    n_unique_pass_variants = len({v["variant_id"] for v in passing})
    n_families_hit = len(families_hit)
    # v23: v2 过门变体的 min dir_acc (pass_variants = gate_pass 且 fdr_pass;
    # v1 legacy: gate_pass 且 ev>0);
    # 无过门变体 (或无数值 dir_acc) 时为 None, goal 条件用 is not None 防护判 unmet 而非 eval error。
    pass_dir_accs = [float(v["dir_acc"]) for v in passing
                     if isinstance(v.get("dir_acc"), (int, float))]
    min_pass_variant_dir_acc = min(pass_dir_accs) if pass_dir_accs else None
    # Phase 1: 基础质量门槛
    n_gate_pass_variants = len([v for v in snap.get("variants", {}).values() if v.get("gate_pass")])
    gate_pass_dir_accs = [float(v["dir_acc"]) for v in snap.get("variants", {}).values()
                          if v.get("gate_pass") and isinstance(v.get("dir_acc"), (int, float))]
    avg_dir_acc_gate_pass = sum(gate_pass_dir_accs) / len(gate_pass_dir_accs) if gate_pass_dir_accs else 0.0

    # 批次 B：tier 值域守卫（Q2=b，键名为现有 tier）

    # Phase 2: 高质量变体
    n_tier_a_or_b = len([v for v in snap.get("variants", {}).values()
                         if is_valid_tier(v) and v.get("tier") in ["A", "B"]])
    n_symbols_represented = len(symbols_hit)
    
    # Phase 3: 稳定性验证 (placeholder - need actual multi-seed validation data)
    n_validated_multi_seed = 0  # TODO: implement multi-seed validation tracking
    decay_below_threshold = 0  # TODO: implement decay tracking
    
    # 目标品种集：与 GOAL_SYMBOLS_SET 同源（L3：原为第二份硬编码 24 个，
    # 与 yaml 恰好重复 —— 两份副本必然漂移）
    TARGET_SYMBOLS = set(sup_state.GOAL_SYMBOLS_SET)
    
    # 按品种统计指标
    symbol_stats = {}
    for symbol in TARGET_SYMBOLS:
        symbol_variants = [
            v for v in snap.values()
            if isinstance(v, dict) and v.get("symbol") == symbol
        ]
        symbol_gate_pass = [v for v in symbol_variants if v.get("gate_pass")]
        symbol_tier_a_b = [v for v in symbol_variants if is_valid_tier(v) and v.get("tier") in ["A", "B"]]
        
        # Phase 1: 基础质量门槛
        n_gate_pass = len(symbol_gate_pass)
        gate_pass_dir_accs = [float(v["dir_acc"]) for v in symbol_gate_pass 
                              if isinstance(v.get("dir_acc"), (int, float))]
        avg_dir_acc = sum(gate_pass_dir_accs) / len(gate_pass_dir_accs) if gate_pass_dir_accs else 0.0
        
        # Phase 2: 高质量变体
        n_tier_a_b = len(symbol_tier_a_b)
        
        # Phase 3 的 multi_seed / decay 仍未实现，不在这里发明通过条件。
        n_validated = 0
        n_decay = 0

        judged = symbol_goal_tier(symbol_variants, symbol)
        phase1_pass = judged["tier"] == "可预测"
        phase2_pass = False
        phase3_pass = False

        symbol_stats[symbol] = {
            "n_gate_pass": n_gate_pass,
            "avg_dir_acc": avg_dir_acc,
            "n_tier_a_b": n_tier_a_b,
            "n_validated": n_validated,
            "n_decay": n_decay,
            "phase1_pass": phase1_pass,
            "phase2_pass": phase2_pass,
            "phase3_pass": phase3_pass,
            "tier": judged["tier"],
            "n_confirmed_variants": judged["n_confirmed_variants"],
        }
    
    # 检查所有品种是否都通过各阶段
    all_symbols_pass_phase1 = all(stats["phase1_pass"] for stats in symbol_stats.values())
    all_symbols_pass_phase2 = all(stats["phase2_pass"] for stats in symbol_stats.values())
    all_symbols_pass_phase3 = all(stats["phase3_pass"] for stats in symbol_stats.values())
    
    # 统计通过各阶段的品种数
    n_symbols_pass_phase1 = sum(1 for stats in symbol_stats.values() if stats["phase1_pass"])
    n_symbols_pass_phase2 = sum(1 for stats in symbol_stats.values() if stats["phase2_pass"])
    n_symbols_pass_phase3 = sum(1 for stats in symbol_stats.values() if stats["phase3_pass"])
    
    return {
        "variants": snap,
        "symbols_hit": symbols_hit,
        "families_hit": families_hit,
        "cycles_done": cycles_done,
        "cpu_hours_used": cpu_hours_used,
        "tokens_used_m": tokens_used_m,
        # Legacy metrics (keep for backward compatibility)
        "n_goal_symbols_hit": n_goal_symbols_hit,
        "n_unique_pass_variants": n_unique_pass_variants,
        "n_families_hit": n_families_hit,
        "min_pass_variant_dir_acc": min_pass_variant_dir_acc,
        # Per-symbol metrics
        "symbol_stats": symbol_stats,
        "target_symbols": TARGET_SYMBOLS,
        # Phase pass status (all symbols)
        "all_symbols_pass_phase1": all_symbols_pass_phase1,
        "all_symbols_pass_phase2": all_symbols_pass_phase2,
        "all_symbols_pass_phase3": all_symbols_pass_phase3,
        # Phase pass counts
        "n_symbols_pass_phase1": n_symbols_pass_phase1,
        "n_symbols_pass_phase2": n_symbols_pass_phase2,
        "n_symbols_pass_phase3": n_symbols_pass_phase3,
        "n_target_symbols": len(TARGET_SYMBOLS),
    }

def collect_proposed_variant_ids(root=None):
    """Parse results/**/proposals/*.json into {symbol_cov}."""
    root = root or sup_paths.FM_ROOT
    out = set()
    pattern = os.path.join(root, "task_FM", "experiments", "run_*", "results",
                           "**", "proposals", "*.json")
    for sp in glob.glob(pattern, recursive=True):
        try:
            with open(sp, encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            continue
        if not isinstance(p, dict):
            continue
        symbol = str(p.get("symbol") or "").lower().strip()
        cov = str(p.get("cov_override") or "").strip()
        if symbol and cov:
            out.add("%s_%s" % (symbol, cov))
    return out

def _protocol_section_line(fp):
    """节级指纹。没有主协议组时写 none，避免编造一代协议。"""
    if isinstance(fp, str) and fp:
        return "protocol %s" % fp[:12]
    return "protocol (none)"

def materialize_known_verdicts(snapshot, dest_path, *, proposed_ids=None,
                               status_map=None, queue_ids=None, root=None,
                               excluded_items=None, commitments_path=None):
    if status_map is None:
        status_map = load_symbol_status()
    if queue_ids is None:
        queue_ids = rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS)
    if proposed_ids is None:
        proposed_ids = collect_proposed_variant_ids(root or sup_paths.FM_ROOT)

    lines = ["## Known aligned verdicts (supervisor snapshot)",
             "v2 pass (gate_pass=True AND fdr_pass=True AND p_value NOT NULL AND run_mode='confirmation'): already solved, do NOT re-propose.",
             "v1 legacy: pass by ev>0 (legacy econ caliber, schema=v1 entries only).",
             "hard-gate-but-losing (gate_pass=True but not fdr_pass): 过硬门但未过统计检验; not a success; do not re-propose as solved.",
             "DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.",
             ""]
    items = list(snapshot.values()) if isinstance(snapshot, dict) else []

    # ── N3: _primary_fp 排名守卫 (spec W1.5「排序与比较的守卫」) ──
    # 不同 protocol_fingerprint 的 dir_acc 不可直接比较 (协议不同 = 评估口径不同).
    # 主协议组选择: 优先含 confirmation 运行的组, 否则成员最多的组.
    # 其余协议组的 verdict 不进主排名, 单独标注.
    _proto_groups = {}
    for _v in items:
        _fp = _v.get("protocol_fingerprint")
        _proto_groups.setdefault(_fp, []).append(_v)
    _primary_fp = next(
        (fp for fp, g in _proto_groups.items()
         if any(str(_v.get("run_mode")) == "confirmation" for _v in g)),
        None)
    if _primary_fp is None and _proto_groups:
        _primary_fp = max(_proto_groups, key=lambda f: len(_proto_groups[f]))
    _items = sorted(_proto_groups.get(_primary_fp, items),
                    key=lambda v: str(v.get("symbol") or "").lower())
    # 按品种预计算主协议组 best dir_acc (排名字段只取主组).
    _best_by_sym = {}
    for v in _items:
        _sym = str(v.get("symbol") or "").lower()
        _da = v.get("dir_acc")
        if isinstance(_da, (int, float)) and not isinstance(_da, bool):
            _da = float(_da)
            if _da == _da and -1e308 < _da < 1e308:
                if _sym not in _best_by_sym or _da > _best_by_sym[_sym]:
                    _best_by_sym[_sym] = _da

    # ── T1 (2026-10-05): 旧协议先验注记（仅上下文，不进主排名） ──
    # excluded_items: 调用侧传入被 only_protocol 过滤掉的行（dict 或 list）。
    # None 时从输入内非主协议组兜底推导——只认「有旧指纹」的行；
    # fp=None 的 v1 legacy 行不进注记（无指纹不构成「旧协议」，也不是当前证据）。
    if excluded_items is None:
        _excl = []
        for _fp, _grp in _proto_groups.items():
            if _fp == _primary_fp or _fp is None:
                continue
            _excl.extend(_grp)
    else:
        _excl = (list(excluded_items.values())
                 if isinstance(excluded_items, dict)
                 else list(excluded_items))
        # 安全网：fp == 主协议的行不得进注记区（调用侧混入时防重复计入）。
        _excl = [v for v in _excl if isinstance(v, dict)
                 and v.get("protocol_fingerprint") != _primary_fp]
    _excl_fp_rows = [v for v in _excl
                     if isinstance(v.get("protocol_fingerprint"), str)
                     and v.get("protocol_fingerprint")]
    _excl_fp_groups = sorted({v["protocol_fingerprint"] for v in _excl_fp_rows})
    # 头部锚点：快照时间 + 主协议指纹 + 源 registry mtime（peer 引用证据时的出处）。
    try:
        _reg_mtime = datetime.fromtimestamp(
            os.path.getmtime(sup_paths.REGISTRY)).isoformat()
    except Exception:
        _reg_mtime = "n/a"
    _fp8 = (_primary_fp[:8]
            if isinstance(_primary_fp, str) and _primary_fp else "none")
    lines.append("generated_at=%s protocol_fp8=%s registry_mtime=%s"
                 % (datetime.now().isoformat(), _fp8, _reg_mtime))
    # ## Symbol status (full GOAL_SYMBOLS_SET, never truncated)
    lines.append("## Symbol status")
    lines.append(_protocol_section_line(_primary_fp))
    lines.append(
        "按协议指纹分组排名；另有 %d 个协议组的 %d 条 verdict 未进主排名"
        "（见 Old-protocol priors，仅上下文）。"
        % (len(_excl_fp_groups), len(_excl_fp_rows)))
    for sym in sorted(sup_state.GOAL_SYMBOLS_SET):
        n_ok = 0
        n_pass = 0
        for v in items:
            if str(v.get("symbol") or "").lower() != sym:
                continue
            if v.get("status", "ok") == "ok":
                n_ok += 1
            if v.get("gate_pass"):
                n_pass += 1
        best = _best_by_sym.get(sym)
        rec = status_map.get(sym) or {}
        sym_status = str(rec.get("status") or "ACTIVE").upper()
        if sym_status == "DEAD":
            label = "SYMBOL_DEAD"
        elif sym_status == "HOLD":
            label = "HOLD"
        else:
            label = "ACTIVE"
        best_s = ("%.3f" % best) if best is not None else "n/a"
        line = "- %s: %s, n_ok=%d, n_pass=%d, best=%s" % (
            sym, label, n_ok, n_pass, best_s)
        reason = rec.get("reason")
        if reason:
            line += " — %s" % reason
        if sym_status == "DEAD":
            line += " — 不要提案"
        elif sym_status == "HOLD":
            hg = rec.get("hold_generations")
            if hg is not None:
                line += " — 暂停 %s 代" % hg
        lines.append(line)
    lines.append("")
    clue_lines = _effective_clue_lines(items)
    if clue_lines and clue_lines[0].startswith("## Effective clues"):
        clue_lines.insert(1, _protocol_section_line(_primary_fp))
    lines.extend(clue_lines)
    lines.extend(_diag_sample_lines(items, _primary_fp))
    lines.extend(st.render_open_trees(
        st.load_tree_index(commitments_path or sup_paths.SEARCH_COMMITMENTS_PATH),
        snapshot if isinstance(snapshot, dict) else {}))
    lines.extend(_dead_family_lines(items, _primary_fp))
    lines.extend(_cross_matrix_lines(_items, _primary_fp))
    lines.extend(_old_protocol_prior_lines(_excl_fp_rows))
    lines.extend(_locked_window_lines(
        snapshot if isinstance(snapshot, dict) else {}, root))

    # ## Do not re-propose; source priority: verdict > queue > proposed
    lines.append("## Do not re-propose (variant_id)")
    lines.append(_protocol_section_line(_primary_fp))
    tagged = {}
    for vid in (proposed_ids or set()):
        tagged[str(vid)] = "proposed"
    for vid in (queue_ids or set()):
        tagged[str(vid)] = "queue"
    if isinstance(snapshot, dict):
        for vid in snapshot.keys():
            tagged[str(vid)] = "verdict"
    all_vids = sorted(tagged.keys())
    total = len(all_vids)
    for vid in all_vids[:80]:
        lines.append("- %s (%s)" % (vid, tagged[vid]))
    if total > 80:
        lines.append("truncated=%d" % total)
    lines.append("")

    def _da_key(v):
        da = v.get("dir_acc")
        # v23: 排序键 dir_acc 降序, 数值缺失排最后; ev 仅作展示列
        return -(float(da) if isinstance(da, (int, float)) else float("-inf"))

    items.sort(key=lambda v: (not v.get("gate_pass", False), _da_key(v)))
    if not items:
        lines.append("(no aligned verdicts yet)")
    # items 已按 (gate_pass 优先, dir_acc 降序) 排序。截断只能切尾部：
    # gate_pass 行是「已解出、不要再提」的集合，切掉它会让 peer 重复提案。
    _shown = [v for v in items if v.get("gate_pass")]
    _shown += [v for v in items if not v.get("gate_pass")][:max(0, 80 - len(_shown))]
    for v in _shown:
        gate = bool(v.get("gate_pass", False))
        ev = float(v.get("ev") or 0)
        status = v.get("status", "ok")
        v2 = v.get("schema") == "fm.aligned_verdict.v2"
        promoted = (bool(v.get("fdr_pass")) or bool(v.get("migrated_pass"))) if v2 else (ev > 0)
        if gate and promoted:
            state = "v2_pass" if v2 else "v1_legacy_pass"
        elif gate:
            state = "hard-gate-but-losing"
        elif status == "ok":
            state = "DEAD"
        else:
            state = status
        own_fp = v.get("protocol_fingerprint")
        vid = v.get("variant_id")
        if isinstance(own_fp, str) and own_fp:
            vid = "[%s] %s" % (own_fp[:12], vid)
        lines.append("- {0}: {1}, gate_pass={2}, ev={3}, n={4}, status={5}".format(
            vid, state, v.get("gate_pass"), v.get("ev"),
            v.get("n"), status))
    if len(items) > len(_shown):
        lines.append("verdicts_truncated=%d" % (len(items) - len(_shown)))
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines) + '\n')

def _verdict_family(v):
    fam = str(v.get("cov_family") or "").strip()
    return fam or str(v.get("cov_override") or "").strip()

def _finite_dir_acc(v):
    da = v.get("dir_acc")
    if isinstance(da, (int, float)) and not isinstance(da, bool):
        da = float(da)
        if da == da and -1e308 < da < 1e308:
            return da
    return None

def _has_prior_failure(snapshot, symbol, cov):
    """True if snapshot has an ok+unpassed+confirmable verdict on this (symbol, cov) PAIR.

    2026-10-03：只认可确认 DM 的失败（见 _is_confirmable_failure）。描述性行不是
    检验结论，不能用来否决新提案——否则确认产出前几乎每份提案都会被
    no_failure_delta 拒收（实测单轮拒 1,922 份、可用候选 7 轮内 123→47）。

    2026-10-08（技术债 L2）：由 symbol OR cov 单键命中改为 (symbol, cov) 配对 AND。
    旧语义下"豆粕的 vor 已确认失败"会连"豆粕换 oi"和"菜粕换 vor"一起否决，
    污染半径远大于文档描述。配对后只有**同一品种的同一协变量**已确认失败才要求
    增量论证；跨维度重复探索由 dedup 门、Do-not-re-propose 段与 locked-window 兜底。
    """
    sym_key = str(symbol or "").lower()
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if not _is_confirmable_failure(v):
            continue
        if str(v.get("symbol") or "").lower() != sym_key:
            continue
        if str(v.get("cov_override") or "") != cov:
            continue
        return True
    return False

def _effective_clue_lines(items):
    """Live passing / near-miss / weak-family clues. Never a frozen menu."""
    fam_ok = {}
    fam_pass = {}
    near = []
    for v in items:
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        fam = _verdict_family(v)
        if fam:
            fam_ok[fam] = fam_ok.get(fam, 0) + 1
            if v.get("gate_pass"):
                fam_pass[fam] = fam_pass.get(fam, 0) + 1
        da = _finite_dir_acc(v)
        if da is None or v.get("gate_pass"):
            continue
        emin = v.get("effective_min")
        if not (isinstance(emin, (int, float)) and not isinstance(emin, bool)):
            emin = 0.52
        else:
            emin = float(emin)
        if 0.49 <= da < emin:
            near.append((v.get("variant_id"), da, emin))
    lines = ["## Effective clues (from snapshot, not a frozen menu)",
             "仅当前协议，旧协议已滤除；分母含描述性裁决。",
             "### Passing families"]
    passing = [(fam, fam_pass[fam]) for fam in fam_pass if fam_pass[fam] > 0]
    passing.sort(key=lambda x: (-x[1], x[0]))
    if passing:
        for fam, n in passing:
            n_ok = fam_ok.get(fam, 0)
            lines.append("- %s: %d/%d gate_pass%s"
                         % (fam, n, n_ok, " low-n" if n_ok < 10 else ""))
    else:
        lines.append("- (none yet)")
    lines.append("### Near-miss (0.49 <= dir_acc < effective_min)")
    if near:
        near.sort(key=lambda x: -x[1])
        for vid, da, emin in near[:12]:
            lines.append("- %s dir_acc=%.3f min=%.3f" % (vid, da, emin))
    else:
        lines.append("- (none)")
    lines.append("### Weak families (>=4 ok, 0 pass)")
    lines.append("ok 含描述性裁决。family_dead 只看 Dead families。")
    weak = [fam for fam, n in fam_ok.items()
            if n >= 4 and fam_pass.get(fam, 0) == 0]
    weak.sort()
    if weak:
        for fam in weak:
            n_ok = fam_ok[fam]
            lines.append("- %s: 0/%d gate_pass%s"
                         % (fam, n_ok, " low-n" if n_ok < 10 else ""))
    else:
        lines.append("- (none)")
    lines.append("")
    return lines

def _cross_matrix_lines(items, primary_fp, max_rows=None):
    """品种×族交叉矩阵（pass/n，仅当前协议主组）— T1 2026-10-05。

    只列有 ok 裁决的品种；每格 `fam p/n`，n<10 追加 low-n（不出现裸比率）。
    品种行数超出预算截断并注明。
    """
    counts = {}
    for v in items:
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        sym = str(v.get("symbol") or "").lower()
        fam = _verdict_family(v)
        if not sym or not fam:
            continue
        p, n = counts.get((sym, fam), (0, 0))
        counts[(sym, fam)] = (p + (1 if v.get("gate_pass") else 0), n + 1)
    lines = ["## Symbol x family (pass/n, current protocol)",
             _protocol_section_line(primary_fp)]
    if not counts:
        lines.append("- (none)")
        lines.append("")
        return lines
    if max_rows is None:
        max_rows = CROSS_MATRIX_MAX_ROWS
    try:
        max_rows = int(max_rows)
    except (TypeError, ValueError):
        max_rows = 0
    syms = sorted({s for (s, _f) in counts})
    shown = syms[:max(0, max_rows)]
    for sym in shown:
        fams = sorted(f for (s, f) in counts if s == sym)
        cells = []
        for fam in fams:
            p, n = counts[(sym, fam)]
            cell = "%s %d/%d" % (fam, p, n)
            if n < 10:
                cell += " low-n"
            cells.append(cell)
        lines.append("- %s: %s" % (sym, ", ".join(cells)))
    if len(syms) > len(shown):
        lines.append("cross_matrix_truncated=%d" % (len(syms) - len(shown)))
    lines.append("")
    return lines

def _prior_class(v):
    """旧协议先验的展示优先级：confirmation > gate_pass > 其余。"""
    if str(v.get("run_mode") or "") == "confirmation":
        return 0
    if v.get("gate_pass"):
        return 1
    return 2

def _old_protocol_prior_lines(rows, max_rows=None):
    """旧协议先验注记 — T1 2026-10-05。仅上下文，不构成当前证据，不进主排名。

    每 (symbol, cov_override) 取最优行（confirmation > gate_pass > 其余，
    同级取 decided_at 最新）；行数超出预算截断并注明。
    """
    if max_rows is None:
        max_rows = OLD_PRIORS_MAX_ROWS
    try:
        max_rows = int(max_rows)
    except (TypeError, ValueError):
        max_rows = 0
    lines = ["## Old-protocol priors (context only, NOT current evidence)",
             "旧协议 = protocol_fingerprint 不同的历史裁决；仅上下文，不构成当前证据。"]
    best = {}
    for v in rows:
        if not isinstance(v, dict):
            continue
        fp = v.get("protocol_fingerprint")
        if not (isinstance(fp, str) and fp):
            continue
        key = (str(v.get("symbol") or "").lower(),
               str(v.get("cov_override") or ""))
        cur = best.get(key)
        if (cur is None or _prior_class(v) < _prior_class(cur)
                or (_prior_class(v) == _prior_class(cur)
                    and str(v.get("decided_at") or "")
                    > str(cur.get("decided_at") or ""))):
            best[key] = v
    if not best:
        lines.append("- (none)")
        lines.append("")
        return lines
    ordered = sorted(best.values(),
                     key=lambda v: str(v.get("decided_at") or ""),
                     reverse=True)
    ordered.sort(key=_prior_class)  # 稳定排序：类内保持 decided_at 降序
    shown = ordered[:max(0, max_rows)]
    for v in shown:
        fp = v.get("protocol_fingerprint")
        da = _finite_dir_acc(v)
        lines.append(
            "- [%s] %s: symbol=%s cov=%s decided_at=%s gate_pass=%s "
            "dir_acc=%s — 仅上下文，不构成当前证据"
            % (fp[:12], v.get("variant_id"),
               str(v.get("symbol") or "").lower(),
               v.get("cov_override"), v.get("decided_at") or "n/a",
               bool(v.get("gate_pass")),
               ("%.3f" % da) if da is not None else "n/a"))
    if len(ordered) > len(shown):
        lines.append("old_priors_truncated=%d" % (len(ordered) - len(shown)))
    lines.append("")
    return lines

def load_covariate_pool():
    """读协变量池 covariate_pool.json → cov dict。fail-open 返回 {}。

    读取时校验 horizon_known 契约（spec §4.5 W5.1）。校验失败**不**阻断
    （与 fail-open 加载一致），但必须把问题打到 stderr —— 一个漏填证据的
    known_ahead 会让下游填充逻辑白得「未来已知」这个最强假设，
    静默通过等于把错误假设喂给消融实验。
    """
    try:
        with open(sup_paths.POOL_PATH, encoding="utf-8") as f:
            pool = json.load(f) or {}
    except Exception as e:
        print("[WARN] covariate pool load failed (fail-open): %s" % e, file=sys.stderr)
        return {}

    try:
        from cascade.cov_family import apply_horizon_known_downgrade
        # spec §4.5 W5.1：缺证据的 known_ahead **不得**保留该标签，
        # 须降级为 unknowable + WARN。仅打 WARN 不降级等于洞没关。
        for name, reason in apply_horizon_known_downgrade(pool):
            print("[WARN] horizon_known 降级: %s -> unknowable（%s）"
                  % (name, reason), file=sys.stderr)
    except Exception as e:  # 降级器本身出错不得阻断加载
        print("[WARN] horizon_known 降级未能执行: %s" % e, file=sys.stderr)

    return pool.get("covariates", {})

def load_symbol_status(path=None):
    """Return {symbol: {"status": "DEAD"|"HOLD"|"ACTIVE", ...}}. Missing file -> {}."""
    p = path or sup_paths.SYMBOL_STATUS_PATH
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f) or {}
        out = {}
        for sym, rec in (raw.get("symbols") or {}).items():
            if not isinstance(rec, dict):
                continue
            st = str(rec.get("status") or "ACTIVE").upper()
            if st in ("DEAD", "HOLD", "ACTIVE"):
                out[str(sym).lower()] = rec
        return out
    except Exception as e:
        print("[WARN] symbol_status load failed (fail-open): %s" % e, file=sys.stderr)
        return {}

def _load_evaluator():
    """惰性导入 evaluator (仅 json/os/AST, 无 torch) 复用 active/archived/symbol 校验。"""
    try:
        p = os.path.join(sup_paths.FM_ROOT, "task_FM", "evaluations", "fm_eval")
        if p not in sys.path:
            sys.path.insert(0, p)
        import evaluator as ev
        return ev
    except Exception as e:
        print("[WARN] evaluator import failed in supervisor: %s" % e, file=sys.stderr)
        return None

# ── v2 预注册宇宙 (evaluator 预注册品种) ──────────────────────────
_ev_mod_for_goal = _load_evaluator()
del _ev_mod_for_goal

_CONFIRMATORY_DM = frozenset({"ok", "set_mismatch_ok"})

def _diag_finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def format_verdict_diag_label(row):
    """给线索文件用的互斥标签。不读盘，不改 row。"""
    if not isinstance(row, dict):
        return "不足以归因"
    gate = bool(row.get("gate_pass", False))
    status = row.get("status", "ok")
    confirmable = row.get("dm_status") in _CONFIRMATORY_DM
    if not gate and status != "ok":
        return "本行不是有效裁决，不写成机制失败"
    if not gate and not confirmable:
        return "DM 不可确认。不计作机制失败。这种 DM 状态不计入家族死亡"
    dir_acc = row.get("dir_acc")
    base = row.get("baseline_dir_acc")
    emin = row.get("effective_min")
    if not (_diag_finite(dir_acc) and _diag_finite(base) and _diag_finite(emin)):
        return "不足以归因"
    p_val = row.get("p_value")
    p_sig = confirmable and _diag_finite(p_val) and p_val <= 0.05
    if gate and not confirmable:
        return "过硬门。DM 不可确认，不能写成统计成功，也不能写成机制失败"
    if gate and p_sig:
        return "过硬门。本行 DM p ≤ 0.05。硬门本身不读 DM，这也不是确认成功"
    if gate:
        return "过硬门。本行 DM 未显示 p ≤ 0.05。硬门本身不读 DM，这也不是确认成功"
    if dir_acc < base:
        text = "方向低于无协变量基线"
    elif dir_acc < emin:
        if p_sig:
            text = "DM 显著改善，但方向准确率未达自适应门槛"
        else:
            text = "方向不低于基线，未过自适应门槛，DM 未显示稳定优势"
    else:
        text = "方向达到自适应门槛，但硬门未过。硬门还检查样本量与有效样本，不读 DM"
        if p_sig:
            text += "。本行 DM p ≤ 0.05，硬门仍未过"
        elif _diag_finite(p_val):
            text += "。本行 DM 亦未显示 p ≤ 0.05"
        return text
    if 0.49 <= dir_acc < emin:
        text += "。近失，距该品种门槛只差一截"
    return text

def _diag_failure(row):
    return (isinstance(row, dict)
            and row.get("status", "ok") == "ok"
            and _is_confirmable_failure(row))

def _diag_dir(row):
    """三个方向字段都是有限数才返回 dir_acc。缺一个就不当候选。"""
    if not isinstance(row, dict):
        return None
    da = row.get("dir_acc")
    base = row.get("baseline_dir_acc")
    emin = row.get("effective_min")
    if _diag_finite(da) and _diag_finite(base) and _diag_finite(emin):
        return float(da)
    return None

def _diag_near_miss(row):
    if not _diag_failure(row):
        return False
    da = _diag_dir(row)
    emin = row.get("effective_min")
    return da is not None and _diag_finite(emin) and 0.49 <= da < float(emin)

def _diag_best(rows):
    """dir_acc 高者优先。同分时品种名较小者优先，再比 variant_id。"""
    ranked = []
    for row in rows:
        da = _diag_dir(row)
        if da is None:
            continue
        ranked.append((
            -da,
            str(row.get("symbol") or "").casefold(),
            str(row.get("variant_id") or ""),
            row,
        ))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[:3])
    return ranked[0][3]

def select_symbol_diag_pair(symbol_rows, other_rows):
    """挑一个品种的正面和反面。不改输入行。"""
    symbol_rows = [r for r in (symbol_rows or []) if isinstance(r, dict)]
    other_rows = [r for r in (other_rows or []) if isinstance(r, dict)]
    passes = [r for r in symbol_rows if bool(r.get("gate_pass", False))]
    positive = _diag_best(passes)
    if positive is None:
        positive = _diag_best([r for r in symbol_rows if _diag_near_miss(r)])
    failures = [r for r in symbol_rows if _diag_failure(r) and r is not positive]
    negative = _diag_best([r for r in failures if _diag_near_miss(r)])
    if negative is None:
        negative = _diag_best(failures)
    cross = False
    repeat_n = 0
    if negative is None:
        cov = None
        if positive is not None:
            cov = positive.get("cov_override")
        else:
            covs = {r.get("cov_override") for r in symbol_rows
                    if r.get("cov_override")}
            if len(covs) == 1:
                cov = next(iter(covs))
        if cov:
            pool = [r for r in other_rows
                    if r.get("cov_override") == cov and _diag_failure(r)]
            repeat_n = len(pool)
            negative = _diag_best(pool)
            cross = negative is not None
        if negative is None:
            repeat_n = 0
    return {
        "positive": positive,
        "negative": negative,
        "positive_empty": None if positive is not None else "本品种无通过、无近失",
        "negative_empty": None if negative is not None else "本品种尚无有效失败记录",
        "cross_symbol": cross,
        "repeat_n": repeat_n if cross else 0,
    }

def _format_diag_bullet(symbol, side, picked):
    row = picked["positive"] if side == "正面" else picked["negative"]
    empty = picked["positive_empty"] if side == "正面" else picked["negative_empty"]
    if row is None:
        return "- %s %s：%s" % (symbol, side, empty)
    label = format_verdict_diag_label(row)
    da = row.get("dir_acc")
    da_s = ("%.3f" % da) if _diag_finite(da) else "n/a"
    head = "- %s %s" % (symbol, side)
    if side == "反面" and picked.get("cross_symbol"):
        head = "- %s 反面（跨品种 %s）" % (
            symbol, str(row.get("symbol") or "").lower())
    line = "%s：%s | variant_id=%s dir_acc=%s cov=%s" % (
        head, label, row.get("variant_id"), da_s, row.get("cov_override"))
    if row.get("decided_at"):
        line += " decided_at=%s" % row.get("decided_at")
    if side == "反面" and picked.get("cross_symbol") and picked.get("repeat_n", 0) >= 2:
        line += " 同协变量可确认失败 n=%d" % picked["repeat_n"]
    return line


def _diag_sample_lines(items, primary_fp):
    rows = []
    if isinstance(primary_fp, str) and primary_fp:
        rows = [v for v in (items or [])
                if isinstance(v, dict)
                and v.get("protocol_fingerprint") == primary_fp]
    by_sym = {}
    for row in rows:
        by_sym.setdefault(str(row.get("symbol") or "").lower(), []).append(row)
    lines = ["## 诊断样本", _protocol_section_line(primary_fp)]
    for sym in sorted(sup_state.GOAL_SYMBOLS_SET):
        mine = by_sym.get(sym, [])
        others = [row for name, group in sorted(by_sym.items()) if name != sym
                  for row in group]
        picked = select_symbol_diag_pair(mine, others)
        lines.append(_format_diag_bullet(sym, "正面", picked))
        lines.append(_format_diag_bullet(sym, "反面", picked))
    lines.append("")
    return lines

def _is_confirmable_failure(v):
    """失败 = 未过门**且** DM 可确认。

    2026-10-03：描述性 DM（set_mismatch_descriptive）与 no_common_cutoff 不是
    检验结论，不能当失败用。确认产出前全库都是描述性行，若把它们算失败，
    _dead_families 会误杀整族、_sector_filter_check 会把板块推向断路器 ——
    与 2026-09-24 饿死同构的陷阱，只是高一层。
    """
    return not v.get("gate_pass") and v.get("dm_status") in _CONFIRMATORY_DM

def _family_confirmatory_counts(rows):
    """与 _dead_families 同一套行。返回 (fam_ok, fam_pass)。

    步③ B（2026-10-07 裁定 A.3）：只计有 admissibility_rule 的行（旧行过滤）。
    """
    fam_ok = {}
    fam_pass = {}
    for v in rows or []:
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        if v.get("dm_status") not in _CONFIRMATORY_DM:
            continue
        if v.get("admissibility_rule") is None:
            continue   # 步③ B: 旧行缺字段不计入
        fam = str(v.get("cov_family") or "").strip()
        if not fam:
            continue
        fam_ok[fam] = fam_ok.get(fam, 0) + 1
        if v.get("gate_pass"):
            fam_pass[fam] = fam_pass.get(fam, 0) + 1
    return fam_ok, fam_pass

def _dead_families(snapshot, min_ok=4):
    """一族至少 min_ok 条可确认 DM 的 ok 裁决且 0 条过门，才算死亡。

    dm_status 缺省、set_mismatch_descriptive、no_common_cutoff、
    insufficient_common 都不计数。min_ok 仍是 4。
    run_mode 不读：探索行上的可确认失败同样计数。
    pass 计数是 gate_pass，不调用 pass_variants。
    """
    rows = (snapshot or {}).values() if isinstance(snapshot, dict) else []
    fam_ok, fam_pass = _family_confirmatory_counts(rows)
    return {fam for fam, n in fam_ok.items()
            if n >= min_ok and fam_pass.get(fam, 0) == 0}

def _dead_family_lines(items, primary_fp, min_ok=4):
    """把 _dead_families 的结果写给 peer。不另数全部 ok 行。"""
    fam_ok, fam_pass = _family_confirmatory_counts(items)
    dead = sorted(
        fam for fam, n in fam_ok.items()
        if n >= min_ok and fam_pass.get(fam, 0) == 0)
    lines = [
        "## Dead families",
        _protocol_section_line(primary_fp),
        "判据与 family_dead 相同：只计 dm_status 为 ok 或 set_mismatch_ok 的 ok 行；"
        "条数达到 min_ok 且 gate_pass 为 0 才列入。描述性 DM 不计数。"
        "列入的族会被无条件拒绝。",
    ]
    if not dead:
        lines.append("- (none)")
    else:
        for fam in dead:
            lines.append("- %s: n_ok=%d, n_gate_pass=%d, min_ok=%d" % (
                fam, fam_ok[fam], fam_pass.get(fam, 0), min_ok))
    lines.append("")
    return lines

# T1 (2026-10-05): known_verdicts 注入通道行数预算（module 常量，供测试 monkeypatch）
CROSS_MATRIX_MAX_ROWS = 40     # 品种×族矩阵最多列出的品种行数（超出截断注明）
OLD_PRIORS_MAX_ROWS = 20       # 旧协议先验注记最多行数（超出截断注明）
LOCKED_WINDOW_MAX_ROWS = 40    # 同窗锁定组合最多行数（超出截断注明）
# T2 (2026-10-05): 已成功组合复跑的 success_delta 增量论证最少字数
SUCCESS_DELTA_MIN_CHARS = 20
STALE_DATA_DAYS = 3            # 上海日历年龄 > 此值 → data_stale 放行；等于此值不放行

def _verdict_sort_key(v):
    """按 decided_at 排序；缺失/非字符串视为最早（确定性，无隐式时区假设）。"""
    d = v.get("decided_at")
    return d if isinstance(d, str) else ""

def _symbol_has_current_nocov_baseline(symbol, root):
    """当前协议的无协变量基线在，才占慢环座位。指纹算不出来时放行。不生成基线。"""
    fp = _current_protocol_fingerprint()
    if fp is None:
        return True
    from cascade.baseline_paths import baseline_filename
    path = os.path.join(root, "task_FM", "config", baseline_filename(symbol, None))
    status, got = _baseline_protocol_fingerprint(path)
    return status == "ok" and got == fp

def _prior_success_row(snapshot, symbol, cov):
    """snapshot 内该 (symbol, cov_override) 最新一条 ok+gate_pass=True 裁决。

    T2 (2026-10-05)：与失败侧 (_has_prior_failure) 刻意不同口径——成功侧要求
    **品种与协变量同时**命中（失败侧是「品种或协变量」）。理由：已过硬门的
    组合复跑必须有增量论证；仅"品种有过成功"或"协变量在别处成功"不构成
    挤占席位的重复提案。
    """
    best = None
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if v.get("status", "ok") != "ok" or not v.get("gate_pass"):
            continue
        if str(v.get("symbol") or "").lower() != str(symbol or "").lower():
            continue
        if str(v.get("cov_override") or "") != str(cov or ""):
            continue
        if best is None or _verdict_sort_key(v) >= _verdict_sort_key(best):
            best = v
    return best

def _row_eval_end_ts(v, cache=None, root=None):
    """裁决行的评估窗锚 eval_end_ts。

    行字段优先（T2 起由 aligned_slow_loop 落章）；缺失时兜底查 checkpoint：
    行内 checkpoint_path 字段 → root 相对 data/cache/aligned_checkpoints/<vid>.jsonl。
    checkpoint 按行扫描，**末行胜出**（同 run 同锚；续跑多 run 取最新）。
    找不到 → None（调用方 fail-open，不用墙钟猜）。
    """
    ts = v.get("eval_end_ts")
    if isinstance(ts, str) and ts:
        return ts
    vid = str(v.get("variant_id") or "")
    if not vid:
        return None
    cache = {} if cache is None else cache
    row_ts = cache.setdefault("_row_ts", {})
    if vid in row_ts:
        return row_ts[vid]
    ts_found = None
    cands = []
    cp = v.get("checkpoint_path")
    if isinstance(cp, str) and cp:
        cands.append(cp)
    if root:
        cands.append(os.path.join(str(root), "data", "cache",
                                  "aligned_checkpoints", vid + ".jsonl"))
    for path in cands:
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        rec = json.loads(ln)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(rec, dict):
                        t = rec.get("eval_end_ts")
                        if isinstance(t, str) and t:
                            ts_found = t
        # T2c (2026-10-05 审计): UnicodeDecodeError 是 ValueError 子类——
        # 撕裂 checkpoint（崩溃多字节字符）不得穿透炸 harvest。撕裂点前的
        # 可信行保留；候选文件整体不可读时弃读（部分读语义与 OSError 一致）。
        except (OSError, ValueError):
            continue
        if ts_found is not None:
            break
    row_ts[vid] = ts_found
    return ts_found

def _current_window_anchor(snapshot, cache=None, root=None):
    """当前评估窗锚（近似）：全部 ok 裁决行 eval_end_ts 的最大值。

    存量行普遍缺 eval_end_ts 时（T2 上线前）锚可能为 None → 调用方
    fail-open。不引入墙钟：没有可靠锚就不执法。
    """
    anchor = None
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        ts = _row_eval_end_ts(v, cache, root)
        if isinstance(ts, str) and ts and (anchor is None or ts > anchor):
            anchor = ts
    return anchor

def _today_shanghai():
    """上海日历日。测试钉这一个函数，不钉 datetime.now。

    ZoneInfo 不可用时回退 UTC 日历日。这是防御，不是预期失败：
    zoneinfo 与 datetime 都是标准库。
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except Exception:
        return datetime.now(timezone.utc).date()

def _kline_1h_max_dt(symbol):
    """只读 kline_1h 的 MAX(dt)。缺库、空表、SQL 错误 → None。不建库。"""
    import sqlite3
    try:
        from data.config import get_db_path
        path = get_db_path(str(symbol or ""))
    except Exception:
        return None
    if path is None or not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row or row[0] is None:
        return None
    return str(row[0])

def _symbol_data_stale(symbol, cache):
    """日历年龄 > STALE_DATA_DAYS 时为真。读失败、日期坏、未来 bar 都为假。

    cache['_kline_max'] 按 symbol 记原始 MAX(dt)。
    cache['_stale_logged'] 保证同一 cache 里每个 symbol 只打一条 WARNING。
    cache['_probe'] 为真时不打日志（物化锁定名单只探门，不假装有提案被拒）。
    """
    if cache is None:
        cache = {}
    key = str(symbol or "").lower()
    maxes = cache.setdefault("_kline_max", {})
    if key not in maxes:
        maxes[key] = _kline_1h_max_dt(key)
    raw = maxes[key]
    if not isinstance(raw, str) or len(raw) < 10:
        return False
    try:
        bar_day = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    today = _today_shanghai()
    age = (today - bar_day).days
    if age <= STALE_DATA_DAYS:
        return False
    if not cache.get("_probe"):
        logged = cache.setdefault("_stale_logged", set())
        if key not in logged:
            logged.add(key)
            logging.warning(
                "success_gate: %s 数据末端 %s 距上海日历 %s 已 %d 天 > %d → data_stale 放行",
                key, raw, today.isoformat(), age, STALE_DATA_DAYS)
    return True

def _prior_success_class(prior):
    """known_verdicts 图例口径：确认且过 FDR 才是 v2-pass。"""
    if (isinstance(prior, dict)
            and prior.get("fdr_pass")
            and prior.get("p_value") is not None
            and prior.get("run_mode") == "confirmation"):
        return "v2-pass"
    return "hard-gate-but-losing"

def _success_delta_gate(prop, symbol, cov, snapshot, root=None, cache=None):
    """T2 (2026-10-05): 已成功组合的增量论证门。

    同 (symbol, cov_override) 在当前评估窗口已有 ok+gate_pass=True 裁决时，
    复跑提案必须用 success_delta (>=SUCCESS_DELTA_MIN_CHARS 字) 写清相对
    上次成功的增量，否则拒收 no_success_delta。
    逃逸阀（fail-open）：评估窗已平移（prior_ts != anchor）或锚不可得
    （行字段与 checkpoint 均缺失）时放行——这两条不看墙钟。窗口平移后旧成功
    不再是当前窗证据（2026-10-04 审计：09-23→09-30 15:00 窗整体更换同理）。
    数据末端距上海日历超过 STALE_DATA_DAYS 天时另放行 data_stale：锚钉死、
    窗口无法平移，空 success_delta 不再把复跑全部拒掉。新 bar 进入 3 天内
    后这条旁路自行关闭。
    返回 (reject_reason_or_None, state)；state 计入 stats["success_gate_states"]：
    no_prior_success / window_moved / anchor_unavailable / data_stale /
    success_delta_ok / no_success_delta。
    """
    prior = _prior_success_row(snapshot, symbol, cov)
    if prior is None:
        return None, "no_prior_success"
    cache = {} if cache is None else cache
    if "anchor" not in cache:
        cache["anchor"] = _current_window_anchor(snapshot, cache, root)
    anchor = cache["anchor"]
    prior_ts = _row_eval_end_ts(prior, cache, root)
    if prior_ts is None or anchor is None:
        return None, "anchor_unavailable"
    if prior_ts != anchor:
        return None, "window_moved"
    if _symbol_data_stale(symbol, cache):
        return None, "data_stale"
    delta = str((prop or {}).get("success_delta") or "").strip()
    if len(delta) >= SUCCESS_DELTA_MIN_CHARS:
        return None, "success_delta_ok"
    # T2b: 拒收信息带先验分类与 run_mode（known_verdicts 图例口径）——
    # 探索先验（gate 过但 fdr/p_value 缺）不得在日志里被封账为成功。
    # 物化锁定名单会以空 success_delta 探门，cache['_probe'] 时不打拒收日志。
    if not cache.get("_probe"):
        logging.warning(
            "success_gate: %s_%s 复跑缺 success_delta (len=%d < %d) → 拒收 (no_success_delta)；"
            "prior=%s class=%s run_mode=%s eval_end_ts=%s",
            str(symbol or ""), str(cov or ""), len(delta), SUCCESS_DELTA_MIN_CHARS,
            str(prior.get("variant_id") or ""),
            _prior_success_class(prior),
            str(prior.get("run_mode") or "None"), prior_ts)
    return "no_success_delta", "no_success_delta"

def _locked_success_rows(snapshot, root, cache=None):
    """同窗已成功、空 success_delta 会被拒的 prior，每个 (symbol, cov) 一条。

    data_stale / window_moved / anchor_unavailable 不进名单，名单与门同一谓词。
    """
    cache = {} if cache is None else cache
    # 原地写入：_symbol_data_stale 会往这份 cache 填 _kline_max / _stale_logged，这里再写 _probe。
    cache["_probe"] = True
    keys = set()
    for v in (snapshot or {}).values():
        if not isinstance(v, dict):
            continue
        if v.get("status", "ok") != "ok" or not v.get("gate_pass"):
            continue
        symbol = str(v.get("symbol") or "").lower()
        cov = str(v.get("cov_override") or "")
        if symbol:
            keys.add((symbol, cov))
    locked = []
    for symbol, cov in sorted(keys):
        reason, state = _success_delta_gate(
            {"success_delta": ""}, symbol, cov, snapshot, root, cache)
        if reason == "no_success_delta" and state == "no_success_delta":
            prior = _prior_success_row(snapshot, symbol, cov)
            if prior is not None:
                locked.append(prior)
    return locked

def _locked_window_lines(snapshot, root):
    """## Locked this window 段落。不含墙钟，保证除 generated_at 外物化幂等。"""
    rows = _locked_success_rows(snapshot, root, cache={})
    lines = [
        "## Locked this window",
        "同评估窗已有 gate_pass=True 的 (symbol, cov)。复跑必须写 success_delta（≥20 字）"
        "并点名 prior。空 success_delta 会被拒 (no_success_delta)。"
        "数据末端距上海日历超过 %d 天时此名单为空。" % STALE_DATA_DAYS,
    ]
    if not rows:
        lines.append("- (none)")
    else:
        cache = {"_probe": True}
        shown = rows[:max(0, LOCKED_WINDOW_MAX_ROWS)]
        for prior in shown:
            symbol = str(prior.get("symbol") or "").lower()
            cov = str(prior.get("cov_override") or "")
            prior_ts = _row_eval_end_ts(prior, cache, root)
            lines.append(
                "- %s cov=%s prior=%s class=%s eval_end_ts=%s" % (
                    symbol, cov, prior.get("variant_id"),
                    _prior_success_class(prior), prior_ts))
        rest = len(rows) - len(shown)
        if rest > 0:
            lines.append("locked_window_truncated=%d" % rest)
    lines.append("")
    return lines

def _valid_n_for_symbol(symbol):
    """复刻 monthly_backtest.run_symbol_backtest 的有效评估点计数 (不 import torch)。

    eval_indices = range(CONTEXT_BARS, total-HORIZON+1, STEP)，再按日线充足性
    (累计日线 >= max(CONTEXT_DAYS-HORIZON_DAYS,100)) 过滤。任何异常返回 None (fail-open)。
    """
    try:
        import bisect
        from config.backtest_config import (
            CONTEXT_BARS, HORIZON, STEP, CONTEXT_DAYS, HORIZON_DAYS, EVAL_WINDOW_BARS)
        from data.data_store import DataStore
        store = DataStore(symbol)
        try:
            h1 = store.get_main_contract_1h(limit=99999)
            daily = store.get_main_continuous(limit=99999)
        finally:
            store.close()
        if h1.empty or len(h1) < CONTEXT_BARS + HORIZON or daily.empty:
            return 0
        need = max(CONTEXT_DAYS - HORIZON_DAYS, 100)
        dates = sorted(daily["dt"].astype(str).str[:10].tolist())
        n_ok = 0
        eval_start = max(CONTEXT_BARS, len(h1) - EVAL_WINDOW_BARS)
        for idx in range(eval_start, len(h1) - HORIZON + 1, STEP):
            if bisect.bisect_right(dates, str(h1["dt"].iloc[idx])[:10]) >= need:
                n_ok += 1
        return n_ok
    except Exception:
        return None

_FP_WEIGHTS_CACHE: dict = {}
_FP_TARGET_CACHE: dict = {}

def _experiment_fp_for(symbol, cov):
    """W6.4 实验身份要素: 权重目录 + 品种 1H close 序列 + 慢环窗口常数 + 请求协变量。

    compute_experiment_fingerprint 唯一家在 cascade/experiment_fingerprint.py,
    本函数是其 supervisor 侧装配者; build_variant_id 的 fp 入参即返回值。
    任何一环不可解析 → None (fail-visible), 调用方必须拒绝候选,
    禁止回退旧式 symbol_cov 身份 (spec §4.5 W6.4)。
    weights 解析一次缓存; target 逐品种缓存 (ALLOWED_SYMBOLS 有界)。
    """
    try:
        import data.config as dc
        from config.backtest_config import CONTEXT_BARS, HORIZON, STEP
        wdir = _FP_WEIGHTS_CACHE.get("weights_dir")
        if wdir is None:
            wdir = dc.get_timesfm_model_path()
            if not wdir or not Path(wdir).is_dir():
                return None
            _FP_WEIGHTS_CACHE["weights_dir"] = wdir
        target = _FP_TARGET_CACHE.get(symbol)
        if target is None:
            from data.data_store import DataStore
            store = DataStore(symbol)
            try:
                h1 = store.get_main_contract_1h(limit=99999)
            finally:
                store.close()
            if h1 is None or h1.empty:
                return None
            target = [float(x) for x in h1["close_price"].tolist()]
            if not target:
                return None
            _FP_TARGET_CACHE[symbol] = target
        return ef.compute_experiment_fingerprint(
            wdir, target, CONTEXT_BARS, HORIZON, STEP, [cov])
    except Exception:
        return None

def _symbol_n_table():
    """[(symbol, valid_n)] for evaluator-allowed symbols; [] if evaluator unavailable."""
    ev = _load_evaluator()
    syms = sorted(getattr(ev, "ALLOWED_SYMBOLS", None) or [])
    return [(s, _valid_n_for_symbol(s)) for s in syms]

def _active_protocol_snapshot(path):
    """收割和复测只看当前协议。无指纹与旧指纹留在 jsonl，不参与拒绝或复测。"""
    return rl.load_snapshot(path, only_protocol=_current_protocol_fingerprint())

def _baseline_protocol_fingerprint(points_path):
    """读取基线首行的 protocol_fingerprint。

    Returns:
        (status, fp):
          ("ok", <str>)      指纹存在
          ("missing", None)  首行无该键（pre-A1 遗留基线）
          ("unreadable", None) 文件不可读 / 首行非法 JSON

    2026-09-28 新增（T1a 实测发现的缺口）:
      原先 ensure_baselines 只按 n_lines<100 判断，导致 PR-A1 引入
      protocol_v2 后，rb 的旧基线（588 行、protocol_v1 指纹）被**静默保留**，
      与其他 7 份新基线跨协议不可比。本函数用于补上该层校验。
    """
    try:
        with open(points_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    return ("unreadable", None)
                fp = rec.get("protocol_fingerprint")
                return ("ok", fp) if fp else ("missing", None)
    except OSError:
        return ("unreadable", None)
    return ("missing", None)

def _current_protocol_fingerprint():
    """当前协议指纹；不可得时返回 None（此时跳过指纹校验并告警）。"""
    try:
        from task_FM.evaluations.fm_eval.evaluator import (
            compute_protocol_fingerprint,
        )
        return compute_protocol_fingerprint()
    except Exception as e:            # noqa: BLE001
        print(f"[WARN] ensure_baselines: 无法计算当前协议指纹 ({e})；跳过指纹校验",
              file=sys.stderr)
        return None

def _archive_baseline_before_regen(points_path):
    """步① 基线快照版本化（2026-10-07 裁定 A.8，事项一五步之第 1 步）。

    重生即归档：gbp.generate() 以临时文件 rename 覆盖旧档，旧快照会直接
    丢失。重生前先将旧档复制为带锚定日的归档副本：

        baseline_points_jd_nocov.archive_20250930T1400.jsonl

    锚定日 = 旧档最后一个可解析行的 cutoff（评估窗末端）；全坏/空档回退
    文件 mtime。copy 语义（原档留给 generate 覆盖）。归档失败仅 WARN 不
    阻塞重生；归档不清理（重生罕见，历史快照保留供审计）。

    Returns:
        归档文件路径；无旧档或归档失败时返回 None。
    """
    if not os.path.exists(points_path):
        return None
    anchor = None
    try:
        with open(points_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    anchor = json.loads(line).get("cutoff")
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    ts = None
    if anchor:
        try:
            ts = datetime.strptime(anchor, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M")
        except (TypeError, ValueError):
            ts = None
    if ts is None:
        try:
            ts = datetime.fromtimestamp(os.path.getmtime(points_path)).strftime("%Y%m%dT%H%M")
        except OSError:
            return None
    d, base = os.path.split(points_path)
    stem, ext = os.path.splitext(base)
    archive = os.path.join(d, f"{stem}.archive_{ts}{ext}")
    n = 1
    while os.path.exists(archive):
        archive = os.path.join(d, f"{stem}.archive_{ts}_{n}{ext}")
        n += 1
    try:
        shutil.copy2(points_path, archive)
        print(f"[INFO] ensure_baselines: 基线快照已归档 → {archive}", file=sys.stderr)
        return archive
    except OSError as e:
        print(f"[WARN] ensure_baselines: 基线快照归档失败 ({base}): {e}", file=sys.stderr)
        return None

# 步② C 漂移上界：基线末端落后数据末端超过此小时数 → 重锚重生。
# 依据 2026-10-07 裁定 C 验收语义（unmatched 收敛到拉取滞后 1-3 点）+
# 实测边缘漂移案例 14 天；7 天既捕获假期级漂移，又避免 2-3 天重启节奏下
# 每次启动全品种重生（33 品种 × ~1.5 分钟回测 ≈ 50 分钟）。
_BASELINE_STALENESS_MAX_H = 168

# ensure_baselines 只在 supervisor 启动的 pre-flight 跑一次，进程内字典活不到
# 下一次启动。停滞品种落到 data/cache（gitignore），下次启动只有数据末端
# 严格变新才允许再重生。
_RECENTLY_REGENED_NO_ADVANCE: dict[str, str] = {}


def _regen_breaker_path(root):
    return os.path.join(root, "data", "cache", "baseline_regen_breaker.json")


def _norm_bar_dt(value):
    """把 bar 时间归一成 '%Y-%m-%d %H:%M:%S'。读不出返回 None。"""
    if not isinstance(value, str):
        return None
    text = value.strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1].strip()
    plus = text.find("+", 10)
    if plus != -1:
        text = text[:plus].strip()
    if "." in text:
        text = text.split(".", 1)[0].strip()
    # 尝试多种时间格式（有无秒均可）
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _canonical_data_end(value):
    norm = _norm_bar_dt(value)
    if norm:
        return norm
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _load_regen_breaker(root):
    """用该 root 的磁盘记录替换进程内记忆。缺失或损坏则清空。"""
    _RECENTLY_REGENED_NO_ADVANCE.clear()
    path = _regen_breaker_path(root)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    for key, val in data.items():
        if isinstance(key, str) and isinstance(val, str) and val.strip():
            _RECENTLY_REGENED_NO_ADVANCE[key.lower()] = val


def _save_regen_breaker(root):
    path = _regen_breaker_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_RECENTLY_REGENED_NO_ADVANCE, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _stall_still_blocks(sym_lower, root):
    """无法证明数据末端比上次停滞时更新 → 跳过重生并保留记录。

    读失败、格式对不上、末端相同或更旧都不清除。只有两边都能解析且
    当前末端严格更晚才放行。
    """
    prev = _RECENTLY_REGENED_NO_ADVANCE.get(sym_lower)
    if not prev:
        return False
    current = _canonical_data_end(sup_state._latest_data_dt(sym_lower))
    prev_c = _canonical_data_end(prev)
    if current is None or prev_c is None:
        return True
    cur_n = _norm_bar_dt(current)
    prev_n = _norm_bar_dt(prev_c)
    if cur_n is not None and prev_n is not None and cur_n > prev_n:
        _RECENTLY_REGENED_NO_ADVANCE.pop(sym_lower, None)
        _save_regen_breaker(root)
        return False
    return True


def _remember_stall(sym_lower, root, data_dt):
    canonical = _canonical_data_end(data_dt)
    if not canonical:
        return
    _RECENTLY_REGENED_NO_ADVANCE[sym_lower] = canonical
    _save_regen_breaker(root)


def _read_last_cutoff(points_path):
    """基线文件最后一个 cutoff。重生后用来判断末端有没有推进。"""
    last_cutoff = None
    try:
        with open(points_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last_cutoff = json.loads(line).get("cutoff") or last_cutoff
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return last_cutoff


def _prereg_confirm_from_ts(sym_lower, root):
    """该品种全部预注册行的 confirm_from_ts 列表（读 root 相对 preregistry）。"""
    path = os.path.join(root, "task_FM", "config", "preregistry.jsonl")
    out = []
    for row in sup_state.load_preregistry(path):
        if str(row.get("symbol", "")).lower() == str(sym_lower).lower():
            ts = row.get("confirm_from_ts")
            if ts:
                out.append(str(ts))
    return out

def _baseline_reanchor_reason(sym_lower, last_cutoff, root):
    """步② C：该品种基线是否需要拉取日重锚；需要则返回原因字符串，否则 None。

    重锚条件（任一触发）：
    (a) 确认窗覆盖缺口：存在预注册 confirm_from_ts ∈ (基线末端, 数据末端]——
        数据已越过确认窗起点而冻结基线尚未覆盖，no_common_cutoff 的直接死因；
    (b) 漂移上界：数据末端 - 基线末端 > _BASELINE_STALENESS_MAX_H。

    fail-open：数据末端或基线末端读不到 → None（重生昂贵，缺证据不动作；
    与派发闸门 _confirm_data_ready 的 fail-closed 语义相反，后者防墓碑）。
    """
    if not last_cutoff:
        return None
    data_dt = sup_state._latest_data_dt(sym_lower)
    if not data_dt:
        return None
    for ts in _prereg_confirm_from_ts(sym_lower, root):
        if last_cutoff < ts <= data_dt:
            return (f"基线末端 {last_cutoff} 未覆盖确认窗起点 {ts}"
                    f"（数据已到位 → 拉取日重锚）")
    try:
        # 支持多种时间格式（有无秒均可）
        data_dt_norm = _norm_bar_dt(data_dt)
        last_cutoff_norm = _norm_bar_dt(last_cutoff)
        if data_dt_norm is None or last_cutoff_norm is None:
            return None
        lag_h = ((datetime.strptime(data_dt_norm, "%Y-%m-%d %H:%M:%S")
                  - datetime.strptime(last_cutoff_norm, "%Y-%m-%d %H:%M:%S"))
                 .total_seconds() / 3600.0)
    except (ValueError, TypeError):
        return None
    if lag_h > _BASELINE_STALENESS_MAX_H:
        return (f"基线末端落后数据末端 {lag_h:.0f}h "
                f"> {_BASELINE_STALENESS_MAX_H}h → 拉取日重锚")
    return None

def finalize_baseline_write(symbol, points_path, root, archive_path):
    """唯一收口：临时文件通过后换名，否则尝试合格归档回滚。

    """
    import glob
    import shutil
    from cascade.eval_grid import baseline_eval_cutoffs, accept_baseline_file

    sym_lower = str(symbol).lower()
    try:
        expected = baseline_eval_cutoffs(sym_lower)
        fp = _current_protocol_fingerprint()
    except Exception as exc:
        print(f"[ERROR] finalize_baseline_write: {sym_lower} 读网格或指纹失败: {exc}",
              file=sys.stderr)
        return False
    if not fp:
        print(f"[ERROR] finalize_baseline_write: {sym_lower} 当前指纹为空",
              file=sys.stderr)
        return False

    points_dir = os.path.dirname(points_path)
    points_name = os.path.basename(points_path)
    tmp_path = os.path.join(points_dir, "." + points_name + ".tmp")

    if os.path.exists(tmp_path):
        ok, reason = accept_baseline_file(tmp_path, expected, fp)
        if ok:
            try:
                n_lines = sum(1 for line in open(tmp_path, encoding="utf-8") if line.strip())
                os.replace(tmp_path, points_path)
                first_cutoff = expected[0] if expected else "?"
                last_cutoff = expected[-1] if expected else "?"
                fp_prefix = fp[:16] if len(fp) >= 16 else fp
                print(f"[INFO] finalize_baseline_write: {sym_lower} 收口通过 "
                      f"({n_lines} 行, {first_cutoff} ~ {last_cutoff}, fp={fp_prefix}…)",
                      file=sys.stderr)
            except OSError as exc:
                print(f"[ERROR] finalize_baseline_write: {sym_lower} 换名失败: {exc}",
                      file=sys.stderr)
                return False

            confirm_set = _prereg_confirm_from_ts(sym_lower, root)
            if confirm_set:
                threshold = min(confirm_set)
                expected_set = set(expected)
                missing = []
                try:
                    with open(archive_path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rec = json.loads(line)
                                c = str(rec.get("cutoff", ""))
                            except json.JSONDecodeError:
                                continue
                            if c >= threshold and c not in expected_set:
                                missing.append(c)
                except (OSError, TypeError):
                    pass
                if missing:
                    shown = missing[:8]
                    total = len(missing)
                    suffix = f"（共 {total} 条）" if total > 8 else ""
                    print(f"[WARN] finalize_baseline_write: {sym_lower} 确认样本缺失 "
                          f"（边界 {threshold}, 缺失 {shown}{suffix}），不回滚探索基线",
                          file=sys.stderr)
            return True
        else:
            n_tmp = 0
            try:
                with open(tmp_path, encoding="utf-8") as f:
                    n_tmp = sum(1 for line in f if line.strip())
            except OSError:
                pass
            print(f"[WARN] finalize_baseline_write: {sym_lower} 临时文件未通过: {reason} "
                  f"(临时文件 {n_tmp} 行)",
                  file=sys.stderr)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

            archive_pattern = os.path.join(
                points_dir,
                os.path.splitext(points_name)[0] + ".archive_*.jsonl"
            )
            archives = sorted(glob.glob(archive_pattern), key=os.path.getmtime, reverse=True)
            for archive in archives:
                archive_ok, _ = accept_baseline_file(archive, expected, fp)
                if archive_ok:
                    try:
                        shutil.copy2(archive, points_path)
                        print(f"[INFO] finalize_baseline_write: {sym_lower} 从归档恢复 "
                              f"{os.path.basename(archive)}",
                              file=sys.stderr)
                    except OSError as exc:
                        print(f"[ERROR] finalize_baseline_write: {sym_lower} 归档恢复失败: {exc}",
                              file=sys.stderr)
                    return False
            return False
    else:
        live_ok, _ = accept_baseline_file(points_path, expected, fp)
        return live_ok


def _temp_path(points_path):
    directory, name = os.path.split(points_path)
    return os.path.join(directory, "." + name + ".tmp")


def _incremental_or_regen(sym_lower, points_path, root, archive_path):
    from scripts import incremental_baseline as ib
    temp = _temp_path(points_path)
    returned = ib.incremental_generate(sym_lower, None, root, finalize=False)
    publishable = returned is not None and os.path.exists(temp)
    if publishable and finalize_baseline_write(sym_lower, points_path, root, archive_path):
        return _read_last_cutoff(points_path)
    # First convergence failed. No more archival.
    try:
        import generate_baseline_points as gbp
        gbp.generate(sym_lower, None, root, finalize=False)
    except Exception as exc:
        print(f"[ERROR] ensure_baselines: {sym_lower} full write failed: {exc}", file=sys.stderr)
        return None
    if finalize_baseline_write(sym_lower, points_path, root, archive_path):
        return _read_last_cutoff(points_path)
    return None


def _regen_baseline_with_archive(sym_lower, points_path, root):
    try:
        import generate_baseline_points as gbp
    except ImportError:
        return
    try:
        gbp.generate(sym_lower, None, root, finalize=False)
    except Exception as e:
        print("[ERROR] ensure_baselines: generate failed for " + sym_lower
              + ": " + str(e), file=sys.stderr)
        return
    return _read_last_cutoff(points_path)



# ══════════════════════════════════════════════════
#  ensure_baselines 全局互斥锁
# ══════════════════════════════════════════════════

ENSURE_LOCK_FILE = "/tmp/ensure_baselines.lock"
_ensure_lock_fp = None

def _acquire_ensure_lock():
    """确保只有一个 ensure_baselines 实例运行"""
    global _ensure_lock_fp

    # 检查残留锁
    if os.path.exists(ENSURE_LOCK_FILE):
        try:
            with open(ENSURE_LOCK_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
        except (ProcessLookupError, ValueError, PermissionError):
            os.remove(ENSURE_LOCK_FILE)

    try:
        _ensure_lock_fp = open(ENSURE_LOCK_FILE, "w")
        fcntl.flock(_ensure_lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _ensure_lock_fp.write(str(os.getpid()))
        _ensure_lock_fp.flush()

        atexit.register(lambda: fcntl.flock(_ensure_lock_fp.fileno(), fcntl.LOCK_UN))
        return True
    except IOError:
        raise RuntimeError(
            "另一个 ensure_baselines 进程正在运行，禁止并发启动。\n"
            f"锁文件: {ENSURE_LOCK_FILE}"
        )

def ensure_baselines(symbols, root):
    _acquire_ensure_lock()
    try:
        import generate_baseline_points as gbp
    except ImportError:
        return
    config_dir = os.path.join(root, "task_FM", "config")
    metrics_path = os.path.join(config_dir, "baseline_metrics.json")
    try:
        with open(metrics_path, encoding="utf-8") as handle:
            metrics = json.load(handle)
    except (OSError, json.JSONDecodeError):
        metrics = {}
        if "pytest" in sys.modules:
            return
    _load_regen_breaker(root)
    for sym in sorted(symbols):
        try:
            sym_lower = sym.lower()
            points_path = os.path.join(config_dir, gbp.baseline_filename(sym_lower, None))
            try:
                from cascade.eval_grid import accept_baseline_file, baseline_eval_cutoffs
                expected = baseline_eval_cutoffs(sym_lower)
            except Exception as exc:
                print(
                    f"[ERROR] ensure_baselines: {sym_lower} grid read failed: {exc}. Skip this symbol, no stall",
                    file=sys.stderr,
                )
                continue
            fp = _current_protocol_fingerprint()
            if not fp:
                print(
                    f"[WARN] ensure_baselines: {sym_lower} current fingerprint unavailable. No regen, no delete, no stall",
                    file=sys.stderr,
                )
                continue
            ok, _reason = accept_baseline_file(points_path, expected, fp)
            if ok:
                continue
            if _stall_still_blocks(sym_lower, root):
                continue
            archive = _archive_baseline_before_regen(points_path)
            try:
                new_cutoff = _incremental_or_regen(sym_lower, points_path, root, archive)
            except Exception as exc:
                print(f"[ERROR] ensure_baselines: {sym_lower} write failed mid-way: {exc}", file=sys.stderr)
                _remember_stall(sym_lower, root, sup_state._latest_data_dt(sym_lower))
                continue
            if new_cutoff is None:
                _remember_stall(sym_lower, root, sup_state._latest_data_dt(sym_lower))
        finally:
            sup_lifecycle._write_heartbeat()
