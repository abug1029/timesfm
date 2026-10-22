"""Tests for B3 generation close hook."""
import sys
import os
import shutil
from pathlib import Path

sys.path.insert(0, "/home/abug/timesfm/scripts/hooks")
sys.path.insert(0, "/home/abug/timesfm/scripts")
from on_generation_close import on_generation_close, render_peer_prompt, AGENDAS_DIR


def test_on_generation_close_synthesizes_agenda(tmp_path):
    """on_generation_close should produce agenda file and return path."""
    # Override AGENDAS_DIR for test isolation
    import on_generation_close as mod
    original_dir = mod.AGENDAS_DIR
    mod.AGENDAS_DIR = tmp_path / "agendas"
    try:
        feedback = [{"family": "momentum", "reward": 0.8}, {"family": "volatility", "reward": 0.3}]
        result = on_generation_close(feedback)
        assert "agenda_path" in result
        assert Path(result["agenda_path"]).exists()
        assert result["gen"] == 1
    finally:
        mod.AGENDAS_DIR = original_dir


def test_peer_prompt_renders_new_quota():
    """render_peer_prompt should format bucket weights as percentages."""
    agenda = {"bucket_weights": {"momentum": 0.7, "volatility": 0.3}}
    prompt = render_peer_prompt(agenda)
    assert "momentum" in prompt
    assert "volatility" in prompt
    assert "70%" in prompt
    assert "30%" in prompt


def test_peer_prompt_empty_weights():
    """render_peer_prompt should handle empty weights gracefully."""
    agenda = {"bucket_weights": {}}
    prompt = render_peer_prompt(agenda)
    assert "No bucket weights" in prompt


def test_get_next_gen_increments(tmp_path):
    """_get_next_gen should increment based on existing agenda files."""
    import on_generation_close as mod
    original_dir = mod.AGENDAS_DIR
    mod.AGENDAS_DIR = tmp_path / "agendas"
    try:
        mod.AGENDAS_DIR.mkdir(parents=True)
        # Create gen1 and gen2 files
        (mod.AGENDAS_DIR / "research_agenda_gen1.yaml").touch()
        (mod.AGENDAS_DIR / "research_agenda_gen2.yaml").touch()
        gen_num = mod._get_next_gen()
        assert gen_num == 3
    finally:
        mod.AGENDAS_DIR = original_dir
