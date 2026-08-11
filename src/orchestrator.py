"""Main orchestration pipeline for batch scraping videos with retry, rate limiting, and progress tracking."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.comments import CommentExtractor
from src.cookies_manager import CookiesManager
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

        cookies_input = config.get("cookies_file") or config.get("cookies_dir") or "cookies"
        self.cookies_manager = CookiesManager(cookies_input)

    def _get_extractors_for_task(self):
        """Instantiate extractors using a rotated cookie file."""
        cookie_file = self.cookies_manager.get_cookie_file()
        if cookie_file:
            self.logger.debug(f"Using rotated cookie file: {cookie_file}")

        meta_extractor = MetadataExtractor(cookies_file=cookie_file)
        transcript_extractor = TranscriptExtractor(cookies_file=cookie_file)
        comment_extractor = CommentExtractor(cookies_file=cookie_file)
        downloader = VideoDownloader(
            quality_ceiling=self.config.get("quality_ceiling", "1080p"),
            audio_only=self.config.get("audio_only", False),
            cookies_file=cookie_file,
        )
        return meta_extractor, transcript_extractor, comment_extractor, downloader

    def process_single_video(self, video_id_or_url: str, force: bool = False) -> bool:
        """Process a single video through the complete pipeline with retry logic."""
        video_id = extract_video_id(video_id_or_url)
        if not video_id:
            self.logger.error(f"Invalid video ID or Channel ID passed as video task: {video_id_or_url}")
            return False

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Resumability check
        if not force and self.db.is_completed(video_id):
            self.logger.info(f"Skipping already completed video: {video_id}")
            return True

        self.db.register_video(video_id)
        self.db.update_status(video_id, "in_progress")

        meta_extractor, transcript_extractor, comment_extractor, downloader = self._get_extractors_for_task()

        start_time = datetime.now(timezone.utc)
        status_info: Dict[str, Any] = {
            "video_id": video_id,
            "started_at": start_time.isoformat(),
            "components": {},
        }

        try:
            # 1. Metadata & Description
            self.logger.info(f"[{video_id}] Extracting metadata & description...")
            metadata = meta_extractor.extract_metadata(video_url)
            channel_id = metadata.channel_id or "unknown_channel"

            dirs = self.organizer.setup_video_dirs(channel_id, video_id)
            meta_extractor.save_metadata(metadata, dirs["metadata"])
            status_info["components"]["metadata"] = "success"

            # Update channel_id in DB manifest
            self.db.update_status(video_id, "in_progress", channel_id=channel_id)

            # 2. Thumbnail
            if self.config.get("download_thumbnail", True):
                self.logger.info(f"[{video_id}] Downloading thumbnail...")
                downloader.download_thumbnail(metadata.thumbnail_url, dirs["thumbnails"])
                status_info["components"]["thumbnail"] = "success"

            # 3. Video Download
            downloaded_video = None
            if self.config.get("download_video", True):
                self.logger.info(f"[{video_id}] Downloading video stream...")
                downloaded_video = downloader.download_video(video_url, dirs["video"], video_id)
                status_info["components"]["video"] = "success"
            else:
                status_info["components"]["video"] = "skipped"

            # 3b. Frame Extraction
            if self.config.get("extract_frames", False) and downloaded_video:
                frame_skip = self.config.get("frame_skip", 1)
                self.logger.info(f"[{video_id}] Extracting frames (frame_skip={frame_skip})...")
                extracted = downloader.extract_frames(downloaded_video, dirs["frames"], frame_skip=frame_skip)
                status_info["components"]["frames"] = f"success ({len(extracted)} frames extracted)"

            # 3c. Audio Extraction
            if self.config.get("extract_audio", True):
                fmt = self.config.get("audio_format", "mp3")
                self.logger.info(f"[{video_id}] Extracting high quality audio ({fmt})...")
                audio_file = downloader.extract_audio(
                    video_file=downloaded_video,
                    output_dir=dirs["audio"],
                    video_url=video_url,
                    audio_format=fmt,
                )
                status_info["components"]["audio"] = f"success ({audio_file.name})"

            # 4. Transcripts
            self.logger.info(f"[{video_id}] Fetching transcripts/captions...")
            langs = transcript_extractor.extract_and_save_transcripts(
                video_url=video_url,
                transcript_dir=dirs["transcript"],
                target_languages=self.config.get("subtitle_languages", ["en"]),
                prefer_manual=self.config.get("prefer_manual_subtitles", True),
            )
            status_info["components"]["transcripts"] = "success" if langs else "no_captions_found"

            # 5. Comments
            self.logger.info(f"[{video_id}] Fetching comment threads...")
            comments = comment_extractor.extract_comments(
                video_url=video_url,
                max_comments=self.config.get("max_comments"),
            )
            comment_extractor.save_comments(comments, dirs["comments"])
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

    def produce_channel_tasks(
        self,
        channel_url: Optional[str] = None,
        playlist_url: Optional[str] = None,
        urls: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        max_videos: Optional[int] = None,
    ) -> int:
        """Producer agent step: Expand channel/playlist URLs and enqueue pending tasks into atomic manifest.db queue."""
        target_urls: List[str] = []

        if urls:
            target_urls.extend(urls)

        if file_path and Path(file_path).exists():
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        target_urls.append(line)

        meta_extractor, _, _, _ = self._get_extractors_for_task()

        if channel_url:
            self.logger.info(f"[PRODUCER] Expanding channel URL: {channel_url}")
            expanded = meta_extractor.expand_url(channel_url)
            target_urls.extend(expanded)

        if playlist_url:
            self.logger.info(f"[PRODUCER] Expanding playlist URL: {playlist_url}")
            expanded = meta_extractor.expand_url(playlist_url)
            target_urls.extend(expanded)

        # Canonicalize & deduplicate
        video_ids: List[str] = []
        seen = set()
        for item in target_urls:
            vid = extract_video_id(item)
            if vid and vid not in seen:
                seen.add(vid)
                video_ids.append(vid)

        if max_videos and max_videos > 0:
            video_ids = video_ids[:max_videos]

        self.logger.info(f"[PRODUCER] Enqueueing {len(video_ids)} video tasks into atomic queue...")
        count = self.db.enqueue_videos(video_ids)
        self.logger.info(f"[PRODUCER] Successfully enqueued {count} pending tasks.")
        return count

    def consume_queue(self, workers: Optional[int] = None) -> Dict[str, int]:
        """Consumer agent step: Launch worker pool pulling pending video tasks atomically from manifest.db queue."""
        max_workers = workers or self.config.get("workers", 2)
        delay = float(self.config.get("rate_limit_delay", 1.5))
        counts = {"success": 0, "failed": 0, "skipped": 0}

        def worker_loop(worker_id: int):
            while True:
                task = self.db.claim_next_pending_task()
                if not task:
                    break

                self.logger.info(f"[CONSUMER-WORKER-{worker_id}] Claimed task: {task.video_id}")
                res = self.process_single_video(task.video_id, force=True)
                if res:
                    counts["success"] += 1
                else:
                    counts["failed"] += 1

                if delay > 0:
                    time.sleep(delay)

        self.logger.info(f"[CONSUMER] Starting {max_workers} worker agent(s)...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_loop, w_id) for w_id in range(1, max_workers + 1)]
            for future in as_completed(futures):
                future.result()

        self.logger.info("==========================================")
        self.logger.info("Consumer Batch Summary:")
        self.logger.info(f"  Success: {counts['success']}")
        self.logger.info(f"  Failed:  {counts['failed']}")
        self.logger.info("==========================================")

        return counts

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
        """Integrated Producer-Consumer entrypoint: Discovery + Queueing + Consumer worker execution."""
        # 1. Producer step
        self.produce_channel_tasks(
            channel_url=channel_url,
            playlist_url=playlist_url,
            urls=urls,
            file_path=file_path,
            max_videos=max_videos,
        )

        # 2. Consumer step
        return self.consume_queue(workers=workers)
