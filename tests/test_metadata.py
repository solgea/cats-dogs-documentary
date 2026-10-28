"""Metadata generation and policy validation."""
from __future__ import annotations

import copy
import unittest

try:
    from ._support import ROOT
except ImportError:  # pragma: no cover
    from _support import ROOT

from cddocs.config import Project
from cddocs.metadata import build_metadata, citation, hashtags_from_package, validate_metadata


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project = Project.open(ROOT)
        cls.channel = cls.project.channel()
        cls.package, cls.research, cls.folder = cls.project.load_package("dog-guilty-look")
        cls.metadata = build_metadata(cls.package, cls.research, cls.channel)

    def test_generated_metadata_passes(self) -> None:
        self.assertEqual(validate_metadata(self.metadata, self.package, self.research, self.channel), [])
        self.assertIn("Illustrative, AI-assisted visuals; not documentary footage.", self.metadata["description"])
        self.assertIn("Educational content, not veterinary advice.", self.metadata["description"])
        self.assertIn("#Shorts", self.metadata["hashtags"])
        self.assertEqual(self.metadata["upload_status"], "not_uploaded_manual_only")
        self.assertIsNone(self.metadata["youtube_video_id"])

    def test_missing_disclosure_is_rejected(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["description"] = metadata["description"].replace(
            self.channel["editorial"]["required_disclosure"], ""
        )
        issues = validate_metadata(metadata, self.package, self.research, self.channel)
        self.assertTrue(any("synthetic-media disclosure" in issue for issue in issues))

    def test_manual_only_and_format_fields_are_enforced(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["upload_status"] = "uploaded"
        metadata["resolution"] = "1920x1080"
        metadata["made_for_kids"] = True
        issues = validate_metadata(metadata, self.package, self.research, self.channel)
        self.assertTrue(any("manual-only" in issue for issue in issues))
        self.assertTrue(any("resolution" in issue for issue in issues))
        self.assertTrue(any("made_for_kids" in issue for issue in issues))

    def test_forbidden_title_claim_is_rejected(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["title"] = "Studies prove every dog feels guilt"
        issues = validate_metadata(metadata, self.package, self.research, self.channel)
        self.assertTrue(any("forbidden claim phrase" in issue for issue in issues))

    def test_shorts_hashtag_is_added_only_when_missing(self) -> None:
        package = copy.deepcopy(self.package)
        package["youtube"]["hashtags"] = ["#Dogs", "#Behavior"]
        metadata = build_metadata(package, self.research, self.channel)
        self.assertEqual(metadata["hashtags"], ["#Dogs", "#Behavior", "#Shorts"])
        self.assertEqual(hashtags_from_package(package), ["#Dogs", "#Behavior"])

        package["youtube"]["hashtags"] = ["#Dogs", "#Shorts"]
        metadata = build_metadata(package, self.research, self.channel)
        self.assertEqual(metadata["hashtags"], ["#Dogs", "#Shorts"])

    def test_citation_formats_author_lists(self) -> None:
        source = {
            "authors": ["Ada One", "Ben Two", "Cara Three"],
            "year": 2024,
            "title": "A study title.",
            "journal": "Journal of Examples",
            "volume": "12",
            "issue": "3",
            "pages": "10-20",
            "url": "https://doi.org/10.1234/example",
        }
        text = citation(source)
        self.assertIn("Ada One et al. (2024)", text)
        self.assertIn("Journal of Examples 12(3), 10-20", text)
        self.assertTrue(text.endswith("https://doi.org/10.1234/example"))


if __name__ == "__main__":
    unittest.main()
