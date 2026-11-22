"""Trim DeepLabCut CSVs to a frame range, for small committed test fixtures (#157).

Adult zebrafish data comes as a pair of DLC CSVs per video (body_points
``*_1100000.csv`` and caudal_fin ``*_600000.csv``), each ~26 MB. This tool cuts
the same frame range out of every file given, so the trimmed files still line up
frame for frame.

The DLC header rows (scorer / bodyparts / coords, plus ``individuals`` for
multi-animal files) are copied unchanged. Kept frames are renumbered from 0 so
code that assumes frame index == row position keeps working; record the original
range in the fixture README.

Usage:
    python tools/trim_dlc_csv.py BODY.csv CAUDAL.csv --start 10000 --frames 2000 \\
        --out data/samples/csv/adult/
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

SIZE_WARNING_BYTES = 1_000_000


def _is_frame_row(row: Sequence[str]) -> bool:
    return bool(row) and row[0].strip().isdigit()


def read_dlc_csv(path: Path) -> Tuple[List[List[str]], List[List[str]]]:
    """Split a DLC CSV into (header rows, frame rows)."""
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


def trim_dlc_csv(src: Path, dst: Path, start: int, frames: int) -> int:
    """Write frames ``[start, start + frames)`` of ``src`` to ``dst``; return rows written."""
    header, rows = read_dlc_csv(src)
    _check_range(src.name, len(rows), start, frames)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(header)
        for new_index, row in enumerate(rows[start:start + frames]):
            writer.writerow([str(new_index), *row[1:]])
    return frames


def trim_pair(srcs: Sequence[Path], out_dir: Path, start: int, frames: int) -> List[Path]:
    """Trim several DLC CSVs from the same video to the same range.

    Raises ValueError if the files don't have the same number of frames, since
    they would no longer line up after trimming.
    """
    counts = {src: len(read_dlc_csv(src)[1]) for src in srcs}
    if len(set(counts.values())) > 1:
        detail = ", ".join(f"{p.name}: {n}" for p, n in counts.items())
        raise ValueError(f"Files have different frame counts ({detail}); they must come from the same video.")
    outputs = []
    for src in srcs:
        dst = out_dir / src.name
        trim_dlc_csv(src, dst, start, frames)
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
