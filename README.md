# YouTube Video Scraper & Archival Tool

Production-grade, scalable YouTube video scraper and archival system built with **Producer-Consumer Multi-Agent Orchestration**, **Rotated Cookies Support**, `yt-dlp`, `FFmpeg`, `Pydantic`, `SQLite (WAL)`, `Click`, and `Rich`.

---

## Features

- **Producer-Consumer Multi-Agent Architecture**:
  - **Producer Agent** (`python main.py produce`): Enumerate channels/playlists/URLs and enqueues video tasks into an atomic SQLite task queue.
  - **Consumer Worker Agents** (`python main.py consume`): Concurrent worker agents pull pending tasks atomically from the queue and process video pipelines in parallel.
- **Rotated Cookies Pool**:
  - Automatically loads and rotates cookie files from [`D:\fai\cookies\`](file:///D:/fai/cookies) (`jaman.txt`, `magan.txt`).
  - Distributes extraction requests across cookie files to bypass rate limits, age restrictions, and bot detection.
- **Custom Quality & Audio Extraction**:
  - Download videos in any specified resolution (`144p`, `360p`, `480p`, `720p`, `1080p`, `4k`, `best`).
  - Extract high-quality audio (`audio.mp3`) into a separate `audio/` directory.
- **FFmpeg Frame Extraction**:
  - Extract image frames from downloaded videos with custom frame-skipping steps (`frames/frame_000001.jpg`).
- **Full Archival & Transcripts**:
  - Transcripts exported in WebVTT, SRT, JSON, and clean plain-text with English translation fallbacks.
  - Complete comment threads and nested replies.

---

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd fai
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your settings:
```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your preferences
```

4. Add your YouTube cookies (optional but recommended):
   - Export cookies from your browser using a cookie extension
   - Save as `.txt` files in the `cookies/` folder
   - Files will be automatically rotated during scraping

---

## Directory Structure

```
data/
└── {channel_id}/
    └── {video_id}/
        ├── video/
        │   └── {video_id}.mp4
        ├── audio/
        │   └── audio.mp3
        ├── frames/
        │   ├── frame_000001.jpg
        │   └── ...
        ├── metadata/
        │   ├── video_metadata.json
        │   └── description.txt
        ├── transcript/
        │   ├── en.srt
        │   ├── en.vtt
        │   ├── en_clean.txt
        │   └── ...
        ├── comments/
        │   ├── comments.json
        │   ├── comments_threaded.json
        │   └── comments.csv
        ├── thumbnails/
        │   └── thumbnail.jpg
        └── status.json
cookies/          # ⚠️ Not tracked in git (contains sensitive auth data)
├── jaman.txt
└── magan.txt
manifest.db       # Task queue database
logs/
└── scraper.log
```

---

## Quick Start (Producer-Consumer Multi-Agent Orchestration)

### 1. Integrated Producer-Consumer Command (Default)
Scrapes a channel end-to-end by discovering videos and running consumer worker agents:
```bash
python main.py scrape --channel "https://www.youtube.com/@ChannelHandle" --workers 4
```

### 2. Discoupled Producer-Consumer Mode

#### Step A: Run Producer Agent (Enqueues Tasks)
```bash
python main.py produce --channel "https://www.youtube.com/@ChannelHandle" --max-videos 100
```

#### Step B: Run Consumer Worker Agents (Processes Queue)
Launch parallel consumer workers pulling tasks atomically from the queue:
```bash
python main.py consume --workers 4
```

---

## Cookies Management

⚠️ **Security Note**: Cookie files contain sensitive authentication data and are excluded from git via `.gitignore`.

Cookie files uploaded to `cookies/` (e.g. `jaman.txt` and `magan.txt`) are automatically detected and rotated round-robin across extraction calls.

**How to export cookies:**
1. Install a browser extension like "Get cookies.txt LOCALLY" or "cookies.txt"
2. Visit YouTube while logged in
3. Export cookies to a `.txt` file
4. Save the file in the `cookies/` folder

You can also specify a custom cookies directory or file via CLI:
```bash
python main.py scrape --channel "..." --cookies-dir "./cookies"
```

---

## Running Tests

```bash
pytest -v
```

---

## Requirements

- Python 3.8+
- FFmpeg (for video processing and frame extraction)
- yt-dlp (for YouTube downloading)

---

## Security & Privacy

- `cookies/` folder is excluded from git tracking
- `config.yaml` with sensitive settings is excluded from git
- Only `config.example.yaml` is tracked as a template
- Never commit authentication tokens or personal data
