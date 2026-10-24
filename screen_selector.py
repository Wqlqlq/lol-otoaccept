"""Full-screen overlay for picking a screen region or a single point.

The overlay shows a frozen, dimmed screenshot of the screen. Everything it
returns is in physical screen pixels, the same coordinates pyautogui uses for
screenshots and clicks.
"""

from __future__ import annotations

import contextlib
import sys
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import pyautogui
from PIL import Image, ImageEnhance, ImageTk

from config_manager import Point, Region

HIDE_DELAY_MS = 300  # gives the main window time to disappear before the screenshot
MIN_REGION_SIZE = 5
DIM_FACTOR = 0.45
ACCENT_COLOR = "#00d8ff"
PANEL_COLOR = "#1b1b1b"
TEXT_COLOR = "#ffffff"
FONT_FAMILY = "Segoe UI"

ResultT = TypeVar("ResultT")


def enable_dpi_awareness() -> None:
    """Make Windows report real pixels so Tk, screenshots and clicks share one coordinate system.

    Without this, display scaling (125%, 150%, ...) makes Tk coordinates differ
    from screenshot pixels. pyautogui also does this on import; calling it here
    keeps the guarantee explicit and is harmless if it is already set.
    """
    if sys.platform != "win32":
        return
    import ctypes

    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


@dataclass(frozen=True)
class RegionSelection:
    region: Region
    image: Image.Image  # the selected area, cropped from the frozen screenshot


class _SelectionOverlay(Generic[ResultT]):
    """Borderless, topmost window covering the primary screen with a dimmed screenshot."""

    def __init__(
        self,
        root: tk.Tk,
        screenshot: Image.Image,
        instruction: str,
        on_finish: Callable[[ResultT | None], None],
    ) -> None:
        self._screenshot = screenshot
        self._on_finish = on_finish
        self._finished = False

        self._canvas_width = root.winfo_screenwidth()
        self._canvas_height = root.winfo_screenheight()
        # Normally 1.0. Differs only if the process is not DPI aware.
        self._scale_x = screenshot.width / self._canvas_width
        self._scale_y = screenshot.height / self._canvas_height
        canvas_size = (self._canvas_width, self._canvas_height)
        self._display_image = (
            screenshot if screenshot.size == canvas_size else screenshot.resize(canvas_size, Image.Resampling.LANCZOS)
        )
        # Prepared before the window exists, so a failure here cannot leave a
        # borderless full-screen window behind.
        dimmed = ImageEnhance.Brightness(self._display_image).enhance(DIM_FACTOR)
        self._background_photo = ImageTk.PhotoImage(dimmed, master=root)

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.geometry(f"{self._canvas_width}x{self._canvas_height}+0+0")
        self.window.attributes("-topmost", True)

        self.canvas = tk.Canvas(
            self.window,
            width=self._canvas_width,
            height=self._canvas_height,
            highlightthickness=0,
            borderwidth=0,
            cursor="crosshair",
            background="black",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self._background_photo, anchor="nw")
        self.set_instruction(instruction)

        self.window.bind("<Escape>", lambda _event: self.cancel())
        self.canvas.bind("<Button-3>", lambda _event: self.cancel())
        self.window.after(50, self._take_focus)

    def set_instruction(self, text: str) -> None:
        self.canvas.delete("instruction")
        center_x = self._canvas_width // 2
        title_id = self.canvas.create_text(
            center_x, 36, text=text, fill=TEXT_COLOR, font=(FONT_FAMILY, 16, "bold"), tags="instruction"
        )
        self.canvas.create_text(
            center_x,
            66,
            text="ESC or right-click to cancel",
            fill="#cfcfcf",
            font=(FONT_FAMILY, 11),
            tags="instruction",
        )
        left, top, right, _ = self.canvas.bbox(title_id)
        panel_id = self.canvas.create_rectangle(
            min(left, center_x - 140) - 20,
            top - 12,
            max(right, center_x + 140) + 20,
            84,
            fill=PANEL_COLOR,
            outline=ACCENT_COLOR,
            width=2,
            tags="instruction",
        )
        self.canvas.tag_lower(panel_id, title_id)

    def finish(self, result: ResultT | None) -> None:
        if self._finished:
            return
        self._finished = True
        self.window.destroy()
        self._on_finish(result)

    def cancel(self) -> None:
        self.finish(None)

    def clamp_to_canvas(self, x: int, y: int) -> tuple[int, int]:
        return min(max(x, 0), self._canvas_width), min(max(y, 0), self._canvas_height)

    def to_screen_point(self, canvas_x: int, canvas_y: int) -> Point:
        x = min(int(canvas_x * self._scale_x), self._screenshot.width - 1)
        y = min(int(canvas_y * self._scale_y), self._screenshot.height - 1)
        return Point(x=max(x, 0), y=max(y, 0))

    def to_screen_region(self, left: int, top: int, right: int, bottom: int) -> Region:
        x0, y0 = round(left * self._scale_x), round(top * self._scale_y)
        x1 = min(round(right * self._scale_x), self._screenshot.width)
        y1 = min(round(bottom * self._scale_y), self._screenshot.height)
        return Region(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

    def crop_screenshot(self, region: Region) -> Image.Image:
        return self._screenshot.crop((region.x, region.y, region.right, region.bottom))

    def crop_display(self, left: int, top: int, right: int, bottom: int) -> Image.Image:
        return self._display_image.crop((left, top, right, bottom))

    def _take_focus(self) -> None:
        if self._finished:
            return
        self.window.lift()
        self.window.focus_force()
        self.canvas.focus_set()


class _RegionOverlay(_SelectionOverlay[RegionSelection]):
    """Drag with the left mouse button to draw a rectangle."""

    def __init__(
        self,
        root: tk.Tk,
        screenshot: Image.Image,
        instruction: str,
        on_finish: Callable[[RegionSelection | None], None],
    ) -> None:
        super().__init__(root, screenshot, instruction, on_finish)
        self._drag_start: tuple[int, int] | None = None
        self._selection_photo: ImageTk.PhotoImage | None = None
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event: tk.Event) -> None:
        self._drag_start = self.clamp_to_canvas(event.x, event.y)
        self._draw_selection(*self._drag_start, *self._drag_start)

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        self._draw_selection(*self._drag_start, *self.clamp_to_canvas(event.x, event.y))

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        left, top, right, bottom = self._normalize(*self._drag_start, *self.clamp_to_canvas(event.x, event.y))
        self._drag_start = None
        region = self.to_screen_region(left, top, right, bottom)
        if region.width < MIN_REGION_SIZE or region.height < MIN_REGION_SIZE:
            self.canvas.delete("selection")
            self.set_instruction("Selection too small - drag a larger rectangle")
            return
        self.finish(RegionSelection(region=region, image=self.crop_screenshot(region)))

    @staticmethod
    def _normalize(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def _draw_selection(self, x0: int, y0: int, x1: int, y1: int) -> None:
        left, top, right, bottom = self._normalize(x0, y0, x1, y1)
        self.canvas.delete("selection")
        if right - left >= 1 and bottom - top >= 1:
            # Show the selected area at full brightness on top of the dimmed screen.
            self._selection_photo = ImageTk.PhotoImage(
                self.crop_display(left, top, right, bottom), master=self.canvas
            )
            self.canvas.create_image(left, top, image=self._selection_photo, anchor="nw", tags="selection")
        self.canvas.create_rectangle(left, top, right, bottom, outline=ACCENT_COLOR, width=2, tags="selection")

        region = self.to_screen_region(left, top, right, bottom)
        label_y = bottom + 14 if bottom + 28 < self._canvas_height else top - 14
        self.canvas.create_text(
            right,
            label_y,
            text=f"{region.width} x {region.height}",
            anchor="e",
            fill=ACCENT_COLOR,
            font=(FONT_FAMILY, 11, "bold"),
            tags="selection",
        )
        self.canvas.tag_raise("instruction")


class _PointOverlay(_SelectionOverlay[Point]):
    """Click once with the left mouse button to pick a point."""

    def __init__(
        self,
        root: tk.Tk,
        screenshot: Image.Image,
        instruction: str,
        on_finish: Callable[[Point | None], None],
    ) -> None:
        super().__init__(root, screenshot, instruction, on_finish)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<ButtonPress-1>", self._on_click)

    def _on_motion(self, event: tk.Event) -> None:
        x, y = self.clamp_to_canvas(event.x, event.y)
        point = self.to_screen_point(x, y)
        self.canvas.delete("crosshair")
        self.canvas.create_line(0, y, self._canvas_width, y, fill=ACCENT_COLOR, dash=(4, 4), tags="crosshair")
        self.canvas.create_line(x, 0, x, self._canvas_height, fill=ACCENT_COLOR, dash=(4, 4), tags="crosshair")
        # Keep the coordinate label on screen near the right edge.
        label_on_right = x + 140 < self._canvas_width
        self.canvas.create_text(
            x + 10 if label_on_right else x - 10,
            y - 8,
            text=str(point),
            anchor="sw" if label_on_right else "se",
            fill=ACCENT_COLOR,
            font=(FONT_FAMILY, 11, "bold"),
            tags="crosshair",
        )
        self.canvas.tag_raise("instruction")

    def _on_click(self, event: tk.Event) -> None:
        self.finish(self.to_screen_point(*self.clamp_to_canvas(event.x, event.y)))


OverlayFactory = Callable[[Image.Image], _SelectionOverlay[Any]]


class ScreenSelector:
    """Runs one selection at a time and hides the main window while it is open.

    Results are delivered to the on_done callback on the Tk main thread;
    None means the user cancelled.
    """

    def __init__(self, root: tk.Tk, capture_screen: Callable[[], Image.Image] = pyautogui.screenshot) -> None:
        self._root = root
        self._capture_screen = capture_screen
        self._overlay: _SelectionOverlay[Any] | None = None
        self._pending_open_id: str | None = None
        self._on_done: Callable[[Any], None] | None = None

    @property
    def is_active(self) -> bool:
        return self._on_done is not None

    def select_region(self, instruction: str, on_done: Callable[[RegionSelection | None], None]) -> None:
        self._begin(lambda shot: _RegionOverlay(self._root, shot, instruction, self._complete), on_done)

    def select_point(self, instruction: str, on_done: Callable[[Point | None], None]) -> None:
        self._begin(lambda shot: _PointOverlay(self._root, shot, instruction, self._complete), on_done)

    def cancel(self) -> None:
        """Leave selection mode if it is active; does nothing otherwise."""
        if self._overlay is not None:
            self._overlay.cancel()
        elif self._pending_open_id is not None:
            self._root.after_cancel(self._pending_open_id)
            self._pending_open_id = None
            self._complete(None)

    def _begin(self, create_overlay: OverlayFactory, on_done: Callable[[Any], None]) -> None:
        if self.is_active:
            return
        self._on_done = on_done
        self._root.withdraw()
        self._pending_open_id = self._root.after(HIDE_DELAY_MS, lambda: self._open(create_overlay))

    def _open(self, create_overlay: OverlayFactory) -> None:
        self._pending_open_id = None
        try:
            self._overlay = create_overlay(self._capture_screen())
        except Exception:
            # Restore the main window, then let Tk's error handler report it.
            self._reset()
            raise

    def _complete(self, result: Any) -> None:
        on_done = self._on_done
        self._reset()
        if on_done is not None:
            on_done(result)

    def _reset(self) -> None:
        self._overlay = None
        self._on_done = None
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
