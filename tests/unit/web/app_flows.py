"""Click-through tests for the web prototype page (spike #136).

Not collected directly (the file name doesn't start with ``test_``): ``test_web_app.py``
runs this file in a separate Python process. See the note there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[3] / "web_prototype" / "app.py")


def _app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click()
    return at.run()


def test_starts_on_species_page_with_zebrafish_default():
    at = _app()
    assert not at.exception
    assert at.session_state.page == "species"
    assert at.selectbox[0].options == ["Zebrafish", "Mouse"]
    assert at.selectbox[0].value == "Zebrafish"


def test_zebrafish_sample_flow_reaches_results_and_back():
    at = _click(_app(), "Continue")
    assert at.session_state.page == "zebrafish_load"

    at = _click(at, "Use the bundled sample file")
    assert not at.exception
    assert at.session_state.page == "zebrafish_results"
    assert any("5,351 frames" in c.value for c in at.caption)
    assert len(at.dataframe) >= 1

    at = _click(at, "Load another file")
    assert at.session_state.page == "zebrafish_load"
    at = _click(at, "Back")
    assert at.session_state.page == "species"
    assert "species" not in at.session_state


def test_mouse_goes_to_mouse_load_and_back():
    at = _app()
    at.selectbox[0].set_value("Mouse").run()
    at = _click(at, "Continue")
    assert not at.exception
    assert at.session_state.page == "mouse_load"
    assert at.session_state.species == "Mouse"

    at = _click(at, "Back")
    assert at.session_state.page == "species"
