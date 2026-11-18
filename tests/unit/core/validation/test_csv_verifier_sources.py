import io

import pandas as pd

from src.core.validation.csv_verifier import list_bodyparts, verify_deeplabcut_csv

VALID_CSV = (
    "scorer,DLC,DLC,DLC\n"
    "bodyparts,Head,Head,Head\n"
    "coords,x,y,likelihood\n"
    "0,1.0,2.0,0.99\n"
    "1,1.5,2.5,0.98\n"
)


def test_file_like_object_passes():
    errors, _ = verify_deeplabcut_csv(io.StringIO(VALID_CSV))
    assert errors == []


def test_dataframe_passes():
    errors, _ = verify_deeplabcut_csv(pd.read_csv(io.StringIO(VALID_CSV)))
    assert errors == []


def test_missing_file_message_is_unchanged(tmp_path):
    errors, _ = verify_deeplabcut_csv(str(tmp_path / "missing.csv"))
    assert any("File does not exist" in error for error in errors)


def test_empty_file_returns_error_instead_of_raising():
    errors, _ = verify_deeplabcut_csv(io.StringIO(""))
    assert errors


def test_header_only_file_returns_error_instead_of_raising():
    errors, _ = verify_deeplabcut_csv(io.StringIO("scorer,DLC,DLC\n"))
    assert any("too small" in error for error in errors)


def test_missing_coords_row_returns_error_instead_of_raising():
    errors, _ = verify_deeplabcut_csv(io.StringIO("scorer,DLC,DLC\nbodyparts,Head,Head\n"))
    assert any("too small" in error for error in errors)


def test_list_bodyparts_from_file_like_object():
    assert list(list_bodyparts(io.StringIO(VALID_CSV))) == ["Head"]

def test_pathlib_path_is_accepted(tmp_path):
    path = tmp_path / "fish.csv"
    path.write_text(VALID_CSV)
    errors, _ = verify_deeplabcut_csv(path)
    assert errors == []


def test_non_csv_path_is_rejected(tmp_path):
    path = tmp_path / "fish.txt"
    path.write_text(VALID_CSV)
    errors, _ = verify_deeplabcut_csv(path)
    assert any("not a CSV" in error for error in errors)


def test_non_numeric_values_are_reported():
    text = VALID_CSV.replace("1.0,2.0", "abc,2.0")
    errors, _ = verify_deeplabcut_csv(io.StringIO(text))
    assert any("Non-numeric values in Head-x" in error for error in errors)


def test_unexpected_coordinate_columns_are_reported():
    text = VALID_CSV.replace("coords,x,y,likelihood", "coords,x,y,z")
    errors, _ = verify_deeplabcut_csv(io.StringIO(text))
    assert any("wrong columns" in error for error in errors)


def test_dataframe_input_is_not_modified():
    frame = pd.read_csv(io.StringIO(VALID_CSV))
    original = frame.copy()
    verify_deeplabcut_csv(frame)
    pd.testing.assert_frame_equal(frame, original)
