"""Trim DeepLabCut CSVs to a frame range, for small committed test fixtures (#157).

Adult zebrafish data comes as a pair of DLC CSVs per video (body_points
``*_1100000.csv`` and caudal_fin ``*_600000.csv``), each ~26 MB. This tool cuts
the same frame range out of every file given, so the trimmed files still line up
frame for frame.

The DLC header rows (scorer / bodyparts / coords, plus ``individuals`` for
multi-animal files) are copied unchanged. Input and output paths must be inside
the repository; copy the lab files in first (e.g. ``data/raw/``; ``*.csv`` is
git-ignored except for committed fixtures). Kept frames are renumbered from 0 so
code that assumes frame index == row position keeps working; record the original
range in the fixture README.

Usage:
    python tools/trim_dlc_csv.py data/raw/BODY.csv data/raw/CAUDAL.csv --start 10000 --frames 2000 \\
        --out data/samples/csv/adult/
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

SIZE_WARNING_BYTES = 1_000_000
REPO_ROOT = Path(__file__).resolve().parents[1]


def _inside(path: Path, root: Path) -> Path:
    """Resolve ``path`` and refuse it unless it is inside ``root``.

    Inputs and outputs are limited to the repository: copy the lab files into
    the repo first (``*.csv`` is git-ignored, so they won't be committed).
    """
    resolved = Path(path).resolve()
    root = Path(root).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{path} is outside {root}; copy the file into the repository first.")
    return resolved


def _is_frame_row(row: Sequence[str]) -> bool:
    return bool(row) and row[0].strip().isdigit()


def read_dlc_csv(path: Path, root: Path = REPO_ROOT) -> Tuple[List[List[str]], List[List[str]]]:
    """Split a DLC CSV into (header rows, frame rows)."""
    path = _inside(path, root)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header: List[List[str]] = []
    for row in rows:
        if _is_frame_row(row):
            break
        header.append(row)
    frames = rows[len(header):]
    if not header or not header[0] or header[0][0] != "scorer":
        raise ValueError(f"{path.name}: not a DeepLabCut CSV (first cell should be 'scorer').")
    if not frames:
        raise ValueError(f"{path.name}: no frame rows found.")
    return header, frames


def trim_dlc_csv(src: Path, dst: Path, start: int, frames: int, root: Path = REPO_ROOT) -> int:
    """Write frames ``[start, start + frames)`` of ``src`` to ``dst``; return rows written."""
    header, rows = read_dlc_csv(src, root)
    _check_range(src.name, len(rows), start, frames)
    dst = _inside(dst, root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(header)
        for new_index, row in enumerate(rows[start:start + frames]):
            writer.writerow([str(new_index), *row[1:]])
    return frames


def trim_pair(srcs: Sequence[Path], out_dir: Path, start: int, frames: int, root: Path = REPO_ROOT) -> List[Path]:
    """Trim several DLC CSVs from the same video to the same range.

    Raises ValueError if the files don't have the same number of frames, since
    they would no longer line up after trimming, or if two files share a name,
    since outputs keep the input names and one would overwrite the other.
    """
    names = [Path(src).name for src in srcs]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"Input files share a name ({', '.join(duplicates)}); outputs would overwrite each other.")
    counts = {src: len(read_dlc_csv(src, root)[1]) for src in srcs}
    if len(set(counts.values())) > 1:
        detail = ", ".join(f"{p.name}: {n}" for p, n in counts.items())
        raise ValueError(f"Files have different frame counts ({detail}); they must come from the same video.")
    outputs = []
    for src in srcs:
        dst = out_dir / src.name
        trim_dlc_csv(src, dst, start, frames, root)
        outputs.append(dst)
    return outputs


def _check_range(name: str, total: int, start: int, frames: int) -> None:
    if start < 0 or frames <= 0:
        raise ValueError("start must be >= 0 and frames must be > 0.")
    if start + frames > total:
        raise ValueError(f"{name}: range {start}..{start + frames - 1} is past the last frame ({total - 1}).")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csvs", nargs="+", type=Path, help="DLC CSV files from the same video")
    parser.add_argument("--start", type=int, required=True, help="first frame to keep (0-based)")
    parser.add_argument("--frames", type=int, required=True, help="number of frames to keep")
    parser.add_argument("--out", type=Path, required=True, help="output folder (file names are kept)")
    args = parser.parse_args(argv)

    try:
        outputs = trim_pair(args.csvs, args.out, args.start, args.frames)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in outputs:
        size = path.stat().st_size
        note = "  (over ~1 MB; consider fewer frames)" if size > SIZE_WARNING_BYTES else ""
        print(f"wrote {path} ({size / 1_000_000:.2f} MB){note}")
    print(f"frames {args.start}..{args.start + args.frames - 1} of the originals, renumbered from 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
