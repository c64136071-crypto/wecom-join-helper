import json
import tempfile
import unittest
from pathlib import Path

from wecom_rusher.config import Config


class ConfigTests(unittest.TestCase):
    def write_config(self, **overrides):
        values = {
            "normal_interval_seconds": 5.0,
            "rush_interval_seconds": 0.5,
            "rush_start": "11:00",
            "rush_end": "12:00",
            "match_threshold": 0.88,
            "action_timeout_seconds": 8.0,
            **overrides,
        }
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "config.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        self.addCleanup(directory.cleanup)
        return path

    def test_rejects_non_positive_intervals(self):
        with self.assertRaisesRegex(ValueError, "normal_interval_seconds"):
            Config.from_json(self.write_config(normal_interval_seconds=0))
        with self.assertRaisesRegex(ValueError, "rush_interval_seconds"):
            Config.from_json(self.write_config(rush_interval_seconds=-1))

    def test_rejects_invalid_threshold(self):
        with self.assertRaisesRegex(ValueError, "match_threshold"):
            Config.from_json(self.write_config(match_threshold=1.1))

    def test_rejects_reversed_rush_window(self):
        with self.assertRaisesRegex(ValueError, "rush_start"):
            Config.from_json(self.write_config(rush_start="12:00", rush_end="11:00"))

    def test_parses_time_and_paths(self):
        config = Config.from_json(self.write_config())
        self.assertEqual(config.rush_start.hour, 11)
        self.assertEqual(config.rush_end.hour, 12)
        self.assertEqual(config.run_weekdays, ())
        self.assertTrue(config.stop_after_submission)
        self.assertFalse(config.setup_complete)
        self.assertFalse(config.recognition_test_passed)
        self.assertIsInstance(config.state_path, Path)

    def test_empty_weekday_list_means_any_day(self):
        config = Config.from_json(self.write_config(run_weekdays=[]))
        self.assertEqual(config.run_weekdays, ())

    def test_write_json_round_trips_utf8_without_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config.json"
            Config(title_keyword="下午茶", dry_run=True).write_json(path)
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            loaded = Config.from_json(path)
            self.assertEqual(loaded.title_keyword, "下午茶")
            self.assertTrue(loaded.dry_run)

    def test_load_or_create_writes_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = Config.load_or_create(path)
            self.assertTrue(path.exists())
            self.assertTrue(config.dry_run)
            self.assertTrue(config.stop_after_submission)
