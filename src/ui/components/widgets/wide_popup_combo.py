"""QComboBox whose drop-down list widens to show full item text (no horizontal ellipses)."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox

from styles.ui_scale import scaled_px


class WidePopupComboBox(QComboBox):
    def showPopup(self) -> None:
        if self.count() == 0:
            super().showPopup()
            return
        view = self.view()
        view.setTextElideMode(Qt.ElideNone)
        fm = self.fontMetrics()
        widest = self.width()
        for i in range(self.count()):
            t = self.itemText(i)
            if t:
                widest = max(widest, fm.size(Qt.TextSingleLine, t).width())
        pad = scaled_px(36)
        win = self.window()
        scr = win.screen() if win is not None else None
        if scr is not None:
            widest = min(widest + pad, int(scr.availableGeometry().width() * 0.92))
        else:
            widest = widest + pad
        view.setMinimumWidth(max(self.width(), widest))
        super().showPopup()
