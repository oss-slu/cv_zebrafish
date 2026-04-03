"""Modal Generate Config: embeds legacy ConfigGeneratorScene (spec: popup outside current session chrome)."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QWidget

from session.session import Session
from styles.themes import THEMES, apply_theme

from ui.components.chrome_separators import horizontal_separator
from ui.components.dialog_title_bar import DialogTitleBar
from ui.scenes.ConfigGeneratorScene import ConfigGeneratorScene


class GenerateConfigDialog(QDialog):
    """Application-modal; on **Accept** (after successful **config_generated**), caller refreshes session + UI."""

    def __init__(self, parent: QWidget | None, session: Session):
        super().__init__(parent)
        self.setObjectName("GenerateConfigDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumSize(880, 620)
        self.resize(960, 720)

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

        self._title_bar = DialogTitleBar(self, "Generate Config", self)
        outer.addWidget(self._title_bar)
        outer.addWidget(horizontal_separator())

        body = QWidget()
        body.setObjectName("GenerateConfigBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.setSpacing(0)

        self.generator = ConfigGeneratorScene()
        self.generator.load_session(session)
        self.generator.config_generated.connect(self.accept)
        bl.addWidget(self.generator, stretch=1)

        outer.addWidget(body, stretch=1)
