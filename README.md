# Cats & Dogs, Explained

A fail-closed documentary Shorts pipeline for an English-language cats-and-dogs
channel. It turns one source-checked question into a 45-second, 9:16 package
with a scene plan, narration, synchronized subtitles, YouTube metadata,
provider-neutral render request, evidence record, and machine-readable QA.

The pipeline does not upload to YouTube and does not claim a video exists until a
real MP4 has been downloaded from ViewMade and validated locally.

## Current status

| Item | State |
| --- | --- |
| Batch | `2026-10-29-cats-dogs-01` |
| Packages | 6 original topics, targeted at 45 seconds and six scenes each |
| Editorial direction | **Real-footage montage** accepted on 2026-10-29 |
| Editorial QA | PASS for all six packages, with no batch duplicate pair at the review thresholds |
| Render | Pilot MP4 validated locally; pilot **rejected** on editorial grounds |
| ViewMade | OAuth, discovery, and bindings complete; balance tool still returns `internal_error` |
| Human sign-off | Required and not recorded |
| YouTube upload | Manual only; not implemented |

The source-checked batch is not publication-ready. A package-level QA result of
`PASS` means the editorial and artifact checks did not fail. It does not mean a
video exists, that a human approved it, or that the provider's footage is
licensed for publication. The pilot used entertainment/compilation clips,
visible watermarks, multiple dogs, and a narrative that diverged from the local
evidence record, so it must not be published. See
[docs/viewmade-output-review.md](docs/viewmade-output-review.md).

## Quick start

Requires Python 3.10 or newer. There are no third-party runtime dependencies.

```powershell
python -m pip install -e .
cddocs doctor
cddocs batch build 2026-10-29-cats-dogs-01
cddocs batch validate 2026-10-29-cats-dogs-01
cddocs batch package 2026-10-29-cats-dogs-01
```

The build is deterministic apart from timestamps and QA hashes. `batch package`
runs a fresh validation first and refuses to create an archive when any package
fails.

Useful checks:

```powershell
python -m unittest discover -s tests -v
cddocs viewmade status
cddocs history list
```

## What is in a package

Each folder under `content/packages/` contains:

| File | Purpose |
| --- | --- |
| `package.json` | Original editorial plan: hook, six scenes, claims, visual policy, YouTube copy, review gate |
| `research.json` | Research question, source records, evidence summaries, limitations, claim checks, uncertainties |
| `script.md` | Human-readable narration, scene table, evidence table, citations |
| `visual-plan.md` | Shot-by-shot direction, continuity, anatomy, welfare, and negative prompt |
| `subtitles.srt` | Burn-in-ready SRT ending exactly at the target duration |
| `metadata.json` | Title, description, tags, hashtags, source list, disclaimers, manual-upload flags |
| `viewmade-request.json` | Local render specification and honest provider state |
| `qa-report.json` | Every gate, artifact hashes, render state, publication readiness |

The batch folder contains `batch.json` and an aggregate `qa-report.json`. The
reviewable duplicate history is `state/history.json`; SQLite is local machine
state and is not portable evidence.

## First batch

| Package | Question |
| --- | --- |
| `dog-guilty-look` | Does a dog's guilty look mean the dog feels guilty? |
| `cat-sweetness` | Why can't cats taste sweetness? |
| `puppy-dog-eyes` | Why do dogs have that expressive inner-eyebrow look? |
| `slow-blink` | Do cats understand a human slow blink? |
| `purr-cry` | Why does a hungry cat's purr sound so urgent? |
| `dog-nose` | How does a dog's nose separate smelling from breathing? |

Each package is built around a primary, peer-reviewed source and records what
the evidence supports, what it only suggests, and what remains unknown.

## Fail-closed rules

- Source records must use HTTPS, an allowed domain, an accessed date, a tier,
  an evidence summary, limitations, and a DOI or PMID for tier-1 research.
- Every source must support at least one claim, and every claim must have a
  verification verdict.
- Narration and metadata may not contain unsupported certainty or medical-advice
  language. Visual instructions may not request distress, injury, or aggression.
- Every package must disclose: `Real-footage montage using third-party clips for illustration; not documentary footage or scientific evidence.`
- Subtitles must start at zero, end at the target duration, stay readable, and
  reproduce the narration.
- Duplicate topics are checked against committed history and within the batch.
  A slug collision, reused package id across batches, or near-identical framing
  fails the build.
- No ViewMade tool name is hardcoded. Rendering requires successful OAuth,
  runtime `tools/list`, an explicit render/status/download binding, `--allow-live`,
  and `CDDOCS_LIVE_CONFIRM=YES`.
- A downloaded render is `COMPLETE` only after local MP4 structure, dimensions,
  duration, aspect ratio, and audio checks pass.
- No YouTube upload path exists. Publishing is a manual editorial action.

## ViewMade workflow

The provider integration uses only the official OAuth 2.1 authorization-code
flow with S256 PKCE, dynamic client registration, and the official MCP endpoint.
The bare minimum is:

```powershell
cddocs viewmade login
cddocs viewmade discover
cddocs viewmade tools
# Read the discovered input schemas, then bind the exact tools and templates.
cddocs viewmade bind --render-tool <name> --status-tool <name> --download-tool <name> `
  --render-template path\to\render-template.json `
  --status-template path\to\status-template.json `
  --download-template path\to\download-template.json
```

Then, only after reviewing the bindings:

```powershell
$env:CDDOCS_LIVE_CONFIRM = "YES"
# Pilot-first: one paid render, 20 credits.
cddocs batch render 2026-10-29-cats-dogs-01 --package cat-sweetness --allow-live
# Only after explicit approval of that render:
cddocs batch render 2026-10-29-cats-dogs-01 --all --allow-live
```

ViewMade is authenticated and bound, but a new paid render still requires an
explicit `--package` selection and live confirmation. See
[docs/viewmade-oauth.md](docs/viewmade-oauth.md),
[docs/viewmade-tool-binding.md](docs/viewmade-tool-binding.md), and
[docs/rendering.md](docs/rendering.md).

## Project layout

```text
config/                 channel policy, source domains, ViewMade endpoints
content/packages/       editorial source and generated package artifacts
content/batches/        batch manifests and aggregate QA reports
src/cddocs/             standard-library pipeline implementation
src/cddocs/viewmade/    OAuth, MCP transport, provider adapter
schemas/                JSON contracts for durable records
docs/                   operating and editorial procedures
state/history.json      committed topic-history export
state/history.db        local SQLite history (gitignored)
dist/                   generated distribution archives (gitignored)
renders/                downloaded provider media (gitignored)
tests/                  deterministic unit and integration tests
```

## Documentation

- [Architecture](docs/architecture.md)
- [Editorial standards](docs/editorial-standards.md)
- [Source verification](docs/source-verification.md)
- [QA gates](docs/qa-gates.md)
- [ViewMade OAuth](docs/viewmade-oauth.md)
- [ViewMade tool binding](docs/viewmade-tool-binding.md)
- [Rendering](docs/rendering.md)
- [ViewMade output review](docs/viewmade-output-review.md)
- [Topic deduplication](docs/deduplication.md)
- [Manual YouTube upload](docs/manual-youtube-upload.md)
- [JSON schemas](schemas/README.md)

## Security

OAuth tokens, OAuth client records, discovered tools, bindings, job state, and
renders are written under local state directories or ignored media directories.
Never commit `.env`, token files, signed download URLs, or API keys. The CLI does
not print access tokens. If a credential was exposed, revoke it at the provider
rather than deleting only the local file.

## License

Proprietary. All rights reserved.
