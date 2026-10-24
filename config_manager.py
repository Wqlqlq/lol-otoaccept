"""Application settings: data types and JSON persistence (config.json)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TEMPLATE_PATH = "assets/accept_template.png"
DEFAULT_THRESHOLD = 0.90
DEFAULT_CHECK_INTERVAL_MS = 300

THRESHOLD_MIN = 0.50
THRESHOLD_MAX = 1.00
CHECK_INTERVAL_MIN_MS = 50
CHECK_INTERVAL_MAX_MS = 5000


class ConfigError(Exception):
    """Raised when config.json exists but cannot be read or parsed."""


@dataclass(frozen=True)
class Point:
    """A screen coordinate in physical pixels."""

    x: int
    y: int

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: Any) -> Point | None:
        if not isinstance(data, dict):
            return None
        try:
            return cls(x=int(data["x"]), y=int(data["y"]))
        except (KeyError, TypeError, ValueError):
            return None

    def __str__(self) -> str:
        return f"x={self.x}  y={self.y}"


@dataclass(frozen=True)
class Region:
    """A rectangular screen area in physical pixels."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height), the format pyautogui expects."""
        return (self.x, self.y, self.width, self.height)

    def fits_inside(self, screen_width: int, screen_height: int) -> bool:
        return self.x >= 0 and self.y >= 0 and self.right <= screen_width and self.bottom <= screen_height

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Any) -> Region | None:
        if not isinstance(data, dict):
            return None
        try:
            region = cls(
                x=int(data["x"]),
                y=int(data["y"]),
                width=int(data["width"]),
                height=int(data["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if region.width <= 0 or region.height <= 0:
            return None
        return region

    def __str__(self) -> str:
        return f"x={self.x}  y={self.y}  width={self.width}  height={self.height}"


def clamp_threshold(value: float) -> float:
    return round(min(max(float(value), THRESHOLD_MIN), THRESHOLD_MAX), 2)


def clamp_check_interval(value: int) -> int:
    return min(max(int(value), CHECK_INTERVAL_MIN_MS), CHECK_INTERVAL_MAX_MS)


@dataclass
class AppConfig:
    """Everything the user configures in the main window."""

    detection_region: Region | None = None
    click_position: Point | None = None
    threshold: float = DEFAULT_THRESHOLD
    check_interval_ms: int = DEFAULT_CHECK_INTERVAL_MS
    template_path: str = DEFAULT_TEMPLATE_PATH

    def to_dict(self) -> dict[str, Any]:
        return {
            "detection_region": self.detection_region.to_dict() if self.detection_region else None,
            "click_position": self.click_position.to_dict() if self.click_position else None,
            "threshold": self.threshold,
            "check_interval_ms": self.check_interval_ms,
            "template_path": self.template_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        """Build a config from parsed JSON, falling back to defaults for invalid fields."""
        try:
            threshold = clamp_threshold(data.get("threshold", DEFAULT_THRESHOLD))
        except (TypeError, ValueError):
            threshold = DEFAULT_THRESHOLD
        try:
            interval = clamp_check_interval(data.get("check_interval_ms", DEFAULT_CHECK_INTERVAL_MS))
        except (TypeError, ValueError):
            interval = DEFAULT_CHECK_INTERVAL_MS
        template_path = data.get("template_path")
        if not isinstance(template_path, str) or not template_path.strip():
            template_path = DEFAULT_TEMPLATE_PATH
        return cls(
            detection_region=Region.from_dict(data.get("detection_region")),
            click_position=Point.from_dict(data.get("click_position")),
            threshold=threshold,
            check_interval_ms=interval,
            template_path=template_path,
        )


class ConfigManager:
    """Loads and saves AppConfig as JSON. Relative paths resolve against base_dir."""

    def __init__(self, config_path: Path, base_dir: Path) -> None:
        self._config_path = config_path
        self._base_dir = base_dir

    @property
    def config_path(self) -> Path:
        return self._config_path

    def resolve_path(self, path: str) -> Path:
        """Turn a path stored in the config into an absolute path."""
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self._base_dir / candidate

    def load(self) -> AppConfig:
        """Return the saved config, or defaults if no config file exists yet."""
        if not self._config_path.exists():
            return AppConfig()
        try:
            with self._config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Could not read {self._config_path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{self._config_path.name} must contain a JSON object.")
        return AppConfig.from_dict(data)

    def save(self, config: AppConfig) -> None:
        """Write the config atomically so a crash never leaves a half-written file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._config_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(config.to_dict(), file, indent=2)
            file.write("\n")
        os.replace(temp_path, self._config_path)
