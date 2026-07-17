import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_public_tree_excludes_runtime_data(self):
        forbidden = {
            "config.json",
            "state.json",
            "wecom-rusher.log",
            "ocr-test.log",
            "outputs",
            "work",
        }
        present = {path.name for path in ROOT.iterdir()}
        self.assertEqual(forbidden.intersection(present), set())

    def test_public_templates_exclude_private_captures(self):
        forbidden = {
            "calibration-screen.png",
            "current-document.png",
            "detail-preview.png",
            "prefilled_name.png",
            "success.png",
            "title_keyword.png",
        }
        present = {path.name for path in (ROOT / "templates").iterdir()}
        self.assertEqual(forbidden.intersection(present), set())

    def test_example_config_is_safe_by_default(self):
        payload = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["stop_after_submission"])
        self.assertEqual(payload["run_weekdays"], [])

    def test_public_text_does_not_contain_machine_specific_paths(self):
        excluded_parts = {".git", "__pycache__"}
        candidates = []
        for pattern in ("*.py", "*.md", "*.json", "*.ps1", "*.spec", "*.yml", "*.yaml"):
            candidates.extend(ROOT.rglob(pattern))
        private_home = str(Path.home()).lower()
        wechat_identifier = "wx" + "id_"
        offending = []
        for path in candidates:
            if excluded_parts.intersection(path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if private_home in text or wechat_identifier in text:
                offending.append(str(path.relative_to(ROOT)))
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
