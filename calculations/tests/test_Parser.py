import unittest
import numpy as np
import os

from calculations.utils.Parser import parse_dlc_csv

class TestDlcParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv_path = "test_dlc.csv"
        # Simulate your DLC CSV structure: scorer row, bodypart row, coords row, data rows
        csv_content = (
            "scorer,DLC_Resnet,DLC_Resnet,DLC_Resnet,DLC_Resnet,DLC_Resnet,DLC_Resnet,DLC_Resnet,DLC_Resnet,DLC_Resnet\n"
            "bodyparts,Head,Head,Head,LE,LE,LE,LF1,LF1,LF1\n"
            "coords,x,y,likelihood,x,y,likelihood,x,y,likelihood\n"
            "0,403.84326,520.2443,0.8864096,393.53666,528.21704,0.84318787,391.16507,549.9573,0.70455974\n"
            "1,403.751,520.2909,0.88278824,393.9016,528.3418,0.84049153,391.08728,549.9916,0.69364315\n"
        )
        with open(cls.csv_path, "w") as f:
            f.write(csv_content)

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.csv_path)

    def test_parse_dlc_csv(self):
        config = {
            "points": {
                "spine": ["Head", "LE", "LF1"],
                "left_fin": ["LF1"],          # Use only one for simplicity
                "right_fin": [],              # No right fin in this sample
                "head": {"pt1": "Head", "pt2": "LE"},
                "tail": ["LF1"]
            }
        }
        parsed = parse_dlc_csv(self.csv_path, config)
        # Check spine extraction
        self.assertEqual(len(parsed["spine"]), 3)  # Head, LE, LF1
        self.assertEqual(len(parsed["spine"][0]), 2)  # Two frames
        self.assertEqual(parsed["spine"][0][0]["x"], 403.84326)
        self.assertEqual(parsed["spine"][1][1]["y"], 528.3418)
        # Check left fin (should match LF1)
        self.assertIn("left_fin", parsed)
        self.assertEqual(parsed["left_fin"][0][1]["x"], 391.08728)
        # Check tail (LF1 for this example)
        self.assertEqual(parsed["tail"][0][0]["conf"], 0.70455974)

if __name__ == '__main__':
    unittest.main()
