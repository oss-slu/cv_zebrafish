"""Click-through tests for the web app page.

Not collected directly (the file name doesn't start with ``test_``): ``test_web_app.py``
runs this file in a separate Python process. See the note there.
"""

from __future__ import annotations

from pathlib import Path

import importlib.util

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
APP = str(REPO_ROOT / "web_prototype" / "app.py")


def _app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click()
    return at.run()


def test_starts_on_species_page_with_zebrafish_default():
    at = _app()
    assert not at.exception
    assert at.session_state.page == "species"
    assert at.selectbox[0].options == ["Zebrafish", "Mouse (coming soon)"]
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


def test_mouse_is_coming_soon_and_cannot_continue():
    at = _app()
    at.selectbox[0].set_value("Mouse").run()
    assert not at.exception
    assert next(b for b in at.button if b.label == "Continue").disabled
    assert any("coming soon" in c.value for c in at.caption)
    assert at.session_state.page == "species"


def test_hidden_mouse_pages_still_render_and_go_back():
    # Unreachable while MOUSE_READY is False; kept working for when mouse analysis lands.
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = "mouse_load"
    at.session_state["species"] = "Mouse"
    at = at.run()
    assert not at.exception

    at = _click(at, "Back")
    assert at.session_state.page == "species"


def test_footer_shows_build_sha_only_in_built_site(tmp_path):
    assert not any('class="cvz-footer"' in m.value for m in _app().markdown)

    spec = importlib.util.spec_from_file_location("build_static", REPO_ROOT / "web_prototype" / "build_static.py")
    build_static = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_static)
    sha = "0123456789abcdef0123456789abcdef01234567"
    build_static.build(tmp_path / "site", sha=sha)

    at = AppTest.from_file(str(tmp_path / "site" / "web_prototype" / "app.py"), default_timeout=60).run()
    assert not at.exception
    footer = next(m.value for m in at.markdown if 'class="cvz-footer"' in m.value)
    assert f"/commit/{sha}" in footer and ">0123456<" in footer
