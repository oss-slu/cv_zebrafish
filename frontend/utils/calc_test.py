# tests/test_run_calculations.py
import numpy as np
import pandas as pd
from pathlib import Path
from run_calculations import run_calculations


def _write_sample_dlc_csv(path: Path):
    """
    Create a tiny DLC-style CSV with a 3-row MultiIndex header.
    Bodyparts: head_pt1, head_pt2, rfin_base, rfin_tip, lfin_base, lfin_tip
    Coords: x, y, likelihood
    Two frames:
      - Frame 0: fish along +X, fins parallel to +X  -> yaw ~ 0, RF/LF ~ 0
      - Frame 1: fish along +Y, left fin along -X    -> yaw ~ +90, LF ~ -90
    """
    
    scorer = ['scorer'] + ['dlc'] * 18
    bodyparts = ['bodyparts'] + [
        'head_pt1','head_pt1','head_pt1',
        'head_pt2','head_pt2','head_pt2',
        'rfin_base','rfin_base','rfin_base',
        'rfin_tip','rfin_tip','rfin_tip',
        'lfin_base','lfin_base','lfin_base',
        'lfin_tip','lfin_tip','lfin_tip',
    ]
    coords = ['coords'] + ['x','y','likelihood'] * 6
    columns = pd.MultiIndex.from_arrays([scorer, bodyparts, coords])

    # Frame 0
    f0 = [
        0,            # (a frame index column isn't required by DLC; we just leave in first col slot)
        0.0, 0.0, 1.0,   # head_pt1
        1.0, 0.0, 1.0,   # head_pt2 (centerline +X)
        0.2, 0.1, 1.0,   # rfin_base
        0.4, 0.1, 1.0,   # rfin_tip  (rf vector +X)
        0.2,-0.1, 1.0,   # lfin_base
        0.4,-0.1, 1.0,   # lfin_tip  (lf vector +X)
    ]

    # Frame 1
    f1 = [
        1,
        0.0, 0.0, 1.0,   # head_pt1
        0.0, 1.0, 1.0,   # head_pt2 (centerline +Y -> yaw ~ +90)
        0.2, 0.1, 1.0,   # rfin_base
        0.2, 0.3, 1.0,   # rfin_tip  (rf vector ~ +Y -> angle ~ 0 relative to +Y centerline)
        0.0, 0.0, 1.0,   # lfin_base
        -1.0, 0.0, 1.0,  # lfin_tip  (lf vector -X; relative to +Y -> about -90)
    ]

    df = pd.DataFrame([f0, f1], columns=columns)
    df.to_csv(path, index=False)


def _parse_points_from_csv(path: Path):
    """Minimal parser that returns parsed_points = {label: (x,y,conf)}."""
    df = pd.read_csv(path, header=[0, 1, 2])
    labels = {}
    for bp in ['head_pt1','head_pt2','rfin_base','rfin_tip','lfin_base','lfin_tip']:
        x = df[('dlc', bp, 'x')].to_numpy(dtype=float)
        y = df[('dlc', bp, 'y')].to_numpy(dtype=float)
        c = df[('dlc', bp, 'likelihood')].to_numpy(dtype=float)
        labels[bp] = (x, y, c)
    return labels


def _basic_config():
    return {
        'labels': {
            'head': {'pt1': 'head_pt1', 'pt2': 'head_pt2'},
            'right_fin': {'base': 'rfin_base', 'tip': 'rfin_tip'},
            'left_fin': {'base': 'lfin_base', 'tip': 'lfin_tip'},
        },
        'fps': 10.0,       # Time column should be [0.0, 0.1]
        # 'conf_min' optional; simplified function doesn't use it
    }


def test_run_calculations_basic(tmp_path):
    """
    Validates:
      - Time uses fps
      - Frame 0: yaw ~ 0, fins ~ 0
      - Frame 1: yaw ~ +90, LF ~ -90 (rf ~ 0 here)
    """
    csv_path = tmp_path / "mini.csv"
    _write_sample_dlc_csv(csv_path)
    points = _parse_points_from_csv(csv_path)
    cfg = _basic_config()

    out = run_calculations(points, cfg)

    # Dimensions and columns
    assert list(out.columns) == ['Time', 'RF_Angle', 'LF_Angle', 'HeadYaw']
    assert len(out) == 2

    # Frame 0 checks
    f0 = out.iloc[0]
    assert np.isclose(f0['Time'], 0.0)
    assert np.isclose(f0['HeadYaw'], 0.0, atol=1e-6)
    assert np.isclose(f0['RF_Angle'], 0.0, atol=1e-6)
    assert np.isclose(f0['LF_Angle'], 0.0, atol=1e-6)

    # Frame 1 checks
    f1 = out.iloc[1]
    assert np.isclose(f1['Time'], 0.1, atol=1e-12)        # 1 / fps
    assert np.isclose(f1['HeadYaw'], 90.0, atol=1e-6)     # centerline +Y vs +X
    assert np.isclose(f1['RF_Angle'], 0.0, atol=1e-6)     # rf vector ~ parallel to centerline
    assert np.isclose(f1['LF_Angle'], -90.0, atol=1e-6)   # +Y -> -X is -90°


def test_zero_centerline_gives_nan(tmp_path):
    """
    Make head_pt2 == head_pt1 at frame 0 → zero centerline vector.
    All angles should be NaN at frame 0; frame 1 remains valid.
    """
    csv_path = tmp_path / "mini_zero.csv"
    _write_sample_dlc_csv(csv_path)

    # Overwrite frame 0 head_pt2 with head_pt1 to force zero-length centerline
    df = pd.read_csv(csv_path, header=[0, 1, 2])
    df[('dlc','head_pt2','x')].iloc[0] = df[('dlc','head_pt1','x')].iloc[0]
    df[('dlc','head_pt2','y')].iloc[0] = df[('dlc','head_pt1','y')].iloc[0]
    df.to_csv(csv_path, index=False)

    points = _parse_points_from_csv(csv_path)
    cfg = _basic_config()
    out = run_calculations(points, cfg)

    f0 = out.iloc[0]
    assert np.isnan(f0['HeadYaw'])
    assert np.isnan(f0['RF_Angle'])
    assert np.isnan(f0['LF_Angle'])

    f1 = out.iloc[1]
    assert np.isfinite(f1['HeadYaw'])
    assert np.isfinite(f1['RF_Angle'])
    assert np.isfinite(f1['LF_Angle'])
