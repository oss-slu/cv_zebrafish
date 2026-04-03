from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QStyle, QToolButton, QVBoxLayout, QWidget


class SidebarTools(QWidget):
    """
    Minimal vertical tool strip: flat icons on chrome background; hover outline + tooltip text.
    """

    tool_triggered = pyqtSignal(str)
    theme_toggle_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarToolsInner")
        self.setFixedWidth(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(6)

        spec = [
            ("verify", QStyle.SP_DialogOpenButton, "Verify Upload"),
            ("generate", QStyle.SP_FileDialogDetailedView, "Generate Config"),
            ("select_run", QStyle.SP_MediaPlay, "Select & Run"),
            ("view_output", QStyle.SP_FileDialogInfoView, "View Output"),
        ]
        self._main_buttons: list[QToolButton] = []
        self._buttons_by_key: dict[str, QToolButton] = {}
        for key, std_icon, tip in spec:
            btn = QToolButton()
            btn.setObjectName("SidebarTool")
            btn.setProperty("toolKey", key)
            btn.setIcon(self.style().standardIcon(std_icon))
            btn.setIconSize(QSize(26, 26))
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.clicked.connect(lambda _=False, k=key: self.tool_triggered.emit(k))
            layout.addWidget(btn, 0, Qt.AlignHCenter)
            self._main_buttons.append(btn)
            self._buttons_by_key[key] = btn

        layout.addStretch(1)

        self._theme_btn = QToolButton()
        self._theme_btn.setObjectName("SidebarTool")
        self._theme_btn.setText("☾")
        self._theme_btn.setToolTip("Dark / Light")
        self._theme_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        self._theme_btn.setAutoRaise(True)
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        layout.addWidget(self._theme_btn, 0, Qt.AlignHCenter)

    def set_session_active(self, active: bool) -> None:
        for btn in self._main_buttons:
            btn.setEnabled(active)

    def apply_session_capabilities(
        self,
        has_session: bool,
        has_csv: bool,
        calculation_has_run: bool,
    ) -> None:
        """
        has_session: any session loaded.
        has_csv: session has at least one CSV (or folder) registered.
        calculation_has_run: at least one successful run (enables View Output).
        """
        v = self._buttons_by_key.get("verify")
        g = self._buttons_by_key.get("generate")
        s = self._buttons_by_key.get("select_run")
        o = self._buttons_by_key.get("view_output")
        if not has_session:
            for b in (v, g, s, o):
                if b is not None:
                    b.setEnabled(False)
            return
        if v:
            v.setEnabled(True)
        if g:
            g.setEnabled(has_csv)
        if s:
            s.setEnabled(has_csv)
        if o:
            o.setEnabled(has_csv and calculation_has_run)

    def reflect_theme(self, theme_name: str) -> None:
        self._theme_btn.setText("☀" if theme_name == "dark" else "☾")
        for btn in self._main_buttons:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
