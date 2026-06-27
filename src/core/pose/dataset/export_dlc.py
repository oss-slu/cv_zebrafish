"""Export label dataset to DLC multi-header CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.pose.labeling.labels_store import LabelDataset


def export_dlc_csv(dataset: LabelDataset, frame_count: int, out_path: Path, scorer: str = "pose_studio") -> Path:
    """Write DLC-shaped CSV for Verify (coords row + frame rows)."""
    bodyparts = dataset.bodyparts()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header0 = ["scorer"] + [scorer] * (len(bodyparts) * 3)
    header1 = ["bodyparts"] + [bp for bp in bodyparts for _ in range(3)]
    header2 = ["coords"] + sum([["x", "y", "likelihood"] for _ in bodyparts], [])

    rows = [header0, header1, header2]
    for fi in range(max(0, int(frame_count))):
        row = [f"frame{fi}"]
        fl = dataset.frames.get(fi)
        for bp in bodyparts:
            xy = fl.points.get(bp) if fl else None
            if xy is None:
                row.extend(["", "", ""])
            else:
                row.extend([xy[0], xy[1], 1.0])
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False, header=False)
    return out_path
