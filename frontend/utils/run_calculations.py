import numpy as np
import pandas as pd

def run_calculations(parsed_points, config):
    """
    Compute basic zebrafish movement metrics.

    Parameters:
        parsed_points: dict
            Example: {"head_pt1": (x_array, y_array, conf_array), ...}
        config: dict
            Should include label names and optionally 'fps' and 'conf_min'.

    Returns:
        pandas DataFrame with columns: Time, RF_Angle, LF_Angle, HeadYaw
    """
    labels = config.get('labels', {})
    fps = config.get('fps', 1.0)
    conf_min = config.get('conf_min', 0.0)

    # Pull out required point names
    head_pt1 = labels['head']['pt1']
    head_pt2 = labels['head']['pt2']
    rfin_base = labels['right_fin']['base']
    rfin_tip  = labels['right_fin']['tip']
    lfin_base = labels['left_fin']['base']
    lfin_tip  = labels['left_fin']['tip']

    # Extract arrays
    hx1, hy1, hc1 = parsed_points[head_pt1]
    hx2, hy2, hc2 = parsed_points[head_pt2]
    rbx, rby, rbc = parsed_points[rfin_base]
    rtx, rty, rtc = parsed_points[rfin_tip]
    lbx, lby, lbc = parsed_points[lfin_base]
    ltx, lty, ltc = parsed_points[lfin_tip]

    # Ensure all arrays are same length
    n = min(len(hx1), len(hy1), len(hx2), len(hy2))
    if n == 0:
        return pd.DataFrame(columns=['Time', 'RF_Angle', 'LF_Angle', 'HeadYaw'])

    # Compute vectors
    cl_x = hx2 - hx1
    cl_y = hy2 - hy1
    rf_x = rtx - rbx
    rf_y = rty - rby
    lf_x = ltx - lbx
    lf_y = lty - lby

    # Helper to compute angle difference in degrees
    def angle_diff(ax, ay, bx, by):
        a = np.arctan2(ay, ax)
        b = np.arctan2(by, bx)
        d = np.rad2deg(b - a)
        return (d + 180) % 360 - 180

    # Compute metrics
    head_yaw = angle_diff(np.ones(n), np.zeros(n), cl_x, cl_y)
    rf_angle = angle_diff(cl_x, cl_y, rf_x, rf_y)
    lf_angle = angle_diff(cl_x, cl_y, lf_x, lf_y)

    # Handle NaN or low-confidence points
    def mask_invalid(arr, *conds):
        mask = np.zeros(n, dtype=bool)
        for c in conds:
            mask |= np.isnan(c)
        arr[mask] = np.nan
        return arr

    head_yaw = mask_invalid(head_yaw, cl_x, cl_y)
    rf_angle = mask_invalid(rf_angle, cl_x, cl_y, rf_x, rf_y)
    lf_angle = mask_invalid(lf_angle, cl_x, cl_y, lf_x, lf_y)

    time = np.arange(n) / fps if fps else np.arange(n)

    df = pd.DataFrame({
        'Time': time,
        'RF_Angle': rf_angle,
        'LF_Angle': lf_angle,
        'HeadYaw': head_yaw
    })

    return df
