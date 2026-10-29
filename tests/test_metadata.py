"""Metadata generation and policy validation."""
from __future__ import annotations

import copy
import unittest

try:
    from ._support import ROOT, load_json
except ImportError:  # pragma: no cover
    from _support import ROOT, load_json

from cddocs.config import Project
from cddocs.metadata import build_metadata, citation, hashtags_from_package, validate_metadata


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project = Project.open(ROOT)
        cls.channel = cls.project.channel()
        cls.package, cls.research, cls.folder = cls.project.load_package("dog-guilty-look")
        request = load_json(cls.folder / "viewmade-request.json")
        provider_package = request.get("provider_package")
        cls.provider_package = provider_package if isinstance(provider_package, dict) else None
        cls.metadata = build_metadata(
            cls.package,
            cls.research,
            cls.channel,
            provider_package=cls.provider_package,
        )

    def test_generated_metadata_passes(self) -> None:
        self.assertEqual(validate_metadata(self.metadata, self.package, self.research, self.channel), [])
        disclosure = self.channel["editorial"]["required_disclosure"]
        self.assertIn(disclosure, self.metadata["description"])
        self.assertNotIn("AI-assisted", self.metadata["description"])
        self.assertIn("Educational content, not veterinary advice.", self.metadata["description"])
        self.assertIn("#Shorts", self.metadata["hashtags"])
        self.assertEqual(self.metadata["visual_mode"], "real_footage_montage")
        self.assertFalse(self.metadata["contains_synthetic_media"])
        self.assertEqual(self.metadata["visual_disclosure"], disclosure)
        self.assertEqual(self.metadata["upload_status"], "not_uploaded_manual_only")
        self.assertIsNone(self.metadata["youtube_video_id"])

    def test_footage_sources_are_credited(self) -> None:
        self.assertIsNotNone(self.provider_package)
        self.assertEqual(self.metadata["footage_provider"], "viewmade")
        self.assertTrue(self.metadata["footage_attributions"])
        description = self.metadata["description"]
        for source in self.provider_package.get("sources") or []:
            self.assertIn(source["url"], description)
        self.assertIn("Footage:", description)

    def test_metadata_without_a_render_has_no_footage_credits(self) -> None:
        metadata = build_metadata(self.package, self.research, self.channel)
        self.assertIsNone(metadata["footage_provider"])
        self.assertEqual(metadata["footage_attributions"], [])
        self.assertNotIn("Footage:", metadata["description"])

    def test_missing_disclosure_is_rejected(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["description"] = metadata["description"].replace(
            self.channel["editorial"]["required_disclosure"], ""
        )
        issues = validate_metadata(metadata, self.package, self.research, self.channel)
        self.assertTrue(any("required visual disclosure" in issue for issue in issues))

    def test_real_footage_rejects_ai_assisted_claim(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["description"] += "\nIllustrative, AI-assisted visuals; not documentary footage."
        issues = validate_metadata(metadata, self.package, self.research, self.channel)
        self.assertTrue(any("must not claim AI-assisted" in issue for issue in issues))

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
