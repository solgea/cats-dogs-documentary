"""Small, dependency-free helpers shared by the pipeline.

The emphasis is on deterministic output: stable slugs, stable JSON formatting,
stable tokenisation for duplicate detection, and atomic writes so a failed
build never leaves half-written metadata behind.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class PipelineError(RuntimeError):
    """A user-facing, expected failure. The CLI prints it without a traceback."""


# --- project discovery ----------------------------------------------------


def find_project_root(start: str | Path | None = None) -> Path:
    """Find the directory containing config/channel.json.

    ``CDDOCS_ROOT`` wins when set. Otherwise walk upward from *start* (or the
    current directory). A missing project is a hard error rather than a silent
    fallback to an unrelated working directory.
    """
    override = os.environ.get("CDDOCS_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
        if (root / "config" / "channel.json").is_file():
            return root
        raise PipelineError(f"CDDOCS_ROOT does not contain config/channel.json: {root}")

    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "config" / "channel.json").is_file():
            return candidate
    raise PipelineError(
        "Could not find the project root (config/channel.json). "
        "Run from inside cats-dogs-documentary or set CDDOCS_ROOT."
    )


# --- files and JSON -------------------------------------------------------


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Write UTF-8 text atomically with LF line endings."""
    target = Path(path)
    ensure_dir(target.parent)
    payload = text.replace("\r\n", "\n").replace("\r", "\n")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


def read_json(path: str | Path) -> Any:
    target = Path(path)
    try:
        with target.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise PipelineError(f"JSON file not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {target}: {exc}") from exc


def write_json(path: str | Path, data: Any, *, indent: int = 2) -> Path:
    text = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False) + "\n"
    return atomic_write_text(path, text)


def write_json_if_changed(path: str | Path, data: Any, *, indent: int = 2) -> bool:
    """Return True when the file changed; avoids noisy rebuilds."""
    text = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False) + "\n"
    target = Path(path)
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError:
            existing = None
        if existing == text:
            return False
    atomic_write_text(target, text)
    return True


# --- text -----------------------------------------------------------------


def normalise_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str, *, max_length: int = 80) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        raise PipelineError(f"cannot create a slug from {text!r}")
    return slug[:max_length].rstrip("-")


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)?", text))


_STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those of in on at to for from by
    with without into over under about as is are was were be been being do does did
    doing have has had having it its it's their they them we our you your he she his
    her i me my mine not no nor so very can could may might will would should just
    also more most much many few some any each every all both either neither because
    while when where why how what which who whom whose there here one two three
    """.split()
)


def normalise_for_dedup(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    folded = folded.lower().replace("\u2019", "'")
    return re.sub(r"[^a-z0-9' ]+", " ", folded)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9']+", normalise_for_dedup(text))
        if len(token) >= 3 and token not in _STOPWORDS
    ]


def token_set(text: str) -> set[str]:
    return set(tokenize(text))


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(left: str, right: str) -> float:
    return jaccard(token_set(left), token_set(right))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- time -----------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    return utc_now().date().isoformat()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def format_clock(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 60}:{total % 60:02d}"


def safe_relative(path: str | Path, root: str | Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)
