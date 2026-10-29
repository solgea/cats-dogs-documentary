"""YouTube Video Upload Manager with safety guards and duplicate prevention."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .api_client import YouTubeAPIClient
from .config import YouTubeConfig
from .token_manager import TokenManager

logger = logging.getLogger(__name__)

# Duplicate detection storage file
UPLOAD_HISTORY_FILE = "upload_history.json"


class UploadManager:
    """Manages YouTube video uploads with safety guards.

    - Default privacy is 'unlisted' (safe)
    - Public upload requires explicit confirm_public=True
    - Privacy status changes also require confirm_public
    - Duplicate upload prevention based on file hash
    """

    def __init__(
        self,
        token_manager: TokenManager,
        config: Optional[YouTubeConfig] = None,
        history_file: Optional[str] = None,
    ):
        self.config = config or YouTubeConfig()
        self.client = YouTubeAPIClient(token_manager, config=self.config)
        self.history_file = Path(history_file or UPLOAD_HISTORY_FILE)

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file for duplicate detection."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _load_upload_history(self) -> Dict[str, Any]:
        """Load upload history from disk."""
        if not self.history_file.exists():
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Upload history load error: %s", e)
            return {}

    def _save_upload_history(self, history: Dict[str, Any]) -> None:
        """Save upload history to disk."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except IOError as e:
            logger.warning("Upload history save error: %s", e)

    def _is_duplicate(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Check if a file with the same hash was already uploaded.

        Returns the previous upload record if duplicate found, None otherwise.
        """
        try:
            file_hash = self._compute_file_hash(file_path)
        except (IOError, OSError) as e:
            logger.warning("File hash computation error: %s", e)
            return None

        history = self._load_upload_history()
        return history.get(file_hash)

    def _record_upload(
        self,
        file_path: str,
        file_hash: str,
        result: Dict[str, Any],
    ) -> None:
        """Record an upload in the history file."""
        history = self._load_upload_history()
        history[file_hash] = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "video_id": result.get("video_id"),
            "video_url": result.get("video_url"),
            "uploaded_at": str(__import__("datetime").datetime.now()),
            "privacy_status": result.get("status", {}).get("privacyStatus"),
        }
        self._save_upload_history(history)

    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = "unlisted",
        category_id: str = "15",
        confirm_public: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        allow_duplicate: bool = False,
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
            progress_callback: Optional callback(uploaded_bytes, total_bytes)
            allow_duplicate: If False, reject duplicate file uploads

        Returns:
            Dict with video_id, video_url, view_url, and status
        """
        # Validate privacy_status
        if privacy_status not in ("public", "private", "unlisted"):
            raise ValueError(
                f"Invalid privacy_status: '{privacy_status}'. "
                "Must be 'public', 'private', or 'unlisted'."
            )

        # Use config default if not explicitly provided
        if privacy_status == "unlisted" and self.config.default_privacy_status != "unlisted":
            privacy_status = self.config.default_privacy_status

        # Check file exists BEFORE any hash/duplicate operations
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Duplicate detection
        if not allow_duplicate:
            duplicate = self._is_duplicate(video_path)
            if duplicate:
                raise ValueError(
                    f"Duplicate upload detected. File '{os.path.basename(video_path)}' "
                    f"was already uploaded as video '{duplicate.get('video_id')}'. "
                    f"Use allow_duplicate=True to override."
                )

        # Compute hash for recording
        try:
            file_hash = self._compute_file_hash(video_path)
        except (IOError, OSError) as e:
            raise ValueError(f"Cannot compute file hash: {e}")

        # Delegate to API client
        result = self.client.upload_short(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            category_id=category_id,
            confirm_public=confirm_public,
            progress_callback=progress_callback,
        )

        # Record upload in history
        self._record_upload(video_path, file_hash, result)

        logger.info(
            "Video uploaded: %s -> %s (privacy: %s)",
            os.path.basename(video_path),
            result.get("video_id"),
            result.get("status", {}).get("privacyStatus"),
        )

        return result

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
            self.client.check_quota("videos.update")

            update_response = youtube.videos().update(
                part="status",
                body={
                    "id": video_id,
                    "status": {
                        "privacyStatus": privacy_status,
                    },
                },
            ).execute()
            self.client.consume_quota("videos.update")

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

    def get_upload_history(self) -> Dict[str, Any]:
        """Return the full upload history."""
        return self._load_upload_history()

    def clear_upload_history(self) -> None:
        """Clear the upload history file."""
        if self.history_file.exists():
            try:
                self.history_file.unlink()
            except OSError as e:
                logger.warning("Upload history clear error: %s", e)

    @staticmethod
    def _validate_required(**kwargs) -> None:
        """Validate that required arguments are not None or empty."""
        for name, value in kwargs.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Required argument '{name}' cannot be empty")
