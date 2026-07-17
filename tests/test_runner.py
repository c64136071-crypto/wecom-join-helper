import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from wecom_rusher.config import Config
from wecom_rusher.runner import Rusher
from wecom_rusher.state import SubmissionState
from wecom_rusher.ui import CardCandidate, UIError


class FakeUI:
    def __init__(self, candidate):
        self.candidate = candidate
        self.opened = 0
        self.submitted = 0

    def find_target_card(self, keyword):
        return self.candidate

    def open_card(self, candidate):
        self.opened += 1

    def submit_current_card(self):
        self.submitted += 1

    def card_is_submitted(self):
        return True


class FakeNotifier:
    def __init__(self):
        self.events = []

    def notify(self, status, message):
        self.events.append((status, message))


class FailingSubmitUI(FakeUI):
    def submit_current_card(self):
        self.submitted += 1
        raise UIError("submit button not found")


class FailingOpenUI(FakeUI):
    def open_card(self, candidate):
        self.opened += 1
        raise UIError("card window did not open")


class FailingVerifyUI(FakeUI):
    def card_is_submitted(self):
        raise UIError("document disappeared after insertion")


class RunnerTests(unittest.TestCase):
    def make_config(self, dry_run=False, **overrides):
        return Config(dry_run=dry_run, **overrides)

    def test_submits_and_records_new_card(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "7月16日下午茶接龙登记", (10, 20)))
            notifier = FakeNotifier()
            result = Rusher(self.make_config(), ui, state, notifier).scan_once()
            self.assertEqual(result, "submitted")
            self.assertEqual(ui.opened, 1)
            self.assertEqual(ui.submitted, 1)
            self.assertTrue(state.seen("card-1"))
            self.assertEqual(notifier.events[0][0], "submitted")

    def test_skips_duplicate_card(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            state.record("card-1", "old")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            result = Rusher(self.make_config(), ui, state, FakeNotifier()).scan_once()
            self.assertEqual(result, "already_submitted")
            self.assertEqual(ui.opened, 0)

    def test_dry_run_does_not_record_card(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            notifier = FakeNotifier()
            result = Rusher(self.make_config(dry_run=True), ui, state, notifier).scan_once()
            self.assertEqual(result, "dry_run")
            self.assertFalse(state.seen("card-1"))
            self.assertEqual(notifier.events[0][0], "dry_run")
            self.assertEqual(ui.opened, 0)
            self.assertEqual(ui.submitted, 0)

    def test_continuous_dry_run_exits_after_first_recognition(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(self.make_config(dry_run=True), ui, state, FakeNotifier())
            statuses = []
            with patch("wecom_rusher.runner.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 16, 11, 30)
                rusher.run_forever(
                    stop_event=threading.Event(), status_callback=statuses.append
                )
            self.assertEqual(ui.opened, 0)
            self.assertEqual(ui.submitted, 0)
            self.assertEqual(statuses, ["rush_waiting", "dry_run"])

    def test_continuous_runner_exits_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(
                self.make_config(run_weekdays=(3,)), ui, state, FakeNotifier()
            )
            with patch("wecom_rusher.runner.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 16, 11, 30)
                rusher.run_forever()
            self.assertEqual(ui.submitted, 1)

    def test_continuous_runner_exits_on_non_configured_weekday(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(
                self.make_config(run_weekdays=(3,)), ui, state, FakeNotifier()
            )
            with patch("wecom_rusher.runner.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 15, 11, 30)
                rusher.run_forever()
            self.assertEqual(ui.submitted, 0)

    def test_empty_weekday_config_runs_on_any_day(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(self.make_config(run_weekdays=()), ui, state, FakeNotifier())
            with patch("wecom_rusher.runner.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 15, 11, 30)
                rusher.run_forever()
            self.assertEqual(ui.submitted, 1)

    def test_continuous_runner_does_not_retry_after_ui_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FailingSubmitUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(self.make_config(), ui, state, FakeNotifier())
            with (
                patch("wecom_rusher.runner.datetime") as clock,
                patch(
                    "wecom_rusher.runner.time.sleep",
                    side_effect=AssertionError("runner attempted another polling cycle"),
                ),
            ):
                clock.now.return_value = datetime(2026, 7, 16, 11, 30)
                statuses = []
                rusher.run_forever(status_callback=statuses.append)
            self.assertEqual(ui.submitted, 1)
            self.assertEqual(statuses, ["rush_waiting", "unsafe_state_after_attempt"])

    def test_open_failure_is_terminal_before_insertion(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FailingOpenUI(CardCandidate("card-1", "title", (10, 20)))
            result = Rusher(self.make_config(), ui, state, FakeNotifier()).scan_once()
            self.assertEqual(result, "unsafe_state")
            self.assertEqual(ui.opened, 1)
            self.assertEqual(ui.submitted, 0)

    def test_verification_failure_after_insertion_is_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FailingVerifyUI(CardCandidate("card-1", "title", (10, 20)))
            result = Rusher(self.make_config(), ui, state, FakeNotifier()).scan_once()
            self.assertEqual(result, "unsafe_state_after_attempt")
            self.assertEqual(ui.submitted, 1)

    def test_continuous_runner_emits_rush_and_submitted_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(self.make_config(), ui, state, FakeNotifier())
            statuses = []
            with patch("wecom_rusher.runner.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 16, 11, 30)
                rusher.run_forever(
                    stop_event=threading.Event(), status_callback=statuses.append
                )
            self.assertEqual(statuses, ["rush_waiting", "submitted"])

    def test_continuous_runner_honors_pre_set_stop_event(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SubmissionState(Path(directory) / "state.json")
            ui = FakeUI(CardCandidate("card-1", "title", (10, 20)))
            rusher = Rusher(self.make_config(), ui, state, FakeNotifier())
            stop_event = threading.Event()
            stop_event.set()
            statuses = []
            with patch("wecom_rusher.runner.datetime") as clock:
                clock.now.return_value = datetime(2026, 7, 16, 11, 30)
                rusher.run_forever(stop_event=stop_event, status_callback=statuses.append)
            self.assertEqual(ui.submitted, 0)
            self.assertEqual(statuses, ["stopped"])
