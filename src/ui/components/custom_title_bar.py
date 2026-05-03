"""Frameless title row: logo | File | (optional Help) | … | window controls (inline menus, no QMenuBar overflow)."""

from __future__ import annotations

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QHBoxLayout, QMainWindow, QMenu, QToolButton, QWidget

from styles.ui_scale import scaled_px
from ui.components.branding import title_bar_logo_label


class CustomTitleBar(QWidget):
    def __init__(
        self,
        main_window: QMainWindow,
        file_menu: QMenu,
        help_menu: QMenu | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("AppTitleBar")
        # Required or Qt ignores stylesheet background on QWidget → bar looked same as main panel.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._win = main_window
        self._drag_anchor: QPoint | None = None

        layout = QHBoxLayout(self)
        m = scaled_px(10)
        mv = scaled_px(8)
        layout.setContentsMargins(m, mv, scaled_px(8), mv)
        layout.setSpacing(scaled_px(4))

        logo_side = scaled_px(34)
        self._logo = title_bar_logo_label(logo_side)
        layout.addWidget(self._logo, 0, Qt.AlignVCenter)

        layout.addSpacing(scaled_px(8))

        self._file_btn = self._strip_menu_button("File", file_menu)
        layout.addWidget(self._file_btn, 0, Qt.AlignVCenter)

        if help_menu is not None:
            self._help_btn = self._strip_menu_button("Help", help_menu)
            layout.addWidget(self._help_btn, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        self._btn_min = self._text_chrome_btn("\u2212")
        self._btn_min.setObjectName("TitleChromeButton")
        self._btn_min.clicked.connect(self._win.showMinimized)

        # Hollow square (U+25A1); QSS uses [maxGlyph="hollow"] for slightly smaller symbol font.
        self._btn_max = self._text_chrome_btn("\u25a1")
        self._btn_max.setObjectName("TitleChromeMaximize")
        self._btn_max.setProperty("maxGlyph", "hollow")
        self._btn_max.clicked.connect(self._toggle_max)

        self._btn_close = self._text_chrome_btn("\u00d7")
        self._btn_close.setObjectName("TitleChromeClose")
        self._btn_close.clicked.connect(self._win.close)

        layout.addWidget(self._btn_min, 0, Qt.AlignVCenter)
        layout.addWidget(self._btn_max, 0, Qt.AlignVCenter)
        layout.addWidget(self._btn_close, 0, Qt.AlignVCenter)

        self._btn_max.style().unpolish(self._btn_max)
        self._btn_max.style().polish(self._btn_max)

        # Match scaled QSS on TitleMenuButton (font + padding); fixed 54px clipped when UI scale > 1.
        self.setFixedHeight(max(scaled_px(58), logo_side + scaled_px(24)))

    def _strip_menu_button(self, label: str, menu: QMenu) -> QToolButton:
        b = QToolButton()
        b.setObjectName("TitleMenuButton")
        b.setText(label)
        b.setMenu(menu)
        b.setPopupMode(QToolButton.InstantPopup)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _text_chrome_btn(self, text: str) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setAutoRaise(True)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        side = scaled_px(54)
        tall = scaled_px(42)
        b.setFixedSize(side, tall)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _toggle_max(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self.update_max_button()

    def update_max_button(self) -> None:
        if self._win.isMaximized():
            self._btn_max.setText("\u29c9")
            self._btn_max.setProperty("maxGlyph", "restore")
        else:
            self._btn_max.setText("\u25a1")
            self._btn_max.setProperty("maxGlyph", "hollow")
        self._btn_max.style().unpolish(self._btn_max)
        self._btn_max.style().polish(self._btn_max)

    def _allow_window_drag(self, pos) -> bool:
        w = self.childAt(pos)
        cur = w
        while cur is not None and cur != self:
            if isinstance(cur, QToolButton):
                return False
            cur = cur.parentWidget()
        return True

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and self._allow_window_drag(event.pos())
        ):
            self._drag_anchor = event.globalPos() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_anchor is not None:
            # Dragging while maximized: restore to last normal geometry, then follow cursor.
            if self._win.isMaximized():
                self._win.showNormal()
            self._win.move(event.globalPos() - self._drag_anchor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_anchor = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._allow_window_drag(event.pos()):
            self._toggle_max()
        super().mouseDoubleClickEvent(event)
