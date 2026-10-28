"""Deterministic subtitle generation and SRT validation.

Cues are derived from the narration itself. Timing is allocated by spoken
character count inside each scene, so the last cue of a scene ends exactly at
the scene boundary. There are no guessed word timestamps and no external
speech-to-text dependency.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .util import PipelineError, atomic_write_text, normalise_whitespace


@dataclass(frozen=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def start_s(self) -> float:
        return self.start_ms / 1000

    @property
    def end_s(self) -> float:
        return self.end_ms / 1000

    @property
    def duration_s(self) -> float:
        return max(0.0, (self.end_ms - self.start_ms) / 1000)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_s": round(self.start_s, 3),
            "end_s": round(self.end_s, 3),
            "text": self.text,
        }


def _best_two_line_split(text: str, max_line_chars: int) -> tuple[str, str] | None:
    """Find a balanced two-line split where both lines fit the limit."""
    words = normalise_whitespace(text).split()
    if len(text) <= max_line_chars:
        return None
    best: tuple[tuple[int, int], str, str] | None = None
    for index in range(1, len(words)):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        if len(left) <= max_line_chars and len(right) <= max_line_chars:
            score = (max(len(left), len(right)), abs(len(left) - len(right)))
            if best is None or score < best[0]:
                best = (score, left, right)
    if best is None:
        return None
    return best[1], best[2]


def wrap_two_lines(text: str, max_line_chars: int = 42) -> str:
    """Wrap one cue into at most two centered subtitle lines."""
    cleaned = normalise_whitespace(text)
    if not cleaned:
        return ""
    if len(cleaned) <= max_line_chars:
        return cleaned
    split = _best_two_line_split(cleaned, max_line_chars)
    if split is not None:
        return f"{split[0]}\n{split[1]}"
    # Fallback: preserve every word. Validation will flag an overlong line
    # rather than silently dropping text.
    words = cleaned.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_line_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = word
        else:
            lines.append(word[:max_line_chars])
            current = word[max_line_chars:]
    if current:
        lines.append(current)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


def _sentence_atoms(text: str) -> list[str]:
    cleaned = normalise_whitespace(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part for part in parts if part]


def _chunk_prefix_lengths(words: list[str]) -> list[int]:
    prefix = [0]
    for word in words:
        prefix.append(prefix[-1] + len(word) + 1)
    return prefix


def _chunk_length(prefix: list[int], start: int, end: int) -> int:
    return prefix[end] - prefix[start] - 1


def _balanced_chunks(
    sentence: str,
    *,
    max_chars: int,
    max_line_chars: int,
) -> list[str]:
    """Split one sentence into balanced chunks that each fit two lines."""
    words = sentence.split()
    if not words:
        return []
    prefix = _chunk_prefix_lengths(words)
    total = _chunk_length(prefix, 0, len(words))
    limit = float("inf")

    def fits(start: int, end: int) -> bool:
        length = _chunk_length(prefix, start, end)
        if length <= 0 or length > max_chars:
            return False
        if length <= max_line_chars:
            return True
        text = " ".join(words[start:end])
        return _best_two_line_split(text, max_line_chars) is not None

    for count in range(1, len(words) + 1):
        target = total / count
        dp = [[limit] * (len(words) + 1) for _ in range(count + 1)]
        previous = [[-1] * (len(words) + 1) for _ in range(count + 1)]
        dp[0][0] = 0.0
        for used in range(1, count + 1):
            for end in range(1, len(words) + 1):
                for start in range(used - 1, end):
                    if dp[used - 1][start] == limit:
                        continue
                    if not fits(start, end):
                        continue
                    length = _chunk_length(prefix, start, end)
                    cost = dp[used - 1][start] + (length - target) ** 2
                    if cost < dp[used][end]:
                        dp[used][end] = cost
                        previous[used][end] = start
        if dp[count][len(words)] == limit:
            continue
        chunks: list[str] = []
        end = len(words)
        for used in range(count, 0, -1):
            start = previous[used][end]
            if start < 0:
                raise PipelineError("subtitle chunk reconstruction failed")
            chunks.append(" ".join(words[start:end]))
            end = start
        chunks.reverse()
        return chunks
    raise PipelineError(
        f"cannot split narration into readable subtitle cues: {sentence!r}"
    )


def split_into_cues(text: str, *, max_chars: int = 84) -> list[str]:
    """Split narration into sentence-based, subtitle-sized chunks.

    Every cue stays within ``max_chars`` and can be wrapped into at most two
    lines. Sentences are not merged across boundaries, which avoids orphaned
    tails such as a single trailing word.
    """
    line_limit = max(1, max_chars // 2)
    chunks: list[str] = []
    for sentence in _sentence_atoms(text):
        if len(sentence) <= max_chars and (
            len(sentence) <= line_limit
            or _best_two_line_split(sentence, line_limit) is not None
        ):
            chunks.append(sentence)
        else:
            chunks.extend(
                _balanced_chunks(sentence, max_chars=max_chars, max_line_chars=line_limit)
            )
    return [chunk for chunk in chunks if chunk]


def cues_for_scene(
    narration: str,
    *,
    start_s: float,
    duration_s: float,
    max_line_chars: int = 42,
) -> list[tuple[float, float, str]]:
    chunks = split_into_cues(narration, max_chars=max_line_chars * 2)
    if not chunks:
        return []
    weights = [max(1, len(chunk)) for chunk in chunks]
    total_weight = sum(weights)
    result: list[tuple[float, float, str]] = []
    cursor = start_s
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        if index == len(chunks) - 1:
            end = start_s + duration_s
        else:
            share = duration_s * (weight / total_weight)
            end = cursor + share
        # Keep millisecond precision and a positive duration.
        start_ms = int(round(cursor * 1000))
        end_ms = int(round(end * 1000))
        if end_ms <= start_ms:
            end_ms = start_ms + 250
        if index == len(chunks) - 1:
            end_ms = int(round((start_s + duration_s) * 1000))
        result.append((start_ms / 1000, end_ms / 1000, wrap_two_lines(chunk, max_line_chars)))
        cursor = end_ms / 1000
    return result


def build_cues(
    scenes: Iterable[dict],
    *,
    total_duration_s: float,
    max_line_chars: int = 42,
) -> list[Cue]:
    raw: list[tuple[float, float, str]] = []
    for scene in scenes:
        narration = scene.get("narration", "")
        start = float(scene.get("start_s", 0))
        duration = float(scene.get("duration_s", 0))
        if duration <= 0:
            raise PipelineError(f"scene {scene.get('id')!r} has non-positive duration")
        raw.extend(
            cues_for_scene(
                narration,
                start_s=start,
                duration_s=duration,
                max_line_chars=max_line_chars,
            )
        )
    if not raw:
        raise PipelineError("cannot build subtitles: no narration")
    raw.sort(key=lambda item: item[0])
    cues: list[Cue] = []
    for index, (start, end, text) in enumerate(raw, start=1):
        start_ms = int(round(start * 1000))
        end_ms = int(round(end * 1000))
        if end_ms > int(round(total_duration_s * 1000)) + 1:
            end_ms = int(round(total_duration_s * 1000))
        cues.append(Cue(index=index, start_ms=start_ms, end_ms=end_ms, text=text))
    return cues


def _format_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def format_srt(cues: Iterable[Cue]) -> str:
    blocks: list[str] = []
    for cue in cues:
        blocks.append(
            f"{cue.index}\n{_format_timestamp(cue.start_ms)} --> {_format_timestamp(cue.end_ms)}\n{cue.text}\n"
        )
    return "\n".join(blocks)


def write_srt(path: str | Path, cues: Iterable[Cue]) -> Path:
    return atomic_write_text(path, format_srt(cues))


_TIMESTAMP_RE = re.compile(
    r"^(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})\s+-->\s+"
    r"(?P<h2>\d{2}):(?P<m2>\d{2}):(?P<s2>\d{2}),(?P<ms2>\d{3})$"
)


def _parse_timestamp(match: re.Match[str], prefix: str = "") -> int:
    return (
        int(match.group(f"h{prefix}")) * 3_600_000
        + int(match.group(f"m{prefix}")) * 60_000
        + int(match.group(f"s{prefix}")) * 1000
        + int(match.group(f"ms{prefix}"))
    )


def parse_srt(text: str) -> list[Cue]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []
    cues: list[Cue] = []
    for block in re.split(r"\n{2,}", cleaned):
        lines = block.split("\n")
        if len(lines) < 3:
            raise PipelineError(f"malformed SRT block: {block!r}")
        try:
            index = int(lines[0].strip())
        except ValueError as exc:
            raise PipelineError(f"malformed SRT cue number: {lines[0]!r}") from exc
        match = _TIMESTAMP_RE.match(lines[1].strip())
        if not match:
            raise PipelineError(f"malformed SRT timestamp: {lines[1]!r}")
        body = "\n".join(lines[2:]).strip()
        if not body:
            raise PipelineError(f"empty SRT cue {index}")
        cues.append(
            Cue(
                index=index,
                start_ms=_parse_timestamp(match),
                end_ms=_parse_timestamp(match, "2"),
                text=body,
            )
        )
    return cues


def cue_text(cues: Iterable[Cue]) -> str:
    return normalise_whitespace(" ".join(cue.text.replace("\n", " ") for cue in cues))


def validate_cues(
    cues: list[Cue],
    *,
    total_duration_s: float,
    max_line_chars: int = 42,
    max_lines: int = 2,
    max_chars_per_second: float = 23.0,
    expected_text: str | None = None,
) -> list[str]:
    issues: list[str] = []
    if not cues:
        return ["subtitles contain no cues"]
    previous_end = 0
    for position, cue in enumerate(cues, start=1):
        if cue.index != position:
            issues.append(f"cue numbering is not contiguous at position {position}")
        if cue.start_ms < 0:
            issues.append(f"cue {cue.index} starts before zero")
        if cue.end_ms <= cue.start_ms:
            issues.append(f"cue {cue.index} has non-positive duration")
        if cue.start_ms + 1 < previous_end:
            issues.append(f"cue {cue.index} overlaps the previous cue")
        previous_end = cue.end_ms
        lines = cue.text.split("\n")
        if len(lines) > max_lines:
            issues.append(f"cue {cue.index} has {len(lines)} lines (max {max_lines})")
        for line in lines:
            if len(line) > max_line_chars:
                issues.append(
                    f"cue {cue.index} line is {len(line)} chars (max {max_line_chars}): {line!r}"
                )
        if cue.duration_s < 0.55:
            issues.append(f"cue {cue.index} is only {cue.duration_s:.2f}s on screen")
        cps = len(cue.text.replace("\n", " ")) / max(cue.duration_s, 0.001)
        if cps > max_chars_per_second:
            issues.append(f"cue {cue.index} reads at {cps:.1f} chars/s (max {max_chars_per_second})")
    if cues[0].start_ms > 50:
        issues.append(f"first cue starts at {cues[0].start_s:.2f}s instead of 0")
    if abs(cues[-1].end_s - total_duration_s) > 0.15:
        issues.append(
            f"last cue ends at {cues[-1].end_s:.2f}s but video is {total_duration_s:.2f}s"
        )
    if expected_text is not None:
        expected = normalise_whitespace(expected_text)
        actual = cue_text(cues)
        if expected != actual:
            # Token comparison gives a useful message without being brittle
            # about punctuation introduced by wrapping.
            expected_words = re.findall(r"[A-Za-z0-9']+", expected.lower())
            actual_words = re.findall(r"[A-Za-z0-9']+", actual.lower())
            if expected_words != actual_words:
                issues.append("subtitle text does not match the scene narration")
    return issues


def cue_stats(cues: list[Cue]) -> dict:
    if not cues:
        return {"cues": 0, "total_duration_s": 0.0, "max_chars_per_second": 0.0}
    cps = [
        len(cue.text.replace("\n", " ")) / max(cue.duration_s, 0.001) for cue in cues
    ]
    return {
        "cues": len(cues),
        "total_duration_s": round(cues[-1].end_s, 3),
        "max_chars_per_second": round(max(cps), 2),
        "mean_cue_duration_s": round(
            sum(cue.duration_s for cue in cues) / len(cues), 2
        ),
    }


def fill_target_duration(cues: list[Cue], target_s: float) -> list[Cue]:
    """Stretch the final cue to a target duration (used only for explicit re-cuts)."""
    if not cues:
        return cues
    if target_s <= cues[-1].end_s:
        return cues
    final = cues[-1]
    return [
        *cues[:-1],
        Cue(
            index=final.index,
            start_ms=final.start_ms,
            end_ms=int(round(target_s * 1000)),
            text=final.text,
        ),
    ]


def split_evenly(text: str, count: int) -> list[str]:
    """Testing helper: split text into roughly equal word groups."""
    words = text.split()
    if count <= 0:
        return []
    size = max(1, math.ceil(len(words) / count))
    return [" ".join(words[index : index + size]) for index in range(0, len(words), size)]
