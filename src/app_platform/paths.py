"""Centralized helpers for resolving important repository paths."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def _detect_root() -> Path:
    return Path.cwd()

@lru_cache(maxsize=1)
def project_root() -> Path:
    """Return the repository root (contains src/, configs/, assets/, etc.)."""
    return _detect_root()


@lru_cache(maxsize=1)
def src_root() -> Path:
    """Return the src directory so scripts can extend sys.path if needed."""
    return project_root() / "src"


def assets_dir() -> Path:
    return project_root() / "assets"


def images_dir() -> Path:
    return assets_dir() / "images"


def configs_dir() -> Path:
    return project_root() / "configs"


def sessions_dir() -> Path:
    return project_root() / "data" / "sessions"


def sample_csv_dir() -> Path:
    return project_root() / "data" / "samples" / "csv"


def sample_json_dir() -> Path:
    return project_root() / "data" / "samples" / "jsons"


def default_sample_csv() -> Path:
    return sample_csv_dir() / "correct_format.csv"


def default_sample_config() -> Path:
    return sample_json_dir() / "BaseConfig.json"


def default_last_config() -> Path:
    return configs_dir() / "LastConfig.json"


__all__ = [
    "project_root",
    "src_root",
    "assets_dir",
    "images_dir",
    "configs_dir",
    "sample_csv_dir",
    "sample_json_dir",
    "default_sample_csv",
    "default_sample_config",
    "default_last_config",
    "sessions_dir",
]
