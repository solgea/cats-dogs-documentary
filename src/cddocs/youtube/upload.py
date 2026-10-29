"""YouTube Video Upload Manager."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .api_client import YouTubeAPIClient
from .token_manager import TokenManager


class UploadManager:
    """Manages YouTube video uploads."""
    
    def __init__(self, token_manager: TokenManager):
        self.client = YouTubeAPIClient(token_manager)
    
    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = "unlisted",
        category_id: str = "15",
        confirm_public: bool = False,
    ) -> Dict[str, Any]:
        """Upload a YouTube Short.
        
        Args:
            video_path: Path to the MP4 video file
            title: Video title
            description: Video description
            tags: List of tags
            privacy_status: Privacy status ("public", "private", "unlisted")
            category_id: YouTube category ID (15 = Pets & Animals)
            confirm_public: Must be True to upload as "public". Defaults to False.
        
        Returns:
            Dict with video_id, view_url, and status
        """
        return self.client.upload_short(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            category_id=category_id,
            confirm_public=confirm_public,
        )
    
    def set_privacy_status(self, video_id: str, privacy_status: str) -> Dict[str, Any]:
        """Change video privacy status."""
        youtube = self.client.service
        
        try:
            update_response = youtube.videos().update(
                part="status",
                body={
                    "id": video_id,
                    "status": {
                        "privacyStatus": privacy_status,
                    },
                },
            ).execute()
            
            return {
                "video_id": video_id,
                "privacy_status": update_response.get("status", {}).get("privacyStatus"),
            }
            
        except Exception as e:
            print(f"Privacy update Hatası: {e}")
            raise