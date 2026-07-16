"""Semi-transparent loading panel that blocks interaction without a wait cursor."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    """Cover a parent widget while background work runs on other threads."""

    def __init__(self, parent: QWidget, *, title: str = "Loading"):
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._title = title
        self._dots = 0
        self._dots_timer = QTimer(self)
        self._dots_timer.timeout.connect(self._tick_dots)
        self._cursor_depth = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)
        self._label = QLabel(title)
        self._label.setObjectName("LoadingOverlayLabel")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setObjectName("LoadingOverlayBar")
        self._bar.setTextVisible(False)
        self._bar.setRange(0, 0)
        self._bar.hide()
        layout.addWidget(self._bar)
        layout.addStretch(1)
        self.hide()

    def set_message(self, message: str) -> None:
        self._title = message.rstrip(".")
        self._dots = 0
        self._label.setText(self._title)

    def set_indeterminate(self, active: bool = True) -> None:
        if active:
            self._bar.setRange(0, 0)
            self._bar.show()
        else:
            self._bar.hide()
            self._bar.setRange(0, 100)
            self._bar.setValue(0)

    def set_progress(self, current: int, total: int, *, message: str | None = None) -> None:
        if message is not None:
            self.set_message(message)
        if total <= 0:
            self.set_indeterminate(True)
            return
        self._bar.setRange(0, total)
        self._bar.setValue(min(max(0, current), total))
        self._bar.setFormat(f"%v / %m")
        self._bar.setTextVisible(True)
        self._bar.show()

    def show_loading(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._push_arrow_cursor()
        self._dots_timer.start(400)
        self._tick_dots()

    def hide_loading(self) -> None:
        self._dots_timer.stop()
        self._pop_arrow_cursor()
        self.hide()
        self.set_indeterminate(False)

    def resize_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def _tick_dots(self) -> None:
        self._dots = (self._dots + 1) % 4
        self._label.setText(self._title + "." * self._dots)

    def _push_arrow_cursor(self) -> None:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        if self._cursor_depth == 0:
            app.setOverrideCursor(Qt.ArrowCursor)
        self._cursor_depth += 1

    def _pop_arrow_cursor(self) -> None:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None or self._cursor_depth <= 0:
            return
        self._cursor_depth -= 1
        if self._cursor_depth == 0:
            app.restoreOverrideCursor()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resize_to_parent()
