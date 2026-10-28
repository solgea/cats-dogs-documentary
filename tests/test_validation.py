"""End-to-end QA validation of a real package plus fail-closed mutations."""
from __future__ import annotations

import copy
import unittest

try:
    from ._support import ROOT
except ImportError:  # pragma: no cover
    from _support import ROOT

from cddocs.config import Project
from cddocs.metadata import build_metadata
from cddocs.subtitles import build_cues, format_srt
from cddocs.validation import summarize_results, validate_package


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project = Project.open(ROOT)
        cls.channel = cls.project.channel()
        cls.sources_config = cls.project.sources()
        cls.package, cls.research, cls.folder = cls.project.load_package("dog-guilty-look")

    def _validate(
        self,
        package: dict | None = None,
        research: dict | None = None,
        metadata: dict | None = None,
    ):
        package = package or self.package
        research = research or self.research
        metadata = metadata or build_metadata(package, research, self.channel)
        cues = build_cues(
            package["scenes"],
            total_duration_s=float(package["target_duration_s"]),
            max_line_chars=int(self.channel["format"]["subtitle_max_line_chars"]),
        )
        return validate_package(
            package=package,
            research=research,
            folder=self.folder,
            channel=self.channel,
            sources_config=self.sources_config,
            history=None,
            metadata=metadata,
            cues=cues,
            srt_text=format_srt(cues),
            artifact_files={},
        )

    def test_real_package_passes_but_is_not_publish_ready(self) -> None:
        result = self._validate()
        self.assertEqual(result.status, "PASS", [check.to_dict() for check in result.checks if check.status == "FAIL"])
        self.assertFalse(result.publish_ready)
        self.assertEqual(result.render_status, "NOT_RENDERED")
        checks = {check.id: check for check in result.checks}
        self.assertEqual(checks["package.editorial"].status, "PASS")
        self.assertEqual(checks["render.artifact"].status, "SKIP")
        self.assertEqual(checks["history.dedup"].status, "SKIP")
        summary = summarize_results([result])
        self.assertEqual(summary["status"], "PASS")
        self.assertFalse(summary["publish_ready"])

    def test_banned_source_domain_and_bad_doi_fail(self) -> None:
        research = copy.deepcopy(self.research)
        source = research["sources"][0]
        source["url"] = "https://reddit.com/r/dogs"
        source["doi"] = "not-a-doi"
        result = self._validate(research=research)
        self.assertEqual(result.status, "FAIL")
        check = next(check for check in result.checks if check.id == "research.source.horowitz-2009")
        self.assertEqual(check.status, "FAIL")
        self.assertIn("allowed domain", check.detail)
        self.assertIn("DOI format", check.detail)

    def test_medical_advice_language_fails(self) -> None:
        package = copy.deepcopy(self.package)
        package["scenes"][1]["narration"] = "A simple pill can cure your dog at home."
        result = self._validate(package=package)
        self.assertEqual(result.status, "FAIL")
        medical = [check for check in result.checks if check.id == "narration.medical_claims"]
        self.assertTrue(medical)
        self.assertEqual(medical[0].status, "FAIL")

    def test_missing_metadata_disclosure_fails(self) -> None:
        metadata = build_metadata(self.package, self.research, self.channel)
        metadata["description"] = metadata["description"].replace(
            self.channel["editorial"]["required_disclosure"], ""
        )
        result = self._validate(metadata=metadata)
        self.assertEqual(result.status, "FAIL")
        check = next(check for check in result.checks if check.id == "metadata.valid")
        self.assertEqual(check.status, "FAIL")
        self.assertIn("synthetic-media disclosure", check.detail)

    def test_visual_distress_term_fails(self) -> None:
        package = copy.deepcopy(self.package)
        package["scenes"][0]["visual"]["description"] += " The crying dog is shaking with fear."
        result = self._validate(package=package)
        check = next(check for check in result.checks if check.id == "scene.s1.welfare")
        self.assertEqual(check.status, "FAIL")
        self.assertEqual(result.status, "FAIL")


if __name__ == "__main__":
    unittest.main()
