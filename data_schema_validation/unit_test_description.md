# Data Schema Validation Unit Tests

This document describes the unit tests implemented in `unit_test.py` for validating DeepLabCut CSV input files and listing bodyparts using the functions in `input_verifier.py`.

## Test Overview

### 1. `test_valid_csv`

- **Purpose:** Checks that a correctly formatted CSV passes all validation checks.
- **Checks:**
  - No errors or warnings are returned for a valid file.

### 2. `test_wrong_columns`

- **Purpose:** Ensures the validator detects missing or incorrect columns for bodyparts.
- **Checks:**
  - An error is returned if the columns for a bodypart do not match the expected set (`x`, `y`, `likelihood`).

### 3. `test_non_numeric_values`

- **Purpose:** Verifies that non-numeric values in coordinate columns are flagged.
- **Checks:**
  - An error is returned if any coordinate value is not numeric.

### 4. `test_out_of_range_coordinates`

- **Purpose:** Checks that coordinate values outside the image bounds are warned about.
- **Checks:**
  - A warning is returned if `x` or `y` values are outside the specified image width or height.

### 5. `test_likelihood_out_of_bounds`

- **Purpose:** Ensures likelihood values outside the [0, 1] range are warned about.
- **Checks:**
  - A warning is returned if any likelihood value is less than 0 or greater than 1.

### 6. `test_list_bodyparts`

- **Purpose:** Verifies that the function correctly lists all unique bodyparts in the CSV.
- **Checks:**
  - The output includes all bodypart names present in the file.

## Helper Functions

- **`make_csv(content: str)`**: Utility to create a file-like object from a string for use with `pandas.read_csv`.

## Usage

- The tests use `pytest` and temporary files to simulate different CSV input scenarios.
- The tested functions are imported from `data_schema_validation.src.input_verifier`.

---

For more details, see the source code in `unit_test.py` and `input_verifier.py`.
