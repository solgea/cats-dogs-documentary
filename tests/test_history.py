"""History persistence, export, and duplicate scoring."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from ._support import load_json
except ImportError:  # pragma: no cover
    from _support import load_json

from cddocs.history import History
from cddocs.util import PipelineError


class HistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        folder = Path(self._tmp.name)
        self.db = folder / "history.db"
        self.export = folder / "history.json"
        self.history = History(self.db, self.export)
        self.addCleanup(self.history.close)
        self.history.register_topic(
            package_id="cat-kneading",
            slug="cat-kneading",
            batch_id="batch-01",
            title="Why Cats Knead Their Blankets",
            central_question="Why do domestic cats knead soft surfaces with their front paws?",
            central_fact=(
                "Kneading is a rhythmic paw movement seen in relaxed cats and may "
                "retain links to nursing behavior."
            ),
            source_ids=["knead-review"],
            status="PASS",
            created_at="2026-01-01T00:00:00Z",
        )

    def test_rebuild_same_package_is_idempotent(self) -> None:
        matches = self.history.check_candidate(
            package_id="cat-kneading",
            slug="cat-kneading",
            title="Why Cats Knead Their Blankets",
            central_question="Why do domestic cats knead soft surfaces with their front paws?",
            central_fact="A changed fact on rebuild is allowed without self-duplication.",
            source_ids=["knead-review"],
            batch_id="batch-01",
        )
        self.assertEqual(matches, [])

    def test_slug_reuse_and_cross_batch_id_fail(self) -> None:
        slug_matches = self.history.check_candidate(
            package_id="another-package",
            slug="cat-kneading",
            title="A Completely Different Topic",
            central_question="What is a different question?",
            central_fact="A different fact with low lexical overlap.",
            source_ids=["other-source"],
            batch_id="batch-02",
        )
        self.assertEqual(slug_matches[0].severity, "FAIL")
        self.assertEqual(slug_matches[0].reason, "slug already used")

        id_matches = self.history.check_candidate(
            package_id="cat-kneading",
            slug="cat-kneading-new",
            title="A Completely Different Topic",
            central_question="What is a different question?",
            central_fact="A different fact with low lexical overlap.",
            source_ids=["other-source"],
            batch_id="batch-02",
        )
        self.assertEqual(id_matches[0].severity, "FAIL")
        self.assertIn("another batch", id_matches[0].reason)

    def test_near_identical_title_fails(self) -> None:
        matches = self.history.check_candidate(
            package_id="cat-kneading-two",
            slug="cat-kneading-two",
            title="Why Cats Knead Their Blankets",
            central_question="Why do domestic cats knead soft surfaces with their front paws?",
            central_fact=(
                "Kneading is a rhythmic paw movement seen in relaxed cats and may "
                "retain links to nursing behavior."
            ),
            source_ids=["different-source"],
            batch_id="batch-02",
        )
        self.assertEqual(matches[0].severity, "FAIL")
        self.assertEqual(matches[0].reason, "near-identical title")

    def test_same_source_with_low_overlap_warns(self) -> None:
        matches = self.history.check_candidate(
            package_id="cat-whiskers",
            slug="cat-whiskers",
            title="How Whiskers Detect a Draft",
            central_question="What do cat whiskers sense in moving air?",
            central_fact=(
                "Whisker follicles are packed with mechanoreceptors that respond "
                "to tiny deflections."
            ),
            source_ids=["knead-review"],
            batch_id="batch-02",
        )
        self.assertEqual(matches[0].severity, "WARN")
        self.assertEqual(matches[0].reason, "same primary source as an earlier topic")

    def test_register_refuses_moving_package_to_another_batch(self) -> None:
        with self.assertRaises(PipelineError):
            self.history.register_topic(
                package_id="cat-kneading",
                slug="cat-kneading",
                batch_id="batch-02",
                title="Why Cats Knead Their Blankets",
                central_question="Why do domestic cats knead soft surfaces with their front paws?",
                central_fact="Kneading is a rhythmic paw movement.",
                source_ids=["knead-review"],
                status="PASS",
            )

    def test_export_is_portable_review_data(self) -> None:
        self.history.register_batch(
            batch_id="batch-01",
            package_count=1,
            status="PASS",
            created_at="2026-01-01T00:00:00Z",
        )
        self.history.export()
        payload = load_json(self.export)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(len(payload["topics"]), 1)
        self.assertEqual(payload["topics"][0]["id"], "cat-kneading")
        self.assertEqual(payload["batches"][0]["package_count"], 1)
        self.assertNotIn("fingerprint", payload["topics"][0])

    def test_pair_similarity_and_summary(self) -> None:
        left = {
            "title": "Why Cats Knead Their Blankets",
            "central_question": "Why do cats knead?",
            "central_fact": "Cats knead soft surfaces.",
        }
        self.assertAlmostEqual(self.history.check_batch_pair(left, dict(left)), 1.0)
        summary = self.history.summary()
        self.assertEqual(summary["topics"], 1)
        self.assertEqual(summary["batches"], 0)


if __name__ == "__main__":
    unittest.main()
