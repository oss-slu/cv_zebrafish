import numpy as np
import numpy.testing as npt
import pandas as pd

from calculations.utils.Driver import run_calculations


def _build_parsed_points():
    clp1_x = np.array([0.0, 0.2, 0.4])
    clp1_y = np.zeros_like(clp1_x)
    clp2_x = np.array([1.0, 1.2, 1.4])
    clp2_y = np.array([0.0, 0.2, 0.4])

    return {
        "clp1": {"x": clp1_x, "y": clp1_y},
        "clp2": {"x": clp2_x, "y": clp2_y},
        "head": {"x": clp1_x, "y": clp1_y},
        "left_fin": [
            {"x": np.array([0.5, 0.5, 0.5]), "y": np.array([0.1, 0.1, 0.1])},
            {"x": np.array([0.5, 0.5, 0.5]), "y": np.array([0.8, 0.4, 0.2])},
        ],
        "right_fin": [
            {"x": np.array([0.5, 0.5, 0.5]), "y": np.array([-0.1, -0.1, -0.1])},
            {"x": np.array([0.5, 0.5, 0.5]), "y": np.array([-0.7, -0.3, -0.2])},
        ],
        "tail": [
            {"x": np.array([1.0, 0.8, 0.6]), "y": np.array([0.5, -0.3, 0.2])},
            {"x": np.array([1.0, 0.8, 0.6]), "y": np.array([0.6, -0.5, 0.4])},
        ],
        "tailPoints": ["tail_tip", "tail_mid"],
        "tp": {"x": np.array([1.0, 0.8, 0.6]), "y": np.array([0.5, -0.3, 0.2])},
        "spine": [
            {"x": clp1_x, "y": clp1_y},
            {"x": clp1_x + 0.3, "y": np.array([0.1, 0.1, 0.1])},
            {"x": clp1_x + 0.6, "y": np.array([0.2, 0.0, -0.1])},
            {"x": clp1_x + 0.9, "y": np.array([0.3, 0.0, -0.2])},
        ],
    }


def _build_config():
    return {
        "video_parameters": {
            "pixel_scale_factor": 1.0,
            "dish_diameter_m": 1.0,
            "pixel_diameter": 1.0,
        },
        "graph_cutoffs": {
            "peak_horizontal_buffer": 1,
            "left_fin_angle": 10,
            "right_fin_angle": 10,
            "tail_angle": 10,
            "movement_bout_width": 1,
            "swim_bout_buffer": 0,
            "swim_bout_right_shift": 0,
            "use_tail_angle": False,
        },
        "auto_find_time_ranges": False,
        "time_ranges": [[0, 2]],
    }


def test_run_calculations_returns_expected_dataframe():
    parsed_points = _build_parsed_points()
    config = _build_config()

    df = run_calculations(parsed_points, config)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3

    required_columns = [
        "Time",
        "LF_Angle",
        "RF_Angle",
        "HeadYaw",
        "HeadX",
        "Tail_Distance",
        "Tail_Side",
        "Furthest_Tail_Point",
        "curBoutHeadYaw",
        "TailAngle_0",
        "TailAngle_1",
        "timeRangeStart_0",
        "timeRangeEnd_0",
    ]
    for column in required_columns:
        assert column in df.columns

    npt.assert_allclose(df["HeadX"].to_numpy(), parsed_points["head"]["x"], atol=1e-6)
    assert df["Tail_Side"].tolist() == ["Right", "Left", "Right"]
    assert df["Furthest_Tail_Point"].tolist() == ["tail_mid", "tail_mid", "tail_mid"]
    centered_yaw = pd.to_numeric(df["curBoutHeadYaw"], errors="coerce").to_numpy()
    npt.assert_allclose(centered_yaw, np.array([0.0, -11.309932, -21.801409]), atol=1e-5)
    assert df["timeRangeStart_0"].iloc[0] == 0
    assert df["timeRangeEnd_0"].iloc[0] == 2
