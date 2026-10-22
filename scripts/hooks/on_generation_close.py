"""B3 Generation Close hook: synthesize research agenda from feedback and write next-gen agenda.

Production trigger: cron every 2 hours (see crontab), or standalone CLI:
    python scripts/hooks/on_generation_close.py
    python scripts/hooks/on_generation_close.py --feedback-path data/cache/bandit_feedback.jsonl
"""
import os
import sys
from pathlib import Path

# Derive task_FM root relative to this script (scripts/hooks/ -> repo root -> task_FM/)
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_TASK_FM_ROOT = _REPO_ROOT / "task_FM"

sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from synthesize_agenda_from_feedback import synthesize_agenda, load_feedback

AGENDAS_DIR = _TASK_FM_ROOT / "agendas"


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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Synthesize next-gen agenda from bandit feedback")
    parser.add_argument("--feedback-path", default="data/cache/bandit_feedback.jsonl",
                        help="Path to bandit feedback JSONL (relative to repo root)")
    args = parser.parse_args()

    feedback_path = _REPO_ROOT / args.feedback_path
    feedback = load_feedback(str(feedback_path))
    if not feedback:
        print(f"No feedback records at {feedback_path}. Nothing to synthesize.")
        sys.exit(0)
    result = on_generation_close(feedback)
    print(f"Agenda synthesized: {result}")
