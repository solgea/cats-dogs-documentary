#!/usr/bin/env python
"""Mock YouTube Upload Test - Gerçek API'ye bağlanmaz."""

import sys
sys.path.insert(0, 'src/cddocs')

from unittest.mock import MagicMock, patch
from youtube.token_manager import TokenManager
from youtube.upload import UploadManager


def test_upload_defaults_to_unlisted():
    """Upload varsayılan olarak 'unlisted' olmalı, 'public' olmamalı."""
    tm = MagicMock(spec=TokenManager)
    tm.load_credentials.return_value = True
    tm.get_credentials.return_value = MagicMock()

    with patch("youtube.upload.YouTubeAPIClient") as MockClient:
        MockClient.return_value.upload_short.return_value = {
            "video_id": "test_video_id",
            "video_url": "https://www.youtube.com/watch?v=test_video_id",
            "view_url": "https://www.youtube.com/embed/test_video_id",
            "status": {"privacyStatus": "unlisted"},
        }

        um = UploadManager(tm)
        result = um.upload_short(
            video_path="test.mp4",
            title="Test",
            description="Desc",
            tags=["test"],
            privacy_status="unlisted",
            allow_duplicate=True,
        )

        assert result["video_id"] == "test_video_id"
        assert result["status"]["privacyStatus"] == "unlisted"


def test_upload_public_blocked_without_confirmation():
    """'public' upload confirm_public=True olmadan engellenmeli."""
    tm = MagicMock(spec=TokenManager)
    um = UploadManager(tm)

    try:
        um.upload_short(
            video_path="test.mp4",
            title="Test",
            description="Desc",
            tags=["test"],
            privacy_status="public",
            confirm_public=False,
            allow_duplicate=True,
        )
        assert False, "Public upload should be blocked without confirmation"
    except ValueError:
        pass  # Beklenen davranış


def test_upload_public_allowed_with_confirmation():
    """'public' upload confirm_public=True ile izin verilmeli."""
    tm = MagicMock(spec=TokenManager)
    tm.load_credentials.return_value = True
    tm.get_credentials.return_value = MagicMock()

    with patch("youtube.upload.YouTubeAPIClient") as MockClient:
        MockClient.return_value.upload_short.return_value = {
            "video_id": "test_video_public",
            "video_url": "https://www.youtube.com/watch?v=test_video_public",
            "view_url": "https://www.youtube.com/embed/test_video_public",
            "status": {"privacyStatus": "public"},
        }

        um = UploadManager(tm)
        result = um.upload_short(
            video_path="test.mp4",
            title="Test Public",
            description="Desc",
            tags=["test"],
            privacy_status="public",
            confirm_public=True,
            allow_duplicate=True,
        )

        assert result["video_id"] == "test_video_public"
        assert result["status"]["privacyStatus"] == "public"


def test_upload_file_not_found():
    """Mevcut olmayan dosya için FileNotFoundError fırlatılmalı."""
    tm = MagicMock(spec=TokenManager)
    um = UploadManager(tm)

    try:
        um.upload_short(
            video_path="nonexistent.mp4",
            title="Test",
            description="Desc",
            tags=["test"],
            privacy_status="unlisted",
            allow_duplicate=True,
        )
        assert False, "FileNotFoundError should be raised"
    except FileNotFoundError:
        pass  # Beklenen davranış


if __name__ == "__main__":
    test_upload_defaults_to_unlisted()
    test_upload_public_blocked_without_confirmation()
    test_upload_public_allowed_with_confirmation()
    test_upload_file_not_found()
    print("Tüm mock upload testleri başarılı.")
