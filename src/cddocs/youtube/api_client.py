"""YouTube Data API v3 Client."""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from youtube.token_manager import TokenManager
from youtube.constants import MAX_RETRIES, DEFAULT_PRIVACY_STATUS

logger = logging.getLogger(__name__)

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


class YouTubeAPIClient:
    """Client for YouTube Data API v3."""
    
    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self.service = self._build_service()
    
    def _build_service(self) -> Any:
        """Build the YouTube API service object."""
        credentials = self.token_manager.get_credentials()
        if credentials is None:
            raise ValueError("Valid YouTube credentials not available")
        
        return build(
            "youtube",
            "v3",
            credentials=credentials,
        )
    
    def _retry_on_error(self, func, *args, **kwargs):
        """Retry transient API errors up to MAX_RETRIES times."""
        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                last_exception = e
                status = e.resp.status if hasattr(e, "resp") else None
                # Do not retry on auth or quota errors
                if status in (401, 403):
                    logger.error(f"YouTube API error (status {status}): {e}")
                    raise
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(f"YouTube API retry {attempt}/{MAX_RETRIES} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"YouTube API failed after {MAX_RETRIES} attempts: {e}")
                    raise
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(f"Unexpected error retry {attempt}/{MAX_RETRIES} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"Unexpected error after {MAX_RETRIES} attempts: {e}")
                    raise
        raise last_exception
    
    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = DEFAULT_PRIVACY_STATUS,
        category_id: str = "15",
        confirm_public: bool = False,
    ) -> Dict[str, Any]:
        """Upload a YouTube Short.
        
        Args:
            video_path: Path to the MP4 video file
            title: Video title
            description: Video description (will include disclosure text)
            tags: List of tags
            privacy_status: Privacy status ("public", "private", "unlisted")
            category_id: YouTube category ID (15 = Pets & Animals)
            confirm_public: Must be True to upload as "public". Defaults to False.
        
        Returns:
            Dict with video_id, view_url, and status
        """
        # Add disclosure to description if mandatory
        disclosure = (
            "Real-footage montage using third-party clips for illustration; "
            "not documentary footage or scientific evidence."
        )
        if disclosure not in description:
            description = f"{description}\n{disclosure}"
        
        # Public upload requires explicit confirmation
        if privacy_status == "public" and not confirm_public:
            raise ValueError(
                "Uploading as 'public' requires confirm_public=True. "
                "Use privacy_status='unlisted' or 'private' for safe defaults."
            )
        
        youtube = self.service
        
        # Build the body - use selected channel if set, otherwise default
        selected_channel = self.token_manager.get_selected_channel()
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }
        # Note: selected_channel is tracked in token_manager but YouTube upload
        # channel is inferred from the OAuth token; the selected channel is used
        # for analytics and stats queries, not the upload body itself.
        
        # Create media file upload
        media_file = MediaFileUpload(
            video_path,
            chunksize=1024 * 1024,  # 1MB chunks
            resumable=True,
        )
        
        # Execute upload with retry
        try:
            def _execute_insert():
                return youtube.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media_file,
                ).execute()
            
            insert_response = self._retry_on_error(_execute_insert)
            
            video_id = insert_response.get("id")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            view_url = f"https://www.youtube.com/embed/{video_id}"
            
            return {
                "video_id": video_id,
                "video_url": video_url,
                "view_url": view_url,
                "status": insert_response.get("status"),
            }
            
        except HttpError as e:
            logger.error(f"YouTube API Hatası: {e}")
            raise
        except Exception as e:
            logger.error(f"Beklenmeyen hata: {e}")
            raise
    
    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Get statistics for a YouTube video."""
        youtube = self.service
        
        try:
            def _execute_stats():
                return youtube.videos().list(
                    part="statistics,contentDetails",
                    id=video_id,
                ).execute()
            
            response = self._retry_on_error(_execute_stats)
            
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
            logger.error(f"Analytics Hatası: {e}")
            raise
    
    def get_channel_stats(self) -> Dict[str, Any]:
        """Get channel statistics.
        
        If a selected channel ID is set in the token manager,
        it will use that channel. Otherwise, it uses "mine=True"
        which returns the default channel associated with the token.
        """
        youtube = self.service
        
        # If a selected channel ID is set, use it; otherwise use mine=True
        selected_channel = self.token_manager.get_selected_channel()
        if selected_channel:
            request = youtube.channels().list(
                part="statistics,snippet",
                id=selected_channel,
            )
        else:
            request = youtube.channels().list(
                part="statistics,snippet",
                mine=True,
            )
        
        response = request.execute()
        
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
        """Get channel statistics for a specific channel ID.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Dict with channel statistics
        """
        youtube = self.service
        
        try:
            request = youtube.channels().list(
                part="statistics,snippet",
                id=channel_id,
            )
            response = request.execute()
            
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
            logger.error(f"Channel stats Hatası: {e}")
            raise