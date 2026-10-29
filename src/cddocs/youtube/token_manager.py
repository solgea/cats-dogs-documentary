"""Token manager for YouTube API OAuth 2.0 flow."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Google Client Info (from environment variables)
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REDIRECT_URIS = ["http://localhost"]

# Scopes
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl", 
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

STORAGE_FILE = "youtube_token.json"


class TokenManager:
    """Manages OAuth 2.0 tokens for YouTube API."""
    
    def __init__(self, storage_path: str = STORAGE_FILE):
        self.storage_path = Path(storage_path)
        self.credentials: Optional[Credentials] = None
        # Selected channel ID (None means use default "mine" channel)
        self.selected_channel_id: Optional[str] = None
    
    def load_credentials(self) -> bool:
        """Load credentials from storage file."""
        if not self.storage_path.exists():
            return False
        
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
            
            self.credentials = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                client_id=YOUTUBE_CLIENT_ID,
                client_secret=YOUTUBE_CLIENT_SECRET,
                scopes=YOUTUBE_SCOPES,
                expiry=datetime.fromisoformat(data.get("expiry", "")) if data.get("expiry") else None
            )
            
            # Load selected channel ID if present
            self.selected_channel_id = data.get("selected_channel_id")
            return True
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Token yükleme hatası: {e}")
            return False
    
    def save_credentials(self) -> bool:
        """Save credentials to storage file."""
        if self.credentials is None:
            return False
        
        try:
            data = {
                "token": self.credentials.token,
                "refresh_token": self.credentials.refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "scopes": YOUTUBE_SCOPES,
                "expiry": self.credentials.expiry.isoformat() if self.credentials.expiry else None,
                # Save selected channel ID
                "selected_channel_id": self.selected_channel_id
            }
            
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
            
            return True
        except (IOError, json.JSONEncodeError) as e:
            print(f"Token kaydetme hatası: {e}")
            return False
    
    def is_valid(self) -> bool:
        """Check if credentials are valid and not expired (no side effects)."""
        if self.credentials is None:
            return False
        return not self.credentials.expired
    
    def refresh_if_needed(self) -> bool:
        """Refresh credentials if expired. Explicit side effect: network I/O + file write."""
        if self.credentials is None:
            return False
        
        if not self.credentials.expired:
            return True
        
        try:
            from google.auth.transport.requests import Request
            request = Request()
            self.credentials.refresh(request)
            self.save_credentials()
            return True
        except Exception as e:
            print(f"Token yenileme hatası: {e}")
            return False
    
    def get_credentials(self) -> Optional[Credentials]:
        """Get credentials. Does NOT refresh automatically — call refresh_if_needed() first."""
        if self.credentials is None:
            return None
        return self.credentials
    
    def set_selected_channel(self, channel_id: str) -> None:
        """Set the selected YouTube channel ID.
        
        Args:
            channel_id: YouTube channel ID to use for API calls
        """
        self.selected_channel_id = channel_id
        # Save immediately so it persists
        self.save_credentials()
    
    def get_selected_channel(self) -> Optional[str]:
        """Get the currently selected channel ID.
        
        Returns:
            Channel ID if set, None means use default "mine" channel
        """
        return self.selected_channel_id