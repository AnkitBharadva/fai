# YouTube Video Scraper & Archival Tool

Production-grade, scalable YouTube video scraper and archival system built in Python using `yt-dlp` (via its native Python API), `FFmpeg`, `Pydantic`, `SQLite`, `Click`, and `Rich`.

---

## Features

- **Custom Resolution & Quality Selection**:
  - Download videos in any specified resolution (e.g. `144p`, `240p`, `360p`, `480p`, `720p`, `1080p`, `1440p`, `4k`, `best`, `worst`).
- **FFmpeg Frame Extraction**:
  - Extract image frames directly from downloaded videos (`frames/frame_000001.jpg`).
  - Configurable frame skip step (e.g., `--frame-skip 1` for all frames, `--frame-skip 10` for 1 frame every 10 frames, `--frame-skip 50` for 1 frame every 50 frames).
- **Comprehensive Data Archival**:
  - High-res thumbnail download (`thumbnail.jpg`).
  - Full structured metadata validated via Pydantic (`video_metadata.json`).
  - Raw description (`description.txt`).
  - Transcripts / Subtitles: Manual captions preferred with auto-generated & multi-language translation fallbacks; exports `.vtt`, `.srt`, `.json`, and clean NLP-ready `.txt`.
  - Complete comment threads including nested replies & author metadata (`comments.json`, `comments_threaded.json`, `comments.csv`).
- **Resumability & Dedup**:
  - SQLite database manifest (`manifest.db`) tracks status (`pending`, `in_progress`, `done`, `failed`) per video.

---

## Directory Structure

```
data/
└── {channel_id}/
    └── {video_id}/
        ├── video/
        │   └── {video_id}.mp4
        ├── frames/
        │   ├── frame_000001.jpg
        │   ├── frame_000002.jpg
        │   └── ...
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

---

## CLI Usage Examples

```bash
# 1. Scrape a single video with custom resolution (e.g., 360p or 480p)
python main.py scrape --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --quality 360p

# 2. Extract frames from video (e.g., 1 frame every 30 frames)
python main.py scrape --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --extract-frames --frame-skip 30

# 3. Scrape an entire channel at 720p resolution
python main.py scrape --channel "https://www.youtube.com/@ChannelHandle" --quality 720p --max-videos 50

# 4. Check database manifest summary
python main.py status

# 5. Retry all failed videos in the manifest
python main.py retry-failed
```

---

## Configuration (`config.yaml`)

```yaml
data_dir: "./data"
db_path: "manifest.db"
log_dir: "./logs"
workers: 2
rate_limit_delay: 1.5

download_video: true
quality_ceiling: "1080p"  # e.g., 144p, 360p, 480p, 720p, 1080p, 4k, best, worst

extract_frames: false    # Set to true to enable FFmpeg frame extraction
frame_skip: 10           # Extract 1 frame every N frames (e.g. 10)

max_comments: null
subtitle_languages:
  - "en"
  - "auto"
```

---

## Running Tests

```bash
pytest -v
```
