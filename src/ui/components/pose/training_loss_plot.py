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
    """Live training loss chart (total + optional heatmap component)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TrainingLossPlot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._epochs: list[int] = []
        self._total_losses: list[float] = []
        self._heatmap_losses: list[float] = []
        if _HAVE_MPL:
            self._fig = Figure(figsize=(4, 2.2), tight_layout=True)
            self._ax = self._fig.add_subplot(111)
            (self._total_line,) = self._ax.plot(
                [], [], color="#4ea1ff", linewidth=1.5, label="Total train loss"
            )
            (self._heatmap_line,) = self._ax.plot(
                [], [], color="#f0a050", linewidth=1.0, linestyle="--", label="Heatmap"
            )
            self._ax.set_xlabel("Epoch")
            self._ax.set_ylabel("Loss")
            self._ax.grid(True, alpha=0.25)
            self._ax.legend(loc="upper right", fontsize=8)
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._canvas)
        else:
            self._fig = None
            self._ax = None
            self._total_line = None
            self._heatmap_line = None
            self._canvas = None

    def clear(self) -> None:
        self._epochs.clear()
        self._total_losses.clear()
        self._heatmap_losses.clear()
        self._redraw()

    def set_history(
        self,
        points: list[tuple[int, float]],
        *,
        heatmap_points: list[tuple[int, float]] | None = None,
    ) -> None:
        self._epochs = [int(ep) for ep, _ in points]
        self._total_losses = [float(loss) for _, loss in points]
        if heatmap_points:
            heatmap_by_epoch = {int(ep): float(loss) for ep, loss in heatmap_points}
            self._heatmap_losses = [
                heatmap_by_epoch[ep] for ep in self._epochs if ep in heatmap_by_epoch
            ]
            if len(self._heatmap_losses) != len(self._epochs):
                self._heatmap_losses = [
                    heatmap_by_epoch.get(ep, float("nan")) for ep in self._epochs
                ]
        else:
            self._heatmap_losses = []
        self._redraw()

    def set_breakdown_history(
        self,
        points: list[tuple[int, float, float | None]],
    ) -> None:
        """Each point is ``(epoch, total_loss, heatmap_loss)``."""
        self._epochs = [int(ep) for ep, _, _ in points]
        self._total_losses = [float(total) for _, total, _ in points]
        self._heatmap_losses = [
            float(heatmap) for _, _, heatmap in points if heatmap is not None
        ]
        if len(self._heatmap_losses) != len(self._epochs):
            self._heatmap_losses = [
                float(heatmap) if heatmap is not None else float("nan")
                for _, _, heatmap in points
            ]
        self._redraw()

    def has_points(self) -> bool:
        return bool(self._epochs)

    def add_point(
        self,
        epoch: int,
        total_loss: float,
        *,
        heatmap_loss: float | None = None,
    ) -> None:
        if epoch in self._epochs:
            idx = self._epochs.index(epoch)
            self._total_losses[idx] = float(total_loss)
            if heatmap_loss is not None:
                if len(self._heatmap_losses) <= idx:
                    self._heatmap_losses.extend(
                        [float("nan")] * (idx + 1 - len(self._heatmap_losses))
                    )
                self._heatmap_losses[idx] = float(heatmap_loss)
        else:
            self._epochs.append(int(epoch))
            self._total_losses.append(float(total_loss))
            if heatmap_loss is not None:
                self._heatmap_losses.append(float(heatmap_loss))
        self._redraw()

    def _redraw(self) -> None:
        if self._ax is None or self._total_line is None or self._canvas is None:
            return
        self._total_line.set_data(self._epochs, self._total_losses)
        if self._heatmap_line is not None:
            if self._heatmap_losses and len(self._heatmap_losses) == len(self._epochs):
                self._heatmap_line.set_data(self._epochs, self._heatmap_losses)
                self._heatmap_line.set_visible(True)
            else:
                self._heatmap_line.set_data([], [])
                self._heatmap_line.set_visible(False)
        self._ax.relim()
        self._ax.autoscale_view()
        self._canvas.draw_idle()
