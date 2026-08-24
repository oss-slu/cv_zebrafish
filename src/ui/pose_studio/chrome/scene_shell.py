"""Standard Pose Studio scene layout: optional context, side | main, advanced bottom."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.pose_studio.chrome.context_bar import PoseContextBar


class _SplitterHandleGrip(QWidget):
    """Three short vertical bars centered on the horizontal splitter handle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PoseSceneSplitterGrip")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFixedSize(10, 40)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        color = self.palette().color(self.palette().Mid)
        if not color.isValid() or color.alpha() == 0:
            color = self.palette().color(self.palette().WindowText)
            color.setAlpha(140)
        pen = QPen(color)
        pen.setWidth(1)
        painter.setPen(pen)
        cx = self.width() // 2
        y0, y1 = 6, self.height() - 6
        for dx in (-3, 0, 3):
            painter.drawLine(cx + dx, y0, cx + dx, y1)


class PoseSceneShell(QWidget):
    """
    Hierarchical scene chrome shared by Start / Video / Label / Model / Auto Label.

    Layout::

        [ context bar ]
        [ side panel | main panel ]   # QSplitter — left width adjustable
        [ advanced (collapsible) ]
    """

    def __init__(
        self,
        *,
        show_context_bar: bool = True,
        side_width: int = 360,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PoseSceneShell")
        self._side_width = max(200, int(side_width))
        self._sizes_applied = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.context_bar = PoseContextBar()
        self.context_bar.setVisible(show_context_bar)
        root.addWidget(self.context_bar)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("PoseSceneSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(10)
        self._splitter.setOpaqueResize(True)

        self.side_host = QFrame()
        self.side_host.setObjectName("PoseSceneSide")
        self.side_host.setAttribute(Qt.WA_StyledBackground, True)
        self.side_host.setMinimumWidth(240)
        self.side_host.setMaximumWidth(720)
        # Preferred horizontally so the splitter can resize; expanding vertically.
        self.side_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        side_scroll = QScrollArea()
        side_scroll.setObjectName("PoseSceneSideScroll")
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        # Never show a horizontal scrollbar — side width fits content instead.
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Ignored: take the splitter's width instead of a tiny QScrollArea sizeHint
        # (that was collapsing the side under the main panel on non-Label tabs).
        side_scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._side_scroll = side_scroll

        self._side_inner = QWidget()
        self._side_inner.setObjectName("PoseSceneSideInner")
        self.side_layout = QVBoxLayout(self._side_inner)
        self.side_layout.setContentsMargins(8, 8, 8, 8)
        self.side_layout.setSpacing(8)
        self.side_layout.addStretch(1)
        side_scroll.setWidget(self._side_inner)
        # Clip sub-panel chrome so QGroupBox borders cannot paint into the main panel.
        side_scroll.viewport().setAttribute(Qt.WA_OpaquePaintEvent, True)
        side_scroll.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        side_wrap = QVBoxLayout(self.side_host)
        side_wrap.setContentsMargins(0, 0, 0, 0)
        side_wrap.setSpacing(0)
        side_wrap.addWidget(side_scroll)

        self.main_host = QFrame()
        self.main_host.setObjectName("PoseSceneMain")
        self.main_host.setAttribute(Qt.WA_StyledBackground, True)
        self.main_host.setMinimumWidth(200)
        self.main_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_layout = QVBoxLayout(self.main_host)
        self.main_layout.setContentsMargins(12, 8, 8, 8)
        self.main_layout.setSpacing(8)

        self._splitter.addWidget(self.side_host)
        self._splitter.addWidget(self.main_host)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._decorate_splitter_handle()
        root.addWidget(self._splitter, stretch=1)

        QTimer.singleShot(0, self._ensure_side_sizes)

        self._advanced_wrap = QFrame()
        self._advanced_wrap.setObjectName("PoseSceneAdvanced")
        self._advanced_wrap.setAttribute(Qt.WA_StyledBackground, True)
        adv_outer = QVBoxLayout(self._advanced_wrap)
        adv_outer.setContentsMargins(8, 0, 8, 8)
        adv_outer.setSpacing(4)
        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setObjectName("PoseAdvancedToggle")
        self._advanced_toggle.setText("Advanced")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setChecked(False)
        self._advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._advanced_toggle.setArrowType(Qt.RightArrow)
        self._advanced_toggle.setToolTip("Show or hide advanced settings")
        self._advanced_toggle.toggled.connect(self._on_advanced_toggled)
        adv_outer.addWidget(self._advanced_toggle, alignment=Qt.AlignLeft)
        self.advanced_body = QWidget()
        self.advanced_body.setVisible(False)
        self.advanced_layout = QVBoxLayout(self.advanced_body)
        self.advanced_layout.setContentsMargins(0, 4, 0, 0)
        self.advanced_layout.setSpacing(6)
        adv_outer.addWidget(self.advanced_body)
        root.addWidget(self._advanced_wrap)
        self.set_advanced_visible(False)

    def _decorate_splitter_handle(self) -> None:
        """Grip bars + ↔ cursor so the side panel resize affordance is obvious."""
        handle = self._splitter.handle(1)
        if handle is None:
            return
        handle.setCursor(Qt.SizeHorCursor)
        handle.setToolTip("Drag to resize side panel")
        lay = QVBoxLayout(handle)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(_SplitterHandleGrip(handle), alignment=Qt.AlignCenter)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._constrain_side_inner_width()
        self.fit_side_to_content()

    def _constrain_side_inner_width(self) -> None:
        """Keep side sub-panels inside the scroll viewport (no bleed under main panel)."""
        viewport = self._side_scroll.viewport()
        avail = viewport.width()
        if avail <= 0:
            return
        # Cap to the splitter pane, not a shrinking feedback loop with the scrollbar.
        host_w = max(0, self.side_host.width() - 2)
        cap = max(120, min(avail, host_w) if host_w else avail)
        self._side_inner.setMaximumWidth(cap)

    def fit_side_to_content(self) -> None:
        """Widen the side panel to fit controls; never shrink below that width."""
        if not self.side_host.isVisible():
            return
        self._side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Clear a stale max-width clamp so sizeHint reflects real control widths.
        self._side_inner.setMaximumWidth(16777215)
        self._side_inner.adjustSize()
        self._side_inner.updateGeometry()
        hint = max(
            self._side_inner.sizeHint().width(),
            self._side_inner.minimumSizeHint().width(),
            240,
        )
        margins = self.side_layout.contentsMargins()
        # Extra room so a vertical scrollbar does not steal horizontal space.
        needed = hint + margins.left() + margins.right() + 24
        needed = min(max(needed, 240), self.side_host.maximumWidth())
        # Keep a drag range: don't pin min to the full fitted width forever.
        self.side_host.setMinimumWidth(min(needed, 320))
        self._side_width = max(self._side_width, needed)
        sizes = self._splitter.sizes()
        side_now = sizes[0] if sizes else 0
        if side_now < needed or not self._sizes_applied:
            self._ensure_side_sizes(force=True)
        self._constrain_side_inner_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._constrain_side_inner_width()
        sizes = self._splitter.sizes()
        if (
            self.side_host.isVisible()
            and sizes
            and sizes[0] < 160
            and self._splitter.width() > self._side_width + 200
        ):
            self._ensure_side_sizes(force=True)

    def _ensure_side_sizes(self, *, force: bool = False) -> None:
        """Apply default side|main widths once the splitter has a real geometry."""
        if not self.side_host.isVisible():
            return
        total = self._splitter.width()
        if total <= 0:
            total = max(self.width(), self._side_width + 480)
        sizes = self._splitter.sizes()
        side_now = sizes[0] if sizes else 0
        if not force and self._sizes_applied and side_now >= 160:
            return
        side = min(max(self._side_width, 200), max(200, total - 220))
        main = max(200, total - side - self._splitter.handleWidth())
        self._splitter.setSizes([side, main])
        self._sizes_applied = True

    def _on_advanced_toggled(self, checked: bool) -> None:
        self.advanced_body.setVisible(checked)
        self._advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def set_advanced_visible(self, visible: bool) -> None:
        """Show/hide the entire advanced strip (e.g. Start has none)."""
        self._advanced_wrap.setVisible(visible)

    def set_side_visible(self, visible: bool) -> None:
        self.side_host.setVisible(visible)
        if visible:
            self._sizes_applied = False
            QTimer.singleShot(0, self._ensure_side_sizes)

    def set_side_width(self, width: int) -> None:
        """Set the default / reset width for the left panel (user can still drag)."""
        self._side_width = max(200, int(width))
        self._sizes_applied = False
        self._ensure_side_sizes(force=True)

    def add_side_widget(self, widget: QWidget, *, stretch: int = 0) -> None:
        # Insert before trailing stretch.
        idx = max(0, self.side_layout.count() - 1)
        self.side_layout.insertWidget(idx, widget, stretch)

    def add_main_widget(self, widget: QWidget, *, stretch: int = 1) -> None:
        self.main_layout.addWidget(widget, stretch)

    def add_advanced_widget(self, widget: QWidget) -> None:
        self.set_advanced_visible(True)
        self.advanced_layout.addWidget(widget)
