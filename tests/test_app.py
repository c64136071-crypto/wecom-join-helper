import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from wecom_rusher.app import (
    WeComRusherApp,
    application_root,
    config_for_worker,
    load_application_config,
    persist_application_config,
    prepare_desktop_automation,
    resolve_application_paths,
    save_title_keyword,
    status_text,
)


class AppTests(unittest.TestCase):
    @patch("importlib.import_module")
    def test_desktop_automation_is_preloaded_before_window_creation(self, import_module):
        prepare_desktop_automation()
        import_module.assert_called_once_with("pyautogui")

    @patch.object(WeComRusherApp, "_build_window")
    @patch("wecom_rusher.app.StringVar")
    def test_opening_live_app_stays_idle_until_start_is_clicked(
        self, _string_var, _build_window
    ):
        from wecom_rusher.config import Config
        from wecom_rusher.paths import AppPaths

        root = Mock()
        paths = AppPaths.resolve(Path.cwd(), portable=True)
        app = WeComRusherApp(
            root,
            Config(dry_run=False, setup_complete=True, recognition_test_passed=True),
            Mock(),
            paths,
        )

        scheduled_callbacks = [call.args[1] for call in root.after.call_args_list]
        self.assertNotIn(app._start_live, scheduled_callbacks)

    def test_submitted_status_keeps_window_open_for_another_manual_run(self):
        app = WeComRusherApp.__new__(WeComRusherApp)
        app.status_var = Mock()
        app.time_var = Mock()
        app.detail_var = Mock()
        app.stop_button = Mock()
        app.root = Mock()
        app.close_scheduled = False

        app._apply_status("submitted")

        self.assertFalse(app.close_scheduled)
        app.root.after.assert_not_called()
        app.detail_var.set.assert_called_once_with(
            "本轮已停止；新接龙出现后可再次开始"
        )

    def test_duplicate_status_says_monitoring_continues(self):
        app = WeComRusherApp.__new__(WeComRusherApp)
        app.status_var = Mock()
        app.time_var = Mock()
        app.detail_var = Mock()
        app.stop_button = Mock()
        app.root = Mock()
        app.close_scheduled = False

        app._apply_status("already_submitted")

        app.detail_var.set.assert_called_once_with("已跳过这张接龙，继续等待新接龙")

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
        self.assertEqual(status_text("paused"), "已暂停扫描")
        self.assertEqual(status_text("rush_waiting"), "高频监控中（11:00-12:00）")
        self.assertEqual(status_text("submitted"), "接龙成功，企微可能需要重新登录")
        self.assertEqual(status_text("unsafe_state"), "界面状态异常，已停止且不会重试")
        self.assertEqual(status_text("timeout"), "未确认成功，已停止且不会重试")

    def test_paused_status_explains_how_to_resume_scanning(self):
        app = WeComRusherApp.__new__(WeComRusherApp)
        app.status_var = Mock()
        app.time_var = Mock()
        app.detail_var = Mock()
        app.stop_button = Mock()
        app.root = Mock()
        app.close_scheduled = False

        app._apply_status("paused")

        app.detail_var.set.assert_called_once_with(
            "助手窗口在前台，当前暂停扫描；切回企微后会继续"
        )

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
            self.assertFalse(config.dry_run)
            self.assertEqual(config.title_keyword, "下午茶|午茶")

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
