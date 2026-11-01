"""Fail-closed editorial, scientific, visual, and packaging checks.

Every check is deterministic and offline. A FAIL blocks rendering and batch
completion. A WARN permits local preview packaging but is surfaced in the QA
report. Human sign-off remains a separate gate before upload.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .history import History
from .metadata import citation, validate_metadata
from .subtitles import Cue, cue_stats, cue_text, validate_cues
from .util import (
    PipelineError,
    normalise_whitespace,
    read_json,
    utc_now_iso,
    word_count,
    write_json,
)

STATUS_ORDER = {"PASS": 0, "SKIP": 1, "WARN": 2, "FAIL": 3}
PLACEHOLDER_RE = re.compile(
    r"\b(TBD|TODO|FIXME|XXX|lorem ipsum|insert here|placeholder|dummy text)\b", re.IGNORECASE
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HASHTAG_RE = re.compile(r"^#[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class QAResult:
    package_id: str
    batch_id: str
    checks: list[Check] = field(default_factory=list)
    render_status: str = "NOT_RENDERED"
    publish_ready: bool = False
    generated_at: str = field(default_factory=utc_now_iso)
    artifacts: dict[str, str] = field(default_factory=dict)

    def add(self, check_id: str, label: str, status: str, detail: str) -> None:
        if status not in STATUS_ORDER:
            raise PipelineError(f"invalid check status {status!r}")
        self.checks.append(Check(check_id, label, status, detail))

    @property
    def status(self) -> str:
        if any(check.status == "FAIL" for check in self.checks):
            return "FAIL"
        if any(check.status == "WARN" for check in self.checks):
            return "WARN"
        return "PASS"

    @property
    def counts(self) -> dict:
        result = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
        for check in self.checks:
            result[check.status] += 1
        return result

    def to_dict(self, *, artifacts: dict[str, str] | None = None) -> dict:
        payload = {
            "schema_version": 1,
            "package_id": self.package_id,
            "batch_id": self.batch_id,
            "generated_at": self.generated_at,
            "status": self.status,
            "publish_ready": self.publish_ready,
            "render_status": self.render_status,
            "summary": self.counts,
            "checks": [check.to_dict() for check in self.checks],
        }
        merged = dict(self.artifacts)
        if artifacts:
            merged.update(artifacts)
        if merged:
            payload["artifacts"] = merged
        return payload


def _status_ok(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _domain_allowed(host: str, allowed: Iterable[str], banned: Iterable[str]) -> tuple[bool, bool]:
    host = host.lower().strip(".")
    allowed_match = any(host == domain or host.endswith("." + domain) for domain in allowed)
    banned_match = any(host == domain or host.endswith("." + domain) for domain in banned)
    return allowed_match, banned_match


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not ISO_DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _nonempty(value: object, min_length: int = 1) -> bool:
    return isinstance(value, str) and len(normalise_whitespace(value)) >= min_length


def _find_terms(text: str, terms: Iterable[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def validate_package(
    *,
    package: dict,
    research: dict,
    folder: Path,
    channel: dict,
    sources_config: dict,
    history: History | None,
    metadata: dict | None = None,
    cues: list[Cue] | None = None,
    srt_text: str | None = None,
    artifact_files: dict[str, str] | None = None,
) -> QAResult:
    package_id = str(package.get("id") or folder.name)
    batch_id = str(package.get("batch_id") or "")
    result = QAResult(package_id=package_id, batch_id=batch_id)
    add = result.add
    editorial_cfg = channel["editorial"]
    visual_cfg = channel["visual"]
    format_cfg = channel["format"]

    # --- identity and basic shape -------------------------------------
    add(
        "package.schema",
        "Package schema version",
        _status_ok(package.get("schema_version") == 1),
        f"schema_version={package.get('schema_version')!r}",
    )
    add(
        "package.id",
        "Package id matches folder and slug format",
        _status_ok(package_id == folder.name and bool(ID_RE.fullmatch(package_id))),
        f"id={package_id!r}, folder={folder.name!r}",
    )
    add(
        "package.batch",
        "Package belongs to a valid batch id",
        _status_ok(bool(ID_RE.fullmatch(batch_id))),
        f"batch_id={batch_id!r}",
    )
    add(
        "package.pillar",
        "Content pillar is defined",
        _status_ok(package.get("pillar") in channel["pillars"]),
        f"pillar={package.get('pillar')!r}",
    )
    for field_name in ("title", "central_question", "central_fact", "takeaway"):
        add(
            f"package.{field_name}",
            f"Package {field_name}",
            _status_ok(_nonempty(package.get(field_name), 8)),
            f"{field_name}={str(package.get(field_name))[:120]!r}",
        )
    add(
        "package.title.length",
        "Working title fits YouTube's title limit",
        _status_ok(len(str(package.get("title", ""))) <= int(editorial_cfg["max_title_chars"])),
        f"{len(str(package.get('title', '')))} chars",
    )
    add(
        "package.placeholder_text",
        "No placeholder text in editorial fields",
        _status_ok(
            not PLACEHOLDER_RE.search(
                " ".join(
                    str(package.get(key, ""))
                    for key in ("title", "central_question", "central_fact", "takeaway")
                )
            )
        ),
        "scanned title, question, fact, and takeaway",
    )
    editorial = package.get("editorial") or {}
    add(
        "package.editorial",
        "Editorial status and human-review gate",
        _status_ok(
            editorial.get("status") == "source-checked"
            and editorial.get("human_review_required") is True
            and editorial.get("human_signoff") is False
        ),
        f"status={editorial.get('status')!r}, human_signoff={editorial.get('human_signoff')!r}",
    )
    result.publish_ready = bool(
        editorial.get("human_review_required") is False or editorial.get("human_signoff") is True
    )

    # --- hook and scenes ----------------------------------------------
    scenes = package.get("scenes")
    if not isinstance(scenes, list):
        scenes = []
        add("scenes.type", "Scenes are a list", "FAIL", "scenes must be an array")
    else:
        add(
            "scenes.count",
            "Scene count is within the channel range",
            _status_ok(int(format_cfg["min_scenes"]) <= len(scenes) <= int(format_cfg["max_scenes"])),
            f"{len(scenes)} scenes (allowed {format_cfg['min_scenes']}-{format_cfg['max_scenes']})",
        )

    hook = package.get("hook") or {}
    hook_text = str(hook.get("text") or "")
    hook_duration = hook.get("duration_s")
    add(
        "hook.duration",
        "Hook lasts 1-3 seconds",
        _status_ok(
            isinstance(hook_duration, (int, float))
            and float(format_cfg["hook_min_s"]) <= float(hook_duration) <= float(format_cfg["hook_max_s"])
        ),
        f"duration={hook_duration!r}s",
    )
    add(
        "hook.text",
        "Hook is a short, concrete spoken line",
        _status_ok(_nonempty(hook_text, 8) and 3 <= word_count(hook_text) <= 18),
        f"{word_count(hook_text)} words: {hook_text!r}",
    )
    add(
        "hook.first_scene",
        "Hook is the first scene and matches its narration",
        _status_ok(
            bool(scenes)
            and scenes[0].get("id") == "s1"
            and normalise_whitespace(str(scenes[0].get("narration", ""))) == normalise_whitespace(hook_text)
            and abs(float(scenes[0].get("duration_s", -1)) - float(hook_duration or -2)) < 0.01
        ),
        "scene s1 must open at 0 and use the hook text/duration",
    )

    total_duration = 0.0
    cursor = 0.0
    scene_ids: set[str] = set()
    narrations: list[str] = []
    all_visual_text: list[str] = []
    for position, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("id") or f"scene-{position}")
        add(
            f"scene.{scene_id}.id",
            f"Scene {scene_id} has a unique id",
            _status_ok(scene_id not in scene_ids and bool(ID_RE.fullmatch(scene_id))),
            f"id={scene_id!r}",
        )
        scene_ids.add(scene_id)
        start = scene.get("start_s")
        duration = scene.get("duration_s")
        start_ok = isinstance(start, (int, float)) and abs(float(start) - cursor) <= 0.01
        add(
            f"scene.{scene_id}.timing",
            f"Scene {scene_id} starts where the previous scene ended",
            _status_ok(start_ok and isinstance(duration, (int, float)) and float(duration) > 0),
            f"start={start!r}, expected={round(cursor, 3)}, duration={duration!r}",
        )
        if isinstance(duration, (int, float)):
            total_duration += float(duration)
            cursor += float(duration)
        narration = str(scene.get("narration") or "")
        narrations.append(narration)
        add(
            f"scene.{scene_id}.narration",
            f"Scene {scene_id} has original narration",
            _status_ok(_nonempty(narration, 10) and not PLACEHOLDER_RE.search(narration)),
            f"{word_count(narration)} words",
        )
        if isinstance(duration, (int, float)) and float(duration) > 0:
            wps = word_count(narration) / float(duration)
            lower = 1.4 if float(duration) < 4 else float(editorial_cfg["min_words_per_second"])
            upper = 4.4 if float(duration) < 4 else float(editorial_cfg["max_words_per_second"])
            add(
                f"scene.{scene_id}.pace",
                f"Scene {scene_id} narration fits its duration",
                _status_ok(lower <= wps <= upper),
                f"{wps:.2f} words/s (allowed {lower:.2f}-{upper:.2f})",
            )
        visual = scene.get("visual") or {}
        description = str(visual.get("description") or "")
        subject = str(visual.get("subject") or "")
        motion = str(visual.get("motion") or "")
        framing = str(visual.get("framing") or "")
        continuity = str(visual.get("continuity") or "")
        avoid = visual.get("avoid") or []
        visual_text = f"{description} {subject} {motion}"
        all_visual_text.append(visual_text)
        add(
            f"scene.{scene_id}.visual",
            f"Scene {scene_id} has a specific visual instruction",
            _status_ok(
                _nonempty(description, 40)
                and _nonempty(subject, 3)
                and _nonempty(motion, 3)
                and _nonempty(continuity, 10)
                and "9:16" in framing
                and isinstance(avoid, list)
                and len(avoid) >= 2
            ),
            "description >=40 chars, subject/motion/continuity set, 9:16 framing, >=2 avoid notes",
        )
        banned_hits = _find_terms(visual_text, visual_cfg["banned_description_terms"])
        add(
            f"scene.{scene_id}.welfare",
            f"Scene {scene_id} does not request distress or aggression",
            _status_ok(not banned_hits),
            f"banned terms: {banned_hits}" if banned_hits else "no banned distress/aggression terms",
        )
        for required in ("text", "logo", "watermark"):
            if required in visual_text.lower():
                add(
                    f"scene.{scene_id}.artifact_risk",
                    f"Scene {scene_id} avoids generated {required} artifacts",
                    "FAIL",
                    f"visual instruction mentions {required!r}; move it to the negative prompt",
                )
        if not _nonempty(description, 40):
            add(
                f"scene.{scene_id}.visual_length",
                f"Scene {scene_id} visual description is long enough",
                "FAIL",
                f"{len(description)} chars (min 40)",
            )

    add(
        "scenes.unique_narration",
        "Scenes do not repeat the same narration",
        _status_ok(len({normalise_whitespace(text).lower() for text in narrations}) == len(narrations)),
        f"{len(narrations)} scene narrations",
    )
    target_duration = package.get("target_duration_s")
    add(
        "timing.total",
        "Scene durations sum to the target duration",
        _status_ok(
            isinstance(target_duration, (int, float))
            and abs(total_duration - float(target_duration)) <= 0.05
        ),
        f"sum={round(total_duration, 3)}s, target={target_duration!r}s",
    )
    add(
        "timing.channel",
        "Target duration is inside the channel range",
        _status_ok(
            isinstance(target_duration, (int, float))
            and float(format_cfg["min_duration_s"]) <= float(target_duration) <= float(format_cfg["max_duration_s"])
        ),
        f"target={target_duration!r}s (allowed {format_cfg['min_duration_s']}-{format_cfg['max_duration_s']})",
    )
    all_narration = " ".join(narrations)
    for pattern in editorial_cfg.get("forbidden_medical_patterns", []):
        if re.search(pattern, all_narration, flags=re.IGNORECASE):
            add(
                "narration.medical_claims",
                "Narration avoids veterinary advice language",
                "FAIL",
                f"matched forbidden pattern: {pattern!r}",
            )
    if not any(check.id == "narration.medical_claims" for check in result.checks):
        add(
            "narration.medical_claims",
            "Narration avoids veterinary advice language",
            "PASS",
            "no medical-advice patterns matched",
        )
    claim_phrase_hits = _find_terms(all_narration, editorial_cfg.get("forbidden_claim_phrases", []))
    add(
        "narration.overclaim",
        "Narration avoids unsupported certainty language",
        _status_ok(not claim_phrase_hits),
        f"matched: {claim_phrase_hits}" if claim_phrase_hits else "no overclaim phrases",
    )

    # --- visual policy -----------------------------------------------
    visual_policy = package.get("visual_policy") or {}
    add(
        "visual.policy",
        "Package carries a visual style, anatomy, welfare, and disclosure policy",
        _status_ok(
            all(
                _nonempty(visual_policy.get(key), 15)
                for key in ("style", "anatomy", "welfare", "disclosure")
            )
            and str(visual_policy.get("disclosure", "")).strip()
            == str(editorial_cfg["required_disclosure"]).strip()
        ),
        "style/anatomy/welfare/disclosure must be present and match channel policy",
    )
    add(
        "visual.negative_prompt",
        "Global negative prompt covers anatomy and welfare risks",
        _status_ok(
            _nonempty(visual_cfg.get("negative_prompt"), 40)
            and "extra limbs" in visual_cfg["negative_prompt"].lower()
            and "distress" in visual_cfg["negative_prompt"].lower()
        ),
        "channel negative prompt includes anatomy and distress controls",
    )

    # --- claims and research ------------------------------------------
    claims = package.get("claims") or []
    sources = research.get("sources") or []
    source_ids = [str(source.get("id") or "") for source in sources if isinstance(source, dict)]
    claim_ids = [str(claim.get("id") or "") for claim in claims if isinstance(claim, dict)]
    add(
        "claims.present",
        "Package states its evidence-backed claims",
        _status_ok(isinstance(claims, list) and len(claims) >= 1),
        f"{len(claims)} claims",
    )
    add(
        "claims.unique",
        "Claim ids are unique",
        _status_ok(len(claim_ids) == len(set(claim_ids)) and all(ID_RE.fullmatch(cid) for cid in claim_ids)),
        f"{len(claim_ids)} claim ids",
    )
    referenced_sources: set[str] = set()
    for claim in claims:
        claim_id = str(claim.get("id") or "?")
        refs = claim.get("source_ids") or []
        missing = [ref for ref in refs if ref not in source_ids]
        referenced_sources.update(ref for ref in refs if ref in source_ids)
        add(
            f"claim.{claim_id}.structure",
            f"Claim {claim_id} has text, evidence level, limits, and valid sources",
            _status_ok(
                _nonempty(claim.get("text"), 10)
                and _nonempty(claim.get("evidence_level"), 5)
                and _nonempty(claim.get("limits"), 10)
                and isinstance(refs, list)
                and refs
                and not missing
            ),
            f"source_ids={refs}, missing={missing}",
        )
    add(
        "claims.sources_used",
        "Every research source supports at least one claim",
        _status_ok(set(source_ids) == referenced_sources and bool(source_ids)),
        f"unused={sorted(set(source_ids) - referenced_sources)}, unknown={sorted(referenced_sources - set(source_ids))}",
    )

    add(
        "research.package_id",
        "Research record matches the package",
        _status_ok(research.get("package_id") == package_id),
        f"package_id={research.get('package_id')!r}",
    )
    verification = research.get("verification") or {}
    add(
        "research.verification",
        "Research record documents method and uncertainty",
        _status_ok(
            _parse_date(verification.get("researched_at")) is not None
            and _nonempty(verification.get("method"), 30)
            and _nonempty(verification.get("source_access"), 15)
            and _nonempty(verification.get("myth_or_anecdote"), 20)
            and isinstance(verification.get("uncertainties"), list)
            and len(verification["uncertainties"]) >= 1
        ),
        "researched_at, method, source_access, myth_or_anecdote, and uncertainties are required",
    )
    add(
        "research.question",
        "Research question matches the package",
        _status_ok(
            normalise_whitespace(str(research.get("question", ""))).lower()
            == normalise_whitespace(str(package.get("central_question", ""))).lower()
        ),
        "research.question must equal package.central_question",
    )
    add(
        "research.source_count",
        "Research uses at least one primary source",
        _status_ok(1 <= len(sources) <= 6),
        f"{len(sources)} sources",
    )
    add(
        "research.source_ids",
        "Source ids are unique and valid",
        _status_ok(
            len(source_ids) == len(set(source_ids))
            and all(ID_RE.fullmatch(source_id) for source_id in source_ids)
        ),
        f"{len(source_ids)} source ids",
    )

    allowed_domains = sources_config["allowed_domains"]
    banned_domains = sources_config["banned_domains"]
    today = date.today()
    for source in sources:
        if not isinstance(source, dict):
            add("research.source_shape", "Source records are objects", "FAIL", repr(source))
            continue
        source_id = str(source.get("id") or "?")
        url = str(source.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        allowed, banned = _domain_allowed(host, allowed_domains, banned_domains)
        tier = source.get("tier")
        accessed = _parse_date(source.get("accessed"))
        doi = str(source.get("doi") or "")
        pmid = str(source.get("pmid") or "")
        problems = []
        if not _nonempty(source.get("title"), 10):
            problems.append("title")
        if not isinstance(source.get("authors"), list) or not source["authors"]:
            problems.append("authors")
        if not isinstance(source.get("year"), int):
            problems.append("year")
        if tier not in sources_config["allowed_tiers"]:
            problems.append("tier")
        if source.get("verified") is not True:
            problems.append("verified flag")
        if not url.startswith("https://"):
            problems.append("https URL")
        if not allowed or banned:
            problems.append(f"allowed domain (host={host!r})")
        if not accessed or accessed > today:
            problems.append("accessed date")
        if not _nonempty(source.get("evidence"), 60):
            problems.append("evidence summary")
        if sources_config.get("require_source_limitations", True) and not _nonempty(
            source.get("limitations"), 30
        ):
            problems.append("limitations")
        if tier == 1 and not (doi or pmid):
            problems.append("DOI or PMID")
        if doi and not doi.startswith("10."):
            problems.append("DOI format")
        if pmid and not pmid.isdigit():
            problems.append("PMID format")
        add(
            f"research.source.{source_id}",
            f"Source {source_id} is verifiable and correctly cited",
            _status_ok(not problems),
            f"problems={problems}" if problems else f"{host}, tier {tier}, accessed {source.get('accessed')}",
        )

    claim_checks = research.get("claim_checks") or []
    checked_ids = [str(item.get("claim_id") or "") for item in claim_checks if isinstance(item, dict)]
    add(
        "research.claim_checks",
        "Every claim has a recorded verification verdict",
        _status_ok(set(checked_ids) == set(claim_ids) and len(checked_ids) == len(set(checked_ids))),
        f"checked={checked_ids}, claims={claim_ids}",
    )
    for item in claim_checks:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or "?")
        add(
            f"research.claim_check.{claim_id}",
            f"Claim check {claim_id} has a valid verdict and notes",
            _status_ok(
                item.get("verdict") in {"supported", "partially_supported", "interpretation"}
                and _nonempty(item.get("notes"), 20)
            ),
            f"verdict={item.get('verdict')!r}",
        )

    # --- metadata and subtitles --------------------------------------
    if metadata is None:
        add("metadata.present", "Metadata is generated", "FAIL", "metadata.json missing")
    else:
        metadata_issues = validate_metadata(metadata, package, research, channel)
        add(
            "metadata.valid",
            "YouTube metadata is complete and policy-compliant",
            _status_ok(not metadata_issues),
            "; ".join(metadata_issues) if metadata_issues else "metadata checks passed",
        )

    if cues is None:
        add("subtitles.present", "Subtitles are generated", "FAIL", "subtitles.srt missing")
    else:
        expected = " ".join(str(scene.get("narration", "")) for scene in scenes)
        subtitle_issues = validate_cues(
            cues,
            total_duration_s=float(target_duration or 0),
            max_line_chars=int(format_cfg["subtitle_max_line_chars"]),
            max_lines=int(format_cfg["subtitle_max_lines"]),
            max_chars_per_second=float(format_cfg["subtitle_max_chars_per_second"]),
            expected_text=expected,
        )
        add(
            "subtitles.valid",
            "Subtitles are synchronized, readable, and complete",
            _status_ok(not subtitle_issues),
            "; ".join(subtitle_issues) if subtitle_issues else str(cue_stats(cues)),
        )
        if srt_text is not None:
            from .subtitles import parse_srt

            try:
                parsed = parse_srt(srt_text)
                roundtrip_ok = [cue.to_dict() for cue in parsed] == [cue.to_dict() for cue in cues]
                problem = "SRT round-trip mismatch"
            except PipelineError as exc:
                roundtrip_ok = False
                problem = str(exc)
            add(
                "subtitles.srt_roundtrip",
                "subtitles.srt parses back to the generated cues",
                _status_ok(roundtrip_ok),
                "round-trip OK" if roundtrip_ok else problem,
            )

    # --- deduplication ------------------------------------------------
    if history is None:
        add("history.dedup", "Topic history duplicate check", "SKIP", "no history store supplied")
    else:
        matches = history.check_candidate(
            package_id=package_id,
            slug=package_id,
            title=str(package.get("title", "")),
            central_question=str(package.get("central_question", "")),
            central_fact=str(package.get("central_fact", "")),
            source_ids=source_ids,
            batch_id=batch_id,
        )
        fail_matches = [match for match in matches if match.severity == "FAIL"]
        warn_matches = [match for match in matches if match.severity == "WARN"]
        status = "FAIL" if fail_matches else ("WARN" if warn_matches else "PASS")
        detail = (
            "; ".join(f"{match.severity}: {match.reason} -> {match.existing_id}" for match in matches)
            if matches
            else "no duplicate or near-duplicate topic found"
        )
        add("history.dedup", "Topic history duplicate check", status, detail)

    # --- rendered artifact, if one exists ----------------------------
    render_path = None
    request_payload = None
    declared_render = ""
    request_path = folder / "viewmade-request.json"
    if request_path.is_file():
        try:
            request_payload = read_json(request_path)
            rendered = request_payload.get("render_path")
            if rendered:
                declared_render = str(rendered)
                candidate = Path(declared_render)
                if not candidate.is_absolute():
                    candidate = folder.parents[2] / candidate
                if candidate.is_file():
                    render_path = candidate
        except (PipelineError, OSError, ValueError):
            render_path = None
    if render_path is None:
        fallback = folder / "render.mp4"
        if fallback.is_file():
            render_path = fallback
    request_complete = (
        isinstance(request_payload, dict)
        and str(request_payload.get("status") or "").upper() == "COMPLETE"
    )
    if render_path is not None and render_path.is_file():
        from .media_probe import validate_render

        info, issues = validate_render(
            render_path,
            min_duration_s=float(channel["format"]["min_duration_s"]),
            max_duration_s=float(channel["format"]["max_duration_s"]),
            width=int(channel["format"]["width"]),
            height=int(channel["format"]["height"]),
        )
        result.render_status = "PASS" if not issues else "FAIL"
        add(
            "render.artifact",
            "Rendered MP4 is valid, vertical, and has audio",
            _status_ok(not issues),
            "; ".join(issues) if issues else str(info.to_dict() if info else "verified"),
        )
    elif declared_render or request_complete:
        # The request claims a render that is not on disk. Reporting SKIP here
        # would hide a lost/corrupt artifact and hand the package a false PASS.
        result.render_status = "FAIL"
        add(
            "render.artifact",
            "Rendered MP4 is valid, vertical, and has audio",
            "FAIL",
            f"request declares {declared_render or 'a completed render'} "
            "but the file is missing",
        )
    else:
        result.render_status = "NOT_RENDERED"
        add(
            "render.artifact",
            "Rendered MP4",
            "SKIP",
            "not rendered yet; live ViewMade rendering is a separate gated stage",
        )

    provider_package = (
        request_payload.get("provider_package")
        if isinstance(request_payload, dict)
        else None
    )
    if render_path is not None and render_path.is_file():
        provider_package = provider_package if isinstance(provider_package, dict) else {}
        source_urls = [
            str(source.get("url") or "").strip()
            for source in provider_package.get("sources") or []
            if str(source.get("url") or "").strip()
        ]
        attributions = [
            str(item).strip()
            for item in provider_package.get("attributions") or []
            if str(item).strip()
        ]
        description = str((metadata or {}).get("description") or "")
        missing_urls = [url for url in source_urls if url not in description]
        if not source_urls:
            add(
                "render.attribution",
                "Rendered real-footage video credits every provider source",
                "FAIL",
                "rendered package has no provider source URLs",
            )
        elif missing_urls:
            add(
                "render.attribution",
                "Rendered real-footage video credits every provider source",
                "FAIL",
                "metadata description is missing footage source URLs: "
                + ", ".join(missing_urls),
            )
        elif not attributions:
            add(
                "render.attribution",
                "Rendered real-footage video credits every provider source",
                "WARN",
                "source URLs are credited, but the provider returned no attribution lines",
            )
        else:
            add(
                "render.attribution",
                "Rendered real-footage video credits every provider source",
                "PASS",
                f"{len(attributions)} attribution lines and {len(source_urls)} source URLs credited",
            )

        review = request_payload.get("editorial_review") if isinstance(request_payload, dict) else None
        review = review if isinstance(review, dict) else {}
        review_status = str(review.get("status") or "PENDING").upper()
        reason = str(review.get("reason") or "").strip()
        if review_status == "APPROVED":
            add(
                "render.editorial_review",
                "Editorial review disposition is recorded",
                "PASS",
                "APPROVED",
            )
        elif review_status == "REJECTED":
            add(
                "render.editorial_review",
                "Editorial review disposition is recorded",
                "PASS",
                "REJECTED: " + (reason or "no reason recorded"),
            )
        else:
            add(
                "render.editorial_review",
                "Editorial review disposition is recorded",
                "WARN",
                "no editorial review recorded; the render is not publishable",
            )
    else:
        add(
            "render.attribution",
            "Rendered real-footage video credits every provider source",
            "SKIP",
            "not rendered yet",
        )
        add(
            "render.editorial_review",
            "Editorial review disposition is recorded",
            "SKIP",
            "not rendered yet",
        )

    # publish_ready is only true when there is a real render and human signoff.
    result.publish_ready = result.publish_ready and result.render_status == "PASS" and result.status != "FAIL"
    if artifact_files:
        add(
            "artifacts.hashes",
            "Generated artifacts were hashed for integrity",
            "PASS",
            f"{len(artifact_files)} files",
        )
    return result


def write_qa_report(path: Path, result: QAResult, *, artifacts: dict[str, str] | None = None) -> Path:
    return write_json(path, result.to_dict(artifacts=artifacts))


def summarize_results(results: Iterable[QAResult]) -> dict:
    results = list(results)
    statuses = [result.status for result in results]
    overall = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
    return {
        "packages": len(results),
        "status": overall,
        "pass": statuses.count("PASS"),
        "warn": statuses.count("WARN"),
        "fail": statuses.count("FAIL"),
        "render_status": {
            result.package_id: result.render_status for result in results
        },
        "publish_ready": all(result.publish_ready for result in results) if results else False,
    }
