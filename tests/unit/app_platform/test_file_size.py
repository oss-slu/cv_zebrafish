"""Tests for file size formatting."""

from pathlib import Path

from app_platform.file_size import format_byte_size, path_size_bytes


def test_format_byte_size():
    assert format_byte_size(512) == "512 B"
    assert format_byte_size(2048) == "2.0 KB"
    assert format_byte_size(5 * 1024 * 1024) == "5.0 MB"


def test_path_size_bytes_file(tmp_path: Path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"x" * 100)
    assert path_size_bytes(f) == 100


def test_path_size_bytes_dir(tmp_path: Path):
    (tmp_path / "a.bin").write_bytes(b"x" * 10)
    (tmp_path / "b.bin").write_bytes(b"y" * 20)
    assert path_size_bytes(tmp_path) == 30
