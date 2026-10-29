"""Explicit ViewMade tool binding and render refusal before binding."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from ._support import copy_project
except ImportError:  # pragma: no cover
    from _support import copy_project

from cddocs.config import Settings
from cddocs.util import PipelineError, read_json
from cddocs.viewmade.adapter import (
    ViewMadeAdapter,
    ViewMadeBlocked,
    _extract_path,
    _resolve_placeholders,
    _script_lines,
    _tool_payload,
)


def _discovery() -> dict:
    return {
        "endpoint": "https://mcp.viewmade.com/mcp",
        "provider": "viewmade",
        "tools": [
            {
                "name": "render_video",
                "description": "Synthetic test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "duration": {"type": "number"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "render_status",
                "description": "Synthetic test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
            {
                "name": "download_render",
                "description": "Synthetic test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
        ],
    }


class BindingTests(unittest.TestCase):
    def test_existing_provider_job_blocks_a_second_paid_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            request_path = project.package_path("dog-guilty-look") / "viewmade-request.json"
            payload = read_json(request_path)
            payload.update(
                {
                    "status": "FAILED",
                    "job_id": "f59f8a91-7b2b-4dbb-a03d-62effc911581",
                    "provider_state": "ready",
                    "render_path": None,
                }
            )
            request_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            adapter = ViewMadeAdapter(project)
            with self.assertRaises(ViewMadeBlocked) as caught:
                adapter.render(payload)
            self.assertIn("Do not submit a second paid render", str(caught.exception))

    def test_structured_mcp_content_is_unwrapped(self) -> None:
        response = {
            "content": [{"type": "text", "text": '{"video_id": "74955fe4"}'}],
            "structuredContent": {
                "data": {
                    "video_id": "74955fe4-199a-49e3-bf8c-305d7ba0c36c",
                    "status": "rendering",
                }
            },
        }
        payload = _tool_payload(response)
        self.assertEqual(payload["status"], "rendering")
        self.assertEqual(
            _extract_path(payload, ["video_id"]),
            "74955fe4-199a-49e3-bf8c-305d7ba0c36c",
        )

    def test_update_request_keeps_prior_fields_for_later_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp))
            request_path = project.package_path("cat-sweetness") / "viewmade-request.json"
            payload = read_json(request_path)
            adapter = ViewMadeAdapter(project)
            adapter._update_request(
                "cat-sweetness",
                payload,
                status="SUBMITTED",
                error=None,
                submission={"submitted_at": "2026-10-29T03:40:34Z"},
            )
            adapter._update_request(
                "cat-sweetness",
                payload,
                status="RENDERING",
                provider_state="rendering",
            )
            saved = read_json(request_path)
            self.assertEqual(saved["status"], "RENDERING")
            self.assertEqual(saved["provider_state"], "rendering")
            self.assertIsNone(saved["error"])
            self.assertEqual(
                saved["submission"]["submitted_at"], "2026-10-29T03:40:34Z"
            )

    def test_package_id_placeholder_is_available(self) -> None:
        resolved = _resolve_placeholders(
            {"operation_key": "$package_id"},
            {"package_id": "dog-guilty-look"},
        )
        self.assertEqual(resolved, {"operation_key": "dog-guilty-look"})

    def test_script_lines_are_limited_and_keep_all_words(self) -> None:
        narration = "One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten. Eleven. Twelve. Thirteen. Fourteen."
        script = _script_lines(narration)
        self.assertLessEqual(len(script.splitlines()), 12)
        self.assertEqual(script.replace("\n", " "), narration)
        self.assertEqual(_script_lines("Only one sentence."), "Only one sentence.")

    def test_render_is_blocked_before_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp))
            adapter = ViewMadeAdapter(
                project,
                Settings(mcp_token=None, live_confirm="", state_dir=project.state_dir),
            )
            with self.assertRaises(ViewMadeBlocked):
                adapter.render({"package_id": "dog-guilty-look"})

    def test_bind_validates_names_required_arguments_and_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp))
            project.viewmade_tools_file.parent.mkdir(parents=True, exist_ok=True)
            project.viewmade_tools_file.write_text(
                json.dumps(_discovery()),
                encoding="utf-8",
            )
            adapter = ViewMadeAdapter(
                project,
                Settings(mcp_token=None, live_confirm="", state_dir=project.state_dir),
            )
            render_template = {"prompt": "$prompt", "duration": "$duration_s"}
            status_template = {"job_id": "$job_id"}
            download_template = {"job_id": "$job_id"}

            with self.assertRaises(PipelineError) as caught:
                adapter.bind(
                    render_tool="not-a-discovered-tool",
                    status_tool="render_status",
                    download_tool="download_render",
                    templates={
                        "render": render_template,
                        "status": status_template,
                        "download": download_template,
                    },
                )
            self.assertIn("not in the discovered tool list", str(caught.exception))

            with self.assertRaises(PipelineError) as caught:
                adapter.bind(
                    render_tool="render_video",
                    status_tool="render_status",
                    download_tool="download_render",
                    templates={
                        "render": {"duration": "$duration_s"},
                        "status": status_template,
                        "download": download_template,
                    },
                )
            self.assertIn("missing required tool argument", str(caught.exception))

            with self.assertRaises(PipelineError) as caught:
                adapter.bind(
                    render_tool="render_video",
                    status_tool="render_status",
                    download_tool="download_render",
                    templates={
                        "render": {"prompt": "$unknown_placeholder", "duration": "$duration_s"},
                        "status": status_template,
                        "download": download_template,
                    },
                )
            self.assertIn("unknown placeholder", str(caught.exception))

            binding = adapter.bind(
                render_tool="render_video",
                status_tool="render_status",
                download_tool="download_render",
                templates={
                    "render": render_template,
                    "status": status_template,
                    "download": download_template,
                },
                job_id_path=["data", "job_id"],
                provider_state_path=["data", "state"],
                download_url_path=["data", "url"],
            )
            self.assertEqual(binding["tools"]["render"]["name"], "render_video")
            self.assertTrue(project.viewmade_binding_file.is_file())
            self.assertTrue(adapter.binding_complete())
            self.assertEqual(adapter.status()["bound"], True)
            self.assertEqual(adapter.status()["authenticated"], False)
            self.assertIsNone(adapter.status()["scope"])

    def test_template_key_outside_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp))
            project.viewmade_tools_file.parent.mkdir(parents=True, exist_ok=True)
            project.viewmade_tools_file.write_text(
                json.dumps(_discovery()),
                encoding="utf-8",
            )
            adapter = ViewMadeAdapter(
                project,
                Settings(mcp_token=None, live_confirm="", state_dir=project.state_dir),
            )
            with self.assertRaises(PipelineError) as caught:
                adapter.bind(
                    render_tool="render_video",
                    status_tool="render_status",
                    download_tool="download_render",
                    templates={
                        "render": {"prompt": "$prompt", "model": "unknown"},
                        "status": {"job_id": "$job_id"},
                        "download": {"job_id": "$job_id"},
                    },
                )
            self.assertIn("is not in the tool schema", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
