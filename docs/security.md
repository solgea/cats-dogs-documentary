# Security Documentation

## Windows Token File Limitation

**Important:** On Windows, the `os.chmod(path, 0o600)` call in `_private_write()` (src/cddocs/viewmade/oauth.py) does not restrict file permissions. The token files (`viewmade-token.json`, `viewmade-oauth-client.json`, `viewmade-binding.json`) remain readable by all users on the system.

### Mitigation

1. **Awareness:** Operators on Windows should be aware that token files in `state/` are not protected by POSIX-style permissions.
2. **Environment Isolation:** Run the pipeline in a dedicated user account with restricted access.
3. **Disk Encryption:** Use BitLocker or equivalent full-disk encryption.
4. **Future Enhancement:** Consider using Windows ACLs via `icacls` or a cross-platform keyring library for sensitive token storage.

The YouTube token store (`token_manager.save_credentials`) has the same
limitation: it writes the JSON with a plain `open()` and wraps `os.chmod` in a
`try/except OSError`, so on Windows the file is readable by every local user.

### Files Affected

- `state/viewmade-token.json` — OAuth access/refresh tokens
- `state/viewmade-oauth-client.json` — OAuth client credentials
- `state/viewmade-binding.json` — MCP tool bindings
- `youtube_token.json` / `src/cddocs/youtube/youtube_token.json` — YouTube OAuth tokens and the selected channel id

All are listed in `.gitignore` and never committed.