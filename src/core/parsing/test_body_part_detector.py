"""
Unit tests for the dynamic body part detection module.

Tests cover both raw DLC CSV format and enriched output CSV format,
including edge cases and error handling.
"""

import pytest
import pandas as pd
import numpy as np
import os
import tempfile
from typing import Dict, List

from .body_part_detector import (
    BodyPartDetectionResult,
    detect_body_parts,
    detect_body_parts_from_dataframe,
    get_body_part_names,
    get_grouped_body_parts,
)

# ---------------------------------------------------------------------------
# Helpers: create temporary CSV files for testing
# ---------------------------------------------------------------------------

def create_dlc_raw_csv(
    body_parts: List[str],
    n_frames: int = 5
) -> str:
    """
    Create a temporary raw DLC CSV file with given body parts.
    Returns the path to the temporary file.
    """
    # Build header rows
    scorer_row = ["scorer"] + ["DLC_model"] * (len(body_parts) * 3)
    bodyparts_row = ["bodyparts"]
    coords_row = ["coords"]

    for part in body_parts:
        bodyparts_row += [part, part, part]
        coords_row += ["x", "y", "likelihood"]

    # Build data rows
    data_rows = []
    for i in range(n_frames):
        row = [str(i)]
        for _ in body_parts:
            row += [
                str(round(100.0 + i, 2)),
                str(round(200.0 + i, 2)),
                str(round(0.9 - i * 0.01, 4))
            ]
        data_rows.append(row)

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    import csv
    writer = csv.writer(tmp)
    writer.writerow(scorer_row)
    writer.writerow(bodyparts_row)
    writer.writerow(coords_row)
    for row in data_rows:
        writer.writerow(row)
    tmp.close()

    return tmp.name


def create_dlc_raw_csv_xy_only(
    body_parts: List[str],
    n_frames: int = 5
) -> str:
    """Create a temporary raw DLC CSV with two columns (x, y) per bodypart."""
    scorer_row = ["scorer"] + ["DLC_model"] * (len(body_parts) * 2)
    bodyparts_row = ["bodyparts"]
    coords_row = ["coords"]

    for part in body_parts:
        bodyparts_row += [part, part]
        coords_row += ["x", "y"]

    data_rows = []
    for i in range(n_frames):
        row = [str(i)]
        for _ in body_parts:
            row += [
                str(round(100.0 + i, 2)),
                str(round(200.0 + i, 2)),
            ]
        data_rows.append(row)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    import csv
    writer = csv.writer(tmp)
    writer.writerow(scorer_row)
    writer.writerow(bodyparts_row)
    writer.writerow(coords_row)
    for row in data_rows:
        writer.writerow(row)
    tmp.close()

    return tmp.name


def create_enriched_csv(
    body_parts_by_group: Dict[str, List[str]],
    n_frames: int = 5
) -> str:
    """
    Create a temporary enriched output CSV file.
    Returns the path to the temporary file.
    """
    # Map group names to column prefixes
    group_to_prefix = {
        "spine": "Spine",
        "left_fin": "LeftFin",
        "right_fin": "RightFin",
        "tail": "Tail",
    }

    # Build column headers
    base_cols = ["Time", "LF_Angle", "RF_Angle", "HeadYaw"]
    coord_cols = []

    for group, parts in body_parts_by_group.items():
        prefix = group_to_prefix.get(group, "Unknown")
        for part in parts:
            coord_cols += [
                f"{prefix}_{part}_x",
                f"{prefix}_{part}_y",
                f"{prefix}_{part}_conf",
            ]

    all_cols = base_cols + coord_cols

    # Build data rows
    rows = []
    for i in range(n_frames):
        row = {col: round(100.0 + i * 0.1, 3) for col in all_cols}
        row["Time"] = i
        rows.append(row)

    df = pd.DataFrame(rows, columns=all_cols)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    df.to_csv(tmp.name, index=False)
    tmp.close()

    return tmp.name

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def standard_body_parts():
    """Standard body parts matching correct_format.csv."""
    return ["Head", "LE", "RE", "BF", "LF1", "LF2", "RF1", "RF2",
            "SB", "T1", "T2", "T3", "T4", "T5", "T6",
            "T7", "T8", "T9", "T10", "ET"]

@pytest.fixture
def minimal_body_parts():
    """Minimal set of body parts for simple tests."""
    return ["Head", "BF", "LF1", "RF1", "ET"]

@pytest.fixture
def dlc_raw_csv_path(standard_body_parts):
    """Path to a temporary raw DLC CSV with standard body parts."""
    path = create_dlc_raw_csv(standard_body_parts)
    yield path
    os.unlink(path)

@pytest.fixture
def minimal_dlc_csv_path(minimal_body_parts):
    """Path to a temporary raw DLC CSV with minimal body parts."""
    path = create_dlc_raw_csv(minimal_body_parts)
    yield path
    os.unlink(path)

@pytest.fixture
def enriched_csv_path():
    """Path to a temporary enriched CSV file."""
    body_parts_by_group = {
        "spine": ["Head", "BF", "SB", "T1", "T2", "ET"],
        "left_fin": ["LF1", "LF2"],
        "right_fin": ["RF1", "RF2"],
        "tail": ["T1", "T2", "T3"],
    }
    path = create_enriched_csv(body_parts_by_group)
    yield path
    os.unlink(path)

@pytest.fixture
def dlc_dataframe(standard_body_parts):
    """DataFrame loaded with header=1, mimicking parser.py behaviour."""
    path = create_dlc_raw_csv(standard_body_parts)
    df = pd.read_csv(path, header=1)
    os.unlink(path)
    return df

# ---------------------------------------------------------------------------
# Tests: detect_body_parts (file-based)
# ---------------------------------------------------------------------------

class TestDetectBodyParts:
    """Tests for the main detect_body_parts function."""

    def test_detects_all_standard_body_parts(
        self, dlc_raw_csv_path, standard_body_parts
    ):
        """Should detect all body parts from a standard DLC CSV."""
        result = detect_body_parts(dlc_raw_csv_path)

        assert isinstance(result, BodyPartDetectionResult)
        for part in standard_body_parts:
            assert part in result.all_body_parts

    def test_returns_sorted_body_parts(self, dlc_raw_csv_path):
        """Body parts list should be sorted alphabetically."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert result.all_body_parts == sorted(result.all_body_parts)

    def test_source_type_dlc_raw(self, dlc_raw_csv_path):
        """Source type should be 'dlc_raw' for raw DLC CSV."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert result.source_type == "dlc_raw"

    def test_source_type_enriched(self, enriched_csv_path):
        """Source type should be 'enriched' for enriched CSV."""
        result = detect_body_parts(enriched_csv_path)
        assert result.source_type == "enriched"

    def test_column_map_has_xyz_for_each_part(self, dlc_raw_csv_path):
        """Each body part should have x, y, conf file indices (classic DLC)."""
        result = detect_body_parts(dlc_raw_csv_path)

        for part, indices in result.column_map.items():
            assert "x" in indices
            assert "y" in indices
            assert "conf" in indices
            assert isinstance(indices["x"], int)
            assert indices["conf"] >= 1

    def test_xy_only_column_map_omits_conf_index(self):
        """XY-only raw DLC maps conf to -1 (no likelihood column on disk)."""
        path = create_dlc_raw_csv_xy_only(["Head", "LF1"])
        try:
            result = detect_body_parts(path)
            assert result.column_map["Head"]["conf"] == -1
            assert result.column_map["LF1"]["conf"] == -1
            assert result.column_map["Head"]["y"] == result.column_map["Head"]["x"] + 1
        finally:
            os.unlink(path)

    def test_file_not_found_raises_error(self):
        """Should raise FileNotFoundError for non-existent file."""
        with pytest.raises(FileNotFoundError, match="not found"):
            detect_body_parts("non_existent_file.csv")

    def test_minimal_body_parts(self, minimal_dlc_csv_path, minimal_body_parts):
        """Should work correctly with a minimal set of body parts."""
        result = detect_body_parts(minimal_dlc_csv_path)

        for part in minimal_body_parts:
            assert part in result.all_body_parts

    def test_no_duplicate_body_parts(self, dlc_raw_csv_path):
        """Should not return duplicate body part names."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert len(result.all_body_parts) == len(set(result.all_body_parts))

    def test_to_dict_structure(self, dlc_raw_csv_path):
        """to_dict() should return all expected keys."""
        result = detect_body_parts(dlc_raw_csv_path)
        d = result.to_dict()

        required_keys = [
            "all_body_parts", "grouped", "source_type",
            "column_map", "skipped_columns", "warnings",
            "body_part_count"
        ]
        for key in required_keys:
            assert key in d

    def test_body_part_count_matches(self, dlc_raw_csv_path):
        """body_part_count in dict should match len(all_body_parts)."""
        result = detect_body_parts(dlc_raw_csv_path)
        d = result.to_dict()
        assert d["body_part_count"] == len(result.all_body_parts)

    def test_warnings_is_list(self, dlc_raw_csv_path):
        """Warnings should always be a list."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert isinstance(result.warnings, list)

    def test_skipped_columns_is_list(self, dlc_raw_csv_path):
        """Skipped columns should always be a list."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert isinstance(result.skipped_columns, list)

# ---------------------------------------------------------------------------
# Tests: grouping logic
# ---------------------------------------------------------------------------

class TestGrouping:
    """Tests for body part grouping by category."""

    def test_left_fin_parts_grouped_correctly(self, dlc_raw_csv_path):
        """LF1, LF2 should be in left_fin group."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert "left_fin" in result.grouped
        assert "LF1" in result.grouped["left_fin"]
        assert "LF2" in result.grouped["left_fin"]

    def test_right_fin_parts_grouped_correctly(self, dlc_raw_csv_path):
        """RF1, RF2 should be in right_fin group."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert "right_fin" in result.grouped
        assert "RF1" in result.grouped["right_fin"]
        assert "RF2" in result.grouped["right_fin"]

    def test_spine_parts_grouped_correctly(self, dlc_raw_csv_path):
        """Head, BF, SB, T1-T10, ET should be in spine group."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert "spine" in result.grouped
        spine = result.grouped["spine"]
        assert "Head" in spine
        assert "BF" in spine
        assert "ET" in spine
        assert "T1" in spine

    def test_eye_parts_grouped_correctly(self, dlc_raw_csv_path):
        """LE and RE should be in eyes group."""
        result = detect_body_parts(dlc_raw_csv_path)
        assert "eyes" in result.grouped
        assert "LE" in result.grouped["eyes"]
        assert "RE" in result.grouped["eyes"]

    def test_no_empty_groups(self, dlc_raw_csv_path):
        """Grouped dictionary should not contain empty lists."""
        result = detect_body_parts(dlc_raw_csv_path)
        for group_name, parts in result.grouped.items():
            assert len(parts) > 0, f"Group '{group_name}' is empty"

    def test_unknown_body_parts_go_to_unknown_group(self):
        """Body parts with unknown names should go to unknown group."""
        # Create CSV with a non-standard body part name
        path = create_dlc_raw_csv(["Head", "MyCustomPart", "ET"])
        try:
            result = detect_body_parts(path)
            assert "unknown" in result.grouped
            assert "MyCustomPart" in result.grouped["unknown"]
        finally:
            os.unlink(path)

    def test_variable_spine_segments(self):
        """Should correctly group any number of spine T segments."""
        # Lab with only 5 tail segments instead of 10
        path = create_dlc_raw_csv(
            ["Head", "BF", "SB", "T1", "T2", "T3", "T4", "T5", "ET"]
        )
        try:
            result = detect_body_parts(path)
            spine = result.grouped.get("spine", [])
            for seg in ["T1", "T2", "T3", "T4", "T5"]:
                assert seg in spine
        finally:
            os.unlink(path)

# ---------------------------------------------------------------------------
# Tests: detect_body_parts_from_dataframe
# ---------------------------------------------------------------------------

class TestFromDataFrame:
    """Tests for DataFrame-based detection."""

    def test_basic_dlc_dataframe(self, dlc_dataframe):
        """Should detect body parts from a DataFrame loaded with header=1."""
        result = detect_body_parts_from_dataframe(dlc_dataframe)
        assert isinstance(result, BodyPartDetectionResult)
        assert len(result.all_body_parts) > 0

    def test_dlc_dataframe_xy_only(self):
        """DataFrame from XY-only DLC should report conf index -1 in column_map."""
        path = create_dlc_raw_csv_xy_only(["Head", "ET"])
        try:
            df = pd.read_csv(path, header=1)
            result = detect_body_parts_from_dataframe(df, source_type="dlc_raw")
            assert "Head" in result.all_body_parts
            assert result.column_map["Head"]["conf"] == -1
            assert result.column_map["Head"]["y"] == result.column_map["Head"]["x"] + 1
        finally:
            os.unlink(path)

    def test_auto_detects_dlc_format(self, dlc_dataframe):
        """Auto detection should identify DLC format from column names."""
        result = detect_body_parts_from_dataframe(dlc_dataframe, source_type="auto")
        assert result.source_type == "dlc_raw"

    def test_auto_detects_enriched_format(self):
        """Auto detection should identify enriched format from column names."""
        df = pd.DataFrame(columns=[
            "Time", "LF_Angle",
            "Spine_Head_x", "Spine_Head_y", "Spine_Head_conf",
            "LeftFin_LF1_x", "LeftFin_LF1_y", "LeftFin_LF1_conf",
        ])
        result = detect_body_parts_from_dataframe(df, source_type="auto")
        assert result.source_type == "enriched"

    def test_enriched_dataframe_detection(self):
        """Should detect body parts from an enriched format DataFrame."""
        df = pd.DataFrame(columns=[
            "Time", "LF_Angle", "RF_Angle",
            "Spine_Head_x", "Spine_Head_y", "Spine_Head_conf",
            "Spine_BF_x", "Spine_BF_y", "Spine_BF_conf",
            "LeftFin_LF1_x", "LeftFin_LF1_y", "LeftFin_LF1_conf",
            "RightFin_RF1_x", "RightFin_RF1_y", "RightFin_RF1_conf",
        ])
        result = detect_body_parts_from_dataframe(df, source_type="enriched")

        assert "Head" in result.all_body_parts
        assert "BF" in result.all_body_parts
        assert "LF1" in result.all_body_parts
        assert "RF1" in result.all_body_parts
    def test_empty_dataframe_returns_empty_result(self):
        """Should return empty result for empty DataFrame."""
        df = pd.DataFrame()
        result = detect_body_parts_from_dataframe(df)

        assert isinstance(result, BodyPartDetectionResult)
        assert result.all_body_parts == []

    def test_no_body_part_columns_returns_empty(self):
        """Should return empty result if no body part columns exist."""
        df = pd.DataFrame(columns=["Time", "LF_Angle", "RF_Angle"])
        result = detect_body_parts_from_dataframe(df, source_type="enriched")

        assert result.all_body_parts == []

    def test_explicit_dlc_source_type(self, dlc_dataframe):
        """Should work correctly with explicit dlc_raw source type."""
        result = detect_body_parts_from_dataframe(
            dlc_dataframe, source_type="dlc_raw"
        )
        assert result.source_type == "dlc_raw"
        assert len(result.all_body_parts) > 0

    def test_explicit_enriched_source_type(self):
        """Should work correctly with explicit enriched source type."""
        df = pd.DataFrame(columns=[
            "Spine_Head_x", "Spine_Head_y", "Spine_Head_conf",
            "LeftFin_LF1_x", "LeftFin_LF1_y", "LeftFin_LF1_conf",
        ])
        result = detect_body_parts_from_dataframe(
            df, source_type="enriched"
        )
        assert result.source_type == "enriched"
        assert "Head" in result.all_body_parts
        assert "LF1" in result.all_body_parts


# ---------------------------------------------------------------------------
# Tests: convenience functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    """Tests for get_body_part_names and get_grouped_body_parts."""

    def test_get_body_part_names_returns_list(self, dlc_raw_csv_path):
        """get_body_part_names should return a list of strings."""
        names = get_body_part_names(dlc_raw_csv_path)

        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_get_body_part_names_matches_detect(self, dlc_raw_csv_path):
        """get_body_part_names should match detect_body_parts result."""
        names = get_body_part_names(dlc_raw_csv_path)
        result = detect_body_parts(dlc_raw_csv_path)

        assert names == result.all_body_parts

    def test_get_grouped_body_parts_returns_dict(self, dlc_raw_csv_path):
        """get_grouped_body_parts should return a dictionary."""
        groups = get_grouped_body_parts(dlc_raw_csv_path)
        assert isinstance(groups, dict)

    def test_get_grouped_body_parts_matches_detect(self, dlc_raw_csv_path):
        """get_grouped_body_parts should match detect_body_parts result."""
        groups = get_grouped_body_parts(dlc_raw_csv_path)
        result = detect_body_parts(dlc_raw_csv_path)

        assert groups == result.grouped

    def test_get_body_part_names_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            get_body_part_names("missing_file.csv")

    def test_get_grouped_body_parts_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            get_grouped_body_parts("missing_file.csv")


# ---------------------------------------------------------------------------
# Tests: variable body part counts (core requirement of Issue #73)
# ---------------------------------------------------------------------------

class TestVariableBodyPartCounts:
    """
    Tests verifying the system handles different labs with
    different numbers of body parts without crashing.
    """

    def test_lab_with_fewer_spine_points(self):
        """Lab tracking only 3 spine segments should work fine."""
        path = create_dlc_raw_csv(
            ["Head", "BF", "T1", "T2", "T3", "ET", "LF1", "RF1"]
        )
        try:
            result = detect_body_parts(path)
            assert "Head" in result.all_body_parts
            assert "T1" in result.all_body_parts
            assert "T3" in result.all_body_parts
            assert "LF1" in result.all_body_parts
        finally:
            os.unlink(path)

    def test_lab_with_more_spine_points(self):
        """Lab tracking 15 spine segments should work fine."""
        spine_parts = ["Head", "BF", "SB"] + \
                      [f"T{i}" for i in range(1, 16)] + ["ET"]
        path = create_dlc_raw_csv(spine_parts)
        try:
            result = detect_body_parts(path)
            for part in spine_parts:
                assert part in result.all_body_parts
        finally:
            os.unlink(path)

    def test_lab_with_no_fin_points(self):
        """Lab not tracking fins should not crash."""
        path = create_dlc_raw_csv(
            ["Head", "BF", "SB", "T1", "T2", "ET"]
        )
        try:
            result = detect_body_parts(path)
            assert "left_fin" not in result.grouped
            assert "right_fin" not in result.grouped
            assert "Head" in result.all_body_parts
        finally:
            os.unlink(path)

    def test_lab_with_extra_custom_parts(self):
        """Lab with extra custom body parts should not crash."""
        path = create_dlc_raw_csv(
            ["Head", "BF", "LF1", "RF1", "ET",
             "DorsalFin", "PectoralFin", "CustomPoint"]
        )
        try:
            result = detect_body_parts(path)
            # Custom parts should land in unknown group
            assert "DorsalFin" in result.all_body_parts
            assert "PectoralFin" in result.all_body_parts
            assert "CustomPoint" in result.all_body_parts
            assert "unknown" in result.grouped
        finally:
            os.unlink(path)

    def test_single_body_part_csv(self):
        """CSV with only one body part should not crash."""
        path = create_dlc_raw_csv(["Head"])
        try:
            result = detect_body_parts(path)
            assert "Head" in result.all_body_parts
            assert len(result.all_body_parts) == 1
        finally:
            os.unlink(path)

    def test_two_datasets_different_body_parts(self):
        """
        Two datasets with different body part counts should both
        be detected correctly and independently.
        """
        # Lab A: 5 body parts
        path_a = create_dlc_raw_csv(
            ["Head", "BF", "LF1", "RF1", "ET"]
        )
        # Lab B: 10 body parts
        path_b = create_dlc_raw_csv(
            ["Head", "LE", "RE", "BF", "LF1", "LF2",
             "RF1", "RF2", "SB", "ET"]
        )
        try:
            result_a = detect_body_parts(path_a)
            result_b = detect_body_parts(path_b)

            assert len(result_a.all_body_parts) == 5
            assert len(result_b.all_body_parts) == 10

            # Each result should be independent
            assert "LE" not in result_a.all_body_parts
            assert "LE" in result_b.all_body_parts
        finally:
            os.unlink(path_a)
            os.unlink(path_b)


# ---------------------------------------------------------------------------
# Tests: integration
# ---------------------------------------------------------------------------

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_workflow_dlc_raw(self, dlc_raw_csv_path, standard_body_parts):
        """
        Full workflow test:
        1. Detect body parts from raw DLC CSV
        2. Verify all parts detected
        3. Verify grouping
        4. Verify column map
        5. Serialise to dict
        """
        # Step 1: Detect
        result = detect_body_parts(dlc_raw_csv_path)

        # Step 2: Verify all parts
        for part in standard_body_parts:
            assert part in result.all_body_parts

        # Step 3: Verify grouping
        assert "spine" in result.grouped
        assert "left_fin" in result.grouped
        assert "right_fin" in result.grouped
        assert "eyes" in result.grouped

        # Step 4: Verify column map
        for part in result.all_body_parts:
            assert part in result.column_map
            assert "x" in result.column_map[part]
            assert "y" in result.column_map[part]
            assert "conf" in result.column_map[part]

        # Step 5: Serialise
        d = result.to_dict()
        assert d["body_part_count"] == len(standard_body_parts)

    def test_full_workflow_enriched(self, enriched_csv_path):
        """
        Full workflow test for enriched CSV:
        1. Detect body parts
        2. Verify source type
        3. Verify grouping
        4. Serialise to dict
        """
        # Step 1: Detect
        result = detect_body_parts(enriched_csv_path)

        # Step 2: Verify source type
        assert result.source_type == "enriched"

        # Step 3: Verify grouping
        assert len(result.grouped) > 0

        # Step 4: Serialise
        d = result.to_dict()
        assert isinstance(d["all_body_parts"], list)
        assert isinstance(d["grouped"], dict)

    def test_result_is_json_serialisable(self, dlc_raw_csv_path):
        """Result dict should be fully JSON serialisable."""
        import json

        result = detect_body_parts(dlc_raw_csv_path)
        d = result.to_dict()

        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_detection_does_not_modify_original_csv(self, dlc_raw_csv_path):
        """Detection should be read-only and not modify the CSV file."""
        import hashlib

        # Get file hash before detection
        with open(dlc_raw_csv_path, "rb") as f:
            hash_before = hashlib.md5(f.read()).hexdigest()

        # Run detection
        detect_body_parts(dlc_raw_csv_path)

        # Get file hash after detection
        with open(dlc_raw_csv_path, "rb") as f:
            hash_after = hashlib.md5(f.read()).hexdigest()

        assert hash_before == hash_after

    def test_repr_is_informative(self, dlc_raw_csv_path):
        """__repr__ should return a meaningful string."""
        result = detect_body_parts(dlc_raw_csv_path)
        repr_str = repr(result)

        assert "BodyPartDetectionResult" in repr_str
        assert "dlc_raw" in repr_str
        assert len(repr_str) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
