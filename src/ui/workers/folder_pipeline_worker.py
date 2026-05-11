"""Background folder-run pipeline: parse → metrics → graph build (off UI thread)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from src.core.calculations.cancelled import CalculationAborted

from ui.main_panels.graph_viewer_widget import (
    build_graphs_from_data,
    get_graph_names_to_build,
)


class FolderPipelineError(Exception):
    """User-visible failure while processing a folder run."""

    pass


def run_folder_pipeline_core(
    data: Dict[str, Any],
    cancel_event: threading.Event,
    on_progress: Callable[[int, int, str], None],
) -> Dict[str, Any]:
    """
    Parse all CSVs, run metrics, build figures. Raises CalculationAborted or FolderPipelineError.
    on_progress(step, total_steps, status_text)
    """
    if cancel_event.is_set():
        raise CalculationAborted()

    csv_files = list(data.get("csv_files") or [])
    config = data.get("config") or {}
    config_path = data.get("config_path") or (
        config.get("config_path") if isinstance(config, dict) else None
    )
    csv_folder_id = data.get("csv_folder")

    if not csv_files or not isinstance(config, dict):
        raise FolderPipelineError("Folder payload is missing CSV files or config.")
    if not csv_folder_id or not config_path:
        raise FolderPipelineError("Folder payload is missing folder id or config path.")

    total_files = len(csv_files)
    tot_phase1 = 5 * max(1, total_files) + 3
    step = 0
    results_by_csv: Dict[str, Any] = {}
    parsed_by_csv: Dict[str, Any] = {}
    g_counts: List[int] = []

    for idx, csv_path in enumerate(csv_files, start=1):
        if cancel_event.is_set():
            raise CalculationAborted()
        base = f"({idx}/{total_files})  {Path(csv_path).name}"
        step += 1
        on_progress(step, tot_phase1, f"{base}  —  reading")
        try:
            parsed_points = parser.parse_dlc_csv(csv_path, config)
        except Exception as exc:
            raise FolderPipelineError(f"Failed on {csv_path}:\n{exc}") from exc

        if cancel_event.is_set():
            raise CalculationAborted()
        step += 1
        on_progress(step, tot_phase1, f"{base}  —  computing…")
        try:
            results_df = calculations.run_calculations(
                parsed_points, config, cancel_check=cancel_event.is_set
            )
        except CalculationAborted:
            raise
        except Exception as exc:
            raise FolderPipelineError(f"Failed on {csv_path}:\n{exc}") from exc

        results_by_csv[csv_path] = results_df
        parsed_by_csv[csv_path] = parsed_points
        payload = {
            "results_df": results_df,
            "config": config,
            "csv_path": csv_path,
            "parsed_points": parsed_points,
        }
        g_counts.append(len(get_graph_names_to_build(payload)))

    total_graphs = int(sum(g_counts))
    if total_graphs <= 0:
        raise FolderPipelineError(
            "No graphs were requested or available for this config."
        )

    total_steps = 2 * total_files + 2 * total_graphs + 2
    on_progress(
        2 * total_files,
        total_steps,
        "All metrics ready — building graphs…",
    )

    step = 2 * total_files
    file_payloads = [
        (
            p,
            {
                "results_df": results_by_csv[p],
                "config": config,
                "csv_path": p,
                "parsed_points": parsed_by_csv[p],
            },
        )
        for p in csv_files
    ]
    graphs_by_csv: Dict[str, Dict[str, Any]] = {}

    for csv_path, payload in file_payloads:
        if cancel_event.is_set():
            raise CalculationAborted()

        def progress_callback2(
            n: int, gtotal: int, graph_name: str, _csv: str = csv_path
        ) -> None:
            nonlocal step
            if cancel_event.is_set():
                raise CalculationAborted()
            step += 1
            on_progress(
                step,
                total_steps,
                f"{Path(_csv).name}  —  {n}/{gtotal}  —  {graph_name}",
            )

        graphs, _cfg = build_graphs_from_data(
            payload, progress_callback2, cancel_event.is_set
        )
        if graphs is None:
            continue
        graphs_by_csv[csv_path] = graphs

    if not graphs_by_csv:
        raise FolderPipelineError("Graphs could not be generated for this folder.")

    return {
        "graphs_by_csv": graphs_by_csv,
        "results_by_csv": results_by_csv,
        "csv_files": csv_files,
        "config": config,
        "config_path": config_path,
        "csv_folder_id": csv_folder_id,
        "total_graphs": total_graphs,
        "total_files": total_files,
    }


class FolderPipelineWorker(QObject):
    """Runs :func:`run_folder_pipeline_core` on a worker thread."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, data: Dict[str, Any], cancel_event: threading.Event):
        super().__init__()
        self._data = data
        self._ce = cancel_event

    def _emit_progress(self, step: int, total: int, msg: str) -> None:
        self.progress.emit(step, total, msg)

    @pyqtSlot()
    def run(self) -> None:
        th = self.thread()
        try:
            try:
                out = run_folder_pipeline_core(self._data, self._ce, self._emit_progress)
                self.finished.emit(out)
            except CalculationAborted:
                self.cancelled.emit()
            except FolderPipelineError as e:
                self.failed.emit(str(e))
            except Exception as e:
                self.failed.emit(str(e))
        finally:
            if th is not None:
                th.quit()
