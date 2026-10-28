"""Minimal, official MCP Streamable HTTP client.

Only the standard MCP JSON-RPC methods are used: ``initialize``,
``notifications/initialized``, ``tools/list``, and ``tools/call``. The client
supports JSON and SSE responses, preserves ``Mcp-Session-Id``, and never
hardcodes provider tool names.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..util import PipelineError, utc_now_iso


class MCPError(PipelineError):
    """An expected MCP transport or protocol failure."""


class MCPAuthError(MCPError):
    """The MCP server rejected the bearer token."""


@dataclass
class MCPResponse:
    status: int
    headers: dict[str, str]
    data: dict[str, Any] | None
    raw: str = ""


def iter_sse_data(lines: Iterable[bytes | str]) -> Iterable[str]:
    """Yield ``data:`` payloads from a text/event-stream response."""
    buffer: list[str] = []
    for raw_line in lines:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="replace")
        else:
            line = raw_line
        line = line.rstrip("\r\n")
        if line == "":
            if buffer:
                yield "\n".join(buffer)
                buffer = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            buffer.append(value)
    if buffer:
        yield "\n".join(buffer)


def _auth_error(connect_url: str, status: int, detail: str = "") -> MCPAuthError:
    suffix = f" ({detail})" if detail else ""
    return MCPAuthError(
        f"ViewMade MCP returned HTTP {status}{suffix}. Run `cddocs viewmade login` "
        f"or connect at {connect_url}, then retry. No token is printed by this tool."
    )


class HTTPTransport:
    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 60.0,
        connect_url: str = "https://viewmade.com/dashboard/connect",
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.connect_url = connect_url

    def request(
        self,
        payload: dict,
        headers: dict[str, str],
        response_id: int | None,
    ) -> MCPResponse:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "cddocs/0.1 (+cats-dogs-documentary)",
            **headers,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers=request_headers,
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raw = exc.read()[:6000].decode("utf-8", errors="replace")
            if exc.code == 401:
                raise _auth_error(self.connect_url, 401, _short_error(raw)) from exc
            if exc.code == 403:
                raise MCPError(
                    f"ViewMade MCP returned HTTP 403. Check that the account has API/MCP access "
                    f"and the granted scopes cover this operation. {_short_error(raw)}"
                ) from exc
            raise MCPError(f"ViewMade MCP returned HTTP {exc.code}: {_short_error(raw)}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(f"could not reach ViewMade MCP endpoint: {exc.reason}") from exc

        with response:
            status = response.status
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            content_type = response_headers.get("content-type", "")
            if status in (202, 204):
                response.read()
                return MCPResponse(status, response_headers, None)
            if "text/event-stream" in content_type:
                data = self._read_sse(response, response_id)
                return MCPResponse(status, response_headers, data)
            raw_bytes = response.read()
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            if not raw_text.strip():
                return MCPResponse(status, response_headers, None)
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise MCPError(
                    f"ViewMade MCP returned non-JSON content ({content_type or 'unknown'}): "
                    f"{raw_text[:300]!r}"
                ) from exc
            if not isinstance(parsed, dict):
                raise MCPError("ViewMade MCP JSON response is not an object")
            return MCPResponse(status, response_headers, parsed, raw_text)

    def _read_sse(self, response: Any, response_id: int | None) -> dict:
        seen: list[dict] = []
        for data in iter_sse_data(response):
            if not data.strip():
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            seen.append(parsed)
            if response_id is not None and parsed.get("id") == response_id:
                return parsed
            if response_id is None and ("result" in parsed or "error" in parsed):
                return parsed
        if seen:
            # A provider may omit ids on a single response. Prefer a response
            # shaped message over a notification, but never accept a response
            # that carries a different request id.
            for message in seen:
                if "result" not in message and "error" not in message:
                    continue
                message_id = message.get("id")
                if response_id is not None and message_id not in (None, response_id):
                    continue
                return message
        raise MCPError("ViewMade MCP SSE stream ended without a matching JSON-RPC response")


def _short_error(raw: str) -> str:
    raw = raw.strip().replace("\n", " ")
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)[:300]
            if error:
                return str(error)[:300]
            if parsed.get("message"):
                return str(parsed["message"])[:300]
    except json.JSONDecodeError:
        pass
    return raw[:300]


class MCPClient:
    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        protocol_version: str = "2025-06-18",
        timeout: float = 60.0,
        connect_url: str = "https://viewmade.com/dashboard/connect",
        transport: Any | None = None,
    ):
        if not endpoint.startswith("https://"):
            raise MCPError("MCP endpoint must be https")
        if not token:
            raise MCPAuthError(
                f"ViewMade MCP token is missing. Run `cddocs viewmade login` or connect at {connect_url}."
            )
        self.endpoint = endpoint
        self.token = token
        self.requested_protocol_version = protocol_version
        self.protocol_version: str | None = None
        self.session_id: str | None = None
        self.server_info: dict = {}
        self.server_capabilities: dict = {}
        self._next_id = 1
        self._transport = transport or HTTPTransport(
            endpoint, timeout=timeout, connect_url=connect_url
        )
        self._connect_url = connect_url

    # --- core JSON-RPC --------------------------------------------------

    def _headers(self, *, initialize: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version and not initialize:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _rpc(self, method: str, params: dict | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        response = self._transport.request(
            payload,
            self._headers(initialize=method == "initialize"),
            request_id,
        )
        if response.status in (401, 403):
            raise _auth_error(self._connect_url, response.status)
        if response.status >= 400:
            raise MCPError(f"ViewMade MCP returned HTTP {response.status} for {method}")
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.session_id = session_id
        data = response.data
        if not isinstance(data, dict):
            raise MCPError(f"empty MCP response for {method}")
        if data.get("error") is not None:
            error = data["error"]
            if isinstance(error, dict):
                raise MCPError(
                    f"MCP error in {method}: {error.get('message') or error} "
                    f"(code {error.get('code')})"
                )
            raise MCPError(f"MCP error in {method}: {error}")
        if data.get("id") not in (None, request_id):
            raise MCPError(
                f"MCP response id mismatch for {method}: {data.get('id')!r} != {request_id}"
            )
        if "result" not in data:
            raise MCPError(f"MCP response for {method} has no result")
        return data["result"]

    def _notify(self, method: str, params: dict | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        response = self._transport.request(
            payload,
            self._headers(initialize=False),
            None,
        )
        if response.status in (401, 403):
            raise _auth_error(self._connect_url, response.status)
        if response.status >= 400:
            raise MCPError(f"ViewMade MCP returned HTTP {response.status} for {method}")
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.session_id = session_id

    # --- lifecycle ------------------------------------------------------

    def initialize(self) -> dict:
        if self.protocol_version:
            raise MCPError("MCP client is already initialized")
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": self.requested_protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "cddocs", "version": "0.1.0"},
            },
        )
        if not isinstance(result, dict):
            raise MCPError("MCP initialize result is not an object")
        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str) or not negotiated:
            raise MCPError("MCP initialize result has no protocolVersion")
        self.protocol_version = negotiated
        self.server_info = result.get("serverInfo") or {}
        self.server_capabilities = result.get("capabilities") or {}
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        if not self.protocol_version:
            self.initialize()
        tools: list[dict] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._rpc("tools/list", params)
            if not isinstance(result, dict):
                raise MCPError("tools/list result is not an object")
            page = result.get("tools")
            if not isinstance(page, list):
                raise MCPError("tools/list result has no tools array")
            for tool in page:
                if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                    raise MCPError("tools/list returned a tool without a name")
                tools.append(tool)
            next_cursor = result.get("nextCursor")
            if not next_cursor:
                break
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                raise MCPError("tools/list pagination cursor is invalid or repeating")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            if len(tools) > 500:
                raise MCPError("tools/list returned too many tools; refusing to continue")
        return tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        if not isinstance(name, str) or not name:
            raise MCPError("tool name is required")
        if not isinstance(arguments, dict):
            raise MCPError("tool arguments must be an object")
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            raise MCPError("tools/call result is not an object")
        if result.get("isError") is True:
            content = result.get("content") or []
            raise MCPError(f"MCP tool {name!r} returned an error: {content}")
        return result

    # --- discovery ------------------------------------------------------

    def discover(self) -> dict:
        init = self.initialize()
        tools = self.list_tools()
        return {
            "endpoint": self.endpoint,
            "fetched_at": utc_now_iso(),
            "protocol_version": self.protocol_version,
            "server_info": self.server_info,
            "capabilities": self.server_capabilities,
            "session_id_present": bool(self.session_id),
            "tools": tools,
            "initialize": init,
        }

    def close(self) -> None:
        # Streamable HTTP is stateless at the client; a server-side session may
        # exist but the MCP standard has no universal DELETE requirement.
        self.session_id = None


def tool_names(discovery: dict) -> list[str]:
    return sorted(
        str(tool.get("name"))
        for tool in discovery.get("tools", [])
        if isinstance(tool, dict) and tool.get("name")
    )


def find_tool(discovery: dict, name: str) -> dict | None:
    for tool in discovery.get("tools", []):
        if isinstance(tool, dict) and tool.get("name") == name:
            return tool
    return None
