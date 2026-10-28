"""Schema files parse and cover the top-level fields of checked-in artifacts."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

try:
    from ._support import BATCH_ID, ROOT, load_json
except ImportError:  # pragma: no cover
    from _support import ROOT, BATCH_ID, load_json


SCHEMA_NAMES = {
    "package.schema.json",
    "research.schema.json",
    "batch.schema.json",
    "metadata.schema.json",
    "qa-report.schema.json",
    "viewmade-request.schema.json",
    "viewmade-binding.schema.json",
    "viewmade-discovery.schema.json",
    "history.schema.json",
}


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema_dir = ROOT / "schemas"
        cls.schemas = {
            path.name: load_json(path)
            for path in sorted(cls.schema_dir.glob("*.schema.json"))
        }

    def test_schema_files_exist_and_parse(self) -> None:
        self.assertTrue(SCHEMA_NAMES.issubset(self.schemas))
        for name in SCHEMA_NAMES:
            with self.subTest(schema=name):
                schema = self.schemas[name]
                self.assertIsInstance(schema, dict)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["type"], "object")
                self.assertIsInstance(schema["required"], list)
                self.assertTrue(schema["required"])
                for key in schema["required"]:
                    self.assertIn(key, schema["properties"])
                self.assertIn("$id", schema)

    def test_current_artifacts_cover_schema_required_fields(self) -> None:
        package = load_json(ROOT / "content" / "packages" / "dog-guilty-look" / "package.json")
        research = load_json(ROOT / "content" / "packages" / "dog-guilty-look" / "research.json")
        metadata = load_json(ROOT / "content" / "packages" / "dog-guilty-look" / "metadata.json")
        qa = load_json(ROOT / "content" / "packages" / "dog-guilty-look" / "qa-report.json")
        request = load_json(ROOT / "content" / "packages" / "dog-guilty-look" / "viewmade-request.json")
        batch = load_json(ROOT / "content" / "batches" / BATCH_ID / "batch.json")
        history = load_json(ROOT / "state" / "history.json")
        pairs = {
            "package.schema.json": package,
            "research.schema.json": research,
            "metadata.schema.json": metadata,
            "qa-report.schema.json": qa,
            "viewmade-request.schema.json": request,
            "batch.schema.json": batch,
            "history.schema.json": history,
        }
        for name, record in pairs.items():
            with self.subTest(schema=name):
                missing = [key for key in self.schemas[name]["required"] if key not in record]
                self.assertEqual(missing, [], f"{name} is missing required top-level fields")

    def test_binding_schema_declares_the_three_required_operations(self) -> None:
        binding = self.schemas["viewmade-binding.schema.json"]
        tools = binding["properties"]["tools"]
        self.assertEqual(set(tools["properties"]), {"render", "status", "download"})
        self.assertEqual(set(tools["required"]), {"render", "status", "download"})
        self.assertEqual(tools["additionalProperties"], False)


if __name__ == "__main__":
    unittest.main()
