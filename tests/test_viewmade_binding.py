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
from cddocs.util import PipelineError
from cddocs.viewmade.adapter import ViewMadeAdapter, ViewMadeBlocked


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
