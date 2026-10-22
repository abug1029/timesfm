#!/usr/bin/env python3
"""B2 offline synthesizer: synthesize research agenda from bandit_feedback.jsonl.

Generation-level Batch Bandit: reuses MultiArmedBandit to update family bucket weights
in batch mode (not online per-item).
Input: data/cache/bandit_feedback.jsonl (symbol, family, reward, enqueued_at)
Output: bucket_weights (family -> mean_reward) + stats summary
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generation_strategy import MultiArmedBandit  # ponytail: reuse existing library code

_DEFAULT_FEEDBACK = "data/cache/bandit_feedback.jsonl"


def load_feedback(feedback_path=_DEFAULT_FEEDBACK):
    """Load bandit feedback records from JSONL file."""
    path = Path(feedback_path)
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def synthesize_agenda(feedback):
    """Generation-level Batch Bandit: aggregate by family, reuse MultiArmedBandit.

    Returns dict with bucket_weights, total_pulls, arm_stats.
    """
    if not feedback:
        return {"bucket_weights": {}, "total_pulls": 0, "arm_stats": {}}

    families = sorted({r.get("family", "unknown") for r in feedback})
    bandit = MultiArmedBandit(arms=families)
    for item in feedback:
        bandit.update(item.get("family", "unknown"), item.get("reward", 0.0))

    # ponytail: get_arm_stats() assumes tuple arms; read bandit.rewards directly
    arm_stats = {}
    bucket_weights = {}
    for fam in families:
        rewards = bandit.rewards.get(fam, [])
        pulls = len(rewards)
        successes = int(sum(rewards)) if pulls else 0
        mean_r = round(successes / pulls, 4) if pulls else 0.0
        arm_stats[fam] = {"pulls": pulls, "successes": successes, "success_rate": mean_r}
        bucket_weights[fam] = mean_r

    return {
        "bucket_weights": bucket_weights,
        "total_pulls": bandit.total_plays,
        "arm_stats": arm_stats,
    }


def main():
    feedback = load_feedback()
    agenda = synthesize_agenda(feedback)
    agenda["synthesized_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(agenda, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
