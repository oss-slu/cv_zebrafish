
## Key Components

### 1. `Utils/Driver.py`
- **Purpose:** Orchestrates the calculation pipeline by combining parsed data and configuration settings.
- **Functionality:**
  - Accepts parsed points and configuration as input.
  - Computes kinematic metrics such as fin angles and head yaw.
  - Outputs a DataFrame with calculated metrics.

### 2. `Utils/Metrics.py`
- **Purpose:** Contains the core mathematical functions for calculating movement metrics.
- **Key Functions:**
  - `calc_fin_angle(head1, head2, fin_points)`: Calculates the angles of the fins relative to the head centerline.
  - `calc_yaw(head1, head2)`: Computes the yaw (orientation) of the head centerline.

### 3. `Utils/Parser.py`
- **Purpose:** Parses DLC-style CSV files into a structured format for calculations.
- **Functionality:**
  - Converts CSV data into a dictionary of body parts with their respective `(x, y, likelihood)` arrays.
  - Handles missing or invalid data gracefully.

### 4. `Utils/configSetup.py`
- **Purpose:** Loads and validates configuration files for the calculation pipeline.
- **Functionality:**
  - Reads configuration files in JSON format.
  - Ensures all required parameters are present and valid.

---

## Tests

### 1. `tests/test_Driver.py`
- **Purpose:** Tests the `Driver` module to ensure the calculation pipeline runs correctly.
- **Key Tests:**
  - Validates the structure and content of the output DataFrame.
  - Ensures all metrics are calculated as expected.

### 2. `tests/test_Parser.py`
- **Purpose:** Tests the `Parser` module for correct parsing of DLC CSV files.
- **Key Tests:**
  - Validates the parsing of body part coordinates and likelihoods.
  - Ensures proper handling of missing or invalid data.

### 3. `tests/test_Calculations.py`
- **Purpose:** Tests the `Metrics` module for numerical correctness of calculations.
- **Key Tests:**
  - Verifies the accuracy of fin angle and yaw calculations.
  - Ensures proper handling of edge cases, such as zero-length centerlines.

---

## How to Use

### 1. Prerequisites
- Python 3.9+
- Required libraries: `numpy`, `pandas`

### 2. Running Calculations
To run the calculation pipeline:
```python
from Calculations.Utils.Driver import run_calculations

# Example usage
parsed_points = {
    "head_pt1": {"x": [1, 2], "y": [2, 3]},
    "head_pt2": {"x": [2, 3], "y": [3, 4]},
    "leftFin": [{"x": [3, 4], "y": [4, 5]}, {"x": [4, 5], "y": [5, 6]}],
    "rightFin": [{"x": [5, 6], "y": [6, 7]}, {"x": [6, 7], "y": [7, 8]}],
}
config = {
    "points": {"head": {"pt1": "head_pt1", "pt2": "head_pt2"}},
    "video_parameters": {"fps": 30},
}
df = run_calculations(parsed_points, config)
print(df)

### Running Tests 

python -m unittest discover -s Calculations/tests

### CONTRUBUTIONS 
# It is important to note that the config setup and parsers were done by Jacob! Even though this is one PR Jacobs sprint 2 work is here! 