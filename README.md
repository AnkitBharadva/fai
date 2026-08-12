<p align="center">
  <h1 align="center">Fai</h1>
  <p align="center">
    <strong>Production-grade YouTube data extraction pipeline</strong>
    <br />
    Multi-threaded · Resumable · Fault-tolerant
  </p>
</p>

<p align="center">
  <a href="#architecture">Architecture</a> •
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#cli-reference">CLI Reference</a> •
  <a href="#output-schema">Output Schema</a> •
  <a href="#configuration">Configuration</a>
</p>

---

**Fai** is a high-throughput, production-grade data extraction pipeline that scrapes, archives, and structures YouTube video data at scale. Built around a **Producer-Consumer architecture** with an **atomic SQLite task queue**, it processes entire channels and playlists through parallel worker agents while maintaining full resumability, deduplication, and structured output.

Designed for ML dataset construction, research corpus building, and large-scale content archival.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI Interface (Click)                       │
│   scrape · produce · consume · status · retry-failed                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                 ┌─────────────▼──────────────┐
                 │    ScrapingOrchestrator     │
                 │  (Producer-Consumer Core)   │
                 └─────┬───────────────┬───────┘
                       │               │
          ┌────────────▼──┐    ┌───────▼────────────┐
          │   Producer    │    │   Consumer Pool     │
          │   Agent       │    │   (ThreadPool)      │
          │               │    │                     │
          │ • Channel     │    │  ┌─Worker 1──────┐  │
          │   expansion   │    │  │ claim_task()  │  │
          │ • Playlist    │    │  │ → metadata    │  │
          │   flattening  │    │  │ → thumbnail   │  │
          │ • URL/file    │    │  │ → video.mp4   │  │
          │   ingestion   │    │  │ → audio.mp3   │  │
          │ • Dedup &     │    │  │ → frames/     │  │
          │   enqueue     │    │  │ → transcript  │  │
          └───────┬───────┘    │  │ → comments    │  │
                  │            │  └───────────────┘  │
                  │            │  ┌─Worker 2──────┐  │
                  │            │  │     ...        │  │
                  │            │  └───────────────┘  │
                  │            │  ┌─Worker N──────┐  │
                  │            │  │     ...        │  │
                  │            │  └───────────────┘  │
                  │            └─────────┬───────────┘
                  │                      │
          ┌───────▼──────────────────────▼───────┐
          │          manifest.db (SQLite)         │
          │  WAL mode · BEGIN IMMEDIATE locking   │
          │  States: pending → in_progress → done │
          └──────────────────────────────────────┘
```

### Design Decisions

| Decision | Rationale |
|:---|:---|
| **SQLite with WAL + `BEGIN IMMEDIATE`** | Lock-free concurrent reads with serialized atomic task claiming. No external DB dependency. |
| **Producer-Consumer separation** | Decouple discovery (slow, network-bound) from processing (CPU + I/O bound). Enable independent scaling. |
| **Cookie pool rotation** | Round-robin across multiple Netscape cookie files to distribute request load and mitigate rate limiting. |
| **3-tier transcript engine** | Native yt-dlp captions → HTTP fallback → Google Translate auto-translation. Maximizes caption coverage. |
| **Pydantic schema validation** | Type-safe data contracts across pipeline stages. Guarantees JSON output consistency. |

---

## Features

### Data Extraction
- **Video** — Configurable quality ceiling (`144p` to `4k`) with automatic stream merging to MP4
- **Audio** — Separate high-quality audio extraction (MP3, M4A, WAV, FLAC) via FFmpeg
- **Frames** — Configurable frame sampling from video files (`frame_skip` parameter)
- **Metadata** — 25+ structured fields including chapters, tags, categories, and engagement metrics
- **Transcripts** — Multi-language captions in VTT, SRT, JSON, and clean plaintext formats
- **Comments** — Full comment trees with nested reply hierarchies
- **Thumbnails** — Maximum resolution thumbnail images

### Pipeline Engineering
- **Atomic task queue** — SQLite-backed with `BEGIN IMMEDIATE` transaction locking for race-free parallel workers
- **Full resumability** — Pipeline state persisted to disk; interrupted runs resume exactly where they stopped
- **Deduplication** — Videos are never processed twice unless explicitly forced
- **Automatic retry** — Failed tasks tracked with error messages and retry counts; dedicated `retry-failed` command
- **Cookie rotation** — Round-robin cookie file distribution across workers
- **Rate limiting** — Configurable inter-request delays to respect platform limits
- **Structured logging** — Rich console output + rotating file logs (10MB × 5 backups)

---

## Quick Start

### Prerequisites

- Python 3.10+
- FFmpeg (optional but recommended — enables frame extraction, audio extraction, and stream merging)

### Installation

```bash
git clone https://github.com/AnkitBharadva/fai.git
cd fai
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

### Basic Usage

```bash
# Scrape a single video
python main.py scrape -u "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Scrape an entire channel
python main.py scrape -c "https://www.youtube.com/@channelname" --workers 4

# Scrape from a playlist
python main.py scrape -p "https://www.youtube.com/playlist?list=PLxxxxxxx"

# Scrape from a file containing video URLs (one per line)
python main.py scrape -f urls.txt --workers 4 --quality 720p
```

### Producer-Consumer Mode (Recommended for Large Jobs)

For channels with hundreds or thousands of videos, decouple discovery from processing:

```bash
# Step 1: Discover and enqueue all videos from a channel
python main.py produce -c "https://www.youtube.com/@channelname"

# Step 2: Launch parallel workers to process the queue
python main.py consume --workers 4

# Step 3: Monitor progress
python main.py status

# Step 4: Retry any failures
python main.py retry-failed --workers 2
```

---

## CLI Reference

### `scrape` — Integrated Pipeline

All-in-one command that discovers videos and processes them in a single run.

```
python main.py scrape [OPTIONS]

Options:
  -u, --url TEXT          Video URL or ID (repeatable)
  -c, --channel TEXT      Channel URL
  -p, --playlist TEXT     Playlist URL
  -f, --file TEXT         Text file with URLs/IDs (one per line)
  -q, --quality TEXT      Quality ceiling (144p, 360p, 480p, 720p, 1080p, 4k, best)
  -w, --workers INTEGER   Parallel worker count
  --extract-frames        Enable frame extraction
  --frame-skip INTEGER    Extract 1 frame every N frames
  --extract-audio         Extract audio track (default: enabled)
  --audio-format TEXT     Audio format: mp3, m4a, wav, flac (default: mp3)
  --cookies-dir TEXT      Path to cookies directory
  --max-videos INTEGER    Limit number of videos to process
  --max-comments INTEGER  Limit comments per video
  --skip-download         Skip video file download
  --force                 Re-process already completed videos
  --config TEXT           Path to custom config file
```

### `produce` — Producer Agent

Enqueues video tasks into the SQLite queue without processing.

```
python main.py produce -c "https://www.youtube.com/@channel" --max-videos 500
```

### `consume` — Consumer Workers

Launches parallel worker agents that pull tasks from the queue.

```
python main.py consume --workers 4
```

### `status` — Queue Dashboard

Displays a formatted summary of pipeline progress.

```
python main.py status
```

```
┌──────────────────────────────────────────┐
│   YouTube Scraper Manifest Status Summary │
├──────────────┬───────────────────────────┤
│ Status       │ Count                     │
├──────────────┼───────────────────────────┤
│ Pending      │ 150                       │
│ In_progress  │ 4                         │
│ Done         │ 352                       │
│ Failed       │ 7                         │
├──────────────┼───────────────────────────┤
│ Total        │ 513                       │
└──────────────┴───────────────────────────┘
```

### `retry-failed` — Retry Failures

Re-processes all videos marked as `failed` in the manifest.

```
python main.py retry-failed --workers 2
```

---

## Output Schema

Each video produces a self-contained directory with structured data:

```
data/
└── {channel_id}/
    └── {video_id}/
        ├── video/
        │   └── {video_id}.mp4           # Video stream (merged MP4)
        ├── audio/
        │   └── audio.mp3                # Extracted audio track
        ├── frames/
        │   ├── frame_000001.jpg         # Sampled video frames
        │   ├── frame_000002.jpg
        │   └── ...
        ├── metadata/
        │   ├── video_metadata.json      # Structured metadata (25+ fields)
        │   └── description.txt          # Raw video description
        ├── transcript/
        │   ├── en.vtt                   # WebVTT captions
        │   ├── en.srt                   # SubRip captions
        │   ├── en_clean.txt             # Plain text (timestamps stripped)
        │   ├── en.json                  # Timed segments with start/end
        │   ├── hi.vtt                   # Hindi captions
        │   └── hi_clean.txt
        ├── comments/
        │   ├── comments.json            # Flat comment records
        │   └── comments_threaded.json   # Nested reply tree hierarchy
        ├── thumbnails/
        │   └── thumbnail.jpg            # Max resolution thumbnail
        └── status.json                  # Pipeline execution log
```

### Metadata Fields (`video_metadata.json`)

```json
{
  "video_id": "dQw4w9WgXcQ",
  "title": "Video Title",
  "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx",
  "channel_name": "Channel Name",
  "upload_date": "20240115",
  "duration": 212.0,
  "view_count": 1500000,
  "like_count": 85000,
  "comment_count": 4200,
  "tags": ["tag1", "tag2"],
  "categories": ["Education"],
  "language": "en",
  "availability": "public",
  "is_live": false,
  "was_live": false,
  "chapters": [
    { "start_time": 0.0, "end_time": 60.0, "title": "Introduction" }
  ],
  "thumbnail_url": "https://i.ytimg.com/vi/...",
  "available_subtitle_languages": ["en", "hi", "en-auto"],
  "age_limit": 0,
  "original_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "description": "Full video description text..."
}
```

---

## Configuration

Copy the example config and customize:

```bash
cp config.example.yaml config.yaml
```

```yaml
# Directory paths
data_dir: "./data"
db_path: "manifest.db"
log_dir: "./logs"

# Performance
workers: 2
rate_limit_delay: 1.5       # Seconds between requests per worker

# Video settings
download_video: true
quality_ceiling: "1080p"     # 144p | 360p | 480p | 720p | 1080p | 4k | best
download_thumbnail: true

# Audio extraction
extract_audio: true
audio_format: "mp3"          # mp3 | m4a | wav | flac

# Frame extraction
extract_frames: false
frame_skip: 10               # 1 = every frame, 10 = every 10th frame

# Content
max_comments: null            # null = unlimited
subtitle_languages:
  - "en"
  - "auto"

# Cookies
cookies_dir: "./cookies"

# Logging
log_level: "INFO"
```

All configuration options can be overridden via CLI flags.

---

## Database Schema

The manifest database (`manifest.db`) tracks pipeline state using SQLite with WAL journaling:

```sql
CREATE TABLE manifest (
    video_id       TEXT PRIMARY KEY,
    channel_id     TEXT,
    status         TEXT NOT NULL,    -- pending | in_progress | done | failed
    last_attempt_at TEXT,
    completed_at   TEXT,
    retry_count    INTEGER DEFAULT 0,
    error_message  TEXT
);
```

### Concurrency Model

Worker threads claim tasks atomically using `BEGIN IMMEDIATE` transaction locks:

```sql
BEGIN IMMEDIATE;
SELECT * FROM manifest WHERE status = 'pending' ORDER BY last_attempt_at ASC LIMIT 1;
UPDATE manifest SET status = 'in_progress' WHERE video_id = ? AND status = 'pending';
COMMIT;
```

This guarantees **zero duplicate processing** across parallel workers without external coordination.

---

## Project Structure

```
fai/
├── main.py                  # CLI entrypoint (Click + Rich)
├── config.example.yaml      # Configuration template
├── requirements.txt         # Python dependencies
├── src/
│   ├── orchestrator.py      # Producer-Consumer pipeline coordinator
│   ├── db.py                # SQLite manifest & atomic task queue
│   ├── metadata.py          # Video metadata & channel/playlist expander
│   ├── downloader.py        # Video, audio, thumbnail & frame extraction
│   ├── transcript.py        # 3-tier caption engine (native → HTTP → translate)
│   ├── comments.py          # Comment extraction & thread tree builder
│   ├── cookies_manager.py   # Round-robin cookie file rotation
│   ├── organizer.py         # Per-video directory structure manager
│   ├── schemas.py           # Pydantic data models
│   ├── config_loader.py     # YAML config + CLI override merger
│   └── utils.py             # Video ID parser, filename sanitizer, logging
└── tests/
    ├── test_comments.py     # Comment hierarchy & serialization tests
    ├── test_cookies.py      # Cookie rotation tests
    ├── test_db.py           # Database state machine tests
    ├── test_downloader.py   # Format spec generation tests
    ├── test_organizer.py    # Directory structure tests
    ├── test_transcript.py   # Caption cleaning & dedup tests
    └── test_utils.py        # URL parsing & sanitization tests
```

---

## Testing

```bash
pytest -v
```

```
tests/test_comments.py::test_build_threaded_comments     PASSED
tests/test_comments.py::test_save_comments               PASSED
tests/test_cookies.py::test_cookies_manager_rotation      PASSED
tests/test_db.py::test_manifest_db_workflow               PASSED
tests/test_downloader.py::test_quality_format_spec        PASSED
tests/test_organizer.py::test_folder_organizer_structure  PASSED
tests/test_transcript.py::test_clean_subtitle_text_vtt    PASSED
tests/test_transcript.py::test_clean_subtitle_dedup       PASSED
tests/test_utils.py::test_extract_video_id_raw            PASSED
tests/test_utils.py::test_extract_video_id_standard_url   PASSED
tests/test_utils.py::test_extract_video_id_short_url      PASSED
tests/test_utils.py::test_extract_video_id_shorts_url     PASSED
tests/test_utils.py::test_sanitize_filename               PASSED

13 passed
```

---

## Tech Stack

| Layer | Technology |
|:---|:---|
| **CLI** | Click + Rich |
| **Data Validation** | Pydantic v2 |
| **Extraction Engine** | yt-dlp |
| **Media Processing** | FFmpeg (via system or imageio-ffmpeg) |
| **Task Queue** | SQLite (WAL mode, atomic transactions) |
| **TLS Fingerprinting** | curl_cffi (Chrome 120 impersonation) |
| **Translation** | deep_translator (Google Translate API) |
| **Retry Logic** | Tenacity (exponential backoff) |
| **Configuration** | PyYAML |
| **Testing** | pytest |

---

## ⚠️ Disclaimer & Best Practices

This tool is intended for **research, educational, and archival purposes only**. Scraping YouTube data at scale may violate their Terms of Service. 

YouTube employs aggressive anti-bot protections, rate limiting, and IP-level bans (resulting in `HTTP 403 Forbidden` or `Requested format is not available` errors).

**Critical Recommendations for Production Use:**
1. **Never scrape from your personal/home IP address.** Always route your traffic through a commercial VPN (rotating servers frequently) or use residential proxy networks.
2. **Use Cookie Rotation.** Populate the `cookies/` directory with multiple anonymous/guest Netscape-format cookie files. The pipeline will automatically distribute requests across them using round-robin rotation.
3. **Respect Rate Limits.** Keep the `rate_limit_delay` in your `config.yaml` high enough (e.g., `3.0` to `5.0` seconds) to avoid immediate throttling.
4. **Scale Responsibly.** Running more than 2-4 concurrent workers on a single IP will likely result in immediate CDN blocks.

*The author is not responsible for any account bans, IP blocks, or legal repercussions resulting from the use of this software.*

---

## License

MIT

