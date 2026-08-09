"""Video, thumbnail, frame extraction, and high-quality audio downloader module."""

import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
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
    """Handles downloading YouTube videos, thumbnails, frame extraction, and audio extraction."""

    def __init__(
        self,
        quality_ceiling: str = "1080p",
        audio_only: bool = False,
        cookies_file: Optional[str] = None,
    ):
        self.quality_ceiling = str(quality_ceiling).strip().lower()
        self.audio_only = audio_only
        self.cookies_file = cookies_file
        self.ffmpeg_path = get_ffmpeg_path()

    def _build_format_spec(self) -> str:
        if self.audio_only:
            return "bestaudio/best"

        if not self.ffmpeg_path:
            # Without ffmpeg, yt-dlp cannot merge video+audio streams, so request single best format
            return "best[ext=mp4]/best"

        qc = self.quality_ceiling

        # Special keywords
        if qc in ["best", "max", "highest", "uncapped"]:
            return "bestvideo+bestaudio/best"
        elif qc in ["worst", "min", "lowest"]:
            return "worstvideo+worstaudio/worst"

        # Parse target resolution height (e.g. 144, 240, 360, 480, 720, 1080, 1440, 2160, 4k, 2k)
        if qc == "4k":
            height = 2160
        elif qc == "2k":
            height = 1440
        else:
            match = re.search(r"(\d+)", qc)
            height = int(match.group(1)) if match else None

        if height:
            return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

        # If user passed custom yt-dlp format selector string directly
        return self.quality_ceiling

    def download_video(self, video_url: str, output_dir: Path, video_id: str) -> Path:
        """Download video at target quality into target dir."""
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

    def extract_frames(self, video_file: Path, output_dir: Path, frame_skip: int = 1) -> List[Path]:
        """Extract frame images from downloaded video using ffmpeg.

        Args:
            video_file: Path to downloaded video file.
            output_dir: Output directory to store frame files.
            frame_skip: Extract 1 frame every N frames (1 = extract all frames, 10 = extract 1 frame every 10 frames).
        """
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg binary is required for frame extraction but was not found.")

        if not video_file.exists():
            raise FileNotFoundError(f"Video file not found for frame extraction: {video_file}")

        output_dir.mkdir(parents=True, exist_ok=True)
        frame_pattern = str(output_dir / "frame_%06d.jpg")

        step = max(1, int(frame_skip))
        vf_filter = f"select='not(mod(n\\,{step}))'"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_file),
            "-vf", vf_filter,
            "-vsync", "0",
            frame_pattern,
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg frame extraction failed: {res.stderr}")

        return sorted(list(output_dir.glob("frame_*.jpg")))

    def extract_audio(
        self,
        video_file: Optional[Path],
        output_dir: Path,
        video_url: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> Path:
        """Extract high-quality audio into a separate audio folder.

        Uses ffmpeg if video_file exists, or falls back to yt-dlp bestaudio download.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        fmt = audio_format.lower().strip()
        target_audio_file = output_dir / f"audio.{fmt}"

        if self.ffmpeg_path and video_file and video_file.exists():
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(video_file),
                "-vn",
            ]
            if fmt == "mp3":
                cmd.extend(["-acodec", "libmp3lame", "-q:a", "0"])
            elif fmt in ["m4a", "aac"]:
                cmd.extend(["-c:a", "copy"])
            elif fmt == "wav":
                cmd.extend(["-acodec", "pcm_s16le"])
            else:
                cmd.extend(["-q:a", "0"])

            cmd.append(str(target_audio_file))
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and target_audio_file.exists():
                return target_audio_file

        # Fallback: direct download best audio stream using yt-dlp
        if video_url:
            outtmpl = str(output_dir / "audio.%(ext)s")
            opts: Dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
            }
            if self.ffmpeg_path:
                opts["ffmpeg_location"] = self.ffmpeg_path
                opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": fmt if fmt in ["mp3", "m4a", "wav", "flac"] else "mp3",
                        "preferredquality": "0",  # Highest VBR quality
                    }
                ]
            if self.cookies_file and Path(self.cookies_file).exists():
                opts["cookiefile"] = self.cookies_file

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([video_url])

            audio_files = list(output_dir.glob("audio.*"))
            if audio_files:
                return audio_files[0]

        raise RuntimeError("Could not extract audio track.")
