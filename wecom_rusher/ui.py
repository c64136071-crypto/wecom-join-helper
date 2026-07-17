from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .ocr import OCRReader, keyword_matches
from .vision import (
    TemplateMatch,
    image_fingerprint,
    image_signature,
    locate_templates_multiscale,
    signature_distance,
)


class UIError(RuntimeError):
    """Raised when the visible UI is not in a safe expected state."""


class TemplateStore:
    _required = ("yellow_icon", "participate", "join", "submit")

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    @classmethod
    def required_names(cls) -> tuple[str, ...]:
        return cls._required

    def load(self, name: str) -> Any:
        path = self.directory / f"{name}.png"
        if not path.exists():
            raise UIError(f"missing template: {path}")
        try:
            from PIL import Image

            return Image.open(path).convert("RGB")
        except ImportError:
            raise UIError("Pillow is not installed; run pip install -r requirements.txt") from None
        except OSError as exc:
            raise UIError(f"could not open template {path}: {exc}") from exc


@dataclass(frozen=True)
class CardCandidate:
    fingerprint: str
    title: str
    participate_point: tuple[int, int]


@dataclass(frozen=True)
class CardVisualMatch:
    icon: TemplateMatch
    button: TemplateMatch


def pair_card_matches(
    icons: list[TemplateMatch], buttons: list[TemplateMatch]
) -> list[CardVisualMatch]:
    pairs: list[CardVisualMatch] = []
    used_buttons: set[tuple[int, int]] = set()
    for icon in sorted(icons, key=lambda match: match.y, reverse=True):
        best: tuple[float, TemplateMatch] | None = None
        for button in buttons:
            if (button.x, button.y) in used_buttons:
                continue
            scale = (icon.scale + button.scale) / 2
            horizontal_gap = icon.x - button.x
            vertical_gap = button.y - icon.y
            if not 120 * scale <= horizontal_gap <= 360 * scale:
                continue
            if not 20 * scale <= vertical_gap <= 150 * scale:
                continue
            score = abs(horizontal_gap - 240 * scale) + abs(vertical_gap - 70 * scale)
            if best is None or score < best[0]:
                best = (score, button)
        if best is not None:
            used_buttons.add((best[1].x, best[1].y))
            pairs.append(CardVisualMatch(icon, best[1]))
    return sorted(pairs, key=lambda pair: pair.button.y, reverse=True)


def safe_commit_point(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    """Return a point in the document's right-side blank area to commit focus."""
    left, top, width, height = bounds
    return width - 120, height // 2


def match_has_filled_blue_background(
    screenshot: Any,
    match: TemplateMatch,
    *,
    minimum_ratio: float = 0.2,
) -> bool:
    left = max(0, match.x - match.width // 2)
    top = max(0, match.y - match.height // 2)
    right = min(screenshot.width, left + match.width)
    bottom = min(screenshot.height, top + match.height)
    crop = screenshot.crop((left, top, right, bottom)).convert("RGB")
    pixels = list(crop.getdata())
    if not pixels:
        return False
    blue_pixels = sum(
        1
        for red, green, blue in pixels
        if blue >= 130 and blue - red >= 35 and blue - green >= 20
    )
    return blue_pixels / len(pixels) >= minimum_ratio


class WeComUI:
    def __init__(self, config: Config, logger: logging.Logger | None = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.templates = TemplateStore(config.templates_dir)
        self.ocr = OCRReader()
        self._group_signature: bytes | None = None

    def _matching_windows(self) -> list[Any]:
        try:
            from pywinauto import Desktop
        except ImportError:
            raise UIError("pywinauto is not installed; run pip install -r requirements.txt") from None

        try:
            pattern = f".*(?:{self.config.window_title_keyword}).*"
            windows = Desktop(backend="uia").windows(title_re=pattern, visible_only=True)
        except Exception as exc:
            raise UIError(f"could not inspect Enterprise WeChat window: {exc}") from exc
        return windows

    def _select_window(self, windows: list[Any], label: str) -> Any:
        if not windows:
            raise UIError(f"no visible {label} window was found")
        if len(windows) == 1:
            return windows[0]

        def window_area(candidate: Any) -> int:
            rectangle = candidate.rectangle()
            return max(0, rectangle.right - rectangle.left) * max(0, rectangle.bottom - rectangle.top)

        selected = max(windows, key=window_area)
        self.logger.debug("selected the largest of %d %s windows", len(windows), label)
        return selected

    def _main_window(self) -> Any:
        windows = [
            window
            for window in self._matching_windows()
            if self.config.document_window_title_keyword not in window.window_text()
        ]
        return self._select_window(windows, "Enterprise WeChat main")

    def _document_window(self) -> Any:
        windows = [
            window
            for window in self._matching_windows()
            if self.config.document_window_title_keyword in window.window_text()
        ]
        return self._select_window(windows, "Enterprise WeChat document")

    @staticmethod
    def _bounds(window: Any) -> tuple[int, int, int, int]:
        rectangle = window.rectangle()
        left, top = int(rectangle.left), int(rectangle.top)
        width = int(rectangle.right - rectangle.left)
        height = int(rectangle.bottom - rectangle.top)
        if width <= 0 or height <= 0:
            raise UIError("Enterprise WeChat window has invalid bounds")
        return left, top, width, height

    def _screenshot(
        self, window: Any, *, focus_window: bool = True
    ) -> tuple[Any, tuple[int, int, int, int]]:
        try:
            import pyautogui

            if focus_window:
                try:
                    if window.is_minimized():
                        window.restore()
                    window.set_focus()
                    time.sleep(0.3)
                except Exception as exc:
                    raise UIError(f"could not bring Enterprise WeChat to foreground: {exc}") from exc
            bounds = self._bounds(window)
            return pyautogui.screenshot(region=bounds), bounds
        except ImportError:
            raise UIError("pyautogui is not installed; run pip install -r requirements.txt") from None
        except Exception as exc:
            raise UIError(f"could not capture Enterprise WeChat window: {exc}") from exc

    def _click(self, point: tuple[int, int], bounds: tuple[int, int, int, int]) -> None:
        if self.config.dry_run:
            self.logger.info("dry-run click at window point %s", point)
            return
        try:
            import pyautogui

            pyautogui.click(bounds[0] + point[0], bounds[1] + point[1])
        except ImportError:
            raise UIError("pyautogui is not installed; run pip install -r requirements.txt") from None
        except Exception as exc:
            raise UIError(f"could not click Enterprise WeChat: {exc}") from exc

    def _match(self, screenshot: Any, template_name: str) -> tuple[int, int] | None:
        matches = self._matches(screenshot, template_name)
        if not matches:
            return None
        return matches[0].x, matches[0].y

    def _matches(self, screenshot: Any, template_name: str) -> list[TemplateMatch]:
        template = self.templates.load(template_name)
        return locate_templates_multiscale(
            screenshot, template, self.config.match_threshold
        )

    def _verify_group_header(self, screenshot: Any) -> None:
        width, height = screenshot.size
        header = screenshot.crop(
            (
                int(width * 0.29),
                0,
                int(width * 0.72),
                min(110, int(height * 0.13)),
            )
        )
        current = image_signature(header)
        if self._group_signature is None:
            self._group_signature = current
            return
        if signature_distance(self._group_signature, current) > 72:
            raise UIError("the Enterprise WeChat group changed while monitoring")

    @staticmethod
    def _title_crop(screenshot: Any, match: CardVisualMatch) -> Any:
        scale = match.icon.scale
        left = max(0, match.icon.x - round(330 * scale))
        top = max(0, match.icon.y - round(60 * scale))
        right = min(screenshot.width, match.icon.x - round(40 * scale))
        bottom = min(screenshot.height, match.icon.y + round(15 * scale))
        return screenshot.crop((left, top, right, bottom))

    def find_target_card(self, title_keyword: str) -> CardCandidate | None:
        window = self._main_window()
        screenshot, bounds = self._screenshot(window)
        self._verify_group_header(screenshot)
        icons = self._matches(screenshot, "yellow_icon")
        buttons = self._matches(screenshot, "participate")
        for visual in pair_card_matches(icons, buttons):
            title_crop = self._title_crop(screenshot, visual)
            title = self.ocr.read(title_crop)
            self.logger.debug("OCR candidate evaluated; keyword_match=%s", keyword_matches(title, title_keyword))
            if not keyword_matches(title, title_keyword):
                continue
            scale = visual.icon.scale
            left = max(0, visual.icon.x - round(340 * scale))
            top = max(0, visual.icon.y - round(80 * scale))
            right = min(screenshot.width, visual.icon.x + round(45 * scale))
            bottom = min(screenshot.height, visual.button.y + round(50 * scale))
            card_crop = screenshot.crop((left, top, right, bottom))
            fingerprint = image_fingerprint(card_crop)
            self.logger.debug(
                "target card found; fingerprint=%s window_bounds=%s",
                fingerprint,
                bounds,
            )
            return CardCandidate(
                fingerprint,
                title or title_keyword,
                (visual.button.x, visual.button.y),
            )
        return None

    def open_card(self, candidate: CardCandidate) -> None:
        window = self._main_window()
        bounds = self._bounds(window)
        self._click(candidate.participate_point, bounds)
        if self.config.dry_run:
            return
        time.sleep(0.25)

    def _wait_for_template(self, template_name: str) -> tuple[int, int, tuple[int, int, int, int]]:
        deadline = time.monotonic() + self.config.action_timeout_seconds
        while time.monotonic() < deadline:
            try:
                window = self._document_window()
            except UIError:
                time.sleep(0.1)
                continue
            screenshot, bounds = self._screenshot(window, focus_window=False)
            point = self._match(screenshot, template_name)
            if point is not None:
                return point, bounds, (screenshot.width, screenshot.height)
            time.sleep(0.1)
        raise UIError(f"timed out waiting for template: {template_name}")

    def submit_current_card(self) -> None:
        if self.config.dry_run:
            self.templates.load("join")
            self.templates.load("submit")
            self.logger.info("dry-run verified document action templates")
            return
        join_point, bounds, _ = self._wait_for_template("join")
        self.logger.debug("document join button detected at %s", join_point)
        self._click(join_point, bounds)
        edit_point, bounds, _ = self._wait_for_template("submit")
        self.logger.debug("document edit state detected at %s", edit_point)
        commit_point = safe_commit_point(bounds)
        self.logger.info("committing the prefilled name by clicking outside the list at %s", commit_point)
        self._click(commit_point, bounds)

    def card_is_submitted(self) -> bool:
        try:
            window = self._document_window()
            screenshot, _ = self._screenshot(window, focus_window=False)
            join_matches = self._matches(screenshot, "join")
            submit_candidates = self._matches(screenshot, "submit")
            filled_submit_matches = [
                match
                for match in submit_candidates
                if match_has_filled_blue_background(screenshot, match)
            ]
            self.logger.debug(
                "submission verification; join=%d submit_candidates=%d filled_submit=%d",
                len(join_matches),
                len(submit_candidates),
                len(filled_submit_matches),
            )
            return bool(join_matches) and not filled_submit_matches
        except UIError:
            return False

    @staticmethod
    def _wait_for_calibration_hotkey(timeout_seconds: float = 120.0) -> None:
        try:
            import ctypes

            user32 = ctypes.windll.user32
        except (ImportError, AttributeError):
            raise UIError("global calibration hotkey is only available on Windows") from None

        vk_control = 0x11
        vk_menu = 0x12
        vk_f8 = 0x77
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            control_down = bool(user32.GetAsyncKeyState(vk_control) & 0x8000)
            alt_down = bool(user32.GetAsyncKeyState(vk_menu) & 0x8000)
            f8_down = bool(user32.GetAsyncKeyState(vk_f8) & 0x8000)
            if control_down and alt_down and f8_down:
                time.sleep(0.15)
                return
            time.sleep(0.03)
        raise UIError("timed out waiting for Ctrl+Alt+F8")

    def save_calibration_screenshot(self, wait_for_hotkey: bool = False) -> Path:
        if wait_for_hotkey:
            self._wait_for_calibration_hotkey()
            window = self._document_window()
            bounds = self._bounds(window)
            try:
                import pyautogui

                screenshot = pyautogui.screenshot(region=bounds)
            except ImportError:
                raise UIError("pyautogui is not installed; run setup again") from None
        else:
            window = self._main_window()
            screenshot, _ = self._screenshot(window)
        self.config.templates_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.templates_dir / "calibration-screen.png"
        screenshot.save(path)
        return path
