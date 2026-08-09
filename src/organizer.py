"""Directory manager and file layout organizer."""

import json
from pathlib import Path
from typing import Any, Dict
from src.utils import sanitize_filename


class FolderOrganizer:
    """Manages creation and structure of per-video archive folders."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir).resolve()

    def get_channel_dir(self, channel_id: str) -> Path:
        """Get path to channel folder."""
        clean_channel = sanitize_filename(channel_id or "unknown_channel")
        return self.data_dir / clean_channel

    def get_video_dir(self, channel_id: str, video_id: str) -> Path:
        """Get path to specific video base folder."""
        return self.get_channel_dir(channel_id) / video_id

    def setup_video_dirs(self, channel_id: str, video_id: str) -> Dict[str, Path]:
        """Create and return subdirectories for a video."""
        base_dir = self.get_video_dir(channel_id, video_id)
        dirs = {
            "base": base_dir,
            "video": base_dir / "video",
            "metadata": base_dir / "metadata",
            "transcript": base_dir / "transcript",
            "comments": base_dir / "comments",
            "thumbnails": base_dir / "thumbnails",
            "frames": base_dir / "frames",
            "audio": base_dir / "audio",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs

    def write_status(self, channel_id: str, video_id: str, status_data: Dict[str, Any]) -> Path:
        """Write per-video status.json file."""
        base_dir = self.get_video_dir(channel_id, video_id)
        base_dir.mkdir(parents=True, exist_ok=True)
        status_file = base_dir / "status.json"
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
        return status_file
