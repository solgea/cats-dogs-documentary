"""Yayın ajanı: biten render'ı denetler, karar verir ve YouTube'a yükler.

Akış üç katmandır:

1. **Kural tabanlı kapılar** her zaman çalışır: dosya bütünlüğü, medya
   doğrulaması, tekrar kontrolü, reddedilen pilot listesi, meta veri, kaynak
   atıfları, günlük kota ve YouTube oturumu.
2. **LLM ikinci görüşü** isteğe bağlıdır. Yapılandırılmamışsa yalnızca kurallar
   karar verir. LLM "ret" derse yükleme durur; LLM'e ulaşılamazsa ya da yanıtı
   ayrıştırılamazsa karar "inceleme gerekli" olur ve yine yükleme yapılmaz.
3. **Yükleme** yalnızca ``APPROVE`` kararında ve otonom yayın açıkken yapılır.
   Ajan ayar açıkça izin vermedikçe herkese açık yüklemez; varsayılan liste
   dışıdır.

Bu modül Streamlit'e bağımlı değildir; panel, arka plan render betiği ve CLI
aynı kararı paylaşır.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Project
from .media_probe import MediaInfo, validate_render
from .util import read_json, write_json

DECISION_FILE = "publish-agent-decisions.json"
UPLOAD_QUOTA_UNITS = 1600
DAILY_QUOTA_LIMIT = 10000

# Panelin yayın merkezinde kullandığı reddedilen pilot işareti.
REJECTED_PILOT_MARKERS = ("dog-guilty-look", "guilty look")

APPROVE = "APPROVE"
REJECT = "REJECT"
NEEDS_REVIEW = "NEEDS_REVIEW"
DISABLED = "DISABLED"


@dataclass
class Check:
    check_id: str
    label: str
    status: str  # PASS | WARN | FAIL
    detail: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "check_id": self.check_id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class Decision:
    verdict: str = REJECT
    checks: List[Check] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    media: Dict[str, Any] = field(default_factory=dict)
    llm_used: bool = False
    llm_model: str = ""
    llm_verdict: str = ""
    llm_reasons: List[str] = field(default_factory=list)
    decided_at: str = ""

    def add(self, check_id: str, label: str, status: str, detail: str) -> None:
        self.checks.append(Check(check_id, label, status, detail))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks": [check.to_dict() for check in self.checks],
            "reasons": list(self.reasons),
            "media": dict(self.media),
            "llm_used": self.llm_used,
            "llm_model": self.llm_model,
            "llm_verdict": self.llm_verdict,
            "llm_reasons": list(self.llm_reasons),
            "decided_at": self.decided_at,
        }


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _read_json_safe(path: Path, default: Any) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return payload if isinstance(payload, type(default)) else default


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_agent_settings(project: Project) -> Dict[str, Any]:
    """Panel ayarlarını (panel_settings.json) okur; yoksa boş sözlük döner."""
    return _read_json_safe(project.root / "panel_settings.json", {})


def youtube_token_valid() -> bool:
    try:
        from .youtube.config import YouTubeConfig
        from .youtube.token_manager import TokenManager

        manager = TokenManager(config=YouTubeConfig())
        return bool(manager.load_credentials() and manager.is_valid())
    except Exception:  # noqa: BLE001 - token yoksa yükleme zaten kapalı
        return False


def agent_privacy(settings: Dict[str, Any]) -> str:
    """Ajanın kullanacağı gizlilik; herkese açık yalnızca açık izinle."""
    privacy = str(settings.get("agent_privacy") or "unlisted").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "unlisted"
    if privacy == "public" and not settings.get("agent_allow_public"):
        privacy = "unlisted"
    return privacy


# NVIDIA multimodal model presets (vision-capable for video frame analysis)
NVIDIA_MODEL_PRESETS: Dict[str, Dict[str, Any]] = {
    "nemotron-3.5-super-vl": {
        "label": "Nemotron 3.5 Super VL (120B, vision)",
        "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "vision": True,
        "context": 262144,
    },
    "nemotron-3.5-super-vl-deepinfra": {
        "label": "Nemotron 3.5 Super VL via DeepInfra",
        "model": "nvidia/NVIDIA-Nemotron-3.5-Super-VL",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "key_env": "DEEPINFRA_API_KEY",
        "vision": True,
        "context": 262144,
    },
    "nemotron-3-nano-omni": {
        "label": "Nemotron 3 Nano Omni (30B, video+audio+image)",
        "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "vision": True,
        "context": 131072,
    },
    "nemotron-nano-12b-vl": {
        "label": "Nemotron Nano 12B V2 VL (vision)",
        "model": "nvidia/nemotron-nano-12b-v2-vl",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "vision": True,
        "context": 128000,
    },
    "nemotron-3-ultra": {
        "label": "Nemotron 3 Ultra (550B, text-only, no vision)",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "vision": False,
        "context": 1000000,
    },
}


def _llm_config(settings: Dict[str, Any]) -> Tuple[str, str, str]:
    """Resolve model, base_url, api_key from settings or NVIDIA presets."""
    # 1) Explicit settings override
    model = str(settings.get("agent_llm_model") or "").strip()
    base = str(settings.get("agent_llm_base_url") or "").strip()
    key_env = str(settings.get("agent_llm_api_key_env") or "").strip()
    key = os.environ.get(key_env) if key_env else ""

    # 2) If model matches a preset, fill in missing base/key
    if model in NVIDIA_MODEL_PRESETS:
        preset = NVIDIA_MODEL_PRESETS[model]
        if not base:
            base = preset["base_url"]
        if not key_env:
            key_env = preset["key_env"]
            key = os.environ.get(key_env) or ""

    # 3) Auto-select NVIDIA vision model if enabled but no explicit model
    if not model and settings.get("agent_llm_enabled"):
        auto_model = _auto_select_nvidia_model(settings)
        if auto_model:
            preset = NVIDIA_MODEL_PRESETS[auto_model]
            model = preset["model"]
            if not base:
                base = preset["base_url"]
            if not key_env:
                key_env = preset["key_env"]
                key = os.environ.get(key_env) or ""
            # Mark as auto-selected for logging
            settings["_auto_llm_model"] = auto_model

    # 4) Env fallbacks
    if not model:
        model = str(os.environ.get("CDDOCS_LLM_MODEL") or "").strip()
    if not base:
        base = str(os.environ.get("CDDOCS_LLM_BASE_URL") or "https://api.openai.com/v1").strip()
    if not key_env:
        key_env = str(settings.get("agent_llm_api_key_env") or "OPENAI_API_KEY").strip()
    if not key:
        key = os.environ.get(key_env) or os.environ.get("CDDOCS_LLM_API_KEY") or ""

    return model, base.rstrip("/"), key


def _auto_select_nvidia_model(settings: Dict[str, Any]) -> Optional[str]:
    """Pick the best available NVIDIA vision model based on env keys."""
    # Priority order: Super VL (best quality) -> Nano Omni (free) -> Nano 12B VL
    priority = [
        "nemotron-3.5-super-vl",
        "nemotron-3.5-super-vl-deepinfra",
        "nemotron-3-nano-omni",
        "nemotron-nano-12b-vl",
    ]
    for preset_id in priority:
        preset = NVIDIA_MODEL_PRESETS[preset_id]
        if os.environ.get(preset["key_env"]):
            return preset_id
    return None


def llm_configured(settings: Dict[str, Any]) -> bool:
    """LLM ikinci görüşü gerçekten kullanılabilir mi (açık + model + anahtar)?"""
    if not settings.get("agent_llm_enabled"):
        return False
    model, _base, key = _llm_config(settings)
    return bool(model and key)


# ---------------------------------------------------------------------------
# Kural tabanlı değerlendirme
# ---------------------------------------------------------------------------
def review_candidate(
    project: Project,
    candidate: Dict[str, Any],
    settings: Optional[Dict[str, Any]] = None,
    *,
    token_valid: Optional[bool] = None,
    registry: Optional[List[Dict[str, Any]]] = None,
    upload_history: Optional[Dict[str, Any]] = None,
) -> Decision:
    """Bir yayın adayını kural tabanlı kapılardan geçirir.

    Hiçbir ağ çağrısı yapmaz; LLM görüşü ayrı adımdadır. ``token_valid``,
    ``registry`` ve ``upload_history`` testlerde enjekte edilebilir.
    """
    settings = settings if settings is not None else load_agent_settings(project)
    decision = Decision(decided_at=_now())

    channel: Dict[str, Any] = {}
    try:
        channel = project.channel() or {}
    except Exception:  # noqa: BLE001 - kanal dosyası yoksa varsayılanlar
        channel = {}
    fmt = channel.get("format") or {}
    width = int(fmt.get("width") or 1080)
    height = int(fmt.get("height") or 1920)
    min_duration = float(fmt.get("min_duration_s") or 30)
    max_duration = float(fmt.get("max_duration_s") or 60)

    path = Path(str(candidate.get("path") or ""))
    if not path.is_absolute():
        path = project.root / path
    name = str(candidate.get("name") or path.name)
    title = str(candidate.get("title") or "").strip()
    description = str(candidate.get("description") or "").strip()
    tags = [str(tag).strip() for tag in (candidate.get("tags") or []) if str(tag).strip()]

    # 1) Dosya
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    decision.add(
        "file.exists",
        "Dosya bütünlüğü",
        "PASS" if exists and size > 0 else "FAIL",
        f"{size / 1_048_576:.1f} MB" if exists else "Video dosyası bulunamadı",
    )

    # 2) Medya doğrulaması (dikey, süre, ses)
    info: Optional[MediaInfo] = None
    issues: List[str] = []
    if exists:
        try:
            info, issues = validate_render(
                path,
                min_duration_s=min_duration,
                max_duration_s=max_duration,
                width=width,
                height=height,
            )
        except Exception as exc:  # noqa: BLE001 - bozuk dosya kapıyı kapatır
            issues = [f"Dosya okunamadı: {exc}"]
    media_ok = bool(info and info.ok) and not issues
    if exists:
        decision.add(
            "media.render",
            "Video doğrulaması",
            "PASS" if media_ok else "FAIL",
            "; ".join(issues) if issues else (
                f"{info.width}×{info.height} · {info.duration_s:.1f} sn · ses "
                f"{'var' if info.has_audio else 'yok'}" if info else "doğrulanamadı"
            ),
        )
        decision.media = info.to_dict() if info else {}

    # 3) Reddedilen pilot
    lowered = f"{name} {title}".casefold()
    rejected = any(marker in lowered for marker in REJECTED_PILOT_MARKERS)
    if rejected:
        decision.add("policy.rejected", "Reddedilen pilot", "FAIL",
                     "Bu çıktı daha önce yayın için reddedildi.")

    # 4) Tekrar kontrolü — YouTube sicili (yayınlanmış + planlanmış + private/unlisted), yükleme geçmişi
    if registry is None:
        payload = _read_json_safe(project.root / "content_registry.json", [])
        registry = payload if isinstance(payload, list) else list(payload.values())
    title_key = _norm(title)
    job_id = str(candidate.get("job_id") or "").strip()
    duplicate = ""
    duplicate_details = []
    for entry in registry or []:
        if not isinstance(entry, dict) or not entry.get("youtube_id"):
            continue
        entry_status = str(entry.get("status") or "").lower()
        entry_privacy = str(entry.get("privacy_status") or "").lower()
        entry_scheduled = entry.get("is_scheduled", False)
        entry_scheduled_time = str(entry.get("scheduled_publish_time") or "")
        matched_by = ""
        if title_key and _norm(entry.get("title")) == title_key:
            matched_by = "başlık eşleşti"
        elif job_id and str(entry.get("viewmade_id") or "") == job_id:
            matched_by = f"ViewMade job_id={job_id} eşleşti"
        if matched_by:
            # Determine human-readable status
            if entry_scheduled:
                status_str = f"PLANLANMIŞ ({entry_scheduled_time[:16]})"
            elif entry_status in ("private", "unlisted"):
                status_str = entry_status.upper()
            else:
                status_str = "YAYINDA"
            duplicate_details.append(
                f"“{entry.get('title')}” · YouTube: {entry['youtube_id']} · Durum: {status_str} · {matched_by}"
            )

    if upload_history is None:
        upload_history = _read_json_safe(project.root / "upload_history.json", {})
    if not duplicate_details and exists:
        try:
            previous = (upload_history or {}).get(_sha256_file(path)) or {}
        except OSError:
            previous = {}
        if previous.get("video_id"):
            duplicate_details.append(
                f"Aynı dosya (hash) daha önce yüklendi: {previous['video_id']}"
            )

    duplicate = "; ".join(duplicate_details)
    decision.add(
        "duplicate.youtube",
        "Tekrar kontrolü (yayınlanmış + planlanmış + private/unlisted + hash)",
        "FAIL" if duplicate_details else "PASS",
        duplicate or "Sicilde, planlarda ve yükleme geçmişinde eşleşme yok",
    )

    # 5) Meta veri
    title_ok = 0 < len(title) <= 100
    decision.add("metadata.title", "Başlık", "PASS" if title_ok else "FAIL",
                 f"{len(title)}/100 karakter" if title else "Başlık boş")
    description_ok = 0 < len(description) <= 5000
    decision.add("metadata.description", "Açıklama",
                 "PASS" if description_ok else "FAIL",
                 f"{len(description)}/5000 karakter" if description else "Açıklama boş")
    decision.add("metadata.tags", "Etiketler",
                 "PASS" if len(tags) >= 3 else "WARN",
                 f"{len(tags)} etiket" + ("" if len(tags) >= 3 else " (en az 3 önerilir)"))

    # 6) Kaynak atıfları — gerçek görüntü kullanan çıktılarda zorunlu
    sources = candidate.get("sources") or []
    attributions = candidate.get("attributions") or []
    if sources and not attributions:
        decision.add("rights.attribution", "Kaynak atıfları", "FAIL",
                     f"{len(sources)} kaynak var ama atıf metni yok")
    else:
        decision.add("rights.attribution", "Kaynak atıfları", "PASS",
                     f"{len(attributions)} atıf" if attributions else "atıf gerekmiyor")

    # 7) Günlük kota — yükleme başına ~1600 birim
    today = datetime.now().strftime("%Y-%m-%d")
    today_uploads = sum(
        1 for record in (upload_history or {}).values()
        if isinstance(record, dict) and str(record.get("uploaded_at") or "")[:10] == today
    )
    max_daily = int(settings.get("max_daily") or 5)
    budget = min(max_daily, DAILY_QUOTA_LIMIT // UPLOAD_QUOTA_UNITS)
    decision.add(
        "quota.daily",
        "Günlük kota",
        "PASS" if today_uploads < max(1, budget) else "FAIL",
        f"Bugün {today_uploads} yükleme · sınır {max(1, budget)}",
    )

    # 8) YouTube oturumu
    if token_valid is None:
        token_valid = youtube_token_valid()
    decision.add("channel.token", "YouTube bağlantısı",
                 "PASS" if token_valid else "FAIL",
                 "OAuth oturumu geçerli" if token_valid else "Geçerli token yok")

    # 9) Gizlilik ayarı tutarlı mı
    privacy = agent_privacy(settings)
    decision.add("policy.privacy", "Gizlilik", "PASS",
                 f"Ajan yüklemesi: {privacy}")

    fails = [check for check in decision.checks if check.status == "FAIL"]
    warns = [check for check in decision.checks if check.status == "WARN"]
    if fails:
        decision.verdict = REJECT
    elif warns:
        decision.verdict = NEEDS_REVIEW
    else:
        decision.verdict = APPROVE
    decision.reasons = [
        f"{check.label}: {check.detail}"
        for check in decision.checks
        if check.status != "PASS"
    ]
    return decision


# ---------------------------------------------------------------------------
# LLM ikinci görüşü
# ---------------------------------------------------------------------------
def _frame_data_urls(path: Path, duration_s: Optional[float], count: int = 4) -> List[str]:
    """Videodan birkaç kare çıkarır; ffmpeg yoksa boş liste döner."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not duration_s or duration_s <= 0:
        return []
    urls: List[str] = []
    folder = Path(tempfile.mkdtemp(prefix="cddocs_frames_"))
    try:
        for index in range(count):
            moment = duration_s * (index + 0.5) / count
            target = folder / f"frame_{index}.jpg"
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-ss", f"{moment:.2f}",
                     "-i", str(path), "-frames:v", "1",
                     "-vf", "scale=360:-2", str(target)],
                    capture_output=True, timeout=30, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if target.is_file() and target.stat().st_size > 0:
                encoded = base64.b64encode(target.read_bytes()).decode("ascii")
                urls.append(f"data:image/jpeg;base64,{encoded}")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return urls


def _parse_llm_response(text: str) -> Tuple[str, List[str]]:
    cleaned = re.sub(r"```(?:json)?", "", str(text or "")).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM yanıtında JSON bulunamadı")
    payload = json.loads(cleaned[start:end + 1])
    verdict = str(payload.get("verdict") or "").strip().lower()
    reasons = [str(reason) for reason in (payload.get("reasons") or []) if str(reason).strip()]
    if verdict in {"approve", "approved", "accept", "accepted", "pass"}:
        return "approve", reasons
    if verdict in {"reject", "rejected", "fail", "failed"}:
        return "reject", reasons
    return "review", reasons or ["LLM kararsız bir yanıt verdi"]


def llm_second_opinion(
    candidate: Dict[str, Any],
    decision: Decision,
    settings: Dict[str, Any],
) -> Tuple[str, List[str], str]:
    """LLM'e kısa bir dosya özeti ve video kareleri gönderir.

    Dönen ilk değer ``approve``, ``reject`` ya da ``review`` olur. Ağ hatası,
    eksik anahtar veya ayrıştırılamayan yanıt ``review`` sayılır: yükleme
    yapılmaz (fail closed).
    """
    model, base_url, api_key = _llm_config(settings)

    if not settings.get("agent_llm_enabled") or not model or not api_key:
        return "review", ["LLM ikinci görüşü yapılandırılmadı"], model

    path = Path(str(candidate.get("path") or ""))
    duration = (decision.media or {}).get("duration_s")
    frames = _frame_data_urls(path, duration)

    dossier = {
        "title": str(candidate.get("title") or ""),
        "description": str(candidate.get("description") or "")[:1200],
        "tags": list(candidate.get("tags") or [])[:15],
        "duration_s": duration,
        "resolution": f"{(decision.media or {}).get('width')}x"
                      f"{(decision.media or {}).get('height')}",
        "has_audio": (decision.media or {}).get("has_audio"),
        "scene_count": candidate.get("scene_count"),
        "provider_status": candidate.get("provider_status"),
        "sources": [
            str((source or {}).get("title") or (source or {}).get("url") or source)[:160]
            if isinstance(source, dict) else str(source)[:160]
            for source in (candidate.get("sources") or [])[:10]
        ],
        "attributions": [str(line)[:160] for line in (candidate.get("attributions") or [])[:10]],
    }
    system_prompt = (
        "Sen bir YouTube kanalının yayın ajanısın. Kanal: cats & dogs documentary "
        "kısa videoları, 9:16, 30-60 saniye. Videoyu ve meta veriyi denetle. "
        "Su işareti, altyazı bozulması, ilgisiz/çöp görüntü, eksik kaynak atfı, "
        "yanıltıcı bilimsel iddia veya telif riski varsa reddet. Yalnızca şu "
        "JSON'u döndür: {\"verdict\": \"approve\" veya \"reject\", "
        "\"reasons\": [\"kısa Türkçe gerekçe\"]}"
    )
    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": json.dumps(dossier, ensure_ascii=False)},
    ]
    for url in frames:
        user_content.append({"type": "image_url", "image_url": {"url": url}})

    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        verdict, reasons = _parse_llm_response(content)
        return verdict, reasons, model
    except (urllib.error.URLError, OSError, KeyError, ValueError, TypeError) as exc:
        return "review", [f"LLM çağrısı başarısız: {exc}"], model


# ---------------------------------------------------------------------------
# Yükleme ve karar kaydı
# ---------------------------------------------------------------------------
def upload_candidate(
    project: Project,
    candidate: Dict[str, Any],
    *,
    privacy: str = "unlisted",
    category_id: str = "15",
) -> Dict[str, Any]:
    """Onaylanmış adayı YouTube'a yükler (UploadManager'ın kendi kapılarıyla)."""
    from .youtube.config import YouTubeConfig
    from .youtube.token_manager import TokenManager
    from .youtube.upload import UploadManager

    config = YouTubeConfig()
    tokens = TokenManager(config=config)
    if not tokens.load_credentials():
        raise RuntimeError("YouTube token dosyası bulunamadı; Ayarlar'dan bağlanın.")
    if not tokens.is_valid():
        raise RuntimeError("YouTube oturumu geçersiz; Ayarlar'dan yeniden bağlanın.")

    manager = UploadManager(
        tokens,
        config=config,
        history_file=str(project.root / "upload_history.json"),
    )
    return manager.upload_short(
        str(candidate["path"]),
        str(candidate.get("title") or "").strip(),
        str(candidate.get("description") or "").strip(),
        [str(tag).strip() for tag in (candidate.get("tags") or []) if str(tag).strip()],
        privacy_status=privacy,
        category_id=category_id,
        confirm_public=(privacy == "public"),
    )


def recent_decisions(project: Project, limit: int = 10) -> List[Dict[str, Any]]:
    entries = _read_json_safe(project.state_dir / DECISION_FILE, [])
    return entries[:limit] if isinstance(entries, list) else []


def record_decision(
    project: Project,
    candidate: Dict[str, Any],
    outcome: Dict[str, Any],
) -> Path:
    entries = recent_decisions(project, limit=1000)
    entry = {
        "decided_at": outcome.get("decided_at") or _now(),
        "title": str(candidate.get("title") or ""),
        "file": str(candidate.get("path") or ""),
        "verdict": outcome.get("verdict") or REJECT,
        "reasons": list(outcome.get("reasons") or []),
        "checks": list(outcome.get("checks") or []),
        "llm_used": bool(outcome.get("llm_used")),
        "llm_model": outcome.get("llm_model") or "",
        "llm_verdict": outcome.get("llm_verdict") or "",
        "llm_reasons": list(outcome.get("llm_reasons") or []),
        "privacy": outcome.get("privacy") or "",
        "upload": outcome.get("upload"),
        "error": outcome.get("error") or "",
    }
    entries.insert(0, entry)
    target = project.state_dir / DECISION_FILE
    project.state_dir.mkdir(parents=True, exist_ok=True)
    write_json(target, entries[:100])
    return target


def run_agent(
    project: Project,
    candidate: Dict[str, Any],
    settings: Optional[Dict[str, Any]] = None,
    *,
    allow_upload: bool = True,
    token_valid: Optional[bool] = None,
    registry: Optional[List[Dict[str, Any]]] = None,
    upload_history: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Adayı değerlendirir, gerekirse LLM'e sorar ve onaylanırsa yükler."""
    settings = settings if settings is not None else load_agent_settings(project)
    if settings.get("agent_enabled") is False:
        outcome = {
            "verdict": DISABLED,
            "reasons": ["Yayın ajanı Ayarlar'dan kapatılmış."],
            "checks": [],
            "decided_at": _now(),
            "upload": None,
        }
        return outcome

    decision = review_candidate(
        project, candidate, settings,
        token_valid=token_valid, registry=registry, upload_history=upload_history,
    )

    if llm_configured(settings):
        verdict, reasons, model = llm_second_opinion(candidate, decision, settings)
        decision.llm_used = True
        decision.llm_model = model
        decision.llm_verdict = verdict
        decision.llm_reasons = list(reasons)
        if verdict == "reject":
            decision.verdict = REJECT
            decision.add("llm.review", "LLM ikinci görüş", "FAIL",
                         "; ".join(reasons) or "LLM onay vermedi")
        elif verdict == "review":
            decision.verdict = NEEDS_REVIEW
            decision.add("llm.review", "LLM ikinci görüş", "WARN",
                         "; ".join(reasons) or "LLM karar veremedi")
        else:
            decision.add("llm.review", "LLM ikinci görüş", "PASS",
                         "; ".join(reasons) or "LLM onayladı")
        decision.reasons = [
            f"{check.label}: {check.detail}"
            for check in decision.checks
            if check.status != "PASS"
        ]

    outcome: Dict[str, Any] = decision.to_dict()
    outcome["privacy"] = agent_privacy(settings)
    outcome["upload"] = None
    outcome["error"] = ""

    if allow_upload and decision.verdict == APPROVE:
        try:
            outcome["upload"] = upload_candidate(
                project,
                candidate,
                privacy=outcome["privacy"],
                category_id=str(settings.get("category_id") or "15"),
            )
        except Exception as exc:  # noqa: BLE001 - panel/scroll hatayı göstermeli
            outcome["error"] = f"{type(exc).__name__}: {exc}"
            outcome["verdict"] = NEEDS_REVIEW
            outcome["reasons"].append(f"Yükleme başarısız: {exc}")

    record_decision(project, candidate, outcome)
    return outcome
