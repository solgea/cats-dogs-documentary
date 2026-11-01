"""Panelden başlatılan ücretli ViewMade render işini arka planda yürütür.

Bu betik yalnızca panelin açık onayından sonra çalışır ve iki kapıyı da
zorunlu tutar:

* ``CDDOCS_LIVE_CONFIRM=YES`` ortam değişkeni,
* request dosyasının ``status`` alanının ``NOT_SUBMITTED`` olması.

Durum dosyası ``state/dashboard-render-<slug>.json`` altında tutulur; panel
bu dosyayı okuyarak ilerlemeyi gösterir. Render tamamlandığında adapter
videoyu indirir, 1080x1920'ye normalize eder ve request dosyasını
``COMPLETE`` olarak günceller.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cddocs.config import Project, Settings  # noqa: E402
from cddocs.util import read_json, write_json  # noqa: E402
from cddocs.viewmade.adapter import ViewMadeAdapter  # noqa: E402


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _state_path(project: Project, slug: str) -> Path:
    folder = project.state_dir
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"dashboard-render-{slug}.json"


def _write_state(path: Path, payload: dict) -> None:
    write_json(path, payload)


def _log(state_path: Path, message: str) -> None:
    line = f"[{_now()}] {message}"
    print(line, flush=True)
    with state_path.with_suffix(".log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _activity(project: Project, message: str, kind: str = "info") -> None:
    """Panelin okuduğu etkinlik günlüğüne tek satır ekler."""
    path = project.root / "activity_log.json"
    entries: list = []
    if path.is_file():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entries = []
    if not isinstance(entries, list):
        entries = []
    entries.insert(0, {"ts": datetime.now().strftime("%d.%m %H:%M"),
                       "msg": message, "kind": kind})
    try:
        path.write_text(json.dumps(entries[:200], indent=2, ensure_ascii=False),
                        encoding="utf-8")
    except OSError:
        pass


def _publish_candidate(project: Project, slug: str, request_payload: dict,
                       result) -> dict:
    """Render çıktısını yayın ajanının beklediği adaya çevirir."""
    package = request_payload.get("provider_package") or {}
    body = request_payload.get("request") or {}
    render_path = str(getattr(result, "render_path", "") or "")
    path = project.root / render_path if render_path else project.root / "renders" / f"{slug}.mp4"

    tags = package.get("tags") or body.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]

    description = str(package.get("description") or body.get("description")
                      or body.get("topic") or "").strip()
    try:
        config = project.viewmade() or {}
        disclosure = str((config.get("render") or {}).get("disclosure") or "").strip()
    except Exception:  # noqa: BLE001 - yapılandırma yoksa açıklama yine geçerli
        disclosure = ""
    attributions = [str(line) for line in (package.get("attributions") or []) if str(line).strip()]
    if attributions:
        description = (description + "\n\nKaynaklar / Atıf:\n" +
                       "\n".join(f"• {line}" for line in attributions)).strip()
    if disclosure and disclosure not in description:
        description = f"{description}\n\n{disclosure}".strip()

    return {
        "path": path,
        "name": path.name,
        "title": str(package.get("title") or body.get("title") or slug).strip(),
        "description": description,
        "tags": list(tags)[:15],
        "sources": package.get("sources") or [],
        "attributions": attributions,
        "provider_status": (getattr(result, "provider_state", "") or
                            package.get("status") or ""),
        "job_id": str(getattr(result, "job_id", "") or ""),
        "scene_count": package.get("scene_count"),
    }


def _run_publish_agent(project: Project, slug: str, request_payload: dict,
                       result, state_path: Path) -> dict:
    """Render tamamlandığında yayın ajanını çalıştırır (otonom mod açıksa)."""
    from cddocs.publish_agent import load_agent_settings, run_agent

    settings = load_agent_settings(project)
    if settings.get("agent_enabled") is False:
        _log(state_path, "Yayın ajanı kapalı; otomatik yükleme atlandı.")
        return {}
    if not settings.get("agent_auto_publish", True):
        _log(state_path, "Otonom yayın kapalı; çıktı yalnızca incelemeye hazır.")
        return {}

    candidate = _publish_candidate(project, slug, request_payload, result)
    # Phase 1A: Background render path MUST NOT upload without explicit human approval.
    # allow_upload=False is the safe default; only the manual dashboard path with
    # explicit approval record should ever pass allow_upload=True.
    outcome = run_agent(project, candidate, settings, allow_upload=False)
    verdict = outcome.get("verdict") or "REJECT"
    upload = outcome.get("upload") or {}
    video_id = str((upload or {}).get("video_id") or "")
    reasons = "; ".join(outcome.get("reasons") or [])[:400]

    if video_id:
        _log(state_path, f"Yayın ajanı ONAYLADI · YouTube'a yüklendi: {video_id} "
                         f"({outcome.get('privacy')})")
        _activity(project, f"Yayın ajanı videoyu yükledi: "
                           f"{candidate.get('title')} ({outcome.get('privacy')})", "ok")
        _mark_published(project, candidate.get("path"), video_id)
    elif outcome.get("error"):
        _log(state_path, f"Yayın ajanı yükleme hatası: {outcome['error']}")
        _activity(project, f"Yayın ajanı yükleme hatası: {outcome['error'][:160]}", "warn")
    else:
        _log(state_path, f"Yayın ajanı kararı: {verdict} · {reasons or 'gerekçe yok'}")
        _activity(project, f"Yayın ajanı {verdict}: {candidate.get('title')} "
                           f"· {reasons[:160]}", "info")
    return {
        "verdict": verdict,
        "privacy": outcome.get("privacy") or "",
        "video_id": video_id,
        "video_url": str((upload or {}).get("video_url") or ""),
        "reasons": list(outcome.get("reasons") or []),
        "llm_used": bool(outcome.get("llm_used")),
        "llm_verdict": outcome.get("llm_verdict") or "",
        "uploaded": bool(video_id),
    }


def _mark_published(project: Project, path, video_id: str) -> None:
    """Yüklenen videoyu proje hattında yayınlandı olarak işaretler."""
    pipeline_path = project.root / "production_pipeline.json"
    if not pipeline_path.is_file():
        return
    try:
        items = json.loads(pipeline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(items, list):
        return
    target = Path(str(path or "")).resolve()
    changed = False
    for item in items:
        output = str(item.get("output_path") or "")
        if output and Path(output).resolve() == target:
            item["video_id"] = video_id
            item["stage_index"] = 5
            item["updated_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            changed = True
    if changed:
        try:
            pipeline_path.write_text(json.dumps(items, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Panel ViewMade render çalıştırıcısı")
    parser.add_argument("slug", help="content/packages/<slug> paket kimliği")
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args(argv)

    if os.environ.get("CDDOCS_LIVE_CONFIRM") != "YES":
        print("CDDOCS_LIVE_CONFIRM=YES olmadan ücretli render başlatılamaz.", file=sys.stderr)
        return 2

    project = Project.open(ROOT)
    settings = Settings.from_env(project)
    slug = args.slug.strip()
    request_path = project.packages_dir / slug / "viewmade-request.json"
    if not request_path.is_file():
        print(f"İstek dosyası bulunamadı: {request_path}", file=sys.stderr)
        return 2

    request_payload = read_json(request_path)
    if not isinstance(request_payload, dict):
        print("İstek dosyası bir JSON nesnesi değil.", file=sys.stderr)
        return 2
    if request_payload.get("status") != "NOT_SUBMITTED":
        print(
            f"Paket durumu {request_payload.get('status')!r}; yeni ücretli render "
            "gönderilmedi.",
            file=sys.stderr,
        )
        return 3

    state_path = _state_path(project, slug)
    state = {
        "package_id": slug,
        "phase": "submitted",
        "pid": os.getpid(),
        "started_at": _now(),
        "updated_at": _now(),
        "request_status": request_payload.get("status"),
    }
    _write_state(state_path, state)
    _log(state_path, f"Render başlatıldı: {slug}")

    adapter = ViewMadeAdapter(project, settings)
    try:
        result = adapter.render(
            request_payload,
            poll_interval=max(1.0, args.poll_interval),
            timeout_s=max(60.0, args.timeout),
        )
    except Exception as exc:  # noqa: BLE001 - panel hatayı göstermeli
        message = f"{type(exc).__name__}: {exc}"
        state.update(
            {
                "phase": "failed",
                "error": message,
                "finished_at": _now(),
                "updated_at": _now(),
            }
        )
        _write_state(state_path, state)
        _log(state_path, message)
        traceback.print_exc()
        return 1

    payload = result.to_dict()
    if result.status == "DEFERRED":
        phase = "deferred"
        note = "Sağlayıcı meşgul; render gönderilmedi, kredi harcanmadı."
    elif result.status == "COMPLETE":
        phase = "complete"
        note = "Render tamamlandı."
    else:
        phase = "failed"
        note = "Render başarısız."
    state.update(
        {
            "phase": phase,
            "finished_at": _now(),
            "updated_at": _now(),
            "request_status": result.status,
            "provider_state": result.provider_state,
            "job_id": result.job_id,
            "render_path": result.render_path,
            "media": payload.get("media"),
            "error": result.error,
            "provider_busy": result.status == "DEFERRED",
        }
    )
    _write_state(state_path, state)
    _log(state_path, f"Render bitti: {result.status} · {note}")

    if result.status == "COMPLETE":
        try:
            latest = read_json(request_path)
            if not isinstance(latest, dict):
                latest = request_payload
            summary = _run_publish_agent(project, slug, latest, result, state_path)
        except Exception as exc:  # noqa: BLE001 - render yine de tamamdır
            summary = {
                "verdict": "ERROR",
                "reasons": [f"Yayın ajanı çalıştırılamadı: {type(exc).__name__}: {exc}"],
                "uploaded": False,
            }
            _log(state_path, summary["reasons"][0])
        if summary:
            state["publish_agent"] = summary
            state["updated_at"] = _now()
            _write_state(state_path, state)
    return 0 if result.status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
