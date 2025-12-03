from __future__ import annotations

import pandas as pd
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication

from ui.scenes.GraphViewerScene import GraphViewerScene


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_set_data_generates_requested_dot_plots(qt_app, monkeypatch):
    """Ensure set_data honors config flags and builds the correct count."""
    scene = GraphViewerScene()

    def fake_pixmap(self, fig):
        pix = QPixmap(10, 10)
        pix.fill(Qt.white)
        return pix

    monkeypatch.setattr(GraphViewerScene, "_figure_to_pixmap", fake_pixmap)

    df = pd.DataFrame(
        {
            "Tail_Distance": [0.0, 0.05, 0.15],
            "LF_Angle": [1.0, 1.1, 1.4],
            "RF_Angle": [0.9, 1.0, 1.2],
        }
    )
    config = {
        "shown_outputs": {
            "show_tail_left_fin_angle_dot_plot": True,
            "show_tail_right_fin_angle_dot_plot": False,
            "show_tail_left_fin_moving_dot_plot": True,
            "show_tail_right_fin_moving_dot_plot": False,
        },
        "video_parameters": {"recorded_framerate": 50},
    }
    payload = {"results_df": df, "config": config}

    scene.set_data(payload)

    assert len(scene._graphs) == 2
    assert "Tail Distance vs Left Fin Angle" in scene._graphs
    assert "Tail Distance vs Left Fin Angle (Moving)" in scene._graphs


def test_set_data_skips_head_plot_when_flag_disabled(qt_app, monkeypatch):
    """Ensure head plot is not generated when show_head_plot is False."""
    scene = GraphViewerScene()

    def fake_pixmap(self, fig):
        pix = QPixmap(10, 10)
        pix.fill(Qt.white)
        return pix

    monkeypatch.setattr(GraphViewerScene, "_figure_to_pixmap", fake_pixmap)

    df = pd.DataFrame(
        {
            "Tail_Distance": [0.0, 0.05, 0.15],
            "LF_Angle": [1.0, 1.1, 1.4],
            "RF_Angle": [0.9, 1.0, 1.2],
        }
    )
    config = {
        "shown_outputs": {
            "show_tail_left_fin_angle_dot_plot": True,
            "show_head_plot": False,
        },
        "video_parameters": {"recorded_framerate": 50},
    }
    payload = {"results_df": df, "config": config}

    scene.set_data(payload)

    # Only dot plot should be present
    assert len(scene._graphs) == 1
    assert "Tail Distance vs Left Fin Angle" in scene._graphs
    assert not any("Head Plot" in name for name in scene._graphs.keys())


def test_set_data_warns_when_head_plot_missing_required_columns(qt_app, monkeypatch):
    """Ensure head plot generates a warning when required DataFrame columns are missing."""
    scene = GraphViewerScene()

    def fake_pixmap(self, fig):
        pix = QPixmap(10, 10)
        pix.fill(Qt.white)
        return pix

    monkeypatch.setattr(GraphViewerScene, "_figure_to_pixmap", fake_pixmap)

    # DataFrame missing HeadYaw column
    df = pd.DataFrame(
        {
            "Tail_Distance": [0.0, 0.05, 0.15],
            "LF_Angle": [1.0, 1.1, 1.4],
            "RF_Angle": [0.9, 1.0, 1.2],
        }
    )
    config = {
        "shown_outputs": {
            "show_tail_left_fin_angle_dot_plot": True,
            "show_head_plot": True,
        },
        "video_parameters": {"recorded_framerate": 50},
    }
    payload = {"results_df": df, "config": config}

    scene.set_data(payload)

    # Should still have the dot plot
    assert len(scene._graphs) == 1
    assert "Tail Distance vs Left Fin Angle" in scene._graphs
    # Check that tooltip contains warning about missing columns
    tooltip = scene.list.toolTip().lower()
    assert "missing dataframe columns" in tooltip and "headyaw" in tooltip


def test_set_data_generates_head_plot_when_all_data_present(qt_app, monkeypatch):
    """Ensure head plot is generated when flag is enabled and all required data is present."""
    scene = GraphViewerScene()

    def fake_pixmap(self, fig):
        pix = QPixmap(10, 10)
        pix.fill(Qt.white)
        return pix

    monkeypatch.setattr(GraphViewerScene, "_figure_to_pixmap", fake_pixmap)

    # DataFrame with all required columns for head plot
    df = pd.DataFrame(
        {
            "Tail_Distance": [0.0, 0.05, 0.15],
            "LF_Angle": [45.0, 50.0, 55.0],
            "RF_Angle": [40.0, 45.0, 50.0],
            "HeadYaw": [10.0, 15.0, 20.0],
        }
    )
    config = {
        "shown_outputs": {
            "show_tail_left_fin_angle_dot_plot": True,
            "show_head_plot": True,
        },
        "video_parameters": {"recorded_framerate": 50},
        "graph_cutoffs": {
            "left_fin_angle": 30,
            "right_fin_angle": 30,
        },
    }
    payload = {"results_df": df, "config": config}

    scene.set_data(payload)

    # Should have both dot plot and head plot
    assert len(scene._graphs) >= 1  # At least the dot plot
    assert "Tail Distance vs Left Fin Angle" in scene._graphs
    # Head plot should be present (may be named with range or just "Head Plot")
    has_head_plot = any("Head Plot" in name for name in scene._graphs.keys())
    assert has_head_plot
