import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from src.core.calculations.Driver import run_calculations
from src.core.comparison.fish_data import (
    FishLoadError,
    load_fish,
    load_fish_batch,
    unique_label,
)
from src.core.parsing.Parser import parse_dlc_csv

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_CSV = REPO_ROOT / "data" / "samples" / "csv" / "correct_format.csv"
SAMPLE_CONFIG = REPO_ROOT / "data" / "samples" / "jsons" / "BaseConfig.json"

needs_samples = pytest.mark.skipif(
    not (SAMPLE_CSV.is_file() and SAMPLE_CONFIG.is_file()),
    reason="sample data not found",
)


@pytest.fixture
def config():
    return json.loads(SAMPLE_CONFIG.read_text(encoding="utf-8"))


def test_unique_label():
    assert unique_label("fish", []) == "fish"
    assert unique_label("fish", ["fish"]) == "fish (2)"
    assert unique_label("fish", ["fish", "fish (2)"]) == "fish (3)"
    assert unique_label("   ", []) == "Fish"


def test_load_fish_rejects_invalid_file(tmp_path):
    bad_file = tmp_path / "bad.csv"
    bad_file.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(FishLoadError):
        load_fish(bad_file, {}, "fish_1")


@needs_samples
def test_load_fish_matches_direct_pipeline(config):
    fish = load_fish(SAMPLE_CSV, config, "fish_1")

    expected = run_calculations(parse_dlc_csv(str(SAMPLE_CSV), config), config)
    pd.testing.assert_frame_equal(fish.results, expected)
    assert fish.label == "correct_format"
    assert fish.source_file == str(SAMPLE_CSV)


@needs_samples
def test_batch_skips_invalid_files_and_keeps_valid_ones(config, tmp_path):
    bad_file = tmp_path / "bad.csv"
    bad_file.write_text("a,b\n1,2\n", encoding="utf-8")
    second = tmp_path / "second.csv"
    shutil.copy(SAMPLE_CSV, second)
    progress = []

    loaded, failures = load_fish_batch(
        [bad_file, SAMPLE_CSV, second],
        config,
        on_progress=lambda index, total, name: progress.append((index, total, name)),
    )

    assert [fish.label for fish in loaded] == ["correct_format", "second"]
    assert [fish.fish_id for fish in loaded] == ["fish_1", "fish_2"]
    assert [path for path, _ in failures] == [str(bad_file)]
    assert [entry[:2] for entry in progress] == [(1, 3), (2, 3), (3, 3)]


@needs_samples
def test_batch_keeps_labels_unique_against_existing(config):
    loaded, _ = load_fish_batch(
        [SAMPLE_CSV], config, existing_labels=["correct_format"], first_number=3
    )

    assert loaded[0].label == "correct_format (2)"
    assert loaded[0].fish_id == "fish_3"