"""Tests for subtitle cleaning and formatting."""

from src.transcript import clean_subtitle_text


def test_clean_subtitle_text_vtt():
    sample_vtt = """WEBVTT
Kind: captions
Language: en

1
00:00:00.000 --> 00:00:02.500
<c.colorFFF>Hello and welcome</c> to the channel.

2
00:00:02.500 --> 00:00:05.000
Today we are testing the <b>YouTube scraper</b>.
"""
    cleaned = clean_subtitle_text(sample_vtt)
    assert "Hello and welcome to the channel." in cleaned
    assert "Today we are testing the YouTube scraper." in cleaned
    assert "WEBVTT" not in cleaned
    assert "-->" not in cleaned
    assert "<b>" not in cleaned


def test_clean_subtitle_text_deduplication():
    sample_vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Repeated caption line

00:00:02.000 --> 00:00:03.000
Repeated caption line
"""
    cleaned = clean_subtitle_text(sample_vtt)
    lines = cleaned.splitlines()
    assert len(lines) == 1
    assert lines[0] == "Repeated caption line"
