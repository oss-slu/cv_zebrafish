"""Test configuration for cv_zebrafish."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    for path in (repo_root, src_root):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


_ensure_src_on_path()
