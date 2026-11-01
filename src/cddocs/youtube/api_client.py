"""YouTube Data API v3 Client with retry, quota tracking, and input validation."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .config import YouTubeConfig
from .token_manager import TokenManager

logger = logging.getLogger(__name__)

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# YouTube API v3 quota costs (approximate, per Google documentation)
QUOTA_COSTS = {
    "videos.insert": 1600,
    "videos.list": 1,
    "videos.update": 50,
    "channels.list": 1,
    "playlistItems.list": 1,
    "search.list": 100,
}


class YouTubeAPIClient:
    """Client for YouTube Data API v3.

    Features:
    - Exponential backoff retry for transient errors
    - No retry on 401 (auth) or 403 (quota/forbidden)
    - Input validation on all public methods
    - Selected channel awareness
    """

    def __init__(self, token_manager: TokenManager, config: Optional[YouTubeConfig] = None):
        self.token_manager = token_manager
        self.config = config or YouTubeConfig()
        self.service = self._build_service()
        self._quota_used_today: int = 0

    def _build_service(self) -> Any:
        """Build the YouTube API service object."""
        self.token_manager.refresh_if_needed()
        credentials = self.token_manager.get_credentials()
        if credentials is None:
            raise ValueError(
                "Valid YouTube credentials not available. "
                "Run OAuth flow first or check YOUTUBE_CLIENT_ID/SECRET."
            )

        return build(
            self.config.api_service_name,
            self.config.api_version,
            credentials=credentials,
        )

    @staticmethod
    def _validate_required(**kwargs) -> None:
        """Validate that required arguments are not None or empty string."""
        for name, value in kwargs.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Required argument '{name}' cannot be empty")

    def _retry_on_error(self, func, *args, **kwargs):
        """Retry transient API errors up to MAX_RETRIES times.

        Does NOT retry on 401 (auth error) or 403 (quota/forbidden).
        Uses exponential backoff with jitter.
        """
        max_retries = self.config.max_retries
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                last_exception = e
                status = e.resp.status if hasattr(e, "resp") else None

                # Never retry on auth or quota errors
                if status in (401, 403):
                    logger.error(
                        "YouTube API error (status %s): %s", status, str(e)[:200]
                    )
                    raise

                if attempt < max_retries:
                    wait = (2 ** attempt) + 0.1 * attempt  # exponential + jitter
                    logger.warning(
                        "YouTube API retry %d/%d after %.1fs: %s",
                        attempt,
                        max_retries,
                        wait,
                        str(e)[:200],
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "YouTube API failed after %d attempts: %s",
                        max_retries,
                        str(e)[:200],
                    )
                    raise
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    wait = (2 ** attempt) + 0.1 * attempt
                    logger.warning(
                        "Unexpected error retry %d/%d after %.1fs: %s",
                        attempt,
                        max_retries,
                        wait,
                        str(e)[:200],
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Unexpected error after %d attempts: %s",
                        max_retries,
                        str(e)[:200],
                    )
                    raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Unknown API error")

    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = "unlisted",
        category_id: str = "15",
        confirm_public: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Upload a YouTube video (Short or regular).

        Args:
            video_path: Path to the MP4 video file
            title: Video title
            description: Video description (disclosure will be appended)
            tags: List of tags
            privacy_status: "public", "private", or "unlisted"
            category_id: YouTube category ID (default "15" = Pets & Animals)
            confirm_public: Must be True to upload as "public"
            progress_callback: Optional callback(uploaded_bytes, total_bytes)

        Returns:
            Dict with video_id, video_url, view_url, and status
        """
        # 1. Validate required fields
        self._validate_required(video_path=video_path, title=title, description=description)

        # 2. Validate privacy_status value
        if privacy_status not in ("public", "private", "unlisted"):
            raise ValueError(
                f"Invalid privacy_status: '{privacy_status}'. "
                "Must be 'public', 'private', or 'unlisted'."
            )

        # 3. Safety: public upload requires explicit confirmation (BEFORE file ops)
        if privacy_status == "public" and not confirm_public:
            raise ValueError(
                "Uploading as 'public' requires confirm_public=True. "
                "Use privacy_status='unlisted' or 'private' for safe defaults."
            )

        # 4. Check file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        total_size = os.path.getsize(video_path)

        # 5. Report initial progress
        if progress_callback:
            try:
                progress_callback(0, total_size)
            except Exception:
                pass  # Don't fail upload due to callback errors

        # 6. Add mandatory disclosure
        disclosure = self.config.disclosure_text
        if disclosure not in description:
            description = f"{description}\n{disclosure}"

        # 7. Build request body
        youtube = self.service
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        # 8. Create resumable media upload
        media_file = MediaFileUpload(
            video_path,
            chunksize=self.config.upload_chunk_size,
            resumable=True,
        )

        # 9. Execute upload with retry
        try:
            self.check_quota("videos.insert")

            def _execute_insert():
                return youtube.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media_file,
                ).execute()

            insert_response = self._retry_on_error(_execute_insert)
            self.consume_quota("videos.insert")

            video_id = insert_response.get("id")
            if not video_id:
                raise RuntimeError("Upload succeeded but no video_id returned")

            # 10. Report final progress
            if progress_callback:
                try:
                    progress_callback(total_size, total_size)
                except Exception:
                    pass

            return {
                "video_id": video_id,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "view_url": f"https://www.youtube.com/embed/{video_id}",
                "status": insert_response.get("status", {}),
            }

        except HttpError as e:
            logger.error("YouTube upload API error: %s", str(e)[:200])
            raise
        except Exception as e:
            logger.error("Unexpected upload error: %s", str(e)[:200])
            raise

    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Get statistics for a YouTube video.

        Args:
            video_id: YouTube video ID

        Returns:
            Dict with views, likes, dislikes, comments, duration
        """
        self._validate_required(video_id=video_id)
        youtube = self.service

        try:
            self.check_quota("videos.list")

            def _execute_stats():
                return youtube.videos().list(
                    part="statistics,contentDetails",
                    id=video_id,
                ).execute()

            response = self._retry_on_error(_execute_stats)
            self.consume_quota("videos.list")

            if response.get("items"):
                item = response["items"][0]
                stats = item.get("statistics", {})
                return {
                    "video_id": video_id,
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "dislikes": int(stats.get("dislikeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "duration": item.get("contentDetails", {}).get("duration"),
                }

            return {}

        except HttpError as e:
            logger.error("YouTube video stats error: %s", str(e)[:200])
            raise

    def get_channel_stats(self) -> Dict[str, Any]:
        """Get channel statistics.

        Uses selected channel ID if set, otherwise mine=True (default channel).
        """
        youtube = self.service
        selected_channel = self.token_manager.get_selected_channel()

        if selected_channel:
            self.check_quota("channels.list")
            request = youtube.channels().list(
                part="statistics,snippet",
                id=selected_channel,
            )
        else:
            self.check_quota("channels.list")
            request = youtube.channels().list(
                part="statistics,snippet",
                mine=True,
            )

        response = request.execute()
        self.consume_quota("channels.list")

        if response.get("items"):
            item = response["items"][0]
            stats = item.get("statistics", {})
            return {
                "channel_id": item.get("id"),
                "title": item.get("snippet", {}).get("title"),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
            }

        return {}

    def get_channel_stats_by_id(self, channel_id: str) -> Dict[str, Any]:
        """Get channel statistics for a specific channel ID."""
        self._validate_required(channel_id=channel_id)
        youtube = self.service

        try:
            self.check_quota("channels.list")

            request = youtube.channels().list(
                part="statistics,snippet",
                id=channel_id,
            )
            response = request.execute()
            self.consume_quota("channels.list")

            if response.get("items"):
                item = response["items"][0]
                stats = item.get("statistics", {})
                return {
                    "channel_id": item.get("id"),
                    "title": item.get("snippet", {}).get("title"),
                    "subscriber_count": int(stats.get("subscriberCount", 0)),
                    "view_count": int(stats.get("viewCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                }

            return {}

        except HttpError as e:
            logger.error("Channel stats error: %s", str(e)[:200])
            raise

    def list_accessible_channels(self) -> List[Dict[str, Any]]:
        """List all channels accessible by the authenticated user.

        Returns:
            List of dicts with channel id, title, and statistics
        """
        youtube = self.service

        try:
            self.check_quota("channels.list")

            request = youtube.channels().list(
                part="snippet,statistics",
                mine=True,
            )
            response = request.execute()
            self.consume_quota("channels.list")

            channels = []
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                channels.append({
                    "channel_id": item.get("id"),
                    "title": item.get("snippet", {}).get("title", ""),
                    "subscriber_count": int(stats.get("subscriberCount", 0)),
                    "view_count": int(stats.get("viewCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                })
            return channels

        except HttpError as e:
            logger.error("List channels error: %s", str(e)[:200])
            raise

    def get_all_channel_videos(self, max_results: int = 500) -> List[Dict[str, Any]]:
        """Get ALL videos from the authenticated user's channel including
        private, unlisted, and scheduled videos.

        Uses search.list with forMine=true to find all videos owned by the
        authenticated user, then fetches full details with videos.list.

        Args:
            max_results: Maximum number of videos to return

        Returns:
            List of dicts with video_id, title, published_at, privacy_status,
            and scheduled_publish_time (if scheduled)
        """
        youtube = self.service

        try:
            # Step 1: Use search.list to find all videos owned by the user
            self.check_quota("search.list")

            video_ids = []
            next_page_token = None

            while len(video_ids) < max_results:
                request = youtube.search().list(
                    part="id",
                    forMine=True,
                    type="video",
                    maxResults=min(50, max_results - len(video_ids)),
                    pageToken=next_page_token,
                    order="date",
                )
                response = request.execute()
                self.consume_quota("search.list")

                for item in response.get("items", []):
                    video_id = item.get("id", {}).get("videoId")
                    if video_id:
                        video_ids.append(video_id)

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

            if not video_ids:
                return []

            # Step 2: Fetch full details for all video IDs in batches of 50
            videos = []
            for i in range(0, len(video_ids), 50):
                batch_ids = video_ids[i:i + 50]
                self.check_quota("videos.list")
                request = youtube.videos().list(
                    part="snippet,status,contentDetails",
                    id=",".join(batch_ids),
                )
                response = request.execute()
                self.consume_quota("videos.list")

                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    status = item.get("status", {})
                    content_details = item.get("contentDetails", {})

                    privacy_status = status.get("privacyStatus", "private")
                    published_at = snippet.get("publishedAt", "")
                    scheduled_publish_time = status.get("publishAt", "")

                    # Scheduled videos have privacyStatus="private" and a publishAt timestamp
                    is_scheduled = bool(scheduled_publish_time and scheduled_publish_time != published_at)

                    videos.append({
                        "video_id": item.get("id"),
                        "title": snippet.get("title", ""),
                        "published_at": published_at,
                        "privacy_status": privacy_status,
                        "scheduled_publish_time": scheduled_publish_time,
                        "is_scheduled": is_scheduled,
                        "duration": content_details.get("duration"),
                    })

            return videos

        except HttpError as e:
            logger.error("Get all channel videos error: %s", str(e)[:200])
            raise

    @property
    def quota_used_today(self) -> int:
        """Return estimated quota used today (approximate)."""
        return self._quota_used_today

    def check_quota(self, method_name: str) -> None:
        """Check if there is enough quota remaining for the given API method.

        Args:
            method_name: YouTube API method name (e.g., "videos.insert")

        Raises:
            RuntimeError: If quota would be exceeded
        """
        cost = QUOTA_COSTS.get(method_name, 1)
        if self._quota_used_today + cost > self.config.daily_quota_limit:
            remaining = self.config.daily_quota_limit - self._quota_used_today
            raise RuntimeError(
                f"Daily quota would be exceeded. "
                f"Needed: {cost}, Remaining: {remaining}, "
                f"Limit: {self.config.daily_quota_limit}"
            )

    def consume_quota(self, method_name: str) -> None:
        """Record quota usage for an API method."""
        cost = QUOTA_COSTS.get(method_name, 1)
        self._quota_used_today += cost
        logger.debug(
            "Quota consumed: %d for %s. Total today: %d/%d",
            cost,
            method_name,
            self._quota_used_today,
            self.config.daily_quota_limit,
        )
