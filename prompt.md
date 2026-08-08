# Build Prompt: YouTube Video Scraper (yt-dlp based)

## Role

You are an expert Python engineer building a production-grade, scalable YouTube
scraping and archival tool. Use `yt-dlp` as the core extraction/download engine
(preferably via its Python API, `import yt_dlp`, rather than shelling out to the
CLI, so we get structured data and proper error handling). Verify current
`yt-dlp` option names against its latest documentation/changelog before relying
on them — flag names and extractor-args occasionally change between releases.

## Project Overview

Build a tool that, given one or more YouTube video URLs, a playlist URL, a
channel URL, or a text file of URLs, downloads the video at the highest
available quality and archives everything associated with it — metadata,
description, transcript/captions, and the full comment thread with comment
metadata — into a clean, scalable, per-video folder structure. The tool must
be safe to run against large batches (hundreds/thousands of videos) without
breaking, getting rate-limited, or losing progress on failure.

## Goals / Success Criteria

- [ ] Given a single video URL, the tool produces a complete, correctly
      structured output folder (see Data & Folder Structure) with video,
      metadata, description, transcript, and comments all populated.
- [ ] Given a channel or playlist URL, the tool enumerates and processes every
      video, skipping ones already completed on a re-run.
- [ ] A killed/interrupted run can be resumed without re-downloading completed
      videos or re-fetching completed data.
- [ ] Comments (including nested replies) are captured with full metadata, not
      just top-level comment text.
- [ ] Transcripts are captured for manual captions when available, falling
      back to auto-generated captions, in multiple languages if present.
- [ ] The tool logs progress, errors, and a final summary report (success /
      failed / skipped counts) for every run.
- [ ] Failures on individual videos do not crash the batch; they are logged
      and retryable.

## Tech Stack

- Python 3.11+
- `yt-dlp` (core extraction and download engine)
- `pydantic` for data schemas/validation of metadata and comment records
- `SQLite` (via `sqlalchemy` or stdlib `sqlite3`) as a run manifest/index for
  tracking status per video (pending / in_progress / done / failed) and
  enabling resumability and dedup
- `typer` or `click` for the CLI
- `tenacity` for retry/backoff logic
- `rich` or `tqdm` for progress display
- `PyYAML` for config file loading
- stdlib `logging` with a rotating file handler + console handler

## Functional Requirements

### 1. Input Handling

- Accept: a single video URL/ID, a list of URLs on the command line, a
  playlist URL, a channel URL, or a path to a text file with one URL/ID per
  line.
- Normalize all inputs to canonical video IDs before processing.
- Deduplicate inputs.

### 2. Video Download

- Download the highest quality available (best video + best audio, merged),
  with a configurable resolution ceiling (e.g. cap at 1080p/4K) and graceful
  fallback if the requested quality isn't available.
- Merge output to `.mp4` where possible.
- Support an audio-only mode via config flag.
- Also save the video thumbnail.

### 3. Video Metadata

Capture and persist (as structured JSON, validated against a pydantic model)
at minimum:
`video_id`, `title`, `channel_id`, `channel_name`, `upload_date`, `duration`,
`view_count`, `like_count`, `comment_count`, `tags`, `categories`, `language`,
`availability`, `is_live`/`was_live`, `chapters`, `thumbnail_url`,
`available_subtitle_languages`, `age_limit`, `license`, `original_url`.

### 4. Description

- Save the raw video description as `description.txt`.
- Also embed it as a field in the metadata JSON for convenience.

### 5. Transcript / Captions

- Prefer manually-created captions; fall back to auto-generated captions if
  no manual captions exist.
- If multiple languages are available, save each.
- Persist in three forms per language: raw `.srt`, raw `.vtt`, and a cleaned
  plain-text version with timestamps and formatting stripped (for easy
  downstream NLP use).

### 6. Comments and Comment Metadata

- Fetch **all** comments (not just a default-limited page) — configure
  `yt-dlp`'s comment extraction to remove/raise the default max-comments cap,
  confirming current option syntax in the yt-dlp docs.
- For each comment capture: `comment_id`, `parent_id` (null for top-level),
  `author`, `author_channel_id`, `text`, `like_count`, `published_time`,
  `is_favorited`, `reply_count`, `is_reply` (bool).
- Preserve the parent/reply relationship (flat list with `parent_id` is fine;
  optionally also emit a nested/threaded JSON view for readability).
- Handle videos with comments disabled gracefully (log and continue, don't
  fail the whole video).
- Save as both `comments.json` (full fidelity) and `comments.csv` (flat, for
  quick analysis).

### 7. Data & Folder Structure

Organize output so it scales to many channels/videos without a single
directory becoming unwieldy, and so any single video's data is self-contained:

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
        └── status.json          # per-video processing state/timestamps
manifest.db                      # SQLite index across all videos (see below)
logs/
└── run_{timestamp}.log
```

The `manifest.db` SQLite index should track, per video: `video_id`,
`channel_id`, `status`, `last_attempt_at`, `completed_at`, `retry_count`,
`error_message`. This is the source of truth for resumability — on every run,
skip videos already marked `done` unless `--force` is passed.

### 8. CLI Design

Design commands roughly like:

```
python main.py scrape --url <video_url>
python main.py scrape --channel <channel_url> --max-videos 50
python main.py scrape --playlist <playlist_url>
python main.py scrape --file urls.txt --workers 4
python main.py status                 # summary of manifest.db
python main.py retry-failed
```

Config (output directory, worker count, quality cap, cookies file path,
rate-limit/sleep interval, comment limits, subtitle languages) should live in
a `config.yaml`, with CLI flags able to override it.

## Non-Functional Requirements

- **Concurrency & rate limiting**: configurable worker pool, with a
  configurable delay/jitter between requests to avoid triggering YouTube
  rate limits or IP blocks. Don't hammer the API.
- **Retries**: exponential backoff (via `tenacity`) on transient
  network/extraction errors; permanent errors (video deleted/private) should
  be logged and skipped, not retried indefinitely.
- **Resumability**: safe to kill and re-run at any point; already-completed
  videos are skipped based on the manifest.
- **Auth/restricted content**: support passing a cookies file (for
  age-restricted or member-only videos) via config.
- **Logging**: structured logs to console and a rotating log file; a final
  run summary (counts of success/failed/skipped, total runtime).
- **Modularity**: separate modules for downloading, metadata extraction,
  transcript extraction, comment extraction, storage/manifest management, and
  the CLI orchestrator — not one monolithic script.
- **Type hints and docstrings** throughout.
- **Tests**: unit tests for parsing/transform logic (e.g. cleaning
  transcripts, flattening comments), using recorded/mocked yt-dlp output
  rather than live network calls.

## Deliverables

- Full repo matching the module breakdown above.
- `requirements.txt` or `pyproject.toml`.
- `config.example.yaml`.
- `README.md` with setup and usage instructions, including a note that this
  tool should be used in compliance with YouTube's Terms of Service and
  applicable law, and that the built-in rate limiting exists to be a
  respectful, non-abusive client.
- Basic test suite (`pytest`).

## Suggested Build Order

1. Scaffold repo structure and config loader.
2. Build the storage/manifest module (folder creation + SQLite index) first,
   since everything else writes through it.
3. Build the single-video extractor module: metadata + description +
   transcript (thin, well-tested wrapper around `yt_dlp.YoutubeDL`).
4. Build the comment extractor module.
5. Build the video downloader module.
6. Build the CLI orchestrator: input resolution → worker pool → per-video
   pipeline → manifest updates → summary report.
7. Add retry/backoff and rate limiting.
8. Write README + tests.
9. Dry-run against a single real video, verify every output file, then test
   against a small playlist before scaling up.

## Notes for the Agent

- Confirm exact `yt-dlp` API/extractor-arg names (e.g. for uncapping comment
  count, subtitle language selection) against the currently installed
  `yt-dlp` version's docs — do not assume flags from memory are still
  correct.
- Prefer the Python API (`yt_dlp.YoutubeDL`) over subprocess calls to the CLI
  binary, for better error handling and structured data access.
- Ask before making structural decisions not covered here (e.g. exact
  database choice beyond SQLite for very large scale) rather than guessing
  silently.