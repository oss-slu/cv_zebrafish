from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cvzebrafish.core.validation.csv_verifier import (
    list_bodyparts,
    verify_deeplabcut_csv,
)


def _write_dlc_csv(tmp_path: Path, name: str, bodyparts: list[str], data_rows: list[str]) -> Path:
    columns = ["scorer"]
    bodyparts_row = ["bodyparts"]
    coords_row = ["coords"]
    for bp in bodyparts:
        columns.extend([bp, bp, bp])
        bodyparts_row.extend([bp, bp, bp])
        coords_row.extend(["x", "y", "likelihood"])

    path = tmp_path / name
    header = [
        ",".join(columns),
        ",".join(bodyparts_row),
        ",".join(coords_row),
    ]
    path.write_text("\n".join(header + data_rows))
    return path


def test_valid_csv(tmp_path: Path):
    csv_path = _write_dlc_csv(tmp_path, "valid.csv", ["body1"], ["frame0,10,20,0.9"])
    errors, warnings = verify_deeplabcut_csv(str(csv_path))
    assert errors == []
    assert warnings == []


def test_wrong_columns(tmp_path: Path):
    path = tmp_path / "wrong_columns.csv"
    path.write_text(
        "\n".join(
            [
                "scorer,body1,body1,body1",
                "bodyparts,body1,body1,body1",
                "coords,x,likelihood,y",  # swapped order
                "frame0,10,0.9,20",
            ]
        )
    )
    errors, warnings = verify_deeplabcut_csv(str(path))
    assert any("wrong columns" in err for err in errors)


def test_non_numeric_values(tmp_path: Path):
    csv_path = _write_dlc_csv(tmp_path, "non_numeric.csv", ["body1"], ["frame0,abc,20,0.9"])
    errors, _ = verify_deeplabcut_csv(str(csv_path))
    assert any("Non-numeric values" in err for err in errors)


def test_out_of_range_coordinates(tmp_path: Path):
    csv_path = _write_dlc_csv(tmp_path, "range.csv", ["body1"], ["frame0,150,-10,0.9"])
    errors, warnings = verify_deeplabcut_csv(str(csv_path), img_width=100, img_height=100)
    assert any("out of range" in warn for warn in warnings)
    assert any("out of range" in err for err in errors)


def test_likelihood_out_of_bounds(tmp_path: Path):
    csv_path = _write_dlc_csv(tmp_path, "likelihood.csv", ["body1"], ["frame0,10,20,1.5"])
    _, warnings = verify_deeplabcut_csv(str(csv_path))
    assert any("Likelihood out of [0,1]" in warn for warn in warnings)


def test_list_bodyparts(tmp_path: Path):
    csv_path = _write_dlc_csv(
        tmp_path,
        "bodyparts.csv",
        ["body1", "body2"],
        [
            "frame0,10,20,0.9,30,40,0.8",
        ],
    )
    bodyparts = list_bodyparts(str(csv_path))
    assert set(bodyparts) == {"body1", "body2"}


def test_empty_file(tmp_path: Path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("")
    with pytest.raises(pd.errors.EmptyDataError):
        list_bodyparts(str(csv_path))
