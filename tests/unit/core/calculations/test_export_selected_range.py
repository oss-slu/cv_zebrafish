"""Unit tests for src.core.calculations.export_selected_range (issue #115)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from src.core.calculations.export_selected_range import (
    InvalidRangeError,
    default_export_filename,
    export_range_to_csv,
    select_range,
    validate_range,
)


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Ten frames with a mix of numeric and string columns."""
    return pd.DataFrame(
        {
            "Time": np.arange(10),
            "LF_Angle": np.linspace(0.0, 9.0, 10),
            "RF_Angle": np.linspace(10.0, 19.0, 10),
            "Tail_Side": ["Left", "Right"] * 5,
        }
    )


# ---------------------------------------------------------------------------
# select_range
# ---------------------------------------------------------------------------


def test_select_range_returns_inclusive_middle_rows(sample_df):
    subset = select_range(sample_df, 2, 5)

    assert subset["Time"].tolist() == [2, 3, 4, 5]
    assert len(subset) == 4


def test_select_range_preserves_columns_and_values(sample_df):
    subset = select_range(sample_df, 3, 6)

    assert list(subset.columns) == list(sample_df.columns)
    pdt.assert_frame_equal(subset, sample_df.iloc[3:7])


def test_select_range_single_row(sample_df):
    subset = select_range(sample_df, 4, 4)

    assert len(subset) == 1
    assert subset["Time"].iloc[0] == 4


def test_select_range_full_dataset(sample_df):
    subset = select_range(sample_df, 0, len(sample_df) - 1)

    pdt.assert_frame_equal(subset, sample_df)


def test_select_range_returns_independent_copy(sample_df):
    subset = select_range(sample_df, 0, 2)
    subset.loc[subset.index[0], "LF_Angle"] = 999.0

    assert sample_df["LF_Angle"].iloc[0] == 0.0


def test_select_range_accepts_numpy_integers(sample_df):
    subset = select_range(sample_df, np.int64(1), np.int32(3))

    assert subset["Time"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# validate_range
# ---------------------------------------------------------------------------


def test_validate_range_returns_plain_ints(sample_df):
    start, end = validate_range(sample_df, np.int64(1), np.int64(4))

    assert (start, end) == (1, 4)
    assert type(start) is int and type(end) is int


@pytest.mark.parametrize(
    "start, end",
    [
        (5, 2),   # start after end
        (-1, 3),  # negative start
        (0, 10),  # end one past the last row (10 rows -> last is 9)
        (0, 999),  # end far out of bounds
    ],
)
def test_validate_range_rejects_out_of_order_or_out_of_bounds(sample_df, start, end):
    with pytest.raises(InvalidRangeError):
        validate_range(sample_df, start, end)


@pytest.mark.parametrize(
    "start, end",
    [
        (1.5, 3),
        (1, 3.0),
        ("1", 3),
        (None, 3),
        (1, None),
        (True, 3),
    ],
)
def test_validate_range_rejects_non_integer_bounds(sample_df, start, end):
    with pytest.raises(InvalidRangeError):
        validate_range(sample_df, start, end)


def test_validate_range_rejects_empty_dataframe():
    with pytest.raises(InvalidRangeError):
        validate_range(pd.DataFrame({"Time": []}), 0, 0)


@pytest.mark.parametrize("bad_df", [None, [1, 2, 3], "not a dataframe"])
def test_validate_range_rejects_missing_dataframe(bad_df):
    with pytest.raises(InvalidRangeError):
        validate_range(bad_df, 0, 1)


def test_invalid_range_error_is_a_value_error():
    assert issubclass(InvalidRangeError, ValueError)


# ---------------------------------------------------------------------------
# default_export_filename
# ---------------------------------------------------------------------------


def test_default_export_filename_uses_source_stem_and_range():
    assert default_export_filename("data/fish1.csv", 100, 250) == "fish1_frames_100-250.csv"


@pytest.mark.parametrize("source", [None, ""])
def test_default_export_filename_falls_back_without_source(source):
    assert default_export_filename(source, 0, 9) == "results_frames_0-9.csv"


# ---------------------------------------------------------------------------
# export_range_to_csv
# ---------------------------------------------------------------------------


def test_export_writes_only_selected_rows(sample_df, tmp_path):
    out = tmp_path / "range.csv"

    written = export_range_to_csv(sample_df, 2, 5, out)

    assert written == out
    exported = pd.read_csv(out)
    assert exported["Time"].tolist() == [2, 3, 4, 5]


def test_export_preserves_headers_and_values(sample_df, tmp_path):
    out = tmp_path / "range.csv"

    export_range_to_csv(sample_df, 3, 7, out)

    exported = pd.read_csv(out)
    expected = sample_df.iloc[3:8].reset_index(drop=True)
    assert list(exported.columns) == list(sample_df.columns)
    pdt.assert_frame_equal(exported, expected)


def test_export_does_not_write_the_index_column(sample_df, tmp_path):
    out = tmp_path / "range.csv"

    export_range_to_csv(sample_df, 0, 2, out)

    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(sample_df.columns)


def test_export_keeps_nan_values_as_empty_cells(tmp_path):
    df = pd.DataFrame({"Time": [0, 1, 2], "LF_Angle": [1.0, np.nan, 3.0]})
    out = tmp_path / "nan.csv"

    export_range_to_csv(df, 0, 2, out)

    exported = pd.read_csv(out)
    assert np.isnan(exported["LF_Angle"].iloc[1])


def test_export_adds_csv_extension_when_missing(sample_df, tmp_path):
    written = export_range_to_csv(sample_df, 0, 1, tmp_path / "no_extension")

    assert written.suffix == ".csv"
    assert written.exists()


def test_export_creates_missing_parent_folders(sample_df, tmp_path):
    out = tmp_path / "nested" / "folder" / "range.csv"

    written = export_range_to_csv(sample_df, 0, 1, out)

    assert written.exists()


def test_export_invalid_range_raises_and_writes_nothing(sample_df, tmp_path):
    out = tmp_path / "should_not_exist.csv"

    with pytest.raises(InvalidRangeError):
        export_range_to_csv(sample_df, 6, 2, out)

    assert not out.exists()


def test_export_does_not_modify_source_dataframe(sample_df, tmp_path):
    before = sample_df.copy(deep=True)

    export_range_to_csv(sample_df, 1, 4, tmp_path / "range.csv")

    pdt.assert_frame_equal(sample_df, before)