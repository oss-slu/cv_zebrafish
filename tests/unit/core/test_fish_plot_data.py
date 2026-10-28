import numpy as np
import pandas as pd
import pytest

from src.core.comparison.fish_data import LoadedFish
from src.core.comparison.fish_plot_data import (
    FISH_COLORS,
    FishColorMap,
    TIME_AXIS_LABEL,
    get_axis_labels,
    get_time_series,
)


def make_fish(results):
    return LoadedFish(fish_id="fish_1", label="Fish 1", source_file="a.csv", results=results)


def test_color_is_stable_for_a_fish():
    colors = FishColorMap()

    first = colors.color_for("fish_1")
    colors.color_for("fish_2")

    assert colors.color_for("fish_1") == first


def test_colors_are_distinct_until_palette_runs_out():
    colors = FishColorMap()

    assigned = [colors.color_for(f"fish_{n}") for n in range(len(FISH_COLORS))]

    assert len(set(assigned)) == len(FISH_COLORS)


def test_more_fish_than_colors_reuses_colors():
    colors = FishColorMap()

    assigned = [colors.color_for(f"fish_{n}") for n in range(len(FISH_COLORS) + 2)]

    assert all(color in FISH_COLORS for color in assigned)


def test_released_color_is_reused_and_others_keep_theirs():
    colors = FishColorMap()
    first = colors.color_for("fish_1")
    second = colors.color_for("fish_2")

    colors.release("fish_1")

    assert colors.color_for("fish_2") == second
    assert colors.color_for("fish_3") == first


def test_time_series_uses_time_column_and_returns_floats():
    fish = make_fish(pd.DataFrame({"Time": [0, 1, 2], "LF_Angle": [1.0, 2.0, 3.0]}))

    x, y = get_time_series(fish, "LF_Angle")

    assert list(x) == [0.0, 1.0, 2.0]
    assert list(y) == [1.0, 2.0, 3.0]


def test_time_series_without_time_column_uses_row_numbers():
    fish = make_fish(pd.DataFrame({"LF_Angle": [5.0, 6.0]}))

    x, _ = get_time_series(fish, "LF_Angle")

    assert list(x) == [0.0, 1.0]


def test_time_series_turns_bad_values_into_nan():
    fish = make_fish(pd.DataFrame({"Time": [0, 1, 2, 3], "HeadYaw": [1.0, "", np.inf, 4.0]}))

    _, y = get_time_series(fish, "HeadYaw")

    assert np.isnan(y[1]) and np.isnan(y[2])
    assert y[0] == 1.0 and y[3] == 4.0


def test_time_series_unknown_parameter_raises():
    fish = make_fish(pd.DataFrame({"LF_Angle": [1.0]}))

    with pytest.raises(KeyError):
        get_time_series(fish, "Nope")


def test_axis_labels_include_units():
    x_label, y_label = get_axis_labels("LF_Angle")

    assert x_label == TIME_AXIS_LABEL
    assert y_label == "LF_Angle (deg)"
    assert get_axis_labels("Tail_Distance")[1] == "Tail_Distance (m)"