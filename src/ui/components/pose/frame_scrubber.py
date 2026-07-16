"""Frame index scrubber with optional QC flag markers and auto-play."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QWidget


class FrameScrubber(QWidget):
    frame_changed = pyqtSignal(int)
    frame_preview = pyqtSignal(int)
    playback_stopped = pyqtSignal(int)
    playback_started = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FrameScrubber")
        self._flagged: set[int] = set()
        self._outlier_orange = QColor(255, 152, 50)
        self._playing = False
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.setTracking(True)
        self._slider.valueChanged.connect(self._on_value_changed)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._label = QLabel("Frame 0 / 0")
        self._prev = QPushButton("◀")
        self._next = QPushButton("▶")
        self._play = QPushButton("▶ Play")
        self._play.setCheckable(True)
        self._play.setToolTip(
            "Play video with blob mask and crop overlay at the FPS below"
        )
        self._fps_spin = QSpinBox()
        self._fps_spin.setObjectName("FrameScrubberFpsSpin")
        self._fps_spin.setRange(1, 120)
        self._fps_spin.setValue(60)
        self._fps_spin.setSuffix(" fps")
        self._fps_spin.setToolTip("Playback frame rate (higher = faster)")
        self._fps_spin.valueChanged.connect(self._on_playback_fps_changed)
        self._fps_label = QLabel("FPS")
        self._fps_label.setObjectName("SettingsHintLabel")
        self._prev.clicked.connect(lambda: self.set_frame(self._slider.value() - 1))
        self._next.clicked.connect(lambda: self.set_frame(self._slider.value() + 1))
        self._play.toggled.connect(self._on_play_toggled)
        self._slider.sliderPressed.connect(self.stop_playback)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._prev)
        lay.addWidget(self._slider, stretch=1)
        lay.addWidget(self._next)
        lay.addWidget(self._play)
        lay.addWidget(self._fps_label)
        lay.addWidget(self._fps_spin)
        lay.addWidget(self._label)

    def is_playing(self) -> bool:
        return self._playing

    def playback_fps(self) -> int:
        return int(self._fps_spin.value())

    def set_playback_fps(self, video_fps: float) -> None:
        """Pick a default playback FPS from the video (2× native, at least 60)."""
        if video_fps > 0:
            suggested = min(120, max(60, int(round(video_fps * 2))))
            self._fps_spin.setValue(suggested)

    def _playback_interval_ms(self) -> int:
        return max(1, int(round(1000.0 / self._fps_spin.value())))

    def _on_playback_fps_changed(self, _value: int) -> None:
        if self._playing:
            self._timer.start(self._playback_interval_ms())

    def set_frame_count(self, count: int) -> None:
        n = max(0, int(count) - 1)
        self._slider.setMaximum(n)
        self._update_label()
        if self._playing and n <= 0:
            self.stop_playback()

    def set_frame(self, index: int) -> None:
        index = max(self._slider.minimum(), min(self._slider.maximum(), int(index)))
        if self._slider.value() != index:
            self._slider.setValue(index)
        else:
            self._update_label()

    def frame_index(self) -> int:
        return int(self._slider.value())

    def set_flagged_frames(self, indices: set[int]) -> None:
        self._flagged = set(indices)
        self._update_label()

    def stop_playback(self) -> None:
        was_playing = self._playing
        self._playing = False
        self._timer.stop()
        self._play.blockSignals(True)
        self._play.setChecked(False)
        self._play.setText("▶ Play")
        self._play.blockSignals(False)
        if was_playing:
            self.playback_stopped.emit(self._slider.value())

    def _on_play_toggled(self, checked: bool) -> None:
        if checked:
            if self._slider.maximum() <= 0:
                self.stop_playback()
                return
            self._playing = True
            self._play.setText("⏸ Pause")
            self._timer.start(self._playback_interval_ms())
            self.playback_started.emit()
        else:
            self.stop_playback()

    def _on_tick(self) -> None:
        if self._slider.value() >= self._slider.maximum():
            self.stop_playback()
            return
        self.set_frame(self._slider.value() + 1)

    def _on_slider_moved(self, value: int) -> None:
        self._update_label()
        self.frame_preview.emit(int(value))

    def _on_slider_released(self) -> None:
        self.frame_changed.emit(self._slider.value())

    def _on_value_changed(self, value: int) -> None:
        if self._slider.isSliderDown():
            return
        self._update_label()
        self.frame_changed.emit(int(value))

    def _update_label(self) -> None:
        i = self._slider.value()
        total = self._slider.maximum() + 1
        flag = " ●" if i in self._flagged else ""
        self._label.setText(f"Frame {i} / {max(0, total - 1)}{flag}")
        if i in self._flagged:
            self._label.setStyleSheet(
                f"color: rgb({self._outlier_orange.red()}, "
                f"{self._outlier_orange.green()}, {self._outlier_orange.blue()});"
            )
        else:
            self._label.setStyleSheet("")
