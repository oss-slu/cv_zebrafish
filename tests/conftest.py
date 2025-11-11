"""Test configuration for cv_zebrafish."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


_ensure_src_on_path()
