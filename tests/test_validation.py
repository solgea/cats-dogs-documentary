"""End-to-end QA validation of a real package plus fail-closed mutations."""
from __future__ import annotations

import copy
import unittest

try:
    from ._support import ROOT, load_json
except ImportError:  # pragma: no cover
    from _support import ROOT, load_json

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
        provider_package = None
        request_path = self.folder / "viewmade-request.json"
        if request_path.is_file():
            request_payload = load_json(request_path)
            candidate = request_payload.get("provider_package")
            provider_package = candidate if isinstance(candidate, dict) else None
        metadata = metadata or build_metadata(
            package,
            research,
            self.channel,
            provider_package=provider_package,
        )
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
        checks = {check.id: check for check in result.checks}
        self.assertEqual(checks["package.editorial"].status, "PASS")
        self.assertEqual(checks["history.dedup"].status, "SKIP")
        render_file = self.project.root / "renders" / "dog-guilty-look.mp4"
        if render_file.is_file():
            self.assertEqual(result.render_status, "PASS")
            self.assertEqual(checks["render.artifact"].status, "PASS")
            self.assertEqual(checks["render.attribution"].status, "PASS")
            self.assertEqual(checks["render.editorial_review"].status, "PASS")
            self.assertIn("REJECTED", checks["render.editorial_review"].detail)
        else:
            self.assertEqual(result.render_status, "NOT_RENDERED")
            self.assertEqual(checks["render.artifact"].status, "SKIP")
            self.assertEqual(checks["render.attribution"].status, "SKIP")
            self.assertEqual(checks["render.editorial_review"].status, "SKIP")
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
        self.assertIn("required visual disclosure", check.detail)

    def test_real_footage_ai_assisted_claim_fails(self) -> None:
        metadata = build_metadata(
            self.package,
            self.research,
            self.channel,
            provider_package=load_json(
                self.folder / "viewmade-request.json"
            ).get("provider_package"),
        )
        metadata["description"] += "\nIllustrative, AI-assisted visuals; not documentary footage."
        result = self._validate(metadata=metadata)
        self.assertEqual(result.status, "FAIL")
        check = next(check for check in result.checks if check.id == "metadata.valid")
        self.assertEqual(check.status, "FAIL")
        self.assertIn("must not claim AI-assisted", check.detail)

    def test_missing_footage_source_url_fails_attribution(self) -> None:
        request = load_json(self.folder / "viewmade-request.json")
        provider_package = request.get("provider_package") or {}
        render_file = self.project.root / "renders" / "dog-guilty-look.mp4"
        if not render_file.is_file():
            self.skipTest("no local pilot render to attribute")
        metadata = build_metadata(
            self.package,
            self.research,
            self.channel,
            provider_package=provider_package,
        )
        url = provider_package["sources"][0]["url"]
        metadata["description"] = metadata["description"].replace(url, "")
        result = self._validate(metadata=metadata)
        check = next(check for check in result.checks if check.id == "render.attribution")
        self.assertEqual(check.status, "FAIL")
        self.assertIn(url, check.detail)

    def test_visual_distress_term_fails(self) -> None:
        package = copy.deepcopy(self.package)
        package["scenes"][0]["visual"]["description"] += " The crying dog is shaking with fear."
        result = self._validate(package=package)
        check = next(check for check in result.checks if check.id == "scene.s1.welfare")
        self.assertEqual(check.status, "FAIL")
        self.assertEqual(result.status, "FAIL")


if __name__ == "__main__":
    unittest.main()
