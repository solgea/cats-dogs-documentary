# QA gates

## What a QA result means

The package QA report is a machine-readable list of checks. Each check is
`PASS`, `WARN`, `FAIL`, or `SKIP`. The package status is:

- `FAIL` if any check failed;
- otherwise `WARN` if any check warned;
- otherwise `PASS`.

A `SKIP` does not fail a package by itself. The important skip in the first batch
is the render artifact: no MP4 exists yet.

`publish_ready` is stricter. It becomes true only when the editorial gate permits
publication **and** a locally validated render exists **and** the package did not
fail. In this batch the editorial gate intentionally remains at
`human_review_required: true` and `human_signoff: false`, so every report says
`publish_ready: false`, even though QA passes.

## Check groups

### Identity and editorial

- Schema version, folder/id agreement, valid batch id, configured pillar.
- Non-empty title, central question, central fact, and takeaway; title length.
- No placeholder text.
- Editorial status is `source-checked`; human review remains required; sign-off is
  not falsely recorded.

### Hook, scene, and timing

- Hook is 1–3 seconds, short, and identical to the first scene's narration.
- Four to eight scenes; unique ids; contiguous timestamps.
- Positive durations that sum to the target duration.
- Original narration in every scene; no duplicate narration.
- Narration pace within configured words-per-second bounds.
- Forbidden medical-advice and overclaim language is absent.

### Visual safety and anatomy

- Every scene has a long, specific description, subject, motion, continuity, 9:16
  framing, and at least two avoid notes.
- No banned distress or aggression terms in the visual instruction.
- No request for text, logos, watermarks, or social handles inside the footage.
- Package visual policy covers style, anatomy, welfare, continuity, and the
  real-footage disclosure, and matches the channel policy exactly.
- Global negative prompt includes anatomy, watermark, and distress controls.

### Evidence and sources

- At least one claim; unique claim ids; every claim has text, evidence level,
  limits, and known source ids.
- Every research source supports at least one claim; every claim has one recorded
  verification verdict.
- Research question exactly matches the package question.
- Verification method, access route, myth/anecdote distinction, and uncertainty
  are recorded.
- Source titles, authors, years, tiers, HTTPS URLs, accessed dates, evidence
  summaries, limitations, DOI format, and PMID format are checked.
- Source domains must be allowed and not banned; tier-1 sources need a DOI or
  PMID.
- One to six sources per package.

### Metadata

Generated metadata is checked for title length and copy policy, description
length, the real-footage disclosure, educational disclaimer, `Sources:` section,
HTTPS links, source-list agreement, hashtags including `#Shorts`, tag budget,
visibility, `made_for_kids: false`, visual-mode/synthetic-media consistency,
duration, 9:16 resolution, and manual-only upload status. A real-footage package
must not claim AI-assisted visuals.

### Subtitles

- Cues start at zero and end at the target duration.
- Cue numbering is contiguous; no overlaps or non-positive durations.
- At most 42 characters per line and two lines per cue.
- Minimum on-screen time and maximum reading speed.
- Text reproduces the narration in order; SRT parses back to the generated cues.
- Cue timing is derived from narration length and scene boundaries, not guessed
  word-level timestamps. Human review still checks that the read feels natural.

### Duplicate detection

The package is checked against committed topic history:

- reused slug: `FAIL`;
- same package id in another batch: `FAIL`;
- title similarity ≥ 0.86: `FAIL`;
- combined topic similarity ≥ 0.66: `FAIL`;
- combined similarity ≥ 0.45: `WARN`;
- same primary source as an earlier topic without textual overlap: `WARN`.

Within a batch, every pair is scored with the same 0.66 fail / 0.45 warn
thresholds. The first batch has no failing or warning pairs.

### Render artifact

If a render exists at the path recorded in `viewmade-request.json`, local probing
requires an MP4 container, 1080x1920, a 9:16 ratio, 30–60 seconds, audio, and
plausible file size. A render that fails becomes `FAIL`; a missing render is
`SKIP`, not a pass.

For a real-footage render, QA also checks that every provider source URL appears
in the metadata description. A rendered package with no provider attribution is a
`FAIL`. The editorial-review disposition is recorded separately: a rejected
render keeps its technical media result but must never be published.

### Artifact hashes

The source and generated files are hashed and recorded in the QA report. Hashes
make accidental edits visible but are not signatures and do not prove authorship.

## Commands

```powershell
cddocs package build <slug>       # regenerate artifacts and QA
cddocs package validate <slug>    # validate existing artifacts
cddocs batch build <batch-id>     # build, pairwise dedup, register history
cddocs batch validate <batch-id>  # validate existing files without registering new topics
cddocs batch package <batch-id>   # validate, then create the review ZIP
```

`batch package` refuses to create an archive if the aggregate status is `FAIL`.
A `WARN` is allowed through, but the warning remains in the report and should be
reviewed before publishing.

## Remediation rules

- Fix the content or source. Do not edit generated QA JSON to manufacture a pass.
- Rebuild after editing `package.json`, `research.json`, configuration, or code
  that affects artifacts.
- Check that history registration happened only after a non-failing build.
- Treat a render `SKIP` as "not available", never as "verified".
- Do not upload because the batch is green. Watch the render and obtain human
  editorial approval first.
