import unittest
import numpy as np
from calculations.utils.Driver import run_calculations

class TestRunner(unittest.TestCase):
    def setUp(self):
        # Minimal mock parsed_points and config
        self.parsed_points = {
            "head_pt1": {"x": np.array([1]), "y": np.array([1])},
            "head_pt2": {"x": np.array([2]), "y": np.array([2])},
            "left_fin": [{"x": np.array([3]), "y": np.array([3])}, {"x": np.array([4]), "y": np.array([4])}],
            "right_fin": [{"x": np.array([5]), "y": np.array([5])}, {"x": np.array([6]), "y": np.array([6])}],
            "spine": [{"x": np.array([7]), "y": np.array([7])}, {"x": np.array([8]), "y": np.array([8])}, {"x": np.array([9]), "y": np.array([9])}],
            "tail": [{"x": np.array([10]), "y": np.array([10])}, {"x": np.array([11]), "y": np.array([11])}],
            "tp": {"x": np.array([12]), "y": np.array([12])}
        }

        self.config = {
            "video_parameters": {"pixel_scale_factor":1, "dish_diameter_m":1, "pixel_diameter":1},
            "points": {"tail": ["tail_pt1", "tail_pt2"]},
            "graph_cutoffs": {"peak_horizontal_buffer":1, "left_fin_angle":5, "right_fin_angle":5, "tail_angle":5,
                              "movement_bout_width":1, "swim_bout_buffer":1, "swim_bout_right_shift":0, "use_tail_angle":True},
            "auto_find_time_ranges": False,
            "time_ranges": [[0, 0]]
        }

    def test_run_calculations(self):
        df = run_calculations(self.parsed_points, self.config)
        self.assertTrue("LF_Angle" in df.columns)
        self.assertEqual(len(df), 1)

if __name__ == '__main__':
    unittest.main()
