"""YouTube-ready metadata generation from a verified package and research file."""
from __future__ import annotations

import re
from typing import Iterable

from .util import PipelineError, normalise_whitespace, word_count


def _authors(source: dict) -> str:
    authors = source.get("authors") or []
    if isinstance(authors, str):
        return authors
    cleaned = [str(author).strip() for author in authors if str(author).strip()]
    if not cleaned:
        return "Unknown authors"
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} & {cleaned[1]}"
    return f"{cleaned[0]} et al."


def citation(source: dict) -> str:
    authors = _authors(source)
    year = source.get("year", "n.d.")
    title = str(source.get("title", "")).strip().rstrip(".")
    journal = str(source.get("journal") or source.get("publisher") or "").strip()
    volume = str(source.get("volume") or "").strip()
    issue = str(source.get("issue") or "").strip()
    pages = str(source.get("pages") or "").strip()
    details = journal
    if volume:
        details += f" {volume}"
        if issue:
            details += f"({issue})"
    if pages:
        details += f", {pages}"
    url = str(source.get("url") or "").strip()
    pieces = [f"{authors} ({year}). {title}."]
    if details:
        pieces.append(f"{details}.")
    if url:
        pieces.append(url)
    return " ".join(pieces)


def _footage_attributions(provider_package: dict | None) -> list[str]:
    if not provider_package:
        return []
    attributions = [
        str(item).strip()
        for item in provider_package.get("attributions") or []
        if str(item).strip()
    ]
    if attributions:
        return attributions
    lines: list[str] = []
    for source in provider_package.get("sources") or []:
        title = str(source.get("title") or "").strip()
        url = str(source.get("url") or "").strip()
        if title and url:
            lines.append(f"{title} — {url}")
        elif url:
            lines.append(url)
    return lines


def build_metadata(
    package: dict,
    research: dict,
    channel: dict,
    *,
    provider_package: dict | None = None,
) -> dict:
    youtube = package.get("youtube") or {}
    editorial = channel["editorial"]
    format_cfg = channel["format"]
    visual_mode = str((channel.get("visual") or {}).get("mode") or "real_footage_montage")
    contains_synthetic_media = bool(editorial.get("contains_synthetic_media", False))

    title = str(youtube.get("title") or package.get("title") or "").strip()
    central_fact = normalise_whitespace(str(package.get("central_fact", "")))
    takeaway = normalise_whitespace(str(package.get("takeaway", "")))
    if not central_fact:
        raise PipelineError(f"{package.get('id')}: central_fact is required for metadata")
    if not takeaway:
        raise PipelineError(f"{package.get('id')}: takeaway is required for metadata")

    hashtags = [str(tag).strip() for tag in youtube.get("hashtags", [])]
    hashtags = [tag if tag.startswith("#") else f"#{tag}" for tag in hashtags]
    if not any(tag.lower() == "#shorts" for tag in hashtags):
        hashtags.append("#Shorts")

    sources = research.get("sources") or []
    citations = [citation(source) for source in sources]
    source_lines = "\n".join(f"- {item}" for item in citations)
    footage = _footage_attributions(provider_package)
    footage_block = ""
    if footage:
        footage_block = "Footage:\n" + "\n".join(f"- {item}" for item in footage) + "\n\n"
    hashtag_line = " ".join(hashtags)

    description = (
        f"{central_fact}\n\n"
        f"{takeaway}\n\n"
        f"Sources:\n{source_lines}\n\n"
        f"{footage_block}"
        f"{editorial['required_disclosure']} "
        f"{editorial['educational_disclaimer']}\n\n"
        f"{hashtag_line}"
    )

    tags = [str(tag).strip() for tag in youtube.get("tags", []) if str(tag).strip()]
    category = str(youtube.get("category") or "Pets & Animals")
    return {
        "schema_version": 1,
        "package_id": package.get("id"),
        "platform": "youtube",
        "format": "short",
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "tags": tags,
        "category": category,
        "category_id": str(youtube.get("category_id") or "15"),
        "language": channel.get("language", "en"),
        "visibility": str(youtube.get("visibility") or channel["publishing"]["visibility_default"]),
        "made_for_kids": bool(channel["publishing"]["made_for_kids"]),
        "visual_mode": visual_mode,
        "contains_synthetic_media": contains_synthetic_media,
        "visual_disclosure": editorial["required_disclosure"],
        "footage_provider": "viewmade" if provider_package else None,
        "footage_attributions": footage,
        "educational_disclaimer": editorial["educational_disclaimer"],
        "manual_upload_required": bool(channel["publishing"]["manual_upload"]),
        "duration_s": package.get("target_duration_s"),
        "aspect_ratio": format_cfg["aspect_ratio"],
        "resolution": f"{format_cfg['width']}x{format_cfg['height']}",
        "sources": [
            {
                "id": source.get("id"),
                "citation": citations[index],
                "url": source.get("url"),
                "doi": source.get("doi"),
                "pmid": source.get("pmid"),
            }
            for index, source in enumerate(sources)
        ],
        "youtube_video_id": None,
        "youtube_url": None,
        "upload_status": "not_uploaded_manual_only",
    }


def validate_metadata(metadata: dict, package: dict, research: dict, channel: dict) -> list[str]:
    issues: list[str] = []
    editorial = channel["editorial"]
    format_cfg = channel["format"]
    title = str(metadata.get("title", ""))
    description = str(metadata.get("description", ""))
    hashtags = metadata.get("hashtags") or []
    tags = metadata.get("tags") or []

    if not title:
        issues.append("metadata title is empty")
    if len(title) > int(editorial["max_title_chars"]):
        issues.append(
            f"metadata title is {len(title)} chars (max {editorial['max_title_chars']})"
        )
    if title != title.strip():
        issues.append("metadata title has leading/trailing whitespace")
    letters = [char for char in title if char.isalpha()]
    if letters and all(char.isupper() for char in letters):
        issues.append("metadata title is entirely uppercase")
    lowered = title.lower()
    for phrase in editorial.get("forbidden_claim_phrases", []):
        if phrase in lowered:
            issues.append(f"metadata title contains forbidden claim phrase: {phrase!r}")

    if not description:
        issues.append("metadata description is empty")
    if len(description) > int(editorial["max_description_chars"]):
        issues.append(
            f"metadata description is {len(description)} chars (max {editorial['max_description_chars']})"
        )
    disclosure = editorial["required_disclosure"]
    visual_mode = str((channel.get("visual") or {}).get("mode") or "real_footage_montage")
    expected_synthetic = bool(editorial.get("contains_synthetic_media", False))
    if disclosure.lower() not in description.lower():
        issues.append("metadata description is missing the required visual disclosure")
    if metadata.get("visual_disclosure") != disclosure:
        issues.append("metadata visual_disclosure does not match channel policy")
    if metadata.get("visual_mode") != visual_mode:
        issues.append("metadata visual_mode does not match channel policy")
    if metadata.get("contains_synthetic_media") is not expected_synthetic:
        issues.append(
            "metadata contains_synthetic_media does not match channel policy "
            f"(expected {expected_synthetic})"
        )
    if not expected_synthetic and "ai-assisted" in description.lower():
        issues.append("real-footage metadata must not claim AI-assisted visuals")
    if editorial.get("visual_attribution_required"):
        if not isinstance(metadata.get("footage_attributions"), list):
            issues.append("metadata footage_attributions must be a list")
    if editorial["educational_disclaimer"].lower() not in description.lower():
        issues.append("metadata description is missing the educational disclaimer")
    if not re.search(r"(?im)^sources:\s*$", description):
        issues.append("metadata description has no Sources section")
    if "http://" in description:
        issues.append("metadata description contains an insecure http:// URL")
    if len(citations := [item.get("citation") for item in metadata.get("sources", [])]) != len(
        research.get("sources", [])
    ):
        issues.append("metadata source list does not match research sources")

    if not isinstance(hashtags, list) or not hashtags:
        issues.append("metadata has no hashtags")
    else:
        if len(hashtags) > int(editorial["max_hashtags"]):
            issues.append(
                f"metadata has {len(hashtags)} hashtags (max {editorial['max_hashtags']})"
            )
        seen: set[str] = set()
        for tag in hashtags:
            if not re.fullmatch(r"#[A-Za-z0-9_]+", str(tag)):
                issues.append(f"invalid hashtag: {tag!r}")
            if str(tag).lower() in seen:
                issues.append(f"duplicate hashtag: {tag!r}")
            seen.add(str(tag).lower())
        if "#shorts" not in seen:
            issues.append("metadata hashtags must include #Shorts")
    if sum(len(str(tag)) + 1 for tag in tags) > int(editorial["max_tags_chars"]):
        issues.append("metadata tags exceed the YouTube tag character budget")
    if metadata.get("visibility") not in {"private", "unlisted", "public"}:
        issues.append("metadata visibility must be private, unlisted, or public")
    if metadata.get("made_for_kids") is not False:
        issues.append("metadata made_for_kids must be false for this channel")
    if metadata.get("duration_s") != package.get("target_duration_s"):
        issues.append("metadata duration does not match the package target duration")
    if metadata.get("aspect_ratio") != format_cfg["aspect_ratio"]:
        issues.append("metadata aspect ratio does not match channel format")
    if metadata.get("resolution") != f"{format_cfg['width']}x{format_cfg['height']}":
        issues.append("metadata resolution does not match channel format")
    if metadata.get("upload_status") != "not_uploaded_manual_only":
        issues.append("metadata upload_status must remain manual-only")
    if word_count(description) < 12:
        issues.append("metadata description is too thin for a documentary Short")
    return issues


def hashtags_from_package(package: dict) -> list[str]:
    youtube = package.get("youtube") or {}
    return list(youtube.get("hashtags") or [])
