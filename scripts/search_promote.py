"""晋升判定（spec 2026-10-05 §6.6）。

纯函数：不写 preregistry，不写 commitments。监督环在停止巡检之后调用。
n_confirm_required 继承该品种已有锁定值，不按新的 var_lr 重算预算。
var_lr 取裁决上冻结的 search_var_lr（节点 d_t 的 compute_hac_se）。
"""
import json
import os

from cascade.statistical_tests import n_required


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def symbol_lock(prereg_rows, symbol):
    """该品种最早一条带锁定样本量的预注册。没有则不能晋升。"""
    wanted = str(symbol or "").lower()
    rows = []
    for row in prereg_rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").lower() != wanted:
            continue
        sample = row.get("n_confirm_required")
        if isinstance(sample, bool) or not isinstance(sample, int):
            continue
        rows.append(row)
    if not rows:
        return None
    rows.sort(key=lambda row: str(row.get("registered_at") or ""))
    return rows[0]


def _later_confirm_from(prereg_rows, symbol, eval_end_ts):
    wanted = str(symbol or "").lower()
    candidates = [eval_end_ts]
    for row in prereg_rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").lower() != wanted:
            continue
        stamp = row.get("confirm_from_ts")
        if isinstance(stamp, str) and stamp:
            candidates.append(stamp)
    return max(candidates)


def _best_node(tree, snapshot):
    best_vid = None
    best_row = None
    best_dp = None
    for vid in tree.member_vids:
        row = snapshot.get(vid) if isinstance(snapshot, dict) else None
        if not isinstance(row, dict) or row.get("status", "ok") != "ok":
            continue
        delta_post = _finite(row.get("delta_post_shrunk"))
        if delta_post is None:
            continue
        if (best_row is None or delta_post > best_dp
                or (delta_post == best_dp and vid < best_vid)):
            best_vid = vid
            best_row = row
            best_dp = delta_post
    return best_vid, best_row, best_dp


def _proposal_id_for(tree, variant_id):
    for proposal_id, member in tree.member_pid_vid.items():
        if member == variant_id:
            return proposal_id
    return ""


def evaluate_tree_promotion(tree, snapshot, prereg_rows):
    """六条件都成立才返回晋升决定，否则 None。不写文件。"""
    variant_id, row, delta_post = _best_node(tree, snapshot)
    if row is None or delta_post is None or delta_post <= 0:
        return None
    if row.get("gate_pass") is not True:
        return None
    if row.get("incremental_vs_incumbent") not in ("pass", "not_applicable"):
        return None
    eval_end = row.get("eval_end_ts")
    if not isinstance(eval_end, str) or not eval_end.strip():
        return None
    symbol = str(row.get("symbol") or tree.symbol or "").lower()
    lock = symbol_lock(prereg_rows, symbol)
    if lock is None:
        return None
    var_lr = _finite(row.get("search_var_lr"))
    if var_lr is None or var_lr <= 0:
        return None
    required = n_required(
        var_d=var_lr, vif=1.0, z_alpha=1.645, z_beta=0.842, delta=delta_post)
    locked_n = int(lock["n_confirm_required"])
    if int(required) > locked_n:
        return None
    return {
        "tree_id": tree.tree_id,
        "variant_id": variant_id,
        "symbol": symbol,
        "family": tree.family,
        "proposal_id": _proposal_id_for(tree, variant_id),
        "delta_post": delta_post,
        "n_required": int(required),
        "n_confirm_required": locked_n,
        "confirm_from_ts": _later_confirm_from(
            prereg_rows, symbol, eval_end.strip()),
        "var_lr": var_lr,
        "cov_override": str(row.get("cov_override") or ""),
        "lock": lock,
        "cov_fingerprint": row.get("cov_fingerprint"),
    }


def read_proposal_copy(root, proposal_id):
    """从提案文件抄 mechanism 与 predicted_direction。读不到则两空。"""
    if not proposal_id:
        return "", ""
    path = (proposal_id if os.path.isabs(proposal_id)
            else os.path.join(root or "", proposal_id))
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    return (str(payload.get("mechanism") or "").strip(),
            str(payload.get("predicted_direction") or "").strip())


def build_promotion_prereg(decision, *, mechanism, predicted_direction,
                           registered_at, prereg_id):
    """追加行。样本量继承锁定值；协变量键锁定为 daily_slope + 本节点。"""
    lock = decision["lock"]
    cov = decision["cov_override"]
    keys = ["daily_slope", cov]
    verdict_fp = decision.get("cov_fingerprint")
    if isinstance(verdict_fp, dict) and list(verdict_fp.get("keys") or []) == keys:
        cov_fp = dict(verdict_fp)
    else:
        # 键不一致时不抄 matrix_sha256：那是另一组键的哈希。
        cov_fp = {"keys": list(keys), "n_channels": 2,
                  "hash_version": "cov_matrix_hash_v1"}
    return {
        "prereg_id": prereg_id,
        "symbol": decision["symbol"],
        "cov_fingerprint": cov_fp,
        "model_fingerprint": lock.get("model_fingerprint"),
        "predict_params": lock.get("predict_params"),
        "horizon": lock.get("horizon"),
        "metric_version": lock.get("metric_version") or "v1",
        "n_confirm_required": decision["n_confirm_required"],
        "registered_at": registered_at,
        "confirm_from_ts": decision["confirm_from_ts"],
        "delta_star": 0.08,
        "power": 0.8,
        "alpha": 0.05,
        "var_lr": decision["var_lr"],
        "kill_condition": lock.get("kill_condition"),
        "promote_condition": lock.get("promote_condition"),
        "mechanism": mechanism,
        "predicted_direction": predicted_direction,
        "n_planned": decision["n_confirm_required"],
        "jev": None,
        "terminal_state": None,
    }
