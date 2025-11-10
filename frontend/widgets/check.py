import importlib.util
import json
from os import getcwd, path
from sys import modules

# === Import json_verifier dynamically ===
module_name = "json_verifier"
parent_dir = path.abspath(path.join(getcwd(), path.pardir))
file_path = path.join(parent_dir, "data_schema_validation",
                      "src", module_name + ".py")

spec = importlib.util.spec_from_file_location(module_name, file_path)
json_verifier = importlib.util.module_from_spec(spec)
modules[module_name] = json_verifier
spec.loader.exec_module(json_verifier)

print("✅ json_verifier module loaded successfully")

# === Load input JSON file ===
# ← replace this with your file path
json_path = r"C:\Users\Finn\Downloads\SLU\Fall_2025\CSCI_4961\cv_zebrafish\data_schema_validation\sample_inputs\jsons\BaseConfig.json"

try:
    with open(json_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"📄 Loaded JSON: {json_path}")
except Exception as e:
    print(f"❌ Error reading JSON file: {e}")
    exit(1)

# === Validate against schema ===
print("\n🔍 Running schema validation...")
errors = json_verifier.validate_config(config, json_verifier.SCHEMA)

# === Optional: run extra checks if available ===
if hasattr(json_verifier, "extra_checks"):
    print("🧩 Running extra checks...")
    errors.extend(json_verifier.extra_checks(config))

if errors:
    print("\n❌ Validation failed with the following issues:")
    for e in errors:
        print(" -", e)
else:
    print("\n✅ JSON config file is valid and matches the expected schema.")

# === Optional: guidance messages ===
if hasattr(json_verifier, "guidance_messages"):
    guidance = json_verifier.guidance_messages(config)
    if guidance:
        print("\nℹ️  Guidance:")
        for m in guidance:
            print(" -", m)

print("\n=== Done ===")
