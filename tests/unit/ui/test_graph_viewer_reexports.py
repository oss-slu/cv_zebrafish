"""Other modules import graph builders from the Graph Viewer widget; keep that working."""

import pytest

from src.core.graphs import figure_builders
from ui.main_panels import graph_viewer_widget

RE_EXPORTED_NAMES = [
    "GraphSource",
    "build_dot_plot_graphs",
    "build_fin_tail_graphs",
    "build_graphs_from_data",
    "build_head_plot_graphs",
    "build_spine_graphs",
    "get_graph_names_to_build",
]


@pytest.mark.parametrize("name", RE_EXPORTED_NAMES)
def test_widget_re_exports_the_core_implementation(name):
    assert getattr(graph_viewer_widget, name) is getattr(figure_builders, name)