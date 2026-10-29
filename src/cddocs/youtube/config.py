"""YouTube Integration - Merkezi Yapılandırma."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class YouTubeConfig:
    """YouTube API yapılandırması. Tüm değerler ortam değişkeninden veya varsayılandan okunur."""

    # OAuth 2.0
    client_id: str = field(default_factory=lambda: os.environ.get("YOUTUBE_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.environ.get("YOUTUBE_CLIENT_SECRET", ""))
    redirect_uris: List[str] = field(
        default_factory=lambda: [
            uri.strip()
            for uri in os.environ.get("YOUTUBE_REDIRECT_URIS", "http://localhost:8501").split(",")
            if uri.strip()
        ]
    )
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"

    # Scopes
    scopes: List[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/youtube.readonly",
    ])

    # API
    api_service_name: str = "youtube"
    api_version: str = "v3"
    analytics_service_name: str = "youtubeAnalytics"
    analytics_version: str = "v2"

    # Upload
    upload_chunk_size: int = 1024 * 1024  # 1MB
    max_retries: int = 3
    default_privacy_status: str = "unlisted"
    default_category_id: str = "15"  # Pets & Animals

    # Quota
    daily_quota_limit: int = 10000  # YouTube default daily quota
    quota_reset_hour: int = 0  # UTC hour when quota resets

    # Storage
    token_storage_path: str = "youtube_token.json"
    token_file_permissions: int = 0o600

    # Disclosure (Zorunlu)
    disclosure_text: str = (
        "Real-footage montage using third-party clips for illustration; "
        "not documentary footage or scientific evidence."
    )

    def validate(self) -> List[str]:
        """Yapılandırmayı doğrula, eksik alanları döndür."""
        errors: List[str] = []
        if not self.client_id:
            errors.append("YOUTUBE_CLIENT_ID ayarlanmamış")
        if not self.client_secret:
            errors.append("YOUTUBE_CLIENT_SECRET ayarlanmamış")
        if self.max_retries < 1:
            errors.append("MAX_RETRIES en az 1 olmalı")
        if self.default_privacy_status not in ("public", "private", "unlisted"):
            errors.append("DEFAULT_PRIVACY_STATUS 'public', 'private' veya 'unlisted' olmalı")
        return errors

    def is_secure(self) -> bool:
        """Gizli anahtarlar ayarlanmış mı?"""
        return bool(self.client_id and self.client_secret)
