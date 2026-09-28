#!/usr/bin/env python3
"""T2: 三路消融实跑（spec §8.2 出口核验）

对审计集以 4 种消融模式各跑一遍，产出对照表：
  full vs content      -> 内容效应（打乱时间轴，保留边际分布）
  full vs structural   -> 通道效应（协变量置零但走相同代码路径）
  structural vs baseline -> 代码路径差异（是否仅因分支跳过）

variant_id 必须含模式后缀，否则 checkpoint 按 vid 分文件会跨模式混点。
"""
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

FM_ROOT = Path("/home/abug/timesfm")
sys.path.insert(0, str(FM_ROOT))
sys.path.insert(0, str(FM_ROOT / "scripts"))

QUEUE = FM_ROOT / "data" / "cache" / "aligned_pending.jsonl"
CONFIG = FM_ROOT / "config" / "ablation_audit_config.json"

# T2 前置冒烟：fu 无基线无裁决，先验 checkpoint 可用性由慢环 no_data 墓碑暴露，
# 不单独阻塞（spec §8.2 要求的是"输入确实改变模型"，不是"每品种都有结论"）。
MAX_POINTS = 6  # 与 T1a 新裁决同量级，控制单批耗时

# spec §8.2 原文是「用少量代表性协变量做完整消融」，非全量 5 协变量。
# 全量 = 7 品种 x 5 协变量 x 4 模式 = 140 任务，单批数小时，超出本轮可判定范围。
# 本轮取最小充分规模：2 品种（rb 有基线 / jd 本轮新裁决已跑通）x 2 代表性协变量
# （calendar_cyclical = 唯一 known_ahead；ccl = inventory 族代表）x 4 模式 = 16 任务。
# 判定目标：full/content/structural/baseline 四值是否可区分 —— 即「输入确实改变模型」。
SUBSET_SYMBOLS = ["rb", "jd"]
SUBSET_COVARIATES = ["calendar_cyclical", "ccl"]


def build_batch(config, max_points=MAX_POINTS, symbols=None, covariates=None):
    modes = config["modes"]
    symbols = symbols or SUBSET_SYMBOLS
    covariates = covariates or SUBSET_COVARIATES
    src_run = f"t2_ablation_{datetime.now().strftime('%Y%m%dT%H%M%S')}"

    rows = []
    for sym in symbols:
        for cov in covariates:
            for mode in modes:
                # variant_id 带模式后缀 —— checkpoint 文件按此分，跨模式会混点
                vid = f"{sym}_{cov}_{mode}_aligned_p{max_points}"
                rows.append({
                    "variant_id": vid,
                    "symbol": sym,
                    "cov_override": cov,
                    "ablation_mode": mode,
                    "max_points": max_points,
                    "stage": "aligned",
                    "checkpoint_path": "",
                    "enqueued_at": datetime.now().isoformat(),
                    "src_run": src_run,
                })
    return rows


def main():
    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)

    n_mode = len(config["modes"])
    print(f"完整审计集: {len(config['symbols'])} 品种 x "
          f"{len(config['covariates'])} 协变量 x {n_mode} 模式 "
          f"= {len(config['symbols']) * len(config['covariates']) * n_mode} 任务")
    print(f"本轮子集  : {len(SUBSET_SYMBOLS)} 品种 x {len(SUBSET_COVARIATES)} 协变量 x "
          f"{n_mode} 模式 = {len(SUBSET_SYMBOLS) * len(SUBSET_COVARIATES) * n_mode} 任务")
    print(f"  symbols    = {SUBSET_SYMBOLS}")
    print(f"  covariates = {SUBSET_COVARIATES}")
    print(f"  modes      = {config['modes']}")

    rows = build_batch(config)
    print(f"\n生成 {len(rows)} 条消融任务")
    print(f"batch_id = {uuid.uuid4().hex[:8]}")

    # 追加到队列（不覆盖既有内容）
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"已入队 -> {QUEUE}")
    print(f"队列总条数: {sum(1 for _ in open(QUEUE))}")
    print("\n下一步: 启动慢环")
    print("  .venv/bin/python scripts/aligned_slow_loop.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
