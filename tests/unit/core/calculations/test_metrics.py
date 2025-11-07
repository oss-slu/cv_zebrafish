import numpy as np
import numpy.testing as npt

from cvzebrafish.core.calculations.Metrics import (
    calc_fin_angle,
    calc_yaw,
    calc_tail_side_and_distance,
    calc_tail_angle,
    calc_spine_angles,
    calc_furthest_tail_point,
    detect_fin_peaks,
    get_time_ranges,
)


def test_calc_fin_angle_sign_conventions():
    head1 = {"x": np.array([0.0, 0.0]), "y": np.array([0.0, 0.0])}
    head2 = {"x": np.array([1.0, 0.0]), "y": np.array([0.0, 1.0])}
    fin_points = [
        {"x": np.array([0.0, 0.0]), "y": np.array([0.1, 0.1])},
        {"x": np.array([0.0, 1.0]), "y": np.array([0.9, 1.0])},
    ]

    right_angles = calc_fin_angle(head1, head2, fin_points)
    left_angles = calc_fin_angle(head1, head2, fin_points, left_fin=True)

    npt.assert_allclose(right_angles, np.array([-90.0, 48.012787]), atol=1e-6)
    npt.assert_allclose(left_angles, np.array([90.0, -48.012787]), atol=1e-6)


def test_calc_yaw_returns_heading_angle():
    head1 = {"x": np.array([0.0, 0.0]), "y": np.array([0.0, 0.0])}
    head2 = {"x": np.array([1.0, 0.0]), "y": np.array([0.0, 1.0])}

    yaws = calc_yaw(head1, head2)
    npt.assert_allclose(yaws, np.array([0.0, -90.0]), atol=1e-6)


def test_tail_side_and_distance_reports_signed_offsets():
    clp1 = {"x": np.array([0.0, 0.0]), "y": np.array([0.0, 0.0])}
    clp2 = {"x": np.array([1.0, 1.0]), "y": np.array([0.0, 0.0])}
    tp = {"x": np.array([1.0, -1.0]), "y": np.array([1.0, -1.0])}

    sides, distances_scaled, distances_raw = calc_tail_side_and_distance(clp1, clp2, tp, scale_factor=2.0)

    assert list(sides) == ["Right", "Left"]
    npt.assert_allclose(distances_raw, np.array([-1.0, 1.0]), atol=1e-6)
    npt.assert_allclose(distances_scaled, np.array([-2.0, 2.0]), atol=1e-6)


def test_tail_angle_matches_expected_geometry():
    clp1 = {"x": np.array([0.0, 0.0]), "y": np.array([0.0, 0.0])}
    clp2 = {"x": np.array([1.0, 1.0]), "y": np.array([0.0, 0.0])}
    tp = {"x": np.array([1.0, -1.0]), "y": np.array([1.0, -1.0])}

    angles = calc_tail_angle(clp1, clp2, tp)
    npt.assert_allclose(angles, np.array([90.0, 26.565051]), atol=1e-6)


def test_spine_angles_vectorize_over_frames_and_segments():
    spine = [
        {"x": np.array([0.0, 0.0]), "y": np.array([0.0, 0.0])},
        {"x": np.array([0.3, 0.5]), "y": np.array([0.0, 0.0])},
        {"x": np.array([0.6, 0.8]), "y": np.array([0.0, 0.2])},
        {"x": np.array([0.9, 1.1]), "y": np.array([0.0, 0.4])},
    ]

    angles = calc_spine_angles(spine)
    assert angles.shape == (2, 2)
    npt.assert_allclose(angles[0], np.array([180.0, 180.0]), atol=1e-6)
    npt.assert_allclose(angles[1], np.array([146.309932, 180.0]), atol=1e-6)


def test_furthest_tail_point_identifies_max_offset_segment():
    clp1 = {"x": np.array([0.0, 0.0]), "y": np.array([0.0, 0.0])}
    clp2 = {"x": np.array([1.0, 1.0]), "y": np.array([0.0, 0.0])}
    tail_points = ["p0", "p1", "p2"]
    tail = [
        {"x": np.array([0.0, 0.0]), "y": np.array([0.1, 0.2])},
        {"x": np.array([0.0, 0.0]), "y": np.array([0.5, -0.4])},
        {"x": np.array([0.0, 0.0]), "y": np.array([-0.7, 0.1])},
    ]

    furthest = calc_furthest_tail_point(clp1, clp2, tail, tail_points)
    assert list(furthest) == ["p2", "p1"]


def test_detect_fin_peaks_marks_local_extrema():
    signal = np.array([0.0, 1.0, 0.0, -1.0, 0.0])
    peaks = detect_fin_peaks(signal, buffer=1)
    assert peaks.tolist() == ["", "max", "", "min", ""]


def test_get_time_ranges_combines_fin_activity_windows():
    left = np.array([0.0, 6.0, 6.5, 0.0, 0.0, 0.0, 6.0, 6.2, 0.0], dtype=float)
    right = np.array([0.0, 6.1, 6.3, 0.0, 0.0, 0.0, 6.4, 6.6, 0.0], dtype=float)
    tail = np.zeros_like(left)
    config = {
        "graph_cutoffs": {
            "left_fin_angle": 5,
            "right_fin_angle": 5,
            "tail_angle": 5,
            "movement_bout_width": 1,
            "swim_bout_buffer": 1,
            "swim_bout_right_shift": 0,
            "use_tail_angle": False,
        }
    }

    ranges = get_time_ranges(left, right, tail, config, len(left))
    assert ranges == [[1, 3], [6, 8]]
