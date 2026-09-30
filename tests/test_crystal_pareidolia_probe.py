import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "crystal_pareidolia_probe.py"
spec = importlib.util.spec_from_file_location("crystal_pareidolia_probe", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


class CrystalPareidoliaProbeTests(unittest.TestCase):
    def test_gamma_transform_preserves_shape_and_dtype(self):
        image = np.full((24, 32, 3), 128, dtype=np.uint8)
        out = probe.gamma_transform(image, 0.8)
        self.assertEqual(out.shape, image.shape)
        self.assertEqual(out.dtype, np.uint8)
        self.assertFalse(np.array_equal(out, image))

    def test_directional_light_changes_opposite_sides(self):
        image = np.full((20, 40, 3), 120, dtype=np.uint8)
        out = probe.directional_light(image, "left", strength=0.4)
        self.assertGreater(float(out[:, :5].mean()), float(out[:, -5:].mean()))

    def test_cluster_marks_repeated_detector_response_persistent(self):
        detections = [
            probe.Detection("baseline", 10, 10, 20, 20, 100, 100),
            probe.Detection("gamma_0.85", 11, 10, 20, 20, 100, 100),
            probe.Detection("light_left", 10, 11, 20, 20, 100, 100),
        ]
        clusters = probe.cluster_detections(detections, variant_count=4)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["variant_hits"], 3)
        self.assertEqual(
            clusters[0]["classification"],
            "PERSISTENT_DETECTOR_CANDIDATE",
        )

    def test_cluster_keeps_distant_responses_separate(self):
        detections = [
            probe.Detection("baseline", 5, 5, 20, 20, 100, 100),
            probe.Detection("gamma_0.85", 70, 70, 20, 20, 100, 100),
        ]
        clusters = probe.cluster_detections(detections, variant_count=2)
        self.assertEqual(len(clusters), 2)


if __name__ == "__main__":
    unittest.main()
