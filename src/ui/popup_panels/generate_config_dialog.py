"""Modal Generate Config (spec: popup outside current session chrome)."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from session.session import Session
from styles.themes import THEMES, apply_theme
from styles.ui_scale import scaled_px

from ui.components.chrome_separators import horizontal_separator
from ui.components.dialog_title_bar import DialogTitleBar

from ui.platform.frameless_resize import FramelessResizeMixin
from .config_generator_widget import ConfigGeneratorScene


class GenerateConfigDialog(FramelessResizeMixin, QDialog):
    """Window-modal to main shell; on **Accept** (after successful **config_generated**), caller refreshes session + UI."""

    def __init__(
        self,
        parent: QWidget | None,
        session: Session,
        *,
        prefill_csv_path: str | None = None,
        prefill_json_path: str | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("GenerateConfigDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        # WindowModal: blocks parent (main shell) only so ErrorToast (separate top-level) stays clickable.
        self.setWindowModality(Qt.WindowModal)

        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr is not None else None
        max_h = int(geo.height() * 0.92) if geo is not None else 1200
        max_w = int(geo.width() * 0.98) if geo is not None else 2000
        self.setMinimumSize(max(scaled_px(880), 640), max(scaled_px(520), 400))
        self.setMaximumHeight(max_h)
        self.setMaximumWidth(max_w)
        rw = min(max(scaled_px(960), 720), max_w)
        rh = min(max(scaled_px(640), 480), max_h)
        self.resize(rw, rh)

        theme_name = "dark"
        p = parent
        while p is not None:
            if hasattr(p, "current_theme"):
                theme_name = getattr(p, "current_theme", "dark") or "dark"
                break
            p = p.parentWidget()
        apply_theme(self, THEMES[theme_name])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._title_bar = DialogTitleBar(
            self,
            "Generate Config",
            self,
            help_title="Generate Config",
            help_paragraph=(
                "Click through the tabs to set body points, video scale, and graph options, then save so the new JSON is part of the current session. "
                "Select & Run will use that file after you finish. "
                "Scroll the window to reach every section."
            ),
            help_tips=(
                "If the app opened this dialog with a path, some fields may already be filled from that file.",
            ),
        )
        outer.addWidget(self._title_bar)
        outer.addWidget(horizontal_separator())

        body = QWidget()
        body.setObjectName("GenerateConfigBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(scaled_px(10), scaled_px(10), scaled_px(10), scaled_px(10))
        bl.setSpacing(0)

        self.generator = ConfigGeneratorScene()
        self.generator.load_session(session)
        if prefill_csv_path:
            self.generator.prefill_from_copy(prefill_csv_path, prefill_json_path)
        self.generator.config_generated.connect(self.accept)
        shell = parent
        while shell is not None and not hasattr(shell, "_show_error_toast"):
            shell = shell.parentWidget()
        if shell is not None:
            self.generator.toast_requested.connect(shell._show_error_toast)
        bl.addWidget(self.generator, stretch=1)

        scroll = QScrollArea()
        scroll.setObjectName("GenerateConfigDialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(body)

        outer.addWidget(scroll, stretch=1)
