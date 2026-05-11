"""Application settings: theme and interface scale (machine-local prefs)."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app_platform.ui_preferences import (
    PRESET_LABELS,
    UiPreferences,
    dpi_auto_multiplier,
    save_ui_preferences,
)
from styles.themes import THEMES, apply_theme
from styles.ui_scale import scaled_px

from ui.components.chrome_separators import horizontal_separator
from ui.components.dialog_title_bar import DialogTitleBar
from ui.platform.frameless_resize import FramelessResizeMixin


class SettingsDialog(FramelessResizeMixin, QDialog):
    """Theme and interface scale; each change is saved immediately."""

    def __init__(self, parent: QWidget | None, prefs: UiPreferences):
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)

        self._prefs_in = prefs

        theme_name = prefs.theme if prefs.theme in THEMES else "dark"
        apply_theme(self, THEMES[theme_name])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(DialogTitleBar(self, "Settings", self))

        outer.addWidget(horizontal_separator())

        body = QWidget()
        body.setObjectName("SettingsDialogBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        self._bl = QVBoxLayout(body)
        self._apply_body_spacing()

        theme_box = QGroupBox("Appearance")
        theme_box.setObjectName("SettingsThemeGroup")
        self._th_row = QHBoxLayout(theme_box)
        self._theme_group = QButtonGroup(self)
        self._dark_btn = self._make_toggle("Dark")
        self._light_btn = self._make_toggle("Light")
        self._theme_group.addButton(self._dark_btn)
        self._theme_group.addButton(self._light_btn)
        if theme_name == "light":
            self._light_btn.setChecked(True)
        else:
            self._dark_btn.setChecked(True)
        self._th_row.addWidget(self._dark_btn)
        self._th_row.addWidget(self._light_btn)
        self._th_row.addStretch(1)
        self._bl.addWidget(theme_box)

        scale_box = QGroupBox("Interface size")
        scale_box.setObjectName("SettingsScaleGroup")
        self._sl = QVBoxLayout(scale_box)

        self._scale_group = QButtonGroup(self)
        self._auto_btn = self._make_toggle("Automatic (recommended)")
        self._scale_group.addButton(self._auto_btn)
        self._sl.addWidget(self._auto_btn)

        self._preset_btns: dict[str, QPushButton] = {}
        for pid, label in PRESET_LABELS:
            b = self._make_toggle(label)
            b.setProperty("preset_id", pid)
            self._scale_group.addButton(b)
            self._sl.addWidget(b)
            self._preset_btns[pid] = b

        if prefs.ui_scale_locked:
            pr = self._preset_btns.get(prefs.ui_scale_preset)
            if pr is not None:
                pr.setChecked(True)
            else:
                self._preset_btns["normal"].setChecked(True)
        else:
            self._auto_btn.setChecked(True)

        # Use buttonToggled(checked=True) so checkedButton() matches the new choice;
        # buttonClicked fires before exclusive groups update the checked button.
        self._theme_group.buttonToggled.connect(self._on_toggle_preview)
        self._scale_group.buttonToggled.connect(self._on_toggle_preview)

        self._apply_scale_section_spacing()

        self._bl.addWidget(scale_box)

        self._hint = QLabel(
            "Each change is saved automatically. Automatic on large displays uses a compact scale "
            "similar to “Small”."
        )
        self._hint.setWordWrap(True)
        self._hint.setObjectName("SettingsHintLabel")
        self._bl.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsDialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(body)

        outer.addWidget(scroll, stretch=1)

        self._resize_window_sensibly()

    def _apply_body_spacing(self) -> None:
        m = scaled_px(14)
        self._bl.setContentsMargins(m, scaled_px(12), m, scaled_px(12))
        self._bl.setSpacing(scaled_px(14))

    def _apply_scale_section_spacing(self) -> None:
        self._th_row.setSpacing(scaled_px(10))
        self._sl.setSpacing(scaled_px(10))

    def _resize_window_sensibly(self) -> None:
        """Cap dialog height to the viewport; body scrolls."""
        from PyQt5.QtWidgets import QApplication

        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr is not None else None
        max_h = int(geo.height() * 0.92) if geo is not None else 1200
        max_w = int(geo.width() * 0.98) if geo is not None else 1600

        self.setMinimumWidth(max(scaled_px(440), 360))
        self.setMinimumHeight(min(scaled_px(260), max_h))
        self.setMaximumHeight(max_h)
        self.setMaximumWidth(max_w)

        rw = min(max(scaled_px(520), 420), max_w)
        rh = min(max(scaled_px(480), 320), max_h)
        self.resize(rw, rh)

    def _make_toggle(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("SettingsToggleButton")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoDefault(False)
        b.setDefault(False)
        return b

    def _screen_metrics(self) -> tuple[float, int, int, float]:
        from PyQt5.QtWidgets import QApplication

        dpi = 96.0
        w, h = 1920, 1080
        dpr = 1.0
        app = QApplication.instance()
        if app is not None:
            scr = app.primaryScreen()
            if scr is not None:
                dpi = float(scr.logicalDotsPerInchX())
                g = scr.availableGeometry()
                w, h = g.width(), g.height()
                dpr = float(scr.devicePixelRatio())
        return dpi, w, h, dpr

    def _gather_prefs(self) -> UiPreferences:
        theme = "light" if self._light_btn.isChecked() else "dark"
        checked = self._scale_group.checkedButton()
        if checked is self._auto_btn:
            locked = False
            preset = "normal"
        else:
            locked = True
            preset = "normal"
            for pid, btn in self._preset_btns.items():
                if btn is checked:
                    preset = pid
                    break
        dpi, w, h, dpr = self._screen_metrics()
        last_auto = self._prefs_in.last_auto_scale
        if not locked:
            last_auto = dpi_auto_multiplier(dpi, w, h, dpr)
        return UiPreferences(
            theme=theme,
            ui_scale_locked=locked,
            ui_scale_preset=preset,
            last_auto_scale=last_auto,
        )

    def _on_toggle_preview(self, _button: QAbstractButton, checked: bool) -> None:
        if not checked:
            return
        self._apply_current_prefs()

    def _apply_current_prefs(self) -> None:
        prefs = self._gather_prefs()
        save_ui_preferences(prefs)
        shell = self.parent()
        if shell is not None:
            shell._ui_prefs = prefs
            if hasattr(shell, "_apply_prefs_preview"):
                shell._apply_prefs_preview(prefs)
        theme_name = prefs.theme if prefs.theme in THEMES else "dark"
        apply_theme(self, THEMES[theme_name])
        self._apply_body_spacing()
        self._apply_scale_section_spacing()
        self._resize_window_sensibly()

    def reject(self) -> None:
        super().reject()
