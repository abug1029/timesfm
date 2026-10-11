import json
import os
import sys
import time

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
del _repo_root

import registry_lib as rl

try:
    from cascade.statistical_tests import bh_fdr_promote
except ImportError:
    bh_fdr_promote = None

from cascade.research_family import (  # noqa: E402
    all_terminal as _fam_all_terminal,
    default_family_key as _fam_default_key,
    make_member as _fam_make_member,
    register_member as _fam_register_member,
    seal_family as _fam_seal_family,
)

import sup_evidence
import sup_lifecycle
import sup_paths
import sup_state

_PERSISTABLE_DM = frozenset({"ok", "set_mismatch_ok"})


def fdr_pass_persistable(verdict):
    """W3.4：只有确认运行、缺失可接受、且 DM 状态可确认时，fdr_pass=True 才能落盘。

    步③ B（2026-10-07 裁定 A.3）：旧行缺 admissibility_rule 不计入、不回溯解释。
    """
    if not isinstance(verdict, dict):
        return False
    return (
        verdict.get("run_mode") == "confirmation"
        and verdict.get("missingness_admissible") is True
        and verdict.get("dm_status") in _PERSISTABLE_DM
        and verdict.get("admissibility_rule") is not None
    )


def promote_batch_for_persistence(verdicts):
    """先做原 BH/Bonferroni，再拒绝不可确认行的 True。不写文件。"""
    updates = bh_fdr_promote(verdicts)
    by_vid = {}
    for verdict in verdicts or []:
        vid = verdict.get("variant_id")
        if vid is not None:
            by_vid[vid] = verdict
    for vid, update in updates.items():
        if update.get("fdr_pass") is True and not fdr_pass_persistable(by_vid.get(vid)):
            update["fdr_pass"] = False
    return updates

# ── PR-C2: 研究 family 接线（spec 4.3 W3.6）────────────────────
# 纯逻辑在 cascade/research_family.py（唯一家）；此处只做 supervisor 侧接线，
# 避免 family 状态机散落进监督环。

def family_key_for(symbol, **kwargs):
    """该品种的默认研究 family 键（一个品种 = 一个 family）。"""
    return _fam_default_key(symbol, **kwargs)


def register_family_member(family_key, symbol, variant_id, registered_at,
                           members, run_mode="confirmation"):
    """把一个确认成员登记进 family。返回 (成员列表, 结果标签)。

    探索期结果会被拒绝进入 —— 探索自由、确认严格是本设计的分界线。
    """
    member = _fam_make_member(
        family_key, symbol, variant_id, registered_at, run_mode=run_mode
    )
    return _fam_register_member(members, member, registered_at)


def seal_research_family(members, now):
    """封账：全部成员终态后一次性跑 family 级 BH-FDR。"""
    return _fam_seal_family(members, now)


def _prereg_field(row, key, default=None):
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(row, key, default)


def _find_prereg(registry, prereg_id):
    for row in registry:
        if _prereg_field(row, "prereg_id") == prereg_id:
            return row
    return None


def dispatch_confirmation(proposal, registry, members):
    """确认分派。不启动监督环。

    调用 queue_decision。拒绝则不登记 family；接受则 register_family_member。
    """
    import preregistry as _prereg

    decision = _prereg.queue_decision(proposal, registry, run_mode="confirmation")
    if not decision.accepted:
        return {
            "accepted": False,
            "reason": decision.reason,
            "run_label": decision.run_label,
            "prereg_id": decision.prereg_id,
            "members": members,
            "registration": None,
        }
    matched = _find_prereg(registry, decision.prereg_id)
    symbol = proposal.get("symbol") or _prereg_field(matched, "symbol")
    variant_id = proposal.get("variant_id")
    if not variant_id:
        raise ValueError("confirmation proposal requires variant_id")
    registered_at = _prereg_field(matched, "registered_at")
    family_key = proposal.get("family_key") or family_key_for(symbol)
    new_members, tag = register_family_member(
        family_key, symbol, variant_id, registered_at, members,
        run_mode="confirmation",
    )
    return {
        "accepted": True,
        "reason": None,
        "run_label": decision.run_label,
        "prereg_id": decision.prereg_id,
        "members": new_members,
        "registration": tag,
    }


def _stamp_member(members, row, label):
    variant_id = row.get("variant_id")
    stamped = []
    for member in members:
        member = dict(member)
        if variant_id is not None and member.get("variant_id") == variant_id:
            member["status"] = label
            if "p_value" in row:
                member["p_value"] = row.get("p_value")
        stamped.append(member)
    return stamped


def _seal_if_all_terminal(members, label, now, audit):
    # underpowered / refuted_by_contamination 也是终态，可以封账。
    # family_bh_fdr 对这两种状态固定按 p=1，不看成员上已写的 p_value。
    if _fam_all_terminal(members):
        sealed, _adjusted = seal_research_family(members, now)
        return {
            "run_label": label,
            "audit": audit,
            "members": sealed,
            "sealed": True,
        }
    return {
        "run_label": label,
        "audit": audit,
        "members": members,
        "sealed": False,
    }


def finalize_confirmation(row, members, now):
    """终结一条确认。不启动监督环，不把 fdr_pass 写成 True。

    样本未满且行上没有 request_early_seal 时，只返回 peek 审计，不改标签。
    显式提前封账走 early_seal。样本已满走 classify_confirmation，
    全体终态才 seal_research_family。
    """
    import preregistry as _prereg

    n_actual = row["n_confirm_actual"]
    n_required = row["n_confirm_required"]
    if n_actual < n_required and row.get("request_early_seal") is not True:
        decision = _prereg.peek_gate(n_actual, n_required)
        return {
            "run_label": row.get("run_label"),
            "audit": decision.audit,
            "members": members,
            "sealed": False,
        }
    if n_actual < n_required:
        seal = _prereg.early_seal(n_actual, n_required)
        updated = _stamp_member(members, row, seal.terminal_state)
        return _seal_if_all_terminal(updated, seal.terminal_state, now, None)
    label = _prereg.classify_confirmation(row)
    updated = _stamp_member(members, row, label)
    return _seal_if_all_terminal(updated, label, now, None)


_BASE_COVARIATE = "daily_slope"


def _requested_covariate(prereg_row):
    keys = ((prereg_row or {}).get("cov_fingerprint") or {}).get("keys") or []
    extra = [key for key in keys if key != _BASE_COVARIATE]
    if len(extra) != 1:
        return None
    return extra[0]


def confirmation_queue_row(prereg_row, variant_id):
    cov = _requested_covariate(prereg_row)
    n_req = int(prereg_row["n_confirm_required"])
    return {
        "variant_id": variant_id,
        "symbol": str(prereg_row["symbol"]).lower(),
        "cov_override": cov,
        "max_points": n_req,
        "stage": "aligned",
        "checkpoint_path": "",
        "enqueued_at": sup_lifecycle._now_iso(),
        "src_run": "confirmation_dispatch",
        "source": "confirmation",
        "run_mode": "confirmation",
        "prereg_id": prereg_row["prereg_id"],
        "confirm_from_ts": prereg_row["confirm_from_ts"],
        "n_confirm_required": n_req,
    }


def due_confirmations(registry, now_ts, blocked_ids, already_ran_ids,
                      fingerprint_for, family_for):
    """到期且未占用、未跑过的预注册。不入队，不读时钟，不读权重。"""
    import cascade.experiment_fingerprint as ef

    out = []
    for row in registry or []:
        if not isinstance(row, dict):
            continue
        if row.get("terminal_state") not in (None, ""):
            continue
        confirm_from = row.get("confirm_from_ts")
        if not isinstance(confirm_from, str) or confirm_from > now_ts:
            continue
        if row.get("prereg_id") in already_ran_ids:
            continue
        cov = _requested_covariate(row)
        if cov is None:
            continue
        fp = fingerprint_for(str(row.get("symbol") or "").lower(), cov)
        fam = family_for(cov)
        if not fp or not fam:
            continue
        vid = ef.build_variant_id(str(row["symbol"]).lower(), fam, fp)
        if vid in blocked_ids:
            continue
        out.append(confirmation_queue_row(row, vid))
    return out


def load_family_members(path):
    by_vid = {}
    order = []
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            member = json.loads(line)
            vid = member.get("variant_id")
            if vid not in by_vid:
                order.append(vid)
            by_vid[vid] = member
    return [by_vid[vid] for vid in order]


def save_family_members(path, members):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for member in members:
            fh.write(json.dumps(member, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _merge_family_members(members, family_key, returned):
    """同一 family_key 整段替换。其它 family 的相对顺序保留。"""
    returned = list(returned or [])
    out = []
    placed = False
    for member in members:
        if member.get("family_key") != family_key:
            out.append(member)
            continue
        if not placed:
            out.extend(returned)
            placed = True
    if not placed:
        out.extend(returned)
    return out


def _confirm_data_ready(symbol, confirm_from_ts):
    """该品种的 1H 数据是否已越过 confirm_from_ts。

    2026-10-03（D1）：confirm_from_ts 是注册时锁定的固定日历边界，但数据要过几天
    才追上来。边界之前派发确认行 → 评估窗口必然为空 → 每轮落一座 no_data 墓碑
    （实测每 ~5.7 分钟一座）。这里做 fail-closed 的数据闸门：查不到数据也算未就绪。
    查询结果按 symbol 缓存 30 分钟，避免每轮打库。
    """
    latest = sup_state._latest_data_dt(symbol)
    if not latest:
        return False
    return latest > str(confirm_from_ts)


def _confirmation_is_final(v):
    """确认终态 = 真实评估落账且样本已满（n_confirm_actual >= n_confirm_required）。

    2026-10-04（E1）：peek（status=ok 但样本未满）不算终态。字段缺失视为
    非终态（走 E2 节流自愈），同时防御 None 参与比较崩溃。
    """
    if not isinstance(v, dict) or v.get("status") != "ok":
        return False
    n_act = v.get("n_confirm_actual")
    n_req = v.get("n_confirm_required")
    return n_act is not None and n_req is not None and n_act >= n_req


def _maybe_enqueue_confirmations(log, now_ts):
    registry = sup_state.load_preregistry(sup_paths.PREREGISTRY_PATH)
    blocked = rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS)
    snap = sup_evidence._active_protocol_snapshot(sup_paths.REGISTRY)
    # 2026-10-04（E1）：只有满样终态裁决才算「已跑过」。D1 闸门只保证有
    # 1 根 bar 越过 confirm_from_ts，不保证 1199/986 个带 24h 前向标签的
    # 样本已就位——数据恢复后的首裁决必然是 status=ok 的未满样 peek
    # （_finalize_confirmation_verdict 的既有语义），若把 peek 计入
    # already，该预注册将永不再派发，n_confirm_required 永远到不了，
    # 确认通道静默死亡。no_data / error / timeout 墓碑同理不占坑；
    # 重派频次由 E2 节流兜底，不会 churn。
    already = {
        v.get("prereg_id") for v in (snap or {}).values()
        if isinstance(v, dict) and v.get("prereg_id")
        and _confirmation_is_final(v)
    }
    pool = sup_evidence.load_covariate_pool()

    def family_for(cov):
        return (pool.get(cov) or {}).get("family")

    rows = due_confirmations(
        registry, now_ts, blocked, already, sup_evidence._experiment_fp_for, family_for)
    # 2026-10-03（D1）：数据未越过 confirm_from_ts 的先不派发 —— 否则空评估 +
    # no_data 墓碑 + 去重失效 = 每轮重复入队。已在队里的不受影响。
    rows = [r for r in rows
            if _confirm_data_ready(r["symbol"], r.get("confirm_from_ts") or "")]
    # 2026-10-04（E2）：非终态结果不永久占坑，但每 prereg 至少间隔 6h 才重派。
    # 否则未满样期间每 ~5.7 分钟一条 peek/墓碑（~250 行/天 × ~50 天填充期
    # ≈ 1.2 万行/prereg），等于把 D1 修掉的死循环换个形式请回来。
    _now_r = time.time()
    throttled = set()
    kept = []
    for r in rows:
        _pid = r.get("prereg_id") or ""
        if _now_r - _CONFIRM_REDISPATCH.get(_pid, 0.0) < _CONFIRM_REDISPATCH_TTL_S:
            throttled.add(_pid)
            continue
        kept.append(r)
    rows = kept
    produced = {row["prereg_id"] for row in rows}
    for src in registry:
        if not isinstance(src, dict) or src.get("terminal_state") not in (None, ""):
            continue
        confirm_from = src.get("confirm_from_ts")
        if not isinstance(confirm_from, str) or confirm_from > now_ts:
            continue
        if src.get("prereg_id") in already or src.get("prereg_id") in produced:
            continue
        # 2026-10-03：确认通道要跑 1.2–2.0 年，无条件每轮记账会写出
        # 30–40 万条/年（实测 17 分钟 8 条）。同一 prereg 每 6h 记一次。
        _pid = src.get("prereg_id") or ""
        _last = _CONFIRMATION_NOTICE.get(_pid, 0.0)
        _now = time.time()
        if _now - _last < _CONFIRMATION_NOTICE_TTL_S:
            continue
        _CONFIRMATION_NOTICE[_pid] = _now
        _state = ("redispatch_throttle"
                  if (src.get("prereg_id") or "") in throttled else "not_ready")
        sup_lifecycle._log_decision(log, "confirmation_not_enqueued",
                      src.get("prereg_id") or "",
                      [str(src.get("symbol") or ""), _state])
    if not rows:
        return 0
    added = 0
    members = load_family_members(sup_paths.FAMILY_REGISTRY)
    for row in rows:
        try:
            family_key = family_key_for(row["symbol"])
            proposal = {
                "prereg_id": row["prereg_id"],
                "symbol": row["symbol"],
                "variant_id": row["variant_id"],
                "family_key": family_key,
            }
            family_members = [
                member for member in members
                if member.get("family_key") == family_key
            ]
            # 已登记只跳过再次 register。没进快照、也不在队里时仍可入队一次。
            registered = any(
                member.get("variant_id") == row.get("variant_id")
                for member in family_members
            )
            if not registered:
                decision = dispatch_confirmation(proposal, registry, family_members)
                if not decision["accepted"] or str(decision.get("registration") or "").startswith("rejected"):
                    sup_lifecycle._log_decision(log, "confirmation_rejected",
                                  decision.get("reason") or decision.get("registration") or "",
                                  [row["variant_id"]])
                    continue
                members = _merge_family_members(members, family_key, decision.get("members") or [])
                save_family_members(sup_paths.FAMILY_REGISTRY, members)
            n = rl.queue_enqueue(sup_paths.QUEUE, [row], dead=set(), existing=set())
            added += n
            if n:
                sup_lifecycle._log_decision(log, "confirmation_enqueued", row["prereg_id"], [row["variant_id"]])
                _CONFIRM_REDISPATCH[row["prereg_id"]] = time.time()
        except Exception as e:
            sup_lifecycle._log_decision(log, "confirmation_enqueue_error", str(e),
                          [str(row.get("variant_id") or "")])
    return added


def _finalize_confirmation_verdict(verdict, members, now):
    """样本未满只 peek。不把 fdr_pass 写成 True，不设 request_early_seal。"""
    if not isinstance(verdict, dict) or verdict.get("run_mode") != "confirmation":
        return None
    row = dict(verdict)
    if row.get("n_confirm_actual") is None:
        row["n_confirm_actual"] = row.get("n") if row.get("n") is not None else 0
    if row.get("n_confirm_required") is None:
        return None
    row["request_early_seal"] = False
    return finalize_confirmation(row, members, now)


# 2026-10-03：confirmation_not_enqueued 的节流状态（prereg_id -> 上次记账时间戳）
_CONFIRMATION_NOTICE: dict[str, float] = {}
_CONFIRMATION_NOTICE_TTL_S = 6 * 3600
# 2026-10-04（E2）：非终态确认结果的重派节流（prereg_id -> 上次派发时间戳）。
# 进程内状态：重启后各放行一次（有界），不落盘。
_CONFIRM_REDISPATCH: dict[str, float] = {}
_CONFIRM_REDISPATCH_TTL_S = 6 * 3600
