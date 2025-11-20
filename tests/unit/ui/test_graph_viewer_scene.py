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
    payload = {"results_df": df, "config": config, "csv_path": "demo.csv"}

    scene.set_data(payload)

    assert len(scene._graphs) == 2
    assert "Tail Distance vs Left Fin Angle" in scene._graphs
    assert "Tail Distance vs Left Fin Angle (Moving)" in scene._graphs
