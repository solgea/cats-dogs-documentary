"""YouTube Video Upload Manager with safety guards."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .api_client import YouTubeAPIClient
from .config import YouTubeConfig
from .token_manager import TokenManager

logger = logging.getLogger(__name__)


class UploadManager:
    """Manages YouTube video uploads with safety guards.

    - Default privacy is 'unlisted' (safe)
    - Public upload requires explicit confirm_public=True
    - Privacy status changes also require confirm_public
    """

    def __init__(self, token_manager: TokenManager, config: Optional[YouTubeConfig] = None):
        self.config = config or YouTubeConfig()
        self.client = YouTubeAPIClient(token_manager, config=self.config)

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
        """Upload a YouTube video.

        Args:
            video_path: Path to the MP4 video file
            title: Video title
            description: Video description
            tags: List of tags
            privacy_status: "public", "private", or "unlisted" (default: "unlisted")
            category_id: YouTube category ID
            confirm_public: Must be True to upload as "public"

        Returns:
            Dict with video_id, video_url, view_url, and status
        """
        # Validate privacy_status against config default
        if privacy_status not in ("public", "private", "unlisted"):
            raise ValueError(
                f"Invalid privacy_status: '{privacy_status}'. "
                "Must be 'public', 'private', or 'unlisted'."
            )

        # Use config default if not explicitly provided
        if privacy_status == "unlisted" and self.config.default_privacy_status != "unlisted":
            privacy_status = self.config.default_privacy_status

        return self.client.upload_short(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            category_id=category_id,
            confirm_public=confirm_public,
        )

    def set_privacy_status(
        self,
        video_id: str,
        privacy_status: str,
        confirm_public: bool = False,
    ) -> Dict[str, Any]:
        """Change video privacy status with safety guard.

        Args:
            video_id: YouTube video ID
            privacy_status: Target privacy status
            confirm_public: Must be True if setting to "public"

        Returns:
            Dict with video_id and new privacy_status
        """
        self._validate_required(video_id=video_id, privacy_status=privacy_status)

        if privacy_status not in ("public", "private", "unlisted"):
            raise ValueError(
                f"Invalid privacy_status: '{privacy_status}'"
            )

        if privacy_status == "public" and not confirm_public:
            raise ValueError(
                "Setting video to 'public' requires confirm_public=True. "
                "This is a safety measure to prevent accidental public release."
            )

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

            logger.info(
                "Video %s privacy changed to %s", video_id, privacy_status
            )

            return {
                "video_id": video_id,
                "privacy_status": update_response.get("status", {}).get("privacyStatus"),
            }

        except Exception as e:
            logger.error("Privacy update error: %s", str(e)[:200])
            raise

    @staticmethod
    def _validate_required(**kwargs) -> None:
        """Validate that required arguments are not None or empty."""
        for name, value in kwargs.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Required argument '{name}' cannot be empty")
