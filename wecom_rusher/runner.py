from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from enum import Enum, auto
from typing import Callable, Protocol

from .config import Config
from .notify import Notifier
from .schedule import PollSchedule
from .state import SubmissionState
from .ui import CardCandidate, UIError, WeComUI


class UIAdapter(Protocol):
    def find_target_card(self, keyword: str) -> CardCandidate | None: ...

    def open_card(self, candidate: CardCandidate) -> None: ...

    def submit_current_card(self) -> None: ...

    def card_is_submitted(self) -> bool: ...


class NotificationAdapter(Protocol):
    def notify(self, status: str, message: str) -> None: ...


class AttemptState(Enum):
    NOT_STARTED = auto()
    CARD_OPENED = auto()
    INSERTION_SENT = auto()
    TERMINAL = auto()


class Rusher:
    def __init__(
        self,
        config: Config,
        ui: UIAdapter,
        state: SubmissionState,
        notifier: NotificationAdapter,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.ui = ui
        self.state = state
        self.notifier = notifier
        self.logger = logger or logging.getLogger(__name__)
        self.schedule = PollSchedule(
            config.normal_interval_seconds,
            config.rush_interval_seconds,
            config.rush_start,
            config.rush_end,
        )

    def scan_once(self) -> str:
        attempt_state = AttemptState.NOT_STARTED
        try:
            candidate = self.ui.find_target_card(self.config.title_keyword)
            if candidate is None:
                self.logger.debug("no matching card found")
                return "not_found"
            if self.state.seen(candidate.fingerprint):
                self.logger.debug("card already submitted; fingerprint=%s", candidate.fingerprint)
                return "already_submitted"

            if self.config.dry_run:
                self.notifier.notify("dry_run", "识别测试通过；未执行真实提交")
                return "dry_run"

            self.ui.open_card(candidate)
            attempt_state = AttemptState.CARD_OPENED
            # From this point onward, conservatively assume an insertion may be sent.
            attempt_state = AttemptState.INSERTION_SENT
            self.ui.submit_current_card()

            deadline = time.monotonic() + self.config.action_timeout_seconds
            while time.monotonic() < deadline:
                if self.ui.card_is_submitted():
                    attempt_state = AttemptState.TERMINAL
                    self.state.record(candidate.fingerprint, "matched card")
                    self.state.save()
                    self.notifier.notify("submitted", "接龙提交成功")
                    return "submitted"
                time.sleep(0.1)
            attempt_state = AttemptState.TERMINAL
            self.notifier.notify("timeout", "未确认提交成功；不会重试")
            return "timeout"
        except UIError as exc:
            after_attempt = attempt_state in {
                AttemptState.INSERTION_SENT,
                AttemptState.TERMINAL,
            }
            status = "unsafe_state_after_attempt" if after_attempt else "unsafe_state"
            self.logger.warning("%s: %s", status, exc)
            self.notifier.notify(status, "界面状态异常；程序已停止且不会重试")
            return status

    def run_forever(
        self,
        stop_event: threading.Event | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        emit = status_callback or (lambda _status: None)
        self.logger.info("monitor started; press Ctrl+C to stop")
        try:
            if (
                self.config.run_weekdays
                and datetime.now().weekday() not in self.config.run_weekdays
            ):
                self.logger.info("today is not an enabled weekday; exiting")
                emit("inactive_day")
                return
            while True:
                if stop_event is not None and stop_event.is_set():
                    emit("stopped")
                    return
                now = datetime.now()
                interval = self.schedule.interval_at(now.time())
                is_rush = (
                    self.config.rush_interval_seconds < self.config.normal_interval_seconds
                    and self.config.rush_start <= now.time() < self.config.rush_end
                )
                emit("rush_waiting" if is_rush else "waiting")
                result = self.scan_once()
                emit(result)
                if result == "dry_run":
                    self.logger.info("recognition test completed; exiting")
                    return
                if result == "submitted" and self.config.stop_after_submission:
                    self.logger.info("submission succeeded; exiting")
                    return
                if result in {
                    "unsafe_state",
                    "unsafe_state_after_attempt",
                    "timeout",
                    "already_submitted",
                }:
                    self.logger.info("terminal scan result %s; exiting without retry", result)
                    return
                if (
                    self.config.run_weekdays
                    and datetime.now().weekday() not in self.config.run_weekdays
                ):
                    self.logger.info("enabled weekday ended; exiting")
                    emit("inactive_day")
                    return
                if stop_event is not None:
                    if stop_event.wait(interval):
                        emit("stopped")
                        return
                else:
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.logger.info("monitor stopped")
            emit("stopped")
        finally:
            self.state.save()


def build_rusher(config: Config, logger: logging.Logger) -> Rusher:
    state = SubmissionState(config.state_path)
    return Rusher(config, WeComUI(config, logger), state, Notifier(logger), logger)
