"""Official ViewMade OAuth 2.1 authorization-code flow with PKCE.

Only documented OAuth endpoints and MCP discovery metadata are used. Tokens
are stored outside version control with best-effort private permissions. No
token, code verifier, or authorization code is ever printed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from ..config import Project, Settings
from ..util import PipelineError, read_json, utc_now_iso, write_json


class OAuthError(PipelineError):
    """An expected OAuth or discovery failure."""


@dataclass(frozen=True)
class AuthServerMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None
    revocation_endpoint: str | None
    scopes_supported: tuple[str, ...]
    code_challenge_methods_supported: tuple[str, ...]
    grant_types_supported: tuple[str, ...]

    @classmethod
    def from_json(cls, data: dict) -> "AuthServerMetadata":
        if not isinstance(data, dict):
            raise OAuthError("authorization server metadata is not a JSON object")
        required = ("issuer", "authorization_endpoint", "token_endpoint")
        missing = [key for key in required if not isinstance(data.get(key), str)]
        if missing:
            raise OAuthError(f"authorization server metadata missing: {missing}")
        for key in ("issuer", "authorization_endpoint", "token_endpoint"):
            if not data[key].startswith("https://"):
                raise OAuthError(f"authorization server {key} must be https")
        methods = data.get("code_challenge_methods_supported") or []
        if not isinstance(methods, list):
            methods = []
        scopes = data.get("scopes_supported") or []
        if not isinstance(scopes, list):
            scopes = []
        grants = data.get("grant_types_supported") or ["authorization_code"]
        if not isinstance(grants, list):
            grants = ["authorization_code"]
        return cls(
            issuer=data["issuer"].rstrip("/"),
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            registration_endpoint=data.get("registration_endpoint"),
            revocation_endpoint=data.get("revocation_endpoint"),
            scopes_supported=tuple(str(item) for item in scopes),
            code_challenge_methods_supported=tuple(str(item) for item in methods),
            grant_types_supported=tuple(str(item) for item in grants),
        )

    def require_pkce_s256(self) -> None:
        if "S256" not in self.code_challenge_methods_supported:
            raise OAuthError(
                "the ViewMade authorization server does not advertise S256 PKCE; refusing to continue"
            )


@dataclass(frozen=True)
class ProtectedResource:
    resource: str | None
    authorization_servers: tuple[str, ...]


def _request_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    allow_empty: bool = False,
) -> dict:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "cddocs/0.1 (+cats-dogs-documentary)",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read()[:4000]
        detail = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                detail = str(parsed.get("error_description") or parsed.get("error") or parsed)
        except json.JSONDecodeError:
            pass
        raise OAuthError(f"HTTP {exc.code} from {url}: {detail[:600]}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"could not reach {url}: {exc.reason}") from exc
    if not raw:
        if allow_empty:
            return {}
        raise OAuthError(f"empty response from {url}")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthError(
            f"expected JSON from {url}, got {content_type or 'unknown content type'}"
        ) from exc
    if not isinstance(parsed, dict):
        raise OAuthError(f"expected a JSON object from {url}")
    return parsed


def discover_authorization_server(metadata_url: str, *, timeout: float = 30.0) -> AuthServerMetadata:
    return AuthServerMetadata.from_json(_request_json(metadata_url, timeout=timeout))


def discover_protected_resource(url: str, *, timeout: float = 30.0) -> ProtectedResource:
    data = _request_json(url, timeout=timeout)
    servers = data.get("authorization_servers") or []
    if not isinstance(servers, list):
        servers = []
    resource = data.get("resource")
    return ProtectedResource(
        resource=str(resource) if isinstance(resource, str) else None,
        authorization_servers=tuple(str(server) for server in servers),
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge) per RFC 7636."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_authorize_url(
    metadata: AuthServerMetadata,
    *,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    code_challenge: str,
    resource: str | None = None,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if resource:
        params["resource"] = resource
    separator = "&" if "?" in metadata.authorization_endpoint else "?"
    return f"{metadata.authorization_endpoint}{separator}{urllib.parse.urlencode(params)}"


def _private_write(path: Path, payload: dict) -> None:
    write_json(path, payload)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_client(project: Project) -> dict | None:
    path = project.viewmade_client_file
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except PipelineError:
        return None
    return data if isinstance(data, dict) else None


def register_client(
    project: Project,
    metadata: AuthServerMetadata,
    *,
    redirect_uri: str,
    client_name: str,
    scopes: list[str],
    force: bool = False,
) -> dict:
    existing = load_client(project)
    if (
        existing
        and not force
        and existing.get("redirect_uri") == redirect_uri
        and existing.get("scopes") == scopes
        and existing.get("issuer") == metadata.issuer
        and existing.get("client_id")
    ):
        return existing
    if not metadata.registration_endpoint:
        raise OAuthError(
            "the ViewMade authorization server does not advertise dynamic client registration"
        )
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": [
            grant
            for grant in ("authorization_code", "refresh_token")
            if grant in metadata.grant_types_supported
        ]
        or ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": " ".join(scopes),
    }
    data = _request_json(
        metadata.registration_endpoint,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    client_id = data.get("client_id")
    if not isinstance(client_id, str) or not client_id:
        raise OAuthError("dynamic client registration returned no client_id")
    record = {
        "issuer": metadata.issuer,
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "token_endpoint_auth_method": data.get("token_endpoint_auth_method", "none"),
        "registration_client_uri": data.get("registration_client_uri"),
        "created_at": utc_now_iso(),
        "note": "Public OAuth client registered through official dynamic client registration. No client secret is expected.",
    }
    _private_write(project.viewmade_client_file, record)
    return record


class _CallbackHandler(BaseHTTPRequestHandler):
    server: "_CallbackServer"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Silence the default request logging: callback URLs contain a code.
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.server.callback_path:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        params = urllib.parse.parse_qs(parsed.query)
        error = params.get("error", [None])[0]
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        if error:
            description = params.get("error_description", [error])[0]
            self.server.fail(f"authorization error: {description}")
            self._respond(400, "ViewMade authorization failed. Return to the terminal for details.")
            return
        if not state or not secrets.compare_digest(state, self.server.expected_state):
            self.server.fail("OAuth state mismatch; the callback was ignored")
            self._respond(400, "OAuth state mismatch. Return to the terminal and try again.")
            return
        issuer = params.get("iss", [None])[0]
        if issuer and issuer.rstrip("/") != self.server.expected_issuer.rstrip("/"):
            self.server.fail(f"OAuth issuer mismatch: {issuer!r}")
            self._respond(400, "OAuth issuer mismatch. Return to the terminal and try again.")
            return
        if not code:
            self.server.fail("authorization callback had no code")
            self._respond(400, "No authorization code received.")
            return
        self.server.succeed(code)
        self._respond(
            200,
            "ViewMade connected. You can close this tab and return to the terminal.",
        )

    def _respond(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html><head><meta charset='utf-8'><title>ViewMade OAuth</title>"
            "<style>body{font-family:system-ui;max-width:38rem;margin:4rem auto;padding:0 1.5rem;"
            "line-height:1.5}</style></head><body><h1>ViewMade OAuth</h1>"
            f"<p>{message}</p></body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _CallbackServer(HTTPServer):
    expected_state: str
    expected_issuer: str
    callback_path: str
    result: dict
    done: threading.Event

    def succeed(self, code: str) -> None:
        if not self.done.is_set():
            self.result = {"code": code}
            self.done.set()

    def fail(self, message: str) -> None:
        if not self.done.is_set():
            self.result = {"error": message}
            self.done.set()


def receive_callback(
    *,
    host: str,
    port: int,
    path: str,
    expected_state: str,
    expected_issuer: str,
    timeout_s: float = 300.0,
) -> str:
    try:
        server = _CallbackServer((host, port), _CallbackHandler)
    except OSError as exc:
        raise OAuthError(
            f"cannot listen on {host}:{port} for the OAuth callback: {exc}. "
            "Choose another port or close the process using it."
        ) from exc
    server.expected_state = expected_state
    server.expected_issuer = expected_issuer
    server.callback_path = path
    server.result = {}
    server.done = threading.Event()
    server.timeout = 1.0
    deadline = time.monotonic() + timeout_s
    try:
        while not server.done.is_set() and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not server.done.is_set():
        raise OAuthError("timed out waiting for the ViewMade authorization callback")
    if "error" in server.result:
        raise OAuthError(server.result["error"])
    return str(server.result["code"])


def _token_request(
    token_endpoint: str,
    form: dict[str, str],
    *,
    timeout: float = 30.0,
) -> dict:
    body = urllib.parse.urlencode(form).encode("utf-8")
    data = _request_json(
        token_endpoint,
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    if not isinstance(data.get("access_token"), str) or not data["access_token"]:
        raise OAuthError("token endpoint returned no access_token")
    token_type = str(data.get("token_type") or "").lower()
    if token_type and token_type != "bearer":
        raise OAuthError(f"unsupported token type: {token_type!r}")
    return data


def _store_token(
    project: Project,
    *,
    token: dict,
    issuer: str,
    token_endpoint: str,
    client_id: str,
    resource: str | None,
) -> dict:
    expires_in = token.get("expires_in")
    expires_at = None
    if isinstance(expires_in, (int, float)):
        expires_at = int(time.time() + float(expires_in))
    record = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "token_type": "Bearer",
        "scope": token.get("scope"),
        "expires_in": expires_in,
        "expires_at": expires_at,
        "issuer": issuer,
        "token_endpoint": token_endpoint,
        "client_id": client_id,
        "resource": resource,
        "obtained_at": utc_now_iso(),
    }
    _private_write(project.viewmade_token_file, record)
    return record


def login(
    project: Project,
    *,
    open_browser: bool = True,
    timeout_s: float = 300.0,
    port: int | None = None,
) -> dict:
    config = project.viewmade()
    metadata = discover_authorization_server(config["authorization_metadata_url"])
    metadata.require_pkce_s256()
    if metadata.issuer.rstrip("/") != str(config["authorization_server"]).rstrip("/"):
        raise OAuthError(
            f"authorization server issuer mismatch: {metadata.issuer!r} != {config['authorization_server']!r}"
        )
    resource = None
    protected: ProtectedResource | None = None
    try:
        protected = discover_protected_resource(config["resource_metadata_url"])
    except OAuthError:
        protected = None
    if protected is not None:
        if protected.authorization_servers and not any(
            server.rstrip("/") == metadata.issuer for server in protected.authorization_servers
        ):
            raise OAuthError(
                "protected-resource metadata does not list the configured authorization server"
            )
        resource = protected.resource or config["mcp_url"]

    host = config.get("redirect_host", "127.0.0.1")
    chosen_port = int(port if port is not None else config.get("redirect_port", 8765))
    redirect_uri = f"http://{host}:{chosen_port}{config.get('redirect_path', '/callback')}"
    client = register_client(
        project,
        metadata,
        redirect_uri=redirect_uri,
        client_name=config["client_name"],
        scopes=list(config["scopes"]),
    )
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    authorize_url = build_authorize_url(
        metadata,
        client_id=client["client_id"],
        redirect_uri=redirect_uri,
        scopes=list(config["scopes"]),
        state=state,
        code_challenge=challenge,
        resource=resource,
    )
    print("Open this URL in a browser to authorize ViewMade:")
    print(authorize_url)
    print()
    print(f"Waiting for the callback on {redirect_uri} (timeout {int(timeout_s)}s)...")
    if open_browser:
        try:
            webbrowser.open(authorize_url)
        except Exception:
            pass
    code = receive_callback(
        host=host,
        port=chosen_port,
        path=str(config.get("redirect_path", "/callback")),
        expected_state=state,
        expected_issuer=metadata.issuer,
        timeout_s=timeout_s,
    )
    token = _token_request(
        metadata.token_endpoint,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client["client_id"],
            "code_verifier": verifier,
            **({"resource": resource} if resource else {}),
        },
    )
    record = _store_token(
        project,
        token=token,
        issuer=metadata.issuer,
        token_endpoint=metadata.token_endpoint,
        client_id=client["client_id"],
        resource=resource,
    )
    print("ViewMade connected. Token stored in the gitignored local state directory.")
    if record.get("scope"):
        print(f"Granted scope: {record['scope']}")
    return _public_token_status(record)


def _load_token(project: Project) -> dict | None:
    path = project.viewmade_token_file
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except PipelineError:
        return None
    return data if isinstance(data, dict) else None


def _public_token_status(record: dict) -> dict:
    expires_at = record.get("expires_at")
    now = int(time.time())
    expired = bool(expires_at and now >= int(expires_at))
    return {
        "authenticated": not expired,
        "expired": expired,
        "expires_at": expires_at,
        "refreshable": bool(record.get("refresh_token")),
        "scope": record.get("scope"),
        "client_id": record.get("client_id"),
        "issuer": record.get("issuer"),
        "source": "token_file",
    }


def status(project: Project, settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env(project)
    if settings.mcp_token:
        return {
            "authenticated": True,
            "expired": False,
            "expires_at": None,
            "refreshable": False,
            "scope": None,
            "client_id": None,
            "issuer": None,
            "source": "VIEWMADE_MCP_TOKEN",
        }
    record = _load_token(project)
    if not record:
        return {
            "authenticated": False,
            "expired": False,
            "expires_at": None,
            "refreshable": False,
            "scope": None,
            "client_id": None,
            "issuer": None,
            "source": "none",
        }
    return _public_token_status(record)


def get_access_token(
    project: Project,
    settings: Settings | None = None,
    *,
    auto_refresh: bool = True,
) -> str:
    settings = settings or Settings.from_env(project)
    if settings.mcp_token:
        return settings.mcp_token
    record = _load_token(project)
    if not record:
        raise OAuthError(
            "ViewMade is not connected. Run `cddocs viewmade login` or connect at "
            f"{project.viewmade()['connect_url']}."
        )
    expires_at = record.get("expires_at")
    if expires_at and time.time() + 60 >= float(expires_at):
        if not auto_refresh:
            raise OAuthError("ViewMade access token has expired; sign in again")
        record = refresh(project)
    token = record.get("access_token")
    if not isinstance(token, str) or not token:
        raise OAuthError("stored ViewMade token is invalid; run `cddocs viewmade login` again")
    return token


def refresh(project: Project) -> dict:
    record = _load_token(project)
    if not record or not record.get("refresh_token"):
        raise OAuthError("no refresh token is available; run `cddocs viewmade login` again")
    endpoint = record.get("token_endpoint")
    client_id = record.get("client_id")
    if not endpoint or not client_id:
        raise OAuthError("stored OAuth client metadata is incomplete; sign in again")
    token = _token_request(
        str(endpoint),
        {
            "grant_type": "refresh_token",
            "refresh_token": str(record["refresh_token"]),
            "client_id": str(client_id),
        },
    )
    if not token.get("refresh_token"):
        token["refresh_token"] = record.get("refresh_token")
    refreshed = _store_token(
        project,
        token=token,
        issuer=str(record.get("issuer") or ""),
        token_endpoint=str(endpoint),
        client_id=str(client_id),
        resource=record.get("resource"),
    )
    return refreshed


def logout(project: Project, *, revoke: bool = True) -> dict:
    record = _load_token(project)
    revoked = False
    warnings: list[str] = []
    if record and revoke:
        endpoint = record.get("token_endpoint")
        client_id = record.get("client_id")
        token = record.get("refresh_token") or record.get("access_token")
        if endpoint and client_id and token:
            try:
                config = project.viewmade()
                metadata = discover_authorization_server(config["authorization_metadata_url"])
                revocation_endpoint = metadata.revocation_endpoint
                if revocation_endpoint:
                    body = urllib.parse.urlencode(
                        {"token": str(token), "client_id": str(client_id)}
                    ).encode("utf-8")
                    _request_json(
                        revocation_endpoint,
                        method="POST",
                        data=body,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        allow_empty=True,
                    )
                    revoked = True
            except OAuthError as exc:
                warnings.append(f"token revocation failed: {exc}")
    removed = False
    if project.viewmade_token_file.is_file():
        project.viewmade_token_file.unlink()
        removed = True
    return {"removed": removed, "revoked": revoked, "warnings": warnings}
