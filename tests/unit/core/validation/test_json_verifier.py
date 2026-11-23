import copy
import json
from pathlib import Path

import pytest

from src.core.validation.json_verifier import (
    SCHEMA,
    extra_checks,
    guidance_messages,
    is_adult_species,
    validate_config,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
ADULT_CONFIG_PATH = REPO_ROOT / "data" / "samples" / "jsons" / "AdultConfig.json"
BASE_CONFIG_PATH = REPO_ROOT / "data" / "samples" / "jsons" / "BaseConfig.json"


@pytest.fixture
def adult_config():
    return json.loads(ADULT_CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def base_config():
    return json.loads(BASE_CONFIG_PATH.read_text(encoding="utf-8"))


def test_adult_config_passes_as_adult(adult_config):
    """AdultConfig.json must pass both structural and semantic validation as adult."""
    schema_errors = validate_config(adult_config, SCHEMA, species="adult")
    semantic_errors = extra_checks(adult_config, species="adult")
    assert schema_errors == []
    assert semantic_errors == []


def test_adult_config_fails_as_larval(adult_config):
    """AdultConfig.json must fail larval validation because fins and tail require >= 2 points."""
    schema_errors = validate_config(adult_config, SCHEMA, species="larval")
    semantic_errors = extra_checks(adult_config, species="larval")
    assert schema_errors == []
    assert any("right_fin must be a list with at least 2 elements" in err for err in semantic_errors)
    assert any("left_fin must be a list with at least 2 elements" in err for err in semantic_errors)
    assert any("tail must be a list with at least 2 elements" in err for err in semantic_errors)


def test_base_config_passes_as_larval(base_config):
    """BaseConfig.json must continue to pass validation as larval."""
    schema_errors = validate_config(base_config, SCHEMA, species="larval")
    semantic_errors = extra_checks(base_config, species="larval")
    assert schema_errors == []
    assert semantic_errors == []


def test_adult_fins_are_optional_when_omitted(adult_config):
    """Adult configs may omit left_fin and right_fin completely."""
    cfg = copy.deepcopy(adult_config)
    del cfg["points"]["right_fin"]
    del cfg["points"]["left_fin"]

    schema_errors = validate_config(cfg, SCHEMA, species="adult")
    semantic_errors = extra_checks(cfg, species="adult")
    assert schema_errors == []
    assert semantic_errors == []

    # Omitted fins fail under larval schema validation
    larval_schema_errors = validate_config(cfg, SCHEMA, species="larval")
    assert any("right_fin" in err for err in larval_schema_errors)
    assert any("left_fin" in err for err in larval_schema_errors)


def test_adult_fin_non_string_elements_fail(adult_config):
    """If adult config contains fins, non-string points must be rejected."""
    cfg = copy.deepcopy(adult_config)
    cfg["points"]["right_fin"] = [123]
    errors = extra_checks(cfg, species="adult")
    assert any("right_fin[0] must be a string, got int" in err for err in errors)


def test_adult_fin_not_a_list_fails(adult_config):
    """If adult fin key is not a list, it must be rejected."""
    cfg = copy.deepcopy(adult_config)
    cfg["points"]["left_fin"] = "invalid"
    errors = extra_checks(cfg, species="adult")
    assert any("left_fin must be a list" in err for err in errors)


def test_adult_tail_must_have_at_least_one_point(adult_config):
    """Adult configs must have at least 1 tail point."""
    cfg = copy.deepcopy(adult_config)
    cfg["points"]["tail"] = []
    errors = extra_checks(cfg, species="adult")
    assert any("tail must be a list with at least 1 element" in err for err in errors)


def test_adult_tail_non_string_elements_fail(adult_config):
    cfg = copy.deepcopy(adult_config)
    cfg["points"]["tail"] = [456]
    errors = extra_checks(cfg, species="adult")
    assert any("tail[0] must be a string, got int" in err for err in errors)


def test_adult_spine_must_have_at_least_two_points(adult_config):
    cfg = copy.deepcopy(adult_config)
    cfg["points"]["spine"] = ["p0"]
    errors = extra_checks(cfg, species="adult")
    assert any("spine must be a list with at least 2 elements" in err for err in errors)


def test_adult_duplicate_spine_or_tail_points_fail(adult_config):
    cfg_spine_dup = copy.deepcopy(adult_config)
    cfg_spine_dup["points"]["spine"] = ["p0", "p1", "p0"]
    assert any("spine must not contain duplicate point names" in err for err in extra_checks(cfg_spine_dup, species="adult"))

    cfg_tail_dup = copy.deepcopy(adult_config)
    cfg_tail_dup["points"]["tail"] = ["caudal_fin", "caudal_fin"]
    assert any("tail must not contain duplicate point names" in err for err in extra_checks(cfg_tail_dup, species="adult"))


def test_adult_spine_tail_overlap_fails(adult_config):
    cfg = copy.deepcopy(adult_config)
    cfg["points"]["spine"] = ["p0", "p1", "caudal_fin"]
    cfg["points"]["tail"] = ["caudal_fin"]
    errors = extra_checks(cfg, species="adult")
    assert any("spine and tail must not share the same point names" in err for err in errors)


def test_head_validation(adult_config):
    cfg_bad_head = copy.deepcopy(adult_config)
    cfg_bad_head["points"]["head"] = {"pt1": "p0"}
    assert any("head must contain exactly" in err for err in extra_checks(cfg_bad_head, species="adult"))

    cfg_bad_head_type = copy.deepcopy(adult_config)
    cfg_bad_head_type["points"]["head"] = {"pt1": "p0", "pt2": 123}
    assert any("head.pt2 must be a string" in err for err in extra_checks(cfg_bad_head_type, species="adult"))


def test_is_adult_species_resolution():
    assert is_adult_species("adult") is True
    assert is_adult_species("Adult_Zebrafish") is True
    assert is_adult_species("larval") is False
    assert is_adult_species("larval_zebrafish") is False
    assert is_adult_species(None, {"species": "adult"}) is True
    assert is_adult_species(None, {"species": "larval"}) is False
    assert is_adult_species(None, {}) is False


def test_guidance_messages(adult_config):
    msgs = guidance_messages(adult_config)
    assert any("bulk_input" in m for m in msgs)
    assert any("auto_find_time_ranges" in m for m in msgs)
