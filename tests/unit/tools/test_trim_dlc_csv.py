"""Tests for tools/trim_dlc_csv.py, the adult fixture trimmer (#157)."""

import csv
import shutil
from pathlib import Path

import pytest

from src.core.validation.csv_verifier import verify_deeplabcut_csv
from tools.trim_dlc_csv import main, read_dlc_csv, trim_dlc_csv, trim_pair

REPO_ROOT = Path(__file__).resolve().parents[3]
LARVAL_SAMPLE = REPO_ROOT / "data" / "samples" / "csv" / "correct_format.csv"


def write_dlc(path: Path, bodyparts, n_frames: int, individuals: bool = False) -> Path:
    """Write a small DLC-style CSV where x == frame index, for easy checking."""
    header = [["scorer"] + ["DLC_test"] * (3 * len(bodyparts))]
    if individuals:
        header.append(["individuals"] + ["fish1"] * (3 * len(bodyparts)))
    header.append(["bodyparts"] + [bp for bp in bodyparts for _ in range(3)])
    header.append(["coords"] + ["x", "y", "likelihood"] * len(bodyparts))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(header)
        for i in range(n_frames):
            writer.writerow([i] + [i, 2 * i, 0.9] * len(bodyparts))
    return path


def test_trim_keeps_header_and_requested_frames(tmp_path):
    src = write_dlc(tmp_path / "body.csv", [f"p{i}" for i in range(10)], n_frames=50)
    dst = tmp_path / "out" / "body.csv"

    trim_dlc_csv(src, dst, start=10, frames=5, root=tmp_path)

    src_header, _ = read_dlc_csv(src, tmp_path)
    header, rows = read_dlc_csv(dst, tmp_path)
    assert header == src_header
    assert len(rows) == 5
    assert [r[0] for r in rows] == ["0", "1", "2", "3", "4"]  # renumbered
    assert [r[1] for r in rows] == ["10", "11", "12", "13", "14"]  # data from frames 10..14


def test_trim_preserves_multi_animal_individuals_row(tmp_path):
    src = write_dlc(tmp_path / "ma.csv", ["p0", "p1"], n_frames=10, individuals=True)
    dst = tmp_path / "out.csv"

    trim_dlc_csv(src, dst, start=0, frames=3, root=tmp_path)

    header, rows = read_dlc_csv(dst, tmp_path)
    assert [row[0] for row in header] == ["scorer", "individuals", "bodyparts", "coords"]
    assert len(rows) == 3


def test_pair_trims_both_files_to_same_range(tmp_path):
    body = write_dlc(tmp_path / "M26R_1100000.csv", [f"p{i}" for i in range(10)], n_frames=40)
    fin = write_dlc(tmp_path / "M26R_600000.csv", ["caudal_fin"], n_frames=40)

    outputs = trim_pair([body, fin], tmp_path / "adult", start=5, frames=20, root=tmp_path)

    assert [p.name for p in outputs] == ["M26R_1100000.csv", "M26R_600000.csv"]
    trimmed = [read_dlc_csv(p, tmp_path)[1] for p in outputs]
    assert len(trimmed[0]) == len(trimmed[1]) == 20
    assert trimmed[0][0][1] == trimmed[1][0][1] == "5"  # same source frame in both


def test_pair_with_different_frame_counts_raises(tmp_path):
    body = write_dlc(tmp_path / "body.csv", ["p0"], n_frames=40)
    fin = write_dlc(tmp_path / "fin.csv", ["caudal_fin"], n_frames=39)

    with pytest.raises(ValueError, match="different frame counts"):
        trim_pair([body, fin], tmp_path / "out", start=0, frames=10, root=tmp_path)
    assert not (tmp_path / "out").exists()  # nothing half-written


def test_pair_with_duplicate_names_raises(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = write_dlc(tmp_path / "a" / "body.csv", ["p0"], n_frames=20)
    second = write_dlc(tmp_path / "b" / "body.csv", ["p0"], n_frames=20)

    with pytest.raises(ValueError, match="share a name"):
        trim_pair([first, second], tmp_path / "out", start=0, frames=5, root=tmp_path)
    assert not (tmp_path / "out").exists()  # nothing written


@pytest.mark.parametrize("start,frames", [(35, 10), (-1, 5), (0, 0)])
def test_bad_range_raises(tmp_path, start, frames):
    src = write_dlc(tmp_path / "body.csv", ["p0"], n_frames=40)
    with pytest.raises(ValueError):
        trim_dlc_csv(src, tmp_path / "out.csv", start=start, frames=frames, root=tmp_path)


def test_non_dlc_file_raises(tmp_path):
    src = tmp_path / "plain.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a DeepLabCut CSV"):
        read_dlc_csv(src, tmp_path)


def test_trimmed_real_sample_still_passes_verifier(tmp_path):
    src = Path(shutil.copy(LARVAL_SAMPLE, tmp_path / "correct_format.csv"))
    dst = tmp_path / "correct_format_trimmed.csv"
    trim_dlc_csv(src, dst, start=1000, frames=200, root=tmp_path)

    errors, _warnings = verify_deeplabcut_csv(str(dst))
    assert errors == []


def test_paths_outside_root_are_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = write_dlc(tmp_path / "body.csv", ["p0"], n_frames=10)
    inside = write_dlc(root / "body.csv", ["p0"], n_frames=10)

    with pytest.raises(ValueError, match="outside"):
        read_dlc_csv(outside, root)
    with pytest.raises(ValueError, match="outside"):
        read_dlc_csv(root / ".." / "body.csv", root)  # traversal
    with pytest.raises(ValueError, match="outside"):
        trim_dlc_csv(inside, tmp_path / "out.csv", start=0, frames=5, root=root)


def test_cli_refuses_files_outside_repo_without_traceback(tmp_path, capsys):
    body = write_dlc(tmp_path / "body.csv", ["p0"], n_frames=10)
    code = main([str(body), "--start", "0", "--frames", "5", "--out", str(tmp_path / "out")])
    assert code == 1
    assert "outside" in capsys.readouterr().err
