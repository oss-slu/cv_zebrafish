"""Centralized helpers for resolving important repository paths."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _detect_root() -> Path:
    # Repo root from this file: src/app_platform/paths.py → parents[2]
    # (Using cwd breaks icons/paths when the app is started from another directory.)
    return Path(__file__).resolve().parents[2]

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


# Canonical session definition file inside each per-session folder (with graph outputs, etc.).
SESSION_JSON_FILENAME = "session.json"


def session_bundle_dir(session_name: str) -> Path:
    """Per-session directory under ``sessions_dir`` (holds ``session.json`` and graph assets)."""
    return sessions_dir() / session_name


def session_json_path(session_name: str) -> Path:
    """``sessions_dir/<name>/session.json`` (preferred layout)."""
    return session_bundle_dir(session_name) / SESSION_JSON_FILENAME


def display_stem_for_session_json(path: Path) -> str:
    """Label/id for a session file path: bundle folder name, else ``.json`` stem (legacy flat file)."""
    try:
        if path.name.lower() == SESSION_JSON_FILENAME.lower():
            return path.parent.name
    except (OSError, ValueError):
        pass
    return path.stem


def _session_dirs_equal(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return False


def _bundle_folder_for_flat_stem(root: Path, stem: str) -> Path | None:
    """Folder under ``root`` whose name matches ``stem`` case-insensitively (Windows-safe)."""
    key = stem.lower()
    for sub in root.iterdir():
        if sub.is_dir() and sub.name.lower() == key:
            return sub
    return None


def is_session_bundle_json(path: Path) -> bool:
    """True if ``path`` is ``sessions_dir/<id>/session.json``."""
    try:
        if path.name.lower() != SESSION_JSON_FILENAME.lower():
            return False
        return _session_dirs_equal(path.parent.parent, sessions_dir())
    except OSError:
        return False


def iter_session_json_files_on_disk() -> list[Path]:
    """Discover session JSON files: bundle layout first, then legacy flat ``*.json`` (only if no bundle)."""
    root = sessions_dir()
    out: list[Path] = []
    if not root.is_dir():
        return out
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        jp = sub / SESSION_JSON_FILENAME
        if jp.is_file():
            out.append(jp)
    for jp in sorted(root.glob("*.json")):
        if not jp.is_file():
            continue
        if jp.name.lower() == SESSION_JSON_FILENAME.lower():
            continue
        folder = _bundle_folder_for_flat_stem(root, jp.stem)
        if folder is not None and (folder / SESSION_JSON_FILENAME).is_file():
            continue
        out.append(jp)
    return out


def migrate_flat_session_json_into_bundle_dirs() -> None:
    """Copy ``sessions_dir/<name>.json`` → ``sessions_dir/<name>/session.json`` when the folder exists.

    Run while flat files still exist so deleting the external JSON later leaves a working bundle.
    """
    import shutil

    root = sessions_dir()
    if not root.is_dir():
        return
    for jp in list(root.glob("*.json")):
        if not jp.is_file():
            continue
        if jp.name.lower() == SESSION_JSON_FILENAME.lower():
            continue
        folder = _bundle_folder_for_flat_stem(root, jp.stem)
        if folder is None:
            continue
        dest = folder / SESSION_JSON_FILENAME
        if dest.is_file():
            continue
        try:
            shutil.copy2(jp, dest)
        except OSError:
            pass


def relocate_flat_registry_path_to_bundle(missing_path_str: str) -> str | None:
    """If ``missing_path_str`` was a legacy flat ``…/Name.json`` that is gone, return ``…/Name/session.json`` if that file exists."""
    try:
        p = Path(missing_path_str).expanduser()
        p = p.resolve()
    except OSError:
        p = Path(missing_path_str).expanduser()
    if p.is_file():
        return str(p)
    try:
        root = sessions_dir().resolve()
    except OSError:
        root = sessions_dir()
    try:
        parent = p.parent.resolve()
    except OSError:
        parent = p.parent
    if not _session_dirs_equal(parent, root):
        return None
    if p.suffix.lower() != ".json":
        return None
    if p.name.lower() == SESSION_JSON_FILENAME.lower():
        return None
    folder = _bundle_folder_for_flat_stem(root, p.stem)
    if folder is None:
        return None
    bundle_jp = folder / SESSION_JSON_FILENAME
    if not bundle_jp.is_file():
        return None
    try:
        return str(bundle_jp.resolve())
    except OSError:
        return str(bundle_jp)


def canonical_session_json_path(path_str: str) -> str:
    """Single on-disk path for a session: prefer bundle ``…/<name>/session.json`` over legacy flat ``…/<name>.json``."""
    try:
        p = Path(path_str).expanduser().resolve()
    except OSError:
        p = Path(path_str).expanduser()
    if p.is_file():
        try:
            root = sessions_dir().resolve()
        except OSError:
            root = sessions_dir()
        if (
            _session_dirs_equal(p.parent, root)
            and p.suffix.lower() == ".json"
            and p.name.lower() != SESSION_JSON_FILENAME.lower()
        ):
            folder = _bundle_folder_for_flat_stem(root, p.stem)
            if folder is not None:
                bj = folder / SESSION_JSON_FILENAME
                if bj.is_file():
                    try:
                        return str(bj.resolve())
                    except OSError:
                        return str(bj)
        return str(p)
    relocated = relocate_flat_registry_path_to_bundle(path_str)
    if relocated:
        try:
            return str(Path(relocated).expanduser().resolve())
        except OSError:
            return relocated
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


def local_data_dir() -> Path:
    """Gitignored machine-local data (session registry path list + last opened)."""
    return project_root() / "data" / "local"


def session_registry_path() -> Path:
    return local_data_dir() / "session_registry.json"


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
    "SESSION_JSON_FILENAME",
    "session_bundle_dir",
    "session_json_path",
    "display_stem_for_session_json",
    "is_session_bundle_json",
    "iter_session_json_files_on_disk",
    "migrate_flat_session_json_into_bundle_dirs",
    "relocate_flat_registry_path_to_bundle",
    "canonical_session_json_path",
    "local_data_dir",
    "session_registry_path",
]
