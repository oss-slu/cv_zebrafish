"""Machine-local session list: JSON paths, display names, and last_opened (not committed to git)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from app_platform.paths import (
    canonical_session_json_path,
    display_stem_for_session_json,
    iter_session_json_files_on_disk,
    migrate_flat_session_json_into_bundle_dirs,
    session_registry_path,
)

_REGISTRY_VERSION = 1


def _safe_resolve(path_str: str) -> str:
    try:
        return str(Path(path_str).expanduser().resolve())
    except OSError:
        return str(Path(path_str).expanduser())


def _read_name_from_session_json(jp: Path) -> str | None:
    if not jp.is_file():
        return None
    try:
        with open(jp, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("name")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _read_or_default() -> dict:
    p = session_registry_path()
    if not p.is_file():
        return {"version": _REGISTRY_VERSION, "entries": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"version": _REGISTRY_VERSION, "entries": []}
    if not isinstance(data, dict):
        return {"version": _REGISTRY_VERSION, "entries": []}
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {"version": _REGISTRY_VERSION, "entries": entries}


def _write_atomic(data: dict) -> None:
    p = session_registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(
        prefix="session_registry.",
        suffix=".tmp",
        dir=str(p.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sync_registry_with_disk() -> list[dict]:
    """Merge registry with on-disk sessions (``<sessions_dir>/<name>/session.json`` and legacy flat ``*.json``).

    Copies legacy flat JSON into a matching folder as ``session.json`` when possible, then remaps
    registry paths from deleted flat files to bundle paths when ``session.json`` exists.

    Missing files remain in the registry so Session Select can show them **greyed out** with a
    stored display name (folder / file stem or last known ``name`` field).
    """
    migrate_flat_session_json_into_bundle_dirs()

    data = _read_or_default()
    entries = data.get("entries", [])
    # key -> {last_opened, name}
    by_path: dict[str, dict[str, float | str | None]] = {}

    def merge_entry(key: str, lo: float, name: str | None) -> None:
        if key not in by_path:
            by_path[key] = {"last_opened": lo, "name": name}
            return
        cur = by_path[key]
        cur["last_opened"] = max(float(cur["last_opened"]), lo)
        if name:
            cur["name"] = name
        elif not cur.get("name"):
            cur["name"] = None

    for e in entries:
        if not isinstance(e, dict):
            continue
        path_s = e.get("path")
        if not path_s or not isinstance(path_s, str):
            continue
        key = _safe_resolve(canonical_session_json_path(path_s))
        try:
            lo = float(e.get("last_opened") or 0)
        except (TypeError, ValueError):
            lo = 0.0
        nm = e.get("name")
        name = str(nm).strip() if isinstance(nm, str) and str(nm).strip() else None
        merge_entry(key, lo, name)

    for jp in iter_session_json_files_on_disk():
        try:
            key = str(jp.resolve())
        except OSError:
            key = str(jp)
        try:
            lo = float(jp.stat().st_mtime)
        except OSError:
            lo = 0.0
        disk_name = _read_name_from_session_json(jp) or display_stem_for_session_json(jp)
        if key not in by_path:
            merge_entry(key, lo, disk_name)
        else:
            merge_entry(key, lo, disk_name)

    merged: list[dict] = []
    for key, meta in by_path.items():
        p = Path(key)
        lo = float(meta["last_opened"])
        stored = meta.get("name")
        stored_s = str(stored).strip() if isinstance(stored, str) and str(stored).strip() else None
        if p.is_file():
            name = _read_name_from_session_json(p) or stored_s or display_stem_for_session_json(p)
        else:
            name = stored_s or display_stem_for_session_json(p)
        merged.append({"path": key, "last_opened": lo, "name": name})

    merged.sort(key=lambda x: x["last_opened"], reverse=True)
    out = {"version": _REGISTRY_VERSION, "entries": merged}
    _write_atomic(out)
    return merged


def touch_last_opened(json_path: str, session_name: str | None = None) -> None:
    key = _safe_resolve(canonical_session_json_path(json_path))
    data = _read_or_default()
    now = time.time()
    entries = [e for e in data.get("entries", []) if isinstance(e, dict)]
    found = False
    for e in entries:
        p = e.get("path")
        if not isinstance(p, str):
            continue
        if _safe_resolve(canonical_session_json_path(p)) == key:
            e["last_opened"] = now
            e["path"] = key
            jp = Path(key)
            disk_nm = _read_name_from_session_json(jp)
            if session_name and str(session_name).strip():
                e["name"] = str(session_name).strip()
            elif disk_nm:
                e["name"] = disk_nm
            elif not (isinstance(e.get("name"), str) and str(e["name"]).strip()):
                e["name"] = display_stem_for_session_json(jp)
            found = True
            break
    if not found:
        jp = Path(key)
        nm = (
            str(session_name).strip()
            if session_name and str(session_name).strip()
            else (_read_name_from_session_json(jp) or display_stem_for_session_json(jp))
        )
        entries.append({"path": key, "last_opened": now, "name": nm})
    data["entries"] = entries
    _write_atomic(data)


def remove_entry(json_path: str) -> None:
    key = _safe_resolve(canonical_session_json_path(json_path))
    data = _read_or_default()
    entries = [
        e
        for e in data.get("entries", [])
        if isinstance(e, dict)
        and isinstance(e.get("path"), str)
        and _safe_resolve(canonical_session_json_path(e["path"])) != key
    ]
    data["entries"] = entries
    _write_atomic(data)


__all__ = [
    "sync_registry_with_disk",
    "touch_last_opened",
    "remove_entry",
]
