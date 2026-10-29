# Rendering

## Current state

ViewMade OAuth, discovery, and render/status/download binding are complete for
batch `2026-10-29-cats-dogs-01`.

The `dog-guilty-look` pilot job `f59f8a91-7b2b-4dbb-a03d-62effc911581` reached
`ready` after 20 credits were charged. The provider file was downloaded,
normalized to 1080x1920, and passed local media validation:

- `renders/dog-guilty-look.mp4` — 47.733 s, H.264 video, AAC stereo audio;
- SHA-256 `ac8ab8917d71d22548077d12fe6f0c535878ff709abd3fd41375b8b1b41e2f61`;
- provider output: 21 scenes, 1440x2560 coded, six third-party YouTube sources.

`COMPLETE` only means the file is parseable and matches the channel format. The
channel owner accepted **real-footage montage** as the visual direction on
2026-10-29, but this pilot is **rejected**: its provider sources are
entertainment/compilation clips, it shows multiple dogs and a visible watermark,
and its narrative diverges from the local evidence record. Do not publish it.

The next render must be a single package, with `engine: clearcut`, the local
script, and the new real-footage policy. Do not render all five remaining
packages until that pilot is reviewed. See
[viewmade-output-review.md](viewmade-output-review.md).

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
    30–60 second MP4 with audio. A higher-resolution 9:16 provider render is
    normalized to 1080x1920 with ffmpeg before this check; if ffmpeg is missing,
    the render fails closed. Normalization forces square pixels (`setsar=1`) and
    re-probes the temporary output, because preserving a non-square source SAR
    can leave a 1080-wide file with a 1071-pixel display width.
11. Attribution: every provider footage source URL must appear in the metadata
    description before the package can be published.
12. Human review: a person must watch the result and record an explicit
    `APPROVED` or `REJECTED` disposition. This does not happen automatically
    inside this repository.

If any gate fails, the result stays blocked or failed. There is no stand-in video,
placeholder MP4, remote URL claimed without a download, or optimistic success.

## Command

Only after OAuth and binding:

```powershell
$env:CDDOCS_LIVE_CONFIRM = "YES"
# One paid pilot (20 credits):
cddocs batch render 2026-10-29-cats-dogs-01 --package cat-sweetness --allow-live --poll-interval 5 --timeout 900
```

`batch render` now refuses to run without `--package <slug>` or `--all`. The
single-package form is the pilot-first default. `--all` authorises a paid render
for every package in the batch and should only be used after the pilot review.

The batch renderer validates first, checks adapter status, then processes the
requested packages in manifest order. It stops at the first blocked or failed
job. A batch report is written to
`content/batches/<batch-id>/render-report.json` with the requested and skipped
packages; package state is written to `viewmade-request.json` and local job
records under `state/viewmade-jobs/`.

If `viewmade_create_short` returns a transport error but `viewmade_list_videos`
shows a matching production, do **not** submit a second job. Verify the job id
and title, then attach to the existing job:

```powershell
$env:CDDOCS_LIVE_CONFIRM = "YES"
python scripts/recover_viewmade_job.py dog-guilty-look <job-id> --poll-interval 60 --timeout 14400
```

The recovery script uses the bound status and download tools, normalizes the
file, runs local validation, and records the provider package state. It never
prints the bearer token.

For a fixed, self-refreshing terminal dashboard instead of a scrolling log:

```powershell
pwsh -File scripts/watch_render.ps1 -PackageId cat-sweetness
```

Use `-Once` for a single snapshot. The dashboard reads the recovery or render
log, refreshes in place, and shows provider status, stage, progress, provider
ETA, estimated time remaining, elapsed time, local request state, recorded
credits, and whether the MP4 exists.

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
`FAILED`. `STALE` means a provider job or MP4 belongs to an older request
specification and must not be published. A status without a job id fails
validation. A `render_path` must exist on disk. The adapter records provider
state and errors rather than hiding them.

`editorial_review` records the human disposition:
`PENDING`, `APPROVED`, or `REJECTED`, with a timestamp, reviewer role, and
reason. A rejected render remains technically valid but cannot be published.
The pilot is marked `REJECTED`, and its request became `STALE` after the
real-footage policy changed; the preserved MP4 must not be published.

`batch build` preserves an existing job id, provider state, render path, hash,
normalization record, and provider package when the `request` object is
unchanged. If the script or other request fields changed, the preserved job is
marked `STALE` instead of silently reusing an unrelated MP4.

## Download and validation

The download tool should return either a short-lived HTTPS URL or a local file
path. The adapter refuses non-HTTPS URLs. It attaches the bearer token only when
the host is `viewmade.com` or a `*.viewmade.com` subdomain; unrelated hosts get no
credential.

The target is `renders/<package-id>.mp4`. If `render.normalize` is enabled and
the provider returns another 9:16 resolution such as 1440x2560, ffmpeg scales
the file to 1080x1920 with Lanczos resampling and AAC audio. It is temporary
until local validation passes:

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
It also refuses to submit a second paid job when a job id exists in an active
provider state (`queued`, `rendering`, or `ready`), or when a `COMPLETE` request
is missing a valid local file. Recover the existing job instead; see the recovery
command above.

The render template uses `$operation_key`, which is the package id plus a short
hash of the request specification. Identical requests keep the same idempotency
key; a materially changed script or policy gets a new key. This prevents both
accidental duplicate charges and silent reuse of an old job after an edit. To
intentionally replace a rejected render, inspect and archive the old files and
state, then reset the request through a deliberate operator workflow. Do not
hand-edit a job to `COMPLETE`; that is the one status the pipeline treats as
evidence of a verified file.

## What rendering does not authorize

A successful render is not publication approval. Human editorial review, source
spot-checks, caption review, welfare review, footage-rights review, attribution
review, and manual YouTube upload are still required. Attribution is not a
licence: if the provider's clip rights are unclear, do not publish. This
repository has no YouTube upload integration.
