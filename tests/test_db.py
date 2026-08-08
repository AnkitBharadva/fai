"""Tests for SQLite manifest database tracking and resumability."""

from pathlib import Path
import tempfile
from src.db import ManifestDB


def test_manifest_db_workflow():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_manifest.db")
        db = ManifestDB(db_path)

        # 1. Register video
        record = db.register_video("vid123", "channelA")
        assert record.status == "pending"
        assert db.is_completed("vid123") is False

        # 2. Update status to in_progress
        db.update_status("vid123", "in_progress", channel_id="channelA")
        rec2 = db.get_record("vid123")
        assert rec2.status == "in_progress"

        # 3. Update status to done
        db.update_status("vid123", "done", channel_id="channelA")
        assert db.is_completed("vid123") is True

        # 4. Failed tracking
        db.update_status("vid456", "failed", channel_id="channelB", error_message="Network error")
        failed = db.get_failed()
        assert len(failed) == 1
        assert failed[0].video_id == "vid456"
        assert failed[0].retry_count == 1
