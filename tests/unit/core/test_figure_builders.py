import subprocess
import sys
from pathlib import Path

import pandas as pd

import pytest

from src.core.graphs.figure_builders import (
    DOT_PLOT_SPECS,
    _extract_time_ranges,
    _iter_custom_angle_graphs,
    build_graphs_from_data,
    build_spine_graphs,
)

from src.core.graphs.figure_builders import (
    build_dot_plot_graphs,
    build_fin_tail_graphs,
    build_head_plot_graphs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_module_imports_without_pyqt():
    probe = (
        "import sys; import src.core.graphs.figure_builders; "
        "print('PyQt5' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "False"


def test_empty_dataframe_gives_warning_not_graphs():
    graphs, warnings = build_dot_plot_graphs(pd.DataFrame(), {})
    assert graphs == {}
    assert any("empty" in warning for warning in warnings)


def test_fin_tail_graphs_skipped_when_flag_is_off():
    graphs, warnings = build_fin_tail_graphs(pd.DataFrame({"LF_Angle": [1.0]}), {})
    assert graphs == {} and warnings == []


def test_head_plot_skipped_when_flag_is_off():
    graphs, warnings = build_head_plot_graphs(pd.DataFrame({"HeadYaw": [1.0]}), {})
    assert graphs == {} and warnings == []

def test_dot_plots_warn_when_no_flag_is_enabled():
    frame = pd.DataFrame({"Time": [0, 1]})
    graphs, warnings = build_dot_plot_graphs(frame, {"shown_outputs": {}})
    assert graphs == {}
    assert warnings == ["No dot plot flags are enabled in the config."]


def test_dot_plots_skip_specs_with_missing_columns():
    spec = DOT_PLOT_SPECS[0]
    config = {"shown_outputs": {spec["flag"]: True}}
    graphs, warnings = build_dot_plot_graphs(pd.DataFrame({"Time": [0, 1]}), config)
    assert graphs == {}
    assert any(spec["title"] in warning and "missing" in warning for warning in warnings)


def test_fin_tail_skipped_without_required_columns():
    config = {"shown_outputs": {"show_angle_and_distance_plot": True}}
    graphs, warnings = build_fin_tail_graphs(pd.DataFrame({"LF_Angle": [1.0, 2.0]}), config)
    assert graphs == {}
    assert any("Fin/tail plot skipped" in warning for warning in warnings)


def test_spine_graphs_skipped_without_parsed_points():
    frame = pd.DataFrame({"LF_Angle": [1.0], "RF_Angle": [2.0]})
    graphs, warnings = build_spine_graphs(frame, {"shown_outputs": {"show_spines": True}}, None)
    assert graphs == {}
    assert any("parsed point coordinates are unavailable" in warning for warning in warnings)


def test_head_plot_skipped_without_head_yaw():
    config = {"shown_outputs": {"show_head_plot": True}}
    graphs, warnings = build_head_plot_graphs(pd.DataFrame({"Time": [0]}), config)
    assert graphs == {}
    assert warnings == ["Head plot skipped: missing HeadYaw column."]


CUSTOM_ANGLE_CONFIG = {
    "custom_calculations": {
        "three_point_angle": {"enabled": True, "output_column": "Angle3"}
    }
}


def test_custom_angle_graph_is_built_from_the_output_column():
    warnings = []
    frame = pd.DataFrame({"Angle3": [10.0, 20.0, 30.0]})
    results = list(_iter_custom_angle_graphs(frame, CUSTOM_ANGLE_CONFIG, warnings))
    assert [name for name, _ in results] == ["Custom Angle: Angle3"]
    assert list(results[0][1].data[0].y) == [10.0, 20.0, 30.0]
    assert warnings == []


def test_custom_angle_graph_warns_when_column_is_missing():
    warnings = []
    results = list(_iter_custom_angle_graphs(pd.DataFrame({"Time": [0]}), CUSTOM_ANGLE_CONFIG, warnings))
    assert results == []
    assert warnings == ["Custom angle enabled but column missing: Angle3"]


def test_custom_angle_graph_is_skipped_when_disabled():
    warnings = []
    results = list(_iter_custom_angle_graphs(pd.DataFrame({"Angle3": [1.0]}), {}, warnings))
    assert results == [] and warnings == []


def test_time_ranges_from_config_take_priority():
    config = {"time_ranges": [[2, 5], [7, 9]]}
    assert _extract_time_ranges(config, pd.DataFrame({"a": [1, 2, 3]})) == [[2, 5], [7, 9]]


def test_time_ranges_are_read_from_result_columns_and_reordered():
    frame = pd.DataFrame(
        {
            "timeRangeStart_0": [20, None, None],
            "timeRangeEnd_0": [10, None, None],
        }
    )
    assert _extract_time_ranges({}, frame) == [[10, 20]]


def test_time_ranges_fall_back_to_the_whole_recording():
    assert _extract_time_ranges({}, pd.DataFrame({"a": [1, 2, 3]})) == [[0, 2]]
    assert _extract_time_ranges({}, pd.DataFrame()) == []


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"results_df": "not a frame", "config": {}}, {"results_df": pd.DataFrame(), "config": None}],
)
def test_build_graphs_from_data_rejects_invalid_payloads(payload):
    assert build_graphs_from_data(payload, lambda *args: None) == (None, None)