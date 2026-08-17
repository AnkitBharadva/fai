"""Pydantic data schemas for video metadata, comments, and manifest records."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChapterRecord(BaseModel):
    """Model representing a YouTube video chapter."""
    start_time: float
    end_time: float
    title: str


class VideoMetadata(BaseModel):
    """Pydantic model validating complete YouTube video metadata."""
    video_id: str
    title: str
    channel_id: Optional[str] = "unknown_channel"
    channel_name: Optional[str] = "Unknown Channel"
    upload_date: Optional[str] = None
    duration: Optional[float] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    language: Optional[str] = None
    availability: Optional[str] = None
    is_live: bool = False
    was_live: bool = False
    chapters: List[ChapterRecord] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    available_subtitle_languages: List[str] = Field(default_factory=list)
    age_limit: Optional[int] = 0
    license: Optional[str] = None
    original_url: str
    description: Optional[str] = ""
    extra_info: Dict[str, Any] = Field(default_factory=dict)


class CommentRecord(BaseModel):
    """Pydantic model validating a single comment or reply record."""
    comment_id: str
    parent_id: Optional[str] = None  # None for top-level comment
    author: Optional[str] = "Anonymous"
    author_channel_id: Optional[str] = None
    text: str
    like_count: int = 0
    published_time: Optional[str] = None
    is_favorited: bool = False
    reply_count: int = 0
    is_reply: bool = False


class CommentThread(BaseModel):
    """Nested model for threaded view of comments."""
    comment: CommentRecord
    replies: List["CommentThread"] = Field(default_factory=list)


CommentThread.model_rebuild()


class ManifestRecord(BaseModel):
    """Database manifest tracking record."""
    video_id: str
    channel_id: Optional[str] = "unknown_channel"
    status: str = "pending"  # pending, in_progress, done, failed
    last_attempt_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    error_message: Optional[str] = None


class CommunityPoll(BaseModel):
    """Pydantic model for community post polls."""
    choices: List[str] = Field(default_factory=list)
    total_votes: Optional[str] = None


class CommunityPost(BaseModel):
    """Pydantic model for full YouTube community post metadata and comments."""
    post_id: str
    post_url: str
    channel_id: Optional[str] = "unknown_channel"
    channel_name: Optional[str] = "Unknown Channel"
    published_time: Optional[str] = None
    text: str = ""
    likes: Optional[str] = "0"
    poll: Optional[CommunityPoll] = None
    images: List[str] = Field(default_factory=list)
    shared_video_id: Optional[str] = None
    comments_count: int = 0
    comments: List[CommentRecord] = Field(default_factory=list)

