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
