import pandas as pd
import pytest
from PyQt5.QtWidgets import QApplication

from src.core.comparison.fish_data import LoadedFish
from src.core.comparison.fish_plot_data import FishColorMap
from ui.components.fish_overlay_widget import FishOverlayWidget


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_fish(number):
    results = pd.DataFrame(
        {
            "Time": [0, 1, 2],
            "LF_Angle": [10.0 * number, 20.0 * number, 30.0 * number],
            "Tail_Distance": [0.1 * number, 0.2 * number, 0.3 * number],
        }
    )
    return LoadedFish(f"fish_{number}", f"Fish {number}", f"fish_{number}.csv", results)


@pytest.fixture
def setup(qt_app):
    widget = FishOverlayWidget()
    colors = FishColorMap()
    fish_list = [make_fish(n) for n in range(1, 6)]
    widget.set_data(fish_list, ["LF_Angle", "Tail_Distance"], colors)
    return widget, colors, fish_list


def test_one_line_per_fish_in_shared_colors(setup):
    widget, colors, fish_list = setup

    assert [trace.name for trace in widget.figure.data] == [f.label for f in fish_list]
    assert [trace.line.color for trace in widget.figure.data] == [
        colors.color_for(f.fish_id) for f in fish_list
    ]


def test_switching_parameter_keeps_colors_and_updates_axis(setup):
    widget, _, _ = setup
    before = [trace.line.color for trace in widget.figure.data]

    widget.parameter_combo.setCurrentText("Tail_Distance")

    assert widget.figure.layout.yaxis.title.text == "Tail_Distance (m)"
    assert [trace.line.color for trace in widget.figure.data] == before


def test_hiding_a_fish_does_not_change_other_colors(setup):
    widget, colors, fish_list = setup
    before = {trace.name: trace.line.color for trace in widget.figure.data}

    widget.set_data(fish_list[2:], ["LF_Angle"], colors)

    for trace in widget.figure.data:
        assert trace.line.color == before[trace.name]


def test_parameter_choice_survives_a_data_refresh(setup):
    widget, colors, fish_list = setup
    widget.parameter_combo.setCurrentText("Tail_Distance")

    widget.set_data(fish_list, ["LF_Angle", "Tail_Distance"], colors)

    assert widget.parameter_combo.currentText() == "Tail_Distance"


def test_clear_shows_the_empty_message(setup):
    widget, _, _ = setup

    widget.clear()

    assert widget.figure is None
    assert not widget.message_label.isHidden()