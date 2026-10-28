"""ViewMade adapter built on official OAuth + MCP discovery.

No ViewMade tool name is hardcoded. The adapter refuses to submit a render
until the official MCP server has been authenticated, tools have been listed,
and the user has explicitly bound render/status/download tools with argument
templates that satisfy each tool's advertised input schema.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Project, Settings
from ..media_probe import MediaInfo, validate_render
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
    "prompt",
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


def _generation_prompt(request_payload: dict) -> str:
    request = request_payload.get("request") or {}
    lines = [
        f"Create a {request.get('duration_s')} second vertical YouTube Short titled {request.get('title')!r}.",
        f"Format: {request.get('aspect_ratio')} {request.get('resolution')}, documentary-style illustrative visuals.",
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
            "- Natural English narration, burned-in captions matching the provided cues.",
            "- Species-correct anatomy and consistent markings; no extra limbs or malformed faces.",
            "- No distressed animals, no staged aggression, no on-screen text artifacts, no logos.",
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
            "prompt": _generation_prompt(request_payload),
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

    def _call_bound(self, key: str, context: dict) -> Any:
        binding = self.binding()
        if not binding:
            raise ViewMadeBlocked("ViewMade tools are not bound")
        entry = (binding.get("tools") or {}).get(key)
        if not entry:
            raise ViewMadeBlocked(f"ViewMade {key} tool is not bound")
        arguments = _resolve_placeholders(entry.get("template") or {}, context)
        if not isinstance(arguments, dict):
            raise ViewMadeBlocked(f"ViewMade {key} template did not produce an object")
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
        if not self.binding_complete():
            raise ViewMadeBlocked(
                "ViewMade render/status/download tools are not fully bound. "
                "Run `cddocs viewmade discover` and `cddocs viewmade bind` first."
            )
        # Never re-render a package already verified in this request file.
        existing_status = request_payload.get("status")
        existing_render = request_payload.get("render_path")
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
                        job_id=request_payload.get("job_id"),
                        render_path=existing_render,
                        media=info,
                    )

        token = oauth.get_access_token(self.project, self.settings)
        client = MCPClient(
            self.config["mcp_url"],
            token,
            protocol_version=self.config.get("protocol_version", "2025-06-18"),
            connect_url=self.config["connect_url"],
        )
        client.initialize()
        binding = self.binding() or {}
        try:
            submit = client.call_tool(
                str(binding["tools"]["render"]["name"]),
                _resolve_placeholders(
                    binding["tools"]["render"].get("template") or {},
                    self._context(request_payload),
                ),
            )
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
                "render_tool": binding["tools"]["render"]["name"],
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
            error=None,
        )
        record.update(
            {
                "status": "COMPLETE",
                "provider_state": provider_state,
                "render_path": render_rel,
                "render_sha256": sha256_file(target),
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
