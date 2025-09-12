import io
import pandas as pd
import pytest
from data_schema_validation.src.input_verifier import verify_deeplabcut_csv, list_bodyparts

# --------- Helpers ---------


def make_csv(content: str):
    """Return a StringIO object so pd.read_csv can read it like a file."""
    return io.StringIO(content)


# --------- Tests for verify_deeplabcut_csv ---------
def test_valid_csv(tmp_path):
    csv_text = """scorer,body1,body1,body1
scorer,x,y,likelihood
s1,10,20,0.9
s2,15,25,0.8
"""
    file_path = tmp_path / "valid.csv"
    file_path.write_text(csv_text)

    errors, warnings = verify_deeplabcut_csv(
        file_path, img_width=100, img_height=100)
    assert errors == []
    assert warnings == []


def test_wrong_columns(tmp_path):
    csv_text = """scorer,body1,body1
scorer,x,z
s1,10,20
"""
    file_path = tmp_path / "wrong_cols.csv"
    file_path.write_text(csv_text)

    errors, warnings = verify_deeplabcut_csv(file_path)
    assert any("wrong columns" in e for e in errors)


def test_non_numeric_values(tmp_path):
    csv_text = """scorer,body1,body1,body1
scorer,x,y,likelihood
s1,abc,25,0.5
"""
    file_path = tmp_path / "non_numeric.csv"
    file_path.write_text(csv_text)

    errors, warnings = verify_deeplabcut_csv(file_path)
    assert any("Non-numeric" in e for e in errors)


def test_out_of_range_coordinates(tmp_path):
    csv_text = """scorer,body1,body1,body1
scorer,x,y,likelihood
s1,999,-10,0.5
"""
    file_path = tmp_path / "range.csv"
    file_path.write_text(csv_text)

    errors, warnings = verify_deeplabcut_csv(
        file_path, img_width=100, img_height=100)
    assert any("out of range" in w for w in warnings)


def test_likelihood_out_of_bounds(tmp_path):
    csv_text = """scorer,body1,body1,body1
scorer,x,y,likelihood
s1,10,20,2.0
"""
    file_path = tmp_path / "likelihood.csv"
    file_path.write_text(csv_text)

    errors, warnings = verify_deeplabcut_csv(file_path)
    assert any("Likelihood out of [0,1]" in w for w in warnings)


# --------- Tests for list_bodyparts ---------
def test_list_bodyparts(capsys, tmp_path):
    csv_text = """scorer,body1,body2,body1
scorer,x,y,likelihood
s1,10,20,0.5
"""
    file_path = tmp_path / "bp.csv"
    file_path.write_text(csv_text)

    list_bodyparts(file_path)
    captured = capsys.readouterr()
    assert "body1" in captured.out
    assert "body2" in captured.out
