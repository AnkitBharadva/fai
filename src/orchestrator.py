"""Main orchestration pipeline for batch scraping videos with retry, rate limiting, and progress tracking."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.comments import CommentExtractor
from src.db import ManifestDB
from src.downloader import VideoDownloader
from src.metadata import MetadataExtractor
from src.organizer import FolderOrganizer
from src.transcript import TranscriptExtractor
from src.utils import extract_video_id, setup_logger


class ScrapingOrchestrator:
    """Orchestrates scraping of YouTube videos, channels, playlists, or input files."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = setup_logger(config.get("log_dir", "./logs"), config.get("log_level", "INFO"))
        self.db = ManifestDB(config.get("db_path", "manifest.db"))
        self.organizer = FolderOrganizer(config.get("data_dir", "./data"))

        cookies_file = config.get("cookies_file")
        self.metadata_extractor = MetadataExtractor(cookies_file=cookies_file)
        self.transcript_extractor = TranscriptExtractor(cookies_file=cookies_file)
        self.comment_extractor = CommentExtractor(cookies_file=cookies_file)
        self.downloader = VideoDownloader(
            quality_ceiling=config.get("quality_ceiling", "1080p"),
            audio_only=config.get("audio_only", False),
            cookies_file=cookies_file,
        )

    def process_single_video(self, video_id_or_url: str, force: bool = False) -> bool:
        """Process a single video through the complete pipeline with retry logic."""
        video_id = extract_video_id(video_id_or_url)
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Resumability check
        if not force and self.db.is_completed(video_id):
            self.logger.info(f"Skipping already completed video: {video_id}")
            return True

        self.db.register_video(video_id)
        self.db.update_status(video_id, "in_progress")

        start_time = datetime.now(timezone.utc)
        status_info: Dict[str, Any] = {
            "video_id": video_id,
            "started_at": start_time.isoformat(),
            "components": {},
        }

        try:
            # 1. Metadata & Description
            self.logger.info(f"[{video_id}] Extracting metadata & description...")
            metadata = self.metadata_extractor.extract_metadata(video_url)
            channel_id = metadata.channel_id or "unknown_channel"

            dirs = self.organizer.setup_video_dirs(channel_id, video_id)
            self.metadata_extractor.save_metadata(metadata, dirs["metadata"])
            status_info["components"]["metadata"] = "success"

            # Update channel_id in DB manifest
            self.db.update_status(video_id, "in_progress", channel_id=channel_id)

            # 2. Thumbnail
            if self.config.get("download_thumbnail", True):
                self.logger.info(f"[{video_id}] Downloading thumbnail...")
                self.downloader.download_thumbnail(metadata.thumbnail_url, dirs["thumbnails"])
                status_info["components"]["thumbnail"] = "success"

            # 3. Video Download
            downloaded_video = None
            if self.config.get("download_video", True):
                self.logger.info(f"[{video_id}] Downloading video stream...")
                downloaded_video = self.downloader.download_video(video_url, dirs["video"], video_id)
                status_info["components"]["video"] = "success"
            else:
                status_info["components"]["video"] = "skipped"

            # 3b. Frame Extraction
            if self.config.get("extract_frames", False) and downloaded_video:
                frame_skip = self.config.get("frame_skip", 1)
                self.logger.info(f"[{video_id}] Extracting frames (frame_skip={frame_skip})...")
                extracted = self.downloader.extract_frames(downloaded_video, dirs["frames"], frame_skip=frame_skip)
                status_info["components"]["frames"] = f"success ({len(extracted)} frames extracted)"

            # 3c. Audio Extraction
            if self.config.get("extract_audio", True):
                fmt = self.config.get("audio_format", "mp3")
                self.logger.info(f"[{video_id}] Extracting high quality audio ({fmt})...")
                audio_file = self.downloader.extract_audio(
                    video_file=downloaded_video,
                    output_dir=dirs["audio"],
                    video_url=video_url,
                    audio_format=fmt,
                )
                status_info["components"]["audio"] = f"success ({audio_file.name})"

            # 4. Transcripts
            self.logger.info(f"[{video_id}] Fetching transcripts/captions...")
            langs = self.transcript_extractor.extract_and_save_transcripts(
                video_url=video_url,
                transcript_dir=dirs["transcript"],
                target_languages=self.config.get("subtitle_languages", ["en"]),
                prefer_manual=self.config.get("prefer_manual_subtitles", True),
            )
            status_info["components"]["transcripts"] = "success" if langs else "no_captions_found"

            # 5. Comments
            self.logger.info(f"[{video_id}] Fetching comment threads...")
            comments = self.comment_extractor.extract_comments(
                video_url=video_url,
                max_comments=self.config.get("max_comments"),
            )
            self.comment_extractor.save_comments(comments, dirs["comments"])
            status_info["components"]["comments"] = f"success ({len(comments)} comments)"

            # Finish
            end_time = datetime.now(timezone.utc)
            status_info["completed_at"] = end_time.isoformat()
            status_info["status"] = "success"
            self.organizer.write_status(channel_id, video_id, status_info)

            self.db.update_status(video_id, "done", channel_id=channel_id)
            self.logger.info(f"[{video_id}] Successfully scraped video data.")
            return True

        except Exception as e:
            err_msg = str(e)
            self.logger.error(f"[{video_id}] Scraping failed: {err_msg}", exc_info=True)
            status_info["status"] = "failed"
            status_info["error"] = err_msg
            self.organizer.write_status("unknown_channel", video_id, status_info)
            self.db.update_status(video_id, "failed", error_message=err_msg)
            return False

    def run(
        self,
        urls: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        channel_url: Optional[str] = None,
        playlist_url: Optional[str] = None,
        max_videos: Optional[int] = None,
        workers: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, int]:
        """Run batch scraper across collected input targets."""
        target_urls: List[str] = []

        if urls:
            target_urls.extend(urls)

        if file_path and Path(file_path).exists():
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        target_urls.append(line)

        if channel_url:
            self.logger.info(f"Expanding channel URL: {channel_url}")
            expanded = self.metadata_extractor.expand_url(channel_url)
            target_urls.extend(expanded)

        if playlist_url:
            self.logger.info(f"Expanding playlist URL: {playlist_url}")
            expanded = self.metadata_extractor.expand_url(playlist_url)
            target_urls.extend(expanded)

        # Extract canonical video IDs & deduplicate
        video_ids: List[str] = []
        seen = set()
        for item in target_urls:
            vid = extract_video_id(item)
            if vid and vid not in seen:
                seen.add(vid)
                video_ids.append(vid)

        if max_videos and max_videos > 0:
            video_ids = video_ids[:max_videos]

        self.logger.info(f"Total canonical video IDs to process: {len(video_ids)}")

        max_workers = workers or self.config.get("workers", 2)
        delay = float(self.config.get("rate_limit_delay", 1.5))

        counts = {"success": 0, "failed": 0, "skipped": 0}

        def worker_fn(vid: str) -> bool:
            if not force and self.db.is_completed(vid):
                return None  # Skipped
            res = self.process_single_video(vid, force=force)
            if delay > 0:
                time.sleep(delay)
            return res

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_vid = {executor.submit(worker_fn, vid): vid for vid in video_ids}
            for future in as_completed(future_to_vid):
                vid = future_to_vid[future]
                try:
                    res = future.result()
                    if res is None:
                        counts["skipped"] += 1
                    elif res:
                        counts["success"] += 1
                    else:
                        counts["failed"] += 1
                except Exception as e:
                    self.logger.error(f"Worker exception for video {vid}: {e}")
                    counts["failed"] += 1

        self.logger.info("==========================================")
        self.logger.info("Batch Run Summary:")
        self.logger.info(f"  Success: {counts['success']}")
        self.logger.info(f"  Skipped: {counts['skipped']}")
        self.logger.info(f"  Failed:  {counts['failed']}")
        self.logger.info("==========================================")

        return counts
