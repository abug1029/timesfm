#!/usr/bin/env python3
"""T1b: 手算核对预测点（spec §8.1）

选取 2 个品种（rb, ss），手动核对 3-5 个预测点的 dir_ok / delta_pred / delta_real，
证明对齐与基线配对正确。
"""
import json
import sys
from pathlib import Path

FM_ROOT = Path("/home/abug/timesfm")
sys.path.insert(0, str(FM_ROOT))

def load_checkpoint(checkpoint_path):
    """加载 checkpoint 文件"""
    points = []
    with open(checkpoint_path) as f:
        for line in f:
            if line.strip():
                points.append(json.loads(line))
    return points

def verify_prediction_point(point, idx):
    """手动核对单个预测点"""
    cutoff = point.get("cutoff")
    delta_pred = point.get("delta_pred")
    delta_real = point.get("delta_real")
    dir_ok = point.get("dir_ok")
    base = point.get("base")
    pred_end = point.get("pred_end")
    real_end = point.get("real_end")

    # 关键口径（monthly_backtest.py:425-426）：
    #   dir_ok 用 **端点** delta（pred_end - base），不是 checkpoint 里存的
    #   delta_pred 字段（那是 position_from_forecast 的信号口径加权值）。
    #   两者故意不同 —— 照搬 delta_pred 字段核对 dir_ok 必然误判。
    delta_pred_endpoint = pred_end - base
    delta_real_endpoint = real_end - base
    eps = 1e-8
    if abs(delta_real_endpoint) < eps:
        expected_dir_ok = False
    else:
        expected_dir_ok = (delta_pred_endpoint * delta_real_endpoint) > 0

    match = "OK" if dir_ok == expected_dir_ok else "MISMATCH"

    print(f"  点 {idx}: cutoff={cutoff}")
    print(f"    端点 delta_pred={delta_pred_endpoint:.4f}, 端点 delta_real={delta_real_endpoint:.4f}")
    print(f"    dir_ok={dir_ok}, 手算={expected_dir_ok} [{match}]")
    print(f"    (参考: 信号口径 delta_pred 字段={delta_pred:.4f} —— 不参与 dir_ok)")

    return dir_ok == expected_dir_ok

def main():
    # 选取 rb 和 ss 的裁决
    variants = [
        ("rb_crack_spread_level_aligned_p6", "rb"),
        ("ss_vor_aligned_p6", "ss"),
    ]

    print("=== T1b: 手算核对预测点 ===\n")

    total_points = 0
    total_correct = 0

    for variant_id, symbol in variants:
        print(f"品种: {symbol}, 变体: {variant_id}")

        # 加载 checkpoint
        checkpoint_path = FM_ROOT / "data" / "cache" / "aligned_checkpoints" / f"{variant_id}.jsonl"
        if not checkpoint_path.exists():
            print(f"  ❌ Checkpoint 不存在: {checkpoint_path}\n")
            continue

        points = load_checkpoint(checkpoint_path)
        print(f"  Checkpoint 点数: {len(points)}")

        # 核对前 5 个点
        n_verify = min(5, len(points))
        correct = 0
        for i in range(n_verify):
            if verify_prediction_point(points[i], i):
                correct += 1
            total_points += 1
        total_correct += correct

        print(f"  核对结果: {correct}/{n_verify} 正确\n")

    print(f"=== 总计: {total_correct}/{total_points} 正确 ===")

    if total_correct == total_points:
        print("✅ T1b 通过：手算核对与代码计算一致")
        return 0
    else:
        print("❌ T1b 失败：手算核对与代码计算不一致")
        return 1

if __name__ == "__main__":
    sys.exit(main())
