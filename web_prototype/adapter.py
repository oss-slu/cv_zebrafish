"""Web-facing adapter around the existing analysis core (spike for #136).

No web framework imports here: this module only turns uploaded bytes into the
same calls the desktop app makes, so it can be tested with plain pytest and
reused by whichever framework the team picks.

Reuse notes (see README "What blocks reuse"):
- The core reads files by path (``verify_deeplabcut_csv`` checks ``os.path.isfile``),
  so uploads are written to a temporary file first.
- The fin/tail figure glue lives in ``ui/main_panels/graph_viewer_widget.py``, which
  imports PyQt. ``fin_tail_figure`` below mirrors ``_iter_fin_tail_graphs`` until
  #133 moves that glue into the core.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from src.core.calculations.Driver import run_calculations  # noqa: E402
from src.core.graphs.loader_bundle import GraphDataBundle  # noqa: E402
from src.core.graphs.plots.fin_tail import render_fin_tail  # noqa: E402
from src.core.parsing.Parser import parse_dlc_csv  # noqa: E402
from src.core.validation.csv_verifier import list_bodyparts, verify_deeplabcut_csv  # noqa: E402

SAMPLE_CONFIG_PATH = REPO_ROOT / "data" / "samples" / "jsons" / "BaseConfig.json"
SAMPLE_CSV_PATH = REPO_ROOT / "data" / "samples" / "csv" / "correct_format.csv"

# Columns shown in the summary table: (results column, label, unit).
SUMMARY_COLUMNS = (
    ("LF_Angle", "Left fin angle", "deg"),
    ("RF_Angle", "Right fin angle", "deg"),
    ("Tail_Distance", "Tail distance", "scaled units"),
    ("HeadYaw", "Head yaw", "deg"),
)


@dataclass
class AnalysisResult:
    """Everything the web page needs from one run."""

    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    results: Optional[pd.DataFrame] = None
    config: Dict[str, Any] = field(default_factory=dict)


def load_sample_config() -> Dict[str, Any]:
    return json.loads(SAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))


def config_bodyparts(config: Dict[str, Any]) -> List[str]:
    """Body-part names the config's ``points`` section refers to."""
    points = (config or {}).get("points") or {}
    names: List[str] = []
    for value in points.values():
        items = value.values() if isinstance(value, dict) else (value if isinstance(value, list) else [value])
        names.extend(str(v) for v in items)
    return sorted(set(names))


def analyze_csv_bytes(data: bytes, config: Dict[str, Any], filename: str = "upload.csv") -> AnalysisResult:
    """Validate and analyze one DeepLabCut CSV given as raw bytes."""
    suffix = Path(filename).suffix.lower() or ".csv"
    if suffix != ".csv":
        return AnalysisResult(ok=False, errors=[f"Only DeepLabCut .csv files are supported in this prototype (got {suffix})."])

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(filename).name
        path.write_bytes(data)

        try:
            errors, warnings = verify_deeplabcut_csv(str(path))
        except Exception as exc:  # the verifier can raise on badly malformed files
            return AnalysisResult(ok=False, errors=[f"This doesn't look like a DeepLabCut CSV ({exc})."])
        if errors:
            return AnalysisResult(ok=False, errors=list(errors), warnings=list(warnings))

        # The parser silently fills missing body parts with NaN, which yields an
        # all-empty "successful" result (e.g. a mouse file with the zebrafish config).
        in_file = {str(b) for b in list_bodyparts(str(path))}
        missing = [b for b in config_bodyparts(config) if b not in in_file]
        if missing:
            return AnalysisResult(
                ok=False,
                errors=[
                    "The config refers to body parts that aren't in this file: "
                    + ", ".join(missing)
                    + ". File has: " + ", ".join(sorted(in_file)) + "."
                ],
                warnings=list(warnings),
            )

        try:
            parsed = parse_dlc_csv(str(path), config)
            results = run_calculations(parsed, config)
        except Exception as exc:  # surface core errors to the page instead of crashing it
            return AnalysisResult(
                ok=False,
                errors=[f"Analysis failed: {exc}. Check that the config's body-part names match the file."],
                warnings=list(warnings),
            )

    return AnalysisResult(ok=True, warnings=list(warnings), results=results, config=config)


def summary_table(results: pd.DataFrame) -> pd.DataFrame:
    """Mean / min / max for the headline measurements present in ``results``."""
    rows = []
    for col, label, unit in SUMMARY_COLUMNS:
        if col not in results.columns:
            continue
        s = pd.to_numeric(results[col], errors="coerce")
        rows.append({"Measurement": label, "Unit": unit, "Mean": s.mean(), "Min": s.min(), "Max": s.max()})
    return pd.DataFrame(rows)


def fin_tail_figure(results: pd.DataFrame, config: Dict[str, Any]) -> tuple[Optional[go.Figure], List[str]]:
    """Fin angles + tail distance plot, built the same way as the desktop graph viewer."""
    warnings: List[str] = []
    cfg = dict(config or {})
    required = {"leftFinAngles": "LF_Angle", "rightFinAngles": "RF_Angle", "tailDistances": "Tail_Distance"}
    missing = [c for c in required.values() if c not in results.columns]
    if missing:
        return None, [f"Fin/tail plot skipped; missing columns: {', '.join(missing)}."]

    cfg["shown_outputs"] = {**(cfg.get("shown_outputs") or {}), "show_angle_and_distance_plot": True}
    cfg["angle_and_distance_plot_settings"] = {**(cfg.get("angle_and_distance_plot_settings") or {}), "open_plot": False}
    cfg["open_plots"] = False

    time_ranges = cfg.get("time_ranges") or [[0, len(results) - 1]]
    calculated = {key: results[col].to_numpy() for key, col in required.items()}
    if "HeadYaw" in results.columns:
        calculated["headYaw"] = results["HeadYaw"].to_numpy()

    bundle = GraphDataBundle(
        time_ranges=[list(tr) for tr in time_ranges],
        input_values={},
        calculated_values=calculated,
        config=cfg,
        dataframe=results,
    )
    result = render_fin_tail(bundle, ctx=None)
    warnings.extend(result.warnings)
    return (result.figures[0] if result.figures else None), warnings
