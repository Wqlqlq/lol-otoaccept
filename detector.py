"""Template matching, the anti-spam state machine and the monitoring thread."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import cv2
import numpy as np
import pyautogui
from PIL import Image

from config_manager import AppConfig, Point, Region


class MonitorStatus(str, Enum):
    IDLE = "Idle"
    MONITORING = "Monitoring"
    MATCH_DETECTED = "Match detected"
    CLICKED = "Clicked"


class TemplateError(Exception):
    """The template image is missing, unreadable or unusable for matching."""


class MonitorSetupError(Exception):
    """The settings are incomplete or inconsistent, so monitoring cannot start."""


def to_grayscale(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)


def save_template(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


@dataclass(frozen=True)
class MatchResult:
    confidence: float
    location: tuple[int, int]  # top-left corner of the best match inside the frame
    size: tuple[int, int]  # template width and height


class TemplateMatcher:
    """Finds a template inside screenshots with cv2.TM_CCOEFF_NORMED."""

    # Below this grayscale standard deviation the template is a flat color and
    # would "match" any flat area of the screen.
    MIN_TEMPLATE_STDDEV = 2.0

    def __init__(self, template: Image.Image) -> None:
        gray = to_grayscale(template)
        if float(gray.std()) < self.MIN_TEMPLATE_STDDEV:
            raise TemplateError(
                "The template is almost a single flat color.\n"
                "Capture an area with visible detail, such as the ACCEPT button text."
            )
        self._template = gray

    @classmethod
    def from_file(cls, path: Path) -> TemplateMatcher:
        # Loaded through Pillow because cv2.imread cannot open paths containing
        # non-ASCII characters on Windows (e.g. C:\Users\Kullanıcı\...).
        if not path.is_file():
            raise TemplateError(
                f"Template image not found:\n{path}\n\nUse 'Capture Template' to create it."
            )
        try:
            with Image.open(path) as image:
                return cls(image)
        except OSError as exc:
            raise TemplateError(f"Could not read the template image:\n{path}\n\n{exc}") from exc

    @property
    def width(self) -> int:
        return int(self._template.shape[1])

    @property
    def height(self) -> int:
        return int(self._template.shape[0])

    def match(self, frame: Image.Image) -> MatchResult:
        gray = to_grayscale(frame)
        frame_height, frame_width = gray.shape
        if self.width > frame_width or self.height > frame_height:
            raise TemplateError(
                f"The template ({self.width}x{self.height}) is larger than the "
                f"detection area ({frame_width}x{frame_height})."
            )
        scores = cv2.matchTemplate(gray, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_location = cv2.minMaxLoc(scores)
        confidence = float(max_value) if math.isfinite(max_value) else 0.0
        return MatchResult(
            confidence=confidence,
            location=(int(max_location[0]), int(max_location[1])),
            size=(self.width, self.height),
        )


class DetectionState(Enum):
    WAITING = auto()
    DETECTED = auto()
    WAIT_FOR_DISAPPEAR = auto()


class DetectionEvent(Enum):
    NONE = auto()
    APPEARED = auto()
    DISAPPEARED = auto()


class DetectionStateMachine:
    """Allows exactly one click per appearance of the template.

    WAITING --(confidence >= threshold)--> DETECTED --mark_clicked()--> WAIT_FOR_DISAPPEAR
    WAIT_FOR_DISAPPEAR --(confidence < threshold)--> WAITING

    The way back to WAITING requires `disappear_frames` consecutive checks below
    the threshold, so one noisy frame cannot re-arm the click while the template
    is still on screen.
    """

    def __init__(self, threshold: float, disappear_frames: int = 3) -> None:
        if disappear_frames < 1:
            raise ValueError("disappear_frames must be at least 1")
        self._threshold = threshold
        self._disappear_frames = disappear_frames
        self._state = DetectionState.WAITING
        self._frames_below_threshold = 0

    @property
    def state(self) -> DetectionState:
        return self._state

    def update(self, confidence: float) -> DetectionEvent:
        matched = confidence >= self._threshold

        if self._state is DetectionState.WAITING and matched:
            self._state = DetectionState.DETECTED
            return DetectionEvent.APPEARED

        if self._state is DetectionState.WAIT_FOR_DISAPPEAR:
            if matched:
                self._frames_below_threshold = 0
                return DetectionEvent.NONE
            self._frames_below_threshold += 1
            if self._frames_below_threshold >= self._disappear_frames:
                self._state = DetectionState.WAITING
                self._frames_below_threshold = 0
                return DetectionEvent.DISAPPEARED

        return DetectionEvent.NONE

    def mark_clicked(self) -> None:
        if self._state is not DetectionState.DETECTED:
            raise RuntimeError("mark_clicked() is only valid right after a detection")
        self._state = DetectionState.WAIT_FOR_DISAPPEAR
        self._frames_below_threshold = 0


@dataclass(frozen=True)
class MonitorSettings:
    region: Region
    click_position: Point
    threshold: float
    check_interval_ms: int


def build_monitor_settings(
    config: AppConfig, template_path: Path, screen_size: tuple[int, int]
) -> tuple[MonitorSettings, TemplateMatcher]:
    """Validate the user's config and return what MatchMonitor needs.

    Raises MonitorSetupError with a message suitable for showing to the user.
    """
    screen_width, screen_height = screen_size

    region = config.detection_region
    if region is None:
        raise MonitorSetupError("No detection area selected.\n\nUse 'Select Area' first.")
    if not region.fits_inside(screen_width, screen_height):
        raise MonitorSetupError(
            f"The detection area ({region}) is outside the current screen "
            f"({screen_width}x{screen_height}).\n\nSelect the area again."
        )

    try:
        matcher = TemplateMatcher.from_file(template_path)
    except TemplateError as exc:
        raise MonitorSetupError(str(exc)) from exc
    if matcher.width > region.width or matcher.height > region.height:
        raise MonitorSetupError(
            f"The template ({matcher.width}x{matcher.height}) is larger than the detection "
            f"area ({region.width}x{region.height}).\n\n"
            "Select a larger detection area or capture a smaller template."
        )

    click = config.click_position
    if click is None:
        raise MonitorSetupError("No click position selected.\n\nUse 'Select Click Point' first.")
    if not (0 <= click.x < screen_width and 0 <= click.y < screen_height):
        raise MonitorSetupError(
            f"The click position ({click}) is outside the current screen "
            f"({screen_width}x{screen_height}).\n\nSelect the click point again."
        )

    settings = MonitorSettings(
        region=region,
        click_position=click,
        threshold=config.threshold,
        check_interval_ms=config.check_interval_ms,
    )
    return settings, matcher


@dataclass(frozen=True)
class MonitorCallbacks:
    """Hooks invoked from the monitoring thread. They must not touch Tk directly."""

    on_status: Callable[[MonitorStatus], None]
    on_frame: Callable[[Image.Image, MatchResult], None]
    on_error: Callable[[str], None]
    on_stopped: Callable[[], None]


ScreenCapture = Callable[[Region], Image.Image]
ClickAction = Callable[[int, int], None]


def capture_region(region: Region) -> Image.Image:
    return pyautogui.screenshot(region=region.as_tuple())


def click_at(x: int, y: int) -> None:
    pyautogui.click(x, y)


class MatchMonitor:
    """Background thread: capture the region, match the template, click once per appearance."""

    def __init__(
        self,
        settings: MonitorSettings,
        matcher: TemplateMatcher,
        callbacks: MonitorCallbacks,
        logger: logging.Logger,
        capture: ScreenCapture = capture_region,
        click: ClickAction = click_at,
    ) -> None:
        self._settings = settings
        self._matcher = matcher
        self._callbacks = callbacks
        self._logger = logger
        self._capture = capture
        self._click = click
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="MatchMonitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the thread to stop and wait briefly for it to finish its current check."""
        self._stop_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _run(self) -> None:
        state_machine = DetectionStateMachine(self._settings.threshold)
        interval_seconds = self._settings.check_interval_ms / 1000
        self._logger.info("Monitoring started")
        self._callbacks.on_status(MonitorStatus.MONITORING)
        try:
            while not self._stop_event.is_set():
                started = time.perf_counter()
                self._check_once(state_machine)
                elapsed = time.perf_counter() - started
                self._stop_event.wait(max(0.0, interval_seconds - elapsed))
        except pyautogui.FailSafeException:
            message = (
                "PyAutoGUI fail-safe triggered because the mouse was in a screen corner.\n"
                "Monitoring was stopped for safety."
            )
            self._logger.info("Error: fail-safe triggered")
            self._callbacks.on_error(message)
        except Exception as exc:  # Report any failure to the GUI instead of dying silently.
            self._logger.error("Error: %s", exc, exc_info=True)
            self._callbacks.on_error(str(exc))
        finally:
            self._logger.info("Monitoring stopped")
            self._callbacks.on_stopped()

    def _check_once(self, state_machine: DetectionStateMachine) -> None:
        frame = self._capture(self._settings.region)
        result = self._matcher.match(frame)
        self._callbacks.on_frame(frame, result)
        if self._stop_event.is_set():
            return  # Stop was requested during this check: never click afterwards.

        event = state_machine.update(result.confidence)
        if event is DetectionEvent.APPEARED:
            self._click_once(state_machine, result)
        elif event is DetectionEvent.DISAPPEARED:
            self._logger.info("Template disappeared")
            self._callbacks.on_status(MonitorStatus.MONITORING)

    def _click_once(self, state_machine: DetectionStateMachine, result: MatchResult) -> None:
        self._logger.info("Template detected confidence=%.2f", result.confidence)
        self._callbacks.on_status(MonitorStatus.MATCH_DETECTED)

        point = self._settings.click_position
        self._click(point.x, point.y)
        state_machine.mark_clicked()

        self._logger.info("Clicked x=%d y=%d", point.x, point.y)
        self._callbacks.on_status(MonitorStatus.CLICKED)
