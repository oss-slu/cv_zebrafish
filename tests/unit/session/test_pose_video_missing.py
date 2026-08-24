"""Tests for missing-video stub + re-link matching."""

from __future__ import annotations

import json
from pathlib import Path

from core.pose.video.video_registry import remove_video_source_files
from session.session import Session


def test_mark_missing_and_relink_match():
    s = Session(name="test_relink")
    pid = s.ensure_default_pose_project()
    s.register_pose_video(
        "vid_a",
        "Zebrafish_vid_3.mp4",
        {"frame_count": 100, "width": 2336, "height": 1728, "fps": 30},
    )
    s.mark_pose_video_missing("vid_a")
    entry = s.get_pose_video_entry("vid_a")
    assert entry is not None
    assert entry.get("missing") is True

    match = s.find_pose_video_relink_id(
        display_name="Zebrafish_vid_3.mp4",
        frame_count=100,
        width=2336,
        height=1728,
    )
    assert match == "vid_a"

    # Wrong resolution → no match
    assert (
        s.find_pose_video_relink_id(
            display_name="Zebrafish_vid_3.mp4",
            frame_count=100,
            width=1920,
            height=1080,
        )
        is None
    )

    # Re-register clears missing
    s.register_pose_video(
        "vid_a",
        "Zebrafish_vid_3.mp4",
        {"frame_count": 100, "width": 2336, "height": 1728, "fps": 30},
    )
    assert s.get_pose_video_entry("vid_a").get("missing") is False
    assert s.find_pose_video_relink_id(
        display_name="Zebrafish_vid_3.mp4",
        frame_count=100,
        width=2336,
        height=1728,
    ) is None


def test_remove_video_source_keeps_meta(tmp_path: Path):
    vdir = tmp_path / "videos" / "vid1"
    vdir.mkdir(parents=True)
    (vdir / "source.mp4").write_bytes(b"fake")
    (vdir / "meta.json").write_text(
        json.dumps({"frame_count": 10, "width": 100, "height": 80}),
        encoding="utf-8",
    )
    (vdir / "arena.json").write_text("{}", encoding="utf-8")
    removed = remove_video_source_files(vdir)
    assert any(p.name == "source.mp4" for p in removed)
    assert (vdir / "meta.json").is_file()
    assert (vdir / "arena.json").is_file()
    assert not (vdir / "source.mp4").exists()
