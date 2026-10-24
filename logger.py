"""Event logging to logs.txt (e.g. "22:16:32 Clicked x=960 y=620")."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "lol_auto_accept"


def setup_event_logger(log_path: Path) -> logging.Logger:
    """Return the application logger, writing timestamped lines to log_path.

    logging.Logger is thread-safe, so the monitoring thread and the GUI thread
    can both write to it.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        # Lines only carry the time of day, so mark where each run begins.
        logger.info("Application started (%s)", datetime.now().strftime("%Y-%m-%d"))

    return logger
