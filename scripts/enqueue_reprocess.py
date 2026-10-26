from datetime import datetime
from .scan_proposals import ProposalInfo


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
        "source": batch_id
    }
