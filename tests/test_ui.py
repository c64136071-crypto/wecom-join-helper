import unittest
from unittest.mock import Mock, call

from PIL import Image, ImageDraw

from wecom_rusher.config import Config
from wecom_rusher.ui import (
    TemplateStore,
    UIError,
    WeComUI,
    pair_card_matches,
    safe_commit_point,
)
from wecom_rusher.vision import TemplateMatch


class TemplateStoreTests(unittest.TestCase):
    def test_required_names_are_stable(self):
        self.assertEqual(
            TemplateStore.required_names(),
            ("yellow_icon", "participate", "join", "submit"),
        )

    def test_safe_commit_point_is_outside_the_document_list(self):
        self.assertEqual(safe_commit_point((0, 0, 3840, 2088)), (3720, 1044))

    def test_submit_clicks_document_join_then_commits_edit_state(self):
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
            [call("join"), call("submit")],
        )
        self.assertEqual(
            ui._click.call_args_list,
            [call((1610, 2045), bounds), call((3720, 1044), bounds)],
        )

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
