import json
import sys

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

# =============== VALIDATION FUNCTION ===============
def validate_config(config: dict, schema: dict, path="root"):
    errors = []
    for key, expected_type in schema.items():
        if key not in config:
            errors.append(f"Missing key at {path}: '{key}'")
            continue
        value = config[key]
        if isinstance(expected_type, dict):
            if not isinstance(value, dict):
                errors.append(
                    f"Wrong type at {path}.{key}: expected dict, got {type(value).__name__}")
            else:
                errors.extend(validate_config(
                    value, expected_type, path=f"{path}.{key}"))
        else:
            if not isinstance(value, expected_type):
                errors.append(
                    f"Wrong type at {path}.{key}: expected {expected_type.__name__}, got {type(value).__name__}")
    return errors

# =============== EXTRA SEMANTIC VALIDATION ===============
def extra_checks(config: dict):
    errors = []
    points = config.get("points", {})

    # right_fin and left_fin must have at least 2 points
    for fin_key in ["right_fin", "left_fin"]:
        if fin_key in points:
            if not isinstance(points[fin_key], list) or len(points[fin_key]) < 2:
                errors.append(
                    f"{fin_key} must be a list with at least 2 elements")

    # spine and tail must have at least 2 points
    for part_key in ["spine", "tail"]:
        if part_key in points:
            if not isinstance(points[part_key], list) or len(points[part_key]) < 2:
                errors.append(
                    f"{part_key} must be a list with at least 2 elements")

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

# =============== MAIN SCRIPT ===============
def main(json_file):
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    errors = validate_config(config, SCHEMA)
    errors.extend(extra_checks(config))

    if errors:
        print("❌ Validation failed with the following issues:")
        for e in errors:
            print(" -", e)
    else:
        print("✅ JSON config file is valid and matches the expected schema.")

# =============== USAGE ===============
if __name__ == "__main__":
    if len(sys.argv) == 2:
        config_path = sys.argv[1]
    else:
        config_path = input("Enter the path to the config JSON file: ").strip()
    main(config_path)
