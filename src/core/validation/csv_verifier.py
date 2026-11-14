import os

import pandas as pd

from ..input_source import CsvSource, InputSourceError, is_path, load_csv_source

# A DeepLabCut CSV needs the bodyparts and coords rows, plus at least one
# column after the scorer column.
MIN_ROWS = 2
MIN_COLUMNS = 2


def verify_deeplabcut_csv(source: CsvSource, img_width=None, img_height=None):
    """Validate a DeepLabCut CSV given as a path, file-like object, or DataFrame.

    Returns ``(errors, warnings)``. Malformed input produces an error message
    instead of raising.
    """
    errors = []
    warnings = []

    if is_path(source):
        file_path = os.fspath(source)
        if not os.path.isfile(file_path):
            errors.append(f"[ERROR] File does not exist: {file_path}")
            return errors, warnings
        if not file_path.lower().endswith('.csv'):
            errors.append(f"[ERROR] File is not a CSV: {file_path}")
            return errors, warnings

    try:
        df = load_csv_source(source)
    except InputSourceError as exc:
        errors.append(f"[ERROR] {exc}")
        return errors, warnings

    if df.shape[0] < MIN_ROWS or df.shape[1] < MIN_COLUMNS:
        errors.append(
            "[ERROR] File is too small to be a DeepLabCut CSV: expected "
            "bodyparts and coords rows below the header."
        )
        return errors, warnings

    # Extract header rows
    bodyparts = df.iloc[0]
    coords = df.iloc[1]

    # 1. Column structure check
    bp_groups = {}
    for col, bp, coord in zip(df.columns[1:], bodyparts[1:], coords[1:]):
        bp_groups.setdefault(bp, []).append(coord)

    for bp, coord_list in bp_groups.items():
        expected_full = ["x", "y", "likelihood"]
        expected_xy = ["x", "y"]
        if coord_list not in (expected_full, expected_xy):
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
                    errors.append(f"[ERROR] Values out of range in {bp}-y")
        elif coord == "likelihood":
            if ((vals < 0) | (vals > 1)).any():
                warnings.append(f"[WARN] Likelihood out of [0,1] for {bp}")

    return errors, warnings


def list_bodyparts(source: CsvSource):
    """Return the unique bodypart names, or an empty list if there is no bodyparts row.

    Unlike ``verify_deeplabcut_csv``, an unreadable file still raises the
    original pandas error, as it did before.
    """
    try:
        df = load_csv_source(source)
    except InputSourceError as exc:
        raise exc.__cause__ from None
    if df.shape[0] < 1:
        return []
    return df.iloc[0, 1:].unique()


if __name__ == "__main__":
    file_path = input("Enter the path to the DLC CSV file: ").strip()
    errors, warnings = verify_deeplabcut_csv(file_path)
    bodyparts = list_bodyparts(file_path)
    print(f"Bodyparts found: {', '.join(bodyparts)}")

    if not errors and not warnings:
        print("✅ File passed all checks.")
    else:
        print("\n".join(errors + warnings))
