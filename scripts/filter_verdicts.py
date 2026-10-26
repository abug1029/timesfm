import json
from pathlib import Path
from scripts.scan_proposals import ProposalInfo


def filter_existing_verdicts(
    proposals: list[ProposalInfo],
    verdict_path: Path,
) -> list[ProposalInfo]:
    """Filter out proposals that already have a verdict."""
    existing = set()
    if verdict_path.exists():
        with open(verdict_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing.add(json.loads(line)["variant_id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return [p for p in proposals if p.variant_id not in existing]
