# Architecture

## Design goals

The pipeline treats a content package as an evidence-bearing artifact. The
cheap, reviewable parts — research, narration, visual intent, metadata, and
subtitle timing — are built first. Rendering and publishing are separate,
permissioned stages. A failure at any stage leaves the next stage closed.

The implementation uses only the Python standard library. That keeps the
repository inspectable and avoids a dependency update silently changing QA
behavior.

## Data flow

```text
package.json + research.json
        |
        v
build_metadata / build_cues / build_script / build_visual_plan
        |
        v
metadata.json, subtitles.srt, script.md, visual-plan.md
        |
        v
viewmade-request.json  (local specification, never a success claim)
        |
        +--> validate_package  --> qa-report.json
        |                           |
        |                           +--> history / duplicate checks
        |
        +--> package the review archive
        |
        +--> [gated] OAuth --> MCP discover --> explicit bind --> live render
                                                |
                                                v
                                  download --> local MP4 validation
                                                |
                                                v
                                      render.mp4 + COMPLETE state
        |
        +--> [manual, outside this repository] human review --> upload
```

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Project discovery, path policy, channel/source/ViewMade configuration, live-render environment gate |
| `util.py` | Atomic writes, stable JSON, slugs, hashing, token similarity, dates |
| `metadata.py` | YouTube metadata generation and policy validation |
| `subtitles.py` | Sentence-aware cue splitting, two-line wrapping, SRT round-trip, timing validation |
| `history.py` | SQLite topic registry, cross-batch duplicate scoring, portable JSON export |
| `validation.py` | Package QA: editorial, evidence, visuals, metadata, subtitles, dedup, render artifact |
| `media_probe.py` | Dependency-free PNG/JPEG/WAV/MP4 header inspection and render validation |
| `artifacts.py` | Markdown and provider-request artifact generation |
| `batch.py` | Batch build/validate/package orchestration and gated render sequencing |
| `cli.py` | `cddocs` command surface |
| `viewmade/oauth.py` | Discovery, S256 PKCE, dynamic registration, callback, token storage, refresh/logout |
| `viewmade/mcp.py` | MCP Streamable HTTP JSON/SSE transport, session handling, `tools/list`, `tools/call` |
| `viewmade/adapter.py` | Discovery snapshot, explicit tool binding, template validation, render/status/download pipeline |

## Trust boundaries

1. **Editorial input is untrusted.** Package and research JSON can contain bad
   citations, overclaims, or unsafe visual instructions. Validation is the gate.
2. **Provider metadata is untrusted until checked.** OAuth discovery must be
   HTTPS, the issuer must match configuration, and S256 PKCE must be advertised.
3. **Provider tool names are unknown at build time.** They are learned through
   official MCP discovery and bound by a human. No source file contains a guessed
   provider tool name.
4. **Provider output is untrusted.** A download is just bytes until local media
   probing confirms an MP4, 1080x1920, 9:16, 30–60 seconds, with audio.
5. **QA is not approval.** Publication readiness also requires a real render and
   recorded human editorial sign-off. There is no publisher in this repository.

## State and determinism

- Generated text and JSON are written atomically with LF newlines.
- Package QA hashes cover source and generated artifacts.
- A batch build registers topics only when the aggregate status is not `FAIL`.
- Rebuilding the same package in the same batch is idempotent for duplicate
  detection.
- Timestamps and QA report hashes make archives non-bit-identical; content
  artifacts are deterministic.
- `state/history.db` is local machine state. `state/history.json` is the reviewed,
  committed export. Do not resolve a history conflict by copying a DB file
  between machines.

## Failure model

Expected failures raise `PipelineError` (or its OAuth/MCP/render subclasses) and
are printed without a traceback. The CLI returns a non-zero exit code. The
render gate deliberately raises `ViewMadeBlocked` when authentication, binding,
discovery, download, or media validation is incomplete. Partial provider jobs
are recorded honestly as `SUBMITTED`, `RENDERING`, or `FAILED`; they are never
rounded up to `COMPLETE`.
