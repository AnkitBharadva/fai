"""Utility functions for URL canonicalization, string sanitization, and logging setup."""

import logging
from logging.handlers import RotatingFileHandler
import os
import re
from pathlib import Path
from typing import List, Optional
from rich.logging import RichHandler


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract canonical 11-character YouTube video ID, returning None if invalid or a Channel ID."""
    url_or_id = url_or_id.strip()
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id

    patterns = [
        r"(?:v=|\/v\/|embed\/|shorts\/|youtu\.be\/|\/e\/|watch\?.*v=)([a-zA-Z0-9_-]{11})",
        r"youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    return None


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Sanitize string to be safe for directory/file names across OSes."""
    # Replace illegal characters with underscore
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", name)
    # Strip leading/trailing dots and spaces
    sanitized = sanitized.strip(". ")
    # Replace multiple spaces/underscores
    sanitized = re.sub(r"[\s_]+", "_", sanitized)
    if not sanitized:
        sanitized = "unnamed"
    return sanitized[:max_length]


def setup_logger(log_dir: str = "./logs", level_name: str = "INFO") -> logging.Logger:
    """Set up rotating file logger and rich console logger."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "scraper.log"

    logger = logging.getLogger("yt_scraper")
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))

    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler (Rich)
    rich_handler = RichHandler(rich_tracebacks=True, show_time=True, show_path=False)
    rich_handler.setLevel(logger.level)
    logger.addHandler(rich_handler)

    # Rotating File Handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logger.level)
    logger.addHandler(file_handler)

    return logger
