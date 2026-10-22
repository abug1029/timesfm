"""Proposal gate plugin — evaluator Step 0 pre-check.

Reuses scripts/proposal_validator.py (R1-R6) and writes validation_signal
to task_FM/validation_signals.jsonl on rejection.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts"))
from proposal_validator import validate_proposal_dict

VALIDATION_SIGNAL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "task_FM", "validation_signals.jsonl"
)


def validate_proposal(proposal: dict) -> dict:
    """Step 0 pre-gate: reuse proposal_validator, reject invalid proposals + persist signal."""
    result = validate_proposal_dict(proposal)
    if not result["valid"]:
        signal = {
            "variant_id": proposal.get("variant_id"),
            "errors": result["errors"],
            "timestamp": datetime.now().isoformat(),
        }
        os.makedirs(os.path.dirname(VALIDATION_SIGNAL_PATH), exist_ok=True)
        with open(VALIDATION_SIGNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(signal, ensure_ascii=False) + "\n")
        return {
            "valid": False,
            "reason": result["errors"][0] if result["errors"] else "unknown",
            "validation_signal": signal,
        }
    return {"valid": True}
