from pathlib import Path

import numpy as np
import numpy.testing as npt

from calculations.utils.Parser import parse_dlc_csv


def test_parse_dlc_csv_shapes_and_values(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "scorer,DLC,DLC,DLC,DLC,DLC,DLC,DLC,DLC,DLC\n"
        "bodyparts,Head,Head,Head,LE,LE,LE,LF1,LF1,LF1\n"
        "coords,x,y,likelihood,x,y,likelihood,x,y,likelihood\n"
        "0,10,20,0.9,30,40,0.8,50,60,0.7\n"
        "1,11,21,0.91,31,41,0.81,51,61,0.71\n"
    )

    config = {
        "points": {
            "spine": ["Head", "LE", "LF1"],
            "left_fin": ["LF1"],
            "right_fin": ["LE"],
            "head": {"pt1": "Head", "pt2": "LE"},
            "tail": ["LF1", "LE"],
        }
    }

    parsed = parse_dlc_csv(str(csv_path), config)

    assert set(parsed.keys()) == {
        "spine",
        "right_fin",
        "left_fin",
        "clp1",
        "clp2",
        "tp",
        "head",
        "tailPoints",
        "tail",
    }

    assert len(parsed["spine"]) == 3
    npt.assert_allclose(parsed["spine"][0]["x"], np.array([10.0, 11.0]))
    npt.assert_allclose(parsed["spine"][1]["y"], np.array([40.0, 41.0]))
    npt.assert_allclose(parsed["left_fin"][0]["x"], np.array([50.0, 51.0]))
    npt.assert_allclose(parsed["right_fin"][0]["x"], np.array([30.0, 31.0]))
    assert parsed["tailPoints"] == ["LF1", "LE"]
    npt.assert_allclose(parsed["tail"][0]["conf"], np.array([0.7, 0.71]))
