"""The analysis core must stay importable without PyQt (web-readiness, #133)."""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

CORE_MODULES = [
    "src.core.input_source",
    "src.core.validation.csv_verifier",
    "src.core.graphs.data_loader",
    "src.core.graphs.figure_builders",
    "src.core.comparison.fish_data",
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_module_imports_without_pyqt(module_name):
    probe = (
        f"import sys, importlib; importlib.import_module({module_name!r}); "
        "print(any(name.startswith('PyQt') for name in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "False"