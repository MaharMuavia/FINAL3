"""Logging system for DataVerse AI.

This module configures a rotating file logger and a console handler.
"""
from __future__ import annotations

import logging
import logging.handlers
import json
from pathlib import Path

from .config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def get_logger(name: str) -> logging.Logger:
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    _logger = logging.getLogger(name)
    _logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if not _logger.handlers:
        # File handler (rotating)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "dataverse_backend.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

        # Console handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter("%(levelname)s | %(name)s | %(message)s")
        console_handler.setFormatter(console_formatter)

        _logger.addHandler(file_handler)
        _logger.addHandler(console_handler)
        _logger.propagate = False

    return _logger


logger = get_logger("dataverse_backend")
