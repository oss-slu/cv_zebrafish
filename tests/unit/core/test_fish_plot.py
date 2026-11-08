import pandas as pd

from src.core.comparison.fish_data import LoadedFish
from src.core.comparison.fish_plot import build_overlay_figure
from src.core.comparison.fish_plot_data import FishColorMap


def make_fish(number, columns=("LF_Angle",)):
    results = pd.DataFrame({"Time": [0, 1, 2]})
    for column in columns:
        results[column] = [10.0 * number, 20.0 * number, 30.0 * number]
    return LoadedFish(
        fish_id=f"fish_{number}",
        label=f"Fish {number}",
        source_file=f"fish_{number}.csv",
        results=results,
    )


def test_one_line_per_fish_with_names_and_values():
    fish_list = [make_fish(1), make_fish(2)]

    figure = build_overlay_figure(fish_list, "LF_Angle", FishColorMap())

    assert [trace.name for trace in figure.data] == ["Fish 1", "Fish 2"]
    assert list(figure.data[1].y) == [20.0, 40.0, 60.0]
    assert list(figure.data[1].x) == [0.0, 1.0, 2.0]


def test_axis_titles_and_legend_include_units():
    figure = build_overlay_figure([make_fish(1)], "LF_Angle", FishColorMap())

    assert figure.layout.xaxis.title.text == "Time (frames)"
    assert figure.layout.yaxis.title.text == "LF_Angle (deg)"
    assert figure.layout.showlegend is True


def test_colors_come_from_the_shared_color_map():
    fish_list = [make_fish(1), make_fish(2)]
    colors = FishColorMap()

    figure = build_overlay_figure(fish_list, "LF_Angle", colors)

    assert [trace.line.color for trace in figure.data] == [
        colors.color_for("fish_1"),
        colors.color_for("fish_2"),
    ]


def test_color_is_consistent_across_different_parameter_plots():
    fish_list = [make_fish(1, ("LF_Angle", "RF_Angle")), make_fish(2, ("LF_Angle", "RF_Angle"))]
    colors = FishColorMap()

    first = build_overlay_figure(fish_list, "LF_Angle", colors)
    second = build_overlay_figure(fish_list, "RF_Angle", colors)
    hidden_first = build_overlay_figure(fish_list[1:], "RF_Angle", colors)

    assert [t.line.color for t in first.data] == [t.line.color for t in second.data]
    assert hidden_first.data[0].line.color == second.data[1].line.color


def test_fish_without_the_parameter_are_left_out():
    fish_list = [make_fish(1, ("LF_Angle",)), make_fish(2, ("Tail_Distance",))]

    figure = build_overlay_figure(fish_list, "LF_Angle", FishColorMap())

    assert [trace.name for trace in figure.data] == ["Fish 1"]


def test_no_fish_gives_an_empty_figure():
    figure = build_overlay_figure([], "LF_Angle", FishColorMap())

    assert len(figure.data) == 0