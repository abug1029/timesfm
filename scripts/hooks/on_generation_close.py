"""B3 Generation Close hook: synthesize research agenda from feedback and write next-gen agenda."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from synthesize_agenda_from_feedback import synthesize_agenda

AGENDAS_DIR = Path("/home/abug/timesfm/task_FM/agendas")


def on_generation_close(feedback: list) -> dict:
    """Called when a generation closes. Synthesizes agenda for next generation."""
    agenda = synthesize_agenda(feedback)
    gen_num = _get_next_gen()
    AGENDAS_DIR.mkdir(parents=True, exist_ok=True)
    agenda_path = AGENDAS_DIR / f"research_agenda_gen{gen_num}.yaml"
    _write_yaml(agenda_path, agenda)
    return {"agenda_path": str(agenda_path), "gen": gen_num}


def _get_next_gen() -> int:
    if not AGENDAS_DIR.exists():
        return 1
    existing = [f for f in AGENDAS_DIR.iterdir() if f.name.startswith("research_agenda_gen")]
    return len(existing) + 1


def _write_yaml(path: Path, data: dict):
    """Write agenda as YAML (simple key-value, no PyYAML dependency)."""
    with open(path, "w") as f:
        for key, val in data.items():
            if isinstance(val, dict):
                f.write(f"{key}:\n")
                for k, v in val.items():
                    f.write(f"  {k}: {v}\n")
            else:
                f.write(f"{key}: {val}\n")


def render_peer_prompt(agenda: dict) -> str:
    """Render peer prompt from agenda bucket weights."""
    weights = agenda.get("bucket_weights", {})
    if not weights:
        return "No bucket weights available."
    total = sum(weights.values()) or 1
    parts = [f"{k}: {v / total * 100:.0f}%" for k, v in sorted(weights.items())]
    return f"Generation quota: {', '.join(parts)}"
