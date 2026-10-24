"""System-wide hotkeys that work while another window (e.g. the game client) has focus."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from pynput import keyboard

KeyType: TypeAlias = keyboard.Key | keyboard.KeyCode
HotkeyCallback: TypeAlias = Callable[[], None]


class GlobalHotkeys:
    """Calls a function when one of the bound keys is pressed anywhere in the system.

    Callbacks run on the pynput listener thread, so they must hand work over to
    the GUI thread before touching Tk. Keys are not suppressed: other
    applications still receive them. Holding a key down fires only once.
    """

    def __init__(self, bindings: dict[KeyType, HotkeyCallback]) -> None:
        self._bindings = dict(bindings)
        self._held_keys: set[KeyType] = set()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key: KeyType | None) -> None:
        if key is None or key not in self._bindings or key in self._held_keys:
            return
        self._held_keys.add(key)
        self._bindings[key]()

    def _on_release(self, key: KeyType | None) -> None:
        self._held_keys.discard(key)
