"""Tests for DLC python path discovery."""

from pathlib import Path

from app_platform.ui_preferences import discover_dlc_python


def test_discover_dlc_python_finds_standard_miniconda_env(monkeypatch, tmp_path: Path):
    env_root = tmp_path / "miniconda3" / "envs" / "cv-zebrafish-pose"
    env_root.mkdir(parents=True)
    py = env_root / "python.exe"
    py.write_text("", encoding="utf-8")

    monkeypatch.setattr("app_platform.ui_preferences.Path.home", lambda: tmp_path)
    assert discover_dlc_python() == str(py)
