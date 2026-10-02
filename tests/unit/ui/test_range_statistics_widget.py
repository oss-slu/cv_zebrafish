"""
Unit tests for RangeStatisticsWidget and InteractiveGraph range statistics integration.
"""

from __future__ import annotations

import plotly.graph_objects as go
import pytest
from PyQt5.QtWidgets import QApplication

from src.ui.components.InteractiveGraph import InteractiveGraph
from src.ui.components.range_statistics_widget import RangeStatisticsWidget


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestRangeStatisticsWidget:
    """Tests for RangeStatisticsWidget functionality and UI behavior."""

    def test_initial_state(self, qt_app):
        widget = RangeStatisticsWidget()
        assert widget.lbl_min_val.text() == "—"
        assert widget.lbl_max_val.text() == "—"
        assert widget.lbl_mean_val.text() == "—"
        assert widget.lbl_count_val.text() == "—"
        assert widget.isEnabled() is False

    def test_set_figure_single_trace(self, qt_app):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 10, 20, 30], y=[5.0, 25.0, 15.0, 10.0], name="Test Signal"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        assert widget.isEnabled() is True
        assert widget.start_spin.value() == 0.0
        assert widget.end_spin.value() == 30.0

        stats = widget.get_current_statistics()
        assert stats is not None
        assert stats.is_valid is True
        assert stats.count == 4
        assert stats.min_value == 5.0
        assert stats.min_x == 0.0
        assert stats.max_value == 25.0
        assert stats.max_x == 10.0
        assert stats.mean_value == pytest.approx((5.0 + 25.0 + 15.0 + 10.0) / 4)

        # Check UI labels
        assert widget.lbl_min_val.text() == "5"
        assert "0" in widget.lbl_min_pos.text()
        assert widget.lbl_max_val.text() == "25"
        assert "10" in widget.lbl_max_pos.text()
        assert widget.lbl_count_val.text() == "4 pts"

    def test_specifying_subrange(self, qt_app):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 10, 20, 30, 40], y=[100.0, 20.0, 50.0, 80.0, 10.0], name="Motion"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        # Specify range [10, 30]
        widget.set_range(10, 30)

        stats = widget.get_current_statistics()
        assert stats.is_valid is True
        assert stats.count == 3  # points at 10, 20, 30
        assert stats.min_value == 20.0
        assert stats.min_x == 10.0
        assert stats.max_value == 80.0
        assert stats.max_x == 30.0
        assert stats.mean_value == pytest.approx(50.0)

        assert widget.lbl_min_val.text() == "20"
        assert "10" in widget.lbl_min_pos.text()
        assert widget.lbl_max_val.text() == "80"
        assert "30" in widget.lbl_max_pos.text()

    def test_invalid_range_handling(self, qt_app):
        """Entering start > end should show an error without crashing the application."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 10, 20], y=[1.0, 2.0, 3.0], name="Test"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        # Simulate user specifying an invalid range directly in spinboxes
        widget.start_spin.setValue(50.0)
        widget.end_spin.setValue(10.0)
        widget.calculate_statistics()

        stats = widget.get_current_statistics()
        assert stats.is_valid is False
        assert not widget.status_label.isHidden()
        assert "cannot exceed" in widget.status_label.text()
        assert widget.lbl_min_val.text() == "—"
        assert widget.lbl_max_val.text() == "—"
        assert widget.lbl_mean_val.text() == "—"

    def test_empty_range_handling(self, qt_app):
        """Range with no points in it should display feedback without crashing."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 10, 20], y=[1.0, 2.0, 3.0], name="Test"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        widget.start_spin.setValue(100.0)
        widget.end_spin.setValue(200.0)
        widget.calculate_statistics()

        stats = widget.get_current_statistics()
        assert stats.is_valid is False
        assert "No data points" in widget.status_label.text()
        assert widget.lbl_min_val.text() == "—"

    def test_multiple_traces_selection(self, qt_app):
        """User can select which trace to compute statistics for."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1, 2], y=[10, 20, 30], name="Trace A"))
        fig.add_trace(go.Scatter(x=[0, 1, 2], y=[100, 200, 300], name="Trace B"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        assert widget.trace_combo.count() == 2
        assert widget.trace_combo.itemText(0) == "Trace A"
        assert widget.trace_combo.itemText(1) == "Trace B"

        # Check initial stats for Trace A
        assert widget.get_current_statistics().max_value == 30.0

        # Switch to Trace B
        widget.trace_combo.setCurrentIndex(1)
        assert widget.get_current_statistics().max_value == 300.0

    def test_full_range_reset(self, qt_app):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[5, 10, 15, 20], y=[2, 4, 6, 8], name="Signal"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        # Narrow range
        widget.set_range(8, 12)
        assert widget.get_current_statistics().count == 1

        # Reset to full range
        widget.reset_to_full_range()
        assert widget.start_spin.value() == 5.0
        assert widget.end_spin.value() == 20.0
        assert widget.get_current_statistics().count == 4

    def test_direct_set_series(self, qt_app):
        widget = RangeStatisticsWidget()
        widget.set_series([10, 20, 30], [5.5, 15.5, 25.5], name="Direct Series")

        assert widget.isEnabled() is True
        stats = widget.get_current_statistics()
        assert stats.min_value == 5.5
        assert stats.max_value == 25.5
        assert stats.mean_value == 15.5

    def test_zoom_requested_signal(self, qt_app):
        widget = RangeStatisticsWidget()
        widget.set_series([0, 100], [1, 2])

        emitted = []
        widget.zoomRequested.connect(lambda s, e: emitted.append((s, e)))

        widget.start_spin.setValue(20.0)
        widget.end_spin.setValue(80.0)
        widget.zoom_btn.click()

        assert len(emitted) == 1
        assert emitted[0] == (20.0, 80.0)


class TestInteractiveGraphIntegration:
    """Tests for InteractiveGraph embedding RangeStatisticsWidget."""

    def test_interactive_graph_embeds_range_stats(self, qt_app):
        graph = InteractiveGraph()
        assert graph.range_stats_widget is not None

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 5, 10], y=[10, 50, 20], name="Trace 1"))
        graph.set_figure(fig)

        stats = graph.range_stats_widget.get_current_statistics()
        assert stats is not None
        assert stats.min_value == 10.0
        assert stats.max_value == 50.0
        assert stats.max_x == 5.0

    def test_interactive_graph_clear_resets_stats(self, qt_app):
        graph = InteractiveGraph()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[2, 3]))
        graph.set_figure(fig)
        assert graph.range_stats_widget.isEnabled() is True

        graph.clear()
        assert graph.range_stats_widget.isEnabled() is False
        assert graph.range_stats_widget.lbl_min_val.text() == "—"

    def test_interactive_graph_range_selected_signal(self, qt_app):
        graph = InteractiveGraph()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 10, 20, 30, 40], y=[5, 15, 25, 35, 45]))
        graph.set_figure(fig)

        # Emitting rangeSelected simulates Plotly box-selection or zoom event
        graph.rangeSelected.emit(10.0, 30.0)

        stats = graph.range_stats_widget.get_current_statistics()
        assert stats.count == 3
        assert stats.min_value == 15.0
        assert stats.max_value == 35.0
