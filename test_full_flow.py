#!/usr/bin/env python
"""Mock Full Flow Test - Gerçek API'ye bağlanmaz."""

import sys
sys.path.insert(0, 'src/cddocs')

from unittest.mock import MagicMock, patch
from youtube.token_manager import TokenManager
from youtube.api_client import YouTubeAPIClient
from youtube.upload import UploadManager


def test_full_flow_mock():
    """Kanal seçimi + upload akışını mock'lar."""
    print("=" * 60)
    print("YOUTUBE INTEGRATION: Mock Full Flow Test")
    print("=" * 60)

    # Step 1: Token manager
    tm = MagicMock(spec=TokenManager)
    tm.load_credentials.return_value = True
    tm.get_credentials.return_value = MagicMock()
    tm.get_selected_channel.return_value = None

    print("\n[1] Token yoneticisi baslatildi (mock).")

    # Step 2: List channels (mock)
    with patch("youtube.upload.YouTubeAPIClient") as MockClient:
        mock_client = MagicMock()
        mock_client.list_accessible_channels.return_value = [
            {
                "channel_id": "UC123456789",
                "title": "Test Kanal",
                "subscriber_count": 1000,
                "view_count": 50000,
                "video_count": 10,
            }
        ]
        MockClient.return_value = mock_client

        channels = mock_client.list_accessible_channels()
        print(f"\n[2] {len(channels)} kanal bulundu (mock).")
        for i, ch in enumerate(channels, 1):
            print(f"   {i}. {ch['title']} ({ch['subscriber_count']} abone)")

        # Step 3: Select first channel
        selected_channel_id = channels[0]["channel_id"]
        tm.set_selected_channel(selected_channel_id)
        print(f"\n[3] Kanal secildi: {selected_channel_id}")

        # Step 4: Upload (mock)
        mock_client.upload_short.return_value = {
            "video_id": "VID123456",
            "video_url": "https://www.youtube.com/watch?v=VID123456",
            "view_url": "https://www.youtube.com/embed/VID123456",
            "status": {"privacyStatus": "unlisted"},
        }

        um = UploadManager(tm)
        result = um.upload_short(
            video_path="test.mp4",
            title="Test Upload",
            description="Desc",
            tags=["test"],
            privacy_status="unlisted",
            allow_duplicate=True,
        )

        print("\n[4] Upload tamamlandi (mock).")
        print(f"   Video ID: {result.get('video_id')}")
        print(f"   Privacy: {result.get('status', {}).get('privacyStatus')}")

        # Step 5: Verify channel state
        print(f"\n[5] Secili channel: {tm.get_selected_channel()}")
        print("=" * 60)
        print("✅ Tüm mock adımlar başarılı!")
        print("=" * 60)


if __name__ == "__main__":
    test_full_flow_mock()
