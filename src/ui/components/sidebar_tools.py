from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QStyle, QToolButton, QVBoxLayout, QWidget

from app_platform.paths import images_dir


class SidebarTools(QWidget):
    """
    Vertical tool strip: SVG icons per theme and enabled state.

    Assets: ``assets/images/sidebar_{key}_{dark|light}_{active|inactive}.svg``
    — active = full contrast; inactive (disabled) = stroke/fill closer to chrome.
    """

    tool_triggered = pyqtSignal(str)
    theme_toggle_requested = pyqtSignal()

    _FALLBACK_STD = {
        "verify": QStyle.SP_DialogOpenButton,
        "generate": QStyle.SP_FileDialogDetailedView,
        "select_run": QStyle.SP_MediaPlay,
        "view_output": QStyle.SP_FileDialogInfoView,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarToolsInner")
        self.setFixedWidth(84)
        self._theme_name = "dark"
        self._active_key: str | None = None
        self._cap_has_session = False
        self._cap_has_csv = False
        self._cap_view_output = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(6)

        spec = [
            ("verify", "Verify Upload"),
            ("generate", "Generate Config"),
            ("select_run", "Select & Run"),
            ("view_output", "View Output"),
        ]
        self._main_buttons: list[QToolButton] = []
        self._buttons_by_key: dict[str, QToolButton] = {}
        for key, tip in spec:
            btn = QToolButton()
            btn.setObjectName("SidebarTool")
            btn.setProperty("toolKey", key)
            btn.setIconSize(QSize(34, 34))
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setAutoRaise(True)
            btn.setMinimumSize(QSize(46, 46))
            btn.clicked.connect(lambda _checked=False, k=key: self.tool_triggered.emit(k))
            layout.addWidget(btn, 0, Qt.AlignHCenter)
            self._main_buttons.append(btn)
            self._buttons_by_key[key] = btn

        self._apply_tool_icons()

        layout.addStretch(1)

        self._theme_btn = QToolButton()
        self._theme_btn.setObjectName("SidebarTool")
        self._theme_btn.setText("☀")
        self._theme_btn.setToolTip("Dark / Light")
        self._theme_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        self._theme_btn.setAutoRaise(True)
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        layout.addWidget(self._theme_btn, 0, Qt.AlignHCenter)

    def _sidebar_svg_icon(self, key: str, enabled: bool) -> QIcon | None:
        theme = self._theme_name
        state = "active" if enabled else "inactive"
        p = images_dir() / f"sidebar_{key}_{theme}_{state}.svg"
        if p.is_file():
            return QIcon(str(p))
        # Legacy two-name fallback (active only)
        leg = images_dir() / f"sidebar_{key}_{theme}.svg"
        if leg.is_file():
            return QIcon(str(leg))
        return None

    def _icon_logically_active(self, key: str) -> bool:
        """Visual / affordance: inactive icon when the shell will block that tool."""
        if not self._cap_has_session:
            return False
        if key == "verify":
            return True
        if key in ("generate", "select_run"):
            return self._cap_has_csv
        if key == "view_output":
            return self._cap_view_output
        return False

    def _apply_tool_icons(self) -> None:
        st = self.style()
        for key, btn in self._buttons_by_key.items():
            active = self._icon_logically_active(key)
            ic = self._sidebar_svg_icon(key, active)
            if ic is None or ic.isNull():
                ic = st.standardIcon(self._FALLBACK_STD[key])
            btn.setIcon(ic)
            btn.setProperty("sidebarMuted", "true" if not active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def apply_session_capabilities(
        self,
        has_session: bool,
        has_csv: bool,
        calculation_has_run: bool,
        *,
        view_output_enabled: bool = False,
    ) -> None:
        """
        Stores capability flags for icon styling. Buttons stay enabled so clicks can
        show prerequisite toasts; the shell enforces gating.
        """
        self._cap_has_session = bool(has_session)
        self._cap_has_csv = bool(has_csv)
        self._cap_view_output = bool(view_output_enabled)
        for btn in self._main_buttons:
            btn.setEnabled(True)
        self._apply_tool_icons()

    def set_active_tool(self, key: str | None) -> None:
        """Highlight the main-panel tool matching the workspace (None = no highlight)."""
        self._active_key = key
        for k, btn in self._buttons_by_key.items():
            is_active = key is not None and k == key
            btn.setProperty("activeTool", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def reflect_theme(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self._apply_tool_icons()
        self._theme_btn.setText("☀" if theme_name == "dark" else "☾")
        for btn in self._main_buttons:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.set_active_tool(self._active_key)
        self._theme_btn.style().unpolish(self._theme_btn)
        self._theme_btn.style().polish(self._theme_btn)
