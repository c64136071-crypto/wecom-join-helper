from __future__ import annotations

import logging
import threading
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


class MonitoringPaused(UIError):
    """Raised when the helper is in front and must not steal focus."""


class ActionStopped(UIError):
    """Raised when an explicit stop interrupts a document action."""


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


def window_style_can_obscure(ex_style: int) -> bool:
    """Mouse-transparent overlay windows do not hide clickable WeCom content."""
    return not bool(ex_style & 0x20)  # WS_EX_TRANSPARENT


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
    _allowed_executable_names = {"wxwork.exe", "wxworkweb.exe"}
    _document_executable_names = _allowed_executable_names | {"wemail.exe"}

    def __init__(
        self,
        config: Config,
        logger: logging.Logger | None = None,
        assistant_window_handle: int | None = None,
    ):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.templates = TemplateStore(config.templates_dir)
        self.ocr = OCRReader()
        self._group_signature: bytes | None = None
        self.assistant_window_handle = assistant_window_handle
        self._button_text_cache: dict[str, str] = {}
        self._edit_confirmed = False
        self._commit_sent = False

    @staticmethod
    def _window_executable_name(window: Any) -> str:
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            process_id = int(window.element_info.process_id)
            handle = kernel32.OpenProcess(0x1000, False, process_id)
            if not handle:
                return ""
            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if not kernel32.QueryFullProcessImageNameW(
                    handle, 0, buffer, ctypes.byref(size)
                ):
                    return ""
                return Path(buffer.value).name
            finally:
                kernel32.CloseHandle(handle)
        except (AttributeError, OSError, TypeError, ValueError):
            return ""

    def _matching_windows(
        self,
        allowed_executable_names: set[str] | None = None,
        exact_titles: dict[str, str] | None = None,
    ) -> list[Any]:
        try:
            from pywinauto import Desktop
        except ImportError:
            raise UIError("pywinauto is not installed; run pip install -r requirements.txt") from None

        try:
            pattern = f".*(?:{self.config.window_title_keyword}).*"
            candidates = Desktop(backend="uia").windows(
                title_re=pattern, visible_only=True
            )
        except Exception as exc:
            raise UIError(f"could not inspect Enterprise WeChat window: {exc}") from exc
        allowed_names = (
            self._allowed_executable_names
            if allowed_executable_names is None
            else allowed_executable_names
        )
        required_titles = exact_titles or {}
        windows = []
        for window in candidates:
            executable_name = self._window_executable_name(window).casefold()
            if executable_name in allowed_names:
                required_title = required_titles.get(executable_name)
                if required_title is not None and window.window_text() != required_title:
                    self.logger.debug(
                        "ignored non-document WeCom host; executable=%s",
                        executable_name,
                    )
                    continue
                windows.append(window)
            else:
                self.logger.debug(
                    "ignored title-matching non-WeCom window; executable=%s",
                    executable_name or "<unknown>",
                )
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
            for window in self._matching_windows(
                self._document_executable_names,
                exact_titles={
                    "wemail.exe": self.config.document_window_title_keyword,
                },
            )
            if self.config.document_window_title_keyword in window.window_text()
        ]
        return self._select_window(windows, "Enterprise WeChat document")

    def prepare_monitoring(self) -> None:
        self.ocr.warmup()
        window = self._main_window()
        try:
            if window.is_minimized():
                window.restore()
            window.set_focus()
            time.sleep(0.3)
        except Exception as exc:
            raise UIError(f"could not bring Enterprise WeChat to foreground: {exc}") from exc

    @staticmethod
    def _window_handle(window: Any) -> int | None:
        try:
            handle = getattr(window, "handle", None)
            if handle is None:
                handle = getattr(window.element_info, "handle", None)
            handle = int(handle)
            return handle if handle > 0 else None
        except (AttributeError, TypeError, ValueError):
            return None

    def _assistant_is_foreground(self) -> bool:
        if not self.assistant_window_handle:
            return False
        try:
            import ctypes

            return int(ctypes.windll.user32.GetForegroundWindow()) == int(
                self.assistant_window_handle
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def _is_window_obscured(self, window: Any) -> bool:
        """Check only actual overlapping windows above the target in z-order."""
        target_handle = self._window_handle(window)
        if target_handle is None:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetWindow.restype = wintypes.HWND
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long

            target_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(target_handle, ctypes.byref(target_pid))
            left, top, width, height = self._bounds(window)
            right, bottom = left + width, top + height
            current = int(user32.GetWindow(target_handle, 3) or 0)  # GW_HWNDPREV
            while current:
                if bool(user32.IsWindowVisible(current)):
                    ex_style = int(user32.GetWindowLongW(current, -20))
                    if not window_style_can_obscure(ex_style):
                        current = int(user32.GetWindow(current, 3) or 0)
                        continue
                    rect = wintypes.RECT()
                    if user32.GetWindowRect(current, ctypes.byref(rect)):
                        overlaps = (
                            rect.left < right
                            and rect.right > left
                            and rect.top < bottom
                            and rect.bottom > top
                        )
                        if overlaps:
                            owner_pid = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(current, ctypes.byref(owner_pid))
                            if int(owner_pid.value) != int(target_pid.value):
                                self.logger.debug(
                                    "Enterprise WeChat is covered by an external window; pid=%s",
                                    owner_pid.value,
                                )
                                return True
                current = int(user32.GetWindow(current, 3) or 0)
        except (AttributeError, OSError, TypeError, ValueError):
            self.logger.debug("could not inspect window z-order", exc_info=True)
        return False

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
        self, window: Any, *, focus_window: bool = False
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

    def _matches(
        self,
        screenshot: Any,
        template_name: str,
        threshold: float | None = None,
    ) -> list[TemplateMatch]:
        template = self.templates.load(template_name)
        return locate_templates_multiscale(
            screenshot,
            template,
            self.config.match_threshold if threshold is None else threshold,
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
        if self._assistant_is_foreground():
            raise MonitoringPaused("Join Helper is in the foreground")
        if window.is_minimized() or self._is_window_obscured(window):
            self.prepare_monitoring()
            window = self._main_window()
        screenshot, bounds = self._screenshot(window, focus_window=False)
        self._verify_group_header(screenshot)
        icons = self._matches(screenshot, "yellow_icon")
        # The current card is rendered at 0.667x on the user's display. Its
        # button has a lower correlation than the icon because the grey card
        # background varies, so pair it with the strong icon before OCR.
        participate_threshold = max(0.70, self.config.match_threshold - 0.18)
        buttons = self._matches(
            screenshot, "participate", threshold=participate_threshold
        )
        visual_matches = pair_card_matches(icons, buttons)
        self.logger.debug(
            "card scan candidates; icons=%d buttons=%d visual_matches=%d",
            len(icons),
            len(buttons),
            len(visual_matches),
        )
        for visual in visual_matches:
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

    def _document_buttons(self, screenshot: Any, template_name: str) -> list[TemplateMatch]:
        expected = {"join": "接龙", "submit": "确定"}[template_name]
        accepted = []
        for match in self._matches(screenshot, template_name):
            # The persistent document toolbar contains an unrelated blue invite
            # button which correlates strongly with the confirmation template.
            if match.y < max(screenshot.height * 0.12, 120 * match.scale):
                continue
            if template_name == "submit" and not match_has_filled_blue_background(screenshot, match):
                continue
            crop = screenshot.crop((
                max(0, match.x - match.width // 2 - 8),
                max(0, match.y - match.height // 2 - 8),
                min(screenshot.width, match.x + match.width // 2 + 8),
                min(screenshot.height, match.y + match.height // 2 + 8),
            ))
            key = image_fingerprint(crop)
            if key not in self._button_text_cache:
                if len(self._button_text_cache) >= 64:
                    self._button_text_cache.clear()
                self._button_text_cache[key] = self.ocr.read(crop)
            if self._button_text_cache[key] == expected:
                accepted.append(match)
        return accepted

    @staticmethod
    def _check_stopped(stop_event: threading.Event | None) -> None:
        if stop_event is not None and stop_event.is_set():
            raise ActionStopped("document action stopped by user")

    def _guard_document(self, window: Any, stop_event: threading.Event | None) -> None:
        self._check_stopped(stop_event)
        if self._assistant_is_foreground() or window.is_minimized() or self._is_window_obscured(window):
            raise UIError("document action interrupted by another window; no retry")

    def _scroll_document(self, window: Any, bounds: tuple[int, int, int, int],
                         stop_event: threading.Event | None) -> None:
        self._guard_document(window, stop_event)
        if self.config.dry_run:
            return
        import pyautogui

        # Wheel input over the document body needs no click in an editable row.
        pyautogui.moveTo(bounds[0] + bounds[2] // 2, bounds[1] + bounds[3] * 3 // 4)
        self._guard_document(window, stop_event)
        pyautogui.scroll(-10)

    def _wait_for_template(
        self, template_name: str, stop_event: threading.Event | None = None,
    ) -> tuple[tuple[int, int], tuple[int, int, int, int], tuple[int, int]]:
        timeout = (self.config.document_load_timeout_seconds if template_name == "join"
                   else self.config.action_timeout_seconds)
        started = time.monotonic()
        deadline = started + timeout
        next_scroll = started + 0.6
        scrolls = 0
        previous = None
        while time.monotonic() < deadline:
            self._check_stopped(stop_event)
            try:
                window = self._document_window()
            except UIError:
                time.sleep(0.1)
                continue
            self._guard_document(window, stop_event)
            screenshot, bounds = self._screenshot(window, focus_window=False)
            matches = self._document_buttons(screenshot, template_name)
            if matches:
                point = (matches[0].x, matches[0].y)
                current = (point, bounds, self._window_handle(window))
                # Require two fresh frames at the same location: concurrent
                # sign-ups can move the button while OCR is running.
                if current == previous and time.monotonic() < deadline:
                    self._guard_document(window, stop_event)
                    self.logger.debug("document %s ready; elapsed=%.2fs scrolls=%d",
                                      template_name, time.monotonic() - started, scrolls)
                    return point, bounds, screenshot.size
                previous = current
            else:
                previous = None
                if next_scroll <= time.monotonic() < deadline and scrolls < 24:
                    self._scroll_document(window, bounds, stop_event)
                    scrolls += 1
                    next_scroll = time.monotonic() + 0.4
            time.sleep(0.1)
        raise UIError(f"timed out waiting for document {template_name}; scrolls={scrolls}")

    def submit_current_card(self, stop_event: threading.Event | None = None) -> None:
        self._edit_confirmed = False
        self._commit_sent = False
        if self.config.dry_run:
            self.templates.load("join")
            self.templates.load("submit")
            self.logger.info("dry-run verified document action templates")
            return
        join_point, bounds, _ = self._wait_for_template("join", stop_event)
        self.logger.debug("document join button detected at %s", join_point)
        self._check_stopped(stop_event)
        self._click(join_point, bounds)
        edit_point, bounds, _ = self._wait_for_template("submit", stop_event)
        self.logger.debug("document edit state detected at %s", edit_point)
        self._edit_confirmed = True
        self._check_stopped(stop_event)
        self._click(edit_point, bounds)
        self._commit_sent = True
        self.logger.info("confirmed the prefilled name once")

    def card_is_submitted(self) -> bool:
        if not self._edit_confirmed or not self._commit_sent:
            return False
        try:
            window = self._document_window()
            self._guard_document(window, None)
            screenshot, _ = self._screenshot(window, focus_window=False)
            join_matches = self._document_buttons(screenshot, "join")
            filled_submit_matches = self._document_buttons(screenshot, "submit")
            self.logger.debug(
                "submission verification; join=%d verified_submit=%d",
                len(join_matches),
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
