"""Configuration loader and management module."""

from pathlib import Path
from typing import Any, Dict, Optional
import yaml


DEFAULT_CONFIG: Dict[str, Any] = {
    "data_dir": "./data",
    "db_path": "manifest.db",
    "log_dir": "./logs",
    "workers": 2,
    "rate_limit_delay": 1.5,
    "retry_count": 3,
    "download_video": True,
    "audio_only": False,
    "quality_ceiling": "1080p",
    "download_thumbnail": True,
    "cookies_file": None,
    "max_comments": None,
    "subtitle_languages": ["en", "auto"],
    "prefer_manual_subtitles": True,
    "log_level": "INFO",
}


def load_config(config_path: Optional[str] = "config.yaml") -> Dict[str, Any]:
    """Load configuration from a YAML file, falling back to defaults if missing."""
    config = DEFAULT_CONFIG.copy()

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
            config.update(file_cfg)

    return config


def merge_config_with_cli(
    base_config: Dict[str, Any], **cli_args: Any
) -> Dict[str, Any]:
    """Merge CLI arguments into base configuration, ignoring None CLI values."""
    merged = base_config.copy()
    for key, val in cli_args.items():
        if val is not None:
            merged[key] = val
    return merged
