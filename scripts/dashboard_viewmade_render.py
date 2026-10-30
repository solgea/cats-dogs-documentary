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
    state.update(
        {
            "phase": "complete" if result.status == "COMPLETE" else "failed",
            "finished_at": _now(),
            "updated_at": _now(),
            "request_status": result.status,
            "provider_state": result.provider_state,
            "job_id": result.job_id,
            "render_path": result.render_path,
            "media": payload.get("media"),
            "error": result.error,
        }
    )
    _write_state(state_path, state)
    _log(state_path, f"Render bitti: {result.status} · {result.render_path or '—'}")
    return 0 if result.status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
