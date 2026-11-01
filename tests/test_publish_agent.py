"""Tests for the autonomous publish agent: review gates, LLM veto, upload call."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

try:
    from ._support import copy_project
except ImportError:  # pragma: no cover - direct execution
    from _support import copy_project

from cddocs import publish_agent
from cddocs.publish_agent import (
    APPROVE,
    DISABLED,
    NEEDS_REVIEW,
    REJECT,
    review_candidate,
    run_agent,
)


def candidate_for(project, **overrides):
    path = project.root / "renders" / "cat-sweetness.mp4"
    candidate = {
        "path": path,
        "name": path.name,
        "title": "Kedilerin Dokunma Duyusu",
        "description": "Kedilerin dokunma duyusu üzerine kısa bir belgesel.",
        "tags": ["kedi", "köpek", "belgesel"],
        "sources": [],
        "attributions": [],
        "provider_status": "ready",
        "job_id": "job-approve-1",
    }
    candidate.update(overrides)
    return candidate


class PublishAgentReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = copy_project(Path(self._tmp.name) / "project")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def review(self, candidate, **kwargs):
        kwargs.setdefault("token_valid", True)
        kwargs.setdefault("registry", [])
        kwargs.setdefault("upload_history", {})
        return review_candidate(self.project, candidate, {}, **kwargs)

    def test_valid_render_is_approved(self) -> None:
        decision = self.review(candidate_for(self.project))
        self.assertEqual(decision.verdict, APPROVE, decision.to_dict())
        self.assertEqual(decision.reasons, [])
        self.assertGreater(decision.media.get("duration_s") or 0, 30)

    def test_missing_file_is_rejected(self) -> None:
        missing = self.project.root / "renders" / "nonexistent.mp4"
        decision = self.review(candidate_for(self.project, path=missing))
        self.assertEqual(decision.verdict, REJECT)
        checks = {check.check_id: check for check in decision.checks}
        self.assertEqual(checks["file.exists"].status, "FAIL")

    def test_duplicate_youtube_title_is_rejected(self) -> None:
        candidate = candidate_for(self.project)
        decision = self.review(candidate, registry=[
            {"title": candidate["title"], "youtube_id": "yt-123"},
        ])
        self.assertEqual(decision.verdict, REJECT)
        self.assertIn("yt-123", " ".join(decision.reasons))

    def test_duplicate_viewmade_job_is_rejected(self) -> None:
        decision = self.review(candidate_for(self.project), registry=[
            {"title": "Başka video", "youtube_id": "yt-999", "viewmade_id": "job-approve-1"},
        ])
        self.assertEqual(decision.verdict, REJECT)

    def test_duplicate_upload_hash_is_rejected(self) -> None:
        candidate = candidate_for(self.project)
        digest = publish_agent._sha256_file(Path(candidate["path"]))
        decision = self.review(candidate, upload_history={
            digest: {"video_id": "yt-hash"},
        })
        self.assertEqual(decision.verdict, REJECT)
        self.assertIn("yt-hash", " ".join(decision.reasons))

    def test_rejected_pilot_is_rejected(self) -> None:
        decision = self.review(candidate_for(self.project, title="The Guilty Look"))
        self.assertEqual(decision.verdict, REJECT)
        checks = {check.check_id: check for check in decision.checks}
        self.assertEqual(checks["policy.rejected"].status, "FAIL")

    def test_title_over_100_chars_is_rejected(self) -> None:
        decision = self.review(candidate_for(self.project, title="K" * 101))
        self.assertEqual(decision.verdict, REJECT)

    def test_missing_attributions_for_real_footage_is_rejected(self) -> None:
        decision = self.review(candidate_for(
            self.project,
            sources=[{"title": "Stock clip", "url": "https://example.com/clip"}],
            attributions=[],
        ))
        self.assertEqual(decision.verdict, REJECT)
        checks = {check.check_id: check for check in decision.checks}
        self.assertEqual(checks["rights.attribution"].status, "FAIL")

    def test_daily_quota_is_enforced(self) -> None:
        from datetime import datetime

        today = datetime.now().isoformat(timespec="seconds")
        history = {
            f"hash-{index}": {"video_id": f"yt-{index}", "uploaded_at": today}
            for index in range(5)
        }
        decision = self.review(candidate_for(self.project), upload_history=history)
        self.assertEqual(decision.verdict, REJECT)
        checks = {check.check_id: check for check in decision.checks}
        self.assertEqual(checks["quota.daily"].status, "FAIL")

    def test_missing_youtube_token_is_rejected(self) -> None:
        decision = review_candidate(
            self.project,
            candidate_for(self.project),
            {},
            token_valid=False,
            registry=[],
            upload_history={},
        )
        self.assertEqual(decision.verdict, REJECT)
        checks = {check.check_id: check for check in decision.checks}
        self.assertEqual(checks["channel.token"].status, "FAIL")

    def test_fewer_than_three_tags_needs_review(self) -> None:
        decision = self.review(candidate_for(self.project, tags=["kedi"]))
        self.assertEqual(decision.verdict, NEEDS_REVIEW)


class PublishAgentRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = copy_project(Path(self._tmp.name) / "project")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_agent(self, settings=None, **kwargs):
        kwargs.setdefault("token_valid", True)
        kwargs.setdefault("registry", [])
        kwargs.setdefault("upload_history", {})
        kwargs.setdefault("allow_upload", True)
        # Mock approval validation to pass by default for tests that expect uploads
        with mock.patch.object(publish_agent, "validate_approval_for_upload",
                               return_value=(True, "Test approval valid", {"file_sha256": "test", "metadata_hash": "test"})):
            return run_agent(self.project, candidate_for(self.project),
                             settings or {}, **kwargs)

    def test_approve_triggers_upload_with_unlisted_privacy(self) -> None:
        settings = {"agent_enabled": True, "agent_privacy": "public"}
        with mock.patch.object(publish_agent, "upload_candidate",
                               return_value={"video_id": "yt-1"}) as upload:
            outcome = self.run_agent(settings)
        self.assertEqual(outcome["verdict"], APPROVE)
        self.assertEqual(outcome["upload"], {"video_id": "yt-1"})
        self.assertEqual(upload.call_args.kwargs["privacy"], "unlisted")

    def test_public_privacy_requires_explicit_permission(self) -> None:
        settings = {"agent_enabled": True, "agent_privacy": "public",
                    "agent_allow_public": True}
        with mock.patch.object(publish_agent, "upload_candidate",
                               return_value={"video_id": "yt-2"}) as upload:
            self.run_agent(settings)
        self.assertEqual(upload.call_args.kwargs["privacy"], "public")

    def test_rejected_candidate_never_uploads(self) -> None:
        with mock.patch.object(publish_agent, "upload_candidate") as upload:
            outcome = self.run_agent({"agent_enabled": True},
                                     upload_history={_digest(self.project):
                                                     {"video_id": "yt-dup"}})
        self.assertEqual(outcome["verdict"], REJECT)
        upload.assert_not_called()

    def test_disabled_agent_does_not_upload(self) -> None:
        with mock.patch.object(publish_agent, "upload_candidate") as upload:
            outcome = self.run_agent({"agent_enabled": False})
        self.assertEqual(outcome["verdict"], DISABLED)
        upload.assert_not_called()

    def test_llm_reject_blocks_upload(self) -> None:
        settings = {"agent_enabled": True, "agent_llm_enabled": True,
                    "agent_llm_model": "test-model"}
        env = {"OPENAI_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(publish_agent, "llm_second_opinion",
                                  return_value=("reject", ["Görüntüde filigran var"],
                                                "test-model")) as opinion, \
                mock.patch.object(publish_agent, "upload_candidate") as upload:
            outcome = self.run_agent(settings)
        opinion.assert_called_once()
        upload.assert_not_called()
        self.assertEqual(outcome["verdict"], REJECT)
        self.assertTrue(outcome["llm_used"])
        self.assertIn("filigran", " ".join(outcome["reasons"]))

    def test_llm_unavailable_blocks_upload(self) -> None:
        settings = {"agent_enabled": True, "agent_llm_enabled": True,
                    "agent_llm_model": "test-model"}
        env = {"OPENAI_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(publish_agent, "llm_second_opinion",
                                  return_value=("review", ["LLM çağrısı başarısız"],
                                                "test-model")), \
                mock.patch.object(publish_agent, "upload_candidate") as upload:
            outcome = self.run_agent(settings)
        upload.assert_not_called()
        self.assertEqual(outcome["verdict"], NEEDS_REVIEW)

    def test_llm_approve_keeps_upload(self) -> None:
        settings = {"agent_enabled": True, "agent_llm_enabled": True,
                    "agent_llm_model": "test-model"}
        env = {"OPENAI_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(publish_agent, "llm_second_opinion",
                                  return_value=("approve", ["Temiz çıktı"],
                                                "test-model")), \
                mock.patch.object(publish_agent, "upload_candidate",
                                  return_value={"video_id": "yt-3"}) as upload:
            outcome = self.run_agent(settings)
        upload.assert_called_once()
        self.assertEqual(outcome["verdict"], APPROVE)
        self.assertEqual(outcome["llm_verdict"], "approve")

    def test_llm_not_configured_skips_second_opinion(self) -> None:
        settings = {"agent_enabled": True, "agent_llm_enabled": True,
                    "agent_llm_model": ""}
        with mock.patch.object(publish_agent, "llm_second_opinion") as opinion, \
                mock.patch.object(publish_agent, "upload_candidate",
                                  return_value={"video_id": "yt-4"}):
            outcome = self.run_agent(settings)
        opinion.assert_not_called()
        self.assertFalse(outcome["llm_used"])

    def test_decision_is_recorded(self) -> None:
        with mock.patch.object(publish_agent, "upload_candidate",
                               return_value={"video_id": "yt-5"}):
            self.run_agent({"agent_enabled": True})
        recorded = publish_agent.recent_decisions(self.project)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["verdict"], APPROVE)


def _load_render_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "dashboard_viewmade_render.py"
    spec = importlib.util.spec_from_file_location("dashboard_viewmade_render_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RENDER_SCRIPT = _load_render_script()


class BackgroundRenderAgentWiringTests(unittest.TestCase):
    """Render bittiğinde arka plan betiğinin ajanı nasıl çağırdığını doğrular."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = copy_project(Path(self._tmp.name) / "project")
        self.slug = "cat-sweetness"
        request_path = self.project.packages_dir / self.slug / "viewmade-request.json"
        self.payload = json.loads(request_path.read_text(encoding="utf-8"))
        self.result = SimpleNamespace(
            render_path="renders/cat-sweetness.mp4",
            provider_state="ready",
            job_id="job-wire-1",
            status="COMPLETE",
        )
        self.state_path = self.project.state_dir / f"dashboard-render-{self.slug}.json"
        self.state_path.write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_settings(self, **values) -> None:
        (self.project.root / "panel_settings.json").write_text(
            json.dumps(values, ensure_ascii=False), encoding="utf-8")

    def run_script_agent(self, **kwargs):
        return RENDER_SCRIPT._run_publish_agent(
            self.project, self.slug, self.payload, self.result, self.state_path)

    def test_auto_publish_disabled_skips_agent(self) -> None:
        self.write_settings(agent_enabled=True, agent_auto_publish=False)
        with mock.patch.object(publish_agent, "upload_candidate") as upload:
            summary = self.run_script_agent()
        self.assertEqual(summary, {})
        upload.assert_not_called()
        self.assertFalse((self.project.state_dir / publish_agent.DECISION_FILE).exists())

    def test_approved_render_is_uploaded_and_logged(self) -> None:
        # Background render path uses allow_upload=False (Phase 1A safety)
        # It should evaluate and log decision, but NOT upload
        approval_mock = (True, "Test approval", {"file_sha256": "test", "metadata_hash": "test"})
        with mock.patch.object(publish_agent, "youtube_token_valid", return_value=True), \
                mock.patch.object(publish_agent, "validate_approval_for_upload",
                                  return_value=approval_mock), \
                mock.patch.object(publish_agent, "upload_candidate",
                                  return_value={"video_id": "yt-wire",
                                                "video_url": "https://youtu.be/yt-wire"}) as upload:
            summary = self.run_script_agent()
        self.assertEqual(summary["verdict"], APPROVE)
        self.assertFalse(summary["uploaded"])  # Background path does NOT upload
        self.assertEqual(summary["video_id"], "")  # Empty string when not uploaded
        upload.assert_not_called()
        recorded = publish_agent.recent_decisions(self.project)
        self.assertEqual(recorded[0]["verdict"], APPROVE)
        activity = json.loads((self.project.root / "activity_log.json").read_text(encoding="utf-8"))
        self.assertTrue(any("APPROVE" in row["msg"] for row in activity))

    def test_invalid_token_blocks_upload(self) -> None:
        approval_mock = (True, "Test approval", {"file_sha256": "test", "metadata_hash": "test"})
        with mock.patch.object(publish_agent, "youtube_token_valid", return_value=False), \
                mock.patch.object(publish_agent, "validate_approval_for_upload",
                                  return_value=approval_mock), \
                mock.patch.object(publish_agent, "upload_candidate") as upload:
            summary = self.run_script_agent()
        self.assertEqual(summary["verdict"], REJECT)
        self.assertFalse(summary["uploaded"])
        upload.assert_not_called()
        recorded = publish_agent.recent_decisions(self.project)
        self.assertEqual(recorded[0]["verdict"], REJECT)


class LlmResponseParsingTests(unittest.TestCase):
    def test_json_code_fence_is_parsed(self) -> None:
        verdict, reasons = publish_agent._parse_llm_response(
            '```json\n{"verdict": "reject", "reasons": ["filigran"]}\n```'
        )
        self.assertEqual(verdict, "reject")
        self.assertEqual(reasons, ["filigran"])

    def test_unknown_verdict_becomes_review(self) -> None:
        verdict, reasons = publish_agent._parse_llm_response('{"verdict": "belki"}')
        self.assertEqual(verdict, "review")
        self.assertTrue(reasons)

    def test_non_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            publish_agent._parse_llm_response("onaylıyorum")


def _digest(project) -> str:
    return publish_agent._sha256_file(project.root / "renders" / "cat-sweetness.mp4")


if __name__ == "__main__":
    unittest.main()
