"""Dependency-free image, audio, MP4, and JSON artifact inspection."""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

try:
    from ._support import ROOT  # noqa: F401
except ImportError:  # pragma: no cover
    from _support import ROOT  # noqa: F401

from cddocs.media_probe import (
    check_aspect,
    json_artifact,
    probe_image,
    probe_video,
    probe_wav,
    validate_file,
    validate_render,
)


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + box_type + payload


def _mp4(
    *,
    width: int = 1080,
    height: int = 1920,
    duration_s: float = 45.0,
    audio: bool = True,
) -> bytes:
    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 0x200) + b"isomiso2mp41")
    mvhd_body = b"\x00\x00\x00\x00" + struct.pack(
        ">IIII", 0, 0, 1000, int(duration_s * 1000)
    )
    tkhd_body = (
        b"\x00\x00\x00\x00"
        + b"\x00" * 76
        + struct.pack(">II", width << 16, height << 16)
    )
    trak_body = _box(b"tkhd", tkhd_body)
    if audio:
        handler = (
            b"\x00\x00\x00\x00"
            + b"\x00" * 4
            + b"soun"
            + b"\x00" * 12
            + b"SoundHandler\x00"
        )
        trak_body += _box(b"mdia", _box(b"hdlr", handler))
    moov = _box(b"moov", _box(b"mvhd", mvhd_body) + _box(b"trak", trak_body))
    padding = max(0, 120_000 - len(ftyp) - len(moov) - 8)
    return ftyp + moov + _box(b"free", b"\x00" * padding)


def _png(width: int = 1080, height: int = 1920) -> bytes:
    header = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
    )
    return header + b"\x00" * 2048


def _jpeg(width: int = 1080, height: int = 1920) -> bytes:
    app0_payload = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    app0 = b"\xff\xe0" + struct.pack(">H", len(app0_payload) + 2) + app0_payload
    sof_payload = (
        b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03"
        + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    sof = b"\xff\xc0" + struct.pack(">H", len(sof_payload) + 2) + sof_payload
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9" + b"\x00" * 2048


def _riff_chunk(chunk_id: bytes, payload: bytes) -> bytes:
    return chunk_id + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) % 2 else b"")


def _wav(seconds: int = 1) -> bytes:
    sample_rate = 16_000
    bits = 16
    channels = 1
    byte_rate = sample_rate * channels * bits // 8
    fmt = _riff_chunk(
        b"fmt ",
        struct.pack("<HHIIHH", 1, channels, sample_rate, byte_rate, 2, bits),
    )
    data = _riff_chunk(b"data", b"\x00" * (byte_rate * seconds))
    body = b"WAVE" + fmt + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


class MediaProbeTests(unittest.TestCase):
    def test_png_and_jpeg_dimensions(self) -> None:
        png = probe_image(_png())
        self.assertTrue(png.ok)
        self.assertEqual((png.width, png.height), (1080, 1920))
        jpeg = probe_image(_jpeg())
        self.assertTrue(jpeg.ok)
        self.assertEqual((jpeg.width, jpeg.height), (1080, 1920))
        unknown = probe_image(b"not an image")
        self.assertFalse(unknown.ok)

    def test_wav_duration(self) -> None:
        info = probe_wav(_wav(seconds=2))
        self.assertTrue(info.ok)
        self.assertEqual(info.sample_rate, 16_000)
        self.assertEqual(info.channels, 1)
        self.assertAlmostEqual(info.duration_s, 2.0)

    def test_mp4_structure_and_audio_detection(self) -> None:
        info = probe_video(_mp4())
        self.assertTrue(info.ok, info.problems)
        self.assertEqual((info.width, info.height), (1080, 1920))
        self.assertAlmostEqual(info.duration_s, 45.0)
        self.assertTrue(info.has_audio)

        silent = probe_video(_mp4(audio=False))
        self.assertFalse(silent.ok)
        self.assertIn("no audio track", " ".join(silent.problems))

    def test_validate_render_accepts_verified_vertical_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "render.mp4"
            path.write_bytes(_mp4())
            info, issues = validate_render(path)
        self.assertEqual(issues, [])
        self.assertIsNotNone(info)
        self.assertEqual((info.width, info.height), (1080, 1920))

    def test_validate_render_rejects_horizontal_and_silent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            horizontal = Path(tmp) / "horizontal.mp4"
            horizontal.write_bytes(_mp4(width=1920, height=1080))
            _info, issues = validate_render(horizontal)
            self.assertTrue(any("aspect ratio" in issue or "width" in issue or "height" in issue for issue in issues))

            silent = Path(tmp) / "silent.mp4"
            silent.write_bytes(_mp4(audio=False))
            _info, issues = validate_render(silent)
            self.assertTrue(any("audio" in issue for issue in issues))

    def test_validate_file_sniffing_and_minimums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "clip.wav"
            wav_path.write_bytes(_wav(seconds=1))
            info, issues = validate_file(
                wav_path,
                expect_format="wav",
                min_bytes=1024,
                min_duration_s=0.5,
                max_duration_s=2,
            )
            self.assertEqual(issues, [])
            self.assertEqual(info.duration_s, 1.0)

            tiny = Path(tmp) / "tiny.mp4"
            tiny.write_bytes(b"x")
            info, issues = validate_file(tiny, expect_format="mp4")
            self.assertIsNone(info)
            self.assertTrue(any("suspiciously small" in issue for issue in issues))

    def test_aspect_helper(self) -> None:
        self.assertEqual(check_aspect(1080, 1920, "9:16")[0], "PASS")
        self.assertEqual(check_aspect(1920, 1080, "9:16")[0], "FAIL")
        self.assertEqual(check_aspect(None, None, "9:16")[0], "FAIL")

    def test_json_artifact(self) -> None:
        parsed, issues = json_artifact(b'{"job_id": "abc", "status": "ok"}', expect_keys=("job_id",))
        self.assertEqual(issues, [])
        self.assertEqual(parsed["job_id"], "abc")
        _parsed, issues = json_artifact(b"[]")
        self.assertTrue(issues)
        _parsed, issues = json_artifact(b'{"status": "ok"}', expect_keys=("job_id",))
        self.assertTrue(any("missing required keys" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
