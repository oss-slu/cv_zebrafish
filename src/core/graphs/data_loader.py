#!/usr/bin/env python3
"""
GraphDataLoader — Structured Data Loader for Plotting Modules

This module provides a unified, well-documented entry point (`GraphDataLoader`) that supplies graphing modules with
validated, structured time-series and aggregate metric data, as well as runtime configuration. Its design decouples
data parsing from visualization, enforces data contracts via dataclasses, and supports robust error handling.

It was created to:
- Guarantee a consistent API for downstream graphs so that column and schema changes only affect this loader.
- Surface parsed results as domain objects, NOT raw pandas Series or DataFrame slices.
- Fail clearly when required data is missing—with actionable errors for analytics or engineering follow-up.

See the bottom of the file or the class docstring for usage examples.

Satisfies these requirements from the project plan:
- Single, documented entry point for all graphing data needs.
- Decouples CSV/config parsing from visualization logic.
- Uses dataclasses/dictionaries for structured returns, enforcing data contracts.
- Surfaces accessor APIs to get bouts, per-frame metrics, spines, pixel trajectories, and config.
- Handles error cases—missing columns, malformed inputs, schema drift—via explicit exceptions with guidance.
- Readily testable: parse, accessor, and error logic are simple to mock and cover in unit tests.

"""

import pandas as pd
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
from dataclasses import dataclass

# ----------------- Constants & Data Contracts -----------------
class Schema:
    """
    Centralizes all analytic column names and schema requirements.
    Update this as your exports evolve to reduce brittle dependencies downstream.
    
    Column Patterns:
        - Spine points: Spine_{label}_x, Spine_{label}_y, Spine_{label}_conf
        - Left fin: LeftFin_{label}_x, LeftFin_{label}_y, LeftFin_{label}_conf
        - Right fin: RightFin_{label}_x, RightFin_{label}_y, RightFin_{label}_conf
        - Tail: Tail_{label}_x, Tail_{label}_y, Tail_{label}_conf
        - DLC raw: DLC_HeadPX, DLC_HeadPY, DLC_HeadPConf, DLC_TailPX, DLC_TailPY, DLC_TailPConf
        - Tail angles: TailAngle_0, TailAngle_1, ..., TailAngle_11
        - Bout metadata: bout_num, bout_start, bout_end, bout_* (aggregate metrics)
        - Time ranges: timeRangeStart_N, timeRangeEnd_N (in row 0)
    """
    # Core time series metrics
    TIME = "Time"
    LF_ANGLE = "LF_Angle"
    RF_ANGLE = "RF_Angle"
    L_EYE_ANGLE = "L_Eye_Angle"
    R_EYE_ANGLE = "R_Eye_Angle"
    HEAD_YAW = "HeadYaw"
    HEAD_X = "HeadX"
    HEAD_Y = "HeadY"
    TAIL_DISTANCE = "Tail_Distance"
    TAIL_DISTANCE_PIXELS = "Tail_Distance_Pixels"
    TAIL_ANGLE = "Tail_Angle"
    TAIL_SIDE = "Tail_Side"
    FURTHEST_TAIL_POINT = "Furthest_Tail_Point"
    
    # Pixel space coordinates (used for movement plots/heatmaps)
    HEAD_PX = "HeadPX"
    HEAD_PY = "HeadPY"
    TAIL_PX = "TailPX"
    TAIL_PY = "TailPY"
    
    # DLC raw outputs
    DLC_HEAD_PX = "DLC_HeadPX"
    DLC_HEAD_PY = "DLC_HeadPY"
    DLC_HEAD_CONF = "DLC_HeadPConf"
    DLC_TAIL_PX = "DLC_TailPX"
    DLC_TAIL_PY = "DLC_TailPY"
    DLC_TAIL_CONF = "DLC_TailPConf"
    
    # Bout metadata columns
    BOUT_NUM = "bout_num"
    BOUT_START = "bout_start"
    BOUT_END = "bout_end"
    
    # Column name patterns (prefixes for iteration)
    SPINE_PREFIX = "Spine_"
    LEFT_FIN_PREFIX = "LeftFin_"
    RIGHT_FIN_PREFIX = "RightFin_"
    TAIL_PREFIX = "Tail_"
    TAIL_ANGLE_PREFIX = "TailAngle_"
    BOUT_AGGREGATE_PREFIX = "bout_"
    
    # Metadata in row 0
    METADATA_PREFIXES = ["timeRangeStart_", "timeRangeEnd_"]
    
    @staticmethod
    def get_spine_columns(label: str) -> tuple:
        """Returns (x_col, y_col, conf_col) for a spine point label."""
        return (f"Spine_{label}_x", f"Spine_{label}_y", f"Spine_{label}_conf")
    
    @staticmethod
    def get_fin_columns(side: str, label: str) -> tuple:
        """Returns (x_col, y_col, conf_col) for a fin point. Side: 'LeftFin' or 'RightFin'."""
        return (f"{side}_{label}_x", f"{side}_{label}_y", f"{side}_{label}_conf")
    
    @staticmethod
    def get_tail_columns(label: str) -> tuple:
        """Returns (x_col, y_col, conf_col) for a tail point label."""
        return (f"Tail_{label}_x", f"Tail_{label}_y", f"Tail_{label}_conf")

REQUIRED_COLUMNS = [
    Schema.TIME, Schema.LF_ANGLE, Schema.RF_ANGLE,
    Schema.HEAD_YAW, Schema.TAIL_DISTANCE, Schema.TAIL_ANGLE
]
# Extend this list as needed per analytic requirements

@dataclass(frozen=True)
class BoutRange:
    """
    Models one bout (contiguous activity segment) for plotting and timeseries slicing.

    Attributes:
        start_frame (int): Start index of bout (row in CSV/DataFrame).
        end_frame (int): End index of bout.
        duration (float): Duration in time units from start to end.
        n_frames (int): Number of frames in the bout.
    """
    start_frame: int
    end_frame: int
    duration: float
    n_frames: int

@dataclass(frozen=True)
class TimeSeriesFrame:
    """
    Data contract for a single frame's metrics as needed for time series graphs.

    Attributes:
        idx (int): Frame index in original CSV/export.
        time (float): Time for this frame, from the Time column.
        metrics (Dict[str, Any]): Dictionary of all required per-frame metric columns.
        tail_side (Optional[str]): Categorical value for side-swimming or other behavior.
        furthest_tail_point (Optional[int]): Categorical or label index, if present.
    """
    idx: int
    time: float
    metrics: Dict[str, Any]
    tail_side: Optional[str] = None
    furthest_tail_point: Optional[int] = None

@dataclass(frozen=True)
class SpineFrame:
    """
    Contract for one frame's spine data with N body points and their confidences.

    Attributes:
        points (List[Dict[str, float]]): Each dict gives x/y/confidence for an anatomically meaningful point.
    """
    points: List[Dict[str, float]]

@dataclass(frozen=True)
class PixelTrack:
    """
    Models the trajectory (pixel positions) of labeled points within one frame.

    Attributes:
        frame (int): Frame index in the video/CSV.
        points (List[Dict[str, float]]): Each dict gives x/y for a tracked pixel-labeled structure.
    """
    frame: int
    points: List[Dict[str, float]]

# ----------------- Exceptions -----------------
class LoaderError(Exception):
    """Generic base for all loader exceptions (parsing, data contract, IO)."""
    pass

class MissingColumnError(LoaderError):
    """Raised if a required column is missing from the input CSV."""
    pass

class MalformedBoutRangeError(LoaderError):
    """Raised if bout start/end markers are invalid or missing."""
    pass

class InconsistentLengthError(LoaderError):
    """Raised when arrays/lists parsed do not have equal lengths."""
    pass

# ----------------- Loader Implementation -----------------
class GraphDataLoader:
    """
    Loads and parses enriched CSV and runtime config as a stable, testable data contract for plotters.

    Initialization:
        loader = GraphDataLoader(csv_path="data.csv", config_path="config.json")
    All accessors and iterators are methods on the loader.

    Key Responsibilities:
      - Loads, parses, and validates the expected CSV schema (including row zero aggregates).
      - Supplies all graphing modules with well-documented, structured data (no raw column lookups outside loader).
      - Exposes accessor API for frames, bouts, annotations, config, etc.
      - Performs robust error handling and validation for rapid troubleshooting.

    See example_usage() for a practical illustration.

    Parameters:
        csv_path (str): File path to calculated/enriched CSV.
        config_path (str): File path to runtime or export config in JSON.
        overrides (dict, optional): Dictionary of config overrides for runtime tests or injected settings.
    """
    def __init__(self, csv_path: str, config_path: str, overrides: Optional[Dict[str, Any]] = None):
        self.csv_path = Path(csv_path)
        self.config_path = Path(config_path)
        self.config = self._load_config(config_path)
        self.df = pd.read_csv(self.csv_path)
        self._validate_columns()
        self.time_ranges = self._parse_time_ranges()
        if overrides:
            self.config.update(overrides)
        self._frame_count = len(self.df)
        self._bout_ranges = self._assemble_bout_ranges()

    def _load_config(self, path: str) -> Dict[str, Any]:
        """
        Loads a JSON configuration file for global settings required by graphs.

        Raises:
            LoaderError if config cannot be loaded or parsed.
        """
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise LoaderError(f"Failed to load config: {e}")

    def _validate_columns(self):
        """
        Checks for presence of all required columns (see REQUIRED_COLUMNS).
        Raises descriptive error if any are missing.
        """
        missing = [col for col in REQUIRED_COLUMNS if col not in self.df.columns]
        if missing:
            raise MissingColumnError(f"Missing required columns: {missing}")

    def _parse_time_ranges(self) -> List[List[int]]:
        """
        Extracts all valid bout start/end frame-pair markers from row 0, according to naming conventions.

        Returns:
            List of [start, end] frame indices as int.

        Raises:
            MalformedBoutRangeError if start/end indices are non-numeric or inconsistent.
        """
        ranges = []
        i = 0
        while f"timeRangeStart_{i}" in self.df.columns:
            start = self.df[f"timeRangeStart_{i}"].iloc[0]
            end = self.df[f"timeRangeEnd_{i}"].iloc[0]
            if pd.isna(start) or pd.isna(end):
                break
            try:
                s, e = int(float(start)), int(float(end))
            except Exception:
                raise MalformedBoutRangeError(
                    f"Malformed time ranges at index {i}: start={start}, end={end}.")
            if s <= e:
                ranges.append([s, e])
            i += 1
        return ranges if ranges else [[0, self._frame_count - 1]]

    def _assemble_bout_ranges(self) -> List[BoutRange]:
        """
        Converts list of frame indices from _parse_time_ranges to strongly-typed BoutRange dataclasses.
        """
        bouts = []
        for start, end in self.time_ranges:
            if end < start:
                raise MalformedBoutRangeError(f"Bout range end < start: {start} -> {end}")
            duration = self.df[Schema.TIME].iloc[end] - self.df[Schema.TIME].iloc[start]
            n_frames = end - start + 1
            bouts.append(BoutRange(start, end, duration, n_frames))
        return bouts

    def iter_frames(self, bout: Optional[BoutRange] = None) -> Iterator[TimeSeriesFrame]:
        """
        Yields full TimeSeriesFrame dataclasses for each frame to enable precise plotting and state tracking.
        Optionally filters to frames in a single bout.

        Parameters:
            bout (BoutRange, optional): Restricts yield to [start_frame, end_frame] of given bout.
        """
        start, end = (bout.start_frame, bout.end_frame) if bout else (0, self._frame_count - 1)
        for idx in range(start, end + 1):
            row = self.df.iloc[idx]
            metrics = {col: row[col] for col in REQUIRED_COLUMNS}
            tail_side = row.get(Schema.TAIL_SIDE, None)
            furthest_tail_point = row.get(Schema.FURTHEST_TAIL_POINT, None)
            yield TimeSeriesFrame(
                idx=idx,
                time=row[Schema.TIME],
                metrics=metrics,
                tail_side=tail_side,
                furthest_tail_point=furthest_tail_point
            )

    def get_bouts(self) -> List[BoutRange]:
        """
        Returns complete list of BoutRange objects in frame order.
        Satisfies plan requirement for bout access and allows graphers to restrict or aggregate data as needed.
        """
        return self._bout_ranges

    def get_fin_peaks(self, side: str, bout: Optional[BoutRange] = None) -> List[int]:
        """
        Yields indices at which peaks (flicks/turns) occur for left or right fin, optionally filtered to a bout.
        Assumes peak indices are stored as a serialized JSON string or comma list in row 0.

        Parameters:
            side (str): 'left' or 'right'
            bout (BoutRange, optional): Restricts peaks to those occurring within given bout.

        Raises:
            LoaderError if peak column is absent or malformatted.
        """
        try:
            key = f"{side.capitalize()}Fin_Peaks"
            peaks = self.df[key].iloc[0]
            if isinstance(peaks, str):
                import json
                try:
                    peaks = json.loads(peaks)
                except Exception:
                    peaks = [int(p) for p in peaks.split(',') if p.strip()]
            if not isinstance(peaks, list):
                peaks = [peaks]
        except Exception:
            raise LoaderError(f"Peaks for '{side}' fin not found or invalid format.")
        if bout:
            peaks = [p for p in peaks if bout.start_frame <= p <= bout.end_frame]
        return peaks

    def get_spines(self, bout: Optional[BoutRange] = None) -> List[SpineFrame]:
        """
        Returns ordered list of SpineFrame objects representing full spine position w/confidence per frame.
        Parameters:
            bout (BoutRange, optional): Restrict to frames in the specified bout.
        """
        labels = self.config["points"]["spine"]
        start, end = (bout.start_frame, bout.end_frame) if bout else (0, self._frame_count - 1)
        spines = []
        for idx in range(start, end + 1):
            row = self.df.iloc[idx]
            pts = []
            for label in labels:
                x, y, conf = (
                    row.get(f"Spine_{label}_x", float("nan")),
                    row.get(f"Spine_{label}_y", float("nan")),
                    row.get(f"Spine_{label}_conf", float("nan")),
                )
                pts.append({"x": x, "y": y, "conf": conf})
            spines.append(SpineFrame(points=pts))
        return spines

    def get_pixel_tracks(self, bout: Optional[BoutRange] = None) -> List[PixelTrack]:
        """
        Returns ordered list of PixelTrack dataclasses for each frame, using label fields from config.
        Satisfies requirement for exporting trajectories for custom graphing/animation.
        """
        track_labels = self.config.get("points", {}).get("pixel_tracks", [])
        start, end = (bout.start_frame, bout.end_frame) if bout else (0, self._frame_count - 1)
        tracks = []
        for idx in range(start, end + 1):
            row = self.df.iloc[idx]
            pts = []
            for label in track_labels:
                x = row.get(f"{label}_x", float("nan"))
                y = row.get(f"{label}_y", float("nan"))
                pts.append({"x": x, "y": y})
            tracks.append(PixelTrack(frame=idx, points=pts))
        return tracks

    def get_config(self) -> Dict[str, Any]:
        """
        Returns defensive copy of configuration dictionary with all needed plotting constants, paths, and cutoffs.
        Satisfies requirement for downstream use by graphing modules and reproducible runs.
        """
        return dict(self.config)

    def get_dataframe(self) -> pd.DataFrame:
        """
        Returns the raw DataFrame for advanced use, e.g., exploratory visualization or ad hoc metrics.
        """
        return self.df

    # --------------- Legacy Bridge Methods ---------------
    # These methods provide backward compatibility with outputDisplay.py
    # which expects specific nested dictionary structures.
    
    def get_time_ranges(self) -> List[List[int]]:
        """
        Returns time ranges as list of [start, end] frame indices.
        
        Legacy compatibility method for outputDisplay.py.
        Modern code should use get_bouts() which returns BoutRange dataclasses.
        
        Returns:
            List of [start_frame, end_frame] pairs, e.g., [[119, 225], [529, 630], ...]
        """
        return self.time_ranges

    def get_input_values(self) -> Dict[str, Any]:
        """
        Reconstructs inputValues nested dictionary structure expected by legacy outputDisplay.py.
        
        This method transforms the enriched CSV columns back into the nested dictionary
        format that the legacy plotting code expects. Each anatomical structure (spine,
        fins, tail) is represented as a list of dictionaries containing x, y, and
        confidence arrays for all frames.
        
        Returns:
            Dictionary with keys:
                - 'spine': List of dicts, one per spine point, each with 'x', 'y', 'conf' arrays
                - 'left_fin': List of dicts for left fin points
                - 'right_fin': List of dicts for right fin points
                - 'tail': List of dicts for tail points
                - 'tailPoints': List of tail point labels
                - 'head': Single dict with 'x', 'y', 'conf' arrays for head position
                - 'tp': Single dict with 'x', 'y', 'conf' arrays for tail base position
                - 'clp1', 'clp2': References to spine points used for head centerline
        
        Example structure:
            {
                'spine': [
                    {'x': array([...]), 'y': array([...]), 'conf': array([...])},  # Point 0
                    {'x': array([...]), 'y': array([...]), 'conf': array([...])},  # Point 1
                    ...
                ],
                'left_fin': [...],
                'right_fin': [...],
                'tail': [...],
                'tailPoints': ['0', '1', '2', ...],
                'head': {'x': array([...]), 'y': array([...]), 'conf': array([...])},
                'tp': {'x': array([...]), 'y': array([...]), 'conf': array([...])},
                'clp1': {...},  # Reference to spine point
                'clp2': {...}   # Reference to spine point
            }
        """
        import numpy as np
        
        # Get point labels from config
        spine_labels = self.config["points"]["spine"]
        left_fin_labels = self.config["points"]["left_fin"]
        right_fin_labels = self.config["points"]["right_fin"]
        tail_labels = self.config["points"]["tail"]
        
        inputValues = {}
        
        # Reconstruct spine
        inputValues["spine"] = []
        for label in spine_labels:
            col_prefix = f"Spine_{label}"
            x = self.df.get(f"{col_prefix}_x", pd.Series([np.nan]*len(self.df))).values
            y = self.df.get(f"{col_prefix}_y", pd.Series([np.nan]*len(self.df))).values
            conf = self.df.get(f"{col_prefix}_conf", pd.Series([1.0]*len(self.df))).values
            inputValues["spine"].append({"x": x, "y": y, "conf": conf})
        
        # Reconstruct left fin
        inputValues["left_fin"] = []
        for label in left_fin_labels:
            col_prefix = f"LeftFin_{label}"
            x = self.df.get(f"{col_prefix}_x", pd.Series([np.nan]*len(self.df))).values
            y = self.df.get(f"{col_prefix}_y", pd.Series([np.nan]*len(self.df))).values
            conf = self.df.get(f"{col_prefix}_conf", pd.Series([1.0]*len(self.df))).values
            inputValues["left_fin"].append({"x": x, "y": y, "conf": conf})
        
        # Reconstruct right fin
        inputValues["right_fin"] = []
        for label in right_fin_labels:
            col_prefix = f"RightFin_{label}"
            x = self.df.get(f"{col_prefix}_x", pd.Series([np.nan]*len(self.df))).values
            y = self.df.get(f"{col_prefix}_y", pd.Series([np.nan]*len(self.df))).values
            conf = self.df.get(f"{col_prefix}_conf", pd.Series([1.0]*len(self.df))).values
            inputValues["right_fin"].append({"x": x, "y": y, "conf": conf})
        
        # Reconstruct tail
        inputValues["tail"] = []
        inputValues["tailPoints"] = tail_labels
        for label in tail_labels:
            col_prefix = f"Tail_{label}"
            x = self.df.get(f"{col_prefix}_x", pd.Series([np.nan]*len(self.df))).values
            y = self.df.get(f"{col_prefix}_y", pd.Series([np.nan]*len(self.df))).values
            conf = self.df.get(f"{col_prefix}_conf", pd.Series([1.0]*len(self.df))).values
            inputValues["tail"].append({"x": x, "y": y, "conf": conf})
        
        # Reconstruct single-point markers (head, tail base)
        inputValues["head"] = {
            "x": self.df.get("DLC_HeadPX", pd.Series([np.nan]*len(self.df))).values,
            "y": self.df.get("DLC_HeadPY", pd.Series([np.nan]*len(self.df))).values,
            "conf": self.df.get("DLC_HeadPConf", pd.Series([1.0]*len(self.df))).values
        }
        
        inputValues["tp"] = {
            "x": self.df.get("DLC_TailPX", pd.Series([np.nan]*len(self.df))).values,
            "y": self.df.get("DLC_TailPY", pd.Series([np.nan]*len(self.df))).values,
            "conf": self.df.get("DLC_TailPConf", pd.Series([1.0]*len(self.df))).values
        }
        
        # Reconstruct clp1 and clp2 (head centerline points) - references to spine points
        head_pt1 = self.config["points"]["head"]["pt1"]
        head_pt2 = self.config["points"]["head"]["pt2"]
        
        if head_pt1 in spine_labels:
            idx = spine_labels.index(head_pt1)
            inputValues["clp1"] = inputValues["spine"][idx]
        
        if head_pt2 in spine_labels:
            idx = spine_labels.index(head_pt2)
            inputValues["clp2"] = inputValues["spine"][idx]
        
        return inputValues

    def get_calculated_values(self) -> Dict[str, np.ndarray]:
        """
        Extracts calculated metrics as numpy arrays expected by legacy outputDisplay.py.
        
        This method pulls all the computed metrics (angles, distances, positions) from
        the enriched CSV and returns them in the dictionary format that the legacy
        plotting functions expect.
        
        Returns:
            Dictionary with metric names as keys mapping to numpy arrays:
                - headX, headY: Head position in meters
                - leftFinAngles, rightFinAngles: Fin angles in degrees
                - tailAngles: List of tail segment angles
                - tailDistances: Tail displacement from base
                - headYaw: Head orientation angle
                - headPixelsX, headPixelsY: Head position in pixel space
                - tailPixelsX, tailPixelsY: Tail base position in pixel space
        
        Example:
            {
                'headX': array([0.001, 0.002, ...]),
                'headY': array([0.001, 0.002, ...]),
                'leftFinAngles': array([45.2, 43.1, ...]),
                'rightFinAngles': array([47.3, 45.9, ...]),
                'tailAngles': array([10.2, 12.3, ...]),
                'tailDistances': array([0.0001, 0.0002, ...]),
                'headYaw': array([90.1, 91.2, ...]),
                'headPixelsX': array([512.3, 513.1, ...]),
                'headPixelsY': array([384.2, 385.3, ...]),
                'tailPixelsX': array([500.1, 501.2, ...]),
                'tailPixelsY': array([390.3, 391.1, ...])
            }
        """
        import numpy as np
        
        calculatedValues = {
            "headX": self.df.get("HeadX", pd.Series([0.0]*len(self.df))).values,
            "headY": self.df.get("HeadY", pd.Series([0.0]*len(self.df))).values,
            "leftFinAngles": self.df.get("LF_Angle", pd.Series([0.0]*len(self.df))).values,
            "rightFinAngles": self.df.get("RF_Angle", pd.Series([0.0]*len(self.df))).values,
            "tailAngles": self.df.get("Tail_Angle", pd.Series([0.0]*len(self.df))).values,
            "tailDistances": self.df.get("Tail_Distance", pd.Series([0.0]*len(self.df))).values,
            "headYaw": self.df.get("HeadYaw", pd.Series([0.0]*len(self.df))).values,
            "headPixelsX": self.df.get("HeadPX", pd.Series([0.0]*len(self.df))).values,
            "headPixelsY": self.df.get("HeadPY", pd.Series([0.0]*len(self.df))).values,
            "tailPixelsX": self.df.get("TailPX", pd.Series([0.0]*len(self.df))).values,
            "tailPixelsY": self.df.get("TailPY", pd.Series([0.0]*len(self.df))).values,
        }
        
        return calculatedValues

    def example_usage(self):
        """
        Example usage illustrating loader lifecycle and data accessors.

        loader = GraphDataLoader("metrics.csv", "BaseConfig.json")
        bouts = loader.get_bouts()
        # Iterate over frames in a chosen bout
        for bout in bouts:
            for frame in loader.iter_frames(bout):
                print(frame.idx, frame.metrics["HeadYaw"])
        # Get all bout peak locations for left fin
        for bout in bouts:
            print(loader.get_fin_peaks("left", bout))
        """
        pass

# --------------- Testing guidance ---------------
def _test_loader():
    """
    Quick smoke test and doc guidance on extending tests.

    If using pytest or unittest, test:
      - init passes with happy path fixture data
      - informative errors are raised for missing column/schemas
      - all accessors return correct type and length
      - get_config and get_dataframe match expected schema
    """
    sample_csv = "tests/fixtures/mini_metrics.csv"
    sample_cfg = "config/BaseConfig.json"
    loader = GraphDataLoader(sample_csv, sample_cfg)
    # Ensure at least one bout is available
    assert len(loader.get_bouts()) > 0
    # Check frame iterator yields expected type
    try:
        assert next(loader.iter_frames()) is not None
    except Exception as e:
        print("Test failed:", e)
    print("Loader basic test passed.")

if __name__ == "__main__":
    _test_loader()
