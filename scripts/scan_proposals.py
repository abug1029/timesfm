import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ProposalInfo:
    symbol: str
    cov_override: str
    variant_id: str
    file_path: Path
    mtime: datetime
    src_run: str


def scan_proposals(paths: list[Path]) -> list[ProposalInfo]:
    proposals = []
    for path in paths:
        try:
            data = json.loads(path.read_text())
            symbol = data.get("symbol")
            cov_override = data.get("cov_override")
            if not symbol or not cov_override:
                print(f"Warning: skipping {path}: missing symbol or cov_override")
                continue
            
            src_run = _extract_src_run(path)
            
            proposals.append(ProposalInfo(
                symbol=symbol,
                cov_override=cov_override,
                variant_id=f"{symbol}_{cov_override}",
                file_path=path,
                mtime=datetime.fromtimestamp(path.stat().st_mtime),
                src_run=src_run
            ))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: skipping {path}: {e}")
            continue
    
    return proposals


def _extract_src_run(path: Path) -> str:
    for part in path.parts:
        if part.startswith("run_"):
            return part
    return "unknown"
