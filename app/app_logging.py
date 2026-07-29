from __future__ import annotations

"""Small, file-based diagnostics shared by the desktop application."""

import logging
from logging.handlers import RotatingFileHandler

from runtime_paths import get_logs_dir


LOGGER_NAME = "kolconnect"
_CONFIGURED = False


def get_logger() -> logging.Logger:
    """Return the process-wide logger without exposing configuration secrets."""
    global _CONFIGURED
    logger = logging.getLogger(LOGGER_NAME)
    if _CONFIGURED:
        return logger

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logs_dir = get_logs_dir()
    for filename, level in (("kolconnect.log", logging.INFO), ("error.log", logging.ERROR)):
        handler = RotatingFileHandler(
            logs_dir / filename, encoding="utf-8", maxBytes=2 * 1024 * 1024, backupCount=3
        )
        handler.setFormatter(formatter)
        handler.setLevel(level)
        logger.addHandler(handler)
    _CONFIGURED = True
    return logger


def log_event(category: str, message: str, *, level: int = logging.INFO) -> None:
    get_logger().log(level, "[%s] %s", category, message)


def log_error(category: str, message: str, exc: BaseException | None = None) -> None:
    if exc is None:
        log_event(category, message, level=logging.ERROR)
        return
    get_logger().error("[%s] %s: %s", category, message, exc)
