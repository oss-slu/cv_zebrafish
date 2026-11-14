import io

import pandas as pd
import pytest

from src.core.input_source import InputSourceError, load_csv_source

CSV_TEXT = "a,b\n1,2\n3,4\n"


def test_reads_file_like_object():
    assert len(load_csv_source(io.StringIO(CSV_TEXT))) == 2


def test_file_like_object_can_be_read_twice():
    source = io.StringIO(CSV_TEXT)
    load_csv_source(source)
    assert len(load_csv_source(source)) == 2


def test_reads_path(tmp_path):
    path = tmp_path / "fish.csv"
    path.write_text(CSV_TEXT)
    assert len(load_csv_source(path)) == 2


def test_dataframe_is_returned_as_a_copy():
    original = pd.DataFrame({"a": [1]})
    result = load_csv_source(original)
    result.loc[0, "a"] = 99
    assert original.loc[0, "a"] == 1


def test_empty_input_raises_input_source_error():
    with pytest.raises(InputSourceError):
        load_csv_source(io.StringIO(""))


def test_missing_path_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_csv_source(tmp_path / "missing.csv")