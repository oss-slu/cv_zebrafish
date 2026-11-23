import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# =============== CONFIG SCHEMA DEFINITION ===============
SCHEMA = {
    "file_inputs": {
        "data": str,
        "video": str,
        "bulk_input_path": str
    },
    "points": {
        "right_fin": list,
        "left_fin": list,
        "head": dict,
        "spine": list,
        "tail": list
    },
    "shown_outputs": dict,
    "angle_and_distance_plot_settings": dict,
    "spine_plot_settings": dict,
    "head_plot_settings": dict,
    "video_parameters": dict,
    "graph_cutoffs": dict,
    "auto_find_time_ranges": bool,
    "time_ranges": list,
    "open_plots": bool,
    "bulk_input": bool
}


# =============== SPECIES HELPER ===============
def is_adult_species(species=None, config: dict = None) -> bool:
    """Determine whether the target species is adult zebrafish."""
    if species is not None:
        s = getattr(species, "value", str(species)).strip().lower()
        if "adult" in s:
            return True
        if "larval" in s:
            return False
    if config and isinstance(config, dict):
        cfg_species = config.get("species")
        if cfg_species is not None:
            s = getattr(cfg_species, "value", str(cfg_species)).strip().lower()
            return "adult" in s
    return False


# =============== VALIDATION FUNCTION ===============
def validate_config(config: dict, schema: dict, path="root", species: str = "larval"):
    errors = []
    adult = is_adult_species(species, config)
    for key, expected_type in schema.items():
        if key not in config:
            # For adult zebrafish configs, fins are optional
            if adult and (path == "points" or path.endswith(".points")) and key in ("right_fin", "left_fin"):
                continue
            errors.append(f"Missing key at {path}: '{key}'")
            continue
        value = config[key]
        if isinstance(expected_type, dict):
            if not isinstance(value, dict):
                errors.append(
                    f"Wrong type at {path}.{key}: expected dict, got {type(value).__name__}")
            else:
                errors.extend(validate_config(
                    value, expected_type, path=f"{path}.{key}", species=species))
        else:
            if not isinstance(value, expected_type):
                errors.append(
                    f"Wrong type at {path}.{key}: expected {expected_type.__name__}, got {type(value).__name__}")
    return errors


# =============== EXTRA SEMANTIC VALIDATION ===============
def extra_checks(config: dict, species: str = "larval"):
    errors = []
    points = config.get("points", {})
    adult = is_adult_species(species, config)

    # Fin validation:
    # Larval: right_fin and left_fin must have at least 2 points
    # Adult: fins are optional; if present, must be a list of strings
    for fin_key in ["right_fin", "left_fin"]:
        if fin_key in points:
            fin_val = points[fin_key]
            if not adult:
                if not isinstance(fin_val, list) or len(fin_val) < 2:
                    errors.append(
                        f"{fin_key} must be a list with at least 2 elements")
                else:
                    for idx, v in enumerate(fin_val):
                        if not isinstance(v, str):
                            errors.append(
                                f"{fin_key}[{idx}] must be a string, got {type(v).__name__}")
            else:
                if not isinstance(fin_val, list):
                    errors.append(f"{fin_key} must be a list")
                else:
                    for idx, v in enumerate(fin_val):
                        if not isinstance(v, str):
                            errors.append(
                                f"{fin_key}[{idx}] must be a string, got {type(v).__name__}")

    # Spine validation: spine must have at least 2 points
    if "spine" in points:
        spine_val = points["spine"]
        if not isinstance(spine_val, list) or len(spine_val) < 2:
            errors.append("spine must be a list with at least 2 elements")
        else:
            for idx, v in enumerate(spine_val):
                if not isinstance(v, str):
                    errors.append(
                        f"spine[{idx}] must be a string, got {type(v).__name__}")

    # Tail validation:
    # Larval: tail must have at least 2 points
    # Adult: tail must have at least 1 point
    if "tail" in points:
        tail_val = points["tail"]
        min_tail_points = 1 if adult else 2
        min_tail_msg = (
            "tail must be a list with at least 1 element"
            if adult
            else "tail must be a list with at least 2 elements"
        )
        if not isinstance(tail_val, list) or len(tail_val) < min_tail_points:
            errors.append(min_tail_msg)
        else:
            for idx, v in enumerate(tail_val):
                if not isinstance(v, str):
                    errors.append(
                        f"tail[{idx}] must be a string, got {type(v).__name__}")

    # Backlog #2: unique names and no spine/tail overlap
    sp = points.get("spine")
    ta = points.get("tail")
    if isinstance(sp, list) and sp and all(isinstance(x, str) for x in sp):
        if len(sp) != len(set(sp)):
            errors.append("spine must not contain duplicate point names")
    if isinstance(ta, list) and ta and all(isinstance(x, str) for x in ta):
        if len(ta) != len(set(ta)):
            errors.append("tail must not contain duplicate point names")
    if isinstance(sp, list) and isinstance(ta, list):
        ov = set(sp) & set(ta)
        if ov:
            errors.append(
                f"spine and tail must not share the same point names: {sorted(ov)}"
            )

    # head must contain pt1 and pt2 as single string points
    head = points.get("head", {})
    if not isinstance(head, dict):
        errors.append("head must be a dictionary with 'pt1' and 'pt2'")
    else:
        required_keys = {"pt1", "pt2"}
        if set(head.keys()) != required_keys:
            errors.append(
                f"head must contain exactly {required_keys}, got {set(head.keys())}")
        else:
            for k in required_keys:
                if not isinstance(head[k], str):
                    errors.append(
                        f"head.{k} must be a string, got {type(head[k]).__name__}")

    return errors


# =============== GUIDANCE MESSAGES ===============
def guidance_messages(config: dict):
    """Return a list of informational messages about optional fields based on flags.

    - If `bulk_input` is False, the bulk input path is not required.
    - If `auto_find_time_ranges` is True, the `time_ranges` field is not required.
    """
    msgs = []
    # If bulk_input is explicitly False, bulk_input_path is not required.
    if config.get("bulk_input") is False:
        msgs.append(
            "'bulk_input' is False — 'file_inputs.bulk_input_path' is not required for this configuration.")

    # If auto_find_time_ranges is True, time_ranges is optional/unused.
    if config.get("auto_find_time_ranges"):
        msgs.append(
            "'auto_find_time_ranges' is True — 'time_ranges' is not required; ranges will be determined automatically.")

    return msgs


# =============== MAIN SCRIPT ===============
def main(json_file, species="larval"):
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return 1

    errors = validate_config(config, SCHEMA, species=species)
    errors.extend(extra_checks(config, species=species))

    stage_name = "adult" if is_adult_species(species, config) else "larval"
    if errors:
        print(f"[ERROR] Validation failed for {stage_name} zebrafish with the following issues:")
        for e in errors:
            print(" -", e)
        return 1
    else:
        print(f"[SUCCESS] JSON config file is valid for {stage_name} zebrafish and matches the expected schema.")

    # Print optional guidance messages based on config flags
    guidance = guidance_messages(config)
    if guidance:
        print("\n[INFO] Guidance:")
        for m in guidance:
            print(" -", m)
    return 0


# =============== USAGE ===============
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate CV Zebrafish JSON config.")
    parser.add_argument("config_path", nargs="?", default=None, help="Path to config JSON file")
    parser.add_argument(
        "--species",
        choices=["larval", "adult"],
        default="larval",
        help="Species stage to validate for (larval or adult, default: larval)",
    )
    args = parser.parse_args()

    config_path = args.config_path
    if not config_path:
        config_path = input("Enter the path to the config JSON file: ").strip()

    exit_code = main(config_path, species=args.species)
    sys.exit(exit_code)
