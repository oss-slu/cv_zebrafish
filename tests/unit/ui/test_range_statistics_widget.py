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

    def test_set_series_with_nans_preserves_coordinate_alignment(self, qt_app):
        """Ensure NaNs in Y or X filter paired elements without shifting frames."""
        widget = RangeStatisticsWidget()
        x_vals = [0, 1, 2, 3, 4]
        y_vals = [10.0, float("nan"), 20.0, float("nan"), 30.0]

        widget.set_series(x_vals, y_vals, name="NaN Test")
        stats = widget.get_current_statistics()
        assert stats is not None
        assert stats.is_valid is True
        assert stats.count == 3
        # Should retain paired x positions: 0 -> 10.0, 2 -> 20.0, 4 -> 30.0
        assert stats.min_value == 10.0
        assert stats.min_x == 0.0
        assert stats.max_value == 30.0
        assert stats.max_x == 4.0

        # Query subrange [1, 3] which only includes x=2 (y=20.0)
        widget.set_range(1, 3)
        sub_stats = widget.get_current_statistics()
        assert sub_stats.count == 1
        assert sub_stats.min_value == 20.0
        assert sub_stats.min_x == 2.0

    def test_reset_to_full_range_emits_reset_requested(self, qt_app):
        widget = RangeStatisticsWidget()
        widget.set_series([10, 20, 30], [1.0, 2.0, 3.0])
        widget.set_range(15, 25)

        resets = []
        widget.resetRequested.connect(lambda: resets.append(True))

        widget.reset_to_full_range()
        assert len(resets) == 1
        assert widget.start_spin.value() == 10.0
        assert widget.end_spin.value() == 30.0

    def test_sync_to_full_range_does_not_emit_reset_requested(self, qt_app):
        """Graph-originated autorange calls sync_to_full_range to prevent feedback loop."""
        widget = RangeStatisticsWidget()
        widget.set_series([10, 20, 30], [1.0, 2.0, 3.0])
        widget.set_range(15, 25)

        resets = []
        widget.resetRequested.connect(lambda: resets.append(True))

        widget.sync_to_full_range()
        assert len(resets) == 0
        assert widget.start_spin.value() == 10.0
        assert widget.end_spin.value() == 30.0

    def test_integer_frames_snap_inward(self, qt_app):
        """Graph range of 10.4–20.6 should snap inward to 11–20 when x-values are integer frames."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(31)), y=[float(i * 2) for i in range(31)], name="Frames"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        widget.set_range(10.4, 20.6)

        assert widget.start_spin.value() == 11.0
        assert widget.end_spin.value() == 20.0

        stats = widget.get_current_statistics()
        assert stats is not None
        assert stats.is_valid is True
        assert stats.count == 10  # frames 11 through 20
        assert stats.min_x == 11.0
        assert stats.max_x == 20.0
        assert stats.min_value == 22.0
        assert stats.max_value == 40.0

    def test_integer_frames_exact_boundary(self, qt_app):
        """Exact integer bounds 10.0–20.0 should remain 10–20 without unintended truncation."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(31)), y=[float(i) for i in range(31)], name="Frames"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        widget.set_range(10.0, 20.0)

        assert widget.start_spin.value() == 10.0
        assert widget.end_spin.value() == 20.0
        assert widget.get_current_statistics().count == 11

    def test_integer_frames_reverse_selection(self, qt_app):
        """Inverted selection range 20.6–10.4 should snap inward correctly to 11–20."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(31)), y=[float(i) for i in range(31)], name="Frames"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        widget.set_range(20.6, 10.4)

        assert widget.start_spin.value() == 11.0
        assert widget.end_spin.value() == 20.0
        assert widget.get_current_statistics().count == 10

    def test_integer_frames_sub_frame_empty_range(self, qt_app):
        """Selection between two frames (10.2–10.8) should show empty-range feedback without crashing or rounding outward."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(31)), y=[float(i) for i in range(31)], name="Frames"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        widget.set_range(10.2, 10.8)

        assert widget.start_spin.value() == 11.0
        assert widget.end_spin.value() == 10.0

        stats = widget.get_current_statistics()
        assert stats is not None
        assert stats.is_valid is False
        assert stats.count == 0
        assert "No data points in selected range" in widget.status_label.text()
        assert widget.lbl_min_val.text() == "—"
        assert widget.lbl_max_val.text() == "—"

    def test_float_series_preserves_decimals(self, qt_app):
        """Float x-data should preserve 3 decimal precision and not snap inward to whole integers."""
        x_vals = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25]
        y_vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

        widget = RangeStatisticsWidget()
        widget.set_series(x_vals, y_vals, name="Float Series")

        assert widget.start_spin.decimals() == 3
        assert widget.end_spin.decimals() == 3

        widget.set_range(0.24, 0.76)

        assert widget.start_spin.value() == pytest.approx(0.24)
        assert widget.end_spin.value() == pytest.approx(0.76)

        stats = widget.get_current_statistics()
        assert stats.is_valid is True
        assert stats.count == 3  # points at 0.25, 0.5, 0.75

    def test_trace_change_preserves_zoom_and_recomputes(self, qt_app):
        """Switching the Signal dropdown should preserve the current range and not reset graph zoom."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(10)), y=[float(i) for i in range(10)], name="Trace A"))
        fig.add_trace(go.Scatter(x=list(range(10)), y=[float(i * 10) for i in range(10)], name="Trace B"))

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        widget.set_range(2, 6)
        assert widget.get_current_statistics().max_value == 6.0

        resets = []
        widget.resetRequested.connect(lambda: resets.append(True))

        # Switch to Trace B
        widget.trace_combo.setCurrentIndex(1)

        # Zoom was NOT reset
        assert len(resets) == 0
        assert widget.start_spin.value() == 2.0
        assert widget.end_spin.value() == 6.0
        # Statistics updated for Trace B
        assert widget.get_current_statistics().max_value == 60.0

    def test_position_label_custom_axis_title(self, qt_app):
        """Position labels should incorporate the figure's x-axis title if specified."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1.0, 2.0, 3.0], y=[10.0, 20.0, 30.0], name="Speed"))
        fig.update_layout(xaxis_title="Time (s)")

        widget = RangeStatisticsWidget()
        widget.set_figure(fig)

        assert "(at Time (s): 1)" in widget.lbl_min_pos.text()
        assert "(at Time (s): 3)" in widget.lbl_max_pos.text()

    def test_position_label_float_trace_neutral_x(self, qt_app):
        """Position labels for float series without axis title should use neutral '(at x: ...)'."""
        widget = RangeStatisticsWidget()
        widget.set_series([0.5, 1.5, 2.5], [10.0, 20.0, 30.0], name="Series")

        assert "(at x: 0.5)" in widget.lbl_min_pos.text()
        assert "(at x: 2.5)" in widget.lbl_max_pos.text()


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

    def test_interactive_graph_range_reset_does_not_retrigger_reset_zoom(self, qt_app):
        """Ensure rangeReset from graph syncs stats without re-emitting resetRequested."""
        graph = InteractiveGraph()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 10, 20], y=[1, 2, 3]))
        graph.set_figure(fig)

        # Zoom into [5, 15]
        graph.rangeSelected.emit(5.0, 15.0)
        assert graph.range_stats_widget.start_spin.value() == 5.0
        assert graph.range_stats_widget.end_spin.value() == 15.0

        # Simulate graph firing rangeReset (autorange)
        reset_calls = []
        graph.range_stats_widget.resetRequested.connect(lambda: reset_calls.append(True))
        graph.rangeReset.emit()

        # Inputs are restored to full range [0, 20]
        assert graph.range_stats_widget.start_spin.value() == 0.0
        assert graph.range_stats_widget.end_spin.value() == 20.0
        # But resetRequested was NOT emitted (loop prevented!)
        assert len(reset_calls) == 0

    def test_interactive_graph_range_selected_snaps_integer_frames(self, qt_app):
        """rangeSelected with fractional values snaps inward on integer frames in InteractiveGraph."""
        graph = InteractiveGraph()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(50)), y=[float(i) for i in range(50)]))
        graph.set_figure(fig)

        # Simulate Plotly fractional zoom event: 10.4 to 20.6
        graph.rangeSelected.emit(10.4, 20.6)

        assert graph.range_stats_widget.start_spin.value() == 11.0
        assert graph.range_stats_widget.end_spin.value() == 20.0
        stats = graph.range_stats_widget.get_current_statistics()
        assert stats is not None
        assert stats.count == 10
        assert stats.min_x == 11.0
        assert stats.max_x == 20.0
