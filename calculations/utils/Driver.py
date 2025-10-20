import numpy as np
import pandas as pd
from .Metrics import (
    calc_fin_angle, calc_yaw, calc_spine_angles, calc_tail_angle,
    calc_tail_side_and_distance, calc_furthest_tail_point, detect_fin_peaks, get_time_ranges
)

def run_calculations(parsed_points, config):
    n_frames = len(parsed_points["spine"][0]["x"])
    vp = config["video_parameters"]
    scale_factor = vp["pixel_scale_factor"] * vp["dish_diameter_m"] / vp["pixel_diameter"]

    clp1 = parsed_points["head_pt1"]
    clp2 = parsed_points["head_pt2"]
    left_fins = parsed_points["left_fin"]
    right_fins = parsed_points["right_fin"]
    tail = parsed_points["tail"]
    tail_points = config["points"]["tail"]
    tp = parsed_points["tp"] 
    head = parsed_points["spine"][0]
    spine = parsed_points["spine"]

    left_fin_angle = calc_fin_angle(clp1, clp2, left_fins, left_fin=True)
    right_fin_angle = calc_fin_angle(clp1, clp2, right_fins, left_fin=False)
    head_yaw = calc_yaw(clp1, clp2)
    head_x = head["x"] * scale_factor
    head_y = head["y"] * scale_factor

    tail_angle = calc_tail_angle(clp1, clp2, tp)
    sides, tail_distances = calc_tail_side_and_distance(clp1, clp2, tp, scale_factor)
    furthest_tail = calc_furthest_tail_point(clp1, clp2, tail, tail_points)
    left_fin_peaks = detect_fin_peaks(left_fin_angle, config["graph_cutoffs"]["peak_horizontal_buffer"])
    right_fin_peaks = detect_fin_peaks(right_fin_angle, config["graph_cutoffs"]["peak_horizontal_buffer"])
    spine_angles = calc_spine_angles(spine)

    # Swim bouts (time ranges)
    if config.get("auto_find_time_ranges", False):
        time_ranges = get_time_ranges(left_fin_angle, right_fin_angle, tail_distances, config, n_frames)
    else:
        time_ranges = config.get("time_ranges", [[0, n_frames-1]])
        if time_ranges == [[0, 0]]:
            time_ranges = [[0, n_frames - 1]]

    # Fill swim bout columns
    bout_head_yaw = np.array([""] * n_frames, dtype=object)
    for start, end in time_ranges:
        bout_yaw_center = head_yaw[start]
        for i in range(start, end + 1):
            bout_head_yaw[i] = head_yaw[i] - bout_yaw_center

    results_dict = {
        "Time": np.arange(n_frames),
        "LF_Angle": left_fin_angle,
        "RF_Angle": right_fin_angle,
        "HeadYaw": head_yaw,
        "HeadX": head_x,
        "HeadY": head_y,
        "Tail_Angle": tail_angle,
        "Tail_Distance": tail_distances,
        "Tail_Side": sides,
        "Furthest_Tail_Point": furthest_tail,
        "leftFinPeaks": left_fin_peaks,
        "rightFinPeaks": right_fin_peaks,
        "curBoutHeadYaw": bout_head_yaw,
    }

    for seg in range(spine_angles.shape[1]):
        results_dict[f"TailAngle_{seg}"] = spine_angles[:, seg]

    result_df = pd.DataFrame(results_dict)

    # Add time range columns as in legacy
    for irange, (start, end) in enumerate(time_ranges):
        col_start, col_end = f"timeRangeStart_{irange}", f"timeRangeEnd_{irange}"
        result_df.loc[..., col_start] = ""
        result_df.loc[..., col_end] = ""
        result_df.loc[0, col_start] = start
        result_df.loc[0, col_end] = end

    return result_df
