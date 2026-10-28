"""MCP JSON/SSE transport and JSON-RPC lifecycle behavior."""
from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

try:
    from ._support import ROOT  # noqa: F401
except ImportError:  # pragma: no cover
    from _support import ROOT  # noqa: F401

from cddocs.viewmade.mcp import (
    HTTPTransport,
    MCPAuthError,
    MCPClient,
    MCPError,
    MCPResponse,
    find_tool,
    iter_sse_data,
    tool_names,
)


class FakeResponse:
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
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, payload, headers, response_id):
        self.calls.append((payload, headers, response_id))
        if not self.responses:
            raise AssertionError("fake transport ran out of responses")
        return self.responses.pop(0)


def _json_rpc(request_id: int, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


class SSEParsingTests(unittest.TestCase):
    def test_iter_sse_data_handles_comments_multiline_and_tail(self) -> None:
        lines = [
            b": keepalive\n",
            b"event: message\n",
            b'data: {"a": 1}\n',
            b'data: {"b": 2}\n',
            b"\n",
            b"data: tail\n",
        ]
        self.assertEqual(
            list(iter_sse_data(lines)),
            ['{"a": 1}\n{"b": 2}', "tail"],
        )

    def test_read_sse_selects_matching_id_and_rejects_missing_match(self) -> None:
        transport = HTTPTransport("https://mcp.example.invalid/mcp")
        response = FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[
                b": comment\n",
                b'data: {"jsonrpc": "2.0", "method": "notifications/progress"}\n',
                b"\n",
                b'data: {"jsonrpc": "2.0", "id": 9, "result": {"ok": true}}\n',
                b"\n",
            ],
        )
        data = transport._read_sse(response, 9)
        self.assertEqual(data["id"], 9)
        self.assertTrue(data["result"]["ok"])

        no_match = FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[b'data: {"jsonrpc": "2.0", "id": 3, "result": {}}\n', b"\n"],
        )
        with self.assertRaises(MCPError):
            transport._read_sse(no_match, 9)

        omitted_id = FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[b'data: {"jsonrpc": "2.0", "result": {"ok": true}}\n', b"\n"],
        )
        data = transport._read_sse(omitted_id, 9)
        self.assertEqual(data["result"], {"ok": True})

    def test_read_sse_falls_back_to_result_without_id(self) -> None:
        transport = HTTPTransport("https://mcp.example.invalid/mcp")
        response = FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[b'data: {"jsonrpc": "2.0", "result": {"ok": true}}\n', b"\n"],
        )
        data = transport._read_sse(response, None)
        self.assertEqual(data["result"], {"ok": True})


class HTTPTransportTests(unittest.TestCase):
    def test_json_response(self) -> None:
        transport = HTTPTransport("https://mcp.example.invalid/mcp")
        fake = FakeResponse(
            body=b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}',
            headers={"Content-Type": "application/json"},
        )
        with mock.patch("urllib.request.urlopen", return_value=fake) as opened:
            result = transport.request(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {"Authorization": "Bearer test-token"},
                1,
            )
        self.assertEqual(result.status, 200)
        self.assertEqual(result.data["result"], {"tools": []})
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn(b"tools/list", request.data)

    def test_sse_response(self) -> None:
        transport = HTTPTransport("https://mcp.example.invalid/mcp")
        fake = FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[
                b": ping\n",
                b'data: {"jsonrpc":"2.0","id":4,"result":{"status":"ok"}}\n',
                b"\n",
            ],
        )
        with mock.patch("urllib.request.urlopen", return_value=fake):
            result = transport.request(
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call"},
                {"Authorization": "Bearer test-token"},
                4,
            )
        self.assertEqual(result.data["id"], 4)
        self.assertEqual(result.data["result"]["status"], "ok")

    def test_401_becomes_auth_guidance_error(self) -> None:
        transport = HTTPTransport(
            "https://mcp.example.invalid/mcp",
            connect_url="https://viewmade.com/dashboard/connect",
        )
        error = urllib.error.HTTPError(
            "https://mcp.example.invalid/mcp",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"invalid_token"}'),
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(MCPAuthError) as caught:
                transport.request({"jsonrpc": "2.0", "method": "initialize"}, {}, 1)
        self.assertIn("viewmade.com/dashboard/connect", str(caught.exception))
        self.assertNotIn("test-token", str(caught.exception))


class MCPClientTests(unittest.TestCase):
    def test_initialize_list_and_call_preserve_session_and_headers(self) -> None:
        transport = FakeTransport(
            [
                MCPResponse(
                    200,
                    {"mcp-session-id": "session-1"},
                    _json_rpc(
                        1,
                        {
                            "protocolVersion": "2025-06-18",
                            "serverInfo": {"name": "fake"},
                            "capabilities": {"tools": {}},
                        },
                    ),
                ),
                MCPResponse(202, {}, None),
                MCPResponse(
                    200,
                    {},
                    _json_rpc(
                        2,
                        {
                            "tools": [
                                {
                                    "name": "render",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {"prompt": {"type": "string"}},
                                        "required": ["prompt"],
                                    },
                                }
                            ]
                        },
                    ),
                ),
                MCPResponse(
                    200,
                    {},
                    _json_rpc(3, {"content": [{"type": "text", "text": "accepted"}], "isError": False}),
                ),
            ]
        )
        client = MCPClient("https://mcp.example.invalid/mcp", "test-token", transport=transport)
        init = client.initialize()
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertEqual(client.session_id, "session-1")
        self.assertEqual(tool_names({"tools": client.list_tools()}), ["render"])
        result = client.call_tool("render", {"prompt": "hello"})
        self.assertFalse(result["isError"])

        methods = [call[0].get("method") for call in transport.calls]
        self.assertEqual(
            methods,
            ["initialize", "notifications/initialized", "tools/list", "tools/call"],
        )
        for _payload, headers, _response_id in transport.calls:
            self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(transport.calls[2][1]["Mcp-Session-Id"], "session-1")
        self.assertEqual(transport.calls[2][1]["MCP-Protocol-Version"], "2025-06-18")
        self.assertEqual(transport.calls[3][0]["params"], {"name": "render", "arguments": {"prompt": "hello"}})

    def test_tool_error_is_raised_not_returned_as_success(self) -> None:
        transport = FakeTransport(
            [
                MCPResponse(
                    200,
                    {},
                    _json_rpc(
                        1,
                        {
                            "protocolVersion": "2025-06-18",
                            "serverInfo": {},
                            "capabilities": {},
                        },
                    ),
                ),
                MCPResponse(202, {}, None),
                MCPResponse(
                    200,
                    {},
                    _json_rpc(
                        2,
                        {
                            "content": [{"type": "text", "text": "bad request"}],
                            "isError": True,
                        },
                    ),
                ),
            ]
        )
        client = MCPClient("https://mcp.example.invalid/mcp", "token", transport=transport)
        client.initialize()
        with self.assertRaises(MCPError) as caught:
            client.call_tool("render", {})
        self.assertIn("returned an error", str(caught.exception))

    def test_missing_token_is_refused(self) -> None:
        with self.assertRaises(MCPAuthError):
            MCPClient("https://mcp.example.invalid/mcp", "")

    def test_find_tool(self) -> None:
        discovery = {"tools": [{"name": "a"}, {"name": "b"}]}
        self.assertEqual(find_tool(discovery, "b")["name"], "b")
        self.assertIsNone(find_tool(discovery, "missing"))


if __name__ == "__main__":
    unittest.main()
