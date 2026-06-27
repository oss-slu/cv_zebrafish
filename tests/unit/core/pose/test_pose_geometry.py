"""Unit tests for pose geometry (arena, blob, crop)."""

from __future__ import annotations

import numpy as np

from core.pose.detection.arena import ArenaConfig, arena_mask
from core.pose.detection.blob import BlobParams, detect_blob_square_crop
from core.pose.detection.crop import crop_to_full_frame, extract_square_crop, fish_mask_in_crop, full_frame_to_crop
from core.pose.labeling.schema import LAB_BODYPARTS, default_lab_schema, edges_for_bodyparts


def test_lab_schema_has_eleven_points():
    assert len(LAB_BODYPARTS) == 11
    schema = default_lab_schema()
    assert len(schema.bodyparts) == 11
    assert schema.bodyparts[-2:] == ["T4", "T5"]
    assert len(schema.edges) >= 8


def test_edges_for_three_point_tail():
    names = ["Head", "BF", "LF1", "LF2", "RF1", "RF2", "T1", "T2", "T3"]
    edges = edges_for_bodyparts(names)
    idx = {n: i for i, n in enumerate(names)}
    assert (idx["BF"], idx["T1"]) in edges
    assert (idx["T2"], idx["T3"]) in edges
    assert (idx["T3"], idx.get("T4", -1)) not in edges


def test_arena_circle_mask_center():
    arena = ArenaConfig(shape="circle", center_x=0.5, center_y=0.5, size=0.5)
    mask = arena_mask(100, 100, arena)
    assert mask[50, 50]
    assert not mask[0, 0]


def test_arena_rectangle_mask():
    arena = ArenaConfig(rect_x=0.25, rect_y=0.25, rect_w=0.5, rect_h=0.5)
    mask = arena_mask(100, 200, arena)
    assert mask[50, 100]
    assert not mask[0, 0]
    assert not mask[99, 199]


def test_blob_padding_expands_mask():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[50:70, 70:90] = 220
    arena = ArenaConfig()
    tight = detect_blob_square_crop(frame, arena, BlobParams(brightness_min=100, blob_padding_px=0))
    loose = detect_blob_square_crop(frame, arena, BlobParams(brightness_min=100, blob_padding_px=8))
    assert tight.found and loose.found
    assert int(loose.mask.sum()) > int(tight.mask.sum())


def test_crop_padding_expands_crop():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[50:70, 70:90] = 220
    arena = ArenaConfig()
    tight = detect_blob_square_crop(frame, arena, BlobParams(brightness_min=100, crop_padding_px=0))
    loose = detect_blob_square_crop(frame, arena, BlobParams(brightness_min=100, crop_padding_px=20))
    assert tight.found and loose.found
    assert loose.side > tight.side


def test_fish_mask_in_crop_aligns_with_extract():
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    frame[5:25, 5:25] = 200
    arena = ArenaConfig()
    blob = detect_blob_square_crop(
        frame, arena, BlobParams(brightness_min=100, crop_padding_px=20)
    )
    assert blob.found
    crop = extract_square_crop(frame, blob)
    mask = fish_mask_in_crop(blob)
    assert mask.shape[:2] == crop.shape[:2]
    assert mask.sum() > 0


def test_extract_square_crop_pads_out_of_frame():
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    frame[5:25, 5:25] = 200
    arena = ArenaConfig()
    blob = detect_blob_square_crop(
        frame, arena, BlobParams(brightness_min=100, crop_padding_px=20)
    )
    assert blob.found
    assert blob.x0 < 0 or blob.y0 < 0
    crop = extract_square_crop(frame, blob)
    assert crop.shape == (blob.side, blob.side, 3)
    assert int(crop[5:25, 5:25].sum()) > 0
    assert int(crop[: max(0, -blob.y0), : max(0, -blob.x0)].sum()) == 0


def test_blob_detects_bright_square():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[40:80, 50:110] = 220
    arena = ArenaConfig()
    params = BlobParams(brightness_min=100, brightness_max=255)
    result = detect_blob_square_crop(frame, arena, params)
    assert result.found
    assert result.side > 0
    cx, cy = crop_to_full_frame(result.side / 2, result.side / 2, result)
    fx, fy = full_frame_to_crop(cx, cy, result)
    assert abs(fx - result.side / 2) < 2
    assert abs(fy - result.side / 2) < 2
