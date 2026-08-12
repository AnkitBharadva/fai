"""Tests for comment tree threading and CSV creation."""

from pathlib import Path
import tempfile
from src.comments import CommentExtractor
from src.schemas import CommentRecord


def test_build_threaded_comments():
    comments = [
        CommentRecord(comment_id="c1", parent_id=None, text="Top level comment 1", is_reply=False),
        CommentRecord(comment_id="c2", parent_id="c1", text="Reply to c1", is_reply=True),
        CommentRecord(comment_id="c3", parent_id=None, text="Top level comment 2", is_reply=False),
    ]

    threaded = CommentExtractor.build_threaded_comments(comments)
    assert len(threaded) == 2

    # Check first top level comment
    t1 = next(t for t in threaded if t.comment.comment_id == "c1")
    assert len(t1.replies) == 1
    assert t1.replies[0].comment.comment_id == "c2"

    # Check second top level comment
    t2 = next(t for t in threaded if t.comment.comment_id == "c3")
    assert len(t2.replies) == 0


def test_save_comments():
    comments = [
        CommentRecord(comment_id="c1", parent_id=None, text="Test text", author="UserA", is_reply=False)
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        extractor = CommentExtractor()
        extractor.save_comments(comments, out_dir)

        assert (out_dir / "comments.json").exists()
        assert (out_dir / "comments_threaded.json").exists()
        assert not (out_dir / "comments.csv").exists()
