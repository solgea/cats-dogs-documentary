"""Batch build, validation, packaging, and gated live rendering."""
from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from .artifacts import build_script, build_viewmade_request, build_visual_plan
from .config import Project, Settings
from .history import History
from .metadata import build_metadata
from .subtitles import build_cues, format_srt, parse_srt
from .util import (
    PipelineError,
    atomic_write_text,
    read_json,
    safe_relative,
    sha256_file,
    similarity,
    utc_now_iso,
    write_json,
)
from .validation import QAResult, summarize_results, validate_package, write_qa_report

GENERATED_ARTIFACTS = (
    "script.md",
    "subtitles.srt",
    "metadata.json",
    "visual-plan.md",
    "viewmade-request.json",
)
SOURCE_ARTIFACTS = ("package.json", "research.json")
REQUIRED_ARTIFACTS = SOURCE_ARTIFACTS + GENERATED_ARTIFACTS


def _binding_complete(project: Project) -> bool:
    path = project.viewmade_binding_file
    if not path.is_file():
        return False
    try:
        data = read_json(path)
    except PipelineError:
        return False
    tools = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(tools, dict):
        return False
    return all(
        isinstance(tools.get(key), dict)
        and isinstance(tools[key].get("name"), str)
        and tools[key]["name"]
        for key in ("render", "status", "download")
    )


def _hash_artifacts(folder: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in REQUIRED_ARTIFACTS:
        path = folder / name
        if path.is_file():
            hashes[name] = sha256_file(path)
    return hashes


def _generated_files(
    package: dict,
    research: dict,
    channel: dict,
    viewmade: dict,
    folder: Path,
    *,
    binding_complete: bool,
) -> tuple[dict, list, str]:
    scenes = package.get("scenes") or []
    target = float(package.get("target_duration_s", 0))
    if target <= 0:
        raise PipelineError(f"{package.get('id')}: target_duration_s must be positive")
    cues = build_cues(
        scenes,
        total_duration_s=target,
        max_line_chars=int(channel["format"]["subtitle_max_line_chars"]),
    )
    srt_text = format_srt(cues)
    metadata = build_metadata(package, research, channel)
    script = build_script(package, research, channel)
    visual_plan = build_visual_plan(package, channel)
    request = build_viewmade_request(
        package,
        cues,
        channel,
        viewmade,
        binding_complete=binding_complete,
    )

    atomic_write_text(folder / "script.md", script)
    atomic_write_text(folder / "subtitles.srt", srt_text)
    write_json(folder / "metadata.json", metadata)
    atomic_write_text(folder / "visual-plan.md", visual_plan)
    write_json(folder / "viewmade-request.json", request)
    return metadata, cues, srt_text


def build_package(
    project: Project,
    slug: str,
    *,
    channel: dict | None = None,
    sources_config: dict | None = None,
    viewmade: dict | None = None,
    history: History | None = None,
    write: bool = True,
) -> QAResult:
    channel = channel or project.channel()
    sources_config = sources_config or project.sources()
    viewmade = viewmade or project.viewmade()
    package, research, folder = project.load_package(slug)
    result = QAResult(
        package_id=slug,
        batch_id=str(package.get("batch_id") or ""),
    )
    try:
        metadata, cues, srt_text = _generated_files(
            package,
            research,
            channel,
            viewmade,
            folder,
            binding_complete=_binding_complete(project),
        )
    except PipelineError as exc:
        result.add("build.error", "Artifact generation", "FAIL", str(exc))
        if write:
            write_qa_report(folder / "qa-report.json", result)
        return result

    hashes = _hash_artifacts(folder)
    result = validate_package(
        package=package,
        research=research,
        folder=folder,
        channel=channel,
        sources_config=sources_config,
        history=history,
        metadata=metadata,
        cues=cues,
        srt_text=srt_text,
        artifact_files=hashes,
    )
    result.artifacts = hashes
    if write:
        write_qa_report(folder / "qa-report.json", result, artifacts=hashes)
    return result


def _read_generated(
    folder: Path,
) -> tuple[dict | None, list | None, str | None, dict | None]:
    metadata = None
    cues = None
    srt_text = None
    request = None
    metadata_path = folder / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = read_json(metadata_path)
        except PipelineError:
            metadata = None
    srt_path = folder / "subtitles.srt"
    if srt_path.is_file():
        try:
            srt_text = srt_path.read_text(encoding="utf-8")
            cues = parse_srt(srt_text)
        except (PipelineError, OSError):
            cues = None
    request_path = folder / "viewmade-request.json"
    if request_path.is_file():
        try:
            request = read_json(request_path)
        except PipelineError:
            request = None
    return metadata, cues, srt_text, request


def validate_package_folder(
    project: Project,
    slug: str,
    *,
    channel: dict | None = None,
    sources_config: dict | None = None,
    history: History | None = None,
    write: bool = True,
) -> QAResult:
    channel = channel or project.channel()
    sources_config = sources_config or project.sources()
    package, research, folder = project.load_package(slug)
    result = QAResult(
        package_id=slug,
        batch_id=str(package.get("batch_id") or ""),
    )
    missing = [name for name in REQUIRED_ARTIFACTS if not (folder / name).is_file()]
    result.add(
        "artifacts.required",
        "All source and generated artifacts exist",
        "FAIL" if missing else "PASS",
        f"missing={missing}" if missing else f"{len(REQUIRED_ARTIFACTS)} files present",
    )
    metadata, cues, srt_text, request = _read_generated(folder)
    if metadata is None:
        result.add("artifacts.metadata_parse", "metadata.json parses", "FAIL", "missing or invalid JSON")
    if cues is None:
        result.add("artifacts.subtitles_parse", "subtitles.srt parses", "FAIL", "missing or malformed SRT")
    if request is None:
        result.add("artifacts.request_parse", "viewmade-request.json parses", "FAIL", "missing or invalid JSON")
    else:
        request_status = request.get("status")
        job_id = request.get("job_id")
        problems = []
        if request.get("package_id") != slug:
            problems.append("package_id mismatch")
        if request_status not in {
            "NOT_SUBMITTED",
            "BLOCKED_UNBOUND",
            "READY_FOR_SUBMISSION",
            "SUBMITTED",
            "RENDERING",
            "COMPLETE",
            "FAILED",
        }:
            problems.append(f"unknown status {request_status!r}")
        if request_status in {"SUBMITTED", "RENDERING", "COMPLETE"} and not job_id:
            problems.append("submitted status without a job_id")
        rendered = request.get("render_path")
        if rendered and not (project.root / rendered).is_file():
            problems.append(f"render_path does not exist: {rendered}")
        text = json.dumps(request)
        for secret_key in ("access_token", "refresh_token", "client_secret", "authorization"):
            if secret_key in text:
                problems.append(f"request contains secret-like field {secret_key!r}")
        result.add(
            "artifacts.request_state",
            "ViewMade request is honest about submission state",
            "FAIL" if problems else "PASS",
            "; ".join(problems) if problems else f"status={request_status!r}",
        )

    hashes = _hash_artifacts(folder)
    result2 = validate_package(
        package=package,
        research=research,
        folder=folder,
        channel=channel,
        sources_config=sources_config,
        history=history,
        metadata=metadata,
        cues=cues,
        srt_text=srt_text,
        artifact_files=hashes,
    )
    # Preserve the artifact-specific checks gathered above.
    for check in result.checks:
        if not any(existing.id == check.id for existing in result2.checks):
            result2.checks.append(check)
    result2.artifacts = hashes
    if write:
        write_qa_report(folder / "qa-report.json", result2, artifacts=hashes)
    return result2


def _add_pairwise_checks(packages: dict[str, dict], results: dict[str, QAResult]) -> list[dict]:
    pairs: list[dict] = []
    for left_id, right_id in combinations(sorted(packages), 2):
        score = similarity(
            f"{packages[left_id].get('title','')} {packages[left_id].get('central_question','')} {packages[left_id].get('central_fact','')}",
            f"{packages[right_id].get('title','')} {packages[right_id].get('central_question','')} {packages[right_id].get('central_fact','')}",
        )
        if score >= 0.66:
            severity = "FAIL"
            reason = "batch topics overlap too much"
        elif score >= 0.45:
            severity = "WARN"
            reason = "batch topics have noticeable framing overlap"
        else:
            continue
        pairs.append(
            {
                "left": left_id,
                "right": right_id,
                "similarity": round(score, 3),
                "severity": severity,
                "reason": reason,
            }
        )
        for own, other in ((left_id, right_id), (right_id, left_id)):
            results[own].add(
                f"batch.duplicate.{other}",
                f"Batch duplicate check against {other}",
                severity,
                f"{reason}: similarity={score:.3f}",
            )
    return pairs


@dataclass
class BatchOutcome:
    batch_id: str
    status: str
    results: list[QAResult]
    pairs: list[dict]
    report_path: Path
    history_path: Path | None

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "summary": summarize_results(self.results),
            "packages": [
                {
                    "id": result.package_id,
                    "status": result.status,
                    "counts": result.counts,
                    "render_status": result.render_status,
                    "publish_ready": result.publish_ready,
                }
                for result in self.results
            ],
            "duplicate_pairs": self.pairs,
            "report": str(self.report_path),
            "history": str(self.history_path) if self.history_path else None,
        }


def _write_batch_report(
    project: Project,
    batch_id: str,
    results: list[QAResult],
    pairs: list[dict],
    *,
    mode: str,
) -> tuple[Path, dict]:
    summary = summarize_results(results)
    payload = {
        "schema_version": 1,
        "batch_id": batch_id,
        "generated_at": utc_now_iso(),
        "mode": mode,
        "status": summary["status"],
        "summary": summary,
        "packages": [
            {
                "id": result.package_id,
                "status": result.status,
                "counts": result.counts,
                "render_status": result.render_status,
                "publish_ready": result.publish_ready,
                "qa_report": f"content/packages/{result.package_id}/qa-report.json",
            }
            for result in results
        ],
        "duplicate_pairs": pairs,
        "render_gate": {
            "status": "NOT_REQUESTED",
            "note": "Live ViewMade rendering is a separate command and requires OAuth, discovered tool bindings, --allow-live, and CDDOCS_LIVE_CONFIRM=YES.",
        },
        "publishing_gate": {
            "manual_youtube_upload": True,
            "human_signoff_required": True,
            "note": "No video has been uploaded. Review every source and render before publishing.",
        },
    }
    path = project.batch_path(batch_id) / "qa-report.json"
    write_json(path, payload)
    return path, payload


def build_batch(project: Project, batch_id: str) -> BatchOutcome:
    channel = project.channel()
    sources_config = project.sources()
    viewmade = project.viewmade()
    batch, folder = project.load_batch(batch_id)
    history = History(project.history_db, project.history_export)
    try:
        results: list[QAResult] = []
        packages: dict[str, dict] = {}
        for slug in batch["packages"]:
            package, _research, _package_folder = project.load_package(slug)
            packages[slug] = package
            result = build_package(
                project,
                slug,
                channel=channel,
                sources_config=sources_config,
                viewmade=viewmade,
                history=history,
                write=True,
            )
            results.append(result)
        pairs = _add_pairwise_checks(packages, {result.package_id: result for result in results})
        # Pairwise checks were added after the first report write; refresh them.
        for result in results:
            write_qa_report(
                project.package_path(result.package_id) / "qa-report.json",
                result,
                artifacts=result.artifacts,
            )
        summary = summarize_results(results)
        history_status = summary["status"]
        if summary["status"] != "FAIL":
            for result in results:
                package = packages[result.package_id]
                source_ids = [
                    str(source.get("id"))
                    for source in read_json(
                        project.package_path(result.package_id) / "research.json"
                    ).get("sources", [])
                ]
                history.register_topic(
                    package_id=result.package_id,
                    slug=result.package_id,
                    batch_id=batch_id,
                    title=str(package.get("title", "")),
                    central_question=str(package.get("central_question", "")),
                    central_fact=str(package.get("central_fact", "")),
                    source_ids=source_ids,
                    status=result.status,
                )
        history.register_batch(
            batch_id=batch_id,
            package_count=len(results),
            status=history_status,
        )
        history_path = history.export()
        report_path, _payload = _write_batch_report(
            project, batch_id, results, pairs, mode="build"
        )
        return BatchOutcome(
            batch_id=batch_id,
            status=summary["status"],
            results=results,
            pairs=pairs,
            report_path=report_path,
            history_path=history_path,
        )
    finally:
        history.close()


def validate_batch(project: Project, batch_id: str) -> BatchOutcome:
    channel = project.channel()
    sources_config = project.sources()
    batch, _folder = project.load_batch(batch_id)
    history = History(project.history_db, project.history_export)
    try:
        results: list[QAResult] = []
        packages: dict[str, dict] = {}
        for slug in batch["packages"]:
            package, _research, _package_folder = project.load_package(slug)
            packages[slug] = package
            results.append(
                validate_package_folder(
                    project,
                    slug,
                    channel=channel,
                    sources_config=sources_config,
                    history=history,
                    write=True,
                )
            )
        pairs = _add_pairwise_checks(packages, {result.package_id: result for result in results})
        for result in results:
            write_qa_report(
                project.package_path(result.package_id) / "qa-report.json",
                result,
                artifacts=result.artifacts,
            )
        summary = summarize_results(results)
        report_path, _payload = _write_batch_report(
            project, batch_id, results, pairs, mode="validate"
        )
        return BatchOutcome(
            batch_id=batch_id,
            status=summary["status"],
            results=results,
            pairs=pairs,
            report_path=report_path,
            history_path=None,
        )
    finally:
        history.close()


def _render_readme(project: Project, outcome: BatchOutcome, batch: dict) -> str:
    lines = [
        f"# {outcome.batch_id}",
        "",
        f"QA status: **{outcome.status}**",
        "",
        "This archive contains editorial source files and YouTube-ready metadata. "
        "It does not contain an uploaded video.",
        "",
        "## Upload checklist",
        "",
        "1. Read `research.json` and verify every DOI/PMID link yourself.",
        "2. Watch the rendered Short end to end. Reject malformed animals or uncanny motion.",
        "3. Confirm the description still contains the AI-visual disclosure and educational disclaimer.",
        "4. Upload manually as a YouTube Short (9:16). Do not let YouTube convert a horizontal file.",
        "5. Keep the visibility private until a human editor signs off.",
        "",
        "## Contents",
        "",
        f"- `batch.json` - source manifest with {len(batch['packages'])} packages",
        "- `batch-qa-report.json` - aggregate QA gates",
        "- `packages/<id>/` - package sources, research, script, subtitles, metadata, visual plan, ViewMade request, QA report",
        "- `history.json` - committed topic history used for cross-batch deduplication",
        "",
        "## Render status",
        "",
    ]
    rendered = [
        result.package_id for result in outcome.results if result.render_status == "PASS"
    ]
    if rendered:
        lines.append(f"Rendered and validated: {', '.join(rendered)}")
    else:
        lines.append(
            "No validated MP4 is present. Live ViewMade rendering is blocked until OAuth "
            "and official MCP tool binding are complete."
        )
    lines.extend(
        [
            "",
            "Illustrative, AI-assisted visuals; not documentary footage.",
            "",
        ]
    )
    return "\n".join(lines)


def package_batch(project: Project, batch_id: str, *, output_dir: Path | None = None) -> dict:
    outcome = validate_batch(project, batch_id)
    if outcome.status == "FAIL":
        raise PipelineError(
            f"batch {batch_id} fails QA; refusing to create a distribution archive"
        )
    batch, folder = project.load_batch(batch_id)
    target_dir = output_dir or project.dist_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{batch_id}.zip"
    entries: list[tuple[str, bytes]] = []

    def add(archive_name: str, path: Path) -> None:
        if path.is_file():
            entries.append((archive_name, path.read_bytes()))

    add("batch.json", folder / "batch.json")
    add("batch-qa-report.json", folder / "qa-report.json")
    for slug in batch["packages"]:
        package_folder = project.package_path(slug)
        for name in REQUIRED_ARTIFACTS + ("qa-report.json", "render.mp4"):
            add(f"packages/{slug}/{name}", package_folder / name)
    add("history.json", project.history_export)
    entries.append(
        (
            "PACKAGE_README.md",
            _render_readme(project, outcome, batch).encode("utf-8"),
        )
    )
    entries.sort(key=lambda item: item[0])
    sums = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n" for name, payload in entries
    ).encode("utf-8")
    entries.append(("SHA256SUMS.txt", sums))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return {
        "batch_id": batch_id,
        "status": outcome.status,
        "archive": str(target),
        "bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "entries": [name for name, _ in entries],
    }


def render_batch(
    project: Project,
    batch_id: str,
    *,
    allow_live: bool,
    settings: Settings,
    poll_interval: float = 5.0,
    timeout_s: float = 900.0,
) -> dict:
    """Submit only when every gate is open; never fabricate a render.

    This function is intentionally late-bound: importing the ViewMade adapter is
    deferred so offline build/validate commands never need OAuth configuration.
    """
    settings.require_live_authorisation(allow_live, provider="ViewMade")
    outcome = validate_batch(project, batch_id)
    if outcome.status == "FAIL":
        raise PipelineError(
            f"batch {batch_id} fails QA; live rendering is blocked. Fix the FAIL checks first."
        )
    from .viewmade.adapter import ViewMadeAdapter, ViewMadeBlocked

    adapter = ViewMadeAdapter(project, settings)
    status = adapter.status()
    if not status.get("authenticated"):
        raise ViewMadeBlocked(
            "ViewMade is not authenticated. Run `cddocs viewmade login` or connect at "
            f"{project.viewmade()['connect_url']}."
        )
    if not status.get("bound"):
        raise ViewMadeBlocked(
            "ViewMade MCP tools are not fully bound. Run `cddocs viewmade discover` and "
            "`cddocs viewmade bind` first."
        )
    batch, _folder = project.load_batch(batch_id)
    jobs: list[dict] = []
    for slug in batch["packages"]:
        request_path = project.package_path(slug) / "viewmade-request.json"
        request = read_json(request_path)
        try:
            render = adapter.render(
                request,
                poll_interval=poll_interval,
                timeout_s=timeout_s,
            )
        except ViewMadeBlocked as exc:
            jobs.append({"package_id": slug, "status": "BLOCKED", "reason": str(exc)})
            break
        jobs.append(render.to_dict())
        if render.status != "COMPLETE":
            break
    report = {
        "batch_id": batch_id,
        "status": "COMPLETE" if jobs and all(job["status"] == "COMPLETE" for job in jobs) else "BLOCKED_OR_FAILED",
        "jobs": jobs,
    }
    write_json(project.batch_path(batch_id) / "render-report.json", report)
    return report
