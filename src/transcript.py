"""Transcript / Subtitle extraction, fast batch translation, and cleaning module."""

import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
import yt_dlp
from src.utils import extract_video_id


def format_seconds_to_srt_time(seconds: float) -> str:
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    secs = int(seconds) % 60
    mins = (int(seconds) // 60) % 60
    hours = int(seconds) // 3600
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_seconds_to_vtt_time(seconds: float) -> str:
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    secs = int(seconds) % 60
    mins = (int(seconds) // 60) % 60
    hours = int(seconds) // 3600
    return f"{hours:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


def segments_to_vtt(segments: List[Dict[str, Any]]) -> str:
    lines = ["WEBVTT\n"]
    for idx, seg in enumerate(segments, 1):
        start = float(seg.get("start", 0.0))
        duration = float(seg.get("duration", 0.0))
        end = start + duration
        text = str(seg.get("text", "")).strip()
        lines.append(f"{idx}")
        lines.append(f"{format_seconds_to_vtt_time(start)} --> {format_seconds_to_vtt_time(end)}")
        lines.append(f"{text}\n")
    return "\n".join(lines)


def segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, seg in enumerate(segments, 1):
        start = float(seg.get("start", 0.0))
        duration = float(seg.get("duration", 0.0))
        end = start + duration
        text = str(seg.get("text", "")).strip()
        lines.append(f"{idx}")
        lines.append(f"{format_seconds_to_srt_time(start)} --> {format_seconds_to_srt_time(end)}")
        lines.append(f"{text}\n")
    return "\n".join(lines)


def segments_to_clean_text(segments: List[Dict[str, Any]]) -> str:
    seen = set()
    cleaned = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        cleaned_text = re.sub(r"<[^>]+>", "", text).strip()
        if cleaned_text and cleaned_text not in seen:
            cleaned.append(cleaned_text)
            seen.add(cleaned_text)
    return "\n".join(cleaned)


def clean_subtitle_text(vtt_or_srt_content: str) -> str:
    """Clean VTT/SRT content into plain text with timestamps and formatting tags removed."""
    lines = vtt_or_srt_content.splitlines()
    cleaned_lines: List[str] = []
    seen_lines = set()

    for line in lines:
        line_str = line.strip()

        if not line_str or line_str.startswith("WEBVTT") or line_str.startswith("Kind:") or line_str.startswith("Language:"):
            continue

        if re.match(r"^\d+$", line_str):
            continue

        if "-->" in line_str:
            continue

        cleaned = re.sub(r"<[^>]+>", "", line_str).strip()
        if not cleaned:
            continue

        if cleaned not in seen_lines:
            cleaned_lines.append(cleaned)
            seen_lines.add(cleaned)

    return "\n".join(cleaned_lines)


def translate_segments(segments: List[Dict[str, Any]], target_lang: str = "en") -> List[Dict[str, Any]]:
    """Translate list of transcript segments into target_lang using translate_batch."""
    try:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="auto", target=target_lang)

        # Batch in groups of 100 segments for maximum speed
        batch_size = 100
        translated_segments: List[Dict[str, Any]] = []

        # Cap max segments to translate at 300 to keep execution fast
        segments_to_translate = segments[:300]

        for i in range(0, len(segments_to_translate), batch_size):
            batch = segments_to_translate[i : i + batch_size]
            texts = [str(s.get("text", "")).strip() for s in batch]
            valid_texts = [t if t else "..." for t in texts]

            try:
                translated_texts = translator.translate_batch(valid_texts)
            except Exception:
                translated_texts = texts

            for j, seg in enumerate(batch):
                trans_text = translated_texts[j] if j < len(translated_texts) else str(seg.get("text", "")).strip()
                translated_segments.append({
                    "start": seg.get("start", 0.0),
                    "duration": seg.get("duration", 0.0),
                    "text": trans_text,
                })

        # Append remaining untranslated segments if any
        for seg in segments[300:]:
            translated_segments.append(seg)

        return translated_segments
    except Exception:
        return segments


class TranscriptExtractor:
    """Extracts, formats, translates, and saves YouTube subtitles and transcripts."""

    def __init__(self, cookies_file: Optional[str] = None):
        self.cookies_file = cookies_file

    def _save_segment_transcript(self, segments: List[Dict[str, Any]], lang_code: str, transcript_dir: Path) -> None:
        """Helper to save segments into .vtt, .srt, _clean.txt, and .json."""
        vtt_content = segments_to_vtt(segments)
        with open(transcript_dir / f"{lang_code}.vtt", "w", encoding="utf-8") as f:
            f.write(vtt_content)

        srt_content = segments_to_srt(segments)
        with open(transcript_dir / f"{lang_code}.srt", "w", encoding="utf-8") as f:
            f.write(srt_content)

        clean_content = segments_to_clean_text(segments)
        with open(transcript_dir / f"{lang_code}_clean.txt", "w", encoding="utf-8") as f:
            f.write(clean_content)

        with open(transcript_dir / f"{lang_code}.json", "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)

    def extract_and_save_transcripts(
        self,
        video_url: str,
        transcript_dir: Path,
        target_languages: Optional[List[str]] = None,
        prefer_manual: bool = True,
    ) -> List[str]:
        """Fetch manual or auto-generated captions, translate to target languages if needed, and save."""
        transcript_dir.mkdir(parents=True, exist_ok=True)
        video_id = extract_video_id(video_url)

        if not target_languages:
            target_languages = ["en", "auto"]

        processed_langs: List[str] = []
        base_segments: List[Dict[str, Any]] = []

        # TIER 1: Native yt-dlp caption extraction with curl_cffi impersonate
        try:
            clean_langs = [tl for tl in (target_languages or ["en"]) if tl != "auto"]
            if not clean_langs:
                clean_langs = ["en", "hi"]
            sub_langs = list(set(clean_langs + ["all"]))
            opts: Dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": sub_langs,
                "js_runtimes": {"node": {}},
                "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "android_vr"]}},
            }
            if self.cookies_file and Path(self.cookies_file).exists():
                opts["cookiefile"] = self.cookies_file

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if info:
                    subtitles = info.get("subtitles") or {}
                    auto_captions = info.get("automatic_captions") or {}

                    all_tracks = {}
                    for lc, trs in auto_captions.items():
                        all_tracks[lc] = trs
                    if prefer_manual:
                        for lc, trs in subtitles.items():
                            all_tracks[lc] = trs

                    for lc, trs in all_tracks.items():
                        # Strict language filter: English (en) and Hindi (hi) ONLY
                        if not any(lc.startswith(prefix) for prefix in ["en", "hi"]):
                            continue

                        sub_url = None
                        for t in trs:
                            if t.get("ext") in ["vtt", "srt", "json3"]:
                                sub_url = t.get("url")
                                break
                        if not sub_url and trs:
                            sub_url = trs[0].get("url")

                        if not sub_url:
                            continue

                        try:
                            from curl_cffi import requests as cffi_requests
                            resp = cffi_requests.get(
                                sub_url,
                                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                                impersonate="chrome120",
                                timeout=10,
                            )
                            raw_data = resp.text
                            if not raw_data or resp.status_code != 200:
                                continue

                            clean_code = re.sub(r"[^a-zA-Z0-9_-]", "_", lc)
                            if raw_data.strip().startswith("{"):
                                parsed_json = json.loads(raw_data)
                                events = parsed_json.get("events", [])
                                segments = []
                                for ev in events:
                                    seg_text = "".join(
                                        s.get("utf8", "") for s in ev.get("segs", []) if s.get("utf8")
                                    )
                                    if seg_text.strip():
                                        segments.append({
                                            "start": ev.get("tStartMs", 0) / 1000.0,
                                            "duration": ev.get("dDurationMs", 0) / 1000.0,
                                            "text": seg_text,
                                        })
                                if segments:
                                    self._save_segment_transcript(segments, clean_code, transcript_dir)
                                    processed_langs.append(clean_code)
                                    if not base_segments:
                                        base_segments = segments
                            else:
                                clean_content = clean_subtitle_text(raw_data)
                                with open(transcript_dir / f"{clean_code}.vtt", "w", encoding="utf-8") as f:
                                    f.write(raw_data)
                                with open(transcript_dir / f"{clean_code}.srt", "w", encoding="utf-8") as f:
                                    f.write(raw_data)
                                with open(transcript_dir / f"{clean_code}_clean.txt", "w", encoding="utf-8") as f:
                                    f.write(clean_content)
                                processed_langs.append(clean_code)
                        except Exception:
                            continue
        except Exception:
            pass

        # TIER 2: Try yt-dlp if base_segments not found yet
        if not base_segments:
            sub_langs = ["en", "hi", "en-orig", "hi-orig"]
            opts: Dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": sub_langs,
                "js_runtimes": {"node": {}},
                "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "android_vr"]}},
            }
            if self.cookies_file and Path(self.cookies_file).exists():
                opts["cookiefile"] = self.cookies_file

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    if info:
                        subtitles = info.get("subtitles") or {}
                        auto_captions = info.get("automatic_captions") or {}

                        all_tracks = {}
                        for lc, trs in auto_captions.items():
                            all_tracks[lc] = trs
                        if prefer_manual:
                            for lc, trs in subtitles.items():
                                all_tracks[lc] = trs

                        for lc, trs in all_tracks.items():
                            # Strict language filter: English (en) and Hindi (hi) ONLY
                            if not any(lc.startswith(prefix) for prefix in ["en", "hi"]):
                                continue

                            sub_url = None
                            for t in trs:
                                if t.get("ext") in ["vtt", "srt", "json3"]:
                                    sub_url = t.get("url")
                                    break
                            if not sub_url and trs:
                                sub_url = trs[0].get("url")

                            if not sub_url:
                                continue

                            try:
                                try:
                                    from curl_cffi import requests as cffi_requests
                                    resp = cffi_requests.get(
                                        sub_url,
                                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                                        impersonate="chrome120",
                                        timeout=15,
                                    )
                                    raw_data = resp.text
                                except Exception:
                                    req = urllib.request.Request(
                                        sub_url,
                                        headers={
                                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                        },
                                    )
                                    with urllib.request.urlopen(req) as resp:
                                        raw_data = resp.read().decode("utf-8", errors="ignore")

                                clean_code = re.sub(r"[^a-zA-Z0-9_-]", "_", lc)
                                if raw_data.strip().startswith("{"):
                                    parsed_json = json.loads(raw_data)
                                    events = parsed_json.get("events", [])
                                    segments = []
                                    for ev in events:
                                        seg_text = "".join(
                                            s.get("utf8", "") for s in ev.get("segs", []) if s.get("utf8")
                                        )
                                        if seg_text.strip():
                                            segments.append({
                                                "start": ev.get("tStartMs", 0) / 1000.0,
                                                "duration": ev.get("dDurationMs", 0) / 1000.0,
                                                "text": seg_text,
                                            })
                                    if segments:
                                        self._save_segment_transcript(segments, clean_code, transcript_dir)
                                        processed_langs.append(clean_code)
                                        if not base_segments:
                                            base_segments = segments
                                else:
                                    clean_content = clean_subtitle_text(raw_data)
                                    with open(transcript_dir / f"{clean_code}.vtt", "w", encoding="utf-8") as f:
                                        f.write(raw_data)
                                    with open(transcript_dir / f"{clean_code}.srt", "w", encoding="utf-8") as f:
                                        f.write(raw_data)
                                    with open(transcript_dir / f"{clean_code}_clean.txt", "w", encoding="utf-8") as f:
                                        f.write(clean_content)
                                    processed_langs.append(clean_code)
                            except Exception:
                                continue
            except Exception:
                pass

        # TIER 3: Ensure English (en) and Hindi (hi) transcripts exist if base_segments are available
        if not any(l.startswith("en") for l in processed_langs) and base_segments:
            en_segments = translate_segments(base_segments, target_lang="en")
            if en_segments:
                self._save_segment_transcript(en_segments, "en", transcript_dir)
                processed_langs.append("en")

        if not any(l.startswith("hi") for l in processed_langs) and base_segments:
            hi_segments = translate_segments(base_segments, target_lang="hi")
            if hi_segments:
                self._save_segment_transcript(hi_segments, "hi", transcript_dir)
                processed_langs.append("hi")

        return processed_langs
