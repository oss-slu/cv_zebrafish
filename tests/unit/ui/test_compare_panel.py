import pandas as pd
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog

from src.core.comparison.fish_data import LoadedFish
from ui.main_panels.compare_panel import ComparePanel


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_fish(number):
    results = pd.DataFrame(
        {
            "Time": [0, 1, 2],
            "LF_Angle": [10.0 * number, 20.0 * number, 30.0 * number],
            "Tail_Distance": [0.1 * number, 0.2 * number, 0.3 * number],
        }
    )
    return LoadedFish(
        fish_id=f"fish_{number}",
        label=f"Fish {number}",
        source_file=f"/data/fish_{number}.csv",
        results=results,
    )


@pytest.fixture
def panel(qt_app):
    widget = ComparePanel()
    widget.add_fish([make_fish(n) for n in range(1, 6)])
    return widget


def header_labels(panel):
    view = panel.comparison_view
    return [view.horizontalHeaderItem(i).text() for i in range(view.columnCount())]


def test_five_fish_each_get_a_column(panel):
    assert header_labels(panel) == [
        "Parameter", "Unit", "Statistic", "Fish 1", "Fish 2", "Fish 3", "Fish 4", "Fish 5",
    ]
    assert panel.comparison_view.rowCount() == 4  # 2 parameters x (mean, median)


def test_unchecking_a_fish_removes_its_column(panel):
    panel.fish_table.item(1, 0).setCheckState(Qt.Unchecked)

    assert "Fish 2" not in header_labels(panel)
    assert len(header_labels(panel)) == 7


def test_unchecking_a_parameter_removes_its_rows(panel):
    names = [panel.parameter_list.item(i).text() for i in range(panel.parameter_list.count())]
    panel.parameter_list.item(names.index("Tail_Distance")).setCheckState(Qt.Unchecked)

    assert panel.comparison_view.rowCount() == 2
    assert panel.comparison_view.item(0, 0).text() == "LF_Angle"


def test_renaming_a_fish_updates_the_table(panel):
    panel.fish_table.item(0, 1).setText("Wild type")

    assert "Wild type" in header_labels(panel)
    assert "Fish 1" not in header_labels(panel)


def test_duplicate_label_is_rejected_and_reverted(panel):
    panel.fish_table.item(0, 1).setText("Fish 2")

    assert panel.fish_table.item(0, 1).text() == "Fish 1"
    assert "already used" in panel.messages.toPlainText()


def test_removing_a_fish_drops_it_everywhere(panel):
    panel._remove_fish("fish_3")

    assert [fish.fish_id for fish in panel.loaded_fish()] == ["fish_1", "fish_2", "fish_4", "fish_5"]
    assert "Fish 3" not in header_labels(panel)


def test_clearing_all_parameters_disables_export(panel):
    panel.clear_all_button.click()

    assert panel.comparison_table() is None
    assert panel.export_button.isEnabled() is False


def test_export_writes_only_selected_fish(panel, tmp_path, monkeypatch):
    panel.fish_table.item(4, 0).setCheckState(Qt.Unchecked)
    target = tmp_path / "comparison.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), "CSV files (*.csv)")
    )

    panel._export_comparison()

    exported = pd.read_csv(target, encoding="utf-8-sig")
    assert "Fish 5" not in exported.columns
    assert exported.loc[0, "Parameter"] == "Fish ID"
    assert exported.loc[1, "Fish 1"] == "/data/fish_1.csv"

    
def test_plots_follow_the_table_selection(panel):
    before = {t.name: t.line.color for t in panel.overlay_widget.figure.data}

    panel.fish_table.item(1, 0).setCheckState(Qt.Unchecked)

    after = {t.name: t.line.color for t in panel.overlay_widget.figure.data}
    assert "Fish 2" not in after
    assert after["Fish 3"] == before["Fish 3"]


def test_removed_fish_leaves_the_plot(panel):
    panel._remove_fish("fish_1")

    assert "Fish 1" not in [t.name for t in panel.overlay_widget.figure.data]


def test_each_fish_row_shows_its_plot_color(panel):
    assert not panel.fish_table.item(0, 1).icon().isNull()