"""Show full text in a tooltip when labels, fields, or buttons clip or elide it."""

from __future__ import annotations

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import QLabel, QLineEdit, QPushButton, QWidget


class LineEditResizeTooltipFilter(QObject):
    """Refresh path tooltips when a ``QLineEdit`` is resized or shown."""

    def __init__(self, refresh):
        super().__init__()
        self._refresh = refresh

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self._refresh()
        return False


def _available_width(widget: QWidget) -> int:
    w = widget.width()
    if isinstance(widget, QLineEdit):
        m = widget.textMargins()
        w -= m.left() + m.right() + 10
    elif isinstance(widget, QPushButton):
        w -= 20
    else:
        w -= 8
    return max(32, w)


def text_is_clipped(widget: QWidget, text: str) -> bool:
    text = text or ""
    if not text:
        return False
    return widget.fontMetrics().horizontalAdvance(text) > _available_width(widget)


def update_line_edit_elide_tooltip(line_edit: QLineEdit) -> None:
    """Tooltip shows the full path or the full placeholder when the control clips it."""
    text = line_edit.text()
    display = text if text else (line_edit.placeholderText() or "")
    if not display:
        line_edit.setToolTip("")
        return
    if text_is_clipped(line_edit, display):
        line_edit.setToolTip(display)
    else:
        line_edit.setToolTip("")


def update_pushbutton_elide_tooltip(button: QPushButton) -> None:
    label = button.text() or ""
    if not label:
        button.setToolTip("")
        return
    if text_is_clipped(button, label):
        button.setToolTip(label)
    else:
        button.setToolTip("")


def update_label_elide_tooltip(
    label: QLabel,
    full_text: str,
    elide_mode: Qt.TextElideMode,
    *,
    elide_width: int | None = None,
) -> None:
    """Use when the label text is set via ``QFontMetrics.elidedText``."""
    full_text = full_text or ""
    if not full_text:
        label.setToolTip("")
        return
    w = elide_width if elide_width is not None else max(32, label.width() - 4)
    elided = label.fontMetrics().elidedText(full_text, elide_mode, w)
    if elided != full_text:
        label.setToolTip(full_text)
    else:
        label.setToolTip("")
