"""Matplotlib loss curve for Pose Studio training dialog."""

from __future__ import annotations

from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    _HAVE_MPL = True
except ImportError:
    _HAVE_MPL = False


class TrainingLossPlot(QWidget):
    """Live training loss chart (falls back to empty widget if matplotlib missing)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TrainingLossPlot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._epochs: list[int] = []
        self._losses: list[float] = []
        if _HAVE_MPL:
            self._fig = Figure(figsize=(4, 2.2), tight_layout=True)
            self._ax = self._fig.add_subplot(111)
            self._line, = self._ax.plot([], [], color="#4ea1ff", linewidth=1.5)
            self._ax.set_xlabel("Epoch")
            self._ax.set_ylabel("Loss")
            self._ax.grid(True, alpha=0.25)
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._canvas)
        else:
            self._fig = None
            self._ax = None
            self._line = None
            self._canvas = None

    def clear(self) -> None:
        self._epochs.clear()
        self._losses.clear()
        if self._ax is not None and self._line is not None:
            self._line.set_data([], [])
            self._ax.relim()
            self._ax.autoscale_view()
            self._canvas.draw_idle()

    def add_point(self, epoch: int, loss: float) -> None:
        self._epochs.append(epoch)
        self._losses.append(loss)
        if self._ax is None or self._line is None or self._canvas is None:
            return
        self._line.set_data(self._epochs, self._losses)
        self._ax.relim()
        self._ax.autoscale_view()
        self._canvas.draw_idle()
