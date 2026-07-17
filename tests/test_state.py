import json
import tempfile
import unittest
from pathlib import Path

from wecom_rusher.state import SubmissionState


class SubmissionStateTests(unittest.TestCase):
    def test_fingerprint_is_seen_after_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = SubmissionState(path)
            self.assertFalse(state.seen("card-1"))
            state.record("card-1", "7月16日下午茶接龙登记")
            state.save()

            reloaded = SubmissionState(path)
            self.assertTrue(reloaded.seen("card-1"))

    def test_missing_or_invalid_state_starts_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("not-json", encoding="utf-8")
            state = SubmissionState(path)
            self.assertEqual(state.submitted, {})

    def test_saved_state_has_expected_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = SubmissionState(path)
            state.record("card-1", "title")
            state.save()
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("card-1", payload["submitted"])
            self.assertEqual(payload["submitted"]["card-1"]["title"], "title")
