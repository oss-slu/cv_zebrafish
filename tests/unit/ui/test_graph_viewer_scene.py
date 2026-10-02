from __future__ import annotations

import pandas as pd
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication

from ui.main_panels.graph_viewer_widget import GraphViewerScene


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def mock_pixmap_generation(monkeypatch):
    """Avoid slow Kaleido PNG generation during UI unit tests."""
    def fake_pixmap(self, fig):
        pix = QPixmap(10, 10)
        pix.fill(Qt.white)
        return pix

    monkeypatch.setattr(GraphViewerScene, "_figure_to_pixmap", fake_pixmap)
    monkeypatch.setattr(GraphViewerScene, "_source_to_pixmap_safe", fake_pixmap)


def test_set_data_generates_requested_dot_plots(qt_app):
    """Ensure set_data honors config flags and builds the correct count."""
    scene = GraphViewerScene()

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
    payload = {"results_df": df, "config": config, "csv_path": "demo.csv"}

    scene.set_data(payload)

    assert len(scene._graphs) == 2
    assert "Tail Distance vs Left Fin Angle" in scene._graphs
    assert "Tail Distance vs Left Fin Angle (Moving)" in scene._graphs


def test_set_data_populates_range_statistics(qt_app):
    """Ensure that loading data automatically computes range statistics for the active graph."""
    scene = GraphViewerScene()

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
        },
        "video_parameters": {"recorded_framerate": 50},
    }
    payload = {"results_df": df, "config": config, "csv_path": "demo.csv"}

    scene.set_data(payload)

    widget = scene.range_stats_widget
    assert widget is not None
    assert widget.isEnabled() is True

    stats = widget.get_current_statistics()
    assert stats is not None
    assert stats.is_valid is True
    assert stats.count == 3
    assert stats.min_value == 1.0
    assert stats.max_value == 1.4
    assert stats.min_x == 0.0
    assert stats.max_x == 0.15
    assert stats.mean_value == pytest.approx((1.0 + 1.1 + 1.4) / 3)


def test_range_statistics_subrange_filtering(qt_app):
    """Ensure user can specify a narrower range and statistics update accurately."""
    scene = GraphViewerScene()

    df = pd.DataFrame(
        {
            "Tail_Distance": [0.0, 0.05, 0.15, 0.25],
            "LF_Angle": [10.0, 50.0, 20.0, 80.0],
            "RF_Angle": [5.0, 15.0, 25.0, 35.0],
        }
    )
    config = {
        "shown_outputs": {
            "show_tail_left_fin_angle_dot_plot": True,
        },
        "video_parameters": {"recorded_framerate": 50},
    }
    payload = {"results_df": df, "config": config, "csv_path": "demo.csv"}
    scene.set_data(payload)

    widget = scene.range_stats_widget
    # Select subrange [0.04, 0.16] -> points at 0.05 (50.0) and 0.15 (20.0)
    widget.set_range(0.04, 0.16)

    stats = widget.get_current_statistics()
    assert stats.is_valid is True
    assert stats.count == 2
    assert stats.min_value == 20.0
    assert stats.min_x == 0.15
    assert stats.max_value == 50.0
    assert stats.max_x == 0.05
    assert stats.mean_value == 35.0


def test_range_statistics_invalid_range_handled_gracefully(qt_app):
    """Ensure invalid range does not crash GraphViewerScene and displays error."""
    scene = GraphViewerScene()

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
        },
        "video_parameters": {"recorded_framerate": 50},
    }
    payload = {"results_df": df, "config": config, "csv_path": "demo.csv"}
    scene.set_data(payload)

    widget = scene.range_stats_widget
    widget.start_spin.setValue(1.0)
    widget.end_spin.setValue(0.1)
    widget.calculate_statistics()

    stats = widget.get_current_statistics()
    assert stats.is_valid is False
    assert not widget.status_label.isHidden()
    assert "cannot exceed" in widget.status_label.text()
