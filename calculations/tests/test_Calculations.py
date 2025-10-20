import unittest
import numpy as np
from calculations.utils.Metrics import calc_fin_angle, calc_yaw

class TestCalculations(unittest.TestCase):
    def setUp(self):
        # Create mock head points and fin points (2 frames)
        self.head1 = {"x": np.array([1, 2]), "y": np.array([2, 3])}
        self.head2 = {"x": np.array([2, 3]), "y": np.array([3, 4])}
        # Fin points: base and tip positions in two frames
        fin_base = {"x": np.array([3, 4]), "y": np.array([4, 5])}
        fin_tip = {"x": np.array([4, 5]), "y": np.array([5, 6])}
        self.fin_points = [fin_base, fin_tip]

    def test_calc_fin_angle(self):
        angles = calc_fin_angle(self.head1, self.head2, self.fin_points)
        self.assertEqual(len(angles), 2)
        self.assertTrue(np.all(np.isfinite(angles)))

    def test_calc_yaw(self):
        yaws = calc_yaw(self.head1, self.head2)
        self.assertEqual(len(yaws), 2)
        self.assertTrue(np.all(np.isfinite(yaws)))

if __name__ == '__main__':
    unittest.main()
