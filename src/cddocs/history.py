"""Topic history and cross-batch duplicate detection.

The SQLite database is machine state. ``state/history.json`` is the committed,
reviewable export written after every successful batch build. Similarity is a
deliberately simple token Jaccard score: transparent, deterministic, and easy
to audit.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .util import (
    PipelineError,
    normalise_for_dedup,
    similarity,
    token_set,
    utc_now_iso,
    write_json_if_changed,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    batch_id TEXT NOT NULL,
    title TEXT NOT NULL,
    central_question TEXT NOT NULL,
    central_fact TEXT NOT NULL,
    source_ids TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    package_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_batch ON topics(batch_id);
CREATE INDEX IF NOT EXISTS idx_topics_created ON topics(created_at);
"""


@dataclass(frozen=True)
class TopicRecord:
    id: str
    slug: str
    batch_id: str
    title: str
    central_question: str
    central_fact: str
    source_ids: tuple[str, ...]
    status: str
    created_at: str

    def combined_text(self) -> str:
        return f"{self.title} {self.central_question} {self.central_fact}"


@dataclass(frozen=True)
class DuplicateMatch:
    severity: str  # FAIL or WARN
    reason: str
    existing_id: str
    existing_slug: str
    existing_batch: str
    existing_title: str
    similarity: float

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "reason": self.reason,
            "existing_id": self.existing_id,
            "existing_slug": self.existing_slug,
            "existing_batch": self.existing_batch,
            "existing_title": self.existing_title,
            "similarity": round(self.similarity, 3),
        }


class History:
    def __init__(self, db_path: str | Path, export_path: str | Path | None = None):
        self.db_path = Path(db_path)
        self.export_path = Path(export_path) if export_path else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "History":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- reads ---------------------------------------------------------

    def topics(self) -> list[TopicRecord]:
        rows = self._connection.execute(
            "SELECT * FROM topics ORDER BY created_at, id"
        ).fetchall()
        return [self._row_to_topic(row) for row in rows]

    def get(self, package_id: str) -> TopicRecord | None:
        row = self._connection.execute(
            "SELECT * FROM topics WHERE id = ?", (package_id,)
        ).fetchone()
        return self._row_to_topic(row) if row else None

    @staticmethod
    def _row_to_topic(row: sqlite3.Row) -> TopicRecord:
        return TopicRecord(
            id=row["id"],
            slug=row["slug"],
            batch_id=row["batch_id"],
            title=row["title"],
            central_question=row["central_question"],
            central_fact=row["central_fact"],
            source_ids=tuple(json.loads(row["source_ids"])),
            status=row["status"],
            created_at=row["created_at"],
        )

    # --- duplicate checks ---------------------------------------------

    def check_candidate(
        self,
        *,
        package_id: str,
        slug: str,
        title: str,
        central_question: str,
        central_fact: str,
        source_ids: list[str] | tuple[str, ...],
        batch_id: str,
    ) -> list[DuplicateMatch]:
        matches: list[DuplicateMatch] = []
        candidate_text = f"{title} {central_question} {central_fact}"
        candidate_sources = set(source_ids)
        candidate_slug = normalise_for_dedup(slug)
        candidate_title = normalise_for_dedup(title)

        for topic in self.topics():
            if topic.id == package_id and topic.batch_id == batch_id:
                # Rebuilding the same package in the same batch is idempotent.
                continue
            if topic.id == package_id and topic.batch_id != batch_id:
                matches.append(
                    DuplicateMatch(
                        "FAIL",
                        "package id already belongs to another batch",
                        topic.id,
                        topic.slug,
                        topic.batch_id,
                        topic.title,
                        1.0,
                    )
                )
                continue
            if normalise_for_dedup(topic.slug) == candidate_slug:
                matches.append(
                    DuplicateMatch(
                        "FAIL",
                        "slug already used",
                        topic.id,
                        topic.slug,
                        topic.batch_id,
                        topic.title,
                        1.0,
                    )
                )
                continue
            title_score = similarity(normalise_for_dedup(topic.title), candidate_title)
            combined_score = similarity(topic.combined_text(), candidate_text)
            if title_score >= 0.86:
                matches.append(
                    DuplicateMatch(
                        "FAIL",
                        "near-identical title",
                        topic.id,
                        topic.slug,
                        topic.batch_id,
                        topic.title,
                        title_score,
                    )
                )
                continue
            if combined_score >= 0.66:
                matches.append(
                    DuplicateMatch(
                        "FAIL",
                        "topic framing is too similar",
                        topic.id,
                        topic.slug,
                        topic.batch_id,
                        topic.title,
                        combined_score,
                    )
                )
                continue
            if combined_score >= 0.45:
                matches.append(
                    DuplicateMatch(
                        "WARN",
                        "overlapping topic framing; review before publishing",
                        topic.id,
                        topic.slug,
                        topic.batch_id,
                        topic.title,
                        combined_score,
                    )
                )
                continue
            if candidate_sources and candidate_sources == set(topic.source_ids):
                matches.append(
                    DuplicateMatch(
                        "WARN",
                        "same primary source as an earlier topic",
                        topic.id,
                        topic.slug,
                        topic.batch_id,
                        topic.title,
                        combined_score,
                    )
                )
        matches.sort(key=lambda item: (item.severity != "FAIL", -item.similarity))
        return matches[:4]

    def check_batch_pair(
        self,
        left: dict,
        right: dict,
        *,
        threshold: float = 0.66,
    ) -> float:
        left_text = f"{left.get('title','')} {left.get('central_question','')} {left.get('central_fact','')}"
        right_text = f"{right.get('title','')} {right.get('central_question','')} {right.get('central_fact','')}"
        return similarity(left_text, right_text)

    # --- writes ---------------------------------------------------------

    def register_topic(
        self,
        *,
        package_id: str,
        slug: str,
        batch_id: str,
        title: str,
        central_question: str,
        central_fact: str,
        source_ids: list[str] | tuple[str, ...],
        status: str,
        created_at: str | None = None,
    ) -> None:
        existing = self.get(package_id)
        if existing and existing.batch_id != batch_id:
            raise PipelineError(
                f"topic {package_id} already belongs to batch {existing.batch_id}"
            )
        duplicate_slug = self._connection.execute(
            "SELECT id FROM topics WHERE slug = ? AND id <> ?", (slug, package_id)
        ).fetchone()
        if duplicate_slug:
            raise PipelineError(f"slug {slug!r} is already registered to {duplicate_slug['id']}")
        fingerprint = " ".join(sorted(token_set(f"{title} {central_question} {central_fact}")))
        self._connection.execute(
            """
            INSERT INTO topics
                (id, slug, batch_id, title, central_question, central_fact,
                 source_ids, fingerprint, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slug=excluded.slug,
                batch_id=excluded.batch_id,
                title=excluded.title,
                central_question=excluded.central_question,
                central_fact=excluded.central_fact,
                source_ids=excluded.source_ids,
                fingerprint=excluded.fingerprint,
                status=excluded.status
            """,
            (
                package_id,
                slug,
                batch_id,
                title,
                central_question,
                central_fact,
                json.dumps(list(source_ids), ensure_ascii=False),
                fingerprint,
                status,
                created_at or utc_now_iso(),
            ),
        )
        self._connection.commit()

    def register_batch(
        self,
        *,
        batch_id: str,
        package_count: int,
        status: str,
        created_at: str | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO batches (batch_id, package_count, status, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(batch_id) DO UPDATE SET
                package_count=excluded.package_count,
                status=excluded.status
            """,
            (batch_id, package_count, status, created_at or utc_now_iso()),
        )
        self._connection.commit()

    # --- export ---------------------------------------------------------

    def export(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.export_path
        if target is None:
            raise PipelineError("no history export path configured")
        topics = []
        for topic in self.topics():
            topics.append(
                {
                    "id": topic.id,
                    "slug": topic.slug,
                    "batch_id": topic.batch_id,
                    "title": topic.title,
                    "central_question": topic.central_question,
                    "central_fact": topic.central_fact,
                    "source_ids": list(topic.source_ids),
                    "status": topic.status,
                    "created_at": topic.created_at,
                }
            )
        batches = [
            dict(row)
            for row in self._connection.execute(
                "SELECT batch_id, package_count, status, created_at FROM batches ORDER BY created_at, batch_id"
            ).fetchall()
        ]
        payload = {
            "schema_version": 1,
            "description": "Committed topic history for cross-batch duplicate detection.",
            "topics": topics,
            "batches": batches,
        }
        write_json_if_changed(target, payload)
        return target

    def summary(self) -> dict:
        topic_count = self._connection.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        batch_count = self._connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        return {"topics": topic_count, "batches": batch_count, "db": str(self.db_path)}
