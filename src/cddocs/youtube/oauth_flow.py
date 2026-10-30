"""OAuth 2.0 Authorization Flow for YouTube Integration."""

from __future__ import annotations

import webbrowser
from typing import Optional, Tuple

from google_auth_oauthlib.flow import InstalledAppFlow

from .config import YouTubeConfig


class OAuthFlowManager:
    """OAuth 2.0 yetkilendirme akışını yönetir.

    Kullanıcıyı Google yetkilendirme sayfasına yönlendirir,
    authorization code alıp access/refresh token'e dönüştürür.
    """

    def __init__(self, config: YouTubeConfig):
        self.config = config

    def run_local_server(self, port: int = 8502) -> Optional[Tuple[str, str]]:
        """Yerel sunucu üzerinden OAuth akışını çalıştırır.

        Returns:
            (access_token, refresh_token) tuple'ı veya None (iptal durumunda)
        """
        if not self.config.is_secure():
            raise ValueError(
                "YOUTUBE_CLIENT_ID ve YOUTUBE_CLIENT_SECRET ortam değişkenleri gereklidir"
            )

        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "auth_uri": self.config.auth_uri,
                    "token_uri": self.config.token_uri,
                    "redirect_uris": self.config.redirect_uris,
                }
            },
            scopes=self.config.scopes,
        )

        try:
            credentials = flow.run_local_server(
                port=port,
                open_browser=True,
                success_message="YouTube yetkilendirmesi tamamlandı! Bu sayfayı kapatabilirsiniz.",
            )
            return credentials.token, credentials.refresh_token
        except Exception as e:
            print(f"OAuth akışı hatası: {e}")
            return None

    def get_authorization_url(self) -> str:
        """Yetkilendirme URL'sini oluşturur (manuel akış için)."""
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "auth_uri": self.config.auth_uri,
                    "token_uri": self.config.token_uri,
                    "redirect_uris": self.config.redirect_uris,
                }
            },
            scopes=self.config.scopes,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url

    def exchange_code(self, code_or_url: str) -> Optional[Tuple[str, str]]:
        """Yetkilendirme kodunu (veya tam redirect URL'sini) token'e dönüştürür.

        Args:
            code_or_url: Ham yetkilendirme kodu (örn. "4/0Axxx…")
                veya Google'ın yönlendirdiği tam URL (içinde code= varsa ayıklanır).

        Returns:
            (access_token, refresh_token) veya None.
        """
        from urllib.parse import parse_qs, urlparse

        if not self.config.is_secure():
            raise ValueError(
                "YOUTUBE_CLIENT_ID ve YOUTUBE_CLIENT_SECRET ortam değişkenleri gereklidir"
            )

        raw = (code_or_url or "").strip()
        if "code=" in raw:
            try:
                query = parse_qs(urlparse(raw).query)
                if query.get("code"):
                    raw = query["code"][0]
            except ValueError:
                pass
        if not raw:
            return None

        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "auth_uri": self.config.auth_uri,
                    "token_uri": self.config.token_uri,
                    "redirect_uris": self.config.redirect_uris,
                }
            },
            scopes=self.config.scopes,
        )
        flow.redirect_uri = next(iter(self.config.redirect_uris), "http://localhost:8502")
        flow.fetch_token(code=raw)
        credentials = flow.credentials
        return credentials.token, credentials.refresh_token

    def open_browser(self, url: str) -> None:
        """Tarayıcıda yetkilendirme URL'sini açar."""
        webbrowser.open(url)
