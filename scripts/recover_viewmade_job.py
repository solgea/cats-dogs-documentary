"""Attach to an existing ViewMade job and finish the local render pipeline.

Use this when `viewmade_create_short` returned an error but the production was
still created. The provider job id must be verified with `viewmade_list_videos`
or the ViewMade dashboard first. No tool name is hardcoded: status and download
calls go through the explicit binding.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from cddocs.config import Project, Settings
from cddocs.media_probe import validate_render
from cddocs.util import PipelineError, read_json, safe_relative, sha256_file, utc_now_iso
from cddocs.viewmade.adapter import ViewMadeAdapter, ViewMadeBlocked
from cddocs.viewmade.mcp import MCPError


def _data(result: dict) -> dict:
    value = result.get("structuredContent")
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        return value["data"]
    return {}


def _print(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_id")
    parser.add_argument("job_id")
    parser.add_argument("--poll-interval", type=float, default=60.0)
    parser.add_argument("--timeout", type=float, default=14400.0)
    args = parser.parse_args()

    project = Project.open()
    settings = Settings.from_env(project)
    settings.require_live_authorisation(True, provider="ViewMade")
    adapter = ViewMadeAdapter(project, settings)
    if not adapter.binding_complete():
        raise ViewMadeBlocked("ViewMade render/status/download tools are not fully bound")

    request_path = project.package_path(args.package_id) / "viewmade-request.json"
    request_payload = read_json(request_path)
    binding = adapter.binding() or {}
    render_tool = (binding.get("tools") or {}).get("render", {}).get("name")

    adapter._update_request(
        args.package_id,
        request_payload,
        status="SUBMITTED",
        job_id=args.job_id,
        provider_state="recovered",
        error=None,
        submission={
            "submitted_at": utc_now_iso(),
            "render_tool": render_tool,
            "recovered_from_provider_error": True,
        },
    )
    record = {
        "package_id": args.package_id,
        "job_id": args.job_id,
        "status": "SUBMITTED",
        "submitted_at": utc_now_iso(),
        "provider_state": "recovered",
        "render_path": None,
        "recovered": True,
    }
    adapter._write_job_state(args.package_id, record)

    deadline = time.monotonic() + max(1.0, args.timeout)
    provider_state = None
    provider_data: dict = {}
    while time.monotonic() < deadline:
        try:
            result = adapter._call_bound(
                "status", adapter._context(request_payload, job_id=args.job_id)
            )
        except (MCPError, ViewMadeBlocked) as exc:
            record.update({"status": "FAILED", "error": str(exc)})
            adapter._write_job_state(args.package_id, record)
            _print(f"Status polling failed: {exc}")
            return 1
        provider_data = _data(result)
        provider_state = str(provider_data.get("status") or "").strip().lower()
        progress = provider_data.get("progress") or {}
        _print(
            f"{utc_now_iso()} status={provider_state or 'unknown'} "
            f"stage={progress.get('stage')} pct={progress.get('pct')} "
            f"eta={progress.get('eta')}"
        )
        record.update(
            {
                "status": "RENDERING" if provider_state else "SUBMITTED",
                "provider_state": provider_state,
                "last_polled_at": utc_now_iso(),
            }
        )
        adapter._write_job_state(args.package_id, record)
        adapter._update_request(
            args.package_id,
            request_payload,
            status="RENDERING",
            job_id=args.job_id,
            provider_state=provider_state,
        )
        if provider_state in {"ready", "complete", "completed", "succeeded", "success", "done"}:
            break
        if provider_state in {"failed", "error", "cancelled", "canceled", "rejected"}:
            message = f"ViewMade job {args.job_id} ended in state {provider_state!r}"
            adapter._update_request(
                args.package_id,
                request_payload,
                status="FAILED",
                job_id=args.job_id,
                provider_state=provider_state,
                error=message,
            )
            record.update({"status": "FAILED", "error": message})
            adapter._write_job_state(args.package_id, record)
            _print(message)
            return 1
        time.sleep(max(5.0, args.poll_interval))
    else:
        message = f"ViewMade job {args.job_id} did not finish within {int(args.timeout)}s"
        adapter._update_request(
            args.package_id,
            request_payload,
            status="FAILED",
            job_id=args.job_id,
            provider_state=provider_state,
            error=message,
        )
        record.update({"status": "FAILED", "error": message})
        adapter._write_job_state(args.package_id, record)
        _print(message)
        return 1

    try:
        download = adapter._call_bound(
            "download",
            adapter._context(
                request_payload, job_id=args.job_id, provider_state=provider_state
            ),
        )
    except (MCPError, ViewMadeBlocked) as exc:
        message = f"ViewMade job {args.job_id} finished but download failed: {exc}"
        adapter._update_request(
            args.package_id,
            request_payload,
            status="FAILED",
            job_id=args.job_id,
            provider_state=provider_state,
            error=message,
        )
        record.update({"status": "FAILED", "error": message})
        adapter._write_job_state(args.package_id, record)
        _print(message)
        return 1

    download_data = _data(download)
    url = download_data.get("video_url") or download_data.get("url")
    if not url:
        message = "ViewMade download tool returned no video_url"
        adapter._update_request(
            args.package_id,
            request_payload,
            status="FAILED",
            job_id=args.job_id,
            provider_state=provider_state,
            error=message,
        )
        record.update({"status": "FAILED", "error": message})
        adapter._write_job_state(args.package_id, record)
        _print(message)
        return 1

    target_dir = project.renders_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{args.package_id}.mp4"
    try:
        adapter._download_url(str(url), target)
        normalization = adapter._normalize_render(target)
    except (OSError, ViewMadeBlocked) as exc:
        message = f"could not download or normalize the ViewMade render: {exc}"
        adapter._update_request(
            args.package_id,
            request_payload,
            status="FAILED",
            job_id=args.job_id,
            provider_state=provider_state,
            error=message,
        )
        record.update({"status": "FAILED", "error": message})
        adapter._write_job_state(args.package_id, record)
        _print(message)
        return 1

    info, issues = validate_render(
        target,
        min_duration_s=float(adapter.config["render"]["min_duration_s"]),
        max_duration_s=float(adapter.config["render"]["max_duration_s"]),
        width=int(adapter.config["render"]["width"]),
        height=int(adapter.config["render"]["height"]),
    )
    if issues:
        invalid = target.with_suffix(".invalid.mp4")
        try:
            target.replace(invalid)
        except OSError:
            invalid = target
        message = "downloaded MP4 failed local validation: " + "; ".join(issues)
        adapter._update_request(
            args.package_id,
            request_payload,
            status="FAILED",
            job_id=args.job_id,
            provider_state=provider_state,
            error=message,
        )
        record.update({"status": "FAILED", "error": message})
        adapter._write_job_state(args.package_id, record)
        _print(message)
        return 1

    provider_package = {
        key: download_data.get(key)
        for key in (
            "id",
            "status",
            "title",
            "description",
            "tags",
            "duration",
            "aspect",
            "resolution",
            "scene_count",
            "sources",
            "attributions",
            "source_window",
            "source_note",
            "clips",
            "subject_note",
            "view_url",
            "credits_charged",
            "credits_refunded",
            "net_credits",
            "created_at",
        )
    }
    render_rel = safe_relative(target, project.root)
    digest = sha256_file(target)
    adapter._update_request(
        args.package_id,
        request_payload,
        status="COMPLETE",
        job_id=args.job_id,
        provider_state=provider_state,
        render_path=render_rel,
        render_sha256=digest,
        normalization=normalization,
        provider_package=provider_package,
        error=None,
    )
    record.update(
        {
            "status": "COMPLETE",
            "provider_state": provider_state,
            "render_path": render_rel,
            "render_sha256": digest,
            "normalization": normalization,
            "completed_at": utc_now_iso(),
            "media": info.to_dict() if info else None,
        }
    )
    adapter._write_job_state(args.package_id, record)
    _print(
        json.dumps(
            {
                "package_id": args.package_id,
                "status": "COMPLETE",
                "job_id": args.job_id,
                "render_path": render_rel,
                "sha256": digest,
                "media": info.to_dict() if info else None,
                "normalization": normalization,
                "provider": provider_package,
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
