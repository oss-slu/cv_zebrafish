"""Selection chain bar: Video → Labels → Model → Output → Dataset."""



from __future__ import annotations



from dataclasses import dataclass



from PyQt5.QtCore import Qt, pyqtSignal

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget



_COMPRESS_THRESHOLD = 18

_COMPRESS_LEN = 16



_DEFAULT_KEYS = ("video", "labels", "model", "output", "dataset")





@dataclass

class ContextChip:

    """One stage in the Pose Studio selection chain."""



    key: str

    label: str

    full_text: str = ""

    active: bool = False





class _ContextChipLabel(QLabel):

    """Chip label that notifies the bar on hover for expand-on-hover."""



    def __init__(self, bar: PoseContextBar, key: str, parent: QWidget | None = None) -> None:

        super().__init__(parent)

        self._bar = bar

        self._key = key

        self.setAttribute(Qt.WA_Hover, True)



    def hoverEnterEvent(self, event) -> None:

        self._bar._on_chip_hover_enter(self._key)

        super().hoverEnterEvent(event)



    def hoverLeaveEvent(self, event) -> None:

        self._bar._on_chip_hover_leave(self._key)

        super().hoverLeaveEvent(event)





class PoseContextBar(QWidget):

    """Top bar showing compressed selection chips; newest expanded, hover shows full text."""



    chip_clicked = pyqtSignal(str)



    def __init__(self, parent: QWidget | None = None) -> None:

        super().__init__(parent)

        self.setObjectName("PoseContextBar")

        self.setAttribute(Qt.WA_StyledBackground, True)

        self._chips: dict[str, ContextChip] = {

            k: ContextChip(key=k, label="—", full_text="") for k in _DEFAULT_KEYS

        }

        self._labels: dict[str, _ContextChipLabel] = {}

        self._hover_key: str | None = None

        row = QHBoxLayout(self)

        row.setContentsMargins(8, 4, 8, 4)

        row.setSpacing(6)

        titles = {

            "video": "Video",

            "labels": "Labels",

            "model": "Model",

            "output": "Output",

            "dataset": "Dataset",

        }

        for i, key in enumerate(_DEFAULT_KEYS):

            if i:

                sep = QLabel("→")

                sep.setObjectName("PoseContextSep")

                row.addWidget(sep)

            stage = QLabel(titles[key])

            stage.setObjectName("PoseContextStage")

            row.addWidget(stage)

            val = _ContextChipLabel(self, key)

            val.setObjectName("PoseContextChip")

            val.setCursor(Qt.PointingHandCursor)

            val.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            val.setProperty("chipKey", key)

            val.mousePressEvent = self._make_click(key)  # type: ignore[method-assign]

            self._labels[key] = val

            row.addWidget(val, stretch=1 if key == "video" else 0)

        row.addStretch(1)

        self._refresh()



    def _make_click(self, key: str):

        def _handler(event) -> None:

            self.chip_clicked.emit(key)



        return _handler



    def set_chip(

        self,

        key: str,

        *,

        label: str,

        full_text: str | None = None,

        active: bool = False,

    ) -> None:

        if key not in self._chips:

            return

        chip = self._chips[key]

        chip.label = label or "—"

        chip.full_text = full_text if full_text is not None else chip.label

        chip.active = active

        self._refresh()



    def set_output_chip(self, *, label: str, full_text: str | None = None) -> None:

        """Set the Output chip after an auto-label run (short label + optional detail)."""

        self.set_chip("output", label=label, full_text=full_text)



    def set_active_key(self, key: str | None) -> None:

        for k, chip in self._chips.items():

            chip.active = k == key

        self._refresh()



    def clear(self) -> None:

        for key in _DEFAULT_KEYS:

            self.set_chip(key, label="—", full_text="", active=False)



    def _on_chip_hover_enter(self, key: str) -> None:

        if key not in self._chips:

            return

        if self._hover_key == key:

            return

        self._hover_key = key

        self._refresh()



    def _on_chip_hover_leave(self, key: str) -> None:

        if self._hover_key != key:

            return

        self._hover_key = None

        self._refresh()



    def _display_text(self, key: str) -> str:

        chip = self._chips[key]

        base = chip.label if chip.label else "—"

        if chip.active or key == self._hover_key:

            expanded = chip.full_text or base

            return expanded if expanded else "—"

        if len(base) > _COMPRESS_THRESHOLD:

            return base[:_COMPRESS_LEN] + "…"

        return base



    def _refresh(self) -> None:

        for key, chip in self._chips.items():

            lbl = self._labels[key]

            text = self._display_text(key)

            lbl.setText(text)

            tip = chip.full_text or chip.label or ""

            lbl.setToolTip(tip if tip and tip != "—" else "")

            hovered = key == self._hover_key

            lbl.setProperty("active", "true" if chip.active else "false")

            lbl.setProperty("hovered", "true" if hovered else "false")

            lbl.style().unpolish(lbl)

            lbl.style().polish(lbl)

