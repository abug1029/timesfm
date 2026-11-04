"""基线文件路径的唯一规范（E7）。

供 generate_baseline_points.py 与 evaluator.load_baseline_points 共同导入，
避免两份实现漂移导致文件名约定分叉。
"""


def baseline_filename(symbol: str, cov=None) -> str:
    """基线文件名。cov=None 或 "none" 表示无协变量基线（E7）。"""
    sym = symbol.lower()
    if cov is None or cov == "none":
        return f"baseline_points_{sym}_nocov.jsonl"
    return f"baseline_points_{sym}.jsonl"


import datetime as _dt


def baseline_jsonl_record(point, protocol_fingerprint) -> dict:
    """Project a point dict onto the baseline JSONL schema.

    Required keys: cutoff, dir_ok, delta_pred, delta_real.
    Optional keys: endpoint_delta, position_sign (written only when present
    and not None).
    cutoff must parse as "%Y-%m-%d %H:%M:%S"; ValueError otherwise.
    """
    cutoff = point["cutoff"]
    _dt.datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    rec = {
        "cutoff": cutoff,
        "dir_ok": bool(point["dir_ok"]),
        "delta_pred": float(point["delta_pred"]),
        "delta_real": float(point["delta_real"]),
        "protocol_fingerprint": protocol_fingerprint,
    }
    if "endpoint_delta" in point and point["endpoint_delta"] is not None:
        rec["endpoint_delta"] = float(point["endpoint_delta"])
    if "position_sign" in point and point["position_sign"] is not None:
        rec["position_sign"] = float(point["position_sign"])
    return rec
