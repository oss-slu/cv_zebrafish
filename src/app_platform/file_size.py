"""Human-readable file and directory sizes for project storage UI."""

from __future__ import annotations

from pathlib import Path

ARTIFACT_SIZE_COLUMN_BYTES = 1_048_576  # 1 MB — show size column at/above this


def path_size_bytes(path: Path) -> int:
    """Total bytes for a file or directory tree (0 if missing)."""
    path = Path(path)
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def format_byte_size(num_bytes: int) -> str:
    """Compact size label (B, KB, MB, GB)."""
    n = max(0, int(num_bytes))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"
