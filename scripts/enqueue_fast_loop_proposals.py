#!/usr/bin/env python3
"""将快环提案加入慢环队列并启动慢环"""
import json
import os
from pathlib import Path
from datetime import datetime

FM_ROOT = Path("/home/abug/timesfm")
QUEUE_PATH = FM_ROOT / "data" / "cache" / "aligned_pending.jsonl"
STATE_PATH = FM_ROOT / "data" / "cache" / "supervisor_state.json"
LATEST_RUN = FM_ROOT / "task_FM" / "experiments" / "run_2026-09-28_15-29-46_primary_task_FM"

def find_proposals():
    """查找所有提案"""
    proposals = []
    results_dir = LATEST_RUN / "results"
    for proposal_file in results_dir.rglob("proposals/*.json"):
        try:
            with open(proposal_file, encoding="utf-8") as f:
                proposal = json.load(f)
            proposals.append(proposal)
        except Exception as e:
            print(f"[WARN] Failed to load {proposal_file}: {e}")
    return proposals

def proposal_to_queue_record(proposal):
    """将提案转换为队列记录"""
    symbol = proposal.get("symbol")
    cov_override = proposal.get("cov_override")
    proposal_id = proposal.get("proposal_id")

    # variant_id 格式: {symbol}_{cov_override}_aligned_p6
    variant_id = f"{symbol}_{cov_override}_aligned_p6"

    return {
        "variant_id": variant_id,
        "symbol": symbol,
        "cov_override": cov_override,
        "max_points": 6,
        "stage": "aligned",
        "checkpoint_path": "",  # 将由慢环填充
        "enqueued_at": datetime.now().isoformat(),
        "src_run": str(LATEST_RUN),
        "proposal_id": proposal_id,
    }

def enqueue_proposals(proposals):
    """将提案加入队列"""
    records = [proposal_to_queue_record(p) for p in proposals]

    # 去重（按 variant_id）
    seen = set()
    unique_records = []
    for r in records:
        if r["variant_id"] not in seen:
            seen.add(r["variant_id"])
            unique_records.append(r)

    # 写入队列
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        for record in unique_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return len(unique_records)

def switch_to_slow_phase():
    """切换 supervisor 到 slow phase"""
    with open(STATE_PATH, encoding="utf-8") as f:
        state = json.load(f)

    state["phase"] = "slow"

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    print(f"[INFO] Switched phase from '{state.get('phase')}' to 'slow'")

def main():
    print("[INFO] Finding proposals from fast loop...")
    proposals = find_proposals()
    print(f"[INFO] Found {len(proposals)} proposals")

    if not proposals:
        print("[ERROR] No proposals found")
        return 1

    print("[INFO] Converting proposals to queue format...")
    count = enqueue_proposals(proposals)
    print(f"[INFO] Enqueued {count} unique proposals to {QUEUE_PATH}")

    print("[INFO] Switching supervisor to slow phase...")
    switch_to_slow_phase()

    print("[INFO] Done! Slow loop will start on next supervisor cycle.")
    print(f"[INFO] Queue: {QUEUE_PATH}")
    print(f"[INFO] To start slow loop immediately, restart supervisor:")
    print(f"  kill $(pgrep -f praxist_supervisor)")
    print(f"  scripts/start_supervisor.sh")

    return 0

if __name__ == "__main__":
    exit(main())
