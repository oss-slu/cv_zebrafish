from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

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
def _make_results_df(n_rows: int = 50) -> pd.DataFrame:
    """Small metrics table with one row per frame."""
    return pd.DataFrame(
        {
            "Time": list(range(n_rows)),
            "LF_Angle": [i * 0.5 for i in range(n_rows)],
            "RF_Angle": [i * 0.25 for i in range(n_rows)],
        }
    )


def _scene_with_results(df: pd.DataFrame) -> GraphViewerScene:
    scene = GraphViewerScene()
    scene.set_graphs({}, results_df=df)
    return scene


@pytest.fixture
def message_boxes(monkeypatch):
    """Replace the modal QMessageBox dialogs so tests never block, and record calls."""
    calls = {"information": [], "warning": [], "critical": []}
    for kind in calls:
        monkeypatch.setattr(
            QMessageBox,
            kind,
            staticmethod(lambda *args, _kind=kind, **kwargs: calls[_kind].append(args)),
        )
    return calls


def test_set_data_generates_requested_dot_plots(qt_app, monkeypatch):
    """Ensure set_data honors config flags and builds the correct count."""
    scene = GraphViewerScene()

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
def test_range_controls_disabled_without_results_df(qt_app):
    """No DataFrame (e.g. PNG-only session) means the export controls stay disabled."""
    scene = GraphViewerScene()
    assert not scene.export_range_btn.isEnabled()

    scene.set_graphs({})  # no results_df passed

    assert not scene.range_start_spin.isEnabled()
    assert not scene.range_end_spin.isEnabled()
    assert not scene.export_range_btn.isEnabled()


def test_range_controls_enabled_with_results_df(qt_app):
    """A results DataFrame enables the controls and sets the full default range."""
    scene = _scene_with_results(_make_results_df(50))

    assert scene.range_start_spin.isEnabled()
    assert scene.range_end_spin.isEnabled()
    assert scene.export_range_btn.isEnabled()
    assert scene.range_start_spin.maximum() == 49
    assert scene.range_start_spin.value() == 0
    assert scene.range_end_spin.value() == 49


def test_export_range_writes_only_selected_rows(qt_app, monkeypatch, tmp_path, message_boxes):
    df = _make_results_df(50)
    scene = _scene_with_results(df)
    out_file = tmp_path / "range.csv"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(out_file), "")),
    )

    scene.range_start_spin.setValue(10)
    scene.range_end_spin.setValue(20)
    scene._on_export_range_clicked()

    exported = pd.read_csv(out_file)
    expected = df.iloc[10:21].reset_index(drop=True)
    pd.testing.assert_frame_equal(exported, expected)
    assert exported["Time"].tolist() == list(range(10, 21))
    assert len(message_boxes["information"]) == 1
    assert message_boxes["critical"] == []


def test_export_range_cancelled_dialog_writes_nothing(qt_app, monkeypatch, tmp_path, message_boxes):
    scene = _scene_with_results(_make_results_df(50))
    dialog_calls = []

    def fake_dialog(*args, **kwargs):
        dialog_calls.append(args)
        return ("", "")  # what Qt returns when the user cancels

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_dialog))

    scene.range_start_spin.setValue(3)
    scene.range_end_spin.setValue(8)
    scene._on_export_range_clicked()

    assert len(dialog_calls) == 1
    assert list(tmp_path.iterdir()) == []
    assert message_boxes["information"] == []
    assert message_boxes["warning"] == []
    assert message_boxes["critical"] == []


def test_export_invalid_range_warns_without_crashing(qt_app, monkeypatch, tmp_path, message_boxes):
    scene = _scene_with_results(_make_results_df(50))
    dialog_calls = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: dialog_calls.append(args) or ("", "")),
    )

    scene.range_start_spin.setValue(30)
    scene.range_end_spin.setValue(5)  # start > end
    scene._on_export_range_clicked()  # must not raise

    assert len(message_boxes["warning"]) == 1
    assert dialog_calls == []  # never got as far as asking where to save
    assert list(tmp_path.iterdir()) == []
    

def test_range_controls_reenabled_after_broken_graph(qt_app, monkeypatch):
    """A missing graph disables the controls; selecting a working graph re-enables them."""
    scene = _scene_with_results(_make_results_df(50))
    monkeypatch.setattr(scene.interactive_graph, "set_figure", lambda fig: None)
    scene._graphs["Working graph"] = go.Figure()
    scene.range_start_spin.setValue(5)

    scene._show_graph("Not a real graph")
    assert not scene.export_range_btn.isEnabled()

    scene._show_graph("Working graph")
    assert scene.export_range_btn.isEnabled()
    assert scene.range_start_spin.value() == 5  # range not reset by clicking a graph
