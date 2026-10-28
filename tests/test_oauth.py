"""OAuth discovery, PKCE, authorization URL, and dynamic registration behavior."""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

try:
    from ._support import ROOT  # noqa: F401
except ImportError:  # pragma: no cover
    from _support import ROOT  # noqa: F401

from cddocs.config import Project
from cddocs.viewmade import oauth


def _metadata(**overrides):
    data = {
        "issuer": "https://viewmade.com",
        "authorization_endpoint": "https://viewmade.com/oauth/authorize",
        "token_endpoint": "https://viewmade.com/api/oauth/token",
        "registration_endpoint": "https://viewmade.com/api/oauth/register",
        "revocation_endpoint": "https://viewmade.com/api/oauth/revoke",
        "scopes_supported": ["video:create", "video:read"],
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code"],
    }
    data.update(overrides)
    return oauth.AuthServerMetadata.from_json(data)


class OAuthTests(unittest.TestCase):
    def test_pkce_pair_is_rfc7636_s256(self) -> None:
        verifier, challenge = oauth.pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        self.assertNotIn("=", verifier)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        self.assertEqual(challenge, expected)
        self.assertEqual(len(challenge), 43)
        self.assertNotEqual(oauth.pkce_pair()[0], verifier)

    def test_metadata_requires_https_and_s256(self) -> None:
        with self.assertRaises(oauth.OAuthError):
            oauth.AuthServerMetadata.from_json(
                {
                    "issuer": "http://viewmade.com",
                    "authorization_endpoint": "https://viewmade.com/oauth/authorize",
                    "token_endpoint": "https://viewmade.com/api/oauth/token",
                }
            )
        with self.assertRaises(oauth.OAuthError):
            oauth.AuthServerMetadata.from_json(
                {
                    "issuer": "https://viewmade.com",
                    "authorization_endpoint": "https://viewmade.com/oauth/authorize",
                }
            )
        no_s256 = _metadata(code_challenge_methods_supported=["plain"])
        with self.assertRaises(oauth.OAuthError):
            no_s256.require_pkce_s256()
        _metadata().require_pkce_s256()

    def test_authorization_url_contains_pkce_state_and_resource(self) -> None:
        metadata = _metadata()
        url = oauth.build_authorize_url(
            metadata,
            client_id="public-client",
            redirect_uri="http://127.0.0.1:8765/callback",
            scopes=["video:create", "video:read"],
            state="state-value",
            code_challenge="challenge-value",
            resource="https://mcp.viewmade.com/mcp",
        )
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "viewmade.com")
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["public-client"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["code_challenge"], ["challenge-value"])
        self.assertEqual(query["state"], ["state-value"])
        self.assertEqual(query["scope"], ["video:create video:read"])
        self.assertEqual(query["resource"], ["https://mcp.viewmade.com/mcp"])

    def test_dynamic_registration_filters_unsupported_refresh_grant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Project(root=Path(tmp), state_dir=(Path(tmp) / "state").resolve())
            metadata = _metadata()
            with mock.patch.object(
                oauth, "_request_json", return_value={"client_id": "vmc_public_test"}
            ) as request:
                record = oauth.register_client(
                    project,
                    metadata,
                    redirect_uri="http://127.0.0.1:8765/callback",
                    client_name="Test Pipeline",
                    scopes=["video:create", "video:read"],
                )
            self.assertEqual(record["client_id"], "vmc_public_test")
            self.assertEqual(record["token_endpoint_auth_method"], "none")
            self.assertNotIn("client_secret", record)
            payload = json.loads(request.call_args.kwargs["data"])
            self.assertEqual(payload["grant_types"], ["authorization_code"])
            self.assertEqual(payload["response_types"], ["code"])
            self.assertEqual(payload["token_endpoint_auth_method"], "none")
            self.assertEqual(payload["scope"], "video:create video:read")
            self.assertEqual(payload["redirect_uris"], ["http://127.0.0.1:8765/callback"])

            request.reset_mock()
            again = oauth.register_client(
                project,
                metadata,
                redirect_uri="http://127.0.0.1:8765/callback",
                client_name="Test Pipeline",
                scopes=["video:create", "video:read"],
            )
            self.assertEqual(again["client_id"], "vmc_public_test")
            self.assertEqual(request.call_count, 0)

    def test_missing_registration_endpoint_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Project(root=Path(tmp), state_dir=(Path(tmp) / "state").resolve())
            metadata = _metadata(registration_endpoint=None)
            with self.assertRaises(oauth.OAuthError):
                oauth.register_client(
                    project,
                    metadata,
                    redirect_uri="http://127.0.0.1:8765/callback",
                    client_name="Test Pipeline",
                    scopes=["video:create"],
                )


if __name__ == "__main__":
    unittest.main()
