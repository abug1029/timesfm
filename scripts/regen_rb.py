#!/usr/bin/env python3
"""重生 rb 的 nocov 基线（其指纹停留在 protocol_v1）。

根因: ensure_baselines 仅按 n_lines<100 判断是否需要重生，
rb 已有 588 行 -> 被跳过 -> 保留 PR-A1 之前的指纹。
"""
import sys
import os

REPO = "/home/abug/timesfm"
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, REPO)
os.chdir(REPO)

import generate_baseline_points as gbp  # noqa: E402

print("=== 重生 rb nocov 基线 ===", flush=True)
gbp.generate("rb", None, REPO)
print("=== 完成 ===", flush=True)

# 校验指纹
import json  # noqa: E402
p = os.path.join(REPO, "task_FM/config/baseline_points_rb_nocov.jsonl")
with open(p) as f:
    d = json.loads(f.readline())
print("新 protocol_fingerprint =", (d.get("protocol_fingerprint") or "None")[:16], flush=True)
