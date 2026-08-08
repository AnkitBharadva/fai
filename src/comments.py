"""Comment extraction, formatting, threading, and CSV serialization module."""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import yt_dlp

from src.schemas import CommentRecord, CommentThread


class CommentExtractor:
    """Extracts YouTube comment threads with full metadata using yt-dlp."""

    def __init__(self, cookies_file: Optional[str] = None):
        self.cookies_file = cookies_file

    def extract_comments(
        self, video_url: str, max_comments: Optional[int] = None
    ) -> List[CommentRecord]:
        """Extract comments and replies for a YouTube video."""
        max_str = str(max_comments) if max_comments is not None else "all"

        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "getcomments": True,
            "extractor_args": {
                "youtube": {
                    "max_comments": [max_str, "all", "all", "all"]
                }
            },
        }
        if self.cookies_file and Path(self.cookies_file).exists():
            opts["cookiefile"] = self.cookies_file

        records: List[CommentRecord] = []
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    return []

                raw_comments = info.get("comments") or []
                for c in raw_comments:
                    if not c or not isinstance(c, dict):
                        continue

                    parent_id = c.get("parent")
                    if parent_id == "root":
                        parent_id = None

                    is_reply = parent_id is not None

                    record = CommentRecord(
                        comment_id=c.get("id") or "",
                        parent_id=parent_id,
                        author=c.get("author") or "Anonymous",
                        author_channel_id=c.get("author_id"),
                        text=c.get("text") or "",
                        like_count=c.get("like_count") or 0,
                        published_time=str(c.get("timestamp") or c.get("time_text") or ""),
                        is_favorited=bool(c.get("is_favorited", False)),
                        reply_count=c.get("reply_count") or 0,
                        is_reply=is_reply,
                    )
                    records.append(record)

        except Exception as e:
            # Handle comments disabled or network error gracefully
            pass

        return records

    @staticmethod
    def build_threaded_comments(records: List[CommentRecord]) -> List[CommentThread]:
        """Build nested hierarchy tree of comments and replies."""
        threads_by_id: Dict[str, CommentThread] = {}
        top_level: List[CommentThread] = []

        # Create all nodes
        for r in records:
            threads_by_id[r.comment_id] = CommentThread(comment=r, replies=[])

        # Attach replies to parents
        for r in records:
            node = threads_by_id[r.comment_id]
            if r.parent_id and r.parent_id in threads_by_id:
                threads_by_id[r.parent_id].replies.append(node)
            else:
                top_level.append(node)

        return top_level

    def save_comments(self, records: List[CommentRecord], comments_dir: Path) -> None:
        """Save comments to comments.json, comments_threaded.json, and comments.csv."""
        comments_dir.mkdir(parents=True, exist_ok=True)

        # 1. comments.json
        json_path = comments_dir / "comments.json"
        dict_records = [r.model_dump() for r in records]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dict_records, f, indent=2, ensure_ascii=False)

        # 2. comments_threaded.json
        threaded = self.build_threaded_comments(records)
        threaded_path = comments_dir / "comments_threaded.json"
        dict_threaded = [t.model_dump() for t in threaded]
        with open(threaded_path, "w", encoding="utf-8") as f:
            json.dump(dict_threaded, f, indent=2, ensure_ascii=False)

        # 3. comments.csv
        csv_path = comments_dir / "comments.csv"
        fieldnames = [
            "comment_id",
            "parent_id",
            "is_reply",
            "author",
            "author_channel_id",
            "like_count",
            "reply_count",
            "published_time",
            "text",
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow(
                    {
                        "comment_id": r.comment_id,
                        "parent_id": r.parent_id or "",
                        "is_reply": r.is_reply,
                        "author": r.author,
                        "author_channel_id": r.author_channel_id or "",
                        "like_count": r.like_count,
                        "reply_count": r.reply_count,
                        "published_time": r.published_time or "",
                        "text": r.text,
                    }
                )
