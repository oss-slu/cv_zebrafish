"""Smoke tests for BodypartLabelList optional chrome."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_clear_all_button_optional(qapp):
    from ui.components.pose.bodypart_label_list import BodypartLabelList

    panel = BodypartLabelList()
    assert not panel._clear_all_btn.isVisible()

    hits: list[int] = []
    panel.clear_all_requested.connect(lambda: hits.append(1))
    panel.set_clear_all_visible(True)
    panel._clear_all_btn.click()
    assert hits == [1]
    panel.close()
