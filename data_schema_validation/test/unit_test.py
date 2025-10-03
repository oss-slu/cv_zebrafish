import io
import os
import pandas as pd
import pytest
from capstone.data_schema_validation.src.csv_verifier import verify_deeplabcut_csv, list_bodyparts

# --------- Helpers ---------
HERE = os.path.dirname(__file__)
SAMPLE_DIR = os.path.abspath(os.path.join(HERE, "..", "sample_inputs", "csv"))

def make_path(filename):
    return os.path.join(SAMPLE_DIR, filename)

def make_csv(content: str):
    """Return a StringIO object so pd.read_csv can read it like a file."""
    return io.StringIO(content)


# --------- Tests for verify_deeplabcut_csv ---------
def test_valid_csv():
    file_path = make_path("correct_format.csv")
    errors, warnings = verify_deeplabcut_csv(file_path)
    assert errors == []
    assert warnings == []


def test_wrong_columns():
    file_path = make_path("incorrect_format.csv")
    errors, warnings = verify_deeplabcut_csv(file_path)
    assert any("wrong columns" in e for e in errors)


def test_non_numeric_values():
    file_path = make_path("non_numeric.csv")
    errors, warnings = verify_deeplabcut_csv(file_path)
    assert any("Non-numeric" in e for e in errors)


def test_out_of_range_coordinates():
    file_path = make_path("range.csv")
    errors, warnings = verify_deeplabcut_csv(file_path, img_width=100, img_height=100)
    assert any("out of range" in w for w in warnings)


def test_likelihood_out_of_bounds():
    file_path = make_path("likelihood.csv")
    errors, warnings = verify_deeplabcut_csv(file_path)
    assert any("Likelihood out of [0,1]" in w for w in warnings)


# --------- Tests for list_bodyparts ---------
def test_list_bodyparts(capsys):
    file_path = make_path("bp.csv")
    list_bodyparts(file_path)
    captured = capsys.readouterr()
    assert "body1" in captured.out
    assert "body2" in captured.out


def test_empty_file():
    file_path = make_path("empty_input.csv")
    with pytest.raises(ValueError, match="Empty input file"):
        list_bodyparts(file_path)
