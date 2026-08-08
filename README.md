# YouTube Video Scraper & Archival Tool

Production-grade, scalable YouTube video scraper and archival system built in Python using `yt-dlp` (via its native Python API), `Pydantic`, `SQLite`, `Click`, and `Rich`.

---

## Features

- **Comprehensive Data Archival**:
  - Video download (highest quality, MP4 merged container up to configurable resolution ceiling e.g. 1080p/4K).
  - High-res thumbnail download (`thumbnail.jpg`).
  - Full structured metadata validated via Pydantic (`video_metadata.json`).
  - Raw description (`description.txt`).
  - Transcripts / Subtitles: Manual captions preferred with auto-generated fallback; exports raw `.srt`, `.vtt`, and clean NLP-ready `.txt` (`en_clean.txt`).
  - Complete comment threads including nested replies & author metadata (`comments.json`, `comments_threaded.json`, `comments.csv`).
- **Resumability & Dedup**:
  - SQLite database manifest (`manifest.db`) tracks status (`pending`, `in_progress`, `done`, `failed`) per video.
  - Interrupted batch runs pick up right where they left off without re-downloading or re-fetching completed data.
- **Flexible Batch Input**:
  - Accepts single video URLs, channel URLs, playlist URLs, or text files containing URL lists.
- **Robustness**:
  - Exponential backoff retry logic, worker concurrency limits, and jitter/delays to respect rate limits.
  - Per-video `status.json` log and error isolation (a failure on one video does not break the batch).

---

## Directory Structure

```
data/
└── {channel_id}/
    └── {video_id}/
        ├── video/
        │   └── {video_id}.mp4
        ├── metadata/
        │   ├── video_metadata.json
        │   └── description.txt
        ├── transcript/
        │   ├── en.srt
        │   ├── en.vtt
        │   ├── en_clean.txt
        │   └── ... (other languages)
        ├── comments/
        │   ├── comments.json
        │   ├── comments_threaded.json
        │   └── comments.csv
        ├── thumbnails/
        │   └── thumbnail.jpg
        └── status.json
manifest.db
logs/
└── scraper.log
```

---

## Installation & Setup

1. **Activate Environment**:
   ```bash
   conda activate fai
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **FFmpeg Note**:
   `ffmpeg` is recommended on your system PATH for yt-dlp to merge high-resolution video and audio streams into `.mp4`. If `ffmpeg` is not present, yt-dlp will fall back to downloading single best combined streams.

---

## Quick Start (CLI Usage)

```bash
# 1. Scrape a single video URL
python main.py scrape --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 2. Scrape an entire channel (capped at 50 videos)
python main.py scrape --channel "https://www.youtube.com/@ChannelHandle" --max-videos 50

# 3. Scrape a playlist with 4 worker threads
python main.py scrape --playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --workers 4

# 4. Scrape from a file containing URLs (one per line)
python main.py scrape --file urls.txt

# 5. Metadata/Comments/Transcripts only (skip video download)
python main.py scrape --url "..." --skip-download

# 6. Check database manifest summary
python main.py status

# 7. Retry all failed videos in the manifest
python main.py retry-failed
```

---

## Configuration (`config.yaml`)

Configuration can be modified in `config.yaml` or overridden via CLI flags:

```yaml
data_dir: "./data"
db_path: "manifest.db"
log_dir: "./logs"
workers: 2
rate_limit_delay: 1.5  # Seconds of delay/jitter between requests
download_video: true
quality_ceiling: "1080p"
subtitle_languages:
  - "en"
  - "auto"
max_comments: null     # null = unlimited / extract all comments
cookies_file: null     # Path to cookies.txt if scraping age-restricted content
```

---

## Compliance & Terms of Service Notice

> **Important**: This tool should be used in compliance with YouTube's Terms of Service and applicable law. Built-in rate limiting and configurable delays are designed to ensure respectful, non-abusive client behavior. Always verify rights and fair use when archiving content.

---

## Running Tests

```bash
pytest -v
```
