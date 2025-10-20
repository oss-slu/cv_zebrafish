import numpy as np

def calc_fin_angle(head1_arr, head2_arr, fin_points_arr, left_fin=False):
    """
    Calculate the angle between head direction and fin orientation.

    Args:
        head1_arr (dict): Coordinates of the first head point with 'x' and 'y' arrays.
        head2_arr (dict): Coordinates of the second head point with 'x' and 'y' arrays.
        fin_points_arr (list[dict]): List of fin point coordinate dictionaries.
        left_fin (bool): If True, sign convention is flipped for left fins.

    Returns:
        np.ndarray: Array of fin angles (in degrees) for each frame.
    """
    n = len(head1_arr["x"])
    angles = np.full(n, np.nan)
    for i in range(n):
        try:
            h1 = np.array([head1_arr["x"][i], head1_arr["y"][i]])
            h2 = np.array([head2_arr["x"][i], head2_arr["y"][i]])
            v1 = h2 - h1
            base = np.array([fin_points_arr[0]["x"][i], fin_points_arr[0]["y"][i]])
            tip = np.array([fin_points_arr[-1]["x"][i], fin_points_arr[-1]["y"][i]])
            v2 = tip - base
            angle_rad = np.arctan2(v2[1], v2[0]) - np.arctan2(v1[1], v1[0])
            angle_deg = np.degrees(angle_rad)
            if angle_deg < -180:
                angle_deg += 360
            elif angle_deg > 180:
                angle_deg -= 360
            angles[i] = angle_deg if left_fin else -angle_deg
        except Exception:
            angles[i] = np.nan
    return angles

def calc_yaw(head1_arr, head2_arr):
    """
    Compute yaw (heading angle) from head point positions.

    Args:
        head1_arr (dict): Coordinates of the first head point.
        head2_arr (dict): Coordinates of the second head point.

    Returns:
        np.ndarray: Array of yaw angles (in degrees) per frame.
    """
    n = len(head1_arr["x"])
    yaws = np.full(n, np.nan)
    for i in range(n):
        dx = head2_arr["x"][i] - head1_arr["x"][i]
        dy = head2_arr["y"][i] - head1_arr["y"][i]
        if np.isnan(dx) or np.isnan(dy):
            yaws[i] = np.nan
        else:
            angle_rad = np.arctan2(dy, dx)
            angle_deg = np.degrees(angle_rad)
            yaws[i] = -angle_deg
    return yaws

def get_angle_between_points(A, B, C):
    """
    Calculate signed angle between vectors BA and BC at point B.

    Args:
        A (dict): Coordinates of point A.
        B (dict): Coordinates of point B (vertex).
        C (dict): Coordinates of point C.

    Returns:
        float: Signed angle (in degrees) between points A-B-C.
    """
    BA = np.array([A["x"] - B["x"], A["y"] - B["y"]], dtype=float)
    BC = np.array([C["x"] - B["x"], C["y"] - B["y"]], dtype=float)
    nBA = np.linalg.norm(BA)
    nBC = np.linalg.norm(BC)
    if nBA == 0 or nBC == 0:
        return np.nan
    dot = float(np.dot(BA, BC))
    cross = float(BA[0] * BC[1] - BA[1] * BC[0])
    unsigned = np.arctan2(abs(cross), dot)
    signed = np.sign(cross) * (np.pi - unsigned)
    return np.degrees(signed)

def calc_spine_angles(spine):
    """
    Compute angles between adjacent spine segments.

    Args:
        spine (list[dict]): List of coordinate dicts for consecutive spine points.

    Returns:
        np.ndarray: 2D array (frames x segments) of spine angles (degrees).
    """
    n_segments = len(spine) - 2
    n_frames = len(spine[0]["x"])
    angles = np.full((n_frames, n_segments), np.nan)
    for idx in range(n_segments):
        ptA, ptB, ptC = spine[idx], spine[idx+1], spine[idx+2]
        for f in range(n_frames):
            angles[f, idx] = get_angle_between_points(
                {k: ptA[k][f] for k in ["x", "y"]},
                {k: ptB[k][f] for k in ["x", "y"]},
                {k: ptC[k][f] for k in ["x", "y"]},
            )
    return angles

def calc_tail_angle(clp1, clp2, tp):
    """
    Calculate tail angles from three tail points per frame.

    Args:
        clp1 (dict): First caudal peduncle point coordinates.
        clp2 (dict): Second caudal peduncle point coordinates.
        tp (dict): Tail tip point coordinates.

    Returns:
        np.ndarray: Tail angles (degrees) per frame.
    """
    n = len(tp["x"])
    return np.array([
        get_angle_between_points(
            {k: clp1[k][i] for k in ["x", "y"]},
            {k: clp2[k][i] for k in ["x", "y"]},
            {k: tp[k][i] for k in ["x", "y"]}
        ) for i in range(n)
    ])

def calc_tail_side_and_distance(clp1, clp2, tp, scale_factor):
    """
    Determine tail side (Left/Right) and signed distance from the body axis.

    Args:
        clp1 (dict): First caudal peduncle point coordinates.
        clp2 (dict): Second caudal peduncle point coordinates.
        tp (dict): Tail tip point coordinates.
        scale_factor (float): Pixel-to-mm or scaling conversion factor.

    Returns:
        tuple[np.ndarray, np.ndarray]: 
            - sides: Array of "Left", "Right", or "On the line".
            - distances: Array of signed distances (scaled).
    """
    n = len(tp["x"])
    sides = np.array([""] * n, dtype=object)
    distances = np.full(n, np.nan)
    for i in range(n):
        x1, y1, x2, y2 = clp1["x"][i], clp1["y"][i], clp2["x"][i], clp2["y"][i]
        xt, yt = tp["x"][i], tp["y"][i]
        m, b = np.polyfit([x1, x2], [y1, y2], 1)
        rel_pos = (m * xt - yt + b) / np.sqrt(m**2 + 1)
        signed_dist = rel_pos * scale_factor
        if rel_pos < 0:
            sides[i] = "Right"
        elif rel_pos > 0:
            sides[i] = "Left"
        else:
            sides[i] = "On the line"
        distances[i] = signed_dist
    return sides, distances

def calc_furthest_tail_point(clp1, clp2, tail, tail_points):
    """
    Identify each frame's tail point farthest from the body axis.

    Args:
        clp1 (dict): First caudal peduncle point.
        clp2 (dict): Second caudal peduncle point.
        tail (list[dict]): List of all tail point coordinates.
        tail_points (list[str]): Names or identifiers of tail segments.

    Returns:
        np.ndarray: Array of tail point names corresponding to the furthest points per frame.
    """
    n = len(tail[0]["x"])
    furthest_pt = np.empty(n, dtype=object)
    for i in range(n):
        x1, y1, x2, y2 = clp1["x"][i], clp1["y"][i], clp2["x"][i], clp2["y"][i]
        m, b = np.polyfit([x1, x2], [y1, y2], 1)
        max_abs_dist = 0
        furthest = tail_points[0]
        for p, pt in enumerate(tail):
            xt, yt = pt["x"][i], pt["y"][i]
            rel_pos = (m * xt - yt + b) / np.sqrt(m**2 + 1)
            if abs(rel_pos) > max_abs_dist:
                max_abs_dist = abs(rel_pos)
                furthest = tail_points[p]
        furthest_pt[i] = furthest
    return furthest_pt

def detect_fin_peaks(angles, buffer):
    """
    Detect local maxima and minima in fin angle signals.

    Args:
        angles (np.ndarray): Array of fin angles per frame.
        buffer (int): Number of frames around each index to consider for peak detection.

    Returns:
        np.ndarray: Array of "max", "min", or empty strings per frame.
    """
    n = len(angles)
    peaks = np.array([""] * n, dtype=object)
    for i in range(buffer, n - buffer):
        segment = angles[i-buffer: i+buffer+1]
        if np.isnan(segment).any():
            continue
        current = angles[i]
        left = angles[i-buffer:i]
        right = angles[i+1:i+buffer+1]
        if (np.all(current >= left) and np.all(current >= right)):
            peaks[i] = "max"
        elif (np.all(current <= left) and np.all(current <= right)):
            peaks[i] = "min"
    return peaks

def get_time_ranges(left_fin_angles, right_fin_angles, tail_distances, config, n_frames):
    """
    Identify periods (time ranges) of active swimming bouts based on movement thresholds.

    Args:
        left_fin_angles (np.ndarray): Left fin angles (degrees).
        right_fin_angles (np.ndarray): Right fin angles (degrees).
        tail_distances (np.ndarray): Tail displacement values.
        config (dict): Configuration with 'graph_cutoffs' thresholds and buffers.
        n_frames (int): Total number of frames in the dataset.

    Returns:
        list[list[int]]: List of [start_frame, end_frame] pairs for detected bouts.
    """
    cutoff = config['graph_cutoffs']
    buffer = cutoff["swim_bout_buffer"]
    bout_width = cutoff["movement_bout_width"]
    ranges = []
    in_bout = False
    start = None
    for i in range(n_frames):
        bout = (abs(left_fin_angles[i]) > cutoff["left_fin_angle"] or
                abs(right_fin_angles[i]) > cutoff["right_fin_angle"] or
                abs(tail_distances[i]) > cutoff["tail_angle"])
        if bout and not in_bout:
            start = max(i - buffer, 0)
            in_bout = True
        elif not bout and in_bout:
            end = min(i + buffer, n_frames - 1)
            if end > start + bout_width:
                ranges.append([start, end])
            in_bout = False
    if in_bout and start is not None and (n_frames - 1) > start:
        ranges.append([start, n_frames - 1])
    if not ranges:
        ranges = [[0, n_frames - 1]]
    return ranges
