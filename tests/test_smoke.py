import json
import tempfile
import unittest
from pathlib import Path

from wecom_rusher.smoke import run_smoke_test


ROOT = Path(__file__).resolve().parents[1]


class FakeOCR:
    def read(self, image):
        return "7月18日下午茶接龙登记"


class SmokeTests(unittest.TestCase):
    def test_smoke_test_loads_templates_vision_and_ocr_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "smoke-result.json"
            result = run_smoke_test(ROOT, result_path=result_path, ocr_reader=FakeOCR())
            self.assertEqual(result["status"], "SMOKE_TEST_OK")
            self.assertEqual(result["templates_loaded"], 4)
            self.assertTrue(result["vision_match"])
            self.assertTrue(result["ocr_keyword_match"])
            self.assertEqual(
                json.loads(result_path.read_text(encoding="utf-8"))["status"],
                "SMOKE_TEST_OK",
            )


if __name__ == "__main__":
    unittest.main()
