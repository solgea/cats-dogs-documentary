"""Token manager for YouTube API OAuth 2.0 flow."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from .config import YouTubeConfig


class TokenManager:
    """Manages OAuth 2.0 tokens for YouTube API.

    Token dosyası dosya sisteminde 0o600 izniyle saklanır.
    Gizli anahtarlar ortam değişkeninden okunur, asla hardcoded olmaz.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        config: Optional[YouTubeConfig] = None,
    ):
        self.config = config or YouTubeConfig()
        self.storage_path = Path(storage_path or self.config.token_storage_path)
        self.credentials: Optional[Credentials] = None
        # Selected channel ID (None means use default "mine" channel)
        self.selected_channel_id: Optional[str] = None

    def load_credentials(self) -> bool:
        """Load credentials from storage file.

        Returns True if credentials loaded successfully, False otherwise.
        """
        if not self.storage_path.exists():
            return False

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.credentials = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                scopes=self.config.scopes,
                expiry=datetime.fromisoformat(data.get("expiry", "")) if data.get("expiry") else None,
            )

            # Load selected channel ID if present
            self.selected_channel_id = data.get("selected_channel_id")
            return True
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print(f"Token yükleme hatası: {e}")
            self.credentials = None
            return False

    def save_credentials(self) -> bool:
        """Save credentials to storage file with restricted permissions (0o600).

        Returns True if saved successfully, False otherwise.
        """
        if self.credentials is None:
            return False

        try:
            data = {
                "token": self.credentials.token,
                "refresh_token": self.credentials.refresh_token,
                "token_uri": self.config.token_uri,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scopes": self.config.scopes,
                "expiry": self.credentials.expiry.isoformat() if self.credentials.expiry else None,
                # Save selected channel ID
                "selected_channel_id": self.selected_channel_id,
            }

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            # Set restrictive file permissions: owner read/write only
            try:
                os.chmod(self.storage_path, self.config.token_file_permissions)
            except OSError:
                # chmod may not be available on all platforms (e.g., Windows)
                pass

            return True
        except (IOError, OSError, ValueError) as e:
            print(f"Token kaydetme hatası: {e}")
            return False

    def is_valid(self) -> bool:
        """Check if credentials are valid and not expired (no side effects).

        Does NOT attempt to refresh. Use refresh_if_needed() for that.
        """
        if self.credentials is None:
            return False
        return not self.credentials.expired

    def refresh_if_needed(self) -> bool:
        """Refresh credentials if expired.

        Explicit side effect: network I/O + file write.
        Returns True if credentials are valid after the call.
        """
        if self.credentials is None:
            return False

        if not self.credentials.expired:
            return True

        try:
            request = Request()
            self.credentials.refresh(request)
            self.save_credentials()
            return True
        except Exception as e:
            print(f"Token yenileme hatası: {e}")
            return False

    def get_credentials(self) -> Optional[Credentials]:
        """Get credentials.

        Does NOT refresh automatically — call refresh_if_needed() first.
        Returns None if credentials are not loaded or expired.
        """
        if self.credentials is None:
            return None
        if self.credentials.expired:
            return None
        return self.credentials

    def set_credentials_from_oauth(
        self, access_token: str, refresh_token: str
    ) -> bool:
        """Save OAuth 2.0 credentials from authorization flow.

        Args:
            access_token: OAuth 2.0 access token
            refresh_token: OAuth 2.0 refresh token

        Returns:
            True if credentials were saved successfully
        """
        try:
            self.credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri=self.config.token_uri,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                scopes=self.config.scopes,
            )
            return self.save_credentials()
        except Exception as e:
            print(f"OAuth token kaydetme hatası: {e}")
            return False

    def ensure_valid(self) -> bool:
        """Ensure credentials are valid, refreshing if necessary.

        Convenience method that calls refresh_if_needed() if expired.
        Returns True if valid credentials are available.
        """
        if self.credentials is None:
            return False
        if self.credentials.expired:
            return self.refresh_if_needed()
        return True

    def set_selected_channel(self, channel_id: Optional[str]) -> None:
        """Set the selected YouTube channel ID.

        Args:
            channel_id: YouTube channel ID to use for API calls.
                       None means use default "mine" channel.
        """
        self.selected_channel_id = channel_id
        # Save immediately so it persists
        self.save_credentials()

    def get_selected_channel(self) -> Optional[str]:
        """Get the currently selected channel ID.

        Returns:
            Channel ID if set, None means use default "mine" channel.
        """
        return self.selected_channel_id

    def clear(self) -> None:
        """Clear credentials and selected channel from memory and disk."""
        self.credentials = None
        self.selected_channel_id = None
        if self.storage_path.exists():
            try:
                self.storage_path.unlink()
            except OSError:
                pass
