"""Offline media artifact inspection using only the standard library.

The pipeline never marks a render COMPLETE on a file it cannot parse. These
functions read documented container headers (PNG, JPEG, WAV, ISO-BMFF/MP4) and
report dimensions, duration, audio presence, and structural problems.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MediaInfo:
    format: str
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bits_per_sample: int | None = None
    has_audio: bool | None = None

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "ok": self.ok,
            "problems": self.problems,
            "width": self.width,
            "height": self.height,
            "duration_s": self.duration_s,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bits_per_sample": self.bits_per_sample,
            "has_audio": self.has_audio,
        }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- images ---------------------------------------------------------------


def probe_image(data: bytes) -> MediaInfo:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return MediaInfo(format="png", width=width, height=height)
    if data[:2] == b"\xff\xd8":
        info = MediaInfo(format="jpeg")
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                break
            marker = data[index + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            if index + 4 > len(data):
                break
            (segment_length,) = struct.unpack(">H", data[index + 2 : index + 4])
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                if index + 9 <= len(data):
                    info.height, info.width = struct.unpack(">HH", data[index + 5 : index + 9])
                    break
            if segment_length <= 0:
                break
            index += 2 + segment_length
        if not info.width or not info.height:
            info.ok = False
            info.problems.append("JPEG dimensions not found")
        return info
    return MediaInfo(format="unknown", ok=False, problems=["not a PNG or JPEG header"])


# --- audio ----------------------------------------------------------------


def probe_wav(data: bytes) -> MediaInfo:
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return MediaInfo(format="unknown", ok=False, problems=["not a RIFF/WAVE header"])
    info = MediaInfo(format="wav")
    index = 12
    byte_rate: int | None = None
    while index + 8 <= len(data):
        chunk_id = data[index : index + 4]
        (chunk_size,) = struct.unpack("<I", data[index + 4 : index + 8])
        body = data[index + 8 : index + 8 + chunk_size]
        if chunk_id == b"fmt " and chunk_size >= 16:
            (
                _audio_format,
                channels,
                sample_rate,
                byte_rate,
                _block_align,
                bits,
            ) = struct.unpack("<HHIIHH", body[:16])
            info.channels = channels
            info.sample_rate = sample_rate
            info.bits_per_sample = bits
        elif chunk_id == b"data":
            if byte_rate:
                info.duration_s = round(chunk_size / byte_rate, 3)
            break
        index += 8 + chunk_size + (chunk_size & 1)
        if chunk_size == 0x7FFFFFFF:
            break
    if info.sample_rate is None:
        info.ok = False
        info.problems.append("missing fmt chunk")
    if info.duration_s is None:
        info.ok = False
        info.problems.append("missing data chunk size")
    return info


# --- MP4 / ISO base media -------------------------------------------------


def _walk_boxes(data: bytes, start: int, end: int) -> list[tuple[int, int, bytes]]:
    boxes: list[tuple[int, int, bytes]] = []
    index = start
    while index + 8 <= end:
        size = struct.unpack(">I", data[index : index + 4])[0]
        box_type = data[index + 4 : index + 8]
        header = 8
        if size == 1:
            if index + 16 > end:
                break
            size = struct.unpack(">Q", data[index + 8 : index + 16])[0]
            header = 16
        elif size == 0:
            size = end - index
        if size < header:
            break
        if index + size > end:
            size = end - index
        boxes.append((index, size, box_type))
        if size <= 0:
            break
        index += size
    return boxes


def _find(boxes: list[tuple[int, int, bytes]], box_type: bytes) -> tuple[int, int, bytes] | None:
    for box in boxes:
        if box[2] == box_type:
            return box
    return None


def _has_audio_handler(data: bytes, start: int, end: int, depth: int = 0) -> bool:
    if depth > 5:
        return False
    for box_start, box_size, box_type in _walk_boxes(data, start, end):
        if box_type == b"hdlr":
            body = data[box_start + 8 : box_start + box_size]
            if len(body) >= 12 and body[8:12] == b"soun":
                return True
        if box_type in {b"moov", b"trak", b"mdia", b"minf", b"stbl"}:
            if _has_audio_handler(data, box_start + 8, box_start + box_size, depth + 1):
                return True
    return False


def probe_video(data: bytes) -> MediaInfo:
    if len(data) < 12 or data[4:8] != b"ftyp":
        return MediaInfo(format="unknown", ok=False, problems=["no ftyp box - not an MP4"])
    info = MediaInfo(format="mp4")
    top = _walk_boxes(data, 0, len(data))
    moov = _find(top, b"moov")
    if moov is None:
        info.ok = False
        info.problems.append("no moov box found")
        return info
    moov_start, moov_size, _ = moov
    moov_body = data[moov_start + 8 : moov_start + moov_size]
    children = _walk_boxes(moov_body, 0, len(moov_body))
    mvhd = _find(children, b"mvhd")
    if mvhd is not None:
        box_start, box_size, _ = mvhd
        body = moov_body[box_start + 8 : box_start + box_size]
        version = body[0] if body else -1
        if version == 0 and len(body) >= 20:
            timescale, duration = struct.unpack(">II", body[12:20])
        elif version == 1 and len(body) >= 28:
            timescale, duration = struct.unpack(">II", body[20:28])
        else:
            timescale, duration = 0, 0
        if timescale > 0 and duration > 0:
            info.duration_s = round(duration / timescale, 3)
    if info.duration_s is None:
        info.ok = False
        info.problems.append("no mvhd duration found")

    for box_start, box_size, box_type in children:
        if box_type != b"trak":
            continue
        trak_body = moov_body[box_start + 8 : box_start + box_size]
        trak_children = _walk_boxes(trak_body, 0, len(trak_body))
        tkhd = _find(trak_children, b"tkhd")
        if tkhd is None:
            continue
        t_start, t_size, _ = tkhd
        body = trak_body[t_start + 8 : t_start + t_size]
        if len(body) < 8:
            continue
        width_fixed, height_fixed = struct.unpack(">II", body[-8:])
        width = width_fixed / 65536.0
        height = height_fixed / 65536.0
        if width > 1 and height > 1:
            info.width = int(round(width))
            info.height = int(round(height))
            break

    info.has_audio = _has_audio_handler(data, moov_start, moov_start + moov_size)
    if not info.has_audio:
        info.ok = False
        info.problems.append("no audio track found in moov")
    return info


# --- validation -----------------------------------------------------------


def aspect_ratio(width: int | None, height: int | None) -> float | None:
    if not width or not height:
        return None
    return round(width / height, 4)


def check_aspect(
    width: int | None,
    height: int | None,
    target: str = "9:16",
    *,
    tolerance: float = 0.02,
) -> tuple[str, str]:
    ratio = aspect_ratio(width, height)
    if ratio is None:
        return "FAIL", "dimensions unknown"
    numerator, denominator = target.split(":")
    target_ratio = float(numerator) / float(denominator)
    if abs(ratio - target_ratio) / target_ratio <= tolerance:
        return "PASS", f"{width}x{height} matches {target} within {tolerance:.0%}"
    return "FAIL", f"{width}x{height} is {ratio}, target {target} is {round(target_ratio, 4)}"


def _sniff(data: bytes) -> str | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if len(data) > 11 and data[4:8] == b"ftyp":
        return "mp4"
    if data[:1] in (b"{", b"["):
        return "json"
    return None


def validate_file(
    path: str | Path,
    *,
    expect_format: str | None = None,
    min_bytes: int = 1024,
    aspect: str | None = None,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    expected_width: int | None = None,
    expected_height: int | None = None,
    require_audio: bool = False,
) -> tuple[MediaInfo | None, list[str]]:
    target = Path(path)
    issues: list[str] = []
    if not target.is_file():
        return None, [f"artifact missing: {target}"]
    data = target.read_bytes()
    if len(data) < min_bytes:
        return None, [f"artifact is suspiciously small ({len(data)} bytes): {target}"]

    sniffed: MediaInfo | None = None
    kind = expect_format or _sniff(data)
    if kind in ("png", "jpeg"):
        sniffed = probe_image(data)
    elif kind == "wav":
        sniffed = probe_wav(data)
    elif kind == "mp4":
        sniffed = probe_video(data)
    else:
        return None, [f"unknown artifact type for {target}"]

    issues.extend(sniffed.problems)
    if expect_format and sniffed.format != expect_format:
        issues.append(f"expected {expect_format} artifact, got {sniffed.format}")
    if aspect:
        status, detail = check_aspect(sniffed.width, sniffed.height, aspect)
        if status == "FAIL":
            issues.append(f"aspect ratio: {detail}")
    if min_duration_s is not None and (sniffed.duration_s or 0) < min_duration_s:
        issues.append(f"duration {sniffed.duration_s}s is below minimum {min_duration_s}s")
    if max_duration_s is not None and (sniffed.duration_s or 0) > max_duration_s:
        issues.append(f"duration {sniffed.duration_s}s is above maximum {max_duration_s}s")
    if expected_width and sniffed.width != expected_width:
        issues.append(f"width {sniffed.width} does not match required {expected_width}")
    if expected_height and sniffed.height != expected_height:
        issues.append(f"height {sniffed.height} does not match required {expected_height}")
    if require_audio and sniffed.has_audio is not True:
        issues.append("artifact has no verified audio track")
    return sniffed, issues


def validate_render(
    path: str | Path,
    *,
    min_duration_s: float = 30,
    max_duration_s: float = 60,
    width: int = 1080,
    height: int = 1920,
    min_bytes: int = 100_000,
) -> tuple[MediaInfo | None, list[str]]:
    return validate_file(
        path,
        expect_format="mp4",
        min_bytes=min_bytes,
        aspect="9:16",
        min_duration_s=min_duration_s,
        max_duration_s=max_duration_s,
        expected_width=width,
        expected_height=height,
        require_audio=True,
    )


def json_artifact(
    data: bytes, *, expect_keys: tuple[str, ...] = ()
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"invalid JSON artifact: {exc}"]
    if not isinstance(parsed, dict):
        return None, ["JSON artifact is not an object"]
    missing = [key for key in expect_keys if key not in parsed]
    if missing:
        return parsed, [f"missing required keys: {missing}"]
    return parsed, []
