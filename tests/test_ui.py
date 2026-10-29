import threading
import unittest
from unittest.mock import Mock, call, patch

from PIL import Image, ImageDraw

from wecom_rusher.config import Config
from wecom_rusher.ui import (
    ActionStopped,
    MonitoringPaused,
    TemplateStore,
    UIError,
    WeComUI,
    pair_card_matches,
    window_style_can_obscure,
)
from wecom_rusher.vision import TemplateMatch


class TemplateStoreTests(unittest.TestCase):
    def test_required_names_are_stable(self):
        self.assertEqual(
            TemplateStore.required_names(),
            ("yellow_icon", "participate", "join", "submit"),
        )

    def test_matching_windows_excludes_non_wecom_processes_with_matching_titles(self):
        ui = WeComUI(Config())
        wecom_window = Mock()
        edge_window = Mock()
        mail_window = Mock()
        desktop = Mock()
        desktop.windows.return_value = [wecom_window, edge_window, mail_window]
        ui._window_executable_name = Mock(
            side_effect=["WXWork.exe", "msedge.exe", "WeMail.exe"]
        )

        with patch("pywinauto.Desktop", return_value=desktop):
            matches = ui._matching_windows()

        self.assertEqual(matches, [wecom_window])

    def test_document_window_accepts_wemail_document_host(self):
        ui = WeComUI(Config())
        mail_document = Mock()
        mail_document.window_text.return_value = "企业微信-文档"
        edge_document = Mock()
        edge_document.window_text.return_value = "企业微信-文档"
        desktop = Mock()
        desktop.windows.return_value = [mail_document, edge_document]
        ui._window_executable_name = Mock(
            side_effect=["WeMail.exe", "msedge.exe"]
        )

        with patch("pywinauto.Desktop", return_value=desktop):
            document = ui._document_window()

        self.assertIs(document, mail_document)

    def test_document_window_rejects_non_exact_wemail_title(self):
        ui = WeComUI(Config())
        mail_window = Mock()
        mail_window.window_text.return_value = "Inbox - 企业微信-文档"
        desktop = Mock()
        desktop.windows.return_value = [mail_window]
        ui._window_executable_name = Mock(return_value="WeMail.exe")

        with patch("pywinauto.Desktop", return_value=desktop):
            with self.assertRaises(UIError):
                ui._document_window()

    def test_prepare_monitoring_focuses_main_window_once(self):
        ui = WeComUI(Config())
        window = Mock()
        window.is_minimized.return_value = False
        ui._main_window = Mock(return_value=window)
        ui.ocr.warmup = Mock()

        ui.prepare_monitoring()

        window.set_focus.assert_called_once_with()

    def test_find_target_card_does_not_refocus_visible_wecom_during_scan(self):
        ui = WeComUI(Config())
        window = Mock()
        window.is_minimized.return_value = False
        screenshot = Image.new("RGB", (1000, 600), "white")
        ui._main_window = Mock(return_value=window)
        ui._assistant_is_foreground = Mock(return_value=False)
        ui._is_window_obscured = Mock(return_value=False)
        ui._screenshot = Mock(return_value=(screenshot, (0, 0, 1000, 600)))
        ui._matches = Mock(return_value=[])
        ui._verify_group_header = Mock()

        self.assertIsNone(ui.find_target_card("下午茶|午茶"))

        ui._screenshot.assert_called_once_with(window, focus_window=False)

    def test_find_target_card_refocuses_wecom_when_external_window_covers_it(self):
        ui = WeComUI(Config())
        window = Mock()
        window.is_minimized.return_value = False
        screenshot = Image.new("RGB", (1000, 600), "white")
        ui._main_window = Mock(return_value=window)
        ui._assistant_is_foreground = Mock(return_value=False)
        ui._is_window_obscured = Mock(return_value=True)
        ui.prepare_monitoring = Mock()
        ui._screenshot = Mock(return_value=(screenshot, (0, 0, 1000, 600)))
        ui._matches = Mock(return_value=[])
        ui._verify_group_header = Mock()

        self.assertIsNone(ui.find_target_card("下午茶|午茶"))

        ui.prepare_monitoring.assert_called_once_with()
        ui._is_window_obscured.assert_called_once_with(window)
        ui._screenshot.assert_called_once_with(window, focus_window=False)

    def test_find_target_card_pauses_when_helper_is_foreground(self):
        ui = WeComUI(Config())
        ui._main_window = Mock()
        ui._assistant_is_foreground = Mock(return_value=True)
        ui.prepare_monitoring = Mock()
        ui._screenshot = Mock()

        with self.assertRaises(MonitoringPaused):
            ui.find_target_card("下午茶|午茶")

        ui.prepare_monitoring.assert_not_called()
        ui._screenshot.assert_not_called()

    def test_find_target_card_accepts_small_card_button_match(self):
        ui = WeComUI(Config())
        window = Mock()
        window.is_minimized.return_value = False
        screenshot = Image.new("RGB", (262, 114), "white")
        icon = TemplateMatch(231, 41, 0.946, 0.667, 29, 30)
        button = TemplateMatch(67, 87, 0.779, 0.667, 81, 25)
        ui._main_window = Mock(return_value=window)
        ui._assistant_is_foreground = Mock(return_value=False)
        ui._is_window_obscured = Mock(return_value=False)
        ui._screenshot = Mock(return_value=(screenshot, (0, 0, 262, 114)))
        ui._matches = Mock(side_effect=[[icon], [button]])
        ui._verify_group_header = Mock()
        ui.ocr.read = Mock(return_value="9月24日下午茶接龙登记")

        candidate = ui.find_target_card("午茶")

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.participate_point, (67, 87))
        self.assertEqual(ui._matches.call_args_list[1].kwargs["threshold"], 0.70)

    def test_mouse_transparent_overlay_cannot_obscure_wecom(self):
        self.assertFalse(window_style_can_obscure(0x20))
        self.assertTrue(window_style_can_obscure(0))

    def test_submit_clicks_join_then_verified_confirm_once(self):
        ui = WeComUI(Config(dry_run=False))
        bounds = (0, 0, 3840, 2088)
        ui._wait_for_template = Mock(
            side_effect=[
                ((1610, 2045), bounds, (3840, 2088)),
                ((1675, 1951), bounds, (3840, 2088)),
            ]
        )
        ui._click = Mock()

        ui.submit_current_card()

        self.assertEqual(
            ui._wait_for_template.call_args_list,
            [call("join", None), call("submit", None)],
        )
        self.assertEqual(
            ui._click.call_args_list,
            [call((1610, 2045), bounds), call((1675, 1951), bounds)],
        )
        self.assertTrue(ui._edit_confirmed)
        self.assertTrue(ui._commit_sent)

    def test_card_is_submitted_ignores_unfilled_submit_false_positive(self):
        ui = WeComUI(Config(dry_run=False))
        ui._edit_confirmed = ui._commit_sent = True
        ui._guard_document = Mock()
        ui.ocr.read = Mock(return_value="接龙")
        screenshot = Image.new("RGB", (400, 220), "#f1f1f1")
        join_match = TemplateMatch(80, 190, 1.0, 1.0, 88, 39)
        false_submit_match = TemplateMatch(300, 190, 0.895, 1.5, 132, 58)
        ui._document_window = Mock()
        ui._screenshot = Mock(return_value=(screenshot, (0, 0, 400, 220)))
        ui._matches = Mock(
            side_effect=lambda _image, name: {
                "join": [join_match],
                "submit": [false_submit_match],
            }[name]
        )

        self.assertTrue(ui.card_is_submitted())

    def test_card_is_submitted_rejects_visible_filled_submit_button(self):
        ui = WeComUI(Config(dry_run=False))
        ui._edit_confirmed = ui._commit_sent = True
        ui._guard_document = Mock()
        ui.ocr.read = Mock(side_effect=["接龙", "确定"])
        screenshot = Image.new("RGB", (400, 220), "#f1f1f1")
        submit_match = TemplateMatch(300, 190, 1.0, 1.0, 88, 39)
        draw = ImageDraw.Draw(screenshot)
        draw.rectangle((256, 171, 343, 209), fill="#2f7fe5")
        join_match = TemplateMatch(80, 190, 1.0, 1.0, 88, 39)
        ui._document_window = Mock()
        ui._screenshot = Mock(return_value=(screenshot, (0, 0, 400, 220)))
        ui._matches = Mock(
            side_effect=lambda _image, name: {
                "join": [join_match],
                "submit": [submit_match],
            }[name]
        )

        self.assertFalse(ui.card_is_submitted())

    def test_verification_requires_observed_edit_and_commit(self):
        ui = WeComUI(Config())
        ui._document_window = Mock()
        self.assertFalse(ui.card_is_submitted())
        ui._document_window.assert_not_called()

    def test_document_confirm_rejects_toolbar_and_other_button_text(self):
        ui = WeComUI(Config())
        screenshot = Image.new("RGB", (1280, 757), "#2f7fe5")
        toolbar = TemplateMatch(1241, 70, 0.894, 0.667, 70, 47)
        unrelated = TemplateMatch(600, 500, 0.95, 1.0, 105, 70)
        ui._matches = Mock(return_value=[toolbar, unrelated])
        ui.ocr.read = Mock(return_value="邀请填写")
        self.assertEqual(ui._document_buttons(screenshot, "submit"), [])
        ui.ocr.read.assert_called_once()

    def make_document_wait_ui(self):
        ui = WeComUI(Config())
        window = Mock()
        window.handle = 100
        window.is_minimized.return_value = False
        ui._document_window = Mock(return_value=window)
        ui._assistant_is_foreground = Mock(return_value=False)
        ui._is_window_obscured = Mock(return_value=False)
        ui._screenshot = Mock(return_value=(Image.new("RGB", (1280, 757)), (50, 40, 1280, 757)))
        ui._scroll_document = Mock()
        return ui

    def test_wait_scrolls_long_list_then_uses_current_button_position(self):
        ui = self.make_document_wait_ui()
        first = TemplateMatch(426, 600, 0.95, 0.667, 113, 38)
        moved = TemplateMatch(426, 720, 0.95, 0.667, 113, 38)
        ui._document_buttons = Mock(side_effect=[[], [first], [moved], [moved]])
        clock = [0.0]
        def advance(_):
            clock[0] += 0.7
        with patch("wecom_rusher.ui.time.monotonic", side_effect=lambda: clock[0]), patch(
            "wecom_rusher.ui.time.sleep", side_effect=advance
        ):
            point, _, _ = ui._wait_for_template("join")
        self.assertEqual(point, (426, 720))

    def test_wait_scrolls_when_button_is_below_viewport(self):
        ui = self.make_document_wait_ui()
        match = TemplateMatch(426, 720, 0.95, 0.667, 113, 38)
        ui._document_buttons = Mock(side_effect=[[], [], [match], [match]])
        clock = [0.0]
        def advance(_):
            clock[0] += 0.7
        with patch("wecom_rusher.ui.time.monotonic", side_effect=lambda: clock[0]), patch(
            "wecom_rusher.ui.time.sleep", side_effect=advance
        ):
            ui._wait_for_template("join")
        ui._scroll_document.assert_called_once()

    def test_slow_document_load_uses_separate_deadline(self):
        ui = self.make_document_wait_ui()
        match = TemplateMatch(426, 720, 0.95, 0.667, 113, 38)
        ui._document_window.side_effect = [UIError("loading"), Mock(), Mock()]
        ui._guard_document = Mock()
        ui._window_handle = Mock(return_value=100)
        ui._document_buttons = Mock(return_value=[match])
        clock = [0.0]
        def advance(_):
            clock[0] += 9.0
        with patch("wecom_rusher.ui.time.monotonic", side_effect=lambda: clock[0]), patch(
            "wecom_rusher.ui.time.sleep", side_effect=advance
        ):
            self.assertEqual(ui._wait_for_template("join")[0], (426, 720))

    def test_missing_button_has_bounded_scroll_and_timeout(self):
        ui = self.make_document_wait_ui()
        ui._document_buttons = Mock(return_value=[])
        clock = [0.0]
        def advance(_):
            clock[0] += 0.7
        with patch("wecom_rusher.ui.time.monotonic", side_effect=lambda: clock[0]), patch(
            "wecom_rusher.ui.time.sleep", side_effect=advance
        ), self.assertRaisesRegex(UIError, "timed out"):
            ui._wait_for_template("join")
        self.assertLessEqual(ui._scroll_document.call_count, 24)

    def test_stop_during_button_search_prevents_insertion(self):
        ui = self.make_document_wait_ui()
        stop = threading.Event()
        def stop_scan(*_):
            stop.set()
            return []
        ui._document_buttons = Mock(side_effect=stop_scan)
        ui._click = Mock()
        with self.assertRaises(ActionStopped):
            ui.submit_current_card(stop)
        ui._click.assert_not_called()

    def test_stop_after_join_prevents_confirmation_click(self):
        ui = WeComUI(Config())
        stop = threading.Event()
        bounds = (0, 0, 1280, 757)
        ui._wait_for_template = Mock(return_value=((400, 600), bounds, (1280, 757)))
        ui._click = Mock(side_effect=lambda *_: stop.set())
        with self.assertRaises(ActionStopped):
            ui.submit_current_card(stop)
        ui._click.assert_called_once()
        self.assertFalse(ui._commit_sent)

    def test_scroll_targets_document_body_without_clicking(self):
        ui = self.make_document_wait_ui()
        ui._scroll_document = WeComUI._scroll_document.__get__(ui)
        with patch("pyautogui.moveTo") as move, patch("pyautogui.scroll") as scroll, patch("pyautogui.click") as click:
            ui._scroll_document(ui._document_window(), (50, 40, 1280, 757), None)
        move.assert_called_once_with(690, 607)
        scroll.assert_called_once_with(-10)
        click.assert_not_called()

    def test_helper_foreground_prevents_document_scroll(self):
        ui = self.make_document_wait_ui()
        ui._assistant_is_foreground.return_value = True
        with patch("pyautogui.scroll") as scroll, self.assertRaises(UIError):
            WeComUI._scroll_document(ui, ui._document_window(), (0, 0, 1280, 757), None)
        scroll.assert_not_called()

    def test_pair_card_matches_returns_lowest_valid_card_first(self):
        icons = [
            TemplateMatch(820, 300, 0.99, 1.0, 40, 40),
            TemplateMatch(820, 700, 0.98, 1.0, 40, 40),
        ]
        buttons = [
            TemplateMatch(580, 370, 0.99, 1.0, 120, 38),
            TemplateMatch(580, 770, 0.98, 1.0, 120, 38),
            TemplateMatch(100, 100, 0.99, 1.0, 120, 38),
        ]

        pairs = pair_card_matches(icons, buttons)

        self.assertEqual([(pair.icon.y, pair.button.y) for pair in pairs], [(700, 770), (300, 370)])

    def test_group_header_change_stops_monitoring(self):
        ui = WeComUI(Config())
        first = Image.new("RGB", (1000, 600), "white")
        second = first.copy()
        first_draw = ImageDraw.Draw(first)
        second_draw = ImageDraw.Draw(second)
        first_draw.rectangle((300, 0, 500, 70), fill="black")
        second_draw.rectangle((550, 0, 700, 70), fill="black")

        ui._verify_group_header(first)
        with self.assertRaises(UIError):
            ui._verify_group_header(second)
