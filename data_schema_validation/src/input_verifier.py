
import os
import pandas as pd


def verify_deeplabcut_csv(file_path, img_width=None, img_height=None):

    errors = []
    warnings = []

    # Check if file exists
    if not os.path.isfile(file_path):
        errors.append(f"[ERROR] File does not exist: {file_path}")
        return errors, warnings

    # Check if file is a CSV
    if not file_path.lower().endswith('.csv'):
        errors.append(f"[ERROR] File is not a CSV: {file_path}")
        return errors, warnings

    # Load file
    df = pd.read_csv(file_path)

    # Extract header rows
    bodyparts = df.iloc[0]
    coords = df.iloc[1]

    # 1. Column structure check
    bp_groups = {}
    for col, bp, coord in zip(df.columns[1:], bodyparts[1:], coords[1:]):
        bp_groups.setdefault(bp, []).append(coord)

    for bp, coord_list in bp_groups.items():
        expected = {"x", "y", "likelihood"}
        if set(coord_list) != expected:
            errors.append(
                f"[ERROR] Bodypart '{bp}' has wrong columns: {coord_list}")

    # 2. Data validity check
    data = df.iloc[2:].copy()
    for col, bp, coord in zip(df.columns[1:], bodyparts[1:], coords[1:]):
        vals = pd.to_numeric(data[col], errors="coerce")

        if coord in ["x", "y"]:
            if vals.isna().any():
                errors.append(f"[ERROR] Non-numeric values in {bp}-{coord}")
            if img_width and coord == "x":
                if ((vals < 0) | (vals > img_width)).any():
                    warnings.append(f"[WARN] Values out of range in {bp}-x")
            if img_height and coord == "y":
                if ((vals < 0) | (vals > img_height)).any():
                    warnings.append(f"[WARN] Values out of range in {bp}-y")
        elif coord == "likelihood":
            if ((vals < 0) | (vals > 1)).any():
                warnings.append(f"[WARN] Likelihood out of [0,1] for {bp}")

    return errors, warnings


def list_bodyparts(file_path):
    # Load the CSV
    df = pd.read_csv(file_path)

    # First row contains bodypart names
    bodyparts = df.iloc[0, 1:].unique()  # skip first col (scorer)

    print("Annotated bodyparts:")
    for bp in bodyparts:
        print(f"- {bp}")


if __name__ == "__main__":
    file_path = input("Enter the path to the DLC CSV file: ").strip()
    errors, warnings = verify_deeplabcut_csv(file_path)
    list_bodyparts(file_path)

    if not errors and not warnings:
        print("✅ File passed all checks.")
    else:
        print("\n".join(errors + warnings))
