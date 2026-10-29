"""Human-readable and provider-request artifacts for one package."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .metadata import citation
from .subtitles import Cue
from .util import format_clock, normalise_whitespace, write_json


def _scene_window(scene: dict) -> str:
    start = float(scene.get("start_s", 0))
    end = start + float(scene.get("duration_s", 0))
    return f"{format_clock(start)}-{format_clock(end)}"


def build_script(package: dict, research: dict, channel: dict) -> str:
    scenes = package.get("scenes") or []
    claims = package.get("claims") or []
    sources = research.get("sources") or []
    lines = [
        f"# {package.get('title')}",
        "",
        f"**Package:** `{package.get('id')}`  ",
        f"**Batch:** `{package.get('batch_id')}`  ",
        f"**Pillar:** {channel['pillars'].get(package.get('pillar'), package.get('pillar'))}  ",
        f"**Runtime:** {package.get('target_duration_s')}s | 9:16 vertical | {channel['format']['width']}x{channel['format']['height']}  ",
        f"**Voice:** {channel['editorial']['voice']}",
        "",
        "## Central question",
        "",
        package.get("central_question", ""),
        "",
        "## Verified core fact",
        "",
        package.get("central_fact", ""),
        "",
        "## Takeaway",
        "",
        package.get("takeaway", ""),
        "",
        "## Narration and scene plan",
        "",
    ]
    for index, scene in enumerate(scenes, start=1):
        heading = "Hook" if index == 1 else f"Scene {index}"
        lines.extend(
            [
                f"### {heading} - {scene.get('id')} ({_scene_window(scene)})",
                "",
                f"> {scene.get('narration', '')}",
                "",
                f"**Visual:** {scene.get('visual', {}).get('description', '')}",
                "",
                f"**Shot:** {scene.get('visual', {}).get('shot_type', '')}; "
                f"**Subject:** {scene.get('visual', {}).get('subject', '')}; "
                f"**Motion:** {scene.get('visual', {}).get('motion', '')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Evidence table",
            "",
            "| Claim | Evidence level | Limit | Sources |",
            "| --- | --- | --- | --- |",
        ]
    )
    for claim in claims:
        source_refs = ", ".join(f"`{ref}`" for ref in claim.get("source_ids", []))
        claim_text = str(claim.get("text", "")).replace("|", "\\|")
        evidence = str(claim.get("evidence_level", "")).replace("|", "\\|")
        limits = str(claim.get("limits", "")).replace("|", "\\|")
        lines.append(f"| {claim_text} | {evidence} | {limits} | {source_refs} |")
    lines.extend(["", "## Sources", ""])
    for source in sources:
        lines.append(f"- {citation(source)}")
    lines.extend(
        [
            "",
            "## Editorial notes",
            "",
            f"- **Source verification:** {research.get('verification', {}).get('method', '')}",
            f"- **Myth or anecdote:** {research.get('verification', {}).get('myth_or_anecdote', '')}",
            "- **Human sign-off:** required before upload. This file is not a claim of human review.",
            f"- **Disclosure:** {channel['editorial']['required_disclosure']}",
            "",
        ]
    )
    return "\n".join(lines)


def build_visual_plan(package: dict, channel: dict) -> str:
    visual_policy = package.get("visual_policy") or {}
    scenes = package.get("scenes") or []
    lines = [
        f"# Visual plan - {package.get('title')}",
        "",
        f"**Package:** `{package.get('id')}`  ",
        f"**Format:** 9:16 vertical, {channel['format']['width']}x{channel['format']['height']}, "
        f"{package.get('target_duration_s')} seconds  ",
        f"**Disclosure:** {visual_policy.get('disclosure', channel['editorial']['required_disclosure'])}",
        "",
        "## Global direction",
        "",
        f"- **Style:** {visual_policy.get('style', channel['visual']['style'])}",
        f"- **Anatomy:** {visual_policy.get('anatomy', '')}",
        f"- **Welfare:** {visual_policy.get('welfare', '')}",
        f"- **Continuity:** {visual_policy.get('continuity', '')}",
        f"- **Negative prompt:** {channel['visual']['negative_prompt']}",
        "",
        "## Scene-by-scene direction",
        "",
    ]
    for index, scene in enumerate(scenes, start=1):
        visual = scene.get("visual") or {}
        lines.extend(
            [
                f"### {index}. {scene.get('id')} ({_scene_window(scene)})",
                "",
                f"- **Shot:** {visual.get('shot_type', '')}",
                f"- **Subject:** {visual.get('subject', '')}",
                f"- **Framing:** {visual.get('framing', '')}",
                f"- **Action:** {visual.get('description', '')}",
                f"- **Camera motion:** {visual.get('motion', '')}",
                f"- **Continuity:** {visual.get('continuity', '')}",
                f"- **Avoid:** {', '.join(visual.get('avoid') or [])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Welfare and authenticity review",
            "",
            "- No scene asks for fear, pain, injury, aggression, or staged distress.",
            "- Real footage is illustrative B-roll, not evidence; never present a clip as an archival record of the claim.",
            "- Every clip must show species-correct, anatomically coherent animals; reject malformed or uncanny animals.",
            "- Reject watermarks, logos, social handles, burned-in captions, extra limbs, or merged faces.",
            "- Credit every third-party clip source in the YouTube description.",
            "- Keep captions in the lower third and outside the main subject's face.",
            "",
        ]
    )
    return "\n".join(lines)


def build_viewmade_request(
    package: dict,
    cues: Iterable[Cue],
    channel: dict,
    viewmade: dict,
    *,
    binding_complete: bool,
    previous: dict | None = None,
) -> dict:
    format_cfg = channel["format"]
    render_cfg = viewmade["render"]
    scenes = []
    for scene in package.get("scenes") or []:
        scenes.append(
            {
                "id": scene.get("id"),
                "start_s": scene.get("start_s"),
                "duration_s": scene.get("duration_s"),
                "narration": scene.get("narration"),
                "visual": scene.get("visual"),
                "transition": scene.get("transition", "cut"),
            }
        )
    cue_list = [
        {
            "index": cue.index,
            "start_s": round(cue.start_s, 3),
            "end_s": round(cue.end_s, 3),
            "text": cue.text.replace("\n", " "),
        }
        for cue in cues
    ]
    narration = " ".join(str(scene.get("narration", "")) for scene in scenes)
    blocked_reason = (
        None
        if binding_complete
        else "ViewMade OAuth and official MCP tool bindings are not both ready. "
        "Run `cddocs viewmade login`, `cddocs viewmade discover`, and `cddocs viewmade bind`."
    )
    payload = {
        "schema_version": 1,
        "package_id": package.get("id"),
        "provider": "viewmade",
        "provider_endpoint": viewmade["mcp_url"],
        "status": "NOT_SUBMITTED",
        "submission_allowed": False,
        "blocked_reason": blocked_reason,
        "preflight": {
            "tool_bindings_complete": binding_complete,
            "authentication": "not_checked_by_build",
            "live_authorisation": "required_at_render_time",
        },
        "request": {
            "title": package.get("title"),
            "provider_topic": package.get("central_question") or package.get("title"),
            "format": "youtube_shorts",
            "duration_s": package.get("target_duration_s"),
            "aspect_ratio": format_cfg["aspect_ratio"],
            "resolution": f"{format_cfg['width']}x{format_cfg['height']}",
            "language": channel.get("language", "en"),
            "narration": narration,
            "scenes": scenes,
            "captions": {
                "mode": "burned_in",
                "srt_file": "subtitles.srt",
                "cues": cue_list,
            },
            "voice": render_cfg["voice"],
            "music": render_cfg["music"],
            "visual_style": channel["visual"]["style"],
            "negative_prompt": channel["visual"]["negative_prompt"],
            "disclosure": render_cfg["disclosure"],
            "output": {
                "container": "mp4",
                "width": format_cfg["width"],
                "height": format_cfg["height"],
                "fps": 30,
                "audio": True,
            },
        },
        "submission": None,
        "job_id": None,
        "render_path": None,
        "editorial_review": None,
        "notes": [
            "This is a local request specification, not evidence that ViewMade accepted a job.",
            "No MCP tool name is hardcoded. The adapter uses the official discovered and bound tools.",
            "A render is COMPLETE only after the downloaded MP4 passes local media validation.",
        ],
    }
    if previous is None:
        return payload

    previous_status = previous.get("status")
    has_job = bool(previous.get("job_id"))
    has_render = bool(previous.get("render_path"))
    same_spec = previous.get("request") == payload["request"]
    if same_spec and (has_job or has_render or previous_status in {"COMPLETE", "FAILED", "STALE"}):
        for key in (
            "status",
            "job_id",
            "provider_state",
            "render_path",
            "render_sha256",
            "normalization",
            "provider_package",
            "submission",
            "editorial_review",
            "error",
            "updated_at",
        ):
            if key in previous:
                payload[key] = previous[key]
        return payload

    if not same_spec and (has_job or has_render):
        # The provider job or MP4 belongs to an older specification. Keep the
        # evidence, but never present it as a valid render for the new script.
        for key in (
            "job_id",
            "provider_state",
            "render_path",
            "render_sha256",
            "normalization",
            "provider_package",
            "submission",
            "editorial_review",
        ):
            payload[key] = previous.get(key)
        payload["status"] = "STALE"
        payload["error"] = (
            "request specification changed after the provider job; the existing "
            "render is stale and must not be published"
        )
        payload["notes"].append(
            "Existing job and render were preserved as STALE after a request change."
        )
    return payload


def write_visual_plan(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    return path


def normalize_request_payload(payload: dict) -> dict:
    """Defensive copy used before any future live submission."""
    import json

    return json.loads(json.dumps(payload, ensure_ascii=False))


def write_request(path: Path, payload: dict) -> Path:
    return write_json(path, payload)


def build_cover_prompt(package: dict) -> str:
    first = (package.get("scenes") or [{}])[0].get("visual", {})
    return normalise_whitespace(
        f"{first.get('subject', '')}. {first.get('description', '')} "
        f"{first.get('framing', '')}. No text, no logos, no watermarks."
    )
