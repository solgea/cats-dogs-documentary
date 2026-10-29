"""Async wrappers for YouTube upload and API operations."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from .api_client import YouTubeAPIClient
from .config import YouTubeConfig
from .token_manager import TokenManager
from .upload import UploadManager

logger = logging.getLogger(__name__)


class AsyncYouTubeClient:
    """Async wrapper for YouTube API operations.

    Runs synchronous API calls in a thread pool executor to avoid
    blocking the event loop.
    """

    def __init__(
        self,
        token_manager: TokenManager,
        config: Optional[YouTubeConfig] = None,
    ):
        self.config = config or YouTubeConfig()
        self._sync_client = YouTubeAPIClient(token_manager, config=self.config)
        self._executor: Optional[asyncio.AbstractExecutor] = None

    @property
    def _loop(self) -> asyncio.AbstractEventLoop:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    async def _run_in_executor(self, func, *args, **kwargs):
        """Run a synchronous function in the default executor."""
        loop = self._loop
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def upload_short(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = "unlisted",
        category_id: str = "15",
        confirm_public: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """Async upload a YouTube video."""
        return await self._run_in_executor(
            self._sync_client.upload_short,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            category_id=category_id,
            confirm_public=confirm_public,
            progress_callback=progress_callback,
        )

    async def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Async get video statistics."""
        return await self._run_in_executor(
            self._sync_client.get_video_stats, video_id
        )

    async def get_channel_stats(self) -> Dict[str, Any]:
        """Async get channel statistics."""
        return await self._run_in_executor(
            self._sync_client.get_channel_stats
        )

    async def list_accessible_channels(self) -> List[Dict[str, Any]]:
        """Async list accessible channels."""
        return await self._run_in_executor(
            self._sync_client.list_accessible_channels
        )

    @property
    def quota_used_today(self) -> int:
        """Return estimated quota used today."""
        return self._sync_client.quota_used_today


class AsyncUploadManager:
    """Async wrapper for UploadManager."""

    def __init__(
        self,
        token_manager: TokenManager,
        config: Optional[YouTubeConfig] = None,
        history_file: Optional[str] = None,
    ):
        self.config = config or YouTubeConfig()
        self._sync_manager = UploadManager(
            token_manager, config=self.config, history_file=history_file
        )

    @property
    def _loop(self) -> asyncio.AbstractEventLoop:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    async def _run_in_executor(self, func, *args, **kwargs):
        loop = self._loop
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def upload_short(
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
        """Async upload a YouTube video."""
        return await self._run_in_executor(
            self._sync_manager.upload_short,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            category_id=category_id,
            confirm_public=confirm_public,
            progress_callback=progress_callback,
            allow_duplicate=allow_duplicate,
        )

    async def set_privacy_status(
        self,
        video_id: str,
        privacy_status: str,
        confirm_public: bool = False,
    ) -> Dict[str, Any]:
        """Async change video privacy status."""
        return await self._run_in_executor(
            self._sync_manager.set_privacy_status,
            video_id=video_id,
            privacy_status=privacy_status,
            confirm_public=confirm_public,
        )

    def get_upload_history(self) -> Dict[str, Any]:
        """Return the full upload history (sync)."""
        return self._sync_manager.get_upload_history()
