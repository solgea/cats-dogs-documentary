"""Subtitle splitting, wrapping, SRT round-trip, and timing gates."""
from __future__ import annotations

import unittest

try:
    from ._support import ROOT  # noqa: F401
except ImportError:  # pragma: no cover - supports `discover -s tests`
    from _support import ROOT  # noqa: F401

from cddocs.subtitles import (
    Cue,
    build_cues,
    cue_stats,
    cue_text,
    fill_target_duration,
    format_srt,
    parse_srt,
    split_evenly,
    split_into_cues,
    validate_cues,
    wrap_two_lines,
)
from cddocs.util import PipelineError, normalise_whitespace


class SubtitleTests(unittest.TestCase):
    def test_short_text_is_not_wrapped(self) -> None:
        self.assertEqual(wrap_two_lines("A short cue.", 42), "A short cue.")

    def test_wrap_keeps_words_and_line_limits(self) -> None:
        text = (
            "The quick brown fox jumps over the lazy dog while the calm cat "
            "naps nearby"
        )
        wrapped = wrap_two_lines(text, 42)
        lines = wrapped.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(line) <= 42 for line in lines))
        self.assertEqual(normalise_whitespace(wrapped), normalise_whitespace(text))

    def test_split_preserves_every_word_and_fits_two_lines(self) -> None:
        text = (
            "This deliberately long narration sentence gives the subtitle splitter "
            "enough material to produce several readable cues without dropping a "
            "single word or creating an orphaned tail at the end of the sequence."
        )
        chunks = split_into_cues(text, max_chars=84)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(normalise_whitespace(" ".join(chunks)), normalise_whitespace(text))
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 84)
            wrapped_lines = wrap_two_lines(chunk, 42).splitlines()
            self.assertLessEqual(len(wrapped_lines), 2)
            self.assertTrue(all(len(line) <= 42 for line in wrapped_lines))

    def test_build_cues_is_contiguous_and_validates(self) -> None:
        scenes = [
            {
                "id": "s1",
                "start_s": 0,
                "duration_s": 4,
                "narration": "Cats have a special way of greeting people they trust.",
            },
            {
                "id": "s2",
                "start_s": 4,
                "duration_s": 6,
                "narration": "A slow blink can signal calm, and the other cat may answer.",
            },
        ]
        expected = " ".join(scene["narration"] for scene in scenes)
        cues = build_cues(scenes, total_duration_s=10, max_line_chars=42)
        issues = validate_cues(
            cues,
            total_duration_s=10,
            max_line_chars=42,
            expected_text=expected,
        )
        self.assertEqual(issues, [])
        self.assertEqual(cues[0].start_ms, 0)
        self.assertAlmostEqual(cues[-1].end_s, 10.0)
        self.assertEqual(cue_text(cues), normalise_whitespace(expected))
        self.assertGreater(cue_stats(cues)["cues"], 0)

    def test_srt_round_trip(self) -> None:
        cues = [
            Cue(index=1, start_ms=0, end_ms=1200, text="First line"),
            Cue(index=2, start_ms=1200, end_ms=3000, text="Second\nline"),
        ]
        text = format_srt(cues)
        self.assertIn("00:00:00,000 --> 00:00:01,200", text)
        self.assertEqual(parse_srt(text), cues)

    def test_malformed_srt_is_rejected(self) -> None:
        with self.assertRaises(PipelineError):
            parse_srt("1\n00:00:01,000 -> 00:00:02,000\nBad timestamp\n")
        with self.assertRaises(PipelineError):
            parse_srt("1\n00:00:01,000 --> 00:00:02,000\n\n")

    def test_validation_catches_overlong_and_fast_cues(self) -> None:
        cues = [
            Cue(index=1, start_ms=0, end_ms=1000, text="x" * 43),
            Cue(index=2, start_ms=1000, end_ms=2000, text="end"),
        ]
        issues = validate_cues(cues, total_duration_s=2, max_line_chars=42)
        self.assertTrue(any("max 42" in issue for issue in issues))
        self.assertTrue(any("chars/s" in issue for issue in issues))

    def test_fill_target_duration_and_even_split(self) -> None:
        cues = [Cue(index=1, start_ms=0, end_ms=2000, text="Only cue")]
        filled = fill_target_duration(cues, 4)
        self.assertAlmostEqual(filled[-1].end_s, 4.0)
        self.assertEqual(fill_target_duration(cues, 1), cues)
        self.assertEqual(split_evenly("one two three four", 2), ["one two", "three four"])
        self.assertEqual(split_evenly("text", 0), [])


if __name__ == "__main__":
    unittest.main()
