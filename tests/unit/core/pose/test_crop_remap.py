"""Tests for label remapping when crop settings change."""

from __future__ import annotations

from core.pose.detection.blob import BlobResult
from core.pose.labeling.crop_remap import (
    frames_with_labels_outside_crops,
    point_inside_square_crop,
    prune_labels_outside_crops,
)
from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import default_lab_schema
import numpy as np


def _blob(x0: int, y0: int, side: int, *, found: bool = True) -> BlobResult:
    return BlobResult(
        mask=np.ones((side, side), dtype=bool) if found else np.zeros((1, 1), dtype=bool),
        center_x=x0 + side / 2.0,
        center_y=y0 + side / 2.0,
        side=side,
        x0=x0,
        y0=y0,
        x1=x0 + side,
        y1=y0 + side,
        found=found,
    )


def test_point_inside_square_crop():
    blob = _blob(100, 50, 40)
    assert point_inside_square_crop(100, 50, blob)
    assert point_inside_square_crop(139.9, 89.9, blob)
    assert not point_inside_square_crop(99.9, 50, blob)
    assert not point_inside_square_crop(120, 100, blob)
    assert not point_inside_square_crop(120, 70, _blob(0, 0, 10, found=False))


def test_frames_with_labels_outside_crops():
    ds = LabelDataset(schema=default_lab_schema())
    ds.set_point(0, "nose", 110.0, 60.0)  # inside crop at (100,50)+40
    ds.set_point(0, "tail", 200.0, 60.0)  # outside
    ds.set_point(1, "nose", 10.0, 10.0)  # frame with no crop
    ds.set_point(2, "nose", 105.0, 55.0)  # inside

    crops = {
        0: _blob(100, 50, 40),
        1: _blob(0, 0, 10, found=False),
        2: _blob(100, 50, 40),
    }
    outside_frames, outside_points = frames_with_labels_outside_crops(
        ds, lambda i: crops.get(i)
    )
    assert outside_frames == {0, 1}
    assert outside_points == 2
    assert ds.get_point(0, "tail") == (200.0, 60.0)
    assert ds.get_point(0, "nose") == (110.0, 60.0)


def test_frames_with_labels_outside_crops_preserves_all_labels():
    """Update-for-all path: warn only, never delete outside-crop points."""
    ds = LabelDataset(schema=default_lab_schema())
    ds.set_point(0, "nose", 110.0, 60.0)
    ds.set_point(0, "tail", 200.0, 60.0)  # outside crop
    ds.set_point(1, "nose", 10.0, 10.0)  # no fish found on frame

    crops = {
        0: _blob(100, 50, 40),
        1: _blob(0, 0, 10, found=False),
    }
    before = {
        fi: {name: ds.get_point(fi, name) for name in ds.frames[fi].points}
        for fi in ds.frames
    }
    outside_frames, outside_points = frames_with_labels_outside_crops(
        ds, lambda i: crops.get(i)
    )
    assert outside_frames == {0, 1}
    assert outside_points == 2
    after = {
        fi: {name: ds.get_point(fi, name) for name in ds.frames[fi].points}
        for fi in ds.frames
    }
    assert before == after


def test_prune_keeps_inside_drops_outside_and_missing_crop():
    ds = LabelDataset(schema=default_lab_schema())
    ds.set_point(0, "nose", 110.0, 60.0)  # inside crop at (100,50)+40
    ds.set_point(0, "tail", 200.0, 60.0)  # outside
    ds.set_point(1, "nose", 10.0, 10.0)  # frame with no crop
    ds.set_point(2, "nose", 105.0, 55.0)  # inside

    crops = {
        0: _blob(100, 50, 40),
        1: _blob(0, 0, 10, found=False),
        2: _blob(100, 50, 40),
    }
    removed, cleared = prune_labels_outside_crops(ds, lambda i: crops.get(i))
    assert removed == 2  # tail on 0 + nose on 1
    assert cleared == 1  # frame 1 fully cleared
    assert ds.get_point(0, "nose") == (110.0, 60.0)
    assert ds.get_point(0, "tail") is None
    assert 1 not in ds.frames
    assert ds.get_point(2, "nose") == (105.0, 55.0)
