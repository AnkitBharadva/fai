"""Metadata extraction module using yt-dlp Python API."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import yt_dlp

from src.schemas import ChapterRecord, VideoMetadata


class MetadataExtractor:
    """Extracts and parses video metadata using yt-dlp."""

    def __init__(self, cookies_file: Optional[str] = None):
        self.cookies_file = cookies_file

    def _get_ydl_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }
        if self.cookies_file and Path(self.cookies_file).exists():
            opts["cookiefile"] = self.cookies_file
        return opts

    def extract_metadata(self, video_url_or_id: str) -> VideoMetadata:
        """Extract full metadata for a video and validate against Pydantic model."""
        if not video_url_or_id.startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_url_or_id}"
        else:
            url = video_url_or_id

        opts = self._get_ydl_opts()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise ValueError(f"Could not extract metadata for {url}")

            # If playlist/multi-entry came back unexpectedly, pick first entry or raise
            if "entries" in info:
                entries = list(info["entries"])
                if not entries:
                    raise ValueError(f"No video entries found for {url}")
                info = entries[0]

        # Extract chapters
        chapters = []
        raw_chapters = info.get("chapters") or []
        for ch in raw_chapters:
            chapters.append(
                ChapterRecord(
                    start_time=ch.get("start_time", 0.0),
                    end_time=ch.get("end_time", 0.0),
                    title=ch.get("title", ""),
                )
            )

        # Subtitles languages available
        sub_langs = set()
        if info.get("subtitles"):
            sub_langs.update(info["subtitles"].keys())
        if info.get("automatic_captions"):
            sub_langs.update(info["automatic_captions"].keys())

        # Construct Pydantic model
        metadata = VideoMetadata(
            video_id=info.get("id", ""),
            title=info.get("title", ""),
            channel_id=info.get("channel_id") or info.get("uploader_id") or "unknown_channel",
            channel_name=info.get("channel") or info.get("uploader") or "Unknown Channel",
            upload_date=info.get("upload_date"),
            duration=info.get("duration"),
            view_count=info.get("view_count"),
            like_count=info.get("like_count"),
            comment_count=info.get("comment_count"),
            tags=info.get("tags") or [],
            categories=info.get("categories") or [],
            language=info.get("language"),
            availability=info.get("availability"),
            is_live=bool(info.get("is_live")),
            was_live=bool(info.get("was_live")),
            chapters=chapters,
            thumbnail_url=info.get("thumbnail"),
            available_subtitle_languages=sorted(list(sub_langs)),
            age_limit=info.get("age_limit", 0),
            license=info.get("license"),
            original_url=url,
            description=info.get("description") or "",
            extra_info={
                "webpage_url": info.get("webpage_url"),
                "fps": info.get("fps"),
                "resolution": info.get("resolution"),
            },
        )
        return metadata

    def save_metadata(self, metadata: VideoMetadata, metadata_dir: Path) -> None:
        """Save video_metadata.json and description.txt to destination folder."""
        metadata_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata JSON
        json_path = metadata_dir / "video_metadata.json"
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(metadata.model_dump_json(indent=2))

        # Save description TXT
        desc_path = metadata_dir / "description.txt"
        with open(desc_path, "w", encoding="utf-8") as f:
            f.write(metadata.description or "")

    def expand_url(self, url: str) -> List[str]:
        """Expand playlist, channel, or video URL into list of canonical video IDs."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        if self.cookies_file and Path(self.cookies_file).exists():
            opts["cookiefile"] = self.cookies_file

        video_ids = []
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []

            if "entries" in info:
                for entry in info["entries"]:
                    if entry and "id" in entry:
                        video_ids.append(entry["id"])
            elif "id" in info:
                video_ids.append(info["id"])

        return video_ids
