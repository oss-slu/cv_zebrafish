import subprocess
import sys
from pathlib import Path

import pandas as pd

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