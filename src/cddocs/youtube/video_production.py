"""Video Production Manager — Viewmade / AI video üretim entegrasyonu.

Sağlayıcılar:
  • slideshow: Yerel görsellerden slayt videosu (ücretsiz)
  • viewmade : Viewmade video oluşturma platformu
  • minimax  : NVIDIA hosted MiniMax
  • kling    : Kling AI
  • openai   : OpenAI video
  • gemini   : Google Gemini
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import YouTubeConfig
from .token_manager import TokenManager


class VideoProviderError(Exception):
    """Video sağlayıcısı hatası."""


class VideoProductionManager:
    """Çoklu sağlayıcı video üretim yöneticisi."""

    def __init__(self, config: YouTubeConfig, token_manager: Optional[TokenManager] = None):
        self.config = config
        self.token_manager = token_manager
        self._history_file = Path("video_production_history.json")

    # -- geçmiş -------------------------------------------------------------
    def _load_history(self) -> Dict[str, Any]:
        if not self._history_file.exists():
            return {}
        try:
            return json.loads(self._history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_history(self, history: Dict[str, Any]) -> None:
        try:
            self._history_file.write_text(
                json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def get_production_history(self) -> Dict[str, Any]:
        return self._load_history()

    def clear_production_history(self) -> None:
        try:
            self._history_file.unlink()
        except OSError:
            pass

    def _record_production(self, source: str, output_path: str, provider: str,
                           status: str, video_id: Optional[str] = None) -> None:
        history = self._load_history()
        digest = self._file_hash(output_path) if os.path.exists(output_path) else ""
        history[digest or output_path] = {
            "source": source[:200],
            "output_path": output_path,
            "provider": provider,
            "status": status,
            "video_id": video_id,
            "created_at": datetime.now().isoformat(),
        }
        self._save_history(history)

    @staticmethod
    def _file_hash(file_path: str) -> str:
        sha = hashlib.sha256()
        try:
            with open(file_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        except (IOError, OSError):
            return ""

    # -- kullanılabilirlik ----------------------------------------------------
    def is_available(self, provider: str) -> bool:
        if provider == "slideshow":
            return True
        if provider == "viewmade":
            return bool(os.environ.get("VIEWMADE_API_KEY") or os.environ.get("VIEWMADE_API_URL"))
        if provider == "minimax":
            return bool(os.environ.get("NVIDIA_API_KEY"))
        if provider == "kling":
            return bool(os.environ.get("KLING_ACCESS_KEY") and os.environ.get("KLING_SECRET_KEY"))
        if provider == "openai":
            return bool(os.environ.get("OPENAI_API_KEY"))
        if provider == "gemini":
            return bool(os.environ.get("GEMINI_API_KEY"))
        return False

    def get_available_providers(self) -> List[Dict[str, Any]]:
        return [
            {"id": "slideshow", "name": "Slideshow (Yerel)",
             "description": "Yerel görsellerden slayt videosu. Ücretsiz, anahtar gerekmez.",
             "available": self.is_available("slideshow"), "cost": "Ücretsiz"},
            {"id": "viewmade", "name": "Viewmade",
             "description": "Viewmade platformu ile profesyonel video üretimi.",
             "available": self.is_available("viewmade"), "cost": "API anahtarı gerekli"},
            {"id": "minimax", "name": "MiniMax (NVIDIA)",
             "description": "NVIDIA hosted MiniMax video modeli.",
             "available": self.is_available("minimax"), "cost": "API kredisi gerekli"},
            {"id": "kling", "name": "Kling AI",
             "description": "Kling AI video üretimi.",
             "available": self.is_available("kling"), "cost": "API kredisi gerekli"},
            {"id": "openai", "name": "OpenAI Video",
             "description": "OpenAI video modeli.",
             "available": self.is_available("openai"), "cost": "API kredisi gerekli"},
            {"id": "gemini", "name": "Google Gemini",
             "description": "Google Gemini video üretimi.",
             "available": self.is_available("gemini"), "cost": "API kredisi gerekli"},
        ]

    # -- üretim ---------------------------------------------------------------
    def generate_video(self, source_text: str, provider: str = "slideshow",
                       output_path: Optional[str] = None,
                       progress_callback: Optional[Callable[[int, int], None]] = None,
                       **kwargs) -> Dict[str, Any]:
        if not self.is_available(provider):
            raise VideoProviderError(
                f"Sağlayıcı '{provider}' yapılandırılmamış veya API anahtarı eksik.")

        if output_path is None:
            safe = "".join(c for c in source_text[:30] if c.isalnum() or c in " -_").strip()
            output_path = f"outputs/video_{safe or 'video'}_{int(time.time())}.mp4"

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        def report(done: int, total: int) -> None:
            if progress_callback:
                try:
                    progress_callback(done, total)
                except Exception:
                    pass

        report(0, 100)
        try:
            if provider == "slideshow":
                result = self._generate_slideshow(source_text, output_path, **kwargs)
            elif provider == "viewmade":
                result = self._generate_viewmade(source_text, output_path, report, **kwargs)
            elif provider == "minimax":
                result = self._generate_minimax(source_text, output_path, **kwargs)
            elif provider == "kling":
                result = self._generate_kling(source_text, output_path, **kwargs)
            elif provider == "openai":
                result = self._generate_openai(source_text, output_path, **kwargs)
            elif provider == "gemini":
                result = self._generate_gemini(source_text, output_path, **kwargs)
            else:
                raise VideoProviderError(f"Bilinmeyen sağlayıcı: {provider}")
            report(100, 100)
            self._record_production(source_text, output_path, provider,
                                    result.get("status", "completed"), result.get("video_id"))
            return result
        except VideoProviderError:
            raise
        except Exception as exc:
            raise VideoProviderError(f"Video üretimi başarısız ({provider}): {exc}") from exc

    # -- sağlayıcı uygulamaları -------------------------------------------------
    def _generate_slideshow(self, source_text: str, output_path: str, **kwargs) -> Dict[str, Any]:
        return {"video_path": output_path, "provider": "slideshow", "status": "pending_render",
                "video_id": None, "message": "Slayt videosu kuyruğa alındı (FFmpeg render)."}

    def _generate_viewmade(self, source_text: str, output_path: str,
                           report: Callable[[int, int], None], **kwargs) -> Dict[str, Any]:
        api_key = os.environ.get("VIEWMADE_API_KEY")
        api_url = os.environ.get("VIEWMADE_API_URL", "https://api.viewmade.com/v1")
        if not api_key:
            raise VideoProviderError("VIEWMADE_API_KEY ortam değişkeni eksik.")
        try:
            import requests
        except ImportError as exc:
            raise VideoProviderError("requests kütüphanesi yüklü değil.") from exc

        try:
            response = requests.post(
                f"{api_url}/projects",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={"title": source_text[:100], "script": source_text,
                      "format": kwargs.get("aspect_ratio", "16:9"),
                      "duration": kwargs.get("duration", 60)},
                timeout=30,
            )
            response.raise_for_status()
            project = response.json()
            project_id = project.get("id")
            report(30, 100)

            render_response = requests.post(
                f"{api_url}/projects/{project_id}/render",
                headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
            render_response.raise_for_status()
            render_data = render_response.json()
            report(90, 100)

            video_url = render_data.get("video_url")
            if video_url:
                video_response = requests.get(video_url, timeout=120)
                video_response.raise_for_status()
                with open(output_path, "wb") as handle:
                    handle.write(video_response.content)

            return {"video_path": output_path, "provider": "viewmade", "status": "completed",
                    "project_id": project_id, "video_id": render_data.get("video_id"),
                    "viewmade_url": render_data.get("viewmade_url")}
        except requests.RequestException as exc:
            raise VideoProviderError(f"Viewmade API hatası: {exc}") from exc

    def _generate_minimax(self, source_text: str, output_path: str, **kwargs) -> Dict[str, Any]:
        return {"video_path": output_path, "provider": "minimax", "status": "pending",
                "video_id": None, "message": "MiniMax entegrasyonu hazırlanıyor."}

    def _generate_kling(self, source_text: str, output_path: str, **kwargs) -> Dict[str, Any]:
        return {"video_path": output_path, "provider": "kling", "status": "pending",
                "video_id": None, "message": "Kling AI entegrasyonu hazırlanıyor."}

    def _generate_openai(self, source_text: str, output_path: str, **kwargs) -> Dict[str, Any]:
        return {"video_path": output_path, "provider": "openai", "status": "pending",
                "video_id": None, "message": "OpenAI entegrasyonu hazırlanıyor."}

    def _generate_gemini(self, source_text: str, output_path: str, **kwargs) -> Dict[str, Any]:
        return {"video_path": output_path, "provider": "gemini", "status": "pending",
                "video_id": None, "message": "Gemini entegrasyonu hazırlanıyor."}
