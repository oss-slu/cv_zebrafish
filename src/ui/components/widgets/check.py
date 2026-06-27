"""Utility script to validate a JSON configuration file against the schema."""

from __future__ import annotations

import json
from pathlib import Path

from cvzebrafish.core.validation import json_verifier
from cvzebrafish.platform.paths import default_sample_config


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_config(path: Path) -> list[str]:
    config = load_config(path)
    errors = json_verifier.validate_config(config, json_verifier.SCHEMA)
    if hasattr(json_verifier, "extra_checks"):
        errors.extend(json_verifier.extra_checks(config))
    if hasattr(json_verifier, "guidance_messages"):
        guidance = json_verifier.guidance_messages(config)
        if guidance:
            print("\nGuidance:")
            for message in guidance:
                print(f" - {message}")
    return errors


def main():
    config_path = default_sample_config()
    print(f"[INFO] Validating config at {config_path}")
    try:
        errors = validate_config(config_path)
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {config_path}")
        return

    if errors:
        print("\n[ERROR] Validation failed:")
        for err in errors:
            print(f" - {err}")
    else:
        print("\n[SUCCESS] JSON config file is valid.")


if __name__ == "__main__":
    main()
