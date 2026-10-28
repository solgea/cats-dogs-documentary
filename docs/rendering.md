# Rendering

## Current state

Live ViewMade rendering is **BLOCKED** for batch
`2026-10-29-cats-dogs-01`. There is no OAuth token, no discovered tool list, and
no render/status/download binding. No MP4 has been produced. Do not report a
render, URL, job id, or file hash that does not exist.

## Gate order

A render request passes through all of these gates:

1. QA: `batch validate` must not return `FAIL`.
2. Live switch: the command must include `--allow-live`.
3. Environment confirmation: `CDDOCS_LIVE_CONFIRM` must equal `YES`.
4. OAuth: the adapter must find a non-expired access token (or a valid env token).
5. Discovery: a tool snapshot must exist from the official MCP endpoint.
6. Binding: render, status, and download tools must all be bound.
7. Provider acceptance: the render tool must return a job id.
8. Polling: the status tool must reach a configured success state before timeout.
9. Download: the download tool must yield an HTTPS URL or an existing local file.
10. Local verification: the downloaded bytes must parse as a 1080x1920, 9:16,
    30–60 second MP4 with audio.
11. Human review: a person must watch the result and approve it. This does not
    happen inside this repository.

If any gate fails, the result stays blocked or failed. There is no stand-in video,
placeholder MP4, remote URL claimed without a download, or optimistic success.

## Command

Only after OAuth and binding:

```powershell
$env:CDDOCS_LIVE_CONFIRM = "YES"
cddocs batch render 2026-10-29-cats-dogs-01 --allow-live --poll-interval 5 --timeout 900
```

The batch renderer validates first, checks adapter status, then processes packages
in manifest order. It stops at the first blocked or failed job. A batch report is
written to `content/batches/<batch-id>/render-report.json`; package state is
written to `viewmade-request.json` and local job records under
`state/viewmade-jobs/`.

Without both live confirmations, even an accidental command with a valid token
does not submit:

```text
Live ViewMade rendering is disabled. Re-run with --allow-live and set
CDDOCS_LIVE_CONFIRM=YES.
```

## Request record

`viewmade-request.json` is generated locally and starts as:

- `status: "NOT_SUBMITTED"`;
- `submission_allowed: false`;
- a `blocked_reason` explaining missing bindings;
- no job id, submission, or render path.

During a real render it can move through `SUBMITTED`, `RENDERING`, `COMPLETE`, or
`FAILED`. A status without a job id fails validation. A `render_path` must exist on
disk. The adapter records provider state and errors rather than hiding them.

## Download and validation

The download tool should return either a short-lived HTTPS URL or a local file
path. The adapter refuses non-HTTPS URLs. It attaches the bearer token only when
the host is `viewmade.com` or a `*.viewmade.com` subdomain; unrelated hosts get no
credential.

The target is `renders/<package-id>.mp4`. It is temporary until local validation
passes:

- ISO-BMFF/MP4 `ftyp` and `moov` structure;
- a duration from `mvhd` in the 30–60 second range;
- a video track with 1080x1920 dimensions and a 9:16 ratio;
- an audio handler in `moov`;
- at least 100,000 bytes.

A failed download or failed probe leaves a `.invalid.mp4` artifact for inspection
when possible and records `FAILED`. It never becomes `COMPLETE`.

## Re-rendering

If a request is already `COMPLETE` and its `render_path` still passes validation,
the adapter returns the existing verified render rather than submitting again.
To intentionally replace a bad render, inspect and archive the old files and
state, then reset the request through a deliberate operator workflow. Do not
hand-edit a job to `COMPLETE`; that is the one status the pipeline treats as
evidence of a verified file.

## What rendering does not authorize

A successful render is not publication approval. Human editorial review, source
spot-checks, caption review, welfare review, and manual YouTube upload are still
required. This repository has no YouTube upload integration.
