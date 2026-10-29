"""ViewMade adapter built on official OAuth + MCP discovery.

No ViewMade tool name is hardcoded. The adapter refuses to submit a render
until the official MCP server has been authenticated, tools have been listed,
and the user has explicitly bound render/status/download tools with argument
templates that satisfy each tool's advertised input schema.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Project, Settings
from ..media_probe import MediaInfo, check_aspect, validate_file, validate_render
from ..util import (
    PipelineError,
    read_json,
    safe_relative,
    sha256_file,
    utc_now_iso,
    write_json,
)
from . import oauth
from .mcp import MCPAuthError, MCPClient, MCPError, find_tool, tool_names

ALLOWED_PLACEHOLDERS = {
    "package_id",
    "operation_key",
    "prompt",
    "provider_topic",
    "script",
    "title",
    "duration_s",
    "aspect_ratio",
    "resolution",
    "narration",
    "scenes",
    "captions",
    "disclosure",
    "request",
    "job_id",
    "provider_state",
}
PLACEHOLDER_RE = re.compile(r"^\$([a-z_]+)$")
BINDING_KEYS = ("render", "status", "download")


class ViewMadeBlocked(PipelineError):
    """The render gate is closed. This is never a successful render."""


@dataclass
class RenderResult:
    package_id: str
    status: str
    job_id: str | None = None
    render_path: str | None = None
    media: MediaInfo | None = None
    error: str | None = None
    provider_state: str | None = None

    def to_dict(self) -> dict:
        return {
            "package_id": self.package_id,
            "status": self.status,
            "job_id": self.job_id,
            "render_path": self.render_path,
            "media": self.media.to_dict() if self.media else None,
            "error": self.error,
            "provider_state": self.provider_state,
        }


def _load_json_optional(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except PipelineError:
        return None
    return data if isinstance(data, dict) else None


def _default_templates() -> dict[str, dict]:
    return {
        "render": {
            "prompt": "$prompt",
            "duration": "$duration_s",
            "aspect_ratio": "$aspect_ratio",
        },
        "status": {"job_id": "$job_id"},
        "download": {"job_id": "$job_id"},
    }


def _resolve_placeholders(value: Any, context: dict) -> Any:
    if isinstance(value, str):
        match = PLACEHOLDER_RE.fullmatch(value.strip())
        if match:
            key = match.group(1)
            if key not in context:
                raise ViewMadeBlocked(f"binding template placeholder ${key} has no value")
            return context[key]
        return value
    if isinstance(value, list):
        return [_resolve_placeholders(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_placeholders(item, context) for key, item in value.items()}
    return value


def _validate_template(template: dict, tool: dict, label: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(template, dict):
        return [f"{label} template is not an object"]
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    if not isinstance(schema, dict):
        return [f"{label} tool has no usable inputSchema"]
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []
    for key in template:
        if not isinstance(key, str):
            problems.append(f"{label} template has a non-string key")
            continue
        if properties and key not in properties:
            problems.append(f"{label} template key {key!r} is not in the tool schema")
    for key in required:
        if key not in template:
            problems.append(f"{label} template is missing required tool argument {key!r}")
    for value in _iter_template_strings(template):
        match = PLACEHOLDER_RE.fullmatch(value.strip())
        if match and match.group(1) not in ALLOWED_PLACEHOLDERS:
            problems.append(f"{label} template uses unknown placeholder ${match.group(1)}")
    return problems


def _iter_template_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_template_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_template_strings(item)


def _extract_path(data: Any, path: list[str] | tuple[str, ...]) -> Any:
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, str) and key.isdigit():
            index = int(key)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _first_present(data: Any, candidates: tuple[str, ...]) -> Any:
    if not isinstance(data, dict):
        return None
    for key in candidates:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _script_lines(narration: str, max_lines: int = 12) -> str:
    """Turn narration into the 7-12 semantic lines the provider expects."""
    text = " ".join(str(narration).split())
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not sentences:
        return ""
    groups = [[sentence] for sentence in sentences]
    while len(groups) > max_lines:
        index = min(
            range(len(groups) - 1),
            key=lambda i: len(" ".join(groups[i] + groups[i + 1])),
        )
        groups[index : index + 2] = [groups[index] + groups[index + 1]]
    return "\n".join(" ".join(group) for group in groups)


def _canonical_sha256(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _operation_key(request_payload: dict) -> str:
    """Stable idempotency key that changes when the render specification changes."""
    digest = _canonical_sha256(request_payload.get("request") or {})[:12]
    return f"{request_payload.get('package_id')}-{digest}"


def _generation_prompt(request_payload: dict) -> str:
    request = request_payload.get("request") or {}
    lines = [
        f"Create a {request.get('duration_s')} second vertical YouTube Short titled {request.get('title')!r}.",
        f"Format: {request.get('aspect_ratio')} {request.get('resolution')}, real-footage montage from third-party pet clips.",
        "Narration:",
        str(request.get("narration", "")),
        "",
        "Scenes:",
    ]
    for scene in request.get("scenes", []):
        visual = scene.get("visual") or {}
        lines.append(
            f"- {scene.get('start_s')}s-{float(scene.get('start_s', 0)) + float(scene.get('duration_s', 0))}s: "
            f"{scene.get('narration', '')} Visual: {visual.get('description', '')} "
            f"Shot: {visual.get('shot_type', '')}. Motion: {visual.get('motion', '')}."
        )
    lines.extend(
        [
            "",
            "Requirements:",
            "- Preserve the supplied script wording verbatim; use natural English narration.",
            "- Burned-in captions must match the spoken narration.",
            "- Species-correct, anatomically coherent animals; no extra limbs or malformed faces.",
            "- No distressed animals, no staged aggression, no on-screen text artifacts, no logos, no watermarks.",
            "- Return every footage source and attribution line.",
            f"- Disclosure: {request.get('disclosure', '')}",
        ]
    )
    return "\n".join(lines)


class ViewMadeAdapter:
    def __init__(self, project: Project, settings: Settings | None = None):
        self.project = project
        self.settings = settings or Settings.from_env(project)
        self.config = project.viewmade()

    # --- status and discovery -----------------------------------------

    def binding(self) -> dict | None:
        return _load_json_optional(self.project.viewmade_binding_file)

    def binding_complete(self) -> bool:
        binding = self.binding()
        if not binding:
            return False
        tools = binding.get("tools")
        if not isinstance(tools, dict):
            return False
        return all(
            isinstance(tools.get(key), dict)
            and isinstance(tools[key].get("name"), str)
            and bool(tools[key]["name"])
            for key in BINDING_KEYS
        )

    def status(self) -> dict:
        auth = oauth.status(self.project, self.settings)
        discovery = _load_json_optional(self.project.viewmade_tools_file)
        binding = self.binding()
        return {
            "provider": "viewmade",
            "endpoint": self.config["mcp_url"],
            "authenticated": auth.get("authenticated", False),
            "expired": auth.get("expired", False),
            "refreshable": auth.get("refreshable", False),
            "token_source": auth.get("source"),
            "scope": auth.get("scope"),
            "tools_discovered": bool(discovery and discovery.get("tools")),
            "tool_count": len(discovery.get("tools", [])) if discovery else 0,
            "bound": self.binding_complete(),
            "binding": binding,
            "connect_url": self.config["connect_url"],
        }

    def discover(self) -> dict:
        token = oauth.get_access_token(self.project, self.settings)
        client = MCPClient(
            self.config["mcp_url"],
            token,
            protocol_version=self.config.get("protocol_version", "2025-06-18"),
            connect_url=self.config["connect_url"],
        )
        discovery = client.discover()
        discovery["provider"] = "viewmade"
        discovery["tool_names"] = tool_names(discovery)
        if not discovery["tools"]:
            raise MCPError("ViewMade MCP returned no tools; discovery is incomplete")
        write_json(self.project.viewmade_tools_file, discovery)
        return discovery

    def list_discovered_tools(self) -> dict:
        discovery = _load_json_optional(self.project.viewmade_tools_file)
        if not discovery:
            raise ViewMadeBlocked(
                "No ViewMade tool discovery exists yet. Run `cddocs viewmade discover` after login."
            )
        return discovery

    def bind(
        self,
        *,
        render_tool: str,
        status_tool: str,
        download_tool: str,
        templates: dict[str, dict] | None = None,
        job_id_path: list[str] | None = None,
        provider_state_path: list[str] | None = None,
        success_states: list[str] | None = None,
        failure_states: list[str] | None = None,
        download_url_path: list[str] | None = None,
        download_file_path: list[str] | None = None,
    ) -> dict:
        discovery = self.list_discovered_tools()
        requested = {
            "render": render_tool,
            "status": status_tool,
            "download": download_tool,
        }
        templates = templates or _default_templates()
        problems: list[str] = []
        tools_record: dict[str, dict] = {}
        for key in BINDING_KEYS:
            name = requested[key]
            tool = find_tool(discovery, name)
            if tool is None:
                problems.append(f"{key} tool {name!r} is not in the discovered tool list")
                continue
            template = templates.get(key) or {}
            problems.extend(_validate_template(template, tool, key))
            tools_record[key] = {"name": name, "template": template}
        if problems:
            raise PipelineError(
                "ViewMade binding refused:\n- " + "\n- ".join(dict.fromkeys(problems))
            )
        binding = {
            "schema_version": 1,
            "provider": "viewmade",
            "bound_at": utc_now_iso(),
            "tools": tools_record,
            "job_id_path": job_id_path or ["job_id"],
            "provider_state_path": provider_state_path or ["status"],
            "success_states": success_states
            or ["complete", "completed", "succeeded", "success", "ready", "done"],
            "failure_states": failure_states
            or ["failed", "error", "cancelled", "canceled", "rejected"],
            "download_url_path": download_url_path or ["url"],
            "download_file_path": download_file_path or ["path"],
        }
        write_json(self.project.viewmade_binding_file, binding)
        return binding

    # --- submission ----------------------------------------------------

    def _request_folder(self, package_id: str) -> Path:
        return self.project.package_path(package_id)

    def _update_request(self, package_id: str, request_payload: dict, **changes: Any) -> None:
        path = self._request_folder(package_id) / "viewmade-request.json"
        payload = dict(request_payload)
        payload.update(changes)
        payload["updated_at"] = utc_now_iso()
        write_json(path, payload)

    def _job_state_path(self, package_id: str) -> Path:
        folder = self.project.state_dir / "viewmade-jobs"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{package_id}.json"

    def _write_job_state(self, package_id: str, record: dict) -> None:
        write_json(self._job_state_path(package_id), record)

    def _context(self, request_payload: dict, *, job_id: str | None = None, provider_state: Any = None) -> dict:
        request = request_payload.get("request") or {}
        return {
            "package_id": request_payload.get("package_id"),
            "operation_key": _operation_key(request_payload),
            "prompt": _generation_prompt(request_payload),
            "provider_topic": request.get("provider_topic") or request.get("title"),
            "script": _script_lines(str(request.get("narration", ""))),
            "title": request.get("title"),
            "duration_s": request.get("duration_s"),
            "aspect_ratio": request.get("aspect_ratio"),
            "resolution": request.get("resolution"),
            "narration": request.get("narration"),
            "scenes": request.get("scenes"),
            "captions": request.get("captions"),
            "disclosure": request.get("disclosure"),
            "request": request,
            "job_id": job_id,
            "provider_state": provider_state,
        }

    def _bound_arguments(self, key: str, context: dict) -> tuple[dict, dict]:
        binding = self.binding()
        if not binding:
            raise ViewMadeBlocked("ViewMade tools are not bound")
        entry = (binding.get("tools") or {}).get(key)
        if not entry:
            raise ViewMadeBlocked(f"ViewMade {key} tool is not bound")
        arguments = _resolve_placeholders(entry.get("template") or {}, context)
        if not isinstance(arguments, dict):
            raise ViewMadeBlocked(f"ViewMade {key} template did not produce an object")
        return entry, arguments

    def _call_bound(self, key: str, context: dict) -> Any:
        entry, arguments = self._bound_arguments(key, context)
        token = oauth.get_access_token(self.project, self.settings)
        client = MCPClient(
            self.config["mcp_url"],
            token,
            protocol_version=self.config.get("protocol_version", "2025-06-18"),
            connect_url=self.config["connect_url"],
        )
        client.initialize()
        return client.call_tool(str(entry["name"]), arguments)

    def render(
        self,
        request_payload: dict,
        *,
        poll_interval: float = 5.0,
        timeout_s: float = 900.0,
    ) -> RenderResult:
        package_id = str(request_payload.get("package_id") or "")
        if not package_id:
            raise ViewMadeBlocked("render request has no package_id")

        existing_status = request_payload.get("status")
        existing_render = request_payload.get("render_path")
        existing_job = request_payload.get("job_id")
        existing_provider_state = str(request_payload.get("provider_state") or "").lower()

        # A verified local render is the only safe reason to skip a new provider
        # call. A COMPLETE request with a missing or invalid file must be repaired
        # explicitly; silently submitting again would charge for a second job.
        if existing_status == "COMPLETE" and existing_render:
            existing_path = self.project.root / existing_render
            if existing_path.is_file():
                info, issues = validate_render(
                    existing_path,
                    min_duration_s=float(self.config["render"]["min_duration_s"]),
                    max_duration_s=float(self.config["render"]["max_duration_s"]),
                    width=int(self.config["render"]["width"]),
                    height=int(self.config["render"]["height"]),
                )
                if not issues:
                    return RenderResult(
                        package_id=package_id,
                        status="COMPLETE",
                        job_id=existing_job,
                        render_path=existing_render,
                        media=info,
                    )
            raise ViewMadeBlocked(
                "the request is COMPLETE but its local render is missing or invalid. "
                "Repair or recover the file; do not submit another paid render."
            )
        if existing_status == "COMPLETE":
            raise ViewMadeBlocked(
                "the request is COMPLETE but has no render_path. Repair the request "
                "state before submitting another paid render."
            )
        if existing_job and (
            existing_status in {"SUBMITTED", "RENDERING", "STALE"}
            or existing_provider_state in {"queued", "rendering", "ready"}
        ):
            raise ViewMadeBlocked(
                f"ViewMade job {existing_job} already exists "
                f"(status={existing_status!r}, provider_state={existing_provider_state!r}). "
                "Do not submit a second paid render. Recover the existing job with "
                "`scripts/recover_viewmade_job.py` or resolve it in the provider dashboard."
            )
        if not self.binding_complete():
            raise ViewMadeBlocked(
                "ViewMade render/status/download tools are not fully bound. "
                "Run `cddocs viewmade discover` and `cddocs viewmade bind` first."
            )

        render_context = self._context(request_payload)
        binding = self.binding() or {}
        render_entry, render_arguments = self._bound_arguments("render", render_context)
        token = oauth.get_access_token(self.project, self.settings)
        client = MCPClient(
            self.config["mcp_url"],
            token,
            protocol_version=self.config.get("protocol_version", "2025-06-18"),
            connect_url=self.config["connect_url"],
        )
        client.initialize()
        try:
            submit = client.call_tool(str(render_entry["name"]), render_arguments)
        except MCPAuthError:
            raise
        except MCPError as exc:
            self._update_request(package_id, request_payload, status="FAILED", error=str(exc))
            return RenderResult(package_id=package_id, status="FAILED", error=str(exc))

        job_id = _extract_path(submit, binding.get("job_id_path") or ["job_id"])
        if not job_id:
            job_id = _first_present(submit, ("job_id", "id", "render_id", "video_id"))
        if not job_id:
            message = (
                "ViewMade render tool returned no job id. Update the binding with "
                "`--job-id-path` after inspecting the tool output schema."
            )
            self._update_request(package_id, request_payload, status="FAILED", error=message)
            return RenderResult(package_id=package_id, status="FAILED", error=message)
        job_id = str(job_id)
        self._update_request(
            package_id,
            request_payload,
            status="SUBMITTED",
            job_id=job_id,
            submission={
                "submitted_at": utc_now_iso(),
                "render_tool": render_entry["name"],
                "arguments_sha256": _canonical_sha256(render_arguments),
                "arguments_summary": {
                    "topic": render_arguments.get("topic"),
                    "engine": render_arguments.get("engine"),
                    "style": render_arguments.get("style"),
                    "voice": render_arguments.get("voice"),
                    "script_lines": len(str(render_arguments.get("script") or "").splitlines()),
                    "operation_key": render_arguments.get("operation_key"),
                },
            },
            error=None,
        )
        record = {
            "package_id": package_id,
            "job_id": job_id,
            "status": "SUBMITTED",
            "submitted_at": utc_now_iso(),
            "provider_state": None,
            "render_path": None,
        }
        self._write_job_state(package_id, record)

        deadline = time.monotonic() + max(1.0, timeout_s)
        provider_state: Any = None
        final_state = ""
        while time.monotonic() < deadline:
            time.sleep(max(0.5, min(poll_interval, 30.0)))
            status_result = self._call_bound(
                "status",
                self._context(request_payload, job_id=job_id),
            )
            provider_state = _extract_path(
                status_result, binding.get("provider_state_path") or ["status"]
            )
            if provider_state is None:
                provider_state = _first_present(status_result, ("status", "state"))
            final_state = str(provider_state or "").strip().lower()
            record.update(
                {
                    "status": "RENDERING" if final_state else "SUBMITTED",
                    "provider_state": provider_state,
                    "last_polled_at": utc_now_iso(),
                }
            )
            self._write_job_state(package_id, record)
            self._update_request(
                package_id,
                request_payload,
                status="RENDERING",
                job_id=job_id,
                provider_state=provider_state,
            )
            if final_state in {state.lower() for state in binding.get("success_states", [])}:
                break
            if final_state in {state.lower() for state in binding.get("failure_states", [])}:
                message = f"ViewMade job {job_id} ended in state {provider_state!r}"
                self._update_request(
                    package_id, request_payload, status="FAILED", job_id=job_id, error=message
                )
                record.update({"status": "FAILED", "error": message})
                self._write_job_state(package_id, record)
                return RenderResult(
                    package_id=package_id,
                    status="FAILED",
                    job_id=job_id,
                    error=message,
                    provider_state=str(provider_state),
                )
        else:
            message = f"ViewMade job {job_id} did not finish within {int(timeout_s)}s"
            self._update_request(
                package_id, request_payload, status="FAILED", job_id=job_id, error=message
            )
            record.update({"status": "FAILED", "error": message})
            self._write_job_state(package_id, record)
            return RenderResult(
                package_id=package_id,
                status="FAILED",
                job_id=job_id,
                error=message,
                provider_state=str(provider_state) if provider_state else None,
            )

        try:
            download_result = self._call_bound(
                "download",
                self._context(
                    request_payload, job_id=job_id, provider_state=provider_state
                ),
            )
        except (MCPError, ViewMadeBlocked) as exc:
            message = f"ViewMade job {job_id} finished but download failed: {exc}"
            self._update_request(
                package_id, request_payload, status="FAILED", job_id=job_id, error=message
            )
            record.update({"status": "FAILED", "error": message})
            self._write_job_state(package_id, record)
            return RenderResult(
                package_id=package_id,
                status="FAILED",
                job_id=job_id,
                error=message,
                provider_state=str(provider_state),
            )

        url = _extract_path(download_result, binding.get("download_url_path") or ["url"])
        if not url:
            url = _first_present(download_result, ("url", "download_url", "video_url"))
        file_path = _extract_path(
            download_result, binding.get("download_file_path") or ["path"]
        )
        if not file_path:
            file_path = _first_present(download_result, ("path", "file", "file_path"))

        target_dir = self.project.renders_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{package_id}.mp4"
        try:
            normalization = None
            if url:
                self._download_url(str(url), target)
            elif file_path and Path(str(file_path)).is_file():
                with open(str(file_path), "rb") as source, tempfile.NamedTemporaryFile(
                    delete=False, dir=target_dir, suffix=".mp4"
                ) as handle:
                    shutil.copyfileobj(source, handle)
                    temp_name = handle.name
                os.replace(temp_name, target)
            else:
                raise ViewMadeBlocked(
                    "ViewMade download tool returned neither a URL nor an existing file path"
                )
            normalization = self._normalize_render(target)
        except (OSError, urllib.error.URLError, ViewMadeBlocked) as exc:
            message = f"could not download the ViewMade render: {exc}"
            self._update_request(
                package_id, request_payload, status="FAILED", job_id=job_id, error=message
            )
            record.update({"status": "FAILED", "error": message})
            self._write_job_state(package_id, record)
            return RenderResult(
                package_id=package_id,
                status="FAILED",
                job_id=job_id,
                error=message,
                provider_state=str(provider_state) if provider_state else None,
            )

        info, issues = validate_render(
            target,
            min_duration_s=float(self.config["render"]["min_duration_s"]),
            max_duration_s=float(self.config["render"]["max_duration_s"]),
            width=int(self.config["render"]["width"]),
            height=int(self.config["render"]["height"]),
        )
        if issues:
            invalid = target.with_suffix(".invalid.mp4")
            try:
                os.replace(target, invalid)
            except OSError:
                invalid = target
            message = "downloaded MP4 failed local validation: " + "; ".join(issues)
            self._update_request(
                package_id,
                request_payload,
                status="FAILED",
                job_id=job_id,
                error=message,
                provider_state=provider_state,
            )
            record.update({"status": "FAILED", "error": message})
            self._write_job_state(package_id, record)
            return RenderResult(
                package_id=package_id,
                status="FAILED",
                job_id=job_id,
                error=message,
                render_path=safe_relative(invalid, self.project.root),
                provider_state=str(provider_state) if provider_state else None,
            )

        render_rel = safe_relative(target, self.project.root)
        self._update_request(
            package_id,
            request_payload,
            status="COMPLETE",
            job_id=job_id,
            provider_state=provider_state,
            render_path=render_rel,
            render_sha256=sha256_file(target),
            normalization=normalization,
            error=None,
        )
        record.update(
            {
                "status": "COMPLETE",
                "provider_state": provider_state,
                "render_path": render_rel,
                "render_sha256": sha256_file(target),
                "normalization": normalization,
                "completed_at": utc_now_iso(),
                "media": info.to_dict() if info else None,
            }
        )
        self._write_job_state(package_id, record)
        return RenderResult(
            package_id=package_id,
            status="COMPLETE",
            job_id=job_id,
            render_path=render_rel,
            media=info,
            provider_state=str(provider_state) if provider_state else None,
        )

    def _normalize_render(self, target: Path) -> dict | None:
        """Normalize a higher-resolution 9:16 render to the channel format."""
        render_config = self.config.get("render") or {}
        if not render_config.get("normalize", False):
            return None
        width = int(render_config["width"])
        height = int(render_config["height"])
        info, _issues = validate_file(target, expect_format="mp4", min_bytes=100_000)
        if info is None or not info.width or not info.height:
            return None
        if info.width == width and info.height == height:
            return None
        status, detail = check_aspect(
            info.width, info.height, str(render_config.get("aspect_ratio", "9:16"))
        )
        if status != "PASS":
            return None
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ViewMadeBlocked(
                f"provider returned {info.width}x{info.height}; ffmpeg is required to "
                f"normalize it to {width}x{height}"
            )
        temporary = target.with_name(f"{target.stem}.normalized.mp4")
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(target),
            "-vf",
            f"scale={width}:{height}:flags=lanczos,setsar=1",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True)
            normalized, issues = validate_file(
                temporary,
                expect_format="mp4",
                min_bytes=100_000,
                expected_width=width,
                expected_height=height,
                require_audio=True,
            )
            if normalized is None or issues:
                raise ViewMadeBlocked(
                    "ffmpeg normalization did not produce the required display size: "
                    + "; ".join(issues)
                )
            os.replace(temporary, target)
        except (OSError, subprocess.CalledProcessError) as exc:
            if temporary.exists():
                temporary.unlink()
            raise ViewMadeBlocked(f"ffmpeg normalization failed: {exc}") from exc
        except ViewMadeBlocked:
            if temporary.exists():
                temporary.unlink()
            raise
        return {
            "source_width": info.width,
            "source_height": info.height,
            "target_width": width,
            "target_height": height,
            "tool": "ffmpeg",
        }

    def _download_url(self, url: str, target: Path) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ViewMadeBlocked("refusing to download a render over a non-https URL")
        headers = {"User-Agent": "cddocs/0.1 (+cats-dogs-documentary)"}
        host = (parsed.hostname or "").lower()
        viewmade_hosts = {"viewmade.com", "www.viewmade.com"}
        if host in viewmade_hosts or host.endswith(".viewmade.com"):
            headers["Authorization"] = f"Bearer {oauth.get_access_token(self.project, self.settings)}"
        request = urllib.request.Request(url, headers=headers)
        temp_name = None
        try:
            with urllib.request.urlopen(request, timeout=120) as response, tempfile.NamedTemporaryFile(
                delete=False, dir=target.parent, suffix=".mp4"
            ) as handle:
                temp_name = handle.name
                shutil.copyfileobj(response, handle, length=1 << 20)
            os.replace(temp_name, target)
            temp_name = None
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass


def public_tool_schema(tool: dict) -> dict:
    return {
        "name": tool.get("name"),
        "title": tool.get("title"),
        "description": tool.get("description"),
        "inputSchema": tool.get("inputSchema"),
        "outputSchema": tool.get("outputSchema"),
    }
