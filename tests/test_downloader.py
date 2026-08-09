"""Unit tests for quality format spec building and downloader settings."""

from src.downloader import VideoDownloader


def test_quality_format_spec_building():
    # 720p
    dl_720 = VideoDownloader(quality_ceiling="720p")
    spec_720 = dl_720._build_format_spec()
    assert "720" in spec_720

    # 360p
    dl_360 = VideoDownloader(quality_ceiling="360p")
    spec_360 = dl_360._build_format_spec()
    assert "360" in spec_360

    # 4k
    dl_4k = VideoDownloader(quality_ceiling="4k")
    spec_4k = dl_4k._build_format_spec()
    assert "2160" in spec_4k

    # Best
    dl_best = VideoDownloader(quality_ceiling="best")
    spec_best = dl_best._build_format_spec()
    assert "bestvideo+bestaudio" in spec_best or "best" in spec_best
