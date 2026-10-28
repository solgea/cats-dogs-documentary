# ViewMade OAuth

## Scope of the integration

The provider integration uses only ViewMade's officially advertised OAuth and MCP
capabilities:

| Item | Official value |
| --- | --- |
| MCP endpoint | `https://mcp.viewmade.com/mcp` |
| Protected-resource metadata | `https://mcp.viewmade.com/.well-known/oauth-protected-resource` |
| Authorization-server metadata | `https://viewmade.com/.well-known/oauth-authorization-server` |
| Authorization endpoint | `https://viewmade.com/oauth/authorize` |
| Token endpoint | `https://viewmade.com/api/oauth/token` |
| Dynamic registration | `https://viewmade.com/api/oauth/register` |
| Revocation | `https://viewmade.com/api/oauth/revoke` |
| Connect page | `https://viewmade.com/dashboard/connect` |
| Scopes | `video:create video:read presets:write account:read` |

These values are recorded in `config/viewmade.json`; the adapter does not guess
additional endpoints. Provider tool names are never placed in OAuth code.

## Flow

`cddocs viewmade login` performs the following:

1. Fetch and parse the authorization-server metadata over HTTPS.
2. Require the issuer to match the configured authorization server.
3. Refuse to continue unless the server advertises S256 PKCE.
4. Fetch protected-resource metadata when available and carry its resource
   identifier into the authorization and token requests.
5. Reuse a compatible cached public client, or perform dynamic client
   registration with `token_endpoint_auth_method: "none"`.
6. Generate a random state value and an RFC 7636 S256 code verifier/challenge.
7. Open the authorization URL, or print it with `--no-browser`.
8. Listen on `127.0.0.1:8765/callback` by default, validate `state` and, when
   supplied, the issuer `iss`, then exchange the code with the verifier.
9. Store the access token locally and print only non-secret status.

The authorization-code grant is always requested. A refresh grant is registered
only when the server metadata advertises it. The metadata observed on 2026-10-29
advertised `authorization_code` only, so do not assume a refresh token will be
issued. If the token expires and no refresh token exists, sign in again.

## Commands

```powershell
cddocs viewmade status
cddocs viewmade login
cddocs viewmade login --no-browser
cddocs viewmade login --port 9876
cddocs viewmade discover
cddocs viewmade logout
```

`logout` attempts official token revocation when the metadata and token permit it,
then removes the local token. It also removes the local tool binding unless
`--keep-binding` is supplied. A warning means revocation could not be completed;
remove access from the ViewMade account dashboard if necessary.

## Local secrets

The login flow writes:

| Path | Content | Git status |
| --- | --- | --- |
| `state/viewmade-token.json` | Access token, optional refresh token, expiry, client id, endpoint metadata | Ignored |
| `state/viewmade-oauth-client.json` | Public dynamic-client registration record | Ignored |
| `state/viewmade-tools.json` | Sanitised tool discovery snapshot | Ignored |
| `state/viewmade-binding.json` | Explicit tool mapping and templates | Ignored |

No token, authorization code, state value, or signed download URL is printed by
the CLI. File permissions are tightened to owner-only where the platform permits
it. On Windows, rely on the user-profile ACL and never copy the token file into
the repository.

For automation, `VIEWMADE_MCP_TOKEN` can supply a bearer token directly. It takes
precedence over the token file and is reported as
`source: "VIEWMADE_MCP_TOKEN"`. It must never be committed or pasted into logs.

## HTTP behavior

The MCP client sends `Authorization: Bearer ...`, preserves `Mcp-Session-Id`, and
sends the negotiated `MCP-Protocol-Version` after initialization. It accepts JSON
and SSE responses. A `401` is treated as an authentication failure with a link to
the connect page. A `403` is treated as an account/scope/permission problem.
Neither is retried as if rendering succeeded.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `ViewMade is not connected` | Run `cddocs viewmade login`, or set a valid env token |
| Token expired, no refresh token | Sign in again; do not invent a refresh grant |
| Callback port busy | Close the process on 8765 or run `--port <free-port>` |
| State or issuer mismatch | Retry the login; do not bypass the callback checks |
| HTTP 401 on discovery/render | Re-authenticate; check account access |
| HTTP 403 | Verify ViewMade Pro API/MCP access and the granted scopes |
| Dynamic registration fails | Check the official registration endpoint/status; do not hardcode a client id |
| Authorization metadata lacks S256 | Stop. The client refuses to downgrade PKCE |
| No tools returned | Treat discovery as failed/blocked; do not invent tool names |

OAuth state, secrets, and signed URLs are operational data, not content. Never
include them in issue reports, screenshots, package JSON, or the distribution ZIP.
