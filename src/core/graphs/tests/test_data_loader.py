#!/usr/bin/env python3
"""Unit tests for GraphDataLoader.

Test coverage:
- Initialization with valid CSV and config
- Column validation and error handling
- Time range parsing from row 0 metadata
- Bout range assembly
- Frame iteration with and without bout filtering
- Fin peak detection
- Spine and pixel track extraction
- Legacy bridge methods (get_input_values, get_calculated_values, get_time_ranges)
- Configuration override mechanism

Run with:
    pytest graphing/tests/test_data_loader.py -v
    python -m pytest graphing/tests/test_data_loader.py -v
"""
import pytest
import pandas as pd
import numpy as np
import json
import tempfile
from pathlib import Path
from typing import Dict, Any

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from graphs.data_loader import (
    GraphDataLoader,
    BoutRange,
    TimeSeriesFrame,
    SpineFrame,
    PixelTrack,
    LoaderError,
    MissingColumnError,
    MalformedBoutRangeError,
    InconsistentLengthError,
    Schema
)


# --------------- Fixtures ---------------

@pytest.fixture
def minimal_config() -> Dict[str, Any]:
    """Minimal configuration for testing."""
    return {
        "points": {
            "spine": ["0", "1", "2"],
            "left_fin": ["0", "1"],
            "right_fin": ["0", "1"],
            "tail": ["0", "1", "2"],
            "head": {"pt1": "0", "pt2": "1"}
        },
        "video_parameters": {
            "recorded_framerate": 30,
            "pixel_scale_factor": 1.0
        },
        "graph_cutoffs": {
            "left_fin_angle": 45.0,
            "right_fin_angle": 45.0
        }
    }


@pytest.fixture
def minimal_enriched_csv_data() -> pd.DataFrame:
    """Create minimal enriched CSV data for testing."""
    n_frames = 100
    data = {
        "Time": np.arange(n_frames),
        "LF_Angle": np.random.uniform(0, 90, n_frames),
        "RF_Angle": np.random.uniform(0, 90, n_frames),
        "HeadYaw": np.random.uniform(-180, 180, n_frames),
        "HeadX": np.random.uniform(0, 0.01, n_frames),
        "HeadY": np.random.uniform(0, 0.01, n_frames),
        "Tail_Distance": np.random.uniform(0, 0.001, n_frames),
        "Tail_Angle": np.random.uniform(-45, 45, n_frames),
        "Tail_Side": ["left"] * 50 + ["right"] * 50,
        "Furthest_Tail_Point": np.random.randint(0, 3, n_frames),
        "HeadPX": np.random.uniform(500, 600, n_frames),
        "HeadPY": np.random.uniform(300, 400, n_frames),
        "TailPX": np.random.uniform(480, 580, n_frames),
        "TailPY": np.random.uniform(310, 410, n_frames),
        # Time ranges in row 0
        "timeRangeStart_0": [10.0] + [""] * (n_frames - 1),
        "timeRangeEnd_0": [30.0] + [""] * (n_frames - 1),
        "timeRangeStart_1": [50.0] + [""] * (n_frames - 1),
        "timeRangeEnd_1": [70.0] + [""] * (n_frames - 1),
    }
    
    # Add spine columns
    for label in ["0", "1", "2"]:
        data[f"Spine_{label}_x"] = np.random.uniform(0, 0.01, n_frames)
        data[f"Spine_{label}_y"] = np.random.uniform(0, 0.01, n_frames)
        data[f"Spine_{label}_conf"] = np.random.uniform(0.8, 1.0, n_frames)
    
    # Add fin columns
    for side in ["LeftFin", "RightFin"]:
        for label in ["0", "1"]:
            data[f"{side}_{label}_x"] = np.random.uniform(0, 0.01, n_frames)
            data[f"{side}_{label}_y"] = np.random.uniform(0, 0.01, n_frames)
            data[f"{side}_{label}_conf"] = np.random.uniform(0.8, 1.0, n_frames)
    
    # Add tail columns
    for label in ["0", "1", "2"]:
        data[f"Tail_{label}_x"] = np.random.uniform(0, 0.01, n_frames)
        data[f"Tail_{label}_y"] = np.random.uniform(0, 0.01, n_frames)
        data[f"Tail_{label}_conf"] = np.random.uniform(0.8, 1.0, n_frames)
    
    # Add DLC raw columns
    data["DLC_HeadPX"] = data["HeadPX"]
    data["DLC_HeadPY"] = data["HeadPY"]
    data["DLC_HeadPConf"] = np.random.uniform(0.9, 1.0, n_frames)
    data["DLC_TailPX"] = data["TailPX"]
    data["DLC_TailPY"] = data["TailPY"]
    data["DLC_TailPConf"] = np.random.uniform(0.9, 1.0, n_frames)
    
    return pd.DataFrame(data)


@pytest.fixture
def temp_csv_and_config(minimal_enriched_csv_data, minimal_config):
    """Create temporary CSV and config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test_enriched.csv"
        config_path = Path(tmpdir) / "test_config.json"
        
        minimal_enriched_csv_data.to_csv(csv_path, index=False)
        
        with open(config_path, 'w') as f:
            json.dump(minimal_config, f)
        
        yield str(csv_path), str(config_path)


# --------------- Tests ---------------

def test_loader_initialization(temp_csv_and_config):
    """Test basic loader initialization."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    assert loader.df is not None
    assert len(loader.df) == 100
    assert loader.config is not None
    assert len(loader.time_ranges) == 2
    assert loader.time_ranges == [[10, 30], [50, 70]]


def test_missing_required_columns():
    """Test that missing required columns raise appropriate error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "bad.csv"
        config_path = Path(tmpdir) / "config.json"
        
        # Create CSV missing required columns
        df = pd.DataFrame({"Time": [0, 1, 2]})
        df.to_csv(csv_path, index=False)
        
        with open(config_path, 'w') as f:
            json.dump({"points": {"spine": [], "left_fin": [], "right_fin": [], "tail": [], "head": {}}}, f)
        
        with pytest.raises(MissingColumnError):
            GraphDataLoader(str(csv_path), str(config_path))


def test_get_bouts(temp_csv_and_config):
    """Test bout range extraction."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    bouts = loader.get_bouts()
    assert len(bouts) == 2
    assert isinstance(bouts[0], BoutRange)
    assert bouts[0].start == 10
    assert bouts[0].end == 30
    assert bouts[0].idx == 0
    assert bouts[1].start == 50
    assert bouts[1].end == 70


def test_iter_frames_all(temp_csv_and_config):
    """Test iterating over all frames."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    frames = list(loader.iter_frames())
    assert len(frames) == 100
    assert all(isinstance(f, TimeSeriesFrame) for f in frames)
    assert frames[0].idx == 0
    assert frames[99].idx == 99


def test_iter_frames_filtered_by_bout(temp_csv_and_config):
    """Test iterating over frames within a specific bout."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    bouts = loader.get_bouts()
    frames = list(loader.iter_frames(bouts[0]))
    
    assert len(frames) == 21  # 10 to 30 inclusive
    assert frames[0].idx == 10
    assert frames[-1].idx == 30


def test_get_fin_peaks(temp_csv_and_config):
    """Test fin peak detection."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    left_peaks = loader.get_fin_peaks("left")
    right_peaks = loader.get_fin_peaks("right")
    
    assert isinstance(left_peaks, list)
    assert isinstance(right_peaks, list)
    # Peaks should be frame indices
    assert all(isinstance(p, (int, np.integer)) for p in left_peaks)
    assert all(isinstance(p, (int, np.integer)) for p in right_peaks)


def test_get_spines(temp_csv_and_config):
    """Test spine frame extraction."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    spines = loader.get_spines()
    assert len(spines) == 100
    assert all(isinstance(s, SpineFrame) for s in spines)
    assert len(spines[0].points) == 3  # 3 spine points in fixture


def test_get_pixel_tracks(temp_csv_and_config):
    """Test pixel track extraction."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    tracks = loader.get_pixel_tracks()
    assert len(tracks) == 100
    assert all(isinstance(t, PixelTrack) for t in tracks)


def test_get_time_ranges_legacy(temp_csv_and_config):
    """Test legacy get_time_ranges method."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    time_ranges = loader.get_time_ranges()
    assert time_ranges == [[10, 30], [50, 70]]
    assert isinstance(time_ranges, list)
    assert all(isinstance(r, list) and len(r) == 2 for r in time_ranges)


def test_get_input_values_legacy(temp_csv_and_config):
    """Test legacy get_input_values bridge method."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    input_values = loader.get_input_values()
    
    # Check structure
    assert "spine" in input_values
    assert "left_fin" in input_values
    assert "right_fin" in input_values
    assert "tail" in input_values
    assert "tailPoints" in input_values
    assert "head" in input_values
    assert "tp" in input_values
    
    # Check spine structure
    assert len(input_values["spine"]) == 3
    assert all("x" in pt and "y" in pt and "conf" in pt for pt in input_values["spine"])
    assert all(len(pt["x"]) == 100 for pt in input_values["spine"])
    
    # Check fin structure
    assert len(input_values["left_fin"]) == 2
    assert len(input_values["right_fin"]) == 2
    
    # Check tail structure
    assert len(input_values["tail"]) == 3
    assert input_values["tailPoints"] == ["0", "1", "2"]


def test_get_calculated_values_legacy(temp_csv_and_config):
    """Test legacy get_calculated_values bridge method."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    calc_values = loader.get_calculated_values()
    
    # Check expected keys
    expected_keys = [
        "headX", "headY", "leftFinAngles", "rightFinAngles",
        "tailAngles", "tailDistances", "headYaw",
        "headPixelsX", "headPixelsY", "tailPixelsX", "tailPixelsY"
    ]
    for key in expected_keys:
        assert key in calc_values
        assert len(calc_values[key]) == 100


def test_configuration_override(temp_csv_and_config):
    """Test configuration override mechanism."""
    csv_path, config_path = temp_csv_and_config
    
    overrides = {"custom_param": 42, "video_parameters": {"recorded_framerate": 60}}
    loader = GraphDataLoader(csv_path, config_path, overrides=overrides)
    
    assert loader.config["custom_param"] == 42
    assert loader.config["video_parameters"]["recorded_framerate"] == 60


def test_get_config_defensive_copy(temp_csv_and_config):
    """Test that get_config returns a defensive copy."""
    csv_path, config_path = temp_csv_and_config
    loader = GraphDataLoader(csv_path, config_path)
    
    config1 = loader.get_config()
    config2 = loader.get_config()
    
    # Modify one copy
    config1["new_key"] = "value"
    
    # Should not affect the other copy
    assert "new_key" not in config2
    assert "new_key" not in loader.config


def test_schema_constants():
    """Test that Schema class constants are defined."""
    assert hasattr(Schema, 'TIME')
    assert hasattr(Schema, 'LF_ANGLE')
    assert hasattr(Schema, 'RF_ANGLE')
    assert hasattr(Schema, 'HEAD_YAW')
    assert hasattr(Schema, 'SPINE_PREFIX')
    assert hasattr(Schema, 'TAIL_ANGLE_PREFIX')
    
    # Test helper methods
    x, y, conf = Schema.get_spine_columns("0")
    assert x == "Spine_0_x"
    assert y == "Spine_0_y"
    assert conf == "Spine_0_conf"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
