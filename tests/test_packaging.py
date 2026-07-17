import unittest
from pathlib import Path

from wecom_rusher.release import release_filenames


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_release_filenames_include_version(self):
        self.assertEqual(
            release_filenames("0.9.0"),
            (
                "JoinHelper-Portable-v0.9.0.zip",
                "JoinHelper-Setup-v0.9.0.exe",
            ),
        )

    def test_spec_uses_lean_runtime_collection(self):
        text = (ROOT / "JoinHelper.spec").read_text(encoding="utf-8")
        self.assertIn('name="JoinHelper"', text)
        self.assertNotIn('collect_all("onnxruntime")', text)
        self.assertNotIn('collect_all("shapely")', text)
        for model in (
            "ch_PP-OCRv4_det_infer.onnx",
            "ch_PP-OCRv4_rec_infer.onnx",
            "ch_ppocr_mobile_v2.0_cls_infer.onnx",
        ):
            self.assertIn(model, text)

    def test_portable_marker_is_present(self):
        self.assertTrue((ROOT / "portable.marker").is_file())

    def test_release_script_builds_versioned_zip_and_checksum(self):
        text = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn("JoinHelper-Portable-v$Version.zip", text)
        self.assertIn("Get-FileHash", text)
        self.assertIn("JoinHelper.spec", text)
        self.assertIn("portable.marker", text)

    def test_frozen_smoke_script_requires_success_result(self):
        text = (ROOT / "scripts" / "frozen_smoke_test.ps1").read_text(encoding="utf-8")
        self.assertIn("SMOKE_TEST_OK", text)
        self.assertIn("--smoke-test", text)


if __name__ == "__main__":
    unittest.main()
