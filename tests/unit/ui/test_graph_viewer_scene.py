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


def _line_figure(*trace_names: str | None) -> go.Figure:
    """Build a small line figure with one trace per name (None leaves a trace unnamed)."""
    fig = go.Figure()
    for offset, trace_name in enumerate(trace_names or (None,)):
        fig.add_trace(
            go.Scatter(x=[0, 1, 2], y=[offset, offset + 1, offset + 2], name=trace_name)
        )
    fig.update_layout(xaxis_title="Frame", yaxis_title="Angle (deg)")
    return fig


def _overlay_scene(monkeypatch, graphs_by_csv):
    """Build a scene from per-CSV graphs with its web views stubbed out.

    Returns the scene, the figures sent to the overlay view, and a list that
    gains an entry each time the overlay view is cleared.
    """
    scene = GraphViewerScene()
    drawn: list[go.Figure] = []
    cleared: list[bool] = []
    monkeypatch.setattr(scene, "_kaleido_available", False)
    monkeypatch.setattr(scene.interactive_graph, "set_figure", lambda fig: None)
    monkeypatch.setattr(scene.overlay_view, "set_figure", drawn.append)
    monkeypatch.setattr(scene.overlay_view, "clear", lambda: cleared.append(True))
    scene.set_graphs_by_csv(graphs_by_csv)
    return scene, drawn, cleared


def _check_all_datasets(scene: GraphViewerScene) -> None:
    for row in range(scene.overlay_list.count()):
        scene.overlay_list.item(row).setCheckState(Qt.Checked)


def test_overlay_lists_every_dataset_and_keeps_other_tabs(qt_app, monkeypatch):
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure()},
            "/data/fish_b.csv": {"Tail Angle": _line_figure()},
        },
    )

    labels = [scene.overlay_list.item(i).text() for i in range(scene.overlay_list.count())]
    assert labels == ["fish_a.csv", "fish_b.csv"]
    assert scene.tab_widget.isTabEnabled(scene.TAB_OVERLAY)
    assert scene.tab_widget.isTabEnabled(scene.TAB_COMPARE)
    assert scene.list.count() == 1  # Graphs tab still lists the selected file's graphs
    assert drawn == []  # nothing is drawn until datasets are checked


def test_overlay_draws_checked_datasets_on_one_figure(qt_app, monkeypatch):
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure()},
            "/data/fish_b.csv": {"Tail Angle": _line_figure()},
        },
    )

    _check_all_datasets(scene)

    assert len(drawn) == 1
    combined = drawn[0]
    assert [trace.name for trace in combined.data] == ["fish_a.csv", "fish_b.csv"]
    assert len({trace.line.color for trace in combined.data}) == 2
    assert combined.layout.showlegend is True
    assert combined.layout.title.text == "Tail Angle (overlay)"


def test_overlay_shares_axes_and_ignores_fixed_ranges(qt_app, monkeypatch):
    narrow = _line_figure()
    narrow.update_layout(xaxis_range=[0, 1])
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": narrow},
            "/data/fish_b.csv": {"Tail Angle": _line_figure()},
        },
    )

    _check_all_datasets(scene)

    combined = drawn[-1]
    assert combined.layout.xaxis.title.text == "Frame"
    assert combined.layout.yaxis.title.text == "Angle (deg)"
    assert combined.layout.xaxis.autorange is True
    assert combined.layout.xaxis.range is None


def test_overlay_prefixes_each_trace_with_its_dataset(qt_app, monkeypatch):
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Fins": _line_figure("Left", "Right")},
            "/data/fish_b.csv": {"Fins": _line_figure("Left", "Right")},
        },
    )

    _check_all_datasets(scene)

    combined = drawn[-1]
    assert [trace.name for trace in combined.data] == [
        "fish_a.csv - Left",
        "fish_a.csv - Right",
        "fish_b.csv - Left",
        "fish_b.csv - Right",
    ]
    assert {trace.legendgroup for trace in combined.data} == {"fish_a.csv", "fish_b.csv"}


def test_overlay_does_not_modify_source_figures(qt_app, monkeypatch):
    fig_a = _line_figure("Left")
    fig_b = _line_figure("Left")
    snapshot = [fig_a.to_dict(), fig_b.to_dict()]
    scene, _, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": fig_a},
            "/data/fish_b.csv": {"Tail Angle": fig_b},
        },
    )

    _check_all_datasets(scene)

    assert [fig_a.to_dict(), fig_b.to_dict()] == snapshot


def test_overlay_requires_two_checked_datasets(qt_app, monkeypatch):
    scene, drawn, cleared = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure()},
            "/data/fish_b.csv": {"Tail Angle": _line_figure()},
        },
    )

    scene.overlay_list.item(0).setCheckState(Qt.Checked)
    assert drawn == []
    assert scene.overlay_status.text() == "Check at least two datasets to overlay."

    scene.overlay_list.item(1).setCheckState(Qt.Checked)
    assert len(drawn) == 1

    cleared_before = len(cleared)
    scene.overlay_list.item(1).setCheckState(Qt.Unchecked)
    assert len(cleared) > cleared_before
    assert scene.overlay_status.text() == "Check at least two datasets to overlay."


def test_overlay_with_a_single_dataset_draws_nothing(qt_app, monkeypatch):
    scene, drawn, _ = _overlay_scene(
        monkeypatch, {"/data/fish_a.csv": {"Tail Angle": _line_figure()}}
    )

    _check_all_datasets(scene)

    assert drawn == []
    assert scene.overlay_status.text() == "Check at least two datasets to overlay."


def test_overlay_reports_datasets_without_a_common_graph(qt_app, monkeypatch):
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure()},
            "/data/fish_b.csv": {"Head Yaw": _line_figure()},
        },
    )

    _check_all_datasets(scene)

    assert scene.overlay_graph.count() == 0
    assert scene.overlay_status.text() == "These datasets do not share a graph."
    assert drawn == []


def test_overlay_handles_static_image_graphs_without_crashing(qt_app, monkeypatch, tmp_path):
    png_path = tmp_path / "tail.png"
    QPixmap(10, 10).save(str(png_path))
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure()},
            "/data/fish_b.csv": {"Tail Angle": str(png_path)},
        },
    )

    _check_all_datasets(scene)

    assert drawn == []
    status = scene.overlay_status.text()
    assert "static image" in status
    assert "fish_b.csv" in status


def test_overlay_skips_static_images_and_draws_the_rest(qt_app, monkeypatch, tmp_path):
    png_path = tmp_path / "tail.png"
    QPixmap(10, 10).save(str(png_path))
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure()},
            "/data/fish_b.csv": {"Tail Angle": _line_figure()},
            "/data/fish_c.csv": {"Tail Angle": str(png_path)},
        },
    )

    _check_all_datasets(scene)

    combined = drawn[-1]
    assert [trace.name for trace in combined.data] == ["fish_a.csv", "fish_b.csv"]
    assert scene.overlay_status.text() == "Skipped (no interactive graph): fish_c.csv."


def test_overlay_redraws_when_another_graph_is_selected(qt_app, monkeypatch):
    scene, drawn, _ = _overlay_scene(
        monkeypatch,
        {
            "/data/fish_a.csv": {"Tail Angle": _line_figure(), "Head Yaw": _line_figure()},
            "/data/fish_b.csv": {"Tail Angle": _line_figure(), "Head Yaw": _line_figure()},
        },
    )
    _check_all_datasets(scene)

    scene.overlay_graph.setCurrentIndex(scene.overlay_graph.findData("Head Yaw"))

    assert drawn[-1].layout.title.text == "Head Yaw (overlay)"
