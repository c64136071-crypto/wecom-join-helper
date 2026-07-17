import importlib.util
import unittest

from wecom_rusher.vision import (
    image_signature,
    locate_template,
    locate_templates_multiscale,
    signature_distance,
)


@unittest.skipUnless(importlib.util.find_spec("cv2"), "opencv-python is not installed")
class VisionTests(unittest.TestCase):
    def test_template_larger_than_source_is_not_a_match(self):
        source = [[1, 2], [3, 4]]
        template = [[1, 2, 3]]
        self.assertIsNone(locate_template(source, template, 0.88))

    def test_multiscale_match_finds_resized_template(self):
        import cv2
        import numpy as np

        template = np.zeros((20, 20), dtype=np.uint8)
        template[4:16, 8:12] = 255
        template[8:12, 4:16] = 255
        resized = cv2.resize(template, (30, 30), interpolation=cv2.INTER_NEAREST)
        source = np.zeros((120, 120), dtype=np.uint8)
        source[40:70, 50:80] = resized

        matches = locate_templates_multiscale(
            source, template, threshold=0.95, scales=(1.0, 1.5)
        )

        self.assertTrue(any(abs(match.x - 65) <= 1 and abs(match.y - 55) <= 1 for match in matches))

    def test_signature_distance_detects_changed_header(self):
        import numpy as np

        first = np.zeros((20, 80), dtype=np.uint8)
        second = first.copy()
        second[:, 40:] = 255
        self.assertEqual(signature_distance(image_signature(first), image_signature(first)), 0)
        self.assertGreater(signature_distance(image_signature(first), image_signature(second)), 0)
