"""Video and thumbnail downloader module using yt-dlp Python API."""

import shutil
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional
import yt_dlp


def get_ffmpeg_path() -> Optional[str]:
    """Find ffmpeg binary path from system PATH or imageio-ffmpeg package."""
    # 1. System PATH
    sys_path = shutil.which("ffmpeg")
    if sys_path:
        return sys_path

    # 2. imageio-ffmpeg
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass

    return None


class VideoDownloader:
    """Handles downloading YouTube videos and thumbnails."""

    def __init__(
        self,
        quality_ceiling: str = "1080p",
        audio_only: bool = False,
        cookies_file: Optional[str] = None,
    ):
        self.quality_ceiling = quality_ceiling.lower()
        self.audio_only = audio_only
        self.cookies_file = cookies_file
        self.ffmpeg_path = get_ffmpeg_path()

    def _build_format_spec(self) -> str:
        if self.audio_only:
            return "bestaudio/best"

        if not self.ffmpeg_path:
            # Without ffmpeg, yt-dlp cannot merge video+audio streams, so request single best format
            return "best[ext=mp4]/best"

        if self.quality_ceiling == "720p":
            return "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif self.quality_ceiling in ["1080p", "1080"]:
            return "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        elif self.quality_ceiling in ["4k", "2160p"]:
            return "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"
        else:
            return "bestvideo+bestaudio/best"

    def download_video(self, video_url: str, output_dir: Path, video_id: str) -> Path:
        """Download video at best available quality up to quality ceiling into target dir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(output_dir / f"{video_id}.%(ext)s")

        format_spec = self._build_format_spec()

        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": format_spec,
            "outtmpl": outtmpl,
        }
        if self.ffmpeg_path:
            opts["ffmpeg_location"] = self.ffmpeg_path
            opts["merge_output_format"] = "mp4"

        if self.cookies_file and Path(self.cookies_file).exists():
            opts["cookiefile"] = self.cookies_file

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video_url])

        # Find downloaded file
        downloaded_files = list(output_dir.glob(f"{video_id}.*"))
        if downloaded_files:
            return downloaded_files[0]
        return output_dir / f"{video_id}.mp4"

    def download_thumbnail(self, thumbnail_url: Optional[str], thumbnail_dir: Path) -> Optional[Path]:
        """Download thumbnail image."""
        if not thumbnail_url:
            return None

        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        out_path = thumbnail_dir / "thumbnail.jpg"

        try:
            req = urllib.request.Request(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
                f.write(resp.read())
            return out_path
        except Exception:
            return None
