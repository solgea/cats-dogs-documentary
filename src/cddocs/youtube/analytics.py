"""YouTube Analytics Reporter with selected channel support."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build

from .api_client import YouTubeAPIClient
from .config import YouTubeConfig
from .token_manager import TokenManager

logger = logging.getLogger(__name__)


class AnalyticsReporter:
    """Reports YouTube analytics and metrics.

    Respects the selected channel ID from TokenManager.
    If no channel is selected, falls back to the default authenticated channel.
    """

    def __init__(self, token_manager: TokenManager, config: Optional[YouTubeConfig] = None):
        self.config = config or YouTubeConfig()
        self.client = YouTubeAPIClient(token_manager, config=self.config)
        self._analytics_service = None

    def _get_analytics_service(self):
        """Get or create YouTube Analytics service instance."""
        if self._analytics_service is None:
            self.client.token_manager.refresh_if_needed()
            credentials = self.client.token_manager.get_credentials()
            if credentials is None:
                raise ValueError(
                    "Valid YouTube credentials not available for analytics"
                )
            self._analytics_service = build(
                self.config.analytics_service_name,
                self.config.analytics_version,
                credentials=credentials,
            )
        return self._analytics_service

    def _get_channel_ids_param(self) -> str:
        """Return the analytics ids parameter based on selected channel."""
        selected_channel = self.client.token_manager.get_selected_channel()
        if selected_channel:
            return f"channel=={selected_channel}"
        return "channel==MINE"

    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Get statistics for a specific video.

        Args:
            video_id: YouTube video ID

        Returns:
            Dict with views, likes, dislikes, comments, duration
        """
        return self.client.get_video_stats(video_id)

    def get_channel_stats(self) -> Dict[str, Any]:
        """Get channel statistics for the selected/default channel."""
        return self.client.get_channel_stats()

    def get_channel_stats_by_id(self, channel_id: str) -> Dict[str, Any]:
        """Get channel statistics for a specific channel ID."""
        return self.client.get_channel_stats_by_id(channel_id)

    def get_recent_videos(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Get recent videos from the selected/default channel's uploads playlist.

        Args:
            max_results: Maximum number of videos to return

        Returns:
            List of dicts with video_id, title, published_at
        """
        youtube = self.client.service

        try:
            # Get channel ID (selected or default)
            selected_channel = self.client.token_manager.get_selected_channel()
            if selected_channel:
                channel_request = youtube.channels().list(
                    part="contentDetails",
                    id=selected_channel,
                )
            else:
                channel_request = youtube.channels().list(
                    part="contentDetails",
                    mine=True,
                )

            channel_response = channel_request.execute()

            if not channel_response.get("items"):
                return []

            channel_id = channel_response["items"][0]["id"]
            content_details = channel_response["items"][0].get("contentDetails", {})
            uploads_playlist_id = content_details.get("uploadsPlaylistId")

            if not uploads_playlist_id:
                logger.warning("No uploadsPlaylistId found for channel %s", channel_id)
                return []

            # Get recent videos from uploads playlist
            playlist_request = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=max_results,
            )
            playlist_response = playlist_request.execute()

            videos = []
            for item in playlist_response.get("items", []):
                snippet = item.get("snippet", {})
                resource_id = snippet.get("resourceId", {})
                videos.append({
                    "video_id": resource_id.get("videoId"),
                    "title": snippet.get("title", ""),
                    "published_at": snippet.get("publishedAt", ""),
                })

            return videos

        except Exception as e:
            logger.error("Recent videos error: %s", str(e)[:200])
            raise

    def get_analytics_report(
        self,
        video_id: Optional[str] = None,
        start_date: str = "",
        end_date: str = "",
        metrics: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get analytics report for a channel or specific video.

        Args:
            video_id: Optional YouTube video ID to filter by
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            metrics: List of metrics (e.g., ["views", "likes", "comments"])
            dimensions: List of dimensions for grouping

        Returns:
            Dict with analytics data rows
        """
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required")

        if metrics is None:
            metrics = ["views", "likes", "comments", "estimatedMinutesWatched"]

        youtube = self.client.service
        analytics = self._get_analytics_service()

        # Build filters: if video_id specified, filter by video
        filters = None
        if video_id:
            filters = f"video=={video_id}"

        try:
            request = analytics.reports().query(
                ids=self._get_channel_ids_param(),
                startDate=start_date,
                endDate=end_date,
                dimensions=",".join(dimensions or []),
                metrics=",".join(metrics),
                filters=filters,
            )
            response = request.execute()
            return response

        except Exception as e:
            logger.error("Analytics report error: %s", str(e)[:200])
            raise

    def get_daily_views(
        self,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Get daily view counts for the selected channel.

        Returns:
            List of dicts with date and views
        """
        report = self.get_analytics_report(
            start_date=start_date,
            end_date=end_date,
            metrics=["views"],
            dimensions=["day"],
        )

        results = []
        for row in report.get("rows", []):
            results.append({
                "date": row[0],
                "views": int(row[1]) if len(row) > 1 else 0,
            })

        return results
