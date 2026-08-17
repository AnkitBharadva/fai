"""Community Tab Scraper for YouTube Channels.

Extracts all community posts, polls, images, likes, metadata, and full threaded comments using YouTube InnerTube API.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
from dataclasses import dataclass, field

from src.schemas import CommentRecord, CommunityPoll, CommunityPost


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class CommunitySummary:
    """Summary statistics for community scraping."""
    channel_name: str = "Unknown"
    channel_url: str = ""
    total_posts_found: int = 0
    posts_scraped_success: int = 0
    posts_scraped_failed: int = 0
    total_comments_extracted: int = 0
    total_images_extracted: int = 0
    total_polls_extracted: int = 0
    output_dir: str = ""
    errors: List[str] = field(default_factory=list)


class CommunityExtractor:
    """Scrapes YouTube Community Posts, Polls, Images, and Threaded Comments."""

    def __init__(self, output_dir: str = "./data", cookies_file: Optional[str] = None):
        self.output_base = Path(output_dir)
        self.cookies_file = cookies_file
        self.logger = logging.getLogger("CommunityScraper")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML with standard browser headers."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self.cookies_file and Path(self.cookies_file).exists():
            try:
                with open(self.cookies_file, "r", encoding="utf-8", errors="ignore") as f:
                    cookie_lines = [
                        line.strip().split("\t")
                        for line in f
                        if line.strip() and not line.startswith("#") and len(line.strip().split("\t")) >= 7
                    ]
                    cookie_str = "; ".join([f"{parts[5]}={parts[6]}" for parts in cookie_lines])
                    if cookie_str:
                        headers["Cookie"] = cookie_str
            except Exception as e:
                self.logger.debug(f"Failed to read cookie file: {e}")

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def _post_innertube(self, endpoint: str, key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON POST request to YouTube InnerTube API."""
        url = f"https://www.youtube.com/youtubei/v1/{endpoint}?key={key}"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))

    def _extract_initial_data(self, html: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[Dict[str, Any]]]:
        """Extract ytInitialData, API key, and INNERTUBE_CONTEXT from HTML."""
        data_match = re.search(r"var\s+ytInitialData\s*=\s*({.+?});</script>", html)
        if not data_match:
            data_match = re.search(r"window\[\"ytInitialData\"\]\s*=\s*({.+?});", html)
        initial_data = json.loads(data_match.group(1)) if data_match else None

        key_match = re.search(r'"INNERTUBE_API_KEY":\s*"([^"]+)"', html)
        api_key = key_match.group(1) if key_match else None

        context_match = re.search(r'"INNERTUBE_CONTEXT":\s*({.+?})\s*,\s*"INNERTUBE', html)
        context = json.loads(context_match.group(1)) if context_match else None

        return initial_data, api_key, context

    def _parse_post_renderer(self, renderer: Dict[str, Any], channel_name: str, channel_id: str) -> Optional[CommunityPost]:
        """Parse a backstagePostRenderer or sharedPostRenderer into CommunityPost model."""
        if not renderer:
            return None

        post_id = renderer.get("postId")
        if not post_id:
            return None
        post_url = f"https://www.youtube.com/post/{post_id}"

        # Text Content
        text_runs = renderer.get("contentText", {}).get("runs", [])
        post_text = "".join([r.get("text", "") for r in text_runs])

        # Published Time & Likes
        published_time = ""
        pub_runs = renderer.get("publishedTimeText", {}).get("runs", [])
        if pub_runs:
            published_time = pub_runs[0].get("text", "")

        likes = renderer.get("voteCount", {}).get("simpleText") or "0"

        # Polls
        poll_model = None
        attachment = renderer.get("backstageAttachment", {})
        if "pollRenderer" in attachment:
            poll = attachment["pollRenderer"]
            choices = []
            for c in poll.get("choices", []):
                t_runs = c.get("text", {}).get("runs", [])
                c_text = "".join([r.get("text", "") for r in t_runs])
                vote_pct = c.get("votePercentage", {}).get("simpleText", "")
                if vote_pct:
                    c_text += f" ({vote_pct})"
                choices.append(c_text)

            total_votes = poll.get("totalVotes", {}).get("simpleText", "")
            poll_model = CommunityPoll(choices=choices, total_votes=total_votes)

        # Images
        images: List[str] = []
        if "backstageImageRenderer" in attachment:
            thumbs = attachment["backstageImageRenderer"].get("image", {}).get("thumbnails", [])
            if thumbs:
                images.append(thumbs[-1].get("url"))
        elif "postMultiImageRenderer" in attachment:
            for img_item in attachment["postMultiImageRenderer"].get("images", []):
                thumbs = img_item.get("backstageImageRenderer", {}).get("image", {}).get("thumbnails", [])
                if thumbs:
                    images.append(thumbs[-1].get("url"))

        # Shared / Attached Video
        shared_vid = None
        if "videoRenderer" in attachment:
            shared_vid = attachment["videoRenderer"].get("videoId")

        return CommunityPost(
            post_id=post_id,
            post_url=post_url,
            channel_id=channel_id,
            channel_name=channel_name,
            published_time=published_time,
            text=post_text,
            likes=likes,
            poll=poll_model,
            images=images,
            shared_video_id=shared_vid,
        )

    def extract_comments_for_post(self, post_id: str, max_comments: Optional[int] = None) -> List[CommentRecord]:
        """Extract comments and threaded replies for a community post using YouTube InnerTube API."""
        post_url = f"https://www.youtube.com/post/{post_id}"
        records: List[CommentRecord] = []
        try:
            html = self._fetch_html(post_url)
            initial_data, api_key, context = self._extract_initial_data(html)
            if not initial_data or not api_key:
                return []

            # Search for initial comment continuation token
            continuation_token = None
            def find_tok(obj: Any) -> None:
                nonlocal continuation_token
                if isinstance(obj, dict):
                    if "continuationCommand" in obj:
                        t = obj["continuationCommand"].get("token")
                        if t and not continuation_token:
                            continuation_token = t
                            return
                    for v in obj.values():
                        find_tok(v)
                        if continuation_token:
                            return
                elif isinstance(obj, list):
                    for it in obj:
                        find_tok(it)
                        if continuation_token:
                            return

            find_tok(initial_data)

            # Paginate through comments
            while continuation_token and (max_comments is None or len(records) < max_comments):
                payload = {
                    "context": context or {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}},
                    "continuation": continuation_token,
                }
                res = self._post_innertube("browse", api_key, payload)
                continuation_token = None

                # 1. Parse modern mutations entityBatchUpdate
                mutations = res.get("frameworkUpdates", {}).get("entityBatchUpdate", {}).get("mutations", [])
                for m in mutations:
                    p = m.get("payload", {})
                    if "commentEntityPayload" in p:
                        cep = p["commentEntityPayload"]
                        c_text = cep.get("properties", {}).get("content", {}).get("content", "")
                        pub_time = cep.get("properties", {}).get("publishedTime", "")
                        author = cep.get("author", {}).get("displayName", "")
                        author_id = cep.get("author", {}).get("channelId", "")
                        cid = cep.get("properties", {}).get("commentId", "") or m.get("entityKey", "")
                        likes_str = cep.get("toolbar", {}).get("likeCountNotliked", "0")
                        
                        # Clean likes
                        try:
                            likes = int(likes_str.replace("K", "000").replace("M", "000000").replace(".", "") or 0)
                        except Exception:
                            likes = 0

                        if c_text or author:
                            records.append(
                                CommentRecord(
                                    comment_id=cid,
                                    parent_id=None,
                                    author=author,
                                    author_channel_id=author_id,
                                    text=c_text,
                                    like_count=likes,
                                    published_time=pub_time,
                                    is_reply=False,
                                )
                            )

                # 2. Parse classic commentRenderer
                endpoints = res.get("onResponseReceivedEndpoints", [])
                for ep in endpoints:
                    cmd = ep.get("appendContinuationItemsAction", {}) or ep.get("reloadContinuationItemsCommand", {})
                    items = cmd.get("continuationItems", [])
                    for it in items:
                        if "commentThreadRenderer" in it:
                            thread = it["commentThreadRenderer"]
                            cr = thread.get("comment", {}).get("commentRenderer", {})
                            if cr:
                                parent_cid = cr.get("commentId", "")
                                text_runs = cr.get("contentText", {}).get("runs", [])
                                c_text = "".join([r.get("text", "") for r in text_runs])
                                author = cr.get("authorText", {}).get("simpleText") or "Anonymous"
                                author_id = cr.get("authorEndpoint", {}).get("browseEndpoint", {}).get("browseId")
                                pub_time = cr.get("publishedTimeText", {}).get("runs", [{}])[0].get("text", "")
                                reply_count = cr.get("replyCount", 0)

                                records.append(
                                    CommentRecord(
                                        comment_id=parent_cid,
                                        parent_id=None,
                                        author=author,
                                        author_channel_id=author_id,
                                        text=c_text,
                                        like_count=0,
                                        published_time=pub_time,
                                        reply_count=reply_count,
                                        is_reply=False,
                                    )
                                )

                        # Find next continuation token in items
                        cont_data = it.get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {})
                        if cont_data.get("token"):
                            continuation_token = cont_data.get("token")

        except Exception as e:
            self.logger.debug(f"Failed to fetch InnerTube comments for post {post_id}: {e}")

        return records

    def scrape_channel_community(
        self,
        channel_url: str,
        max_posts: Optional[int] = None,
        extract_comments: bool = True,
        max_comments_per_post: Optional[int] = None,
    ) -> Tuple[List[CommunityPost], CommunitySummary]:
        """Scrape all community posts from a channel URL with full metadata, images, polls, and comments."""
        clean_url = channel_url.rstrip("/")
        if not clean_url.endswith("/community"):
            community_url = f"{clean_url}/community"
        else:
            community_url = clean_url

        summary = CommunitySummary(channel_url=channel_url)
        self.logger.info(f"Connecting to YouTube Community tab: {community_url}")

        try:
            html = self._fetch_html(community_url)
        except Exception as e:
            err = f"Failed to connect to channel community page: {e}"
            self.logger.error(err)
            summary.errors.append(err)
            return [], summary

        initial_data, api_key, context = self._extract_initial_data(html)
        if not initial_data:
            err = "Could not parse initial YouTube data from page."
            self.logger.error(err)
            summary.errors.append(err)
            return [], summary

        # Extract Channel Header info
        header = initial_data.get("header", {}).get("pageHeaderRenderer", {}) or initial_data.get("header", {}).get("c4TabbedHeaderRenderer", {})
        channel_name = (
            header.get("pageTitle")
            or header.get("title")
            or initial_data.get("microformat", {}).get("microformatDataRenderer", {}).get("title")
            or "Unknown_Channel"
        )
        channel_id = initial_data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId") or "unknown_channel"
        summary.channel_name = channel_name

        safe_name = re.sub(r'[\\/*?:"<>|]', "_", channel_name).strip()
        channel_dir = self.output_base / safe_name / "community"
        channel_dir.mkdir(parents=True, exist_ok=True)
        summary.output_dir = str(channel_dir)

        # Collect initial posts and continuation token recursively
        posts_collected: List[CommunityPost] = []
        seen_post_ids = set()
        continuation_token = None

        def extract_items_and_token(obj: Any) -> None:
            nonlocal continuation_token
            if isinstance(obj, dict):
                # Check for post renderer
                renderer = obj.get("backstagePostThreadRenderer", {}).get("post", {}).get("backstagePostRenderer")
                if not renderer:
                    renderer = obj.get("backstagePostThreadRenderer", {}).get("post", {}).get("sharedPostRenderer")
                if not renderer:
                    renderer = obj.get("backstagePostRenderer") or obj.get("sharedPostRenderer")

                if renderer:
                    post = self._parse_post_renderer(renderer, channel_name, channel_id)
                    if post and post.post_id not in seen_post_ids:
                        seen_post_ids.add(post.post_id)
                        posts_collected.append(post)

                # Check for continuation item
                if "continuationItemRenderer" in obj:
                    tok = obj["continuationItemRenderer"].get("continuationEndpoint", {}).get("continuationCommand", {}).get("token")
                    if tok:
                        continuation_token = tok

                for v in obj.values():
                    extract_items_and_token(v)
            elif isinstance(obj, list):
                for it in obj:
                    extract_items_and_token(it)

        # Process initial page
        extract_items_and_token(initial_data)

        # Follow continuation tokens for complete channel post history
        while continuation_token and api_key and (max_posts is None or len(posts_collected) < max_posts):
            try:
                self.logger.info(f"Paginating community posts (Found {len(posts_collected)} so far)...")
                payload = {
                    "context": context or {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}},
                    "continuation": continuation_token,
                }
                continuation_token = None
                res = self._post_innertube("browse", api_key, payload)

                extract_items_and_token(res)

            except Exception as ex:
                self.logger.warning(f"Error during continuation pagination: {ex}")
                break

        if max_posts and len(posts_collected) > max_posts:
            posts_collected = posts_collected[:max_posts]

        summary.total_posts_found = len(posts_collected)
        self.logger.info(f"Total community post(s) collected: {len(posts_collected)}. Processing details...")

        # Process comments and aggregate stats for each post
        final_posts: List[CommunityPost] = []
        for idx, post in enumerate(posts_collected, start=1):
            try:
                self.logger.info(f"[{idx}/{len(posts_collected)}] Scraping Post: {post.post_id} ({post.published_time})")

                if post.poll:
                    summary.total_polls_extracted += 1
                if post.images:
                    summary.total_images_extracted += len(post.images)

                if extract_comments:
                    self.logger.info(f"    Fetching comments for post {post.post_id}...")
                    comments = self.extract_comments_for_post(post.post_id, max_comments=max_comments_per_post)
                    post.comments = comments
                    post.comments_count = len(comments)
                    summary.total_comments_extracted += len(comments)

                final_posts.append(post)
                summary.posts_scraped_success += 1

            except Exception as e:
                self.logger.error(f"Failed processing post {post.post_id}: {e}")
                summary.posts_scraped_failed += 1
                summary.errors.append(f"Post {post.post_id}: {str(e)}")

        # Save to JSON outputs
        self._save_results(final_posts, channel_dir, summary)
        return final_posts, summary

    def _save_results(self, posts: List[CommunityPost], output_dir: Path, summary: CommunitySummary) -> None:
        """Save posts to structured JSON, summary JSON, and individual post directories."""
        output_dir.mkdir(parents=True, exist_ok=True)

        all_posts_file = output_dir / "community_posts.json"
        posts_data = [p.model_dump() for p in posts]
        with open(all_posts_file, "w", encoding="utf-8") as f:
            json.dump(posts_data, f, indent=2, ensure_ascii=False)

        posts_dir = output_dir / "posts"
        posts_dir.mkdir(exist_ok=True)

        for post in posts:
            p_folder = posts_dir / post.post_id
            p_folder.mkdir(exist_ok=True)

            meta_file = p_folder / "post_metadata.json"
            post_dict = post.model_dump()
            comments_data = post_dict.pop("comments", [])
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(post_dict, f, indent=2, ensure_ascii=False)

            if comments_data:
                comm_file = p_folder / "comments.json"
                with open(comm_file, "w", encoding="utf-8") as f:
                    json.dump(comments_data, f, indent=2, ensure_ascii=False)

        summary_file = output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "channel_name": summary.channel_name,
                "channel_url": summary.channel_url,
                "total_posts_found": summary.total_posts_found,
                "posts_scraped_success": summary.posts_scraped_success,
                "posts_scraped_failed": summary.posts_scraped_failed,
                "total_comments_extracted": summary.total_comments_extracted,
                "total_images_extracted": summary.total_images_extracted,
                "total_polls_extracted": summary.total_polls_extracted,
                "output_dir": summary.output_dir,
                "errors": summary.errors,
            }, f, indent=2)

        self.logger.info(f"Saved complete community data to: {output_dir}")
