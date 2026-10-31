# CHANGELOG

All notable changes to the Cats & Dogs Documentary project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/) and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Changed
- **Control-room UI v2.3** (`dashboard.py`): Added a shared page-header and status vocabulary, an action queue on Genel Bakış, a five-stage lifecycle board with bottleneck highlighting, count badges on the Video Üretim segmented control, a compact ViewMade status chip (details moved into Üretimler), a visible publish-gate checklist and three-step publish wizard, an agent stage map, and theme preview cards in Ayarlar. The large Video Üretim KPI strip and redundant ViewMade status bar were removed so content appears above the fold.
- **Video Üretim çalışma alanı** (`dashboard.py`): The page is now a four-part workspace (Üretimler, İçerik Ajanı, Projeler, Yayın Merkezi) with a compact header, count badges, and a collapsible connection panel. Decorative global stage/provider blocks were removed and the local preview gallery was consolidated into the publishing center.
- **ViewMade production info screen** (`dashboard.py`, `src/cddocs/viewmade/adapter.py`): The selected production now shows the full ViewMade info card — title, description, tags, status, duration, resolution, scene count, credits, creation time, source footage links, attribution lines, and the editorial subject note. Completed project renders expose the same card, and publishing from either place opens Yayın Merkezi directly.

### Fixed
- **ViewMade `invalid_input` rejection** (`src/cddocs/viewmade/adapter.py`, `dashboard.py`): The provider requires a 7-12 line English script for `language: en`. `_script_lines` now preserves explicit narration lines and splits long ones to reach the minimum, `validate_arguments_against_schema`/`validate_render_arguments` run a free local preflight against the bound tool schema before any paid call, and the dashboard blocks Turkish narration, shows per-field validation errors, and offers a "ViewMade yazsın" mode that omits the script so the provider writes the English narration from the topic.
- **Retry after rejected submission** (`dashboard.py`): A `FAILED` request without a provider job id no longer locks the project; the panel shows that no credits were charged and re-opens the render form after the input is fixed.

### Added
- **Content registry and YouTube matching** (`dashboard.py`): `content_registry.json` links ViewMade jobs, local packages, and YouTube videos by title tokens and provider IDs. All 6 published ViewMade productions now match their YouTube video IDs, and duplicates are blocked at suggestion, project creation, paid render, and upload.
- **ViewMade ↔ YouTube matching panel** (`dashboard.py`): Table of every ViewMade production with local-copy status and the matching YouTube link, so published productions are never re-rendered or re-uploaded.
- **Ideal preview sizes** (`dashboard.py`): All vertical video previews render at 320 px (`PREVIEW_WIDTH` and `GALLERY_PREVIEW_WIDTH`) instead of full column width.
- **Dashboard ViewMade bridge** (`dashboard.py`): OAuth/MCP connection card with token expiry, scope, 3/3 tool binding, live MCP test, provider video list, on-demand free preview download, 1080x1920 normalization, and sidecar metadata.
- **Per-project render gate** (`dashboard.py`, `scripts/dashboard_viewmade_render.py`): English narration check, 30–60 s duration, typed `RENDER` confirmation, background worker with `CDDOCS_LIVE_CONFIRM=YES`, stale-state protection, and automatic preview on completion.
- **Yayın Merkezi** (`dashboard.py`): Local `renders/` + `outputs/` gallery, editable title/description/tags, privacy selection, target-channel display, quota display, human-review checkbox, typed `YAYINLA` confirmation, duplicate guard, and rejected-pilot block for `dog-guilty-look`.
- **Preview verification**: Downloaded `viewmade-2fd8c784-e45a-4dfb-89a9-402922d4e758.mp4` (26.3 MB, 1080x1920, 46.0 s, AAC audio) without submitting a paid render.

### Changed
- **ViewMade provider availability** (`dashboard.py`): The legacy API-key check is overridden by real OAuth + binding status.
- **Runtime state ignores** (`.gitignore`): Added `upload_history.json`, `content_registry.json`, and `state/dashboard-render-*` so local publish/render/registry state is never committed.

## [0.2.0] - 2026-10-29
### Added
- **Real-footage montage policy and attribution gates** (`3f9cd62`): Replaced AI-assisted disclosure with the real-footage channel standard. Every provider source URL is now credited. Render attribution and editorial-review QA checks added.
- **Package `rights` schema** (`schemas/package.schema.json`): Added `rights.footage_sources` and `rights.music_sources` arrays with full licensing metadata (URL, creator, license, commercial_use_allowed, derivative_work_allowed, permission_evidence_url, reviewed_at, reviewer_id, status).
- **Editorial review gates** (`src/cddocs/validation.py`): `publish_ready` now requires `human_signoff=True`, `footage_rights_reviewed=True`, `music_rights_reviewed=True`, `caption_reviewed=True`, plus valid `rights` evidence and `render_status="PASS"`.
- **Request-hash operation key** (`src/cddocs/viewmade/adapter.py`): `_operation_key()` generates a stable idempotency key from the canonical SHA-256 of the request payload, changing only when the render specification changes.
- **Nested MCP envelope unwrapping** (`src/cddocs/viewmade/adapter.py`/_extract_path/_tool_payload): ViewMade returns create/status payloads under `structuredContent.data`. The adapter now unwraps this envelope before extracting job ID, provider state, download URL, and package metadata.
- **Footage/music rights source tracking** (`schemas/package.schema.json`/`src/cddocs/validation.py`): `_rights_ok()` validates that every source has a non-"Unknown" license, `commercial_use_allowed=True`, `status="cleared"`, and a `permission_evidence_url`. `publish_ready` is only `True` when all gates pass.
- **Visual disclosure policy** (`config/viewmade.json`/`schemas/package.schema.json`): Disclosure must exactly match the channel's required disclosure string (`REAL_FOOTAGE_MONTAGE_DISCLOSURE`).
- **Pilot REJECTED/STALE preservation** (`dog-guilty-look`): After the policy adoption, `dog-guilty-look` was marked REJECTED and its job/MP4 preserved as STALE evidence.
- **Explicit render submission guard** (`src/cddocs/viewmade/adapter.py` `render()`): A second paid render is blocked if a ViewMade job already exists with status `SUBMITTED`, `RENDERING`, or `STALE` (provider_state `queued`/`rendering`/`ready`). Only one render per package without explicit recovery.
- **Operation key in render arguments** (`src/cddocs/viewmade/adapter.py`): Render arguments now include `operation_key` for idempotency tracking.

### Changed
- **Metadata schema**: `footage_rights_reviewed`, `music_rights_reviewed`, `caption_reviewed` changed from `const:false` to free boolean; `rights` object added as a top-level property.
- **QA report format**: `publish_ready` now depends on editorial flags + human sign-off + rights evidence + valid render.
- **Batch validation**: `batch.py` `artifacts.request_state` check no longer fails on missing render_path files (renders/ is gitignored).
- **Distribution archive**: Rebuilt after every significant change (current SHA-256: `78ee55be...`).

### Fixed
- **Stale render-report.json removal**: Removed outdated render reports that conflicted with the new request-state model.
- **.gitignore updates**: Added `state/review/`, `state/recovery-*.log`, and `dist/` entries.
- **Batch validation edge case**: Fixed false FAIL when `request_path` exists but `render_path` is missing (expected for gitignored renders/ directory).

## [0.1.1] - 2026-10-29
### Added
- **ViewMade MCP envelope handling** (`8f76bbe`): Documented the `structuredContent.data` envelope contract. Added regression test `tests/test_viewmade_binding.py` for envelope unwrapping.
- **Tool binding dashboard** (`scripts/watch_render.ps1`, `scripts/recover_viewmade_job.py`): Generalized terminal dashboard to any package; distinguishes recovered jobs from failed ones.
- **Binding persistence** (`src/cddocs/viewmade/adapter.py` `bind()`): Writes binding to `state/viewmade-binding.json` with `schema_version: 1`, `provider_schema_version: "1"`, `bound_at` timestamp, poll retry configuration (exponential backoff with jitter).
- **Auth status endpoint** (`src/cddocs/viewmade/adapter.py` `status()`): Returns `authenticated`, `expired`, `refreshable`, `token_source`, `scope`, `tools_discovered`, `tool_count`, `bound`, and binding details.

### Changed
- **Request state mutation** (`src/cddocs/viewmade/adapter.py` `_update_request()`): Request payload is cleared and replaced rather than merged, preserving submission, recovery, and cleared-error fields across status updates.
- **Provider package capture** (`src/cddocs/viewmade/adapter.py` `render()`): All non-sensitive fields from the provider response are captured (denylist approach) for later attribution and rights review.

### Fixed
- **MCP auth error mapping** (`src/cddocs/viewmade/adapter.py`): `MCPAuthError` → `ViewMadeBlocked` / `FAILED`; no automatic retry.
- **Render skip prevention** (`src/cddocs/viewmade/adapter.py` `render()`): If existing request is `COMPLETE` with a valid local MP4, the adapter returns `COMPLETE` instead of submitting a second paid render.

## [0.1.0] - 2026-10-29
### Added
- **Initial project build** (`1c2ec45`): Created the full Cats & Dogs Documentary Shorts pipeline.
  - Channel config (`config/channel.json`, `config/viewmade.json`, `config/sources.json`)
  - Six package foundations (each with `package.json`, `research.json`, `script.md`, `visual-plan.md`, `subtitles.srt`, `metadata.json`, `viewmade-request.json`, `qa-report.json`)
  - Batch manifest and aggregate QA report (`content/batches/2026-10-29-cats-dogs-01/`)
  - JSON schemas for package, QA report, batch, metadata, research, history, viewmade binding, viewmade discovery
  - Core pipeline implementation (`src/cddocs/`: `__init__.py`, `__main__.py`, `artifacts.py`, `batch.py`, `cli.py`, `config.py`, `history.py`, `media_probe.py`, `metadata.py`, `subtitles.py`, `util.py`, `validation.py`)
  - ViewMade OAuth and MCP integration (`src/cddocs/viewmade/`: `adapter.py`, `mcp.py`, `oauth.py`, `__init__.py`)
  - Test suite (`tests/`: `test_batch.py`, `test_history.py`, `test_mcp.py`, `test_media_probe.py`, `test_metadata.py`, `test_oauth.py`, `test_schemas.py`, `test_subtitles.py`, `test_validation.py`, `test_viewmade_binding.py`)
  - CLI entry point (`cddocs` script via `pyproject.toml`)
  - Documentation (`docs/`: architecture, editorial standards, source verification, QA gates, ViewMade OAuth, tool binding, rendering, output review, deduplication, manual YouTube upload)
  - Security and licensing (`.env.example`, `.gitignore`, `README.md`, `LICENSE` Proprietary)

---