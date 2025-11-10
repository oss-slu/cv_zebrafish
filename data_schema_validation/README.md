# Input Data Format for DeepLabCut CSV Validation

This project expects input data in the form of a DeepLabCut-generated CSV file. The file must follow a specific structure for successful validation and downstream analysis.

## Expected CSV Structure

- **Header Row 1:** Scorer/model name for each set of columns (e.g., `DLC_Resnet50_...`).
- **Header Row 2:** Bodypart name for each set of columns (e.g., `Head`, `LE`, `RE`, etc.).
- **Header Row 3:** Coordinate type for each column (`x`, `y`, `likelihood`).
- **Data Rows:** Numeric values for each frame and bodypart.

### Example (first few columns):

| scorer    | DLC_Resnet50... | DLC_Resnet50... | DLC_Resnet50... | ... |
| --------- | --------------- | --------------- | --------------- | --- |
| bodyparts | Head            | Head            | Head            | ... |
| coords    | x               | y               | likelihood      | ... |
| 0         | 403.84          | 520.24          | 0.88            | ... |
| 1         | 403.75          | 520.29          | 0.88            | ... |

- Each bodypart is represented by three columns: `x`, `y`, and `likelihood`.
- The first column is always `scorer`, followed by repeating sets of three columns per bodypart.

## Data Requirements

- **x, y:** Numeric pixel coordinates (should be within image bounds).
- **likelihood:** Float between 0 and 1 (confidence score).
- **No missing or non-numeric values** in coordinate or likelihood columns.
- **All bodyparts** must have all three columns: `x`, `y`, `likelihood`.

## Example File

See `sample_inputs/correct_format.csv` for a full example.

## Invalid Examples

- Missing columns for a bodypart (e.g., only `x` and `y` but no `likelihood`).
- Non-numeric values in any coordinate or likelihood column.
- Likelihood values outside the range [0, 1].

## Usage

Use the provided validation scripts to check your CSV files before analysis. Files not matching the above format will trigger errors or warnings.
