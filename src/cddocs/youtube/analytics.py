"""YouTube Analytics Reporter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .api_client import YouTubeAPIClient
from .token_manager import TokenManager


class AnalyticsReporter:
    """Reports YouTube analytics and metrics."""
    
    def __init__(self, token_manager: TokenManager):
        self.client = YouTubeAPIClient(token_manager)
    
    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Get statistics for a specific video."""
        return self.client.get_video_stats(video_id)
    
    def get_channel_stats(self) -> Dict[str, Any]:
        """Get channel statistics."""
        return self.client.get_channel_stats()
    
    def get_recent_videos(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Get recent videos from the channel."""
        youtube = self.client.service
        
        try:
            request = youtube.channels().list(
                part="contentDetails",
                mine=True,
            )
            response = request.execute()
            
            if response.get("items"):
                channel_id = response["items"][0]["id"]
                
                # Get uploads playlist ID if available
                content_details = response["items"][0].get("contentDetails", {})
                uploads_playlist_id = content_details.get("uploadsPlaylistId")
                
                if not uploads_playlist_id:
                    # Fallback: return empty list if no uploads playlist
                    return []
                
                # Get recent videos from uploads playlist
                request = youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_playlist_id,
                    maxResults=max_results,
                )
                response = request.execute()
                
                videos = []
                for item in response.get("items", []):
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    title = item["snippet"]["title"]
                    published_at = item["snippet"]["publishedAt"]
                    videos.append({
                        "video_id": video_id,
                        "title": title,
                        "published_at": published_at,
                    })
                
                return videos
            
            return []
            
        except Exception as e:
            print(f"Recent videos Hatası: {e}")
            raise
    
    def get_analytics_report(
        self,
        video_id: str,
        start_date: str,
        end_date: str,
        metrics: List[str],
        dimensions: List[str] = None,
    ) -> Dict[str, Any]:
        """Get analytics report for a video.
        
        Args:
            video_id: YouTube video ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            metrics: List of metrics to retrieve
            dimensions: List of dimensions for grouping
        
        Returns:
            Dict with analytics data
        """
        from googleapiclient.discovery import build
        youtube = self.client.service
        
        # Use selected channel ID if set, otherwise fall back to MINE (default)
        selected_channel = self.client.token_manager.get_selected_channel()
        if selected_channel:
            ids = f"channel=={selected_channel}"
        else:
            ids = "channel==MINE"
        
        analytics = build("youtubeAnalytics", "v2", credentials=self.client.get_credentials())
        
        request = analytics.reports().query(
            ids=ids,
            startDate=start_date,
            endDate=end_date,
            dimensions=dimensions or [],
            metrics=metrics or [],
        )
        
        response = request.execute()
        return response