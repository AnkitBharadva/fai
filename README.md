<p align="center">
  <h1 align="center">Fai</h1>
  <p align="center">
    <strong>Production-grade YouTube data extraction pipeline</strong>
    <br />
    Videos · Audio · Transcripts · Comments · Community Posts · Polls · Multi-threaded · Resumable
  </p>
</p>

<p align="center">
  <a href="#architecture">Architecture</a> •
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#cli-reference">CLI Reference</a> •
  <a href="#community-scraper">Community Scraper</a> •
  <a href="#output-schema">Output Schema</a> •
  <a href="#configuration">Configuration</a>
</p>

---

**Fai** is a high-throughput, production-grade data extraction pipeline that scrapes, archives, and structures YouTube video and community data at scale. Built around a **Producer-Consumer architecture** with an **atomic SQLite task queue** and a native **InnerTube Community Extractor**, it processes entire channels, playlists, and community feeds through parallel worker agents while maintaining full resumability, deduplication, and structured output.

Designed for ML dataset construction, research corpus building, and large-scale content archival.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLI Interface (Click)                          │
│    scrape · produce · consume · status · retry-failed · community       │
└──────────────────┬──────────────────────────────────┬───────────────────┘
                   │                                  │
     ┌─────────────▼──────────────┐       ┌───────────▼──────────────┐
     │    ScrapingOrchestrator     │       │    CommunityExtractor    │
     │  (Producer-Consumer Core)   │       │  (InnerTube API Engine)  │
     └─────┬───────────────┬───────┘       └───────────┬──────────────┘
           │               │                           │
┌──────────▼────┐    ┌─────▼──────────────┐   ┌────────▼──────────────┐
│   Producer    │    │   Consumer Pool     │   │   Community Feed      │
│   Agent       │    │   (ThreadPool)      │   │                       │
│               │    │                     │   │ • Full post history   │
│ • Channel     │    │  ┌─Worker 1──────┐  │   │ • Poll vote splits    │
│   expansion   │    │  │ claim_task()  │  │   │ • HD image assets     │
│ • Playlist    │    │  │ → metadata    │  │   │ • Threaded comments   │
│   flattening  │    │  │ → thumbnail   │  │   │ • Recursive token     │
│ • URL/file    │    │  │ → video.mp4   │  │   │   pagination          │
│   ingestion   │    │  │ → audio.mp3   │  │   └───────────┬───────────┘
│ • Dedup &     │    │  │ → frames/     │  │               │
│   enqueue     │    │  │ → transcript  │  │               ▼
└───────┬───────┘    │  │ → comments    │  │   ┌───────────────────────┐
        │            │  └───────────────┘  │   │ data/{channel}/       │
        │            │  ┌─Worker 2──────┐  │   │ └── community/        │
        │            │  │     ...        │  │   │     ├── posts.json    │
        │            │  └───────────────┘  │   │     └── posts/        │
        │            └─────────┬───────────┘   └───────────────────────┘
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
| **Native InnerTube Community Engine** | Direct recursive continuation token pagination for complete community post and threaded comment trees without headless browser overhead. |
| **Cookie pool rotation** | Round-robin across multiple Netscape cookie files to distribute request load and mitigate rate limiting. |
| **3-tier transcript engine** | Native yt-dlp captions → HTTP fallback → Google Translate auto-translation. Maximizes caption coverage. |
| **Pydantic schema validation** | Type-safe data contracts across pipeline stages. Guarantees JSON output consistency. |

---

## Features

### Video Data Extraction
- **Video** — Configurable quality ceiling (`144p` to `4k`) with automatic stream merging to MP4
- **Audio** — Separate high-quality audio extraction (MP3, M4A, WAV, FLAC) via FFmpeg
- **Frames** — Configurable frame sampling from video files (`frame_skip` parameter)
- **Metadata** — 25+ structured fields including chapters, tags, categories, and engagement metrics
- **Transcripts** — Multi-language captions in VTT, SRT, JSON, and clean plaintext formats
- **Comments** — Full video comment trees with nested reply hierarchies
- **Thumbnails** — Maximum resolution thumbnail images

### Community Tab Extraction
- **Full Post History** — Recursive token pagination capturing 100% of community posts from day one
- **Interactive Polls** — Multi-choice options, percentage splits, and total vote statistics
- **HD Image Attachments** — Direct URLs to full-resolution image assets
- **Threaded Community Comments** — Modern protobuf `commentEntityPayload` extraction with author info, timestamps, likes, and parent IDs
- **Shared Videos** — Captures linked video attachments inside community posts

### Pipeline Engineering
- **Atomic task queue** — SQLite-backed with `BEGIN IMMEDIATE` transaction locking for race-free parallel workers
- **Full resumability** — Pipeline state persisted to disk; interrupted runs resume exactly where they stopped
- **Deduplication** — Videos and posts are never processed twice unless explicitly forced
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

### Basic Video Scraping

```bash
# Scrape a single video
python main.py scrape -u "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Scrape an entire channel's videos
python main.py scrape -c "https://www.youtube.com/@channelname" --workers 4

# Scrape from a playlist
python main.py scrape -p "https://www.youtube.com/playlist?list=PLxxxxxxx"
```

### Scraping the Community Tab

```bash
# Scrape all community posts, polls, images, and threaded comments
python main.py community -c "https://www.youtube.com/@channelname"

# Scrape latest 50 posts with comments
python main.py community -c "https://www.youtube.com/@channelname" --max-posts 50

# Fast mode: Scrape posts only (skip comments)
python main.py community -c "https://www.youtube.com/@channelname" --skip-comments
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

### `scrape` — Integrated Video Pipeline

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

### `community` — Community Tab Scraper

Scrapes all community posts, polls, images, likes, and full threaded comment trees.

```
python main.py community [OPTIONS]

Options:
  -c, --channel TEXT              YouTube channel URL or Community URL (required)
  --max-posts INTEGER             Maximum number of community posts to scrape
  --extract-comments / --skip-comments
                                  Extract comments and threaded replies (default: True)
  --max-comments INTEGER          Maximum comments to extract per post
  --cookies-file TEXT             Path to cookies file
  --config TEXT                   Path to custom config file
```

```
               Community Scrape Summary: ChannelName               
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric                    ┃ Value                              ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Channel Name              │ ChannelName                        │
│ Total Posts Found         │ 339                                │
│ Successfully Scraped      │ 339 (100%)                         │
│ Failed Posts              │ 0                                  │
│ Total Comments Scraped    │ 2,924                              │
│ Total Polls Found         │ 2                                  │
│ Total Images Found        │ 253                                │
│ Output Directory          │ data\ChannelName\community         │
└───────────────────────────┴────────────────────────────────────┘
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

### `retry-failed` — Retry Failures

Re-processes all videos marked as `failed` in the manifest.

```
python main.py retry-failed --workers 2
```

---

## Output Schema

```
data/
└── {channel_name}/
    ├── community/
    │   ├── community_posts.json         # Master dataset: all posts + comments
    │   ├── summary.json                 # Scrape execution metrics
    │   └── posts/
    │       └── {post_id}/
    │           ├── post_metadata.json   # Text, poll options, HD images, likes
    │           └── comments.json        # Threaded comments for this post
    └── {video_id}/
        ├── video/
        │   └── {video_id}.mp4           # Video stream (merged MP4)
        ├── audio/
        │   └── audio.mp3                # Extracted audio track
        ├── frames/
        │   ├── frame_000001.jpg         # Sampled video frames
        │   └── ...
        ├── metadata/
        │   ├── video_metadata.json      # Structured metadata (25+ fields)
        │   └── description.txt          # Raw video description
        ├── transcript/
        │   ├── en.vtt                   # WebVTT captions
        │   ├── en.srt                   # SubRip captions
        │   ├── en_clean.txt             # Plain text (timestamps stripped)
        │   └── en.json                  # Timed segments with start/end
        ├── comments/
        │   ├── comments.json            # Flat comment records
        │   └── comments_threaded.json   # Nested reply tree hierarchy
        ├── thumbnails/
        │   └── thumbnail.jpg            # Max resolution thumbnail
        └── status.json                  # Pipeline execution log
```

### Community Post Schema (`community_posts.json`)

```json
[
  {
    "post_id": "UgkxhS207wZClLI9KVbY6MKUH8QHQq1prc5i",
    "post_url": "https://www.youtube.com/post/UgkxhS207wZClLI9KVbY6MKUH8QHQq1prc5i",
    "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx",
    "channel_name": "Channel Name",
    "published_time": "6 months ago",
    "text": "What is the most important factor in investing?",
    "likes": "146",
    "poll": {
      "choices": ["Fundamental Analysis (45%)", "Technical Analysis (15%)", "Right Mindset (40%)"],
      "total_votes": "5.9K votes"
    },
    "images": [
      "https://yt3.ggpht.com/..."
    ],
    "shared_video_id": null,
    "comments_count": 48,
    "comments": [
      {
        "comment_id": "Ugwp0uomtLsgivsvrr54AaABAg",
        "parent_id": null,
        "author": "TraderPro",
        "text": "Mindset is definitely 90% of the game!",
        "like_count": 12,
        "published_time": "5 months ago",
        "is_reply": false
      }
    ]
  }
]
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
rate_limit_delay: 2.5       # Seconds between requests per worker

# Video settings
download_video: true
quality_ceiling: "1080p"     # 144p | 360p | 480p | 720p | 1080p | 4k | best
download_thumbnail: true

# Audio extraction
extract_audio: true
audio_format: "mp3"          # mp3 | m4a | wav | flac

# Frame extraction
extract_frames: false
frame_skip: 50               # 1 = every frame, 50 = every 50th frame

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
│   ├── community.py         # YouTube Community Tab, poll, image & comment scraper
│   ├── db.py                # SQLite manifest & atomic task queue
│   ├── metadata.py          # Video metadata & channel/playlist expander
│   ├── downloader.py        # Video, audio, thumbnail & frame extraction
│   ├── transcript.py        # 3-tier caption engine (native → HTTP → translate)
│   ├── comments.py          # Video comment extraction & thread tree builder
│   ├── cookies_manager.py   # Round-robin cookie file rotation
│   ├── organizer.py         # Directory structure & folder manager
│   ├── schemas.py           # Pydantic data models (Video, Comment, Community)
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

---

## ⚠️ Disclaimer & Best Practices

This tool is intended for **research, educational, and archival purposes only**. Scraping YouTube data at scale may violate their Terms of Service. 

YouTube employs anti-bot protections, rate limiting, and IP-level bans (resulting in `HTTP 403 Forbidden` or `Requested format is not available` errors).

**Critical Recommendations for Production Use:**
1. **Pacing and Delays:** Keep `rate_limit_delay` in `config.yaml` at `2.5` to `5.0` seconds to avoid triggering rapid CDN burst-rate limits.
2. **DNS Flushing:** If connection timeouts occur against `googlevideo.com` CDN nodes, flush your local DNS (`ipconfig /flushdns`) or use Google DNS (`8.8.8.8`).
3. **Use Cookie Rotation:** Populate `cookies/` with multiple Netscape-format cookie files for automatic round-robin rotation when scraping restricted/age-gated content.
4. **Resumable Queues:** Always use `produce` and `consume` for large batch scraping to ensure full fault-tolerance and atomic task recovery.

*The author is not responsible for any account bans, IP blocks, or legal repercussions resulting from the use of this software.*

---

## License

MIT
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

