"""Application-wide logging for Schedule 1 Auto Clicker."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import threading


APP_NAME = "Schedule1AutoClicker"
LOG_FILE_NAME = "Schedule1AutoClicker.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s"
_LOGGER_NAMESPACE = "schedule1_auto_clicker"
_configured = False
_log_file: Path | None = None


def _choose_log_directory() -> Path:
    candidates = []
    if local_app_data := os.getenv("LOCALAPPDATA"):
        candidates.append(Path(local_app_data) / APP_NAME / "logs")
    candidates.extend(
        (
            Path.home() / "AppData" / "Local" / APP_NAME / "logs",
            Path(tempfile.gettempdir()) / APP_NAME / "logs",
        )
    )

    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return directory
        except OSError:
            continue
    raise OSError("No writable logging directory is available")


def setup_logging() -> Path | None:
    """Configure all application loggers once and return the log file path."""
    global _configured, _log_file
    if _configured:
        return _log_file

    logger = logging.getLogger(_LOGGER_NAMESPACE)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT)

    try:
        _log_file = _choose_log_directory() / LOG_FILE_NAME
        file_handler = RotatingFileHandler(
            _log_file,
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as error:
        _log_file = None
        if sys.stderr is not None:
            print(f"Unable to create application log: {error}", file=sys.stderr)

    if sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    _configured = True
    logger.info("Logging initialized%s", f" at {_log_file}" if _log_file else "")
    return _log_file


def get_logger(name: str | None = None) -> logging.Logger:
    suffix = f".{name}" if name else ""
    return logging.getLogger(f"{_LOGGER_NAMESPACE}{suffix}")


def get_log_file() -> Path | None:
    return _log_file


def install_exception_hooks() -> None:
    """Log uncaught exceptions from both the main thread and worker threads."""
    logger = get_logger("exceptions")
    original_sys_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            original_sys_hook(exc_type, exc_value, traceback)
            return
        logger.critical(
            "Uncaught main-thread exception",
            exc_info=(exc_type, exc_value, traceback),
        )

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "Uncaught exception in thread %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
    logger.debug("Global exception hooks installed")
