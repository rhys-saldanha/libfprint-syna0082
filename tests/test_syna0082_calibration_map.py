import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("calibration_map", ROOT / "tools" / "syna0082_calibration_map.py")
mapping = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mapping)


class CalibrationMapTests(unittest.TestCase):
    def test_finds_relocated_unique_run(self):
        calibration = bytes(range(64)) + b"repeated" * 4
        matrix = b"HEADER" + calibration[10:50] + b"TAIL"
        result = mapping.summarize(calibration, matrix, 8)
        self.assertGreaterEqual(result["directly_mapped_bytes"], 40)
        self.assertEqual(result["runs"][0]["matrix_offset"], 6)
        self.assertEqual(result["runs"][0]["calibration_offset"], 10)

    def test_maps_repeated_content_without_claiming_uniqueness(self):
        runs = mapping.direct_runs(b"abcdefghabcdefgh", b"abcdefgh", 8)
        self.assertEqual(runs[0]["length"], 8)


if __name__ == "__main__":
    unittest.main()
