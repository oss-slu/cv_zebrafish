"""Background export of folder-run Plotly figures to HTML/PNG (keeps GUI thread free)."""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import plotly.graph_objs as go
import plotly.io as pio
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from src.core.calculations.cancelled import CalculationAborted


def _safe_filename(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", title).strip("_")


def _safe_dirname(name: str) -> str:
    return _safe_filename(name) or "item"


def _is_kaleido_available() -> bool:
    try:
        import kaleido  # noqa: F401
    except Exception:
        return False
    return True

AssetRecord = Tuple[str, str, str, str]


def run_folder_graph_save_core(
    *,
    session_root: Path,
    csv_folder_id: str,
    csv_files: List[str],
    config_path: str,
    graphs_by_csv: Dict[str, Dict[str, Any]],
    cancel_check: Callable[[], bool],
    on_progress: Optional[Callable[[int, int, str], None]],
) -> List[AssetRecord]:
    """
    Write each ``go.Figure`` to disk under session folders; return rows for
    :meth:`session.Session.addFolderGraph`.
    """
    if not csv_folder_id or not config_path:
        return []

    base = session_root / "folders" / _safe_dirname(Path(csv_folder_id).name)
    base.mkdir(parents=True, exist_ok=True)

    used_csv_dirnames = set()
    csv_dir_for_path: Dict[str, Path] = {}
    for csv_path in csv_files or []:
        stem = Path(csv_path).stem
        dname = _safe_dirname(stem)
        if dname in used_csv_dirnames:
            i = 2
            while f"{dname}_{i}" in used_csv_dirnames:
                i += 1
            dname = f"{dname}_{i}"
        used_csv_dirnames.add(dname)
        out_dir = base / dname
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_dir_for_path[csv_path] = out_dir

    n_total = sum(
        sum(1 for s in (g or {}).values() if isinstance(s, go.Figure))
        for g in (graphs_by_csv or {}).values()
    )
    done = 0
    records: List[AssetRecord] = []

    for csv_path, graphs in (graphs_by_csv or {}).items():
        out_dir = csv_dir_for_path.get(csv_path)
        if out_dir is None:
            continue
        csv_label = Path(csv_path).name
        for title, src in (graphs or {}).items():
            if not isinstance(src, go.Figure):
                continue
            if cancel_check():
                raise CalculationAborted()
            done += 1
            if on_progress is not None and n_total > 0:
                on_progress(done, n_total, f"{csv_label}  —  {title}")
            try:
                fname = _safe_filename(title) or "graph"
                html_path = out_dir / f"{fname}.html"
                png_path = out_dir / f"{fname}.png"

                pio.write_html(
                    src,
                    file=str(html_path),
                    include_plotlyjs="cdn",
                    auto_open=False,
                )
                wrote_png = False
                if _is_kaleido_available():
                    try:
                        png_bytes = pio.to_image(src, format="png", scale=2)
                        png_path.write_bytes(png_bytes)
                        wrote_png = True
                    except Exception:
                        wrote_png = False

                if wrote_png and png_path.exists():
                    records.append(
                        (csv_folder_id, config_path, csv_path, str(png_path))
                    )
                if html_path.exists():
                    records.append(
                        (csv_folder_id, config_path, csv_path, str(html_path))
                    )
            except Exception:
                pass

    return records


class FolderGraphSaveWorker(QObject):
    """Runs :func:`run_folder_graph_save_core` on a worker thread."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        session_root: Path,
        csv_folder_id: str,
        csv_files: List[str],
        config_path: str,
        graphs_by_csv: Dict[str, Dict[str, Any]],
        cancel_event: threading.Event,
    ):
        super().__init__()
        self._session_root = Path(session_root)
        self._csv_folder_id = csv_folder_id
        self._csv_files = list(csv_files or [])
        self._config_path = config_path
        self._graphs_by_csv = graphs_by_csv
        self._ce = cancel_event

    def _emit_progress(self, done: int, total: int, msg: str) -> None:
        self.progress.emit(done, total, msg)

    @pyqtSlot()
    def run(self) -> None:
        th = self.thread()
        try:
            records = run_folder_graph_save_core(
                session_root=self._session_root,
                csv_folder_id=self._csv_folder_id,
                csv_files=self._csv_files,
                config_path=self._config_path,
                graphs_by_csv=self._graphs_by_csv,
                cancel_check=self._ce.is_set,
                on_progress=self._emit_progress,
            )
            self.finished.emit(records)
        except CalculationAborted:
            self.cancelled.emit()
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            if th is not None:
                th.quit()
