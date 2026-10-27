import json
from datetime import datetime
from pathlib import Path

from .scan_proposals import ProposalInfo, scan_proposals, deduplicate_proposals
from .filter_verdicts import filter_existing_verdicts


def construct_queue_row(proposal: ProposalInfo, batch_id: str) -> dict:
    return {
        "variant_id": proposal.variant_id,
        "symbol": proposal.symbol,
        "cov_override": proposal.cov_override,
        "max_points": 600,
        "stage": "aligned",
        "checkpoint_path": "",
        "enqueued_at": datetime.utcnow().isoformat() + "Z",
        "src_run": proposal.src_run,
        "source": batch_id,
    }


def load_supported_covariates():
    """Load valid covariate names and family names from covariate_pool.json.

    Schema:
    - families: list[str] (family names — must NOT be used as cov_override)
    - covariates: dict[str, dict] where key is covariate name,
      value has 'status' field; only status=='active' are valid.
    """
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path) as f:
        pool = json.load(f)

    supported = {
        name for name, data in pool.get("covariates", {}).items()
        if data.get("status") == "active"
    }
    supported.update({"slope_only", "none", "baseline"})

    family_names = set(pool.get("families", []))
    return supported, family_names


def main(
    experiments_dir: Path,
    verdict_path: Path,
    queue_path: Path,
    batch_id: str,
) -> dict:
    """Scan, dedup, filter, validate covariates, construct queue rows, and append to queue file."""
    # 1. Scan all proposal files (exclude prescreen)
    proposal_files = [
        f for f in experiments_dir.rglob("*/proposals/*.json")
        if not f.name.endswith(".prescreen.json")
    ]

    all_proposals = scan_proposals(proposal_files)
    total_files = len(proposal_files)

    # 2. Deduplicate by variant_id
    unique_proposals = deduplicate_proposals(all_proposals)

    # 3. Filter out proposals with existing verdicts
    filtered = filter_existing_verdicts(unique_proposals, verdict_path)
    already_verdict = len(unique_proposals) - len(filtered)

    # 4. Validate covariates — reject family names and unregistered covariates
    supported_covs, family_names = load_supported_covariates()
    valid_proposals = []
    invalid_count = 0
    for proposal in filtered:
        if proposal.cov_override in family_names:
            invalid_count += 1
            print(f"Warning: skipping {proposal.variant_id} - "
                  f"cov_override='{proposal.cov_override}' is a family name, not a covariate")
        elif proposal.cov_override not in supported_covs:
            invalid_count += 1
            print(f"Warning: skipping {proposal.variant_id} - "
                  f"cov_override='{proposal.cov_override}' not in registry")
        else:
            valid_proposals.append(proposal)

    # 5. Construct rows and append to queue file
    enqueued = 0
    failed = 0
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "a") as f:
        for proposal in valid_proposals:
            try:
                row = construct_queue_row(proposal, batch_id)
                f.write(json.dumps(row) + "\n")
                enqueued += 1
            except Exception as e:
                print(f"Warning: failed to enqueue {proposal.variant_id}: {e}")
                failed += 1

    return {
        "total_files": total_files,
        "unique_proposals": len(unique_proposals),
        "already_verdict": already_verdict,
        "invalid_covariate": invalid_count,
        "to_enqueue": len(valid_proposals),
        "enqueued": enqueued,
        "failed": failed,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enqueue proposals for reprocessing")
    parser.add_argument("--experiments-dir", type=Path, default=Path("task_FM/experiments"))
    parser.add_argument("--verdict-path", type=Path, default=Path("task_FM/config/aligned_verdicts.jsonl"))
    parser.add_argument("--queue-path", type=Path, default=Path("data/cache/aligned_pending.jsonl"))
    parser.add_argument("--batch-id", type=str, default="reprocess_20261026")

    args = parser.parse_args()
    stats = main(args.experiments_dir, args.verdict_path, args.queue_path, args.batch_id)
    print(json.dumps(stats, indent=2))
