"""Tests for utility functions: video ID extraction and filename sanitization."""

from src.utils import extract_video_id, sanitize_filename


def test_extract_video_id_raw():
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_standard_url():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_short_url():
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_shorts_url():
    url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_sanitize_filename():
    unsafe = 'Test / Video : Title? <Special> *Chars*|'
    cleaned = sanitize_filename(unsafe)
    assert "/" not in cleaned
    assert ":" not in cleaned
    assert "?" not in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "*" not in cleaned
    assert "|" not in cleaned
