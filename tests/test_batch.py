"""Full batch build, validation, packaging, and live-render refusal flow."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from ._support import BATCH_ID, copy_project, load_json, write_json
except ImportError:  # pragma: no cover
    from _support import BATCH_ID, copy_project, load_json, write_json

from cddocs.batch import build_batch, package_batch, render_batch, validate_batch
from cddocs.cli import main
from cddocs.config import Settings
from cddocs.util import PipelineError


class BatchFlowTests(unittest.TestCase):
    def test_build_validate_package_and_refuse_live_without_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            request_path = project.package_path("dog-guilty-look") / "viewmade-request.json"
            request = load_json(request_path)
            request.update(
                {
                    "status": "NOT_SUBMITTED",
                    "submission_allowed": False,
                    "job_id": None,
                    "provider_state": None,
                    "render_path": None,
                    "render_sha256": None,
                    "normalization": None,
                    "provider_package": None,
                    "error": None,
                    "submission": None,
                }
            )
            write_json(request_path, request)
            # The test requires a clean request state; reset editorial_review
            # so the build/validate flow starts from a neutral state.
            request = load_json(request_path)
            request["editorial_review"] = None
            write_json(request_path, request)
            outcome = build_batch(project, BATCH_ID)
            self.assertEqual(outcome.status, "PASS", outcome.to_dict())
            self.assertEqual(len(outcome.results), 6)
            self.assertEqual(outcome.pairs, [])
            for result in outcome.results:
                self.assertEqual(result.status, "PASS")
                self.assertFalse(result.publish_ready)
                self.assertEqual(result.render_status, "NOT_RENDERED")

            history_payload = load_json(project.history_export)
            self.assertEqual(len(history_payload["topics"]), 6)
            self.assertEqual(len(history_payload["batches"]), 1)
            self.assertEqual(history_payload["batches"][0]["batch_id"], BATCH_ID)

            request = load_json(project.package_path("dog-guilty-look") / "viewmade-request.json")
            self.assertEqual(request["status"], "NOT_SUBMITTED")
            self.assertFalse(request["submission_allowed"])
            self.assertIsNone(request["job_id"])
            self.assertIsNone(request["render_path"])

            validation = validate_batch(project, BATCH_ID)
            self.assertEqual(validation.status, "PASS")
            self.assertEqual(validation.pairs, [])

            archive_info = package_batch(
                project,
                BATCH_ID,
                output_dir=Path(tmp) / "dist",
            )
            archive = Path(archive_info["archive"])
            self.assertTrue(archive.is_file())
            self.assertEqual(len(archive_info["sha256"]), 64)
            with zipfile.ZipFile(archive) as zipped:
                names = set(zipped.namelist())
                self.assertIn("batch.json", names)
                self.assertIn("batch-qa-report.json", names)
                self.assertIn("history.json", names)
                self.assertIn("PACKAGE_README.md", names)
                self.assertIn("SHA256SUMS.txt", names)
                self.assertIn("packages/dog-guilty-look/metadata.json", names)
                self.assertIn("packages/dog-guilty-look/subtitles.srt", names)
                self.assertNotIn("packages/dog-guilty-look/render.mp4", names)
                readme = zipped.read("PACKAGE_README.md").decode("utf-8")
                self.assertIn("No validated MP4 is present", readme)

            settings = Settings(
                mcp_token=None,
                live_confirm="",
                state_dir=project.state_dir,
            )
            with self.assertRaises(PipelineError) as caught:
                render_batch(project, BATCH_ID, allow_live=False, settings=settings)
            self.assertIn("Live ViewMade rendering is disabled", str(caught.exception))

            wrong_confirm = Settings(
                mcp_token=None,
                live_confirm="NO",
                state_dir=project.state_dir,
            )
            with self.assertRaises(PipelineError) as caught:
                render_batch(project, BATCH_ID, allow_live=True, settings=wrong_confirm)
            self.assertIn("CDDOCS_LIVE_CONFIRM=YES", str(caught.exception))
            self.assertFalse((project.batch_path(BATCH_ID) / "render-report.json").exists())

    def test_rebuild_marks_changed_policy_stale_and_preserves_render_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            request_path = project.package_path("dog-guilty-look") / "viewmade-request.json"
            before = load_json(request_path)
            self.assertEqual(
                before["job_id"], "f59f8a91-7b2b-4dbb-a03d-62effc911581"
            )
            self.assertTrue(before["render_path"])
            self.assertTrue(before["provider_package"])

            outcome = build_batch(project, BATCH_ID)
            self.assertEqual(outcome.status, "PASS", outcome.to_dict())

            after = load_json(request_path)
            self.assertEqual(after["status"], "STALE")
            for key in (
                "job_id",
                "provider_state",
                "render_path",
                "render_sha256",
                "normalization",
                "provider_package",
                "editorial_review",
            ):
                self.assertEqual(after.get(key), before.get(key), key)

            report = load_json(outcome.report_path)
            self.assertEqual(
                report["render_gate"]["rejected_packages"], ["dog-guilty-look"]
            )

    def test_cli_render_requires_explicit_package_or_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "--root",
                        str(project.root),
                        "batch",
                        "render",
                        BATCH_ID,
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("--package", stderr.getvalue())
            self.assertFalse(
                (project.batch_path(BATCH_ID) / "render-report.json").exists()
            )

    def test_render_batch_rejects_package_outside_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            settings = Settings(
                mcp_token=None,
                live_confirm="YES",
                state_dir=project.state_dir,
            )
            with self.assertRaises(PipelineError) as caught:
                render_batch(
                    project,
                    BATCH_ID,
                    allow_live=True,
                    settings=settings,
                    only_packages=["not-in-this-batch"],
                )
            self.assertIn("not in batch", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
