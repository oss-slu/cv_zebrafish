"""Helpers for loading calculation configuration files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Union

from cvzebrafish.platform.paths import (
    configs_dir,
    default_last_config,
    default_sample_config,
    sample_json_dir,
)

PathLike = Union[str, Path]

BASE_CONFIG = default_sample_config()
LAST_CONFIG = default_last_config()


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _search_paths(candidate: Path) -> Iterable[Path]:
    if candidate.is_absolute():
        yield candidate
        return
    yield Path.cwd() / candidate
    yield configs_dir() / candidate
    yield sample_json_dir() / candidate


def _resolve_candidate(src: PathLike | None) -> Path:
    if src is None:
        return LAST_CONFIG
    candidate = Path(src)
    for option in _search_paths(candidate):
        if option.exists():
            return option
    return candidate if candidate.is_absolute() else configs_dir() / candidate


def loadConfig(src: PathLike | None = None) -> dict:
    """
    Load a configuration file, falling back to BaseConfig.json when missing.

    If the requested file does not exist, the base config is returned and,
    when possible, written to the resolved target for convenience.
    """

    target_path = _resolve_candidate(src)
    if target_path.exists():
        return _load_json(target_path)

    print("No config file found, loading base config")
    config = _load_json(BASE_CONFIG)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=4)
    except OSError:
        # If we cannot write the fallback, silently continue with in-memory config.
        pass
    return config
