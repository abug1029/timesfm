"""C11: get_timesfm_model_path 解析顺序 (不加载 TimesFM)."""
import inspect
import logging
import os
from pathlib import Path

import pytest

from data.config import get_timesfm_model_path

HUB_ID = "google/timesfm-2.5-200m-pytorch"
LOCAL_NAME = "timesfm-2.5-200m-pytorch"
ENV_KEYS = ("FM_TIMESFM_MODEL_PATH", "TIMESFM_MODEL_PATH", "TIMESFM_WEIGHTS_DIR")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setattr("data.config.MODELS_DIR", models)
    monkeypatch.setattr("data.config.FM_ROOT", tmp_path)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path, models


def _abs(p: Path) -> str:
    return os.path.abspath(str(p))


def test_fm_env_wins_over_others(isolated, monkeypatch):
    tmp_path, models = isolated
    fm = tmp_path / "fm_override"
    other = tmp_path / "other"
    weights = tmp_path / "weights"
    local = models / LOCAL_NAME
    for d in (fm, other, weights, local):
        d.mkdir()
        (d / "w").write_text("x")
    monkeypatch.setenv("FM_TIMESFM_MODEL_PATH", str(fm))
    monkeypatch.setenv("TIMESFM_MODEL_PATH", str(other))
    monkeypatch.setenv("TIMESFM_WEIGHTS_DIR", str(weights))
    assert get_timesfm_model_path() == _abs(fm)


def test_timesfm_model_path_when_fm_unset(isolated, monkeypatch):
    tmp_path, models = isolated
    model_path = tmp_path / "model_path"
    weights = tmp_path / "weights"
    local = models / LOCAL_NAME
    for d in (model_path, weights, local):
        d.mkdir()
        (d / "w").write_text("x")
    monkeypatch.setenv("TIMESFM_MODEL_PATH", str(model_path))
    monkeypatch.setenv("TIMESFM_WEIGHTS_DIR", str(weights))
    assert get_timesfm_model_path() == _abs(model_path)


def test_weights_dir_when_set_and_exists(isolated, monkeypatch):
    tmp_path, models = isolated
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "w").write_text("x")
    local = models / LOCAL_NAME
    local.mkdir()
    (local / "w").write_text("x")
    monkeypatch.setenv("TIMESFM_WEIGHTS_DIR", str(weights))
    assert get_timesfm_model_path() == _abs(weights)


def test_weights_dir_skipped_if_missing(isolated, monkeypatch):
    tmp_path, models = isolated
    monkeypatch.setenv("TIMESFM_WEIGHTS_DIR", str(tmp_path / "no_such_weights"))
    local = models / LOCAL_NAME
    local.mkdir()
    (local / "w").write_text("x")
    assert get_timesfm_model_path() == _abs(local)


def test_local_nonempty_dir(isolated):
    tmp_path, models = isolated
    local = models / LOCAL_NAME
    local.mkdir()
    (local / "model.safetensors").write_bytes(b"W")
    assert get_timesfm_model_path() == _abs(local)


def test_empty_local_dir_falls_back_to_hub(isolated):
    tmp_path, models = isolated
    (models / LOCAL_NAME).mkdir()
    assert get_timesfm_model_path() == HUB_ID


def test_missing_local_dir_falls_back_to_hub(isolated):
    assert get_timesfm_model_path() == HUB_ID


def test_blank_env_treated_as_unset(isolated, monkeypatch):
    monkeypatch.setenv("FM_TIMESFM_MODEL_PATH", "  ")
    monkeypatch.setenv("TIMESFM_MODEL_PATH", "")
    assert get_timesfm_model_path() == HUB_ID


def test_symlink_path_warns(isolated, tmp_path, monkeypatch, caplog):
    real = tmp_path / "real_weights"
    real.mkdir()
    (real / "w").write_text("x")
    link = tmp_path / "link_weights"
    link.symlink_to(real)
    monkeypatch.setenv("FM_TIMESFM_MODEL_PATH", str(link))
    with caplog.at_level(logging.WARNING, logger="data.config"):
        got = get_timesfm_model_path()
    assert got == _abs(link)
    text = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "symlink" in text
    assert "copy" in text


def test_dir_with_symlink_children_warns(isolated, tmp_path, monkeypatch, caplog):
    d = tmp_path / "mixed"
    d.mkdir()
    blob = tmp_path / "blob"
    blob.write_bytes(b"W")
    (d / "model.safetensors").symlink_to(blob)
    monkeypatch.setenv("FM_TIMESFM_MODEL_PATH", str(d))
    with caplog.at_level(logging.WARNING, logger="data.config"):
        got = get_timesfm_model_path()
    assert got == _abs(d)
    text = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "symlink" in text
    assert "copy" in text


def test_real_dir_does_not_warn(isolated, tmp_path, monkeypatch, caplog):
    d = tmp_path / "copied"
    d.mkdir()
    (d / "model.safetensors").write_bytes(b"W")
    monkeypatch.setenv("FM_TIMESFM_MODEL_PATH", str(d))
    with caplog.at_level(logging.WARNING, logger="data.config"):
        assert get_timesfm_model_path() == _abs(d)
    text = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "symlink" not in text


def test_hub_fallback_does_not_warn(isolated, caplog):
    with caplog.at_level(logging.WARNING, logger="data.config"):
        assert get_timesfm_model_path() == HUB_ID
    text = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "symlink" not in text


def test_daily_hourly_init_use_resolver_not_hardcoded_hub():
    root = Path(__file__).resolve().parents[1]
    for rel in ("cascade/daily_model.py", "cascade/hourly_model.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "get_timesfm_model_path()" in src, rel
        init = inspect.getblock(src[src.index("def __init__"):].splitlines(True))
        init_src = "".join(init)
        assert "from_pretrained" in init_src
        assert "get_timesfm_model_path()" in init_src
        assert HUB_ID not in init_src
