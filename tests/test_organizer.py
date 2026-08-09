"""Tests for directory organization and per-video output structure."""

from pathlib import Path
import tempfile
from src.organizer import FolderOrganizer


def test_folder_organizer_structure():
    with tempfile.TemporaryDirectory() as tmpdir:
        organizer = FolderOrganizer(tmpdir)
        dirs = organizer.setup_video_dirs("UC12345", "vid999")

        assert dirs["video"].exists()
        assert dirs["audio"].exists()
        assert dirs["frames"].exists()
        assert dirs["metadata"].exists()
        assert dirs["transcript"].exists()
        assert dirs["comments"].exists()
        assert dirs["thumbnails"].exists()

        status_file = organizer.write_status("UC12345", "vid999", {"status": "success"})
        assert status_file.exists()
