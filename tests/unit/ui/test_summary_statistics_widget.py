"""
Unit tests for SummaryStatisticsWidget (src/ui/components/summary_statistics_widget.py).
"""

from __future__ import annotations

import pandas as pd
import pytest
from PyQt5.QtWidgets import QApplication

from src.ui.components.summary_statistics_widget import SummaryStatisticsWidget


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_summary_widget_initial_state(qt_app):
    """Widget starts with an empty table and disabled export buttons."""
    widget = SummaryStatisticsWidget()
    assert widget.table.columnCount() == 4
    assert widget.table.rowCount() == 0
    assert widget.export_csv_btn.isEnabled() is False
    assert widget.export_excel_btn.isEnabled() is False
    assert widget.get_summary_dataframe() is None


def test_summary_widget_populate_table(qt_app):
    """Setting a results DataFrame populates the summary table with mean, median, units."""
    widget = SummaryStatisticsWidget()
    df = pd.DataFrame({
        "Time": [0, 1, 2, 3],
        "LF_Angle": [10.0, 20.0, 30.0, 40.0],
        "Tail_Distance": [2.0, 4.0, 6.0, 8.0],
    })

    widget.set_dataframe(df)

    assert widget.table.rowCount() == 2
    assert widget.export_csv_btn.isEnabled() is True
    assert widget.export_excel_btn.isEnabled() is True

    # Check first row (LF_Angle)
    assert widget.table.item(0, 0).text() == "LF_Angle"
    assert widget.table.item(0, 1).text() == "25"  # mean
    assert widget.table.item(0, 2).text() == "25"  # median
    assert widget.table.item(0, 3).text() == "deg"

    # Check second row (Tail_Distance)
    assert widget.table.item(1, 0).text() == "Tail_Distance"
    assert widget.table.item(1, 1).text() == "5"   # mean
    assert widget.table.item(1, 2).text() == "5"   # median
    assert widget.table.item(1, 3).text() == "m"

    summary_df = widget.get_summary_dataframe()
    assert summary_df is not None
    assert len(summary_df) == 2


def test_summary_widget_clear(qt_app):
    """Calling clear resets the table and disables export actions."""
    widget = SummaryStatisticsWidget()
    df = pd.DataFrame({"LF_Angle": [10.0, 20.0]})
    widget.set_dataframe(df)
    assert widget.table.rowCount() == 1

    widget.clear()
    assert widget.table.rowCount() == 0
    assert widget.export_csv_btn.isEnabled() is False
    assert widget.get_summary_dataframe() is None


def test_summary_widget_multi_csv(qt_app):
    """Multi-CSV dataset support populates dropdown and switches views."""
    widget = SummaryStatisticsWidget()
    df_fish1 = pd.DataFrame({"LF_Angle": [10.0, 20.0]})
    df_fish2 = pd.DataFrame({"LF_Angle": [100.0, 200.0]})

    results = {
        "fish1.csv": df_fish1,
        "fish2.csv": df_fish2,
    }

    widget.set_results_by_csv(results)
    assert not widget.csv_combo.isHidden()
    assert widget.csv_combo.count() == 2

    # Switch to fish2
    widget.csv_combo.setCurrentIndex(1)
    assert widget.table.item(0, 1).text() == "150"  # mean of fish2
