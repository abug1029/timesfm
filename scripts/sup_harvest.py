import glob
import json
import logging
import os
import sys
import threading
from pathlib import Path

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
del _repo_root

# ── Schema 接受集合（Phase 1 Task 2）──
# Spec §3.6: 接受 v1 和 v2；v1 的 version 默认为 1；v2 必须有合法 version
_ACCEPTED_SCHEMAS = {
    "fm.hypothesis_proposal.v1",
    "fm.hypothesis_proposal.v2",
}

def _check_v2_version(p: dict) -> bool:
    """v2 schema 必须带 version 字段且为整数 ≥1。"""
    v = p.get("version")
    if v is None:
        return False
    if not isinstance(v, int) or isinstance(v, bool):
        return False
    return v >= 1

import registry_lib as rl
import search_trees as st
from cascade import experiment_fingerprint as ef
from cascade.cov_family import resolve_cov_family

import sup_evidence
import sup_lifecycle
import sup_paths
from proposal_status import write_proposal_status
from rejected_proposals import write_rejected_proposal
from variant_registry import VariantRegistry


def harvest_survivors(root, snapshot, dead, existing, top_k, aligned_max_points=600):
    """Pick up to top_k diagnostic survivors, preferring symbol×cov diversity.

    Ranking is by diagnostic dir_acc, but we fill seats in passes:
      1) unique symbols (avoid 3× same symbol)
      2) remaining by dir_acc (different cov on a seen symbol is OK)
    """
    out = []
    seen = set()
    passing_ids = {v["variant_id"] for v in rl.pass_variants(snapshot or {})}
    run_dirs = sorted(glob.glob(os.path.join(root, "task_FM", "experiments", "run_*")),
                      key=os.path.getmtime, reverse=True)
    for run_dir in run_dirs:
        for sp in glob.glob(os.path.join(run_dir, "results", "**", "evaluation_summary.json"),
                            recursive=True):
            try:
                d = json.load(open(sp, encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or d.get("stage") != "diagnostic":
                continue
            metrics = d.get("metrics") or {}
            dir_acc = float(metrics.get("dir_acc") or d.get("dir_acc") or 0.0)
            if dir_acc < 0.50:
                continue
            try:
                symbol = d["symbol"].lower()
                cov = d["cov_override"]
            except KeyError:
                continue
            fam = resolve_cov_family({"cov_override": cov})
            fp = sup_evidence._experiment_fp_for(symbol, cov)
            if fam == "unknown" or fp is None:
                continue  # W6.4: 身份不可得 → 跳过, 不回退旧式 symbol_cov
            vid = ef.build_variant_id(symbol, fam, fp)
            if vid in dead or vid in existing or vid in passing_ids or vid in seen:
                continue
            seen.add(vid)
            out.append({"variant_id": vid, "symbol": symbol, "cov_override": cov,
                        "max_points": int(aligned_max_points),
                        "stage": "aligned", "checkpoint_path": "",
                        "enqueued_at": sup_lifecycle._now_iso(), "src_run": os.path.basename(run_dir),
                        "_dir_acc": dir_acc})
    out.sort(key=lambda r: -r["_dir_acc"])
    selected = []
    used_symbols = set()
    for r in out:
        if len(selected) >= int(top_k):
            break
        if r["symbol"] in used_symbols:
            continue
        selected.append(r)
        used_symbols.add(r["symbol"])
    if len(selected) < int(top_k):
        selected_ids = {r["variant_id"] for r in selected}
        for r in out:
            if len(selected) >= int(top_k):
                break
            if r["variant_id"] in selected_ids:
                continue
            selected.append(r)
            selected_ids.add(r["variant_id"])
    for r in selected:
        r.pop("_dir_acc", None)
    return selected


def _cross_run_repeat_counts(root=None, max_runs=20):
    """Count how many runs each variant_id appears in (shared_findings).

    Returns {variant_name: run_count}. Used for repeat-offender penalty.
    Scans at most `max_runs` most recent runs to bound cost.
    """
    base = root or sup_paths.FM_ROOT
    runs_dir = os.path.join(base, "task_FM", "experiments")
    if not os.path.isdir(runs_dir):
        return {}
    # Most recent N runs
    run_dirs = sorted(glob.glob(os.path.join(runs_dir, "run_*")),
                      key=os.path.getmtime, reverse=True)[:max_runs]
    counts = {}
    for rd in run_dirs:
        sf_dir = os.path.join(rd, "shared_findings")
        if not os.path.isdir(sf_dir):
            continue
        seen_in_run = set()
        for f in glob.glob(os.path.join(sf_dir, "*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
                # variant_name is the symbol_cov key
                vn = d.get("variant_name") or ""
                if not vn:
                    title = d.get("title", "")
                    vn = title.split(":")[0].strip() if ":" in title else ""
                if vn:
                    seen_in_run.add(vn)
            except (OSError, json.JSONDecodeError):
                continue
        for vn in seen_in_run:
            counts[vn] = counts.get(vn, 0) + 1
    return counts

def _apply_prescreen_score(score, proposal_path):
    """Laya prescreen score adjustment (Phase 2)."""
    if not proposal_path:
        return score
    ps_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if not os.path.exists(ps_path):
        return score
    try:
        with open(ps_path, encoding="utf-8") as _f:
            ps = json.load(_f)
    except (json.JSONDecodeError, OSError):
        return score
    if not isinstance(ps, dict) or ps.get("status") != "success":
        return score
    skip = ps.get("skip_suggested")
    novelty = str(ps.get("novelty") or "").strip().lower()
    plausibility = ps.get("mechanism_plausibility")
    effect_size = ps.get("effect_size")
    if skip is True:
        if novelty == "invalid":
            return score - 100.0
        if novelty == "redundant" and (effect_size is None or effect_size <= 1):
            return score - 30.0
        if plausibility is not None and isinstance(plausibility, (int, float)) and plausibility < 0.4:
            return score - 20.0
        # skip 第 4 分支: effect==0 且 plausibility ∈ [0.4, 0.6) -- 无新增信息且可信度不足以补偿
        if (effect_size == 0
                and isinstance(plausibility, (int, float))
                and plausibility < 0.6):
            return score - 15.0
    if skip is False and isinstance(effect_size, (int, float)) and effect_size >= 2:
        score += 10.0
    if novelty in ("novel", "extension") and isinstance(plausibility, (int, float)) and plausibility > 0.6:
        score += 5.0
    return score

def _prescreen_async(p, proposal_path, symbol):
    """Fire-and-forget Laya prescreen (daemon thread, 不阻塞 harvest)。

    prescreen 是软建议伴随元数据，不应拖慢 supervisor 收割循环。
    - daemon=True: 进程退出时自动杀死，不阻塞 shutdown
    - 失败静默丢弃 (记录 warning)，不影响主流程
    - 幂等守卫: 已有 status=success 的结果则跳过，避免每轮重复付费调用
    - 仍通过原子写盘落盘，慢环读到的一定是完整结果
    - 注意: 因异步, 本轮 _proposal_priority_score 读不到刚写入的结果,
      Phase2 降权在下一个收割周期才生效 (新提案首次调度用未调整分)。
    """
    # 幂等守卫 (WARN-3): 已有成功 prescreen 结果则不再重复调用
    try:
        from cascade.typesafe_prescreen import prescreen_and_save
    except Exception as _e:
        logging.warning("Laya 预筛导入失败 (%s): %s", proposal_path, _e)
        return

    _existing_ps = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if os.path.exists(_existing_ps):
        try:
            with open(_existing_ps, encoding="utf-8") as _f:
                if json.load(_f).get("status") == "success":
                    return
        except (json.JSONDecodeError, OSError):
            pass  # 损坏/失败结果 → 允许重试

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _verdicts_path = os.path.join(_root, "task_FM", "config", "aligned_verdicts.jsonl")
    _menu_path = os.path.join(_root, "task_FM", "covariate_menu.inc.md")

    def _run():
        try:
            _history = []
            if os.path.exists(_verdicts_path):
                with open(_verdicts_path, encoding="utf-8") as f:
                    _history = [json.loads(l) for l in f if l.strip()]
            _menu = {}
            if os.path.exists(_menu_path):
                with open(_menu_path, encoding="utf-8") as f:
                    _menu = {"text": f.read()}
            prescreen_and_save(
                proposal=p,
                proposal_path=proposal_path,
                symbol=symbol,
                verdict_history=_history,
                covariate_menu=_menu,
            )
        except Exception as _e:
            logging.warning("Laya 预筛异步调用失败 (%s): %s", proposal_path, _e)

    threading.Thread(target=_run, daemon=True).start()


def _proposal_priority_score(prop, cov, symbol, snapshot, status_map=None, repeat_counts=None, proposal_path=None):
    """机制化排序 (替代噪声小样本 EV)。确定性可复现。
    1) 协变量履历 (v23 口径): 同 cov 任一品种 (含自身; 生产经历史去重同 vid
       不可达) gate_pass=True 时, dir_acc 超过硬门 0.52 的部分 x200 加分。
       gate_pass 门槛为有意校准: 过硬门未过 FDR 的高 dir_acc 仍视为有意义信号
       (v23 完整 pass 定义见 registry_lib.pass_variants, 更严)。评审 M-1 登记。
       NaN/inf/bool dir_acc 一律不计入。
    2) 机制完备度: symbol_fit/kill/promote 齐全加分
    3) 新颖性: 未测组合加分 +5 (2026-09-17 探索偏置调整, 原 +2)
    4) 探索分: 协变量开发度 —— 该 cov 累计 ok verdicts 越少加分越高
       (0 个 +6 / 1 个 +4 / 2 个 +2 / >=3 个 0), 对冲履历分的利用偏置。
       平衡点 (可达路径: 已测 1 次 + 新组合有新颖分): 其他品种
       dir_acc > 0.53 的真履历胜过全新组合。评审 M-2 修正 (原误写 0.555)。
    5) 过门族迁移: 提案带 covariate_family 且该族在其他品种有 gate_pass 时 +8
       (压过全新 cov 的探索 +6)。
    6) 弱族: 同 cov_family ≥4 条 ok 且 0 过门时 -8。
    """
    score = 0.0
    n_cov_ok = 0
    for v in (snapshot or {}).values():
        if v.get("cov_override") == cov and v.get("status", "ok") == "ok":
            n_cov_ok += 1
            da = v.get("dir_acc")
            if v.get("gate_pass") and isinstance(da, (int, float)) and not isinstance(da, bool):
                da = float(da)
                if da == da and -1e308 < da < 1e308:
                    score += max(0.0, da - 0.52) * 200.0
    for key in ("symbol_fit", "kill_condition", "promote_condition"):
        if str(prop.get(key) or "").strip():
            score += 1.0
    if "%s_%s" % (symbol, cov) not in (snapshot or {}):
        score += 5.0
    score += {0: 6.0, 1: 4.0, 2: 2.0}.get(n_cov_ok, 0.0)
    n_fail = 0
    for v in (snapshot or {}).values():
        if v.get("symbol") == symbol and v.get("status", "ok") == "ok" and not v.get("gate_pass"):
            n_fail += 1
    if n_fail >= 8:
        # Steeper curve: 8→-50, 9→-60, 10→-70, ...
        score -= 50.0 + 10.0 * (n_fail - 8)
    elif n_fail >= 3:
        score -= 8.0 * (n_fail - 2)
    if status_map is None:
        status_map = sup_evidence.load_symbol_status()
    st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
    if st == "DEAD":
        score -= 50.0
    elif st == "HOLD":
        score -= 20.0
    fam = str(prop.get("covariate_family") or "").strip()
    if fam:
        n_fam_ok = 0
        n_fam_pass = 0
        other_pass = False
        for v in (snapshot or {}).values():
            if str(v.get("cov_family") or "") != fam:
                continue
            if v.get("status", "ok") != "ok":
                continue
            n_fam_ok += 1
            if v.get("gate_pass"):
                n_fam_pass += 1
                if str(v.get("symbol") or "").lower() != str(symbol).lower():
                    other_pass = True
        if other_pass and st == "ACTIVE":
            score += 8.0
        if n_fam_ok >= 4 and n_fam_pass == 0:
            score -= 8.0
    # Cross-run repeat offender penalty
    # 注: 此 vid 是与快环 shared_findings.variant_name (旧式 symbol_cov) 的 join 键,
    # 不是 W6.4 实验身份 —— 勿改 build_variant_id, 否则 repeat penalty 静默失效。
    vid = "%s_%s" % (symbol, cov)
    repeat_counts = repeat_counts or {}
    n_runs = repeat_counts.get(vid, 0)
    if n_runs >= 3:
        score -= 20.0 + 10.0 * (n_runs - 3)  # 3→-20, 4→-30, 5→-40
    elif n_runs >= 2:
        score -= 8.0
    score = _apply_prescreen_score(score, proposal_path)
    return score

def _append_backlog(prop, src_path):
    """新协变量想法追加到 backlog (宿主评审用)，不入 aligned 队列。

    按 name 去重: harvest_proposals 每个 cycle 重扫所有 run, 同一 new_cov
    proposal 会被反复看到; 已在 backlog 的同名想法不得重复追加。
    返回 True=本次新增, False=同名已存在。
    """
    os.makedirs(os.path.dirname(sup_paths.BACKLOG_PATH), exist_ok=True)
    nc = prop.get("new_covariate") or prop.get("new_cov") or {}
    name = nc.get("name") or prop.get("cov_override")
    existing = set()
    if os.path.exists(sup_paths.BACKLOG_PATH):
        try:
            with open(sup_paths.BACKLOG_PATH, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        existing.add(json.loads(line).get("name"))
        except (OSError, json.JSONDecodeError):
            pass
    if name in existing:
        return False
    rec = {"ts": sup_lifecycle._now_iso(), "src": src_path,
           "name": name, "proposal": prop}
    with open(sup_paths.BACKLOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True

# ---------------------------------------------------------------------------
# PR-B6 提案质量门
# ---------------------------------------------------------------------------
# 口径说明: v2 verdict (fm.aligned_verdict.v2) 不含 pf/ev/ic —— 生产 registry
# 143 条全为 v2。因此评分与过滤一律基于 v2 可观测字段 (gate_pass / dir_acc /
# decided_at / cov_override / symbol)，不引入不可得字段。

MIN_QUALITY_SCORE = 0.0        # score < 该值 → 拒绝 (0.0 = 仅拦截净负分提案)
# SECTOR_BLOCK_MIN_FAILED 已废弃: 改为 sector_map 定义的全部品种都失败才拦截
# (见 _sector_filter_check 的 circuit-breaker 注释)
COV_CROSS_FAIL_MIN = 3         # 该协变量在其他品种失败 >= N 次且从无过门 → 拦截
SYMBOL_FAIL_WINDOW = 5         # 品种最近 N 次裁决全失败 → 扣分
COV_FAIL_WINDOW = 3            # 协变量在其他品种最近 N 次全失败 → 扣分


def _latest_verdict_per_symbol(snapshot):
    """每个品种最近一次 ok 裁决 → {symbol: verdict}

    当 decided_at 相同（或缺失导致都排序为 ""）时，取**最后**遇到的裁决
    (使用 `>=` 而非 `>`)。jsonl 是追加写入，同 key 时后到的通常更新，
    因此 `>=` 在 ties 时给出更符合直觉的"最新"裁决。
    """
    latest = {}
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        s = str(v.get("symbol") or "").lower().strip()
        if not s:
            continue
        cur = latest.get(s)
        if cur is None or sup_evidence._verdict_sort_key(v) >= sup_evidence._verdict_sort_key(cur):
            latest[s] = v
    return latest


def _recent_ok_verdicts(snapshot, predicate, n):
    """最近 n 条满足 predicate 的 ok 裁决（按 decided_at 升序取尾部）。"""
    rows = [v for v in (snapshot or {}).values()
            if isinstance(v, dict) and v.get("status", "ok") == "ok" and predicate(v)]
    rows.sort(key=sup_evidence._verdict_sort_key)
    return rows[-n:] if n > 0 else []


def _prescreen_plausibility(proposal_path):
    """读取 prescreen 侧写的 mechanism_plausibility；缺失/非法 → None。"""
    if not proposal_path:
        return None
    ps_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if not os.path.exists(ps_path):
        return None
    try:
        with open(ps_path, encoding="utf-8") as f:
            ps = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(ps, dict) or ps.get("status") != "success":
        return None
    p = ps.get("mechanism_plausibility")
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        return None
    p = float(p)
    if not (0.0 <= p <= 1.0):
        return None
    return p


def _has_proposal_version_status(status_path, proposal_id, version, statuses=None):
    """Check if proposal_id+version already has a record in proposal_status.jsonl.

    statuses: optional filter set (e.g. {"rejected", "queued", "verdicted"}).
    None = any status counts as duplicate.
    """
    if not os.path.exists(status_path):
        return False
    target = (proposal_id, version)
    with open(status_path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (r.get("proposal_id"), r.get("version")) == target:
                if statuses is None or r.get("status") in statuses:
                    return True
    return False


def _sector_filter_check(symbol, snapshot):
    """板块级拦截 (circuit-breaker 语义)。

    该品种所属板块在 config.sector_map 中定义的**全部**品种（不是仅有裁决的）
    其最近一次裁决均未过门 → 拦截。未观察到的品种视为"未评估"，不参与失败计数，
    因此未评估的品种不触发拦截。

    这是防饿死设计: 若仅凭 "≥N 个品种失败" 拦截，生产快照中所有三个板块都
    ≥3 失败 → 所有提案被拦 → 慢环饿死 (与 2026-09-24 no_failure_delta 饿死同构)。
    改为 "全部已观察品种 + 全部未观察品种都等于板块成员全集失败" 才拦，
    即只有板块真死透了才拦。

    T7 新增: 当失败数 >= 板块规模 50% 但未达全失败时，打 WARN 预警板块部分退化。

    Returns: (blocked, sector, n_failed)
    """
    from config.sector_map import SECTORS, sector_of
    sector = sector_of(symbol)
    if sector == "other":
        return False, sector, 0
    sector_size = len(SECTORS[sector])  # 板块在 sector_map 中定义的品种总数
    latest = _latest_verdict_per_symbol(snapshot)
    # 2026-10-03：失败数只认可确认的 DM 失败（见 _is_confirmable_failure）。
    # 否则描述性行会把板块推向断路器，而断路器一拦就是全局饿死。
    n_failed = sum(1 for s, v in latest.items()
                   if sector_of(s) == sector and sup_evidence._is_confirmable_failure(v))

    # T7: 板块部分退化预警（50% 阈值）
    if n_failed >= sector_size * 0.5 and n_failed < sector_size:
        logging.warning(
            f"Sector partial degradation: {sector} has {n_failed}/{sector_size} "
            f"symbols failed ({100*n_failed/sector_size:.0f}%). "
            f"Approaching circuit-breaker threshold."
        )

    # 仅当失败数 >= 板块成员总数时拦截（即全部成员都失败，包括未观察到的）
    return n_failed >= sector_size, sector, n_failed


def _covariate_filter_check(cov, symbol, snapshot):
    """协变量跨品种失败拦截。

    该协变量在**其他**品种上失败 >= COV_CROSS_FAIL_MIN 次，且从未在任一品种
    过门 → 拦截。有任一品种过门即放行（品种特异性优先于跨品种共性）。

    Returns: (blocked, n_other_fail, n_pass)
    """
    n_fail = 0
    n_pass = 0
    sym = str(symbol).lower().strip()
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        if str(v.get("cov_override") or "") != cov:
            continue
        if v.get("gate_pass"):
            n_pass += 1
        elif str(v.get("symbol") or "").lower().strip() != sym and sup_evidence._is_confirmable_failure(v):
            # 2026-10-04（E4）：同 _sector_filter_check —— 失败数只认可确认的
            # DM 失败（dm_status ∈ {ok, set_mismatch_ok}）。描述性行（dm_status
            # 缺省 / set_mismatch_descriptive / no_common_cutoff）不得把协变量
            # 推向跨品种拦截。
            n_fail += 1
    return (n_pass == 0 and n_fail >= COV_CROSS_FAIL_MIN), n_fail, n_pass


def _proposal_quality_gate(prop, snapshot, proposal_path=None):
    """基于历史表现的提案质量评分 (PR-B6)。

    评分项（全部基于 v2 可观测字段）：
      +5    该品种有过成功协变量 (gate_pass=True)
      +3    该组合从未测过 (新颖性)
      +3    机制论证完整 (symbol_fit/kill_condition/promote_condition 齐全)
      +10 * prescreen mechanism_plausibility
      -20   该协变量在其他品种最近 COV_FAIL_WINDOW 次裁决全失败
      -15   该品种最近 SYMBOL_FAIL_WINDOW 次裁决全失败

    Returns: (score, breakdown dict)
    """
    symbol = str(prop.get("symbol") or "").lower().strip()
    cov = str(prop.get("cov_override") or "").strip()
    snap = snapshot or {}
    bd = {}

    # +5 该品种有过成功协变量（必须与 pass_variants 严格定义一致，排除探索运行）
    # §1.4: 探索运行不得出现在任何"已确认"表述中
    sym_pass = any(
        isinstance(v, dict)
        and v.get("status", "ok") == "ok"
        and v.get("run_mode") in rl.RUN_MODES
        and v.get("run_mode") != "exploration"
        and v.get("gate_pass")
        and v.get("fdr_pass")
        and v.get("p_value") is not None
        and str(v.get("symbol") or "").lower().strip() == symbol
        for v in snap.values()
    )
    bd["symbol_has_pass"] = 5.0 if sym_pass else 0.0

    # +3 新颖性: 该组合从未出现在 snapshot
    bd["novel_combo"] = 3.0 if ("%s_%s" % (symbol, cov)) not in snap else 0.0

    # +3 机制论证完整
    complete = all(str(prop.get(k) or "").strip()
                   for k in ("symbol_fit", "kill_condition", "promote_condition"))
    bd["mechanism_complete"] = 3.0 if complete else 0.0

    # +10 * prescreen plausibility
    plaus = _prescreen_plausibility(proposal_path)
    bd["prescreen"] = 10.0 * plaus if plaus is not None else 0.0

    # -20 该协变量在其他品种最近 N 次全失败
    cov_recent = _recent_ok_verdicts(
        snap,
        lambda v: str(v.get("cov_override") or "") == cov
        and str(v.get("symbol") or "").lower().strip() != symbol,
        COV_FAIL_WINDOW)
    bd["cov_recent_fail"] = -20.0 if (
        len(cov_recent) == COV_FAIL_WINDOW
        and not any(v.get("gate_pass") for v in cov_recent)) else 0.0

    # -15 该品种最近 M 次全失败
    sym_recent = _recent_ok_verdicts(
        snap,
        lambda v: str(v.get("symbol") or "").lower().strip() == symbol,
        SYMBOL_FAIL_WINDOW)
    bd["symbol_recent_fail"] = -15.0 if (
        len(sym_recent) == SYMBOL_FAIL_WINDOW
        and not any(v.get("gate_pass") for v in sym_recent)) else 0.0

    return sum(bd.values()), bd


def harvest_proposals(root, snapshot, dead, existing, pool, top_k,
                      aligned_max_points=600, priority_symbols=None,
                      search_policy="off"):
    """收割 peer 机制化假设 (results/**/proposals/*.json) → aligned 队列行。
    与 harvest_survivors 平行但:
      - 不依赖诊断评估 (peer 不跑 eval)，验证证据来自慢环
      - 强制机制论证 (mechanism>=40 字)
      - 多样性按 family (QD 门)
      - priority_symbols (目标 1 星品种) 优先选座: 其中当前有效点 n>=350 的最先,
        样本暂不足的次之, 其余品种最后 —— 慢环是瓶颈, 座位优先给能直接推进目标的组合
    new_cov_*.json (new_covariate 字段) → 汇入 backlog, 不入队。
    返回 (selected_rows, stats)。
    """
    priority = set(priority_symbols or [])
    n_cache = {}
    ev = sup_evidence._load_evaluator()
    status_map = sup_evidence.load_symbol_status()
    # ── 写盘前全局 variant 登记（SPEC v3.1 §5.1）──
    _vreg = VariantRegistry(sup_paths.VARIANT_REGISTRY_PATH)
    _vreg.load()
    stats = {"seen": 0, "rejected": 0, "backlog": 0, "selected": 0,
             "reject_reasons": {},
             # spec 2026-10-05 §6.1：档位随收割留档（off|shadow|enforce）
             "search_policy": search_policy,
             # PR-B6 质量门计数（键名与 reject_reasons 一致，防止两套计数漂移）
             "quality_below_threshold": 0, "sector_blocked": 0, "cov_cross_fail": 0,
             # T2 (2026-10-05): success 门分类计数（放行侧也计数，供观察口径是否过宽）
             "success_gate_states": {},
             # SPEC v3.1 §5.1: variant registry 命中统计
             "registry_hit": 0}
    _sg_cache = {}  # T2: 单次 harvest 内复用评估窗锚与行级 eval_end_ts
    passing_ids = {v["variant_id"] for v in rl.pass_variants(snapshot or {})}
    archived = getattr(ev, "ARCHIVED_COVARIATES", {}) if ev else {}
    valid_covs = getattr(ev, "VALID_COVARIATES", None) if ev else None
    allowed_syms = getattr(ev, "ALLOWED_SYMBOLS", None) if ev else None
    # ── P2.2 / P2.9 (spec §6.2 / §6.1) 搜索树资格门。
    # enforce：拒绝生效，guard-pass 即内存建树/占座。
    # shadow：同一套检查只记「本会拒绝」，不拒绝、不把树字段带进队列、不写账。
    # off：不构造守卫。──
    search_guard = None
    shadow_guard = None
    if search_policy == "enforce":
        search_guard = st.SearchGuard.load(sup_paths.SEARCH_COMMITMENTS_PATH, snapshot or {})
    elif search_policy == "shadow":
        shadow_guard = st.SearchGuard.load(sup_paths.SEARCH_COMMITMENTS_PATH, snapshot or {})
        stats["search_would_reject"] = {}
        stats["search_shadow_log"] = []

    def _reject(reason):
        stats["rejected"] += 1
        stats["reject_reasons"][reason] = stats["reject_reasons"].get(reason, 0) + 1
        # 安全写盘（P0-2）：写盘失败不得改变统计语义
        try:
            _run_id = os.path.basename(run_dir)  # src_run，禁止虚构 current_run_id
            # _qs, _bd 已在循环开头重置为 None（P1-A）；若质量门已计算则填充真实值
            write_rejected_proposal(
                rejected_file=sup_paths.REJECTED_PROPOSALS_PATH,
                proposal_id=_proposal_id or "no_id",
                version=_version,
                reject_reason=reason,
                quality_score=_qs,
                run_id=_run_id,
                symbol=_symbol,
                cov_override=_cov,
                covariate_family=p.get("covariate_family"),
                breakdown=_bd,
            )
            write_proposal_status(
                status_file=sup_paths.PROPOSAL_STATUS_PATH,
                proposal_id=_proposal_id or "no_id",
                version=_version,
                status="rejected",
                run_id=_run_id,
                reject_reason=reason,
                quality_score=_qs,
            )
        except Exception:
            import logging as _logging
            _logging.getLogger("sup_harvest").warning(
                "failed to write proposal status/rejected for %s: %s",
                _proposal_id or "no_id", reason, exc_info=True)

    candidates = []
    seen_vids = set()
    run_dirs = sorted(glob.glob(os.path.join(root, "task_FM", "experiments", "run_*")),
                      key=os.path.getmtime, reverse=True)
    # ── Phase 1 Task 5: pre-loop scope init (prevents NameError in _reject before first p) ──
    _qs = None; _bd = None; _proposal_id = None; _version = 1
    _symbol = None; _cov = None
    for run_dir in run_dirs:
        if sup_lifecycle._SHUTDOWN_REQUESTED:
            # 长扫描不得吃掉停机信号：立刻中止，且不返回半份候选（避免停机途中入队）
            stats["aborted_by_shutdown"] = True
            return [], stats
        for sp in glob.glob(os.path.join(run_dir, "results", "**", "proposals", "*.json"),
                            recursive=True):
            if sup_lifecycle._SHUTDOWN_REQUESTED:
                stats["aborted_by_shutdown"] = True
                return [], stats
            # ── SPEC v3.1 §5.1: 写盘前 variant 登记检查 ──
            _stem = Path(sp).stem
            if _vreg.has_stem(_stem):
                stats["registry_hit"] += 1
                continue
            try:
                with open(sp, encoding="utf-8") as f:
                    p = json.load(f)
            except Exception:
                _reject("unparseable_json"); continue
            stats["seen"] += 1
            # ── SPEC v3.1 §5.1: 解析成功后立即注册 stem（无论后续入队或拒绝）──
            _vreg.register(_stem, os.path.basename(run_dir))
            # ── Phase 1 Task 5: per-proposal scope reset (P1-A) ──
            _qs = None  # quality_score
            _bd = None  # quality breakdown
            _proposal_id = p.get("proposal_id")
            _version = int(p.get("version") or 1)
            _symbol = p.get("symbol")
            _cov = p.get("cov_override")
            # 批次 F (M4)：abandon 提案处理
            # peer 输出 decision="abandon" 表示反对当前假设，不入队、不加分
            if p.get("decision") == "abandon":
                sup_lifecycle._log_decision(log, "proposal_abandoned",
                             f"peer={p.get('peer_id', 'unknown')} reason={p.get('abandon_reason', 'N/A')}")
                _reject("decision_abandon")
                continue
            # 新协变量想法 → backlog（不要求 hypothesis_proposal schema）
            if p.get("new_covariate") or p.get("new_cov"):
                if _append_backlog(p, sp):
                    stats["backlog"] += 1
                else:
                    _reject("backlog_dup")
                continue
            _schema = p.get("schema")
            if _schema not in _ACCEPTED_SCHEMAS:
                _reject("schema_mismatch"); continue
            if _schema == "fm.hypothesis_proposal.v2" and not _check_v2_version(p):
                _reject("schema_mismatch"); continue
            # ── Phase 1 Task 5: explicit missing_proposal_id reject (P1-B) ──
            if not _proposal_id:
                _reject("missing_proposal_id")
                continue
            symbol = str(p.get("symbol") or "").lower().strip()
            cov = str(p.get("cov_override") or "").strip()
            mechanism = str(p.get("mechanism") or "").strip()
            if not symbol or not cov:
                _reject("missing_symbol_or_cov"); continue
            # ── P2.2 (spec §6.2) 树资格检查钉在管道最前（先于池/机制长度/族
            # 死亡/去重/质量门/成功门）。族未解析时跳过守卫，归因仍走下方既有
            # family_unresolved（树拒绝码不覆盖非树归因）。──
            search_info = None
            if search_guard is not None:
                _fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
                if _fam:
                    _pid = os.path.relpath(sp, root)
                    _sr, search_info = search_guard.check(
                        p, symbol, _fam, cov, _pid)
                    if _sr is not None:
                        _reject(_sr); continue
                    # P2.3 (spec §6.7)：落账辅助字段（spec 三字段之外的记账
                    # 辅助）——写入器按行落 accept 时不再反查 pool/relpath。
                    search_info["search_family"] = _fam
                    search_info["search_proposal_id"] = _pid
            if shadow_guard is not None:
                _fam_s = ((pool.get(cov, {}) or {}).get("family")
                          or p.get("covariate_family") or "")
                if _fam_s:
                    _sr_s, _shadow_info = shadow_guard.check(
                        p, symbol, _fam_s, cov, os.path.relpath(sp, root))
                    if _sr_s is not None:
                        bucket = stats["search_would_reject"]
                        bucket[_sr_s] = bucket.get(_sr_s, 0) + 1
                        stats["search_shadow_log"].append(
                            "%s %s" % (_sr_s, os.path.relpath(sp, root)))
            if allowed_syms is not None and symbol not in allowed_syms:
                _reject("symbol_not_allowed"); continue
            if cov in archived:
                _reject("cov_archived"); continue
            if valid_covs is not None and cov not in valid_covs:
                _reject("cov_not_in_active_pool"); continue
            if not sup_evidence._symbol_has_current_nocov_baseline(symbol, root):
                _reject("no_current_baseline"); continue
            if len(mechanism) < 40:
                _reject("mechanism_too_short"); continue
            sym_st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
            if sym_st == "DEAD":
                _reject("symbol_dead"); continue
            if sym_st == "HOLD":
                _reject("symbol_hold"); continue
            # DEAD family check: 4+ ok verdicts, 0 pass → family is dead
            dead_fams = sup_evidence._dead_families(snapshot or {})
            fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
            if not fam:
                _reject("family_unresolved"); continue
            if fam in dead_fams:
                _reject("family_dead"); continue
            # W6.4 (spec §4.5): vid = 实验身份 {symbol}_{cov_family}_{experiment_fp[:12]},
            # 非请求名拼接; 身份要素不可解析 → 拒收, 禁止回退旧式 symbol_cov。
            fp = sup_evidence._experiment_fp_for(symbol, cov)
            if fp is None:
                _reject("experiment_fp_unavailable"); continue
            vid = ef.build_variant_id(symbol, fam, fp)
            if sup_evidence._has_prior_failure(snapshot or {}, symbol, cov):
                delta = str(p.get("failure_delta") or "").strip()
                if len(delta) < 20:
                    _reject("no_failure_delta"); continue
            if vid in dead or vid in existing or vid in passing_ids or vid in seen_vids:
                _reject("dedup"); continue
            seen_vids.add(vid)

            # ── P3.2: proposal_id+version dedup (spec §3.5.3) ──
            if _has_proposal_version_status(
                    sup_paths.PROPOSAL_STATUS_PATH, _proposal_id, _version):
                _reject("version_dup"); continue

            # ── PR-B6 提案质量门 (在 dedup 之后，保证既有 reject 归因不变) ──
            _snap = snapshot or {}
            sec_blocked, sector, _sec_failed = _sector_filter_check(symbol, _snap)
            if sec_blocked:
                stats["sector_blocked"] += 1
                _reject("sector_blocked"); continue
            cov_blocked, _cov_fail_n, _cov_pass_n = _covariate_filter_check(cov, symbol, _snap)
            if cov_blocked:
                stats["cov_cross_fail"] += 1
                _reject("cov_cross_fail"); continue
            quality_score, _quality_bd = _proposal_quality_gate(p, _snap, proposal_path=sp)
            _qs, _bd = quality_score, _quality_bd  # P0-2: 回填到 _reject 可见的外层作用域
            if quality_score < MIN_QUALITY_SCORE:
                stats["quality_below_threshold"] += 1
                _reject("quality_below_threshold"); continue

            # ── T2 (2026-10-05) 已成功组合增量论证门（dedup+PR-B6 之后、
            # prescreen 之前——只作用于此前会被选中的提案，既有 reject 归因
            # 绝对不变）──
            _sg_reason, _sg_state = sup_evidence._success_delta_gate(
                p, symbol, cov, _snap, root, cache=_sg_cache)
            stats["success_gate_states"][_sg_state] = \
                stats["success_gate_states"].get(_sg_state, 0) + 1
            if _sg_reason is not None:
                _reject(_sg_reason); continue

            family = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or "other"
            repeat_counts = _cross_run_repeat_counts()
            score = _proposal_priority_score(p, cov, symbol, snapshot or {},
                                            status_map=status_map,
                                            repeat_counts=repeat_counts,
                                            proposal_path=sp)
            if priority:
                if symbol not in n_cache:
                    n_cache[symbol] = sup_evidence._valid_n_for_symbol(symbol)
                n_now = n_cache[symbol]
                # 0=目标品种且当前可过门; 1=目标品种但样本暂不足(cj/lh); 2=非目标品种; 查询失败归 1
                if symbol not in priority:
                    tier = 2
                elif n_now is not None and n_now >= sup_paths.RETEST_GATE_N:
                    tier = 0
                else:
                    tier = 1
            else:
                tier = 0
            _cand = {
                "variant_id": vid, "symbol": symbol, "cov_override": cov,
                "max_points": int(aligned_max_points), "stage": "aligned",
                "checkpoint_path": "", "enqueued_at": sup_lifecycle._now_iso(),
                "src_run": os.path.basename(run_dir), "source": "peer_proposal",
                # PR-B6 质量门留痕 (队列行，供宿主审查门是否过严)
                "quality_score": round(quality_score, 4), "sector": sector,
                # Phase 1: 绑定键（P0-1），禁止 "unknown" 哨兵（P1-B）
                "proposal_id": _proposal_id,
                "version": _version,
                "_family": family, "_score": score, "_tier": tier,
                "_proposal_path": sp}
            if search_info is not None:
                # P2.2 (spec §6.2): enforce 档队列行携带树三字段（2.3 落账依据）；
                # off/shadow 不带（S1：off 下行形状与今日相同）
                _cand.update(search_info)
            candidates.append(_cand)
            # ── Phase 1 Task 5: 成功入队 → 写入 status (queued) ──
            try:
                write_proposal_status(
                    status_file=sup_paths.PROPOSAL_STATUS_PATH,
                    proposal_id=_cand["proposal_id"],
                    version=_cand["version"],
                    status="queued",
                    run_id=os.path.basename(run_dir),
                    variant_id=_cand["variant_id"],
                    quality_score=round(quality_score, 4),
                )
            except Exception:
                import logging as _logging
                _logging.getLogger("sup_harvest").warning(
                    "failed to write queued status for %s", _cand.get("proposal_id"), exc_info=True)
            # ── Laya 预筛触发 (fire-and-forget, 不阻塞 harvest) ──
            _prescreen_async(p, sp, symbol)

    candidates.sort(key=lambda r: (r["_tier"], -r["_score"], r["_family"], r["variant_id"]))
    selected = []
    used_families = set()
    # Pass 1: 每个 family 一个名额 (QD 多样性)
    for r in candidates:
        if len(selected) >= int(top_k):
            break
        if r["_family"] in used_families:
            continue
        selected.append(r); used_families.add(r["_family"])
    # Pass 2: 剩余名额按分数补
    if len(selected) < int(top_k):
        sel_ids = {r["variant_id"] for r in selected}
        for r in candidates:
            if len(selected) >= int(top_k):
                break
            if r["variant_id"] not in sel_ids:
                selected.append(r); sel_ids.add(r["variant_id"])
    for r in selected:
        r.pop("_family", None); r.pop("_score", None); r.pop("_tier", None)
    stats["selected"] = len(selected)
    return selected, stats

def materialize_covariate_menu(pool, dest_path):
    """从协变量池生成 peer 菜单 (active 机制目录 + archived 禁用块)。"""
    lines = ["## Covariate pool (supervisor snapshot)",
             "Propose symbol x covariate combos ONLY with ACTIVE covariates below.",
             "Each covariate carries a mechanism hypothesis — your own mechanism argument must extend it to the chosen symbol.",
             "archived covariates are RETIRED: do NOT propose them.",
             ""]
    active = {n: v for n, v in pool.items() if v.get("status") == "active"}
    archived = {n: v for n, v in pool.items() if v.get("status") == "archived"}
    experimental = {n: v for n, v in pool.items() if v.get("status") == "experimental"}
    by_fam = {}
    for n, v in active.items():
        by_fam.setdefault(v.get("family", "other"), []).append((n, v))
    for fam in sorted(by_fam):
        lines.append("### family: %s" % fam)
        for n, v in sorted(by_fam[fam]):
            tr = " 【旧口径线索·非证据】[track: %s]" % v["track_record"] if v.get("track_record") else ""
            lines.append("- %s: %s%s" % (n, v.get("mechanism", ""), tr))
        lines.append("")
    if experimental:
        lines.append("### experimental (host testing — do not propose yet)")
        for n in sorted(experimental):
            lines.append("- %s" % n)
        lines.append("")
    if archived:
        lines.append("### archived — DO NOT PROPOSE")
        for n in sorted(archived):
            lines.append("- %s: %s" % (n, archived[n].get("archived_reason", "archived")))
        lines.append("")
    # 品种样本天花板 (本地库当前可对齐有效点; 硬门 n>=350)。fail-open：无 DB/查询失败则跳过。
    try:
        n_table = sup_evidence._symbol_n_table()
    except Exception as exc:
        # 仅预期失败 (DB 连接/查询); 其余 (ImportError, AttributeError) 需浮出
        if isinstance(exc, (ImportError, AttributeError, SyntaxError)):
            raise
        n_table = []
    if n_table:
        lines.append("### symbol sample ceiling (valid aligned points now; hard gate n>=350)")
        lines.append("BELOW GATE symbols cannot pass today regardless of covariate "
                     "(1H bars accrue over time; supervisor auto-retests near-misses):")
        for sym, n in n_table:
            tag = "unknown" if n is None else ("gate-reachable" if n >= sup_paths.RETEST_GATE_N else "BELOW GATE")
            lines.append("- %s: n=%s %s" % (sym, "?" if n is None else n, tag))
        lines.append("")
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
