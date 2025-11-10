import pandas as pd
import json
import copy
import os


def load_bodyparts_from_csv(csv_path):
    """Reads DLC CSV and extracts cleaned bodypart names."""
    df = pd.read_csv(csv_path, header=[0, 1])
    raw_bps = [bp for bp in df.columns.levels[1]
               if bp not in ["coords", "bodyparts", "index"]]
    bodyparts = sorted(set(bp.split('.')[0] for bp in raw_bps))
    return bodyparts


def build_config(points_mapping, base_config):
    """Builds a full JSON config dict from UI selections."""
    config = copy.deepcopy(base_config)
    config["points"] = points_mapping
    return config


def save_config_json(config, save_path):
    """Writes config dict to JSON file."""
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


BASE_CONFIG = {
    "file_inputs": {
        "data": "input.csv",
        "video": "Zebrafish_vid.avi",
        "bulk_input_path": "Multiple_Input"
    },
    "points": {},
    "shown_outputs": {
        "print_time_ranges": False,
        "print_fin_freq": False,
        "print_tail_freq": False,
        "print_travel_distance": False,
        "print_travel_velocity": False,
        "show_angle_and_distance_plot": False,
        "show_spines": True,
        "show_movement_track": False,
        "show_heatmap": False,
        "show_head_plot": True
    },
    "angle_and_distance_plot_settings": {
        "show_left_fin_angle": True,
        "show_right_fin_angle": True,
        "show_tail_distance": True,
        "show_head_yaw": True
    },
    "spine_plot_settings": {
        "select_by_bout": True,
        "select_by_parallel_fins": True,
        "select_by_peaks": True,
        "spines_per_bout": 20,
        "parallel_error_range": 20,
        "fin_peaks_for_right_fin": True,
        "ignore_synchronized_fin_peaks": True,
        "sync_fin_peaks_range": 5,
        "min_accepted_confidence": 0.3,
        "accepted_broken_points": 1,
        "min_confidence_replace_from_surrounding_points": 0.5,
        "draw_with_gradient": True,
        "plot_draw_offset": 50,
        "split_plots_by_bout": True
    },
    "head_plot_settings": {
        "fin_peaks_for_right_fin": True,
        "ignore_synchronized_fin_peaks": True,
        "sync_fin_peaks_range": 5,
        "min_accepted_confidence": 0.3,
        "plot_draw_offset": 10,
        "split_plots_by_bout": True
    },
    "video_parameters": {
        "pixel_diameter": 1450,
        "dish_diameter_m": 0.02,
        "recorded_framerate": 648,
        "pixel_scale_factor": 1.825
    },
    "graph_cutoffs": {
        "left_fin_angle": 50,
        "right_fin_angle": 50,
        "tail_angle": 25,
        "movement_bout_width": 50,
        "use_tail_angle": False,
        "swim_bout_buffer": 26,
        "swim_bout_right_shift": 13
    },
    "auto_find_time_ranges": True,
    "time_ranges": [[0, 110]],
    "open_plots": True,
    "bulk_input": False
}
