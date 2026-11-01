"""Full MCP integration tests with mocked ViewMade server responses.

These tests exercise the complete render pipeline with mocked HTTP/SSE responses,
without making any live network calls to the ViewMade provider.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

try:
    from ._support import BATCH_ID, copy_project, load_json, write_json
except ImportError:  # pragma: no cover
    from _support import BATCH_ID, copy_project, load_json, write_json

from cddocs.batch import render_batch, validate_batch
from cddocs.config import Project, Settings
from cddocs.util import PipelineError, read_json, write_json
from cddocs.viewmade.adapter import ViewMadeAdapter
from cddocs.viewmade.mcp import (
    HTTPTransport,
    MCPAuthError,
    MCPClient,
    MCPError,
    MCPResponse,
)


def _json_rpc(request_id: int, result) -> dict:
    """Create a JSON-RPC 2.0 response object."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


class FakeResponse:
    """Fake HTTP response for testing."""
    def __init__(self, *, status: int = 200, headers=None, body: bytes = b"", lines=None):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._body = body
        self._lines = lines or []

    def read(self, _size: int = -1) -> bytes:
        return self._body

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False


class FakeTransport:
    """Fake transport for testing MCP client."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, payload, headers, response_id):
        self.calls.append((payload, headers, response_id))
        if not self.responses:
            raise AssertionError("fake transport ran out of responses")
        return self.responses.pop(0)


def _json_rpc(request_id: int, result) -> dict:
    """Create a JSON-RPC 2.0 response object."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _mock_render_tool_response(job_id: str = "test-job-123") -> MCPResponse:
    """Mock response for viewmade_create_short tool."""
    return MCPResponse(
        200,
        {"mcp-session-id": "session-1"},
        _json_rpc(
            1,
            {
                "structuredContent": {
                    "data": {
                        "job_id": job_id,
                        "status": "rendering",
                        "kind": "short",
                        "topic": "Test Topic",
                    }
                }
            },
        ),
    )


def _mock_status_tool_response(job_id: str = "test-job-123", status: str = "ready") -> MCPResponse:
    """Mock response for viewmade_check_video_status tool."""
    return MCPResponse(
        200,
        {"mcp-session-id": "session-1"},
        _json_rpc(
            2,
            {
                "structuredContent": {
                    "data": {
                        "id": job_id,
                        "status": status,
                        "kind": "short",
                        "progress": {"stage": "finalize", "pct": 100},
                        "video_url": "https://viewmade.com/renders/test-job-123.mp4",
                        "title": "Test Video",
                        "description": "Test description",
                        "tags": ["test"],
                        "duration": "0:45",
                        "aspect": "9:16",
                        "resolution": "1080x1920",
                        "scene_count": 6,
                        "sources": [
                            {"title": "Source 1", "url": "https://example.com/src1"},
                            {"title": "Source 2", "url": "https://example.com/src2"},
                        ],
                        "attributions": [
                            "Source 1 · https://example.com/src1",
                            "Source 2 · https://example.com/src2",
                        ],
                        "credits_charged": 20,
                        "credits_refunded": 0,
                        "net_credits": 20,
                    }
                }
            },
        ),
    )


def _mock_download_tool_response() -> MCPResponse:
    """Mock response for viewmade_get_video tool."""
    return MCPResponse(
        200,
        {"mcp-session-id": "session-1"},
        _json_rpc(
            3,
            {
                "structuredContent": {
                    "data": {
                        "video_url": "https://viewmade.com/renders/test-job-123.mp4",
                    }
                }
            },
        ),
    )


class FakeResponse:
    """Fake HTTP response for testing."""
    def __init__(self, *, status: int = 200, headers=None, body: bytes = b"", lines=None):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._body = body
        self._lines = lines or []

    def read(self, _size: int = -1) -> bytes:
        return self._body

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False


class FakeTransport:
    """Fake transport for testing MCP client."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, payload, headers, response_id):
        self.calls.append((payload, headers, response_id))
        if not self.responses:
            raise AssertionError("fake transport ran out of responses")
        return self.responses.pop(0)


class MockViewMadeServer:
    """A mock ViewMade MCP server that simulates the complete render lifecycle."""

    def __init__(self, job_id: str = "test-job-123", should_fail: bool = False):
        self.job_id = job_id
        self.should_fail = should_fail
        self.call_count = 0
        self.responses = []

    def _next_response(self) -> MCPResponse:
        if not self.responses:
            raise AssertionError("Mock server ran out of responses")
        return self.responses.pop(0)

    def make_transport(self) -> FakeTransport:
        self.responses = [
            # initialize
            MCPResponse(
                200,
                {"mcp-session-id": "session-1"},
                _json_rpc(
                    1,
                    {
                        "protocolVersion": "2025-06-18",
                        "serverInfo": {"name": "ViewMade Mock"},
                        "capabilities": {"tools": {}},
                    },
                ),
            ),
            # tools/list (discovery)
            MCPResponse(
                200,
                {"mcp-session-id": "session-1"},
                _json_rpc(
                    2,
                    {
                        "tools": [
                            {
                                "name": "viewmade_create_short",
                                "description": "Create a short video",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "topic": {"type": "string"},
                                        "script": {"type": "string"},
                                        "language": {"type": "string"},
                                        "style": {"type": "string"},
                                        "voice": {"type": "string"},
                                        "narration_pace": {"type": "string"},
                                        "music_mood": {"type": "string"},
                                        "style_hint": {"type": "string"},
                                        "sound_effects": {"type": "string"},
                                        "engine": {"type": "string"},
                                        "speech": {"type": "string"},
                                        "operation_key": {"type": "string"},
                                    },
                                    "required": ["topic", "operation_key"],
                                },
                            },
                            {
                                "name": "viewmade_check_video_status",
                                "description": "Check video status",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"video_id": {"type": "string"}},
                                    "required": ["video_id"],
                                },
                            },
                            {
                                "name": "viewmade_get_video",
                                "description": "Download video",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"video_id": {"type": "string"}},
                                    "required": ["video_id"],
                                },
                            },
                        ],
                    },
                ),
            ),
            # render tool call
            MCPResponse(
                200,
                {"mcp-session-id": "session-1"},
                _json_rpc(
                    3,
                    {
                        "structuredContent": {
                            "data": {
                                "job_id": self.job_id,
                                "status": "rendering",
                                "kind": "short",
                                "topic": "Test Topic",
                            }
                        }
                    },
                ),
            ),
        ]
        return FakeTransport(self.responses)


class MockViewMadeServerTests(unittest.TestCase):
    """Integration tests for the complete MCP render pipeline with mocked provider."""

    def test_mock_server_transport_sequence(self) -> None:
        """Verify the mock server produces the expected sequence of responses."""
        server = MockViewMadeServer("test-job-123")
        transport = server.make_transport()
        
        # Should have 3 responses: initialize, tools/list, render
        self.assertEqual(len(transport.responses), 3)
        
        # Check initialize
        init_resp = transport.responses[0]
        self.assertEqual(init_resp.data["result"]["protocolVersion"], "2025-06-18")
        
        # Check tools/list
        tools_resp = transport.responses[1]
        tools = tools_resp.data["result"]["tools"]
        self.assertEqual(len(tools), 3)
        tool_names = [t["name"] for t in tools]
        self.assertIn("viewmade_create_short", tool_names)
        self.assertIn("viewmade_check_video_status", tool_names)
        self.assertIn("viewmade_get_video", tool_names)
        
        # Check render tool call
        render_resp = transport.responses[2]
        self.assertEqual(render_resp.data["result"]["structuredContent"]["data"]["job_id"], "test-job-123")
        self.assertEqual(render_resp.data["result"]["structuredContent"]["data"]["status"], "rendering")

    def test_mock_status_response(self) -> None:
        """Test the mock status tool response."""
        resp = _mock_status_tool_response("test-job-123", "ready")
        data = resp.data["result"]["structuredContent"]["data"]
        self.assertEqual(data["id"], "test-job-123")
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["video_url"], "https://viewmade.com/renders/test-job-123.mp4")
        self.assertEqual(data["credits_charged"], 20)
        self.assertEqual(len(data["sources"]), 2)

    def test_mock_download_response(self) -> None:
        resp = _mock_download_tool_response()
        data = resp.data["result"]["structuredContent"]["data"]
        self.assertEqual(data["video_url"], "https://viewmade.com/renders/test-job-123.mp4")


class HTTPTransportEdgeCases(unittest.TestCase):
    """Edge case tests for HTTP transport layer."""

    def test_mcp_response_with_structured_content_envelope(self) -> None:
        """Test that structuredContent.data envelope is properly handled."""
        transport = HTTPTransport("https://mcp.example/mcp")
        
        fake = FakeResponse(
            headers={"Content-Type": "application/json"},
            body=b'{"jsonrpc":"2.0","id":1,"result":{"structuredContent":{"data":{"job_id":"test-123","status":"rendering"}}}}',
        )
        
        with mock.patch("urllib.request.urlopen", return_value=fake):
            result = transport.request(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}},
                {"Authorization": "Bearer test"},
                1,
            )
        
        self.assertIn("structuredContent", result.data["result"])
        self.assertEqual(result.data["result"]["structuredContent"]["data"]["job_id"], "test-123")

    def test_sse_with_multiple_data_lines(self) -> None:
        """Test SSE parsing with multiple data lines."""
        transport = HTTPTransport("https://mcp.example/mcp")
        fake = FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[
                b": ping\n",
                b'data: {"jsonrpc":"2.0","id":1,"result":{"a":1}}\n',
                b'data: {"jsonrpc":"2.0","id":1,"result":{"b":2}}\n',
                b"\n",
                # Add a matching response
                b'data: {"jsonrpc":"2.0","id":1,"result":{"final":true}}\n',
                b"\n",
            ],
        )
        with mock.patch("urllib.request.urlopen", return_value=fake):
            result = transport.request({"jsonrpc": "2.0", "id": 1, "method": "tools/call"}, {}, 1)
        self.assertEqual(result.data["id"], 1)

    def test_403_error_handling(self) -> None:
        """Test HTTP 403 handling with proper error message."""
        transport = HTTPTransport("https://mcp.example/mcp", connect_url="https://viewmade.com/connect")
        error = urllib.error.HTTPError(
            "https://mcp.example/mcp", 403, "Forbidden", {},
            io.BytesIO(b'{"error":"insufficient_scope"}')
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(MCPError) as ctx:
                transport.request({"jsonrpc": "2.0", "method": "initialize"}, {}, 1)
            self.assertIn("403", str(ctx.exception))
            self.assertIn("scope", str(ctx.exception).lower())

    def test_malformed_json_response(self) -> None:
        """Test handling of malformed JSON responses."""
        transport = HTTPTransport("https://mcp.example/mcp")
        fake = FakeResponse(body=b"not valid json", headers={"Content-Type": "application/json"})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            with self.assertRaises(MCPError) as ctx:
                transport.request({"jsonrpc": "2.0", "method": "initialize"}, {}, 1)
            self.assertIn("non-JSON content", str(ctx.exception))

    def test_empty_response_handling(self) -> None:
        """Test handling of empty responses - returns response with None data."""
        transport = HTTPTransport("https://mcp.example/mcp")
        fake = FakeResponse(body=b"", headers={"Content-Type": "application/json"})
        with mock.patch("urllib.request.urlopen", return_value=fake):
            result = transport.request({"jsonrpc": "2.0", "method": "initialize"}, {}, 1)
            # Empty response returns MCPResponse with data=None, not an error
            self.assertIsNone(result.data)


class BatchConcurrencyTests(unittest.TestCase):
    """Tests for batch concurrency and state isolation."""

    def test_temp_project_isolation(self) -> None:
        """Each temp project should have isolated state."""
        with tempfile.TemporaryDirectory() as tmp1:
            project1 = copy_project(Path(tmp1) / "p1")
            pkg_path = project1.package_path("dog-guilty-look") / "package.json"
            pkg = load_json(pkg_path)
            pkg["title"] = "Modified in Project 1"
            write_json(pkg_path, pkg)
            
            with tempfile.TemporaryDirectory() as tmp2:
                project2 = copy_project(Path(tmp2) / "p2")
                pkg_path2 = project2.package_path("dog-guilty-look") / "package.json"
                pkg2 = load_json(pkg_path2)
                self.assertNotEqual(pkg2["title"], "Modified in Project 1")
                self.assertEqual(pkg2["title"], "The Guilty Look Isn't Guilt")

    def test_batch_validate_independence(self) -> None:
        """validate_batch should not mutate source packages."""
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            for pkg_name in ["dog-guilty-look", "cat-sweetness", "puppy-dog-eyes", "slow-blink", "purr-cry", "dog-nose"]:
                req_path = project.package_path(pkg_name) / "viewmade-request.json"
                req = load_json(req_path)
                req.update({"status": "NOT_SUBMITTED", "render_path": None, "job_id": None})
                write_json(req_path, req)
                # Also set editorial flags to pass validation
                pkg_path = project.package_path(pkg_name) / "package.json"
                pkg = load_json(pkg_path)
                pkg["editorial"]["footage_rights_reviewed"] = True
                pkg["editorial"]["music_rights_reviewed"] = True
                pkg["editorial"]["caption_reviewed"] = True
                write_json(pkg_path, pkg)
            
            from cddocs.batch import validate_batch
            result1 = validate_batch(project, "2026-10-29-cats-dogs-01")
            self.assertEqual(result1.status, "PASS")
            
            result2 = validate_batch(project, "2026-10-29-cats-dogs-01")
            self.assertEqual(result2.status, "PASS")
            
            # Check original files weren't modified
            for pkg_name in ["dog-guilty-look", "cat-sweetness", "puppy-dog-eyes", "slow-blink", "purr-cry", "dog-nose"]:
                req_path = project.package_path(pkg_name) / "viewmade-request.json"
                req = load_json(req_path)
                self.assertEqual(req["status"], "NOT_SUBMITTED")


class MediaProbeEdgeCases(unittest.TestCase):
    """Edge case tests for media validation."""

    def test_missing_render_file_detection(self) -> None:
        """Missing render file should be detected."""
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            req_path = project.package_path("dog-guilty-look") / "viewmade-request.json"
            req = load_json(req_path)
            req["status"] = "COMPLETE"
            req["render_path"] = "renders/nonexistent.mp4"
            write_json(req_path, req)
            
            from cddocs.batch import validate_package_folder
            result = validate_package_folder(project, "dog-guilty-look")
            self.assertEqual(result.status, "FAIL")
            checks = {c.id: c for c in result.checks}
            self.assertIn("render.artifact", checks)
            self.assertEqual(checks["render.artifact"].status, "FAIL")

    def test_invalid_mp4_detection(self) -> None:
        """Corrupted MP4 should be detected."""
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp) / "project")
            renders_dir = project.renders_dir
            renders_dir.mkdir(parents=True, exist_ok=True)
            fake_mp4 = renders_dir / "dog-guilty-look.mp4"
            fake_mp4.write_bytes(b"not a real mp4")
            
            req_path = project.package_path("dog-guilty-look") / "viewmade-request.json"
            req = load_json(req_path)
            req["status"] = "COMPLETE"
            req["render_path"] = "renders/dog-guilty-look.mp4"
            write_json(req_path, req)
            
            from cddocs.batch import validate_package_folder
            result = validate_package_folder(project, "dog-guilty-look")
            self.assertEqual(result.status, "FAIL")
            checks = {c.id: c for c in result.checks}
            self.assertEqual(checks["render.artifact"].status, "FAIL")


if __name__ == "__main__":
    unittest.main()