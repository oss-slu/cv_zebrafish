"""Tests for graph_builder helpers."""

import pandas as pd

from core.graphs.graph_builder import get_graph_names_to_build


def test_get_graph_names_empty_payload():
    assert get_graph_names_to_build(None) == []
    assert get_graph_names_to_build({}) == []


def test_get_graph_names_dot_plot_when_enabled():
    df = pd.DataFrame({"Tail_Distance": [1.0], "LF_Angle": [2.0]})
    config = {
        "shown_outputs": {"show_tail_left_fin_angle_dot_plot": True},
        "video_parameters": {"recorded_framerate": 30},
    }
    names = get_graph_names_to_build(
        {"results_df": df, "config": config, "parsed_points": {}}
    )
    assert "Tail Distance vs Left Fin Angle" in names
