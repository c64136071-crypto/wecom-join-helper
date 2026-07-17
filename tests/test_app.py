import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wecom_rusher.app import (
    application_root,
    config_for_worker,
    load_application_config,
    persist_application_config,
    resolve_application_paths,
    save_title_keyword,
    status_text,
)


class AppTests(unittest.TestCase):
    def test_application_root_uses_executable_when_frozen(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", r"D:\Apps\WeComRusher\WeComRusher.exe"),
        ):
            self.assertEqual(application_root(), Path(r"D:\Apps\WeComRusher"))

    def test_application_root_uses_source_root_during_development(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(
                application_root(),
                Path(__file__).resolve().parents[1],
            )

    def test_status_text_is_clear_for_user_visible_states(self):
        self.assertEqual(status_text("waiting"), "等待接龙")
        self.assertEqual(status_text("rush_waiting"), "高频监控中（11:00-12:00）")
        self.assertEqual(status_text("submitted"), "接龙成功，企微可能需要重新登录")
        self.assertEqual(status_text("unsafe_state"), "界面状态异常，已停止且不会重试")
        self.assertEqual(status_text("timeout"), "未确认成功，已停止且不会重试")

    def test_save_title_keyword_preserves_other_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"title_keyword": "下午茶", "dry_run": False}),
                encoding="utf-8",
            )
            save_title_keyword(path, "团建")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["title_keyword"], "团建")
            self.assertFalse(payload["dry_run"])

    def test_resolve_application_paths_detects_portable_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "portable.marker").touch()
            paths = resolve_application_paths(root)
            self.assertTrue(paths.portable)
            self.assertEqual(paths.data_dir, root / "data")

    def test_load_application_config_injects_runtime_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            root.mkdir()
            (root / "portable.marker").touch()
            paths = resolve_application_paths(root)
            config = load_application_config(paths)
            self.assertEqual(config.templates_dir, root / "templates")
            self.assertEqual(config.state_path, root / "data" / "state.json")
            self.assertEqual(config.log_path, root / "data" / "join-helper.log")
            self.assertTrue(config.dry_run)

    def test_test_worker_is_always_dry_run(self):
        from wecom_rusher.config import Config

        live = Config(dry_run=False, setup_complete=True, recognition_test_passed=True)
        self.assertTrue(config_for_worker(live, test_mode=True).dry_run)
        self.assertFalse(config_for_worker(live, test_mode=False).dry_run)

    def test_persist_application_config_does_not_store_runtime_paths(self):
        from wecom_rusher.config import Config

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = Config(
                title_keyword="下午茶",
                templates_dir=Path(r"D:\Private\templates"),
                state_path=Path(r"C:\Users\Private\state.json"),
                log_path=Path(r"C:\Users\Private\join-helper.log"),
            )
            persist_application_config(path, config)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("templates_dir", payload)
            self.assertNotIn("state_path", payload)
            self.assertNotIn("log_path", payload)
