"""Background parse, metrics, and graph build for single-CSV calculation runs."""

from __future__ import annotations

import threading
from typing import Any

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

import core.calculations.Driver as calculations
import core.parsing.Parser as parser
from core.calculations.cancelled import CalculationAborted
from core.graphs.graph_builder import build_graphs_from_data, get_graph_names_to_build


class SingleCalculationWorker(QObject):
    """Runs parse → calculate → graph build off the UI thread."""

    ok = pyqtSignal(object)  # payload dict
    err = pyqtSignal(str)
    cancelled = pyqtSignal()
    graph_progress = pyqtSignal(int, int, str)  # n, total, graph name

    def __init__(self, csv_path: str, config: dict[str, Any], cancel_event: threading.Event):
        super().__init__()
        self._csv = csv_path
        self._config = config
        self._ce = cancel_event

    def _cancelled(self) -> bool:
        return self._ce.is_set()

    @pyqtSlot()
    def work(self) -> None:
        th = self.thread()
        try:
            if self._cancelled():
                self.cancelled.emit()
                return
            try:
                parsed_points = parser.parse_dlc_csv(self._csv, self._config)
            except Exception as e:
                self.err.emit(str(e))
                return
            if self._cancelled():
                self.cancelled.emit()
                return
            try:
                results = calculations.run_calculations(
                    parsed_points, self._config, cancel_check=self._cancelled
                )
            except CalculationAborted:
                self.cancelled.emit()
                return
            except Exception as e:
                self.err.emit(str(e))
                return
            if results is None:
                self.err.emit("The calculation pipeline returned no results.")
                return
            if self._cancelled():
                self.cancelled.emit()
                return

            payload = {
                "results_df": results,
                "config": self._config,
                "csv_path": self._csv,
                "parsed_points": parsed_points,
            }
            if len(get_graph_names_to_build(payload)) == 0:
                self.ok.emit(payload)
                return

            def _prog(n: int, tot: int, gname: str) -> None:
                self.graph_progress.emit(n, tot, gname)

            try:
                graphs, cfg = build_graphs_from_data(payload, _prog, self._cancelled)
            except CalculationAborted:
                self.cancelled.emit()
                return
            payload["_prebuilt_graphs"] = graphs
            payload["_prebuilt_config"] = cfg
            self.ok.emit(payload)
        finally:
            if th is not None:
                th.quit()
