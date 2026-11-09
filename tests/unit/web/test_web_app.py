"""Runs the web prototype click-through tests (``app_flows.py``) in their own process.

Streamlit's test runner in the same process as the Qt/Plotly tests intermittently
crashed Python with a bus error, so the flows run in a fresh interpreter. Skipped when
Streamlit isn't installed (it's only in web_prototype/requirements.txt).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

if importlib.util.find_spec("streamlit") is None:  # checks without importing it
    pytest.skip("streamlit not installed", allow_module_level=True)

FLOWS = Path(__file__).with_name("app_flows.py")


def test_app_flows_in_separate_process():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(FLOWS)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert " passed" in proc.stdout
