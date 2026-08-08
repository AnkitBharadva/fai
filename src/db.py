"""SQLite database manifest for tracking processing status and resumability."""

from datetime import datetime, timezone
import sqlite3
from typing import List, Optional
from src.schemas import ManifestRecord


from contextlib import contextmanager


class ManifestDB:
    """SQLite database helper for persistent video status manifest."""

    def __init__(self, db_path: str = "manifest.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manifest (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    status TEXT NOT NULL,
                    last_attempt_at TEXT,
                    completed_at TEXT,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT
                )
                """
            )
            conn.commit()

    def register_video(self, video_id: str, channel_id: Optional[str] = "unknown_channel") -> ManifestRecord:
        """Register video in manifest if not already present."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manifest WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                return ManifestRecord(**dict(row))

            now_str = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO manifest (video_id, channel_id, status, last_attempt_at, retry_count)
                VALUES (?, ?, 'pending', ?, 0)
                """,
                (video_id, channel_id, now_str),
            )
            conn.commit()
            return ManifestRecord(
                video_id=video_id, channel_id=channel_id, status="pending", last_attempt_at=now_str
            )

    def update_status(
        self,
        video_id: str,
        status: str,
        channel_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update processing status for a video."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retry_count, channel_id FROM manifest WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            retry_count = (row["retry_count"] if row else 0) + (1 if status == "failed" else 0)
            existing_channel = row["channel_id"] if row else "unknown_channel"
            final_channel = channel_id or existing_channel or "unknown_channel"

            completed_at = now_str if status == "done" else None

            cursor.execute(
                """
                INSERT INTO manifest (video_id, channel_id, status, last_attempt_at, completed_at, retry_count, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    status=excluded.status,
                    channel_id=COALESCE(excluded.channel_id, manifest.channel_id),
                    last_attempt_at=excluded.last_attempt_at,
                    completed_at=COALESCE(excluded.completed_at, manifest.completed_at),
                    retry_count=excluded.retry_count,
                    error_message=excluded.error_message
                """,
                (video_id, final_channel, status, now_str, completed_at, retry_count, error_message),
            )
            conn.commit()

    def get_record(self, video_id: str) -> Optional[ManifestRecord]:
        """Fetch manifest record for a video."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manifest WHERE video_id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                return ManifestRecord(**dict(row))
            return None

    def is_completed(self, video_id: str) -> bool:
        """Check if video was already successfully processed."""
        record = self.get_record(video_id)
        return record is not None and record.status == "done"

    def get_all(self) -> List[ManifestRecord]:
        """Fetch all manifest records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manifest")
            rows = cursor.fetchall()
            return [ManifestRecord(**dict(r)) for r in rows]

    def get_failed(self) -> List[ManifestRecord]:
        """Fetch all failed manifest records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manifest WHERE status = 'failed'")
            rows = cursor.fetchall()
            return [ManifestRecord(**dict(r)) for r in rows]
