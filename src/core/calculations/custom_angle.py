"""Helpers for optional/custom angle calculations."""

from typing import Any, Dict, Tuple

import numpy as np

from .Metrics import calc_three_point_angle


def build_three_point_angle_column(
    parsed_points: Dict[str, Any], config: Dict[str, Any], n_frames: int
) -> Tuple[str, np.ndarray, str]:
    """
    Build one custom three-point-angle column from runtime config.

    Returns:
        tuple[str, np.ndarray, str]:
            (output_column_name, values, log_message)
    """
    try:
        three_cfg = ((config or {}).get("custom_calculations") or {}).get("three_point_angle") or {}
        output_col = str(three_cfg.get("output_column") or "ThreePointAngle")

        points = three_cfg.get("points") or []
        direction = str(three_cfg.get("direction") or "cw")
        custom_points = (parsed_points or {}).get("custom_points") or {}

        if not (isinstance(points, (list, tuple)) and len(points) == 3):
            msg = (
                f"[three_point_angle] Enabled but invalid 'points' spec ({points}); "
                f"writing NaNs to column '{output_col}'."
            )
            return output_col, np.full(n_frames, np.nan, dtype=float), msg

        a_lbl, b_lbl, c_lbl = (str(points[0]), str(points[1]), str(points[2]))
        A = custom_points.get(a_lbl)
        B = custom_points.get(b_lbl)
        C = custom_points.get(c_lbl)
        if not (isinstance(A, dict) and isinstance(B, dict) and isinstance(C, dict)):
            msg = (
                f"[three_point_angle] Missing parsed custom points for {points}; "
                f"writing NaNs to column '{output_col}'."
            )
            return output_col, np.full(n_frames, np.nan, dtype=float), msg

        ang = calc_three_point_angle(A, B, C, direction=direction)
        if len(ang) != n_frames:
            tmp = np.full(n_frames, np.nan, dtype=float)
            tmp[: min(n_frames, len(ang))] = ang[: min(n_frames, len(ang))]
            ang = tmp

        finite = int(np.isfinite(ang).sum())
        preview = np.array2string(ang[: min(10, len(ang))], precision=3, separator=", ")
        msg = (
            f"[three_point_angle] {output_col} ({a_lbl}-{b_lbl}-{c_lbl}, dir={direction}) "
            f"finite={finite}/{n_frames} preview={preview}"
        )
        return output_col, ang, msg
    except Exception as exc:
        try:
            three_cfg = ((config or {}).get("custom_calculations") or {}).get("three_point_angle") or {}
            output_col = str(three_cfg.get("output_column") or "ThreePointAngle")
        except Exception:
            output_col = "ThreePointAngle"
        msg = f"[three_point_angle] Failed to compute custom angle; wrote NaNs. Error: {exc}"
        return output_col, np.full(n_frames, np.nan, dtype=float), msg
