"""LoL Auto Accept: main window and application wiring.

Watches a screen area for the match "ACCEPT" button by template matching
screenshots, and clicks a user-chosen point once when it appears. Only
screenshots and simulated mouse clicks are used; the game client's files,
memory, process and API are never touched.
"""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from types import TracebackType
from typing import Any

import pyautogui
from PIL import Image, ImageDraw, ImageTk
from pynput import keyboard

from config_manager import (
    CHECK_INTERVAL_MAX_MS,
    CHECK_INTERVAL_MIN_MS,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    AppConfig,
    ConfigError,
    ConfigManager,
    Point,
    clamp_threshold,
)
from detector import (
    MatchMonitor,
    MatchResult,
    MonitorCallbacks,
    MonitorSetupError,
    MonitorStatus,
    TemplateError,
    TemplateMatcher,
    build_monitor_settings,
    save_template,
)
from hotkeys import GlobalHotkeys
from logger import setup_event_logger
from screen_selector import RegionSelection, ScreenSelector, enable_dpi_awareness

APP_TITLE = "LoL Auto Accept"
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "logs.txt"

PREVIEW_SIZE = (360, 200)
TEMPLATE_THUMBNAIL_SIZE = (200, 50)
SAVE_DEBOUNCE_MS = 500
MATCH_BOX_COLOR = "#22c55e"
PREVIEW_BACKGROUND = "#111111"
STATUS_COLORS: dict[MonitorStatus, str] = {
    MonitorStatus.IDLE: "#6b7280",
    MonitorStatus.MONITORING: "#2563eb",
    MonitorStatus.MATCH_DETECTED: "#d97706",
    MonitorStatus.CLICKED: "#16a34a",
}


class MainThreadDispatcher:
    """Runs functions posted from any thread on the Tk main thread.

    Tkinter is not thread-safe, so the monitoring and hotkey threads never call
    Tk themselves: they post here and the main loop executes the calls.
    """

    def __init__(self, root: tk.Tk, poll_interval_ms: int = 30) -> None:
        self._root = root
        self._poll_interval_ms = poll_interval_ms
        self._queue: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()
        self._after_id: str | None = None
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._after_id = self._root.after(self._poll_interval_ms, self._drain)

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            self._root.after_cancel(self._after_id)
            self._after_id = None

    def post(self, func: Callable[..., None], *args: Any) -> None:
        self._queue.put((func, args))

    def wrap(self, func: Callable[..., None]) -> Callable[..., None]:
        """Return a thread-safe stand-in for func that runs it on the main thread."""
        return lambda *args: self.post(func, *args)

    def _drain(self) -> None:
        try:
            while self._running:
                try:
                    func, args = self._queue.get_nowait()
                except queue.Empty:
                    break
                func(*args)
        finally:
            if self._running:
                self._after_id = self._root.after(self._poll_interval_ms, self._drain)


def render_preview(frame: Image.Image, result: MatchResult | None = None, threshold: float = 1.0) -> Image.Image:
    """Shrink a captured frame for the preview, outlining the template if it was found."""
    preview = frame.convert("RGB")  # copy: never draw on the captured frame itself
    if result is not None and result.confidence >= threshold:
        x, y = result.location
        width, height = result.size
        line_width = max(2, preview.width // 160)
        ImageDraw.Draw(preview).rectangle(
            (x, y, x + width - 1, y + height - 1), outline=MATCH_BOX_COLOR, width=line_width
        )
    preview.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
    return preview


class LolAutoAcceptApp:
    """Main window: configure detection, then start or stop monitoring."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._logger = setup_event_logger(LOG_PATH)
        self._config_manager = ConfigManager(CONFIG_PATH, APP_DIR)
        self._config, config_warning = self._load_config()

        self._dispatcher = MainThreadDispatcher(root)
        self._selector = ScreenSelector(root)
        self._hotkeys = GlobalHotkeys(
            {
                keyboard.Key.f8: self._dispatcher.wrap(self.toggle_monitoring),
                # ESC only leaves selection mode; cancel() does nothing otherwise.
                keyboard.Key.esc: self._dispatcher.wrap(self._selector.cancel),
            }
        )
        self._monitor: MatchMonitor | None = None
        self._save_after_id: str | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._template_photo: ImageTk.PhotoImage | None = None

        self._threshold_var = tk.DoubleVar(master=root, value=self._config.threshold)
        self._interval_var = tk.StringVar(master=root, value=str(self._config.check_interval_ms))

        root.title(APP_TITLE)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self._report_callback_exception

        self._build_ui()
        self._refresh_region_label()
        self._refresh_template_info()
        self._refresh_click_label()
        self._apply_idle_state()

        self._dispatcher.start()
        self._hotkeys.start()
        if config_warning:
            root.after(200, lambda: messagebox.showwarning(APP_TITLE, config_warning, parent=root))

    # ----------------------------------------------------------------- UI setup

    def _build_ui(self) -> None:
        container = ttk.Frame(self._root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        # Two columns keep the window short enough for 768 px tall screens.
        settings_column = ttk.Frame(container)
        settings_column.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        settings_column.columnconfigure(0, weight=1)
        monitor_column = ttk.Frame(container)
        monitor_column.grid(row=0, column=1, sticky="nsew")
        monitor_column.columnconfigure(0, weight=1)

        self._build_settings_column(settings_column)
        self._build_monitor_column(monitor_column)

        ttk.Label(
            container, text="F8: start / stop monitoring     ESC: cancel selection", foreground="#6b7280"
        ).grid(row=1, column=0, columnspan=2, pady=(4, 0))

    def _build_settings_column(self, column: ttk.Frame) -> None:
        area = self._add_section(column, "Detection Area", row=0)
        self._region_label = ttk.Label(area, width=40)
        self._region_label.grid(row=0, column=0, sticky="w")
        self._select_area_button = ttk.Button(area, text="Select Area", command=self._on_select_area)
        self._select_area_button.grid(row=0, column=1, sticky="e")

        template = self._add_section(column, "Template Image", row=1)
        self._template_image_label = ttk.Label(template)
        self._template_image_label.grid(row=0, column=0, sticky="w")
        self._template_info_label = ttk.Label(template)
        self._template_info_label.grid(row=1, column=0, sticky="w")
        self._capture_template_button = ttk.Button(
            template, text="Capture Template", command=self._on_capture_template
        )
        self._capture_template_button.grid(row=0, column=1, rowspan=2, sticky="e")

        click = self._add_section(column, "Click Position", row=2)
        self._click_label = ttk.Label(click)
        self._click_label.grid(row=0, column=0, sticky="w")
        self._select_click_button = ttk.Button(
            click, text="Select Click Point", command=self._on_select_click_point
        )
        self._select_click_button.grid(row=0, column=1, sticky="e")

        threshold = self._add_section(column, "Detection Threshold", row=3)
        self._threshold_scale = ttk.Scale(
            threshold,
            from_=THRESHOLD_MIN,
            to=THRESHOLD_MAX,
            variable=self._threshold_var,
            command=self._on_threshold_moved,
        )
        self._threshold_scale.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._threshold_value_label = ttk.Label(threshold, width=5, anchor="e")
        self._threshold_value_label.grid(row=0, column=1, sticky="e")
        self._update_threshold_label()

        interval = self._add_section(column, "Check Interval", row=4)
        interval.columnconfigure(0, weight=0)
        interval.columnconfigure(1, weight=1)  # keeps "ms" right next to the spinbox
        self._interval_spinbox = ttk.Spinbox(
            interval,
            from_=CHECK_INTERVAL_MIN_MS,
            to=CHECK_INTERVAL_MAX_MS,
            increment=50,
            width=8,
            textvariable=self._interval_var,
        )
        self._interval_spinbox.grid(row=0, column=0, sticky="w")
        ttk.Label(interval, text="ms").grid(row=0, column=1, sticky="w", padx=(6, 0))
        self._interval_var.trace_add("write", lambda *_: self._schedule_save())

        buttons = ttk.Frame(column)
        buttons.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        buttons.columnconfigure((0, 1), weight=1, uniform="buttons")
        self._start_button = ttk.Button(buttons, text="Start Monitoring", command=self.start_monitoring)
        self._start_button.grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=4)
        self._stop_button = ttk.Button(buttons, text="Stop Monitoring", command=self.stop_monitoring)
        self._stop_button.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=4)

    def _build_monitor_column(self, column: ttk.Frame) -> None:
        status = ttk.Frame(column, padding=(2, 6, 2, 0))
        status.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, text="Status:").grid(row=0, column=0, sticky="w")
        self._status_label = ttk.Label(status, font=("Segoe UI", 10, "bold"))
        self._status_label.grid(row=0, column=1, sticky="w", padx=(6, 0))
        self._confidence_label = ttk.Label(status)
        self._confidence_label.grid(row=0, column=2, sticky="e")

        preview = self._add_section(column, "Preview", row=1)
        preview_box = tk.Frame(
            preview, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], background=PREVIEW_BACKGROUND
        )
        preview_box.grid(row=0, column=0)
        preview_box.grid_propagate(False)
        self._preview_label = tk.Label(
            preview_box, text="No preview yet", background=PREVIEW_BACKGROUND, foreground="#9ca3af"
        )
        self._preview_label.place(relx=0.5, rely=0.5, anchor="center")

    @staticmethod
    def _add_section(parent: ttk.Frame, title: str, row: int) -> ttk.LabelFrame:
        section = ttk.LabelFrame(parent, text=title, padding=(10, 6))
        section.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        section.columnconfigure(0, weight=1)
        return section

    # ------------------------------------------------------------ config & labels

    def _load_config(self) -> tuple[AppConfig, str | None]:
        try:
            return self._config_manager.load(), None
        except ConfigError as exc:
            self._logger.error("Error: %s", exc)
            return AppConfig(), f"{exc}\n\nDefault settings are used; the file is overwritten on the next save."

    def _template_path(self) -> Path:
        return self._config_manager.resolve_path(self._config.template_path)

    def _refresh_region_label(self) -> None:
        region = self._config.detection_region
        self._region_label.configure(text=str(region) if region else "Not selected")

    def _refresh_click_label(self) -> None:
        point = self._config.click_position
        self._click_label.configure(text=str(point) if point else "Not selected")

    def _refresh_template_info(self) -> None:
        path = self._template_path()
        self._template_photo = None
        self._template_image_label.configure(image="")
        if not path.is_file():
            self._template_info_label.configure(text=f"Not captured ({self._config.template_path})")
            return
        try:
            with Image.open(path) as image:
                width, height = image.size
                thumbnail = image.convert("RGB")
        except OSError as exc:
            self._template_info_label.configure(text=f"Unreadable template: {exc}")
            return
        thumbnail.thumbnail(TEMPLATE_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        self._template_photo = ImageTk.PhotoImage(thumbnail, master=self._root)
        self._template_image_label.configure(image=self._template_photo)
        self._template_info_label.configure(text=f"{self._config.template_path}  ({width}x{height})")

    def _on_threshold_moved(self, value: str) -> None:
        rounded = clamp_threshold(float(value))
        if abs(self._threshold_var.get() - rounded) > 1e-9:
            self._threshold_var.set(rounded)  # snap the slider to 0.01 steps
        self._update_threshold_label()
        self._schedule_save()

    def _update_threshold_label(self) -> None:
        self._threshold_value_label.configure(text=f"{clamp_threshold(self._threshold_var.get()):.2f}")

    def _read_interval(self) -> int | None:
        try:
            value = int(self._interval_var.get().strip())
        except ValueError:
            return None
        return value if CHECK_INTERVAL_MIN_MS <= value <= CHECK_INTERVAL_MAX_MS else None

    def _sync_config_from_controls(self) -> bool:
        """Copy slider/spinbox values into the config. Returns False if the interval is invalid."""
        self._config.threshold = clamp_threshold(self._threshold_var.get())
        interval = self._read_interval()
        if interval is None:
            return False
        self._config.check_interval_ms = interval
        return True

    def _schedule_save(self) -> None:
        if self._save_after_id is not None:
            self._root.after_cancel(self._save_after_id)
        self._save_after_id = self._root.after(SAVE_DEBOUNCE_MS, self._save_from_controls)

    def _save_from_controls(self) -> None:
        self._save_after_id = None
        self._sync_config_from_controls()
        self._save_config()

    def _save_config(self, show_errors: bool = True) -> None:
        try:
            self._config_manager.save(self._config)
        except OSError as exc:
            self._logger.error("Error: could not save settings: %s", exc)
            if show_errors:
                messagebox.showerror("Could not save settings", f"{CONFIG_PATH}\n\n{exc}", parent=self._root)

    # ---------------------------------------------------------------- selection

    def _on_select_area(self) -> None:
        self._selector.select_region("Drag to select the detection area", self._on_area_selected)

    def _on_area_selected(self, selection: RegionSelection | None) -> None:
        if selection is None:
            return
        self._config.detection_region = selection.region
        self._logger.info("Detection area set: %s", selection.region)
        self._refresh_region_label()
        self._show_preview(render_preview(selection.image))
        self._save_config()

    def _on_capture_template(self) -> None:
        self._selector.select_region("Drag a tight box around the ACCEPT button", self._on_template_selected)

    def _on_template_selected(self, selection: RegionSelection | None) -> None:
        if selection is None:
            return
        path = self._template_path()
        try:
            TemplateMatcher(selection.image)  # rejects flat, featureless selections
            save_template(selection.image, path)
        except TemplateError as exc:
            messagebox.showerror("Invalid template", str(exc), parent=self._root)
            return
        except OSError as exc:
            messagebox.showerror("Could not save template", f"{path}\n\n{exc}", parent=self._root)
            return

        width, height = selection.image.size
        self._logger.info("Template captured %dx%d saved to %s", width, height, self._config.template_path)
        self._refresh_template_info()
        self._save_config()

        region = self._config.detection_region
        if region is not None and (width > region.width or height > region.height):
            messagebox.showwarning(
                APP_TITLE,
                "The template is larger than the detection area.\n"
                "Select a larger detection area before starting.",
                parent=self._root,
            )

    def _on_select_click_point(self) -> None:
        self._selector.select_point("Click the point to press when a match is found", self._on_click_point_selected)

    def _on_click_point_selected(self, point: Point | None) -> None:
        if point is None:
            return
        self._config.click_position = point
        self._logger.info("Click position set: %s", point)
        self._refresh_click_label()
        self._save_config()

    # --------------------------------------------------------------- monitoring

    def toggle_monitoring(self) -> None:
        if self._monitor is None:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    def start_monitoring(self) -> None:
        if self._monitor is not None or self._selector.is_active:
            return
        if not self._sync_config_from_controls():
            messagebox.showerror(
                "Invalid check interval",
                f"The check interval must be a whole number between "
                f"{CHECK_INTERVAL_MIN_MS} and {CHECK_INTERVAL_MAX_MS} ms.",
                parent=self._root,
            )
            return
        try:
            settings, matcher = build_monitor_settings(self._config, self._template_path(), pyautogui.size())
        except MonitorSetupError as exc:
            messagebox.showerror("Cannot start monitoring", str(exc), parent=self._root)
            return
        self._save_config()

        def on_frame(frame: Image.Image, result: MatchResult) -> None:
            # Runs on the monitoring thread: image work happens here, Tk work on the main thread.
            preview = render_preview(frame, result, settings.threshold)
            self._dispatcher.post(self._show_live_frame, preview, result.confidence)

        callbacks = MonitorCallbacks(
            on_status=self._dispatcher.wrap(self._set_status),
            on_frame=on_frame,
            on_error=self._dispatcher.wrap(self._on_monitor_error),
            on_stopped=self._dispatcher.wrap(self._on_monitor_stopped),
        )
        self._monitor = MatchMonitor(settings, matcher, callbacks, self._logger)
        self._set_monitoring_controls(monitoring=True)
        self._monitor.start()

    def stop_monitoring(self) -> None:
        if self._monitor is not None:
            self._monitor.stop()  # the UI resets when the thread reports it has stopped

    def _show_live_frame(self, preview: Image.Image, confidence: float) -> None:
        if self._monitor is None:
            return
        self._show_preview(preview)
        self._confidence_label.configure(text=f"Confidence: {confidence:.2f}")

    def _show_preview(self, preview: Image.Image) -> None:
        self._preview_photo = ImageTk.PhotoImage(preview, master=self._root)
        self._preview_label.configure(image=self._preview_photo, text="")

    def _set_status(self, status: MonitorStatus) -> None:
        self._status_label.configure(text=status.value, foreground=STATUS_COLORS[status])

    def _set_monitoring_controls(self, monitoring: bool) -> None:
        settings_state = ["disabled"] if monitoring else ["!disabled"]
        for widget in (
            self._select_area_button,
            self._capture_template_button,
            self._select_click_button,
            self._threshold_scale,
            self._interval_spinbox,
        ):
            widget.state(settings_state)
        self._start_button.state(["disabled"] if monitoring else ["!disabled"])
        self._stop_button.state(["!disabled"] if monitoring else ["disabled"])

    def _apply_idle_state(self) -> None:
        self._set_status(MonitorStatus.IDLE)
        self._confidence_label.configure(text="Confidence: -")
        self._set_monitoring_controls(monitoring=False)

    def _on_monitor_error(self, message: str) -> None:
        self._apply_idle_state()
        messagebox.showerror("Monitoring error", message, parent=self._root)

    def _on_monitor_stopped(self) -> None:
        self._monitor = None
        self._apply_idle_state()

    # ---------------------------------------------------------------- lifecycle

    def _report_callback_exception(
        self, exc_type: type[BaseException], exc_value: BaseException, exc_traceback: TracebackType | None
    ) -> None:
        self._logger.error("Unexpected error: %s", exc_value, exc_info=(exc_type, exc_value, exc_traceback))
        messagebox.showerror("Unexpected error", f"{exc_type.__name__}: {exc_value}", parent=self._root)

    def close(self) -> None:
        self._hotkeys.stop()
        self._selector.cancel()
        if self._monitor is not None:
            self._monitor.stop()
        if self._save_after_id is not None:
            self._root.after_cancel(self._save_after_id)
            self._save_after_id = None
        self._sync_config_from_controls()
        self._save_config(show_errors=False)
        self._dispatcher.stop()
        self._logger.info("Application closed")
        self._root.destroy()


def main() -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    LolAutoAcceptApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
