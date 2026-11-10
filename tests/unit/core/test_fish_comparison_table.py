import math

import pandas as pd
import pytest

from src.core.analysis.summary_statistics import compute_summary_statistics_df
from src.core.comparison.fish_comparison_table import (
    build_comparison_table,
    export_comparison_table,
    get_parameter_names,
)
from src.core.comparison.fish_data import LoadedFish


def make_fish(fish_id, label, results):
    return LoadedFish(
        fish_id=fish_id, label=label, source_file=f"{label}.csv", results=results
    )


@pytest.fixture
def fish_list():
    return [
        make_fish(
            "fish_1",
            "Fish A",
            pd.DataFrame(
                {
                    "Time": [0, 1, 2, 3],
                    "LF_Angle": [10.0, 20.0, 30.0, 40.0],
                    "HeadYaw": [179.0, -179.0, 179.0, -179.0],
                }
            ),
        ),
        make_fish(
            "fish_2",
            "Fish B",
            pd.DataFrame(
                {
                    "Time": [0, 1, 2],
                    "LF_Angle": [5.0, 5.0, 11.0],
                    "Tail_Distance": [0.1, 0.2, 0.3],
                }
            ),
        ),
    ]


def cell(table, parameter, statistic, label):
    row = table[(table["Parameter"] == parameter) & (table["Statistic"] == statistic)]
    return row.iloc[0][label]


def test_parameter_names_exclude_time(fish_list):
    names = get_parameter_names(fish_list)

    assert set(names) == {"LF_Angle", "HeadYaw", "Tail_Distance"}
    assert "Time" not in names


def test_values_match_single_fish_summary_statistics(fish_list):
    table = build_comparison_table(fish_list)

    for fish in fish_list:
        summary = compute_summary_statistics_df(fish.results).set_index("parameter")
        for parameter in summary.index:
            for statistic in ("mean", "median"):
                assert cell(table, parameter, statistic, fish.label) == pytest.approx(
                    summary.at[parameter, statistic]
                )


def test_head_yaw_uses_circular_mean(fish_list):
    table = build_comparison_table(fish_list)

    assert abs(cell(table, "HeadYaw", "mean", "Fish A")) == pytest.approx(180.0, abs=0.1)


def test_units_come_from_summary_statistics(fish_list):
    table = build_comparison_table(fish_list)

    units = table.drop_duplicates("Parameter").set_index("Parameter")["Unit"]
    assert units["LF_Angle"] == "deg"
    assert units["Tail_Distance"] == "m"


def test_missing_parameter_is_nan(fish_list):
    table = build_comparison_table(fish_list)

    assert math.isnan(cell(table, "HeadYaw", "mean", "Fish B"))
    assert math.isnan(cell(table, "Tail_Distance", "median", "Fish A"))


def test_fish_and_parameter_selection(fish_list):
    table = build_comparison_table(fish_list[1:], parameters=["LF_Angle"])

    assert list(table.columns) == ["Parameter", "Unit", "Statistic", "Fish B"]
    assert len(table) == 2


def test_duplicate_or_reserved_labels_are_rejected(fish_list):
    fish_list[1].label = "Fish A"
    with pytest.raises(ValueError):
        build_comparison_table(fish_list)

    fish_list[1].label = "Unit"
    with pytest.raises(ValueError):
        build_comparison_table(fish_list)


def test_export_csv_has_ids_sources_and_excel_bom(fish_list, tmp_path):
    table = build_comparison_table(fish_list, parameters=["LF_Angle"])
    output_path = tmp_path / "comparison.csv"

    export_comparison_table(table, fish_list, output_path)

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    exported = pd.read_csv(output_path, encoding="utf-8-sig")
    assert exported.loc[0, "Parameter"] == "Fish ID"
    assert exported.loc[0, "Fish A"] == "fish_1"
    assert exported.loc[1, "Parameter"] == "Source file"
    assert exported.loc[1, "Fish B"] == "Fish B.csv"
    assert float(exported.loc[2, "Fish A"]) == pytest.approx(25.0)  # LF_Angle mean


def test_export_xlsx_round_trip(fish_list, tmp_path):
    pytest.importorskip("openpyxl")
    table = build_comparison_table(fish_list, parameters=["LF_Angle"])
    output_path = tmp_path / "comparison.xlsx"

    export_comparison_table(table, fish_list, output_path)

    exported = pd.read_excel(output_path)
    assert exported.loc[0, "Fish B"] == "fish_2"
    assert float(exported.loc[2, "Fish B"]) == pytest.approx(7.0)  # LF_Angle mean
    assert float(exported.loc[3, "Fish B"]) == pytest.approx(5.0)  # LF_Angle median


def test_export_rejects_unknown_format(fish_list, tmp_path):
    table = build_comparison_table(fish_list)

    with pytest.raises(ValueError):
        export_comparison_table(table, fish_list, tmp_path / "comparison.txt")